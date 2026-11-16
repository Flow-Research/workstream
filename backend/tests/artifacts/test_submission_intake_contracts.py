"""Exact command/source identity proof; no database or provider claims."""

import hashlib
import asyncio
from datetime import UTC, datetime, timedelta
import json
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_archive import MAXIMUM_SUBMISSION_ZIP_BYTES
from app.modules.artifacts.api.submission_intake import (
    SealedSubmissionSource,
    SubmissionIntakeMetadata,
    SubmissionSourceLocation,
    SubmissionSourceCompletion,
    SubmissionSourcePart,
    SubmissionSourceUpload,
    SubmissionSourceUploadIntent,
)
from app.interfaces.artifacts import (
    ArtifactInputMismatchError, ArtifactLimitExceededError, ArtifactStoreUnavailableError,
)
from app.modules.artifacts.intake.streaming import receive_submission_source, SubmissionUploadTimeout


OPERATION = UUID("019a0000-0000-7000-8000-000000000001")
NAMESPACE_FINGERPRINT = "sha256:" + "c" * 64
TASK = UUID("019a0000-0000-7000-8000-000000000003")
ASSIGNMENT = UUID("019a0000-0000-7000-8000-000000000004")
PREDECESSOR = UUID("019a0000-0000-7000-8000-000000000005")
REVISION = UUID("019a0000-0000-7000-8000-000000000006")
SHA = "sha256:" + "a" * 64


def metadata(**updates):
    return SubmissionIntakeMetadata.model_validate({
        "task_id": TASK, "assignment_id": ASSIGNMENT, **updates,
    })


@pytest.mark.parametrize("missing", ["capacity", "runtime", "upload_total_seconds", "upload_idle_seconds",
    "foreground_lease_seconds", "heartbeat_seconds", "replay_total_seconds", "part_bytes"])
def test_submission_execution_profile_requires_explicit_deployment_values(missing):
    from app.modules.artifacts.api.submission_command import SubmissionExecutionProfile
    from app.modules.checkers.api.source_contracts import source_contracts_context
    from app.adapters.artifacts import selected_pre_submit_source_contracts
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation

    values = dict(capacity={"maximum_total_bytes": 1_000_000},
        runtime=_source_reservation().runtime_profile.model_dump(mode="json"),
        upload_total_seconds=300.0, upload_idle_seconds=10.0, foreground_lease_seconds=60.0,
        heartbeat_seconds=10.0, replay_total_seconds=30.0, part_bytes=5 * 1024**2)
    context = source_contracts_context(selected_pre_submit_source_contracts())
    assert SubmissionExecutionProfile.model_validate(values, context=context).upload_total_seconds == 300.0
    del values[missing]
    with pytest.raises(ValidationError) as caught:
        SubmissionExecutionProfile.model_validate(values, context=context)
    assert any(error["loc"] == (missing,) and error["type"] == "missing" for error in caught.value.errors())


def location(**updates):
    return SubmissionSourceLocation.model_validate({
        "operation_id": OPERATION, "namespace_id": "primary",
        "namespace_fingerprint": NAMESPACE_FINGERPRINT,
        "provider_profile": "aws-s3-v1", **updates,
    })


def source(**updates):
    return SealedSubmissionSource.model_validate({
        "location": location(), "provider_generation": "opaque/version+1=",
        "raw_sha256": SHA, "raw_byte_count": 123, "sealed_upload_fence": 1,
        **updates,
    })


def test_metadata_canonical_fixture_and_round_trip_preserve_exact_packet():
    value = metadata(summary="A  B", contributor_attestation="I did this.")
    # Independent literal fixture fixes field names, nulls and domain separation.
    canonical = (
        '{"assignment_id":"019a0000-0000-7000-8000-000000000004",'
        '"contributor_attestation":"I did this.","predecessor_submission_id":null,'
        '"revision_preparation_id":null,"revision_preparation_sha256":null,'
        '"schema_version":"workstream.submission_intake_metadata.v1",'
        '"summary":"A  B","task_id":"019a0000-0000-7000-8000-000000000003"}'
    )
    assert value.metadata_sha256() == "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    restored = SubmissionIntakeMetadata.model_validate_json(value.model_dump_json())
    assert restored == value
    assert restored.summary == "A  B"
    assert metadata().summary == metadata().contributor_attestation == ""
    assert metadata(summary="x" * 65536).summary == "x" * 65536


