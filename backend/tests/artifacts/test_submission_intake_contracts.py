"""Exact command/source identity proof; no database or provider claims."""

import hashlib
import json
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.modules.artifacts.api.submission_archive import MAXIMUM_SUBMISSION_ZIP_BYTES
from app.modules.artifacts.api.submission_intake import (
    SealedSubmissionSource,
    SubmissionIntakeMetadata,
    SubmissionSourceLocation,
)


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
