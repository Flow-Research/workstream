"""CP01B proof for planned ContributionPolicy AUTH registration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from app.modules.authorization.api import (
    ContributionPolicyCreateDraftFacts,
    ContributionPolicyPublishFacts,
    ContributionPolicyReadFacts,
    ContributionPolicyRetireFacts,
    ContributionPolicyUpdateDraftFacts,
    action_id,
    contribution_policy_resource_digest,
)
from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    SERVICE_ACTIONS_BY_IDENTITY,
    ActionAvailability,
    ActionId,
    ActionOwner,
    PermissionId,
    resolve_executable_action,
)

_ACTIONS = {
    ActionId.CONTRIBUTION_POLICY_READ,
    ActionId.CONTRIBUTION_POLICY_CREATE_DRAFT,
    ActionId.CONTRIBUTION_POLICY_UPDATE_DRAFT,
    ActionId.CONTRIBUTION_POLICY_PUBLISH,
    ActionId.CONTRIBUTION_POLICY_RETIRE,
}
_SHA256 = "sha256:" + "a" * 64


def test_cp01b_registers_only_exact_planned_policy_actions() -> None:
    """The five canonical actions remain unavailable and unassigned."""
    for action in _ACTIONS:
        definition = ACTION_BY_ID[action]
        assert definition.permission_id is PermissionId.COMPENSATION_POLICY_MANAGE
        assert definition.owner is ActionOwner.ARCH_CP01B
        assert definition.availability is ActionAvailability.PLANNED
        with pytest.raises(ValueError, match="authorization action is not active"):
            resolve_executable_action(action)

    assert not ({"compensation.policy.read", "compensation.policy.publish"} & {item.value for item in ActionId})
    assert all(_ACTIONS.isdisjoint(actions) for actions in SERVICE_ACTIONS_BY_IDENTITY.values())


def test_cp01b_public_facts_are_immutable_and_lifecycle_bound() -> None:
    """Mutation facts reject wrong lifecycle state and mutable lineage."""
    project_id, policy_id, version_id = uuid4(), uuid4(), uuid4()
    read = ContributionPolicyReadFacts(
        project_id=project_id,
        contribution_policy_id=policy_id,
    )
    with pytest.raises(FrozenInstanceError):
        read.project_id = uuid4()  # type: ignore[misc]
    with pytest.raises(ValueError, match="requires draft"):
        ContributionPolicyUpdateDraftFacts(
            project_id=project_id,
            contribution_policy_id=policy_id,
            contribution_policy_version_id=version_id,
            expected_status="published",
        )
    with pytest.raises(ValueError, match="requires published"):
        ContributionPolicyRetireFacts(
            project_id=project_id,
            contribution_policy_id=policy_id,
            contribution_policy_version_id=version_id,
            expected_status="draft",
        )


def test_cp01b_publish_requires_canonical_digest_and_binding_lineage() -> None:
    """Publish binding identities are immutable, sorted, and duplicate-free."""
    project_id, policy_id, version_id = uuid4(), uuid4(), uuid4()
    low = uuid4()
    high = uuid4()
    low, high = sorted((low, high), key=str)
    facts = ContributionPolicyPublishFacts(
        project_id=project_id,
        contribution_policy_id=policy_id,
        contribution_policy_version_id=version_id,
        rules_and_definitions_digest=_SHA256,
        adapter_binding_ids=(low, high),
    )
    assert facts.adapter_binding_ids == (low, high)
    for binding_ids in ([low], (high, low), (low, low)):
        with pytest.raises(ValueError, match="adapter_binding_ids"):
            ContributionPolicyPublishFacts(
                project_id=project_id,
                contribution_policy_id=policy_id,
                contribution_policy_version_id=version_id,
                rules_and_definitions_digest=_SHA256,
                adapter_binding_ids=binding_ids,  # type: ignore[arg-type]
            )
    with pytest.raises(ValueError, match="canonical sha256"):
        ContributionPolicyPublishFacts(
            project_id=project_id,
            contribution_policy_id=policy_id,
            contribution_policy_version_id=version_id,
            rules_and_definitions_digest="sha256:ABC",
            adapter_binding_ids=(),
        )


def test_cp01b_digest_is_deterministic_and_action_domain_separated() -> None:
    """Resource digests bind both the action and exact typed facts."""
    project_id, policy_id = uuid4(), uuid4()
    read = ContributionPolicyReadFacts(
        project_id=project_id,
        contribution_policy_id=policy_id,
    )
    read_action = action_id("contribution.policy.read")
    digest = contribution_policy_resource_digest(read_action, read)
    assert digest == contribution_policy_resource_digest(read_action, read)
    assert digest.startswith("sha256:") and len(digest) == 71
    with pytest.raises(ValueError, match="does not match"):
        contribution_policy_resource_digest(
            action_id("contribution.policy.create_draft"), read
        )


def test_cp01b_public_api_exports_exact_registration_surface() -> None:
    """The dependency-free API exposes the exact CP01B fact family."""
    import app.modules.authorization.api as authorization_api

    expected = {
        "ContributionPolicyCreateDraftFacts",
        "ContributionPolicyPublishFacts",
        "ContributionPolicyReadFacts",
        "ContributionPolicyRetireFacts",
        "ContributionPolicyUpdateDraftFacts",
        "contribution_policy_resource_digest",
    }
    assert expected <= set(authorization_api.__all__)
    assert all(hasattr(authorization_api, name) for name in expected)


def test_cp01b_create_draft_binds_only_the_project_collection() -> None:
    """Draft creation targets the project collection without product payload."""
    project_id = uuid4()
    facts = ContributionPolicyCreateDraftFacts(project_id=project_id)
    assert facts.project_id == project_id