@pytest.mark.parametrize("field", ["task_id", "assignment_id", "predecessor_submission_id",
                                  "summary", "contributor_attestation",
                                  "revision_preparation_id", "revision_preparation_sha256"])
def test_every_metadata_selector_participates_in_replay_identity(field):
    original = metadata(predecessor_submission_id=PREDECESSOR,
                        revision_preparation_id=REVISION, revision_preparation_sha256=SHA)
    replacement = (
        uuid4() if field.endswith("_id") else
        "sha256:" + "b" * 64 if field.endswith("_sha256") else "changed"
    )
    changed = SubmissionIntakeMetadata.model_validate({**original.model_dump(), field: replacement})
    assert changed.metadata_sha256() != original.metadata_sha256()


@pytest.mark.parametrize("text", [" leading", "trailing ", "line\nbreak", "tab\tvalue",
                                  "café", "\x7f", "x" * 65537])
@pytest.mark.parametrize("field", ["summary", "contributor_attestation"])
def test_packet_rejects_unrepresentable_headers_without_normalization(field, text):
    with pytest.raises(ValidationError):
        metadata(**{field: text})


@pytest.mark.parametrize("updates", [
    {"revision_preparation_id": REVISION},
    {"revision_preparation_sha256": SHA},
    {"revision_preparation_id": REVISION, "revision_preparation_sha256": SHA},
    {"predecessor_submission_id": PREDECESSOR, "revision_preparation_id": REVISION},
    {"predecessor_submission_id": PREDECESSOR, "revision_preparation_sha256": SHA},
])
def test_revision_acknowledgement_cannot_be_partial_or_initial(updates):
    with pytest.raises(ValidationError):
        metadata(**updates)
    # Whether a revision requires acknowledgement is still a TASK policy check.
    assert metadata(predecessor_submission_id=PREDECESSOR).revision_preparation_id is None


def test_source_address_is_operation_bound_and_opaque_generation_round_trips():
    value = source()
    assert value.location.object_ref == f"submission-source/v1/{OPERATION}/bundle.zip"
    assert SealedSubmissionSource.model_validate_json(value.model_dump_json()) == value
    assert value.provider_generation == "opaque/version+1="
    assert value.raw_sha256 == SHA
    # The raw identity is not the identity of the complete source descriptor.
    assert value.source_sha256() != value.raw_sha256
    other = source(location=location(operation_id=REVISION))
    assert other.raw_sha256 == value.raw_sha256
    assert other.location.object_ref != value.location.object_ref
    assert other.source_sha256() != value.source_sha256()


@pytest.mark.parametrize("updates", [
    {"location": location(namespace_fingerprint="sha256:" + "d" * 64)},
    {"location": location(provider_profile="qualified-managed-v1")},
    {"provider_generation": "other-version"},
    {"raw_sha256": "sha256:" + "b" * 64},
    {"raw_byte_count": 124},
    {"sealed_upload_fence": 2},
])
def test_source_identity_detects_substitution_of_every_custody_fact(updates):
    assert source(**updates).source_sha256() != source().source_sha256()


