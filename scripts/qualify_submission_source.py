"""Explicit live AWS adapter drill; synthetic keys only, no product SQL writes.

Run with the reviewed backend on PYTHONPATH. Private key files must already have
mode0400. This script never applies policies and never sweeps existing objects.
A failed run keeps its private JSONL journal for exact-target reconciliation.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import traceback

from botocore.exceptions import ClientError
from app.adapters.artifacts import create_artifact_store_bootstrap
from app.adapters.artifacts.source_cleanup import S3SubmissionSourceCleanup
from app.core.config import Settings
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import (
    ArtifactStoreNamespaceClaim, artifact_store_namespace_material,
    ArtifactPreconditionFailedError, ArtifactStoreUnavailableError, ArtifactIntegrityError,
)
from app.modules.artifacts.api.submission_intake import (
    SubmissionSourceLocation, SubmissionSourceUploadIntent, SubmissionSourceCompletion,
)

BUCKET = "flow-workstream-pilot-artifacts"
PREFIX = "workstream/artifacts"
RUNTIME = "arn:aws:iam::094032936130:user/workstream-storage"
CLEANUP = "arn:aws:iam::094032936130:user/workstream-source-cleanup"


def store_for(key_file, principal, *, scratch_root):
    limits = {f"artifact_admission_{scope}_maximum_bytes": 6 * 1024**2
              for scope in ("task", "producer", "project", "deployment")}
    settings = Settings(environment="production", artifact_store_backend="s3_compatible",
        artifact_s3_provider_profile="aws_s3", artifact_s3_region="eu-north-1",
        artifact_s3_bucket=BUCKET, artifact_s3_private_prefix=PREFIX,
        artifact_s3_credential_mode="aws_access_key", artifact_s3_runtime_user_arn=principal,
        artifact_s3_direct_user_credential_file=key_file,
        artifact_scratch_root=scratch_root,
        artifact_stream_buffer_bytes=65536, artifact_s3_operation_total_timeout_seconds=60,
        **limits)
    bootstrap = create_artifact_store_bootstrap(settings)
    identity = bootstrap.namespace_identity
    _, fingerprint = artifact_store_namespace_material(backend="s3_compatible",
        adapter_identity=bootstrap.identity, namespace_identity=identity)
    return bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(bootstrap.identity, identity, fingerprint))


@asynccontextmanager
async def lose_ack(store, operation, emit):
    original = store._client
    effect = {}

    class Client:
        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, name):
            method = getattr(self.inner, name)
            if name != operation:
                return method

            async def lost(**kwargs):
                result = await method(**kwargs)
                # Record the returned handle/version privately before injecting loss.
                effect.update(upload_id=result.get("UploadId"), version_id=result.get("VersionId"))
                emit("provider_effect_before_lost_ack", operation=operation, **effect)
                raise OSError("injected response loss after successful provider operation")
            return lost

    @asynccontextmanager
    async def wrapped():
        async with original() as client:
            yield Client(client)
    store._client = wrapped
    try:
        yield effect
    finally:
        store._client = original


async def denied(store, operation, **kwargs):
    async with store._client() as client:
        try:
            await getattr(client, operation)(Bucket=BUCKET, **kwargs)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"AccessDenied", "403"}:
                return
            raise AssertionError("unexpected denial classification") from None
    raise AssertionError("restricted operation unexpectedly permitted")


async def qualify(runtime, cleanup_store, emit, *, retained_artifact_key):
    cleanup = S3SubmissionSourceCleanup(cleanup_store)
    owned = set()
    # A missing key is not a permission-denial control. HEAD checks the same
    # GetObject permission without retrieving retained user bytes.
    async with runtime._client() as client:
        await client.head_object(Bucket=BUCKET, Key=retained_artifact_key)
    await denied(cleanup_store, "head_object", Key=retained_artifact_key)
    emit("passed", check="existing_retained_artifact_cleanup_read_denied")

    def intent():
        location = SubmissionSourceLocation(operation_id=new_record_id(), namespace_id="primary",
            namespace_fingerprint=runtime._expected_namespace_fingerprint(), provider_profile="aws-s3-v1")
        owned.add(location.operation_id)
        value = SubmissionSourceUploadIntent(location=location, upload_fence=1,
            maximum_raw_bytes=6 * 1024**2, declared_raw_bytes=None, part_bytes=5 * 1024**2,
            idle_timeout_seconds=30.0, upload_deadline_at=datetime.now(UTC) + timedelta(minutes=10))
        emit("owned_target_before_provider_io", intent=value.model_dump(mode="json"))
        return value

    async def completion(value, body):
        upload = await runtime.begin_source_upload(value)
        emit("upload", upload=upload.model_dump(mode="json"))
        parts = []
        for offset in range(0, len(body), value.part_bytes):
            parts.append(await runtime.upload_source_part(upload, len(parts) + 1, body[offset:offset + value.part_bytes]))
        result = SubmissionSourceCompletion(upload=upload, parts=tuple(parts),
            raw_sha256="sha256:" + hashlib.sha256(body).hexdigest(), raw_byte_count=len(body))
        emit("completion_ready", completion=result.model_dump(mode="json"))
        return result

    async def read_exact(source, body):
        digest, count = hashlib.sha256(), 0
        async for chunk in runtime.open_source(source):
            assert 0 < len(chunk) <= 65536
            count += len(chunk)
            digest.update(chunk)
        assert count == len(body) and digest.hexdigest() == hashlib.sha256(body).hexdigest()

    async def remove_owned(source, upload):
        assert source.location.operation_id in owned and source.location == upload.intent.location
        result = await cleanup.remove(source, upload)
        assert result.object_absent and result.writes_settled and result.parts_absent
        emit("exact_source_removal_confirmed", source=source.model_dump(mode="json"))

    body = b"qualification-source\n" * (5 * 1024**2 // 21 + 2000)
    first_intent, retained_intent = intent(), intent()
    first_upload = await completion(first_intent, body)
    first = await runtime.complete_source_upload(first_upload)
    emit("sealed", source=first.model_dump(mode="json"))
    assert first.provider_generation not in {"", "null"} and len(first_upload.parts) == 2
    await read_exact(first, body)
    assert await runtime.observe_source_upload(first_upload) == first
    retained_upload = await completion(retained_intent, body)
    retained = await runtime.complete_source_upload(retained_upload)
    emit("sealed", source=retained.model_dump(mode="json"))
    assert first.raw_sha256 == retained.raw_sha256 and first.location != retained.location
    competitor = await completion(first_intent.model_copy(update={"upload_fence": 2}), b"different")
    try:
        await runtime.complete_source_upload(competitor)
    except ArtifactPreconditionFailedError:
        pass
    else:
        raise AssertionError("conditional source overwrite accepted")
    key = runtime._source_key(first.location)
    await denied(runtime, "delete_object", Key=key, VersionId=first.provider_generation)
    await denied(runtime, "abort_multipart_upload", Key=key, UploadId=competitor.upload.provider_upload_id)
    await cleanup_store.request_source_abort(competitor.upload)
    assert await cleanup_store.source_upload_parts_absent(competitor.upload)
    await denied(cleanup_store, "put_object", Key=key, Body=b"forbidden", IfNoneMatch="*")
    emit("passed", check="conditional_versioned_multipart_and_separate_principals")
    async with lose_ack(cleanup_store, "delete_object", emit) as delete_effect:
        try:
            await remove_owned(first, first_upload.upload)
        except ArtifactStoreUnavailableError:
            pass
        else:
            raise AssertionError("lost deletion response did not remain uncertain")
    assert delete_effect["version_id"] == first.provider_generation
    await remove_owned(first, first_upload.upload)
    await read_exact(retained, body)
    emit("passed", check="lost_delete_ack_and_independent_retained_source_survival")
    await remove_owned(retained, retained_upload.upload)

    missing_handle = intent()
    async with lose_ack(runtime, "create_multipart_upload", emit) as begin_effect:
        try:
            await runtime.begin_source_upload(missing_handle)
        except ArtifactStoreUnavailableError:
            pass
        else:
            raise AssertionError("lost begin response did not remain uncertain")
    handles = await cleanup_store.discover_source_uploads(missing_handle)
    assert len(handles) == 1 and handles[0].provider_upload_id == begin_effect["upload_id"]
    emit("discovered_handles_before_abort", uploads=[v.model_dump(mode="json") for v in handles])
    await cleanup_store.request_source_abort(handles[0])
    assert await cleanup_store.source_upload_parts_absent(handles[0])
    assert await cleanup_store.discover_source_uploads(missing_handle) == ()
    emit("passed", check="lost_begin_ack_exact_handle_discovery_and_abort")

    lost_completion = await completion(intent(), b"response-loss-source")
    async with lose_ack(runtime, "complete_multipart_upload", emit) as complete_effect:
        try:
            await runtime.complete_source_upload(lost_completion)
        except ArtifactStoreUnavailableError:
            pass
        else:
            raise AssertionError("lost completion response did not remain uncertain")
    recovered = await runtime.observe_source_upload(lost_completion)
    assert recovered is not None and recovered.provider_generation == complete_effect["version_id"]
    emit("recovered_sealed", source=recovered.model_dump(mode="json"))
    await read_exact(recovered, b"response-loss-source")
    try:
        await runtime.observe_source_upload(lost_completion.model_copy(update={"raw_sha256": "sha256:" + "0" * 64}))
    except ArtifactIntegrityError:
        pass
    else:
        raise AssertionError("substituted raw hash accepted")
    await remove_owned(recovered, lost_completion.upload)
    emit("passed", check="lost_completion_ack_exact_bytes_and_hash_substitution_refusal")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-key-file", required=True, type=Path)
    parser.add_argument("--cleanup-key-file", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--retained-artifact-key", required=True)
    args = parser.parse_args()
    if re.fullmatch(re.escape(PREFIX) + r"/sha256/[0-9a-f]{2}/[0-9a-f]{62}", args.retained_artifact_key) is None:
        parser.error("retained artifact key must be an existing canonical SHA key")
    if not __debug__:
        parser.error("qualification requires Python assertions enabled; do not use -O")
    # Never load the invalid default AWS profile or ambient credentials.
    for key in tuple(os.environ):
        if key.startswith(("AWS_", "BOTOCORE_")):
            os.environ.pop(key)
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    runtime = cleanup_store = None
    with os.fdopen(fd, "w") as output, tempfile.TemporaryDirectory(prefix="workstream-source-qualification-") as scratch:
        def emit(event, **facts):
            output.write(json.dumps({"event": event, "at": datetime.now(UTC).isoformat(), **facts}) + "\n")
            output.flush()
            os.fsync(output.fileno())
        try:
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            emit("started", commit=head, bucket=BUCKET, prefix=PREFIX, runtime=RUNTIME, cleanup=CLEANUP,
                 script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
            runtime = store_for(args.runtime_key_file.resolve(), RUNTIME, scratch_root=Path(scratch))
            cleanup_store = store_for(args.cleanup_key_file.resolve(), CLEANUP, scratch_root=Path(scratch))
            asyncio.run(asyncio.wait_for(qualify(runtime, cleanup_store, emit,
                retained_artifact_key=args.retained_artifact_key), timeout=900))
            emit("completed", result="passed")
            print("AWS source adapter qualification passed; see private report")
        except BaseException as error:
            emit("failed", error_type=type(error).__name__,
                 assertion=str(error) if type(error) is AssertionError else None,
                 frames=[{"file": Path(frame.filename).name, "line": frame.lineno,
                          "function": frame.name} for frame in traceback.extract_tb(error.__traceback__)])
            print("AWS source adapter qualification failed; retain journal and owned targets")
            raise SystemExit(1) from None
        finally:
            if runtime is not None:
                runtime.close()
            if cleanup_store is not None:
                cleanup_store.close()


if __name__ == "__main__":
    main()
