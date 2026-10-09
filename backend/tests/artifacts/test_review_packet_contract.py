"""Metadata transport proofs, without claiming stored ownership or authority."""

from copy import deepcopy
from uuid import UUID

from pydantic import ValidationError
import pytest

from app.modules.artifacts.api import (
    ReviewGuideMember,
    ReviewPacketMembership,
    ReviewPacketMembershipPort,
    ReviewPacketMembershipRequest,
    ReviewPacketMembershipUnavailable,
    ReviewSubmissionMember,
)


def packet() -> dict:
    return {
        "request": {
            "project_id": UUID(int=1), "task_id": UUID(int=2),
            "submission_id": UUID(int=3), "submission_version": 1,
            "checker_run_id": UUID(int=4), "result_id": UUID(int=5),
            "guide_id": UUID(int=6), "guide_version": "initial-guide",
            "source_snapshot_id": UUID(int=7), "project_setup_run_id": UUID(int=8),
            "setup_generation": 1,
        },
        "submission": {
            "binding_id": UUID(int=9), "logical_role": "submission_bundle_original",
            "media_type": "application/zip",
        },
        "guide_documents": (guide(0), guide(2)),
    }


def guide(order: int) -> dict:
    return {
        "ingest_id": UUID(int=100 + order),
        "source_item_id": UUID(int=300 + order), "item_order": order,
        "logical_role": "guide_source_original", "media_type": "application/pdf",
    }


@pytest.mark.parametrize("version", [1, 4])
def test_exact_packet_round_trip_and_frozen_nested_values(version: int) -> None:
    raw = packet()
    raw["request"]["submission_version"] = version
    value = ReviewPacketMembership.model_validate(raw)
    value.require_request(ReviewPacketMembershipRequest.model_validate(raw["request"]))
    assert ReviewPacketMembership.model_validate_json(value.model_dump_json()) == value
    assert value.model_dump() == {**raw, "guide_documents": tuple(raw["guide_documents"])}
    assert isinstance(value.request.project_id, UUID)
    for obj, field, replacement in (
        (value, "submission", value.submission),
        (value.request, "submission_version", 2),
        (value.submission, "binding_id", UUID(int=20)),
        (value.guide_documents[0], "item_order", 7),
    ):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(obj, field, replacement)


def test_closed_public_field_inventories() -> None:
    assert set(ReviewPacketMembershipRequest.model_fields) == {
        "project_id", "task_id", "submission_id", "submission_version", "checker_run_id",
        "result_id", "guide_id", "guide_version", "source_snapshot_id",
        "project_setup_run_id", "setup_generation",
    }
    assert set(ReviewSubmissionMember.model_fields) == {"binding_id", "logical_role", "media_type"}
    assert set(ReviewGuideMember.model_fields) == {
        "ingest_id", "source_item_id", "item_order", "logical_role", "media_type",
    }
    assert set(ReviewPacketMembership.model_fields) == {"request", "submission", "guide_documents"}
    with pytest.raises(TypeError, match="Protocols cannot be instantiated"):
        ReviewPacketMembershipPort()


@pytest.mark.parametrize("scope", ["packet", "request", "submission", "guide"])
def test_every_field_required_and_private_additions_rejected(scope: str) -> None:
    raw = packet()
    model, data = {
        "packet": (ReviewPacketMembership, raw),
        "request": (ReviewPacketMembershipRequest, raw["request"]),
        "submission": (ReviewSubmissionMember, raw["submission"]),
        "guide": (ReviewGuideMember, raw["guide_documents"][0]),
    }[scope]
    model.model_validate(data)
    for name in data:
        reduced = {key: value for key, value in data.items() if key != name}
        with pytest.raises(ValidationError, match="Field required"):
            model.model_validate(reduced)
    for name in (
        "required", "sha256", "byte_count", "content_id", "replica_id", "provider_url",
        "object_key", "scratch_path", "receipt", "lease_capability", "policy", "metadata",
        "checker_result_id", "authorization",
    ):
        with pytest.raises(ValidationError, match="Extra inputs"):
            model.model_validate({**data, name: False})


@pytest.mark.parametrize("field", list(packet()["request"]))
def test_scope_substitution_is_concealed(field: str) -> None:
    raw = packet()
    value = ReviewPacketMembership.model_validate(raw)
    changed = deepcopy(raw["request"])
    old = changed[field]
    changed[field] = UUID(int=999) if isinstance(old, UUID) else old + 1 if isinstance(old, int) else "other-guide"
    expected = ReviewPacketMembershipRequest.model_validate(changed)
    with pytest.raises(ReviewPacketMembershipUnavailable) as caught:
        value.require_request(expected)
    assert str(caught.value) == "review_packet_membership_unavailable"