@pytest.mark.parametrize("updates", [
    {"raw_byte_count": 0}, {"raw_byte_count": MAXIMUM_SUBMISSION_ZIP_BYTES + 1},
    {"raw_byte_count": True}, {"raw_byte_count": "123"},
    {"sealed_upload_fence": 0}, {"sealed_upload_fence": True},
    {"provider_generation": ""}, {"provider_generation": "null"},
    {"provider_generation": None}, {"raw_sha256": "a" * 64},
    {"raw_sha256": "sha256:" + "A" * 64}, {"media_type": "application/octet-stream"},
    {"signed_url": "https://storage.invalid/private?credential=secret"},
    {"host_path": "/tmp/bundle.zip"}, {"manifest_sha256": SHA},
])
def test_sealed_source_rejects_unsealed_coercive_or_authority_bearing_inputs(updates):
    with pytest.raises(ValidationError):
        source(**updates)
    assert source(raw_byte_count=MAXIMUM_SUBMISSION_ZIP_BYTES).raw_byte_count == 524288000


@pytest.mark.parametrize("updates", [
    {"operation_id": uuid4()}, {"namespace_id": uuid4()},
    {"namespace_id": "other"}, {"namespace_fingerprint": "invalid"},
    {"operation_id": str(OPERATION)}, {"provider_profile": "https://storage.invalid"},
    {"object_ref": "submission-source/v1/foreign/bundle.zip"},
    {"idempotency_key": OPERATION},
])
def test_location_cannot_take_a_caller_path_or_nonrecord_selector(updates):
    with pytest.raises(ValidationError):
        location(**updates)


def test_frozen_values_revalidate_nested_instances_and_reject_unknown_command_fields():
    value = source()
    with pytest.raises(ValidationError):
        value.location.operation_id = REVISION
    with pytest.raises(ValidationError):
        value.raw_byte_count = 42
    with pytest.raises(ValidationError):
        source(location=location().model_copy(update={"operation_id": uuid4()}))
    with pytest.raises(ValidationError):
        metadata(bearer_token="secret")
    with pytest.raises(ValidationError):
        SubmissionIntakeMetadata.model_validate_json(json.dumps({
            "task_id": str(TASK), "assignment_id": str(ASSIGNMENT), "summary": 1,
        }))


def test_source_accepts_existing_art_namespace_and_binds_its_fingerprint(tmp_path):
    """Use ART's actual singleton and adapter-derived fingerprint, not a fake UUID."""
    from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
    from app.core.config import Settings
    from app.modules.artifacts.models import ArtifactStorageNamespace
    from app.modules.artifacts.service import (
        ARTIFACT_STORAGE_NAMESPACE_ID,
        artifact_storage_namespace_spec,
    )
    from tests.artifact_store_helpers import artifact_admission_limit_settings

    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    settings = Settings(
        **artifact_admission_limit_settings(), environment="test",
        artifact_store_backend="local", artifact_local_root=root,
        artifact_scratch_root=tmp_path / "scratch", artifact_scratch_minimum_free_bytes=0,
    )
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(
        root=root, buffer_bytes=settings.artifact_stream_buffer_bytes,
        lock_timeout_seconds=settings.artifact_operation_lock_timeout_seconds,
    ))
    try:
        spec = artifact_storage_namespace_spec(settings, bootstrap)
    finally:
        bootstrap.close()
    namespace = ArtifactStorageNamespace(
        id=ARTIFACT_STORAGE_NAMESPACE_ID, backend=spec.backend, adapter=spec.adapter,
        provider_profile=spec.provider_profile, namespace_descriptor=spec.namespace_descriptor,
        namespace_fingerprint=spec.namespace_fingerprint,
    )
    bound = location(namespace_id=namespace.id, namespace_fingerprint=namespace.namespace_fingerprint,
                     provider_profile=namespace.provider_profile)
    assert bound.namespace_id == "primary"
    assert bound.namespace_fingerprint == spec.namespace_fingerprint
    assert source(location=bound).source_sha256() != source(location=location(
        namespace_id=namespace.id, namespace_fingerprint="sha256:" + "d" * 64,
        provider_profile=namespace.provider_profile,
    )).source_sha256()


