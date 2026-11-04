"""Real feature PREP, immutable release custody and revocation behavior."""

import asyncio
from copy import copy, deepcopy
import pickle
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError

from app.adapters.auth import assignment_invalidation_authorization
from app.adapters.audit import assignment_invalidation_audit
from app.modules.audit.repository import AuditRepository
from app.modules.authorization.domain.assignment_invalidation import assignment_invalidation_resource
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.outbox.api import HandlerOutcome
from app.modules.tasks.api.assignment_invalidation import (
    AssignmentInvalidationUnavailable,
)
from app.modules.tasks.models import AuditEvent, TaskAssignment, WorkstreamTask
from tests.authorization.test_assignment_invalidation_contract import facts, substitutions
from tests.test_tasks import auth_headers, delete_audit_fixture_as_owner, set_dev_actor
from tests.test_tasks import task_client as task_client, task_database_env as task_database_env
from tests.tasks.invalidation_support import setup_assignment, revoke, invoked, snapshot


async def service_status(s, status):
    set_dev_actor(s.monkeypatch, roles="viewer", issuer=s.admin_identity[0], subject=s.admin_identity[1])
    route = (f"actor-identity-links/{s.feature_link}/revoke" if status == "revoked"
             else f"actors/{s.feature_actor}/{status}")
    response = await s.client.post(f"/api/v1/{route}", headers=auth_headers(), json={"reason": "Reconciler lifecycle proof"})
    assert response.status_code == 200, response.text


async def decisions(s):
    async with s.sessions() as session:
        return list((await session.scalars(select(AuditEvent.id).where(
            AuditEvent.action_id == "task.assignment.authority_reconcile"
        ))).all())


