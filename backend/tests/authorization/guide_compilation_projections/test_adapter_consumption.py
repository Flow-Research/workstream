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
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ProjectGuideSufficiencyMutationResourceContext,
    ProjectSetupServiceCustodyContext,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.guide_compilation_projections import (
    GuideSufficiencyProjectionAuthorization,
)
from app.modules.authorization.domain.guide_compilation_projections import (
    projection_resource_context,
)
from app.modules.authorization import guide_compilation_projections as adapters

from .support import DIGEST, custody, policy_facts, sufficiency_facts


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
async def test_projection_closed_copied_and_reconstructed_handles_deny(
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
        with pytest.raises(TypeError, match="handles are internal"):
            PreparedAuthorizationHandle()
    with pytest.raises(PreparedAuthorizationInvalid):
        await prepared.consume_new(facts)


@pytest.mark.asyncio
async def test_legacy_preparation_cannot_consume_projection_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owned, session, evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    guide_id, snapshot_id, setup_run_id = (uuid4() for _ in range(3))
    setup_custody = ProjectSetupServiceCustodyContext(
        setup_run_id=setup_run_id,
        expected_step="guide_sufficiency",
        task_id=uuid4(),
        correlation_id=uuid4(),
        scope_project_id=locator.project_id,
        guide_id=guide_id,
        source_snapshot_id=snapshot_id,
        setup_generation=1,
        stale_output_digest=DIGEST,
    )
    legacy = ProjectGuideSufficiencyMutationResourceContext(
        resource_type="project_guide_sufficiency_mutation",
        resource_id=snapshot_id,
        operation_id=uuid4(),
        request_digest=DIGEST,
        scope_project_id=locator.project_id,
        guide_id=guide_id,
        guide_version="v1",
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=DIGEST,
        target_kind="run",
        execution_kind="setup_service",
        setup_generation=1,
        stale_output_digest=DIGEST,
        setup_service_custody=setup_custody,
    )
    request_value = legacy.model_dump(mode="json")
    request_value.update({"project_id": str(locator.project_id), "report_id": None})
    caller = PreparedAuthorizationInput(idempotency_key=uuid4(), request_value=request_value)
    legacy_handle = await _owned.service.prepare(
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
        caller,
        PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT,
            project_id=locator.project_id,
        ),
    )
    projection_adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with projection_adapter.prepare_sufficiency_projection(locator) as projection:
        projection_resource = projection_resource_context(
            "guide_sufficiency",
            projection.identity,
            sufficiency_facts(locator.project_id, locator.attempt_id),
        )
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await _owned.service.consume(
                legacy_handle,
                ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
                caller,
                projection_resource,
            )
    assert evidence.events == []


@pytest.mark.asyncio
async def test_projection_preparation_cannot_consume_legacy_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owned, session, evidence = _install_custody(monkeypatch)
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    legacy = ProjectGuideSufficiencyMutationResourceContext.model_construct(
        resource_type="project_guide_sufficiency_mutation",
        resource_id=uuid4(),
        scope_project_id=locator.project_id,
        execution_kind="setup_service",
    )
    adapter = GuideSufficiencyProjectionAuthorization(session)  # type: ignore[arg-type]
    async with adapter.prepare_sufficiency_projection(locator) as prepared:
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await prepared._custody.service.consume(  # type: ignore[attr-defined]
                prepared._handle,  # type: ignore[attr-defined]
                ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
                prepared._input,  # type: ignore[attr-defined]
                legacy,
            )
    assert evidence.events == []


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
@pytest.mark.parametrize(
    ("failure", "public_error"),
    (
        (PreparedAuthorizationHandleInvalid("bad"), PreparedAuthorizationInvalid),
        (
            PreparedAuthorizationUnsupported(AuthorizationDenialCode.RESOURCE_GUARD_DENIED),
            AuthorizationDenied,
        ),
        (AuthorizationEvidenceUnavailable("down"), AuthorizationUnavailable),
    ),
)
async def test_projection_replay_conceals_internal_failures(
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

        owned.service.validate_replay = fail  # type: ignore[method-assign]
        with pytest.raises(public_error):
            await prepared.validate_replay(facts, uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "public_error"),
    (
        (PreparedAuthorizationHandleInvalid("bad"), PreparedAuthorizationInvalid),
        (
            PreparedAuthorizationUnsupported(AuthorizationDenialCode.RESOURCE_GUARD_DENIED),
            AuthorizationDenied,
        ),
        (AuthorizationEvidenceUnavailable("down"), AuthorizationUnavailable),
    ),
)
async def test_projection_prepare_conceals_internal_entry_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    public_error: type[Exception],
) -> None:
    class FailingManager:
        async def __aenter__(self):
            raise failure

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(
        adapters, "fixed_service_prepared_authorization", lambda *_a, **_k: FailingManager()
    )
    locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
    adapter = GuideSufficiencyProjectionAuthorization(SimpleNamespace())  # type: ignore[arg-type]
    with pytest.raises(public_error):
        async with adapter.prepare_sufficiency_projection(locator):
            pass


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


@pytest.mark.asyncio
async def test_projection_consume_denial_still_closes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned, session, _evidence = custody()
    close_calls = 0
    original_close = owned.service.close

    def close() -> None:
        nonlocal close_calls
        close_calls += 1
        original_close()

    async def deny(*_args, **_kwargs):
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.RESOURCE_GUARD_DENIED)

    owned.service.close = close  # type: ignore[method-assign]

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
        owned.service.consume = deny  # type: ignore[method-assign]
        with pytest.raises(AuthorizationDenied):
            await prepared.consume_new(facts)
    assert close_calls == 1
