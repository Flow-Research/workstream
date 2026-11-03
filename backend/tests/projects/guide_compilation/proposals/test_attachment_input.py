"""Public approval requires deliberate, phase-separated human image attachments."""

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.projects.api.compilation_identity import CompilationComponentHashes
from app.modules.projects.api.guide_proposals import (
    GuideProposalApprovalInput,
    GuideProposalTarget,
)
from tests.checkers.external.test_policy import _entry, _attachment

SHA = "sha256:" + "a" * 64


def _target():
    return GuideProposalTarget(
        project_id=new_record_id(), guide_id=new_record_id(),
        compilation_id=new_record_id(), guide_version="v1",
        source_snapshot_id=new_record_id(), source_snapshot_hash=SHA,
        setup_run_id=new_record_id(), setup_generation=1,
        finalization_id=new_record_id(), finalization_facts_digest=SHA,
        result_hash=SHA,
        component_hashes=CompilationComponentHashes(
            sufficiency_hash=SHA, artifact_policy_hash=SHA,
            requirement_inventory_hash=SHA, pre_submit_hash=SHA, post_submit_hash=SHA,
        ),
        artifact_policy_id=None, artifact_policy_hash=None,
        artifact_projection_operation_id=None, artifact_projection_output_digest=None,
    )


def test_omitted_attachments_are_invalid_but_explicit_empty_is_valid():
    target = _target()
    with pytest.raises(ValidationError):
        GuideProposalApprovalInput(target=target)
    approved = GuideProposalApprovalInput(
        target=target, pre_submit_attachments=(), post_submit_attachments=(),
    )
    assert approved.pre_submit_attachments == ()
    assert approved.post_submit_attachments == ()


def test_duplicate_human_execution_key_is_invalid_even_for_distinct_images():
    first = _entry("project.first", "pre_submit")
    second = _entry("project.second", "pre_submit")
    with pytest.raises(ValidationError, match="unique canonical"):
        GuideProposalApprovalInput(
            target=_target(),
            pre_submit_attachments=(
                _attachment(first, "same_key"), _attachment(second, "same_key"),
            ),
            post_submit_attachments=(),
        )


def test_current_target_rejects_old_catalogue_identity():
    body = _target().model_dump(mode="json")
    body["pre_catalogue_manifest_hash"] = SHA
    with pytest.raises(ValidationError):
        GuideProposalTarget.model_validate(body)