async def test_real_reconciliation_binds_decision(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, envelope = await invoked(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    async with s.sessions() as session:
        receipt = await assignment_invalidation_audit(session).read_release(target)
        event = await session.get(AuditEvent, str(receipt.authority.decision_id))
        assert event.event_type == "SensitiveAuthorizationAllowed"
        assert event.actor_id == str(s.feature_actor) and event.actor_ref_kind == "actor_profile"
        assert event.resource_type == "task" and event.resource_id == s.task["id"]
        assert event.project_id == s.project["id"]
        assert UUID(event.request_id) == envelope.claim.event_id
        assert UUID(event.correlation_id) == target.authority_invalidation_event_id
        digest = authorization_resource_digest(assignment_invalidation_resource(s.trace[0][1]))
        assert event.after_facts == {"allowed": True, "resource_context_digest": digest}
        assert receipt.authority.resource_context_digest == digest


@pytest.mark.parametrize("status", ["missing", "suspend", "deactivate", "revoked"])
async def test_reconciler_lifecycle_denies(task_client, monkeypatch, status):
    s = await setup_assignment(task_client, monkeypatch, reconciler=status != "missing")
    await revoke(s)
    _, envelope = await invoked(s)
    if status != "missing":
        await service_status(s, status)
    before = await snapshot(s)
    assert before[0]["status"] == "in_progress" and before[1][0]["status"] == "active"
    assert await s.handler(envelope) is HandlerOutcome.REJECT
    assert [stage for stage, _ in s.trace] == ["prepare"]
    assert await snapshot(s) == before
    assert await decisions(s) == []


async def test_prepared_reconciliation_binds_every_fact(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    value = facts().model_copy(update={"target": facts().target.model_copy(update={
        "project_id": UUID(s.project["id"]), "task_id": UUID(s.task["id"]),
    })})
    async with s.sessions() as session, session.begin():
        owner = assignment_invalidation_authorization(session)
        for field, changed in substitutions(value):
            async with owner.prepare_assignment_invalidation(value) as prepared:
                with pytest.raises(AssignmentInvalidationUnavailable, match="denied"):
                    await prepared.consume(changed)
                result = await prepared.consume(value)
                assert result.actor_profile_id == s.feature_actor, field
                with pytest.raises(AssignmentInvalidationUnavailable):
                    await prepared.consume(value)


async def test_prepared_reconciliation_custody(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    value = facts()
    async with s.sessions() as session:
        await session.begin()
        async with assignment_invalidation_authorization(session).prepare_assignment_invalidation(value) as prepared:
            for transfer in (copy, deepcopy, pickle.dumps):
                with pytest.raises(TypeError, match="process-local"):
                    transfer(prepared)
            await session.rollback()
            await session.begin()
            with pytest.raises(AssignmentInvalidationUnavailable):
                await prepared.consume(value)
        with pytest.raises(AssignmentInvalidationUnavailable):
            await prepared.consume(value)

    from app.modules.authorization.catalogue import ActionId
    from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid

    async with s.sessions() as first, s.sessions() as second:
        await first.begin()
        async with assignment_invalidation_authorization(first).prepare_assignment_invalidation(value) as original:
            await first.commit()
            async with second.begin():
                async with assignment_invalidation_authorization(second).prepare_assignment_invalidation(value) as foreign:
                    with pytest.raises(PreparedAuthorizationHandleInvalid):
                        await foreign._authority.service.consume(
                            original._handle, ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE,
                            original._input, assignment_invalidation_resource(value),
                        )


async def test_unavailable_evidence_is_not_terminal_rejection(task_client, monkeypatch):
    from app.modules.authorization.kernel import AuthorizationService
    from app.modules.authorization.runtime import AuthorizationEvidenceUnavailable

    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    before = await snapshot(s)
    original = AuthorizationService._stage_decision
    reached = []

    async def unavailable(owner, decision, *args):
        if decision.action_id.value == "task.assignment.authority_reconcile":
            reached.append(decision)
            raise AuthorizationEvidenceUnavailable("test evidence unavailable")
        return await original(owner, decision, *args)

    monkeypatch.setattr(AuthorizationService, "_stage_decision", unavailable)
    with pytest.raises(AuthorizationEvidenceUnavailable):
        await s.handler(envelope)
    assert len(reached) == 1 and reached[0].allowed
    assert await snapshot(s) == before and await decisions(s) == []

async def test_real_reconciliation_rollback(task_client, monkeypatch):
    from app.adapters.audit import _AssignmentInvalidationAudit

    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, envelope = await invoked(s)
    before = await snapshot(s)
    original = _AssignmentInvalidationAudit.record_release
    observed = []

    async def fail_after_staged(owner, evidence):
        await original(owner, evidence)
        session = owner._repo._session
        task = await session.get(WorkstreamTask, s.task["id"])
        assignment = await session.get(TaskAssignment, s.assignment["id"])
        decision = await session.get(AuditEvent, str(evidence.authority.decision_id))
        receipt = await AuditRepository(session).assignment_release_event(
            target.assignment_id, target.authority_invalidation_event_id,
        )
        assert task.status == "ready" and assignment.status == "authority_revoked"
        assert decision.event_type == "SensitiveAuthorizationAllowed"
        assert receipt.event_payload["authorization_resource_digest"] == decision.after_facts["resource_context_digest"]
        observed.append((decision.id, receipt.id))
        raise RuntimeError("after real staged release")

    with monkeypatch.context() as patch:
        patch.setattr(_AssignmentInvalidationAudit, "record_release", fail_after_staged)
        with pytest.raises(RuntimeError, match="after real staged"):
            await s.handler(envelope)
    assert len(observed) == 1
    assert await snapshot(s) == before
    assert await decisions(s) == []
    async with s.sessions() as session:
        for event_id in observed[0]:
            assert await session.get(AuditEvent, event_id) is None


@pytest.mark.parametrize("status", ["suspend", "deactivate", "revoked"])
async def test_release_replay_survives_service_revocation(task_client, monkeypatch, status):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, envelope = await invoked(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    before, ids = await snapshot(s), await decisions(s)
    await service_status(s, status)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    assert await snapshot(s) == before and await decisions(s) == ids
    async with s.sessions() as session:
        assert str((await assignment_invalidation_audit(session).read_release(target)).authority.decision_id) == ids[0]


async def test_reconciler_revocation_waits_for_effect(task_client, task_database_env, monkeypatch):
    from app.adapters.audit import _AssignmentInvalidationAudit

    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    staged, release = asyncio.Event(), asyncio.Event()
    original = _AssignmentInvalidationAudit.record_release

    async def pause(owner, evidence):
        await original(owner, evidence)
        staged.set()
        await asyncio.wait_for(release.wait(), 20)

    from auth_concurrency_support import wait_for_named_database_lock
    from app.modules.authorization.repository import AdminAuthorizationRepository

    waiter = "reconciler-revocation-" + new_record_id().hex
    original_control = AdminAuthorizationRepository.lock_control

    async def named_control(owner):
        await owner._session.execute(text("select set_config('application_name', :name, true)"), {"name": waiter})
        return await original_control(owner)

    with monkeypatch.context() as patch:
        patch.setattr(_AssignmentInvalidationAudit, "record_release", pause)
        patch.setattr(AdminAuthorizationRepository, "lock_control", named_control)
        effect = asyncio.create_task(s.handler(envelope))
        revocation = None
        try:
            await asyncio.wait_for(staged.wait(), 20)
            revocation = asyncio.create_task(service_status(s, "suspend"))
            await asyncio.wait_for(wait_for_named_database_lock(task_database_env, waiter), 15)
            assert not revocation.done()
        finally:
            release.set()
            assert await asyncio.wait_for(effect, 20) is HandlerOutcome.ACKNOWLEDGE
            if revocation is not None:
                await asyncio.wait_for(revocation, 20)
    assert (await snapshot(s))[0]["status"] == "ready"


async def test_release_receipt_rejects_substitution(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, envelope = await invoked(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    async with s.sessions() as session:
        stored = await AuditRepository(session).assignment_release_event(
            target.assignment_id, target.authority_invalidation_event_id,
        )
        assert stored is not None
        receipt = {column.key: getattr(stored, column.key) for column in AuditEvent.__table__.columns}
        await delete_audit_fixture_as_owner(session, receipt["id"])
        other_decision = await session.scalar(select(AuditEvent.id).where(
            AuditEvent.action_id == "task.claim", AuditEvent.event_type == "SensitiveAuthorizationAllowed"
        ))
        assert other_decision is not None
        alternate = dict((await session.execute(select(TaskAssignment.__table__).where(
            TaskAssignment.id == s.assignment["id"]
        ))).mappings().one())
        alternate["id"] = str(new_record_id())
        # This terminal reference does not assert a second start of the original work.
        # The unchanged insertion guard requires every new row's start stamp absent.
        alternate["started_at"] = None
        await session.execute(insert(TaskAssignment).values(**alternate))
        assert await session.scalar(select(TaskAssignment.id).where(
            TaskAssignment.id == alternate["id"],
            TaskAssignment.task_id == alternate["task_id"],
            TaskAssignment.project_id == alternate["project_id"],
            TaskAssignment.contributor_id == alternate["contributor_id"],
        )) == alternate["id"]
        for field in ("decision", "missing_decision", "actor", "project", "task", "assignment", "valid_assignment", "cause", "digest", "extra"):
            changed = deepcopy(receipt)
            changed["id"] = str(new_record_id())
            refs = changed["event_payload"]["references"]
            if field in {"decision", "missing_decision"}:
                refs["authorization_decision_id"] = other_decision if field == "decision" else str(new_record_id())
            elif field == "actor":
                changed["actor_id"] = s.grant["actor_profile_id"]
            elif field == "task":
                changed["entity_id"] = refs["task_id"] = str(new_record_id())
            elif field == "valid_assignment":
                # Every surrounding lookup succeeds; only the decision's
                # original facts commitment distinguishes this assignment.
                refs["assignment_id"] = alternate["id"]
                changed["event_payload"]["assignment_invalidation_facts"]["target"]["assignment_id"] = alternate["id"]
            elif field in {"project", "assignment", "cause"}:
                refs[{"project": "project_id", "assignment": "assignment_id", "cause": "authority_invalidation_event_id"}[field]] = str(new_record_id())
            elif field == "digest":
                changed["event_payload"]["authorization_resource_digest"] = "sha256:" + "f" * 64
            else:
                changed["event_payload"]["private_material"] = "forbidden"
            with pytest.raises(DBAPIError, match="assignment release authority mismatch"):
                async with session.begin_nested():
                    await session.execute(insert(AuditEvent).values(**changed))
        # A complete control reaches the very same insert and guard.
        control = deepcopy(receipt)
        control["id"] = str(new_record_id())
        transaction = await session.begin_nested()
        await session.execute(insert(AuditEvent).values(**control))
        await transaction.rollback()


async def test_real_authority_digest_mismatch_rolls_back(task_client, monkeypatch):
    from dataclasses import replace
    from app.adapters.audit import _AssignmentInvalidationAudit
    from app.modules.authorization.assignment_invalidation_authorization import _PreparedReconciliation
    from app.modules.tasks.api.assignment_invalidation import assignment_invalidation_resource_digest

    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, envelope = await invoked(s)
    before, prior_decisions = await snapshot(s), await decisions(s)
    consume = _PreparedReconciliation.consume
    record = _AssignmentInvalidationAudit.record_release
    observed = []

    async def wrong_digest(owner, facts):
        authority = await consume(owner, facts)
        altered = "sha256:" + "f" * 64
        assert altered != authority.resource_context_digest
        return replace(authority, resource_context_digest=altered)

    async def observe_real_decision(owner, evidence):
        assert evidence.authority.resource_context_digest != assignment_invalidation_resource_digest(evidence.facts)
        event = await owner._repo._session.get(AuditEvent, str(evidence.authority.decision_id))
        assert event.event_type == "SensitiveAuthorizationAllowed"
        task = await owner._repo._session.get(WorkstreamTask, s.task["id"])
        assignment = await owner._repo._session.get(TaskAssignment, s.assignment["id"])
        assert task.status == "ready" and assignment.status == "authority_revoked"
        observed.append(event.id)
        await record(owner, evidence)

    with monkeypatch.context() as patch:
        patch.setattr(_PreparedReconciliation, "consume", wrong_digest)
        patch.setattr(_AssignmentInvalidationAudit, "record_release", observe_real_decision)
        assert await s.handler(envelope) is HandlerOutcome.REJECT
    assert len(observed) == 1
    assert await snapshot(s) == before
    assert await decisions(s) == prior_decisions
    async with s.sessions() as session:
        assert await assignment_invalidation_audit(session).read_release(target) is None


async def test_release_receipt_rejects_out_of_range_generation(task_client, monkeypatch):
    from app.core.hashing import canonical_json_hash

    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, envelope = await invoked(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    async with s.sessions() as session:
        stored = await AuditRepository(session).assignment_release_event(
            target.assignment_id, target.authority_invalidation_event_id,
        )
        assert stored is not None
        receipt = {column.key: getattr(stored, column.key) for column in AuditEvent.__table__.columns}
        await delete_audit_fixture_as_owner(session, receipt["id"])
        decision = dict((await session.execute(select(AuditEvent.__table__).where(
            AuditEvent.id == receipt["event_payload"]["references"]["authorization_decision_id"]
        ))).mappings().one())
        for generation in (0, 2147483648, 2147483647):
            changed, allowed = deepcopy(receipt), deepcopy(decision)
            changed["id"], allowed["id"] = str(new_record_id()), str(new_record_id())
            allowed["entity_id"] = allowed["id"]
            payload = changed["event_payload"]
            payload["assignment_invalidation_facts"]["delivery_generation"] = generation
            digest = canonical_json_hash({"resource_context": {
                "resource_type": "task_authority", "resource_id": changed["entity_id"],
                "scope_project_id": payload["references"]["project_id"],
                "facts": payload["assignment_invalidation_facts"],
            }})
            payload["authorization_resource_digest"] = digest
            payload["references"]["authorization_decision_id"] = allowed["id"]
            allowed["after_facts"] = {"allowed": True, "resource_context_digest": digest}
            async with session.begin_nested() as nested:
                await session.execute(insert(AuditEvent).values(**allowed))
                if generation == 2147483647:
                    await session.execute(insert(AuditEvent).values(**changed))
                else:
                    with pytest.raises(DBAPIError, match="assignment release authority mismatch"):
                        async with session.begin_nested():
                            await session.execute(insert(AuditEvent).values(**changed))
                await nested.rollback()
