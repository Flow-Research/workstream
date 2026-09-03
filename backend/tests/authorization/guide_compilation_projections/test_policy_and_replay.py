"""Artifact-policy separation and exact replay behavior."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.modules.authorization import guide_compilation_projections as adapters
from app.modules.authorization.api import ProjectGuideProjectionLocator
from app.modules.authorization.guide_compilation_projections import (
    ArtifactPolicyProjectionAuthorization,
    GuideSufficiencyProjectionAuthorization,
)
from app.modules.authorization.prepared import (
    FixedServicePreparedAuthorization,
    PreparedAuthorizationService,
)
from app.modules.authorization.domain.guide_compilation_projections import (
    projection_resource_context,
    projection_resource_digest,
)

from .support import custody, policy_facts, sufficiency_facts


@pytest.mark.asyncio
async def test_artifact_policy_projection_uses_only_its_existing_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned, session, evidence = custody()

    @asynccontextmanager
    async def fixed(*_args, **_kwargs):
        try:
            yield owned
        finally:
            owned.service.close()

    monkeypatch.setattr(adapters, "fixed_service_prepared_authorization", fixed)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    adapter = ArtifactPolicyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_artifact_policy_projection(locator) as prepared:
        await prepared.consume_new(policy_facts(locator.project_id, locator.attempt_id))
    assert evidence.events[0].action_id.value == "project.submission_artifact_policy.derive"
    assert evidence.events[0].permission_id.value == "project.effective_policy.manage"


@pytest.mark.asyncio
async def test_projection_exact_replay_uses_original_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, session, evidence = custody()
    second_service = PreparedAuthorizationService(
        session,
        first.service._context,
        first.service._authorization,
        first.service._repository,
    )
    second = FixedServicePreparedAuthorization(
        actor_profile_id=first.actor_profile_id,
        identity_link_id=first.identity_link_id,
        service=second_service,
    )
    queue = [first, second]

    @asynccontextmanager
    async def fixed(*_args, **_kwargs):
        owned = queue.pop(0)
        try:
            yield owned
        finally:
            owned.service.close()

    monkeypatch.setattr(adapters, "fixed_service_prepared_authorization", fixed)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    facts = sufficiency_facts(locator.project_id, locator.attempt_id)
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        receipt = await prepared.consume_new(facts)
    stored = await evidence.get_authority_event(str(receipt.decision_event_id))
    assert stored.__dict__ == {
        **stored.__dict__,
        "request_id": str(first.service._context.request_id),
        "correlation_id": str(first.service._context.correlation_id),
    }
    assert stored.event_type == "SensitiveAuthorizationAllowed"
    assert stored.actor_id == str(first.actor_profile_id)
    assert stored.action_id == "project.guide_sufficiency.run"
    assert stored.permission_id == "project.guide.manage"
    assert stored.project_id == str(locator.project_id)
    assert stored.resource_type == "project_guide_sufficiency_projection"
    assert stored.resource_id == str(prepared.identity.operation_id)
    assert stored.after_facts["resource_context_digest"] == receipt.resource_context_digest
    assert stored.after_facts["allowed"] is True
    assert (
        projection_resource_digest(
            projection_resource_context("guide_sufficiency", prepared.identity, facts)
        )
        == receipt.resource_context_digest
    )
    async with adapter.prepare_sufficiency_projection(locator) as replay:
        await replay.validate_replay(facts, receipt.decision_event_id)
    assert len(evidence.events) == 1
