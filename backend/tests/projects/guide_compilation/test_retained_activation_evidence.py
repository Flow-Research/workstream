"""Original activation receipts retain their exact locked policy selections."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.projects.guide_activation.custody import (
    _retained_activation_custody,
    load_guide_activation,
)

from .test_retained_post_receipt import _operation


def _record():
    post = _operation()
    digest = "sha256:" + "a" * 64
    target = post.target_json
    project_id = post.project_id
    guide_id = post.guide_id
    actor_id, link_id, activation_id = (new_record_id() for _ in range(3))
    contribution_id, contribution_version_id = (new_record_id() for _ in range(2))
    idempotency_key = uuid4()
    policy_selection = dict(policy_id=str(new_record_id()), generation=1, policy_hash=digest)
    command = dict(
        target=target,
        post_approval_operation_id=str(new_record_id()),
        post_approval_output_digest=digest,
        guide_mutation_generation=1,
        review=policy_selection,
        revision=dict(policy_selection),
        contribution_policy_id=str(contribution_id),
        contribution_policy_version_id=str(contribution_version_id),
        expected_previous_active_guide_id=None,
        expected_previous_active_guide_generation=None,
        idempotency_key=str(idempotency_key),
    )
    receipt = dict(
        operation_id=str(activation_id),
        command=command,
        contribution=dict(
            project_id=project_id,
            contribution_policy_id=str(contribution_id),
            contribution_policy_version_id=str(contribution_version_id),
            purpose="guide_activation",
            version_number=1,
            rules_and_definitions_digest=digest,
            adapter_binding_ids=[],
        ),
        activation_generation=2,
        effective_at="2026-11-03T00:00:00Z",
        prior_project_status="draft",
    )
    locator = dict(
        project_id=project_id,
        guide_id=guide_id,
        actor_profile_id=str(actor_id),
        identity_link_id=str(link_id),
        operation_id=str(activation_id),
        action_id="project.guide.activate",
    )
    body = {"locator": locator, "receipt": receipt}
    authority = dict(
        actor_profile_id=str(actor_id),
        identity_link_id=str(link_id),
        admin_role_grant_id=str(new_record_id()),
        authorization_decision_event_id=str(new_record_id()),
        action_id="project.guide.activate",
        permission_id="project.guide.manage",
        scope_project_id=project_id,
        resource_context_digest=canonical_json_hash(body),
    )
    return SimpleNamespace(
        response_json=receipt,
        activation_facts_json=body,
        activation_authority_json=authority,
        status="committed",
        action_id="project.guide.activate",
        request_digest=canonical_json_hash(command),
        operation_id=activation_id,
        operation_generation=2,
        idempotency_key=idempotency_key,
        setup_run_id=None,
        resource_context_digest=canonical_json_hash(body),
        project_id=project_id,
        resource_id=guide_id,
        actor_profile_id=str(actor_id),
        identity_link_id=str(link_id),
    )


def test_retained_activation_accepts_original_receipt():
    record = _record()
    receipt = _retained_activation_custody(record, request_id=record.operation_id)
    assert receipt.command.target.proposal.component_hashes.setup_notes_hash == "sha256:" + "a" * 64
    assert receipt.command.target.policy_id == UUID(
        record.response_json["command"]["target"]["policy_id"]
    )


@pytest.mark.parametrize("field", ["request_digest", "resource_context_digest", "policy_hash"])
def test_retained_activation_rejects_tampering(field):
    record = _record()
    if field == "policy_hash":
        record.response_json["command"]["target"]["policy_hash"] = "sha256:" + "b" * 64
    else:
        setattr(record, field, "sha256:" + "b" * 64)
    with pytest.raises(ValueError):
        _retained_activation_custody(record, request_id=record.operation_id)


async def test_retained_activation_read_binds_exact_guide_selection():
    record = _record()
    receipt = _retained_activation_custody(record, request_id=record.operation_id)
    guide = SimpleNamespace(
        activation_operation_id=record.operation_id,
        id=record.resource_id,
        project_id=record.project_id,
        version=receipt.command.target.proposal.guide_version,
        mutation_generation=receipt.activation_generation,
        contribution_policy_id=receipt.command.contribution_policy_id,
        contribution_policy_version_id=receipt.command.contribution_policy_version_id,
        effective_at=receipt.effective_at,
        approved_by=record.actor_profile_id,
        status="active",
        selected_review_policy_id=str(receipt.command.review.policy_id),
        selected_review_policy_generation=receipt.command.review.generation,
        selected_review_policy_hash=receipt.command.review.policy_hash,
        selected_revision_policy_id=str(receipt.command.revision.policy_id),
        selected_revision_policy_generation=receipt.command.revision.generation,
        selected_revision_policy_hash=receipt.command.revision.policy_hash,
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=record))
    assert await load_guide_activation(session, guide) == receipt
    guide.selected_revision_policy_hash = "sha256:" + "b" * 64
    with pytest.raises(ValueError):
        await load_guide_activation(session, guide)
