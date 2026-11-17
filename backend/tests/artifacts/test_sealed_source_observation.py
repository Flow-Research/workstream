"""Exact-version availability proof must not reread or adopt another ZIP."""
from contextlib import asynccontextmanager
import os

import pytest

from app.interfaces.artifacts import (
    ArtifactIntegrityError, ArtifactObjectMissingError, ArtifactOperationConflictError,
    ArtifactStoreUnavailableError, SealedSourceObservation,
)
from app.modules.artifacts.api.submission_intake import SubmissionSourceUpload
from tests.test_local_artifact_store import (
    initialize_local_store, local_source_completion, local_source_intent,
)
from tests.test_s3_artifact_store import (
    MINIO_BUCKET, source_completion, source_intent, _client_error,
    source_store as source_store,
    provision_minio_bucket as provision_minio_bucket,
)

pytestmark = pytest.mark.asyncio


async def test_local_abort_does_not_confirm_retained_staging_bytes(tmp_path):
    root = tmp_path / "store"
    store = initialize_local_store(root=root)
    try:
        upload = await store.begin_source_upload(local_source_intent(store))
        await store.upload_source_part(upload, 1, b"retained-part")
        await store.request_source_abort(upload)
        assert await store.source_upload_parts_absent(upload) is False
        assert (root / "objects" / upload.intent.location.object_ref).read_bytes() == b"retained-part"
        foreign = upload.model_copy(update={"provider_upload_id": "foreign"})
        with pytest.raises(ArtifactOperationConflictError):
            await store.source_upload_parts_absent(foreign)
    finally:
        store.close()


@pytest.mark.parametrize("code,status,expected", [
    ("NoSuchUpload", 404, True),
    ("NoSuchUpload", 403, ArtifactStoreUnavailableError),
    ("NoSuchBucket", 404, ArtifactStoreUnavailableError),
    ("NoSuchKey", 404, ArtifactObjectMissingError),
    ("AccessDenied", 403, ArtifactStoreUnavailableError),
    (None, None, False),
])
async def test_parts_absence_requires_exact_upload_missing(source_store, monkeypatch, code, status, expected):
    store = source_store
    upload = SubmissionSourceUpload(intent=source_intent(store), provider_upload_id="owned-upload")
    seen = []

    class PartsOnly:
        async def list_parts(self, **kwargs):
            seen.append(kwargs)
            if code:
                raise _client_error(code, status)
            return {"Parts": [], "IsTruncated": False}

    @asynccontextmanager
    async def client():
        yield PartsOnly()

    monkeypatch.setattr(store, "_client", client)
    if isinstance(expected, type):
        with pytest.raises(expected):
            await store.source_upload_parts_absent(upload)
    else:
        assert await store.source_upload_parts_absent(upload) is expected
    assert seen == [dict(Bucket=MINIO_BUCKET, Key=store._source_key(upload.intent.location),
                         UploadId="owned-upload", MaxParts=1)]
    foreign = upload.model_copy(update={"intent": upload.intent.model_copy(update={
        "location": upload.intent.location.model_copy(update={"namespace_fingerprint": "sha256:" + "0" * 64}),
    })})
    with pytest.raises(ArtifactOperationConflictError):
        await store.source_upload_parts_absent(foreign)
    assert len(seen) == 1


async def test_local_observation_uses_seal_and_inode_without_body_read(tmp_path, monkeypatch):
    store = initialize_local_store(root=tmp_path / "store")
    try:
        upload = await store.begin_source_upload(local_source_intent(store))
        completion = await local_source_completion(store, upload, b"original")
        source = await store.complete_source_upload(completion)
        def forbid_body(*args, **kwargs):
            pytest.fail("metadata observation read source bytes")
        path = tmp_path / "store" / "objects" / source.location.object_ref
        bundle_stat = path.stat()
        original_read = os.read
        def guarded_read(descriptor, size):
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) == (bundle_stat.st_dev, bundle_stat.st_ino):
                pytest.fail("metadata observation read source bytes")
            return original_read(descriptor, size)
        monkeypatch.setattr(os, "pread", forbid_body)
        monkeypatch.setattr(os, "read", guarded_read)
        observed = await store.observe_sealed_source(source)
        assert observed == SealedSourceObservation(
            source.location, source.provider_generation, len(b"original"), source.sealed_upload_fence,
        )
        path = tmp_path / "store" / "objects" / source.location.object_ref
        replacement = path.with_name("replacement")
        replacement.write_bytes(b"original")
        replacement.chmod(0o400)
        replacement.replace(path)
        with pytest.raises(ArtifactIntegrityError, match="generation"):
            await store.observe_sealed_source(source)
        path.unlink()
        assert await store.observe_sealed_source(source) is None
    finally:
        store.close()


async def test_s3_observation_pins_old_version_without_body_io(source_store, monkeypatch):
    store = source_store
    source = await store.complete_source_upload(await source_completion(store, b"original"))
    original_client = store._client
    async with original_client() as client:
        await client.put_object(Bucket=MINIO_BUCKET, Key=store._source_key(source.location), Body=b"newer")
    seen = []
    class HeadOnly:
        def __init__(self, client):
            self.client = client
        async def head_object(self, **kwargs):
            seen.append(kwargs)
            return await self.client.head_object(**kwargs)
    @asynccontextmanager
    async def head_only():
        async with original_client() as client:
            yield HeadOnly(client)
    monkeypatch.setattr(store, "_client", head_only)
    assert await store.observe_sealed_source(source) == SealedSourceObservation(
        source.location, source.provider_generation, len(b"original"), source.sealed_upload_fence,
    )
    assert seen == [dict(Bucket=MINIO_BUCKET, Key=store._source_key(source.location),
                         VersionId=source.provider_generation)]
    async with original_client() as client:
        await client.delete_object(Bucket=MINIO_BUCKET, Key=store._source_key(source.location),
                                   VersionId=source.provider_generation)
    assert await store.observe_sealed_source(source) is None


@pytest.mark.parametrize("field,value", [("VersionId", "another-version"), ("ContentLength", 99),
                                          ("Metadata", {"operation-id": "foreign"})])
async def test_s3_observation_refuses_inconsistent_version_metadata(source_store, monkeypatch, field, value):
    store = source_store
    source = await store.complete_source_upload(await source_completion(store, b"original"))
    original_client = store._client
    class ChangedHead:
        def __init__(self, client):
            self.client = client
        async def head_object(self, **kwargs):
            response = await self.client.head_object(**kwargs)
            return dict(response, **{field: value})
    @asynccontextmanager
    async def changed_client():
        async with original_client() as client:
            yield ChangedHead(client)
    monkeypatch.setattr(store, "_client", changed_client)
    with pytest.raises(ArtifactIntegrityError, match="custody"):
        await store.observe_sealed_source(source)


@pytest.mark.parametrize("field,value", [
    ("location", {}), ("provider_generation", ""), ("provider_generation", "null"),
    ("provider_generation", 1), ("raw_byte_count", True), ("raw_byte_count", 0),
    ("raw_byte_count", 2**64), ("sealed_upload_fence", True), ("sealed_upload_fence", 0),
])
async def test_observation_rejects_malformed_metadata(tmp_path, field, value):
    store = initialize_local_store(root=tmp_path / "store")
    try:
        fields = dict(location=local_source_intent(store).location,
                      provider_generation="version", raw_byte_count=8, sealed_upload_fence=1)
        fields[field] = value
        with pytest.raises(ValueError):
            SealedSourceObservation(**fields)
    finally:
        store.close()