def upload_value(**updates):
    return SubmissionSourceUpload(
        intent=SubmissionSourceUploadIntent.model_validate({
            "location": location(), "upload_fence": 1,
            "maximum_raw_bytes": 6 * 1024 * 1024, "part_bytes": 5 * 1024 * 1024,
            "idle_timeout_seconds": 20.0,
            "upload_deadline_at": datetime.now(UTC) + timedelta(minutes=1), **updates,
        }), provider_upload_id="opaque-upload",
    )


@pytest.mark.asyncio
async def test_source_stream_backpressures_and_hashes_original_bytes_without_completing():
    first_part_started, release = asyncio.Event(), asyncio.Event()
    reads = 0
    part_sizes = []

    class Store:
        async def upload_source_part(self, upload, number, data, **kwargs):
            part_sizes.append(len(data))
            if number == 1:
                first_part_started.set()
                await release.wait()
            return SubmissionSourcePart(number=number, byte_count=len(data), provider_etag=f"part-{number}")

    async def chunks():
        nonlocal reads
        for chunk in [b"a" * (1024 * 1024)] * 5 + [b"end"]:
            reads += 1
            yield chunk

    task = asyncio.create_task(receive_submission_source(Store(), upload_value(), chunks()))
    try:
        await asyncio.wait_for(first_part_started.wait(), 2)
        assert reads == 5  # The sixth input chunk cannot outrun a pending provider write.
        assert not task.done()
        release.set()
        completion = await asyncio.wait_for(task, 2)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert reads == 6
    assert part_sizes == [5 * 1024 * 1024, 3]
    assert completion.raw_sha256 == "sha256:" + hashlib.sha256(b"a" * (5 * 1024 * 1024) + b"end").hexdigest()
    assert completion.raw_byte_count == 5 * 1024 * 1024 + 3


@pytest.mark.asyncio
@pytest.mark.parametrize("updates,chunks,error", [
    ({}, [], ArtifactInputMismatchError),
    ({"declared_raw_bytes": 4}, [b"abc"], ArtifactInputMismatchError),
    ({"declared_raw_bytes": 2}, [b"abc"], ArtifactInputMismatchError),
    ({"maximum_raw_bytes": 2}, [b"abc"], ArtifactLimitExceededError),
    ({}, [b"a" * (1024 * 1024 + 1)], ArtifactLimitExceededError),
])
async def test_invalid_stream_cannot_send_final_part_or_produce_eof(updates, chunks, error):
    class NoWrites:
        async def upload_source_part(self, *args, **kwargs):
            pytest.fail("invalid small input reached storage")

    async def ingress():
        for chunk in chunks:
            yield chunk

    with pytest.raises(error):
        await receive_submission_source(NoWrites(), upload_value(**updates), ingress())


@pytest.mark.parametrize("parts,count", [
    ((SubmissionSourcePart(number=2, byte_count=1, provider_etag="x"),), 1),
    ((SubmissionSourcePart(number=1, byte_count=1, provider_etag="x"),), 2),
    ((SubmissionSourcePart(number=1, byte_count=1, provider_etag="x"),
      SubmissionSourcePart(number=2, byte_count=1, provider_etag="y")), 2),
])
def test_completion_rejects_missing_short_nonfinal_or_count_mismatched_parts(parts, count):
    with pytest.raises(ValidationError):
        SubmissionSourceCompletion(upload=upload_value(), parts=parts, raw_sha256=SHA, raw_byte_count=count)


