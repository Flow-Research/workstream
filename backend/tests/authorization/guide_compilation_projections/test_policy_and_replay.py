"""Artifact-policy separation and exact replay behavior."""

from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization import guide_compilation_projections as adapters
from app.modules.authorization import kernel as kernel_module
from app.modules.authorization.api import (
    AuthorizationDenied,
    PreparedAuthorizationInvalid,
    ProjectGuideProjectionLocator,
    artifact_policy_projection_facts_digest,
    projection_authority_digest,
)
from app.modules.authorization.guide_compilation_projections import (
    ArtifactPolicyProjectionAuthorization,
    GuideSufficiencyProjectionAuthorization,
)
from app.modules.authorization.prepared import (
    FixedServicePreparedAuthorization,
    PreparedAuthorizationService,
)
from app.modules.authorization.catalogue import ActionAvailability, ActionId
from app.modules.authorization.runtime import ActorStatus, IdentityLinkStatus
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
        facts = policy_facts(locator.project_id, locator.attempt_id)
        receipt = await prepared.consume_new(facts)
        identity = prepared.identity
    event = evidence.events[0]
    assert event.action_id.value == "project.submission_artifact_policy.derive"
    assert event.permission_id.value == "project.effective_policy.manage"
    assert event.resource_type == "project_submission_artifact_policy_projection"
    assert event.resource_id == str(identity.operation_id)
    assert event.project_id == str(locator.project_id)
    assert receipt.actor_profile_id == owned.actor_profile_id
    assert receipt.identity_link_id == owned.identity_link_id
    assert receipt.resource_context_digest == projection_authority_digest(
        component="submission_artifact_policy",
        identity=identity,
        project_id=locator.project_id,
        facts_digest=artifact_policy_projection_facts_digest(facts),
    )
    assert event.after_facts["resource_context_digest"] == receipt.resource_context_digest


@pytest.mark.asyncio
@pytest.mark.parametrize("component", ("guide_sufficiency", "submission_artifact_policy"))
@pytest.mark.parametrize(
    "custody_kwargs",
    (
        {"identity": ServiceIdentity.ARTIFACT_BINDING},
        {"actor_status": ActorStatus.SUSPENDED},
        {"link_status": IdentityLinkStatus.REVOKED},
    ),
)
async def test_projection_requires_exact_project_setup_authority(
    monkeypatch: pytest.MonkeyPatch,
    component: str,
    custody_kwargs: dict,
) -> None:
    owned, session, evidence = custody(**custody_kwargs)

    @asynccontextmanager
    async def fixed(*_args, **_kwargs):
        try:
            yield owned
        finally:
            owned.service.close()

    monkeypatch.setattr(adapters, "fixed_service_prepared_authorization", fixed)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    adapter = (
        GuideSufficiencyProjectionAuthorization(session)
        if component == "guide_sufficiency"
        else ArtifactPolicyProjectionAuthorization(session)
    )
    with pytest.raises(AuthorizationDenied):
        async with (
            adapter.prepare_sufficiency_projection(locator)
            if component == "guide_sufficiency"
            else adapter.prepare_artifact_policy_projection(locator)
        ):
            pass
    assert evidence.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ("matrix", "availability"))
async def test_sufficiency_projection_requires_active_action_matrix(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    owned, session, evidence = custody()
    if missing == "matrix":
        monkeypatch.setattr(
            kernel_module,
            "SERVICE_ACTIONS_BY_IDENTITY",
            {ServiceIdentity.PROJECT_SETUP: frozenset()},
        )
    else:
        rows = dict(kernel_module.ACTION_BY_ID)
        rows[ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN] = replace(
            rows[ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN],
            availability=ActionAvailability.PLANNED,
        )
        monkeypatch.setattr(kernel_module, "ACTION_BY_ID", rows)

    @asynccontextmanager
    async def fixed(*_args, **_kwargs):
        try:
            yield owned
        finally:
            owned.service.close()

    monkeypatch.setattr(adapters, "fixed_service_prepared_authorization", fixed)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    with pytest.raises(AuthorizationDenied):
        async with adapter.prepare_sufficiency_projection(locator):
            pass
    assert evidence.events == []


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


@pytest.mark.asyncio
async def test_projection_replay_rejects_mismatched_decision_without_new_evidence(
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
    facts = sufficiency_facts(locator.project_id, locator.attempt_id)
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        with pytest.raises(AuthorizationDenied):
            await prepared.validate_replay(facts, uuid4())
    assert evidence.events == []


@pytest.mark.asyncio
async def test_policy_projection_rejects_wrong_deterministic_output(
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
    facts = replace(policy_facts(locator.project_id, locator.attempt_id), policy_id=uuid4())
    adapter = ArtifactPolicyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_artifact_policy_projection(locator) as prepared:
        with pytest.raises(PreparedAuthorizationInvalid):
            await prepared.consume_new(facts)
    assert evidence.events == []
