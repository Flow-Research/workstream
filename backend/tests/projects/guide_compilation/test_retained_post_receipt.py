"""Old POST receipts remain exact, read-only approval evidence."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.api.post_policy import post_policy_derive_authorization_selector
from app.modules.projects.post_policy.custody import operation_receipt


def _operation():
    digest = "sha256:" + "a" * 64
    project, guide, compilation, source, setup, finalization = (new_record_id() for _ in range(6))
    artifact, projection, policy, approval, effective, pre = (new_record_id() for _ in range(6))
    hashes = {
        name: digest
        for name in (
            "sufficiency_hash",
            "artifact_policy_hash",
            "requirement_inventory_hash",
            "pre_submit_hash",
            "post_submit_hash",
            "capability_suggestions_hash",
            "setup_notes_hash",
        )
    }
    proposal = dict(
        project_id=str(project),
        guide_id=str(guide),
        compilation_id=str(compilation),
        guide_version="v1",
        source_snapshot_id=str(source),
        source_snapshot_hash=digest,
        setup_run_id=str(setup),
        setup_generation=1,
        finalization_id=str(finalization),
        finalization_facts_digest=digest,
        result_hash=digest,
        component_hashes=hashes,
        pre_catalogue_id="pre",
        pre_catalogue_version="v1",
        pre_catalogue_schema_version="v1",
        pre_catalogue_manifest_hash=digest,
        post_catalogue_id="post",
        post_catalogue_version="v1",
        post_catalogue_schema_version="v1",
        post_catalogue_manifest_hash=digest,
        artifact_policy_id=str(artifact),
        artifact_policy_hash=digest,
        artifact_projection_operation_id=str(projection),
        artifact_projection_output_digest=digest,
    )
    upstream = dict(
        operation_id=str(approval),
        target_digest=canonical_json_hash(proposal),
        artifact_policy_id=str(artifact),
        effective_policy_id=str(effective),
        effective_policy_hash=digest,
        pre_submit_policy_id=str(pre),
        pre_submit_bundle_hash=digest,
        effective_pre_submit_plan_hash=digest,
        acknowledged_warning_hashes=[],
    )
    operation_id, post_projection, actor, link = (new_record_id() for _ in range(4))
    target = dict(
        proposal=proposal,
        upstream=upstream,
        upstream_output_digest=canonical_json_hash(upstream),
        policy_id=str(policy),
        projection_operation_id=str(post_projection),
        policy_hash=digest,
        predecessor_policy_id=None,
    )
    receipt = dict(operation_id=str(operation_id), kind="derive", target=target, correction=None)
    request = {
        "selection": {"project_id": str(project)},
        "upstream_approval_operation_id": str(approval),
    }
    output_digest = canonical_json_hash(receipt)
    request_digest = canonical_json_hash(request)
    facts = dict(
        locator=dict(
            project_id=str(project),
            guide_id=str(guide),
            compilation_id=str(compilation),
            actor_profile_id=str(actor),
            identity_link_id=str(link),
            action_id="project.post_submit_checker_policy.derive",
            operation_id=str(post_policy_derive_authorization_selector(approval)),
        ),
        policy_id=str(policy),
        finalization_id=str(finalization),
        setup_run_id=str(setup),
        setup_generation=1,
        upstream_approval_operation_id=str(approval),
        upstream_approval_output_digest=canonical_json_hash(upstream),
        guide_version="v1",
        source_snapshot_id=str(source),
        source_snapshot_hash=digest,
        result_hash=digest,
        post_component_hash=digest,
        requirement_inventory_hash=digest,
        catalogue_manifest_hash=digest,
        effective_policy_id=str(effective),
        effective_policy_hash=digest,
        pre_submit_policy_id=str(pre),
        pre_submit_bundle_hash=digest,
        projection_operation_id=str(post_projection),
        lifecycle_status="compiled",
        policy_hash=digest,
        target_digest=canonical_json_hash(target),
        request_digest=request_digest,
        output_digest=output_digest,
    )
    return SimpleNamespace(
        operation_id=operation_id,
        kind="derive",
        idempotency_key=uuid4(),
        project_id=str(project),
        guide_id=str(guide),
        compilation_id=compilation,
        policy_id=str(policy),
        upstream_approval_operation_id=approval,
        target_json=target,
        target_digest=canonical_json_hash(target),
        request_json=request,
        request_digest=request_digest,
        receipt_json=receipt,
        output_digest=output_digest,
        resource_context_json=facts,
        resource_context_digest=canonical_json_hash(facts),
        actor_profile_id=str(actor),
        identity_link_id=str(link),
    )


def test_retained_post_receipt_preserves_old_resource_commitment():
    operation = _operation()
    assert (
        operation_receipt(operation).target.proposal.post_catalogue_manifest_hash
        == (operation.resource_context_json["catalogue_manifest_hash"])
    )
    operation.resource_context_json["catalogue_manifest_hash"] = "sha256:" + "b" * 64
    operation.resource_context_digest = canonical_json_hash(operation.resource_context_json)
    with pytest.raises(GuideProposalError):
        operation_receipt(operation)