@pytest.mark.asyncio
async def test_source_stream_idle_deadline_stops_without_emitting_completion():
    stopped = asyncio.Event()

    async def stalled_input():
        try:
            await asyncio.Event().wait()
            yield b"never"
        finally:
            stopped.set()

    with pytest.raises(ArtifactStoreUnavailableError):
        await receive_submission_source(object(), upload_value(idle_timeout_seconds=0.01), stalled_input())
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_source_stream_total_deadline_cancels_an_inflight_part_without_completion():
    stopped = asyncio.Event()

    class SlowStore:
        async def upload_source_part(self, *args, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    async def ingress():
        yield b"abc"

    upload = upload_value(upload_deadline_at=datetime.now(UTC) + timedelta(seconds=0.2))
    with pytest.raises(ArtifactStoreUnavailableError):
        await receive_submission_source(SlowStore(), upload, ingress())
    assert stopped.is_set()


@pytest.mark.parametrize("field,value", [
    ("raw_sha256", "sha256:" + "f" * 64), ("raw_byte_count", 2), ("sealed_upload_fence", 2),
])
def test_foreground_upload_source_must_match_committed_receipt_facts(field, value):
    from app.interfaces.artifacts import ArtifactIntegrityError
    from app.modules.artifacts.intake.foreground_upload import ForegroundSourceUpload
    upload = upload_value()
    completion = SubmissionSourceCompletion(upload=upload,
        parts=(SubmissionSourcePart(number=1, byte_count=1, provider_etag="part"),),
        raw_sha256="sha256:" + "a" * 64, raw_byte_count=1)
    original = SealedSubmissionSource(location=upload.intent.location, provider_generation="version",
        raw_sha256=completion.raw_sha256, raw_byte_count=1, sealed_upload_fence=upload.intent.upload_fence)
    assert ForegroundSourceUpload._bind_source(completion, original) == original
    with pytest.raises(ArtifactIntegrityError, match="identity mismatch"):
        ForegroundSourceUpload._bind_source(completion, original.model_copy(update={field: value}))


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan"), True, "60", 1e30])
def test_foreground_upload_rejects_unbounded_or_coercive_deadlines(seconds):
    from app.modules.artifacts.intake.foreground_upload import _duration
    with pytest.raises(ValueError):
        _duration(seconds)


@pytest.mark.parametrize("duration,interval", [(0, 1), (1, 0), (1, 1), (1, 2), (-1, 1)])
def test_foreground_lease_rejects_invalid_timing(duration, interval):
    from app.modules.artifacts.intake.foreground_lease import ForegroundIntakeLease
    with pytest.raises(ValueError):
        ForegroundIntakeLease(None, None, lease_duration=timedelta(seconds=duration),
                              heartbeat_interval=timedelta(seconds=interval))


async def test_foreground_lease_committed_command_wins_simultaneous_pulse_failure(monkeypatch):
    from app.modules.artifacts.intake.foreground_lease import ForegroundIntakeLease
    from app.modules.artifacts.intake.repository import IntakeCustodyConflict
    runner = ForegroundIntakeLease(None, None, lease_duration=timedelta(seconds=2),
                                  heartbeat_interval=timedelta(seconds=0.1))
    release = asyncio.Event()
    calls = 0

    async def renew(*owner):
        nonlocal calls
        calls += 1
        if calls == 1:
            return 1
        release.set()
        raise IntakeCustodyConflict("fixture_after_commit")

    async def command(*owner):
        await release.wait()
        return "committed"

    monkeypatch.setattr(runner, "_renew", renew)
    assert await runner.run(new_record_id(), new_record_id(), 1, command) == "committed"


@pytest.mark.asyncio
async def test_discard_replay_hashes_exact_raw_bytes_across_chunk_boundaries():
    from app.modules.artifacts.intake.streaming import hash_submission_replay

    payload = b"PK\x03\x04\x00\xffraw ZIP bytes"

    async def chunks():
        for chunk in (payload[:3], b"", payload[3:8], payload[8:]):
            yield chunk

    receipt = await hash_submission_replay(
        chunks(), maximum_raw_bytes=100, declared_raw_bytes=len(payload),
        idle_timeout_seconds=1, deadline_at=datetime.now(UTC) + timedelta(seconds=2),
    )
    assert receipt.raw_byte_count == len(payload)
    assert receipt.raw_sha256 == "sha256:" + hashlib.sha256(payload).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize("updates,payload,error", [
    ({}, [], ArtifactInputMismatchError),
    ({"declared_raw_bytes": 4}, [b"abc"], ArtifactInputMismatchError),
    ({"declared_raw_bytes": 2}, [b"abc"], ArtifactInputMismatchError),
    ({"maximum_raw_bytes": 2}, [b"abc"], ArtifactLimitExceededError),
    ({"maximum_raw_bytes": 2 * 1024 * 1024}, [b"x" * (1024 * 1024 + 1)], ArtifactLimitExceededError),
    ({}, [bytearray(b"abc")], ArtifactInputMismatchError),
])
async def test_discard_replay_enforces_raw_ingress_contract(updates, payload, error):
    from app.modules.artifacts.intake.streaming import hash_submission_replay

    async def chunks():
        for chunk in payload:
            yield chunk

    limits = dict(maximum_raw_bytes=100, declared_raw_bytes=None,
                  idle_timeout_seconds=1, deadline_at=datetime.now(UTC) + timedelta(seconds=2))
    with pytest.raises(error):
        await hash_submission_replay(chunks(), **(limits | updates))


@pytest.mark.asyncio
@pytest.mark.parametrize("total_deadline", [False, True])
async def test_discard_replay_deadlines_drain_pending_body_read(total_deadline):
    from app.modules.artifacts.intake.streaming import hash_submission_replay

    stopped = asyncio.Event()

    async def chunks():
        try:
            await asyncio.Event().wait()
            yield b"never"
        finally:
            stopped.set()

    with pytest.raises(SubmissionUploadTimeout):
        await hash_submission_replay(
            chunks(), maximum_raw_bytes=100, declared_raw_bytes=None,
            idle_timeout_seconds=10 if total_deadline else 0.01,
            deadline_at=datetime.now(UTC) + timedelta(seconds=0.02 if total_deadline else 10),
        )
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_discard_replay_cancellation_drains_read_and_remains_cancellation():
    from app.modules.artifacts.intake.streaming import hash_submission_replay

    started, stopped = asyncio.Event(), asyncio.Event()

    async def chunks():
        try:
            started.set()
            await asyncio.Event().wait()
            yield b"never"
        finally:
            stopped.set()

    task = asyncio.create_task(hash_submission_replay(
        chunks(), maximum_raw_bytes=100, declared_raw_bytes=None,
        idle_timeout_seconds=10, deadline_at=datetime.now(UTC) + timedelta(seconds=10),
    ))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["replay", "upload"])
