"""Hidden effect proof with real AUTH causes, feature authority and OUTBOX custody."""

from contextlib import asynccontextmanager
import pytest
from uuid import UUID
from app.core.identifiers import new_record_id
from sqlalchemy import select

from app.adapters.tasks import (
    TransactionalAssignmentInvalidationHandler,
)
from app.modules.outbox.api import HandlerOutcome
from app.modules.tasks.api.assignment_invalidation import (
    AssignmentInvalidationAuthority,
    AssignmentInvalidationTarget,
    PreparedAssignmentInvalidation,
)
from app.modules.tasks.models import TaskAssignment, WorkstreamTask, Submission
from app.modules.tasks.repository import TaskRepository
from tests.submission_fixtures import seed_retained_submission
from tests.test_tasks import (
    auth_headers,
    complete_submission_payload,
    set_dev_actor,
    admit_and_grant_project_submitter,
)
from tests.test_tasks import task_client as task_client, task_database_env as task_database_env
from tests.tasks.invalidation_support import (
    TracedFeatureAuthority,
    setup_assignment,
    revoke,
    invoked,
    snapshot,
)


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("kind", ["grant", "suspend", "deactivate", "link"])
async def test_exact_real_cause_releases_only_pre_submit_assignment(
    task_client, monkeypatch, started, kind
):
    s = await setup_assignment(task_client, monkeypatch, started=started)
    await revoke(s, kind)
    target, envelope = await invoked(s)
    before = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    task, assignments, events = await snapshot(s)
    assert task["status"] == "ready" and task["assigned_to"] is None
    assert (
        assignments[0]["status"] == "authority_revoked"
        and assignments[0]["released_at"] is not None
    )
    assert {k: v for k, v in task.items() if k.startswith("locked_")} == {
        k: v for k, v in before[0].items() if k.startswith("locked_")
    }
    assert {k: v for k, v in assignments[0].items() if k not in {"status", "released_at"}} == {
        k: v for k, v in before[1][0].items() if k not in {"status", "released_at"}
    }
    added = [event for event in events if event["id"] not in {old["id"] for old in before[2]}]
    assert len(added) == 1 and UUID(str(added[0]["id"])).version == 7
    assert added[0]["event_payload"]["references"]["assignment_id"] == str(target.assignment_id)
    assert added[0]["event_payload"]["references"]["authority_invalidation_event_id"] == str(target.authority_invalidation_event_id)
    assert added[0]["event_type"] == "TaskAssignmentAuthorityRevoked"
    assert all(event in events for event in before[2])
    claim_event = next(event for event in before[2] if event["event_type"] == "TaskClaimed")
    # Assignment time is its DB insertion time, not the claim transaction start.
    assert before[1][0]["assigned_at"] > claim_event["created_at"]
    assert [stage for stage, _ in s.trace] == ["prepare", "consume", "close"]
    from app.adapters.audit import committed_authority_invalidation
    from app.core.hashing import canonical_json_hash

    cause = await committed_authority_invalidation(s.sessions).read_invalidation(s.invalidation_id)
    from app.modules.tasks.service import LOCKED_CONTEXT_REQUIRED_FIELDS

    facts = s.trace[0][1]
    assert facts.task_status == before[0]["status"]
    assert facts.locked_context_hash == canonical_json_hash(
        {
            key: str(before[0][key]) if isinstance(before[0][key], UUID) else before[0][key]
            for key in LOCKED_CONTEXT_REQUIRED_FIELDS
        }
    )
    assert facts.target == target and facts.cause_event_id == cause.cause_event_id
    assert facts.delivery_event_id == envelope.claim.event_id
    assert facts.delivery_generation == envelope.claim.claim_generation
    assert facts.cause_digest == canonical_json_hash(cause.model_dump(mode="json"))
    assert facts.invocation_digest == canonical_json_hash(envelope.model_dump(mode="json"))
    after = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    assert await snapshot(s) == after
    assert len(s.trace) == 3


@pytest.mark.parametrize("origin", ["missing", "mismatched"])
async def test_fixture_requires_exact_canonical_publication_by_default(
    task_client, monkeypatch, origin
):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target = AssignmentInvalidationTarget(
        project_id=UUID(s.project["id"]),
        task_id=UUID(s.task["id"]),
        assignment_id=UUID(s.assignment["id"]),
        contributor_id=UUID(s.grant["actor_profile_id"]),
        authority_invalidation_event_id=s.invalidation_id,
    )
    if origin == "missing":
        target = target.model_copy(
            update={"authority_invalidation_event_id": new_record_id()}
        )
        message = "canonical assignment invalidation publication is required"
    else:
        target = target.model_copy(update={"contributor_id": new_record_id()})
        message = "canonical assignment invalidation publication does not match target"
    with pytest.raises(AssertionError, match=message):
        await invoked(s, target=target)


