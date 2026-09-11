"""Retained checker packet validation, not a retired Submission POST contract."""

import pytest
from pydantic import ValidationError

from app.modules.checkers.schemas import PreSubmitCheckRequest
from tests.test_tasks import complete_submission_payload


def test_checker_packet_accepts_complete_input():
    payload = complete_submission_payload()
    parsed = PreSubmitCheckRequest.model_validate({"submission": payload})
    assert parsed.submission.model_dump(by_alias=True) == payload


@pytest.mark.parametrize("field", [
    "contributor_id",
    "version",
    "status",
    "locked_guide_version",
    "locked_post_submit_checker_policy_id",
    "locked_post_submit_checker_policy_version",
    "locked_post_submit_checker_policy_hash",
    "locked_post_submit_checker_policy_body",
    "locked_review_policy_id",
    "locked_review_policy_generation",
    "locked_review_policy_hash",
    "locked_revision_policy_id",
    "locked_revision_policy_generation",
    "locked_revision_policy_hash",
    "locked_payment_policy_version",
    "locked_guide_source_snapshot_id",
    "locked_guide_source_snapshot_hash",
    "locked_effective_project_submission_artifact_policy_id",
    "locked_effective_project_submission_artifact_policy_hash",
    "locked_pre_submit_checker_policy_id",
    "locked_pre_submit_checker_bundle_hash",
    "runtime_parameters",
    "finalized_at",
])
def test_checker_packet_rejects_each_client_owned_authority_or_lock_field(field):
    payload = complete_submission_payload()
    payload[field] = "client-controlled"
    with pytest.raises(ValidationError) as rejected:
        PreSubmitCheckRequest.model_validate({"submission": payload})
    assert [(error["loc"], error["type"]) for error in rejected.value.errors()] == [
        (("submission", field), "extra_forbidden"),
    ]


@pytest.mark.parametrize(("collection", "field"), [
    ("artifact_hash_manifest", "locked_guide_version"),
    ("evidence_items", "submission_id"),
])
def test_checker_packet_rejects_nested_authority_injection(collection, field):
    payload = complete_submission_payload()
    payload[collection][0][field] = "client-controlled"
    with pytest.raises(ValidationError) as rejected:
        PreSubmitCheckRequest.model_validate({"submission": payload})
    assert [(error["loc"], error["type"]) for error in rejected.value.errors()] == [
        (("submission", collection, 0, field), "extra_forbidden"),
    ]


@pytest.mark.parametrize(("field", "value"), [
    ("package_uri", "https://storage.example.test/package.tar?token=secret"),
    ("evidence_items", "file:///home/worker/private/evidence.log"),
    ("package_uri", "local://"),
    ("evidence_items", "local://../private/evidence.log"),
])
def test_checker_packet_rejects_unsafe_storage_references(field, value):
    payload = complete_submission_payload()
    if field == "evidence_items":
        payload[field][0]["uri"] = value
        expected_location = ("submission", field, 0, "uri")
    else:
        payload[field] = value
        expected_location = ("submission", field)
    with pytest.raises(ValidationError) as rejected:
        PreSubmitCheckRequest.model_validate({"submission": payload})
    assert [(error["loc"], error["type"]) for error in rejected.value.errors()] == [
        (expected_location, "value_error"),
    ]