@pytest.mark.parametrize("deadline", ["idle", "total"])
@pytest.mark.parametrize("stall_at_eof", [False, True])
async def test_non_yielding_ingress_cannot_escape_deadline(path, deadline, stall_at_eof):
    import time
    from app.modules.artifacts.intake.streaming import hash_submission_replay

    class NoWrites:
        async def upload_source_part(self, *args, **kwargs):
            pytest.fail("expired ingress reader reached provider storage")

    async def chunks():
        if not stall_at_eof:
            time.sleep(0.05)
        yield b"abc"
        if stall_at_eof:
            time.sleep(0.05)

    idle = 0.01 if deadline == "idle" else 10
    expires = datetime.now(UTC) + timedelta(seconds=0.01 if deadline == "total" else 10)
    with pytest.raises(SubmissionUploadTimeout):
        if path == "replay":
            await hash_submission_replay(chunks(), maximum_raw_bytes=100, declared_raw_bytes=None,
                                         idle_timeout_seconds=idle, deadline_at=expires)
        else:
            # This small body must not reach a provider when its reader expires.
            await receive_submission_source(NoWrites(), upload_value(
                idle_timeout_seconds=idle, upload_deadline_at=expires,
            ), chunks())


@pytest.mark.asyncio
async def test_non_yielding_final_part_cannot_return_completion_after_deadline():
    import time

    class BufferedStore:
        async def upload_source_part(self, upload, number, data, **kwargs):
            time.sleep(0.05)
            return SubmissionSourcePart(number=number, byte_count=len(data), provider_etag="late")

    async def chunks():
        yield b"abc"

    with pytest.raises(SubmissionUploadTimeout):
        await receive_submission_source(BufferedStore(), upload_value(
            upload_deadline_at=datetime.now(UTC) + timedelta(seconds=0.01),
        ), chunks())


