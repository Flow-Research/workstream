"""Fail-closed guards for exact projection replay authorization."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.authorization import guide_compilation_projections as adapters
from app.modules.authorization import prepared_projection_replay as replay_module
from app.modules.authorization.api import ProjectGuideProjectionLocator
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_compilation_projections import (
    projection_resource_context,
)
from app.modules.authorization.guide_compilation_projections import (
    GuideSufficiencyProjectionAuthorization,
)
from app.modules.authorization.prepared import (
    FixedServicePreparedAuthorization,
    PreparedAuthorizationService,
)
from app.modules.authorization.runtime import (
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
)

from .support import custody, sufficiency_facts


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ("action", "binding", "transaction", "scope"))
async def test_projection_replay_rejects_every_prepared_custody_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    first, session, evidence = custody()
    replay_service = PreparedAuthorizationService(
        session,
        first.service._context,
        first.service._authorization,
        first.service._repository,
    )
    queue = [
        first,
        FixedServicePreparedAuthorization(
            actor_profile_id=first.actor_profile_id,
            identity_link_id=first.identity_link_id,
            service=replay_service,
        ),
    ]

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
    async with adapter.prepare_sufficiency_projection(locator) as original:
        receipt = await original.consume_new(facts)

    async with adapter.prepare_sufficiency_projection(locator) as replay:
        action = ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
        caller_input = replay._input  # type: ignore[attr-defined]
        resource = projection_resource_context("guide_sufficiency", replay.identity, facts)
        if mismatch == "action":
            action = ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE
        elif mismatch == "binding":
            caller_input = PreparedAuthorizationInput(
                idempotency_key=uuid4(),
                request_value=caller_input.request_value,
            )
        elif mismatch == "transaction":
            session.root = SimpleNamespace(is_active=True)
        else:
            resource = resource.model_copy(update={"scope_project_id": uuid4()})

        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await replay_service.validate_replay(
                replay._handle,  # type: ignore[attr-defined]
                action,
                caller_input,
                resource,
                receipt.decision_event_id,
            )
        assert replay_service._authorization._sealed_prelocked == set()
    assert len(evidence.events) == 1


@pytest.mark.asyncio
async def test_projection_replay_rejects_project_setup_resource_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, session, evidence = custody()
    replay_service = PreparedAuthorizationService(
        session,
        first.service._context,
        first.service._authorization,
        first.service._repository,
    )
    queue = [
        first,
        FixedServicePreparedAuthorization(
            actor_profile_id=first.actor_profile_id,
            identity_link_id=first.identity_link_id,
            service=replay_service,
        ),
    ]

    @asynccontextmanager
    async def fixed(*_args, **_kwargs):
        owned = queue.pop(0)
        try:
            yield owned
        finally:
            owned.service.close()

    monkeypatch.setattr(adapters, "fixed_service_prepared_authorization", fixed)
    monkeypatch.setattr(replay_module, "project_setup_resource_matches", lambda *_a: False)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    facts = sufficiency_facts(locator.project_id, locator.attempt_id)
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as original:
        receipt = await original.consume_new(facts)

    async with adapter.prepare_sufficiency_projection(locator) as replay:
        resource = projection_resource_context("guide_sufficiency", replay.identity, facts)
        with pytest.raises(PreparedAuthorizationUnsupported):
            await replay_service.validate_replay(
                replay._handle,  # type: ignore[attr-defined]
                ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
                replay._input,  # type: ignore[attr-defined]
                resource,
                receipt.decision_event_id,
            )
        assert replay_service._authorization._sealed_prelocked == set()
    assert len(evidence.events) == 1
