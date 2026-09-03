"""Fixed-service projection preparation and consumption behavior."""

from contextlib import asynccontextmanager
from copy import copy, deepcopy
import asyncio
import pickle
from dataclasses import replace
from uuid import uuid4
from types import SimpleNamespace

import pytest

from app.modules.authorization.api import (
    AuthorizationDenied,
    AuthorizationUnavailable,
    PreparedAuthorizationInvalid,
    ProjectGuideProjectionLocator,
    projection_authority_digest,
    guide_sufficiency_projection_facts_digest,
)
from app.modules.authorization.runtime import (
    AuthorizationDenialCode,
    AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationUnsupported,
)
from app.modules.authorization.guide_compilation_projections import (
    GuideSufficiencyProjectionAuthorization,
)
from app.modules.authorization import guide_compilation_projections as adapters

from .support import custody, policy_facts, sufficiency_facts


def _install_custody(monkeypatch: pytest.MonkeyPatch):
    owned, session, evidence = custody()

    @asynccontextmanager
    async def fixed(*_args, **_kwargs):
        try:
            yield owned
        finally:
            owned.service.close()

    monkeypatch.setattr(adapters, "fixed_service_prepared_authorization", fixed)
    return owned, session, evidence


@pytest.mark.asyncio
async def test_projection_consume_returns_exact_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned, session, evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    facts = sufficiency_facts(locator.project_id, locator.attempt_id)
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        receipt = await prepared.consume_new(facts)
        assert receipt.actor_profile_id == owned.actor_profile_id
        assert receipt.identity_link_id == owned.identity_link_id
        assert receipt.resource_context_digest == projection_authority_digest(
            component="guide_sufficiency",
            identity=prepared.identity,
            project_id=locator.project_id,
            facts_digest=guide_sufficiency_projection_facts_digest(facts),
        )
    assert [event.event_id for event in evidence.events] == [receipt.decision_event_id]


@pytest.mark.asyncio
async def test_projection_allowed_evidence_has_exact_resource_custody(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned, session, evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    facts = sufficiency_facts(locator.project_id, locator.attempt_id)
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        receipt = await prepared.consume_new(facts)
        identity = prepared.identity
    event = evidence.events[0]
    assert event.event_id == receipt.decision_event_id
    assert event.resource_type == "project_guide_sufficiency_projection"
    assert event.resource_id == str(identity.operation_id)
    assert event.project_id == str(locator.project_id)
    assert event.actor_ref == str(owned.actor_profile_id)
    assert event.action_id.value == "project.guide_sufficiency.run"
    assert event.permission_id.value == "project.guide.manage"
    assert event.after_facts["resource_context_digest"] == receipt.resource_context_digest


@pytest.mark.asyncio
async def test_projection_consumption_is_single_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owned, session, evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    facts = sufficiency_facts(locator.project_id, locator.attempt_id)
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        await prepared.consume_new(facts)
        with pytest.raises(PreparedAuthorizationInvalid):
            await prepared.consume_new(facts)
    assert len(evidence.events) == 1


@pytest.mark.asyncio
async def test_projection_prepared_is_nominal_and_closed_on_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owned, session, _evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    facts = sufficiency_facts(locator.project_id, locator.attempt_id)
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        with pytest.raises(Exception, match="cannot be copied"):
            copy(prepared)
        with pytest.raises(Exception, match="cannot be copied"):
            deepcopy(prepared)
        with pytest.raises(TypeError, match="cannot be serialized"):
            pickle.dumps(prepared)
    with pytest.raises(PreparedAuthorizationInvalid):
        await prepared.consume_new(facts)


@pytest.mark.asyncio
async def test_projection_locator_mismatch_denies_before_consumption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owned, session, evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        with pytest.raises(PreparedAuthorizationInvalid):
            await prepared.consume_new(sufficiency_facts(uuid4(), locator.attempt_id))
    assert evidence.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "public_error"),
    (
        (PreparedAuthorizationHandleInvalid("bad"), PreparedAuthorizationInvalid),
        (
            PreparedAuthorizationUnsupported(AuthorizationDenialCode.RESOURCE_GUARD_DENIED),
            AuthorizationDenied,
        ),
        (AuthorizationEvidenceUnavailable("bad"), AuthorizationUnavailable),
    ),
)
async def test_projection_consume_conceals_internal_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    public_error: type[Exception],
) -> None:
    owned, session, _evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    facts = sufficiency_facts(locator.project_id, locator.attempt_id)
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:

        async def fail(*_args, **_kwargs):
            raise failure

        owned.service.consume = fail  # type: ignore[method-assign]
        with pytest.raises(public_error):
            await prepared.consume_new(facts)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("consume", "replay"))
async def test_cross_component_facts_are_concealed_without_evidence(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    _owned, session, evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    wrong_facts = policy_facts(locator.project_id, locator.attempt_id)
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        with pytest.raises(PreparedAuthorizationInvalid):
            if operation == "consume":
                await prepared.consume_new(wrong_facts)  # type: ignore[arg-type]
            else:
                await prepared.validate_replay(wrong_facts, uuid4())  # type: ignore[arg-type]
    assert evidence.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", (None, RuntimeError("late"), asyncio.CancelledError()))
async def test_projection_prepared_close_matrix(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException | None,
) -> None:
    owned, session, _evidence = custody()
    close_calls = 0
    original_close = owned.service.close

    def close() -> None:
        nonlocal close_calls
        close_calls += 1
        original_close()

    owned.service.close = close  # type: ignore[method-assign]

    @asynccontextmanager
    async def fixed(*_args, **_kwargs):
        try:
            yield owned
        finally:
            owned.service.close()

    monkeypatch.setattr(adapters, "fixed_service_prepared_authorization", fixed)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    if failure is None:
        async with adapter.prepare_sufficiency_projection(locator):
            pass
    else:
        with pytest.raises(type(failure)):
            async with adapter.prepare_sufficiency_projection(locator):
                raise failure
    assert close_calls == 1


@pytest.mark.asyncio
async def test_wrong_deterministic_output_denies_before_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owned, session, evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    facts = replace(sufficiency_facts(locator.project_id, locator.attempt_id), report_id=uuid4())
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        with pytest.raises(PreparedAuthorizationInvalid):
            await prepared.consume_new(facts)
    assert evidence.events == []


@pytest.mark.asyncio
async def test_caller_body_exception_is_not_remapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owned, session, _evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    failure = AuthorizationEvidenceUnavailable("caller-owned failure")
    with pytest.raises(AuthorizationEvidenceUnavailable) as caught:
        async with adapter.prepare_sufficiency_projection(locator):
            raise failure
    assert caught.value is failure


@pytest.mark.asyncio
async def test_projection_handle_cannot_cross_root_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owned, session, evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    facts = sufficiency_facts(locator.project_id, locator.attempt_id)
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        session.root = SimpleNamespace(is_active=True)
        with pytest.raises(PreparedAuthorizationInvalid):
            await prepared.consume_new(facts)
    assert evidence.events == []