@pytest.mark.parametrize("changed", ["none", "mapping", "forged", "subclass"])
def test_checker_source_contracts_reject_non_owner_or_unvalidated_values(changed):
    from app.adapters.artifacts import selected_pre_submit_source_contracts

    contracts = selected_pre_submit_source_contracts()
    original = source()
    class SourceSubclass(SealedSubmissionSource):
        pass
    invalid = {
        "none": None,
        "mapping": original.model_dump(mode="json"),
        "forged": original.model_copy(update={"raw_byte_count": True}),
        "subclass": SourceSubclass.model_validate_json(original.model_dump_json()),
    }[changed]
    with pytest.raises(ValueError):
        contracts.require_source(invalid)
    recovered = contracts.parse_source(original.model_dump(mode="json"))
    assert recovered == original
    assert recovered.source_sha256() == original.source_sha256()
    assert contracts.require_source(recovered) == original


@pytest.mark.parametrize("changed", ["missing", "extra", "coercion", "overflow"])
def test_checker_source_contracts_preserve_closed_limits_and_source_wire(changed):
    from app.adapters.artifacts import selected_pre_submit_source_contracts
    from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits

    contracts = selected_pre_submit_source_contracts()
    limits = SubmissionArchiveLimits()
    body = limits.canonical_body()
    assert contracts.parse_limits(body) == limits
    assert contracts.require_limits(limits).canonical_body() == body
    if changed == "missing":
        del body["maximum_entries"]
    elif changed == "extra":
        body["unbounded"] = True
    elif changed == "coercion":
        body["maximum_entries"] = "2000"
    else:
        body["maximum_expanded_bytes"] = 512 * 1024 * 1024 + 1
    with pytest.raises(ValueError):
        contracts.parse_limits(body)
    source_body = source().model_dump(mode="json")
    del source_body["media_type"]
    with pytest.raises(ValueError, match="not canonical"):
        contracts.parse_source(source_body)


@pytest.mark.parametrize("changed", [None, "original_event_id", "original_claim_generation",
    "original_payload_digest", "original_event_type", "evaluation_request_id", "checker_run_id",
    "evaluation_generation", "retained_digest"])