def test_invalid_ids_and_strict_versions() -> None:
    raw = packet()
    for name, value in raw["request"].items():
        if isinstance(value, UUID):
            with pytest.raises(ValidationError):
                ReviewPacketMembershipRequest.model_validate({**raw["request"], name: "invalid"})
    for model, data, fields in (
        (ReviewSubmissionMember, raw["submission"], ["binding_id"]),
        (ReviewGuideMember, raw["guide_documents"][0], ["ingest_id", "source_item_id"]),
    ):
        for name in fields:
            with pytest.raises(ValidationError):
                model.model_validate({**data, name: "invalid"})
    for name in ("submission_version", "setup_generation"):
        for invalid in (0, -1, True, "1", 1.0):
            with pytest.raises(ValidationError):
                ReviewPacketMembershipRequest.model_validate({**raw["request"], name: invalid})
    for invalid in ("", "  ", "x" * 51):
        with pytest.raises(ValidationError):
            ReviewPacketMembershipRequest.model_validate({**raw["request"], "guide_version": invalid})
    for invalid in (-1, True, "0", 0.0):
        with pytest.raises(ValidationError):
            ReviewGuideMember.model_validate({**guide(0), "item_order": invalid})


def test_closed_roles_and_supported_media() -> None:
    raw = packet()
    for model, data in ((ReviewSubmissionMember, raw["submission"]), (ReviewGuideMember, guide(0))):
        for field, invalid in (("logical_role", "other"), ("media_type", "text/plain")):
            with pytest.raises(ValidationError):
                model.model_validate({**data, field: invalid})
    for media in (
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/markdown",
    ):
        assert ReviewGuideMember.model_validate({**guide(0), "media_type": media}).media_type == media


@pytest.mark.parametrize("attribute", ["ingest_id", "source_item_id", "item_order"])
def test_independent_duplicate_membership_rejected(attribute: str) -> None:
    raw = packet()
    raw["guide_documents"][1][attribute] = raw["guide_documents"][0][attribute]
    with pytest.raises(ValidationError, match="membership is duplicated"):
        ReviewPacketMembership.model_validate(raw)


def test_canonical_order_and_document_count_bounds() -> None:
    raw = packet()
    ReviewPacketMembership.model_validate(raw)
    with pytest.raises(ValidationError) as caught:
        ReviewPacketMembership.model_validate({**raw, "guide_documents": list(raw["guide_documents"])})
    assert len(caught.value.errors()) == 1
    assert caught.value.errors()[0]["type"] == "tuple_type"
    assert caught.value.errors()[0]["loc"] == ("guide_documents",)
    with pytest.raises(ValidationError, match="source order"):
        ReviewPacketMembership.model_validate({**raw, "guide_documents": tuple(reversed(raw["guide_documents"]))})
    for count in (1, 100):
        assert len(ReviewPacketMembership.model_validate({**raw, "guide_documents": tuple(guide(i) for i in range(count))}).guide_documents) == count
    for count in (0, 101):
        with pytest.raises(ValidationError):
            ReviewPacketMembership.model_validate({**raw, "guide_documents": tuple(guide(i) for i in range(count))})


def test_python_uuid_strings_rejected_at_each_nested_boundary() -> None:
    """JSON is decoded at its boundary; Python callers must supply native UUIDs."""
    raw = packet()
    ReviewPacketMembership.model_validate(raw)
    for scope, fields in (
        ("request", ("project_id", "task_id", "submission_id", "checker_run_id",
                     "result_id", "guide_id", "source_snapshot_id", "project_setup_run_id")),
        ("submission", ("binding_id",)),
        ("guide", ("ingest_id", "source_item_id")),
    ):
        for field in fields:
            changed = deepcopy(raw)
            nested = changed["guide_documents"][0] if scope == "guide" else changed[scope]
            nested[field] = str(nested[field])
            with pytest.raises(ValidationError) as caught:
                ReviewPacketMembership.model_validate(changed)
            assert len(caught.value.errors()) == 1
            assert caught.value.errors()[0]["type"] == "is_instance_of"
            expected_location = ("guide_documents", 0, field) if scope == "guide" else (scope, field)
            assert caught.value.errors()[0]["loc"] == expected_location


def test_removed_guide_binding_identity_is_not_an_alias():
    from app.modules.artifacts.api.review_packet import ReviewGuideMember
    from app.core.identifiers import new_record_id
    with pytest.raises(ValidationError):
        ReviewGuideMember(guide_binding_id=new_record_id(),source_item_id=new_record_id(),
            item_order=0,logical_role='guide_source_original',media_type='application/pdf')
