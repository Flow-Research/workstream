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


@pytest.mark.parametrize("phase", ["pre_submit_attachments", "post_submit_attachments"])
@pytest.mark.parametrize("count", [None, 0, 2])
def test_approval_requires_exactly_one_explicit_image_per_phase(phase, count):
    pre = _attachment(_entry("project.pre", "pre_submit"), "intake")
    post = _attachment(_entry("project.post", "post_submit"), "quality")
    body = {"target": _target(), "pre_submit_attachments": (pre,),
            "post_submit_attachments": (post,)}
    if count is None:
        del body[phase]
    else:
        member = body[phase][0]
        body[phase] = tuple(member.model_copy(update={"requirement_id": f"member_{i}"})
                            for i in range(count))
    with pytest.raises(ValidationError) as error:
        GuideProposalApprovalInput(**body)
    assert error.value.errors()[0]["loc"] == (phase,)


def test_approval_preserves_exact_single_phase_selections():
    pre = _attachment(_entry("project.pre", "pre_submit"), "intake")
    post = _attachment(_entry("project.post", "post_submit"), "quality")
    approved = GuideProposalApprovalInput(
        target=_target(), pre_submit_attachments=(pre,), post_submit_attachments=(post,),
    )
    assert approved.pre_submit_attachments == (pre,)
    assert approved.post_submit_attachments == (post,)


def test_current_target_rejects_old_catalogue_identity():
    body = _target().model_dump(mode="json")
    body["pre_catalogue_manifest_hash"] = SHA
    with pytest.raises(ValidationError):
        GuideProposalTarget.model_validate(body)