async def test_evaluation_progress_follows_only_exact_reconciliation_child(changed):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.core.hashing import canonical_json_hash
    from app.modules.artifacts.intake.progress import evaluation_delivery_progress
    from app.modules.artifacts.intake.repository import IntakeCustodyConflict
    from app.modules.checkers.api.delivery_reconciliation import PostSubmitDeliveryChildPayload
    from app.modules.outbox.api import OutboxAppendInput
    event_id, child_id, project, run, request = (new_record_id() for _ in range(5))
    event = OutboxAppendInput(event_type="PostSubmissionEvaluationRequested", event_version=1,
        aggregate_type="submission", aggregate_id=new_record_id(), project_id=project,
        correlation_id=str(request), idempotency_key="progress-fixture", payload={})
    resource = {"resource_context": {}}
    payload = PostSubmitDeliveryChildPayload(
        original_event_id=event_id, original_claim_generation=2, original_payload_digest=canonical_json_hash(event.payload),
        original_event_type=event.event_type, original_event_version=1,
        evaluation_request_id=request, checker_run_id=run, evaluation_generation=1,
        classification="retry_safe", reconciliation_request_id=new_record_id(), request_digest=SHA,
        authorization_decision_id=new_record_id(),
        authorization_resource_digest=canonical_json_hash(resource),
        authorization_resource_json=json.dumps(resource, sort_keys=True, separators=(",", ":")),
        operator_actor_profile_id=new_record_id(), operator_identity_link_id=new_record_id(),
    )
    body = payload.model_dump(mode="json")
    if changed == "retained_digest":
        body["original_payload_digest"] = SHA
    elif changed is not None:
        body[changed] = (3 if changed.endswith("generation") else
                         "sha256:" + "b" * 64 if changed.endswith("digest") else
                         "PostSubmissionEvaluationCompleted" if changed.endswith("type") else
                         str(new_record_id()))
    original = SimpleNamespace(state="dead_letter", error_code="INVOKE_OUTCOME_UNKNOWN")
    child = SimpleNamespace(state="pending", error_code=None)
    events = SimpleNamespace(observe_delivery=AsyncMock(side_effect=[original, child]))
    retained = SimpleNamespace(
        envelope=SimpleNamespace(claim=SimpleNamespace(event_id=event_id, project_id=project,
            claim_generation=2, payload_digest=SHA if changed == "retained_digest" else canonical_json_hash(event.payload))),
        child=SimpleNamespace(event_id=child_id, payload_json=json.dumps(body)),
    )
    deliveries = SimpleNamespace(read_finalized_unknown=AsyncMock(return_value=retained))
    evaluation = SimpleNamespace(current=SimpleNamespace(
        request=SimpleNamespace(evaluation_request_id=request),
        reservation=SimpleNamespace(attempt_id=run, evaluation_generation=1),
    ))
    if changed:
        with pytest.raises(IntakeCustodyConflict):
            await evaluation_delivery_progress(event_id, event, evaluation, events, deliveries)
        assert events.observe_delivery.await_count == 1
    else:
        assert await evaluation_delivery_progress(event_id, event, evaluation, events, deliveries) is child
        observed_id, expected = events.observe_delivery.await_args.args
        assert observed_id == child_id and expected.payload == payload.model_dump(mode="json")
        assert expected.causation_event_id == event_id and expected.aggregate_id == event_id
    assert deliveries.read_finalized_unknown.await_args.kwargs["lock"] is False


@pytest.mark.parametrize("selectors,valid", [
    ({}, False), ({"operation_id": OPERATION}, True),
    ({"idempotency_key": OPERATION}, True),
    ({"operation_id": OPERATION, "idempotency_key": OPERATION}, False),
    ({"operation_id": "not-a-uuid"}, False),
    ({"operation_id": OPERATION, "actor_id": TASK}, False),
])
def test_operation_progress_requires_one_selector_without_caller_actor_scope(selectors, valid):
    from app.modules.artifacts.api.submission_command import SubmissionOperationSelector
    if valid:
        assert SubmissionOperationSelector.model_validate(selectors)
    else:
        with pytest.raises(ValidationError):
            SubmissionOperationSelector.model_validate(selectors)


def test_operation_progress_wire_contract_keeps_nulls_and_rejects_extra_fields():
    from app.modules.artifacts.api.submission_command import SubmissionOperationResponse
    values = dict(operation_id=OPERATION, task_id=TASK, assignment_id=ASSIGNMENT,
        idempotency_key=REVISION, operation_state="receiving", processing_stage="receiving",
        accepted_at=None, task_status_at_acceptance=None, current_task_status=None,
        submission_id=None, submission_version=None, evaluation_request_id=None,
        pre_submission_results=[], failure_code=None, operationally_stalled=False,
        next_action="wait")
    response = SubmissionOperationResponse.model_validate(values)
    assert response.model_dump(mode="json").keys() == values.keys()
    for key, value in values.items():
        if value is None:
            assert response.model_dump(mode="json")[key] is None
            with pytest.raises(ValidationError):
                SubmissionOperationResponse.model_validate({k: v for k, v in values.items() if k != key})
    for updates in ({"provider_key": "secret"}, {"processing_stage": "submitted"},
                    {"operation_state": "accepted"}, {"current_task_status": "invented"},
                    {"submission_version": 0}, {"submission_version": True},
                    {"next_action": "retry_same_key"}):
        with pytest.raises(ValidationError):
            SubmissionOperationResponse.model_validate({**values, **updates})