async def test_valid_delivery_cannot_substitute_target_or_cause(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, envelope = await invoked(s)
    before = await snapshot(s)
    for field in ("task_id", "assignment_id", "contributor_id", "authority_invalidation_event_id"):
        _, crossed = await invoked(
            s,
            target=target.model_copy(update={field: new_record_id()}),
            synthetic_transport=True,
        )
        assert await s.handler(crossed) is HandlerOutcome.REJECT
        assert await snapshot(s) == before
    for bad in (
        object(),
        envelope.model_copy(update={"payload_json": "{}"}),
        envelope.model_copy(update={"event_version": 2}),
        envelope.model_copy(update={"correlation_id": "forged"}),
    ):
        assert await s.handler(bad) is HandlerOutcome.REJECT
        assert await snapshot(s) == before
    assert s.trace == []
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE


async def test_invalid_authority_results_rollback(task_client, monkeypatch):
    from app.adapters.audit import _AssignmentInvalidationAudit

    audit_calls = []
    original = _AssignmentInvalidationAudit.record_release

    async def observed_audit(owner, evidence):
        audit_calls.append(evidence)
        await original(owner, evidence)

    monkeypatch.setattr(_AssignmentInvalidationAudit, "record_release", observed_audit)
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    before = await snapshot(s)
    for result in (
        None,
        AssignmentInvalidationAuthority("not-a-uuid", new_record_id(), "sha256:" + "a" * 64),
        AssignmentInvalidationAuthority(new_record_id(), "not-a-uuid", "sha256:" + "a" * 64),
        AssignmentInvalidationAuthority(new_record_id(), new_record_id(), None),
        AssignmentInvalidationAuthority(new_record_id(), new_record_id(), "not-a-digest"),
    ):

        class InvalidPrepared(PreparedAssignmentInvalidation):
            async def consume(self, facts):
                return result

        class InvalidAuthority:
            @asynccontextmanager
            async def prepare_assignment_invalidation(self, facts):
                yield InvalidPrepared()

        bad = TransactionalAssignmentInvalidationHandler(
            s.sessions,
            observer=s.h.delivery,
            authorization_factory=lambda session: InvalidAuthority(),
        )
        assert await bad(envelope) is HandlerOutcome.REJECT
        assert await snapshot(s) == before
        assert audit_calls == []


async def test_audit_failure_rolls_back_every_effect(task_client, monkeypatch):
    from app.adapters.audit import _AssignmentInvalidationAudit

    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    before = await snapshot(s)
    original = _AssignmentInvalidationAudit.record_release

    async def fail_after_evidence(owner, evidence):
        await original(owner, evidence)
        raise RuntimeError("test failure after effect and evidence flush")

    with monkeypatch.context() as patch:
        patch.setattr(_AssignmentInvalidationAudit, "record_release", fail_after_evidence)
        with pytest.raises(RuntimeError, match="after effect"):
            await s.handler(envelope)
    assert await snapshot(s) == before
    assert s.trace[-1][0] == "close"
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE


async def test_old_delivery_cannot_release_real_replacement_claim(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s, "suspend")
    target, envelope = await invoked(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    before_restore = await snapshot(s)
    response = await s.client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/reactivate",
        headers=auth_headers(),
        json={"reason": "Restore actor, not prior work"},
    )
    assert response.status_code == 200, response.text
    assert await snapshot(s) == before_restore
    set_dev_actor(monkeypatch, roles="viewer", subject="invalidation-submitter")
    claimed = await s.client.post(f"/api/v1/tasks/{s.task['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["assignment"]["id"] != s.assignment["id"]
    after = await snapshot(s)
    from app.adapters.audit import committed_authority_invalidation

    cause = await committed_authority_invalidation(s.sessions).read_invalidation(s.invalidation_id)
    new_assignment = next(
        row for row in after[1] if row["id"] == claimed.json()["assignment"]["id"]
    )
    assert before_restore[1][0]["assigned_at"] <= cause.recorded_at < new_assignment["assigned_at"]
    # A fully committed forged event cannot reuse an old cause for a newer assignment.
    _, retargeted = await invoked(
        s,
        target=target.model_copy(update={"assignment_id": UUID(new_assignment["id"])}),
        synthetic_transport=True,
    )
    assert await s.handler(retargeted) is HandlerOutcome.REJECT
    assert await snapshot(s) == after
    # A fresh transport event for the same immutable cause still addresses only the old assignment.
    _, duplicate = await invoked(s, target=target, synthetic_transport=True)
    assert await s.handler(duplicate) is HandlerOutcome.ACKNOWLEDGE
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    assert await snapshot(s) == after


async def test_released_work_can_be_claimed_by_another_eligible_contributor(
    task_client, monkeypatch
):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    other = await admit_and_grant_project_submitter(
        s.client, monkeypatch, s.project["id"], "next-contributor"
    )
    claim = await s.client.post(f"/api/v1/tasks/{s.task['id']}/claim", headers=auth_headers())
    assert claim.status_code == 200, claim.text
    task, assignments, _ = await snapshot(s)
    assert task["assigned_to"] == other["actor_profile_id"] and task["status"] == "claimed"
    assert {row["status"] for row in assignments} == {"active", "authority_revoked"}


async def test_existing_submission_and_revision_history_are_never_released(
    task_client, monkeypatch
):
    s = await setup_assignment(task_client, monkeypatch, started=True)
    await revoke(s, "suspend")
    target, envelope = await invoked(s)
    restored = await s.client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/reactivate",
        headers=auth_headers(),
        json={"reason": "Allow submission before pending invalidation delivery"},
    )
    assert restored.status_code == 200, restored.text

    # Reuse the admitted downstream packet fixture; this is not new ART intake proof.
    submission_id = await seed_retained_submission(
        s.task["id"], complete_submission_payload()
    )
    await revoke(s, "suspend")
    assert s.invalidation_id != target.authority_invalidation_event_id
    history_checks = []
    has_submission = TaskRepository.has_submission

    async def observe_history(owner, task_id):
        retained = await has_submission(owner, task_id)
        history_checks.append((task_id, retained))
        return retained

    monkeypatch.setattr(TaskRepository, "has_submission", observe_history)
    for state in (
        "submitted",
        "evaluation_pending",
        "review_pending",
        "needs_revision",
        "in_progress",
    ):
        async with s.sessions() as session, session.begin():
            task = await session.get(WorkstreamTask, s.task["id"])
            task.status = state  # Last case isolates the independent existing-Submission guard.
        before = await snapshot(s)
        async with s.sessions() as session:
            submission_before = dict(
                (
                    await session.execute(
                        select(Submission.__table__).where(Submission.id == submission_id)
                    )
                )
                .mappings()
                .one()
            )
        assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        assert await snapshot(s) == before
        async with s.sessions() as session:
            assert (
                dict(
                    (
                        await session.execute(
                            select(Submission.__table__).where(Submission.id == submission_id)
                        )
                    )
                    .mappings()
                    .one()
                )
                == submission_before
            )
    assert history_checks == [(target.task_id, True)]
    assert s.trace == []


async def test_inconsistent_assignment_cannot_be_released(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    for kind in ("status", "owner", "released"):
        async with s.sessions() as session, session.begin():
            task = await session.get(WorkstreamTask, s.task["id"])
            assignment = await session.get(TaskAssignment, s.assignment["id"])
            task.assigned_to = None if kind == "owner" else s.grant["actor_profile_id"]
            assignment.status = "authority_revoked" if kind == "status" else "active"
            assignment.released_at = envelope.claim.claimed_at if kind == "released" else None
        before = await snapshot(s)
        assert await s.handler(envelope) is HandlerOutcome.REJECT
        assert await snapshot(s) == before
    assert s.trace == []


async def test_release_requires_root_transaction_and_exact_prior_receipt(task_client, monkeypatch):
    from types import SimpleNamespace
    from app.adapters.audit import assignment_invalidation_audit, committed_authority_invalidation
    from app.adapters.outbox import outbox_invocation_fence
    from app.modules.audit.repository import AuditRepository
    from app.modules.tasks.assignment_invalidation import AssignmentInvalidationOperation
    from app.modules.tasks.api.assignment_invalidation import AssignmentInvalidationUnavailable
    from app.modules.tasks.models import AuditEvent

    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, envelope = await invoked(s)
    async with s.sessions() as session:
        operation = AssignmentInvalidationOperation(
            session,
            observer=s.h.delivery,
            fence=outbox_invocation_fence(session),
            causes=committed_authority_invalidation(s.sessions),
            authorization=TracedFeatureAuthority(session, []),
            audit=assignment_invalidation_audit(session),
        )
        with pytest.raises(AssignmentInvalidationUnavailable, match="root transaction"):
            await operation.reconcile(envelope)
        async with session.begin(), session.begin_nested():
            with pytest.raises(AssignmentInvalidationUnavailable, match="root transaction"):
                await operation.reconcile(envelope)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    before = await snapshot(s)
    async with s.sessions() as session:
        row = await AuditRepository(session).assignment_release_event(
            target.assignment_id, target.authority_invalidation_event_id,
        )
        original = {column.key: getattr(row, column.key) for column in AuditEvent.__table__.columns}
    for altered in (
        {**original, "event_payload": {"references": {}}},
        {**original, "entity_id": str(new_record_id())},
    ):

        async def bad_receipt(owner, assignment_id, cause_id):
            assert (assignment_id, cause_id) == (target.assignment_id, target.authority_invalidation_event_id)
            return SimpleNamespace(**altered)

        with monkeypatch.context() as patch:
            patch.setattr(AuditRepository, "assignment_release_event", bad_receipt)
            assert await s.handler(envelope) is HandlerOutcome.REJECT
        assert await snapshot(s) == before
    async with s.sessions() as session, session.begin():
        assignment = await session.get(TaskAssignment, s.assignment["id"])
        assignment.released_at = None
    inconsistent = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.REJECT
    assert await snapshot(s) == inconsistent
