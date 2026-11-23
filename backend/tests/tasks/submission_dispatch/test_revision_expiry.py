"""Durable revision expiry keeps the old Submission and releases its assignment."""

from datetime import UTC, datetime, timedelta
from contextlib import asynccontextmanager
import asyncio
import json
import traceback
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from uuid import UUID

from app.adapters.auth import outbox_dispatch_authorization, revision_expiry_authorization
from app.adapters.outbox import outbox_delivery
from app.adapters.tasks import (
    TransactionalTaskRevisionExpiredNoticeHandler, TransactionalTaskRevisionExpiryHandler,
)
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.outbox.api import DeliveryOptions
from app.modules.outbox.api import HandlerOutcome
from app.modules.outbox.delivery import CommittedInvocationReader, OutboxDelivery
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.registry import HandlerRegistry
from app.modules.tasks.api.revision_expiry import REVISION_EXPIRED_EVENT, REVISION_EXPIRY_EVENT
from app.modules.tasks.api.revision_expiry import (
    TaskRevisionExpiryAuthorityFacts, revision_expiry_resource_digest,
)
from app.modules.tasks.revision.expiry_event import revision_expiry_event
from app.modules.tasks.revision.models import TaskRevisionExpiration, TaskRevisionPreparation
from app.modules.tasks.revision.service import project_current_revision
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from tests.tasks.post_submit_routing.backfill_support import assert_backfill_matches_live
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.tasks.post_submit_routing.remediation_support import remediation_source, no_economic_effects
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_dispatch.test_revision_capacity import _retain_pre_revision_source
from tests.tasks.submission_dispatch.test_replacement_creation import (
    _admission_status, _creation_snapshot, _ready_replacement,
)
from tests.tasks.test_public_submission_intake import _client, _payload
from tests.test_submission_predecessor_custody import _fixture_revision_context


def test_expiry_request_keeps_the_original_window_when_the_head_changes():
    """The scheduled event binds the original failure, not a later repair head."""
    manifest_id = new_record_id()
    manifest = SimpleNamespace(id=manifest_id, outcome_event_id=new_record_id())
    root = SimpleNamespace(
        id=new_record_id(), project_id=str(new_record_id()), task_id=str(new_record_id()),
        assignment_id=str(new_record_id()), contributor_id=str(new_record_id()),
        submission_id=str(new_record_id()), routing_manifest_id=manifest_id,
        sequence=1, predecessor_id=None,
        preparation_sha256="sha256:" + "a" * 64,
        deadline_at=datetime(2026, 10, 14, tzinfo=UTC) + timedelta(hours=24),
    )
    event = revision_expiry_event(manifest, root)
    assert event.event_type == REVISION_EXPIRY_EVENT
    assert event.idempotency_key == f"task.revision.expire:{manifest_id}"
    assert event.not_before_at == root.deadline_at
    assert event.payload["root_preparation_id"] == str(root.id)
    assert event.payload["root_preparation_sha256"] == root.preparation_sha256
    assert "head_preparation_id" not in event.payload

    from app.modules.authorization.catalogue import ActionId
    from app.modules.authorization.domain.audit_targets import project_authority_audit_target
    from app.modules.authorization.domain.resource_digest import authorization_resource_digest
    from app.modules.authorization.domain.revision_expiry import revision_expiry_resource

    from app.modules.tasks.api.revision_expiry import TaskRevisionExpiryTarget
    facts = TaskRevisionExpiryAuthorityFacts(
        target=TaskRevisionExpiryTarget.model_validate_json(json.dumps(event.payload)),
        head_preparation_id=new_record_id(),
        head_preparation_sha256="sha256:" + "b" * 64,
        delivery_event_id=new_record_id(), delivery_generation=1,
        invocation_digest="sha256:" + "c" * 64,
        task_status="needs_revision", assignment_status="active",
    )
    resource = revision_expiry_resource(facts)
    assert authorization_resource_digest(resource) == revision_expiry_resource_digest(facts)
    assert project_authority_audit_target(resource, ActionId.TASK_REVISION_EXPIRE) == (
        str(facts.target.project_id), "task", str(facts.target.task_id),
        "project", str(facts.target.project_id),
    )


async def _provision_expirer(factory):
    actor_id = new_record_id()
    async with factory() as session, session.begin():
        session.add(ActorProfile(
            id=str(actor_id), actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.TASK_REVISION_EXPIRER.value,
            created_by=str(actor_id),
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(new_record_id()), actor_profile_id=str(actor_id),
            issuer="workstream.internal", subject=ServiceIdentity.TASK_REVISION_EXPIRER.value,
            subject_kind="service", status="active", linked_by="workstream:system:bootstrap",
        ))
    return actor_id


async def _observed_expiry(h, handler, envelope):
    """Keep bounded owner diagnostics when durable delivery catches a handler error."""
    try:
        outcome = await handler(envelope)
        h.expiry_handler_outcome = outcome.value
        return outcome
    except Exception as exc:
        original = exc
        for _ in range(6):
            nested = getattr(original, "orig", None) or original.__cause__
            if nested is None or nested is original:
                break
            original = nested
        frames = traceback.extract_tb(exc.__traceback__)
        owner = next((
            f"{frame.filename.rsplit('/backend/', 1)[-1]}:{frame.lineno}:{frame.name}"
            for frame in reversed(frames) if "/backend/app/" in frame.filename
        ), None)
        h.expiry_handler_error = (
            type(original).__name__, getattr(original, "sqlstate", None),
            getattr(original, "constraint_name", None),
            str(original).splitlines()[0][:160], owner,
        )
        raise


async def expire_retained_revision(
    h, *, monkeypatch, isolated_database_env, ack_lost=False, deliver=True,
    window_seconds=None,
):
    """Exercise a pre-preparation retained failure through PM recovery and durable delivery."""
    source_id = await _fixture_revision_context(h)
    await _retain_pre_revision_source(h, source_id)
    async with h.factory() as session, session.begin():
        await session.execute(text(
            "ALTER TABLE public.task_post_submit_routing_manifests "
            "DISABLE TRIGGER task_routing_manifest_immutable"
        ))
        deadline = await session.scalar(text("""
            UPDATE public.task_post_submit_routing_manifests m
            SET created_at=clock_timestamp()-make_interval(hours => p.revision_deadline_hours)
                +make_interval(secs => :seconds)
            FROM public.submissions s JOIN public.revision_policies p
              ON p.id=s.locked_revision_policy_id
            WHERE m.id=:id AND s.id=m.submission_id
            RETURNING m.created_at+make_interval(hours => p.revision_deadline_hours)
        """), {"id": source_id, "seconds": -3600 if window_seconds is None else window_seconds})
        await session.execute(text(
            "ALTER TABLE public.task_post_submit_routing_manifests "
            "ENABLE TRIGGER task_routing_manifest_immutable"
        ))
    async with _client(h, monkeypatch, isolated_database_env) as client:
        recovered = await client.post(
            f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair",
            json={"routing_manifest_id": str(source_id), "reason": "Recover retained failure for expiry proof"},
            headers={"Idempotency-Key": str(new_record_id())},
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["disposition"] == (
            "revision_deadline_expired" if window_seconds is None else "ready"
        )
        h.revision_preparation_id = UUID(recovered.json()["preparation_id"])
        h.revision_preparation_sha256 = recovered.json()["preparation_sha256"]
    async with h.factory() as session:
        event = await session.scalar(select(OutboxEvent).where(
            OutboxEvent.event_type == REVISION_EXPIRY_EVENT,
            OutboxEvent.idempotency_key == f"task.revision.expire:{source_id}",
        ))
        assert event is not None and event.not_before_at == deadline
        event_id = event.event_id
    await _provision_expirer(h.factory)
    handler = TransactionalTaskRevisionExpiryHandler(
        h.factory, observer=CommittedInvocationReader(h.factory),
        authorization_factory=revision_expiry_authorization,
    )

    async def observed_expiry(envelope):
        return await _observed_expiry(h, handler, envelope)

    delivery = outbox_delivery(
        h.factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry(
            [
                (REVISION_EXPIRY_EVENT, 1, observed_expiry),
                (REVISION_EXPIRED_EVENT, 1, TransactionalTaskRevisionExpiredNoticeHandler(
                    h.factory, observer=CommittedInvocationReader(h.factory),
                )),
            ],
            replay_safe=frozenset({(REVISION_EXPIRY_EVENT, 1)}),
        ),
        options=(DeliveryOptions(lease_seconds=30, handler_timeout_seconds=25,
                                 retry_base_seconds=1, retry_cap_seconds=1)
                 if ack_lost else DeliveryOptions()),
    )
    h.expiry_delivery = delivery
    if ack_lost:
        claim = await delivery.claim(event_id, h.request.project_id, "revision-expiry-proof")
        assert claim is not None
        h.expiry_claim_expires_at = claim.claim_expires_at
        envelope = await delivery._begin_invocation(claim)
        assert envelope is not None
        assert await observed_expiry(envelope) is HandlerOutcome.ACKNOWLEDGE
    elif deliver:
        delivered = await delivery.deliver(event_id, h.request.project_id, "revision-expiry-proof")
        assert delivered is not None
        assert json.loads(delivered.outcome_json)["delivery_state"] == "acknowledged", (
            delivered.outcome_json,
            getattr(h, "expiry_handler_outcome", None),
            getattr(h, "expiry_handler_error", None),
        )
    return source_id, recovered.json(), event_id


async def _assert_expired_assignment_immutable(h, receipt):
    """A committed expiry freezes its assignment and all receipt-bound history."""
    assignment_id = receipt.assignment_id
    receipt_id = receipt.id

    async def custody():
        async with h.factory() as session:
            row = (await session.execute(text("""
                SELECT to_jsonb(a),to_jsonb(e),
                  (SELECT jsonb_agg(to_jsonb(s) ORDER BY s.version)
                     FROM public.submissions s WHERE s.task_assignment_id=a.id),
                  (SELECT jsonb_agg(to_jsonb(p) ORDER BY p.sequence)
                     FROM public.task_revision_preparations p
                     WHERE p.routing_manifest_id=e.routing_manifest_id),
                  (SELECT to_jsonb(o) FROM public.outbox_events o
                     WHERE o.event_id=e.outcome_event_id),
                  (SELECT to_jsonb(v) FROM public.audit_events v WHERE v.id=e.audit_event_id),
                  public.task_revision_expired_assignment_current(
                    e.assignment_id,e.source_submission_id)
                FROM public.task_assignments a
                JOIN public.task_revision_expirations e ON e.assignment_id=a.id
                WHERE a.id=:assignment AND e.id=:receipt
            """), {"assignment": assignment_id, "receipt": receipt_id})).one()
            assert row[-1] is True
            return row

    before = await custody()
    attacks = (
        ("UPDATE public.task_assignments SET status='active' WHERE id=:assignment", {}),
        ("UPDATE public.task_assignments SET released_at=NULL WHERE id=:assignment", {}),
        ("UPDATE public.task_assignments SET released_at=released_at+interval '1 second' "
         "WHERE id=:assignment", {}),
        ("UPDATE public.task_assignments SET accepted_at=accepted_at+interval '1 second' "
         "WHERE id=:assignment", {}),
        ("UPDATE public.task_assignments SET id=:new_assignment,project_id=:new_project,"
         "task_id=:new_task,contributor_id=:new_contributor WHERE id=:assignment", {
             "new_assignment": new_record_id(), "new_project": new_record_id(),
             "new_task": new_record_id(), "new_contributor": new_record_id(),
         }),
        ("UPDATE public.task_assignments SET submitter_contribution_policy_version_id=:replacement "
         "WHERE id=:assignment", {"replacement": new_record_id()}),
        ("DELETE FROM public.task_assignments WHERE id=:assignment", {}),
    )
    for statement, parameters in attacks:
        with pytest.raises(DBAPIError) as rejected:
            async with h.factory() as session, session.begin():
                await session.execute(text(statement), parameters | {"assignment": assignment_id})
                raise AssertionError("terminal assignment mutation unexpectedly succeeded")
        assert rejected.value.orig.sqlstate == "23514"
        database_error = rejected.value.orig.__cause__
        assert database_error.constraint_name == "ck_revision_expired_assignment_immutable"
        assert await custody() == before


async def test_due_failure_auto_rejects_and_releases_with_immutable_receipt(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            source_before = await session.scalar(text(
                "SELECT to_jsonb(s)-ARRAY['attempt_status','status_reason','decided_at','updated_at'] "
                "FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id})
        source_id, recovered, event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
        )
        async with h.factory() as session:
            receipt = await session.scalar(select(TaskRevisionExpiration).where(
                TaskRevisionExpiration.routing_manifest_id == source_id,
            ))
            assert receipt is not None
            assert receipt.root_preparation_id == receipt.head_preparation_id
            assert receipt.root_preparation_id == UUID(recovered["preparation_id"])
            repair_target = (await session.execute(text("""
                SELECT a.resource_type,a.resource_id FROM public.task_revision_preparations p
                JOIN public.audit_events a ON a.id=p.authorization_decision_id
                WHERE p.id=:preparation
            """), {"preparation": receipt.root_preparation_id})).one()
            assert repair_target == ("project", str(h.request.project_id))
            assert receipt.delivery_event_id == event_id
            outcome = await session.get(OutboxEvent, receipt.outcome_event_id)
            assert outcome is not None
            assert outcome.event_type == REVISION_EXPIRED_EVENT
            assert outcome.causation_event_id == event_id
            assert outcome.payload["expiration_receipt_id"] == str(receipt.id)
            assert outcome.payload["authorization_decision_id"] == str(receipt.authorization_decision_id)
            assert outcome.payload["audit_event_id"] == str(receipt.audit_event_id)
            assert await session.scalar(text(
                "SELECT count(*) FROM public.outbox_events "
                "WHERE event_type='TaskRevisionExpired' AND idempotency_key=:key"
            ), {"key": f"task.revision.expired:{source_id}"}) == 1
            assert receipt.deadline_at <= receipt.expired_at
            assert await session.scalar(text(
                "SELECT to_jsonb(s)-ARRAY['attempt_status','status_reason','decided_at','updated_at'] "
                "FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id}) == source_before
            # The expiry receipt, not the caller, supplies the rejection time and reason.
            assert (await session.execute(text(
                "SELECT attempt_status,status_reason,decided_at FROM public.submissions WHERE id=:id"
            ), {"id": h.created.submission_id})).one() == (
                "rejected", "revision_deadline_expired", receipt.expired_at,
            )
            task = (await session.execute(text(
                "SELECT status,assigned_to FROM public.workstream_tasks WHERE id=:id"
            ), {"id": h.request.task_id})).one()
            assignment = (await session.execute(text(
                "SELECT status,released_at FROM public.task_assignments WHERE id=:id"
            ), {"id": h.request.assignment_id})).one()
            assert task == ("ready", None)
            assert assignment == ("revision_expired", receipt.expired_at)
            assert await session.scalar(text(
                "SELECT public.task_revision_expired_assignment_current(:assignment,:submission)"
            ), {"assignment": h.request.assignment_id, "submission": h.created.submission_id}) is True
            await no_economic_effects(session)
        await _assert_expired_assignment_immutable(h, receipt)
        acknowledged = await h.expiry_delivery.deliver(
            receipt.outcome_event_id, h.request.project_id, "revision-expired-notice-proof",
        )
        assert acknowledged is not None
        assert json.loads(acknowledged.outcome_json)["delivery_state"] == "acknowledged"
        async with _client(h, monkeypatch, isolated_database_env) as client:
            history = await client.get(f"/api/v1/tasks/{h.request.task_id}/submissions")
            assert history.status_code == 200, history.text
            row = next(item for item in history.json()["items"]
                       if item["id"] == str(h.created.submission_id))
            assert row["status"] == "rejected"
            assert row["status_reason"] == "revision_deadline_expired"
            assert row["decided_at"] is not None
            claimed = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/claim",
                headers={"Idempotency-Key": str(new_record_id())},
            )
            assert claimed.status_code == 200, claimed.text
            assert UUID(claimed.json()["assignment"]["id"]) != h.request.assignment_id
        async with h.factory() as session:
            assert (await session.execute(text(
                "SELECT status,released_at FROM public.task_assignments WHERE id=:assignment"
            ), {"assignment": h.request.assignment_id})).one() == (
                "revision_expired", receipt.expired_at,
            )
            assert await session.scalar(text(
                "SELECT public.task_revision_expired_assignment_current(:assignment,:submission)"
            ), {"assignment": h.request.assignment_id,
                 "submission": h.created.submission_id}) is True
        await assert_backfill_matches_live(h.factory)


async def test_late_coverage_return_inherits_the_expired_window_and_expires_once(
    tmp_path, isolated_database_env, monkeypatch,
):
    """A second coverage return routed after the first deadline is blocked, not stuck.

    Both coverage sources share one deadline: the superseded first source's
    expiry acknowledges without effect and only the second attempt is rejected.
    """
    from app.modules.tasks.models import SubmissionDispatch
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.tasks.submission_dispatch.test_revision_capacity import (
        COVERAGE_GAP, _fail_current_submission, _revision_http_runtime, _revision_upload_headers,
    )

    async with remediation_source(
        tmp_path, isolated_database_env, human_review_required=False, findings=COVERAGE_GAP,
    ) as h:
        first_id = h.created.submission_id
        first_source, first_window, first_event = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
            deliver=False, window_seconds=75,
        )
        async with _client(h, monkeypatch, isolated_database_env) as client:
            data = revision_archive(h.data)
            settings, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, data)
            created = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submissions",
                headers=_revision_upload_headers(h), content=data,
            )
            assert created.status_code == 202, created.text
            assert len(calls) == 1 and not errors, errors
        deadline = datetime.fromisoformat(first_window["deadline_at"])
        assert datetime.fromisoformat(created.json()["accepted_at"].replace("Z", "+00:00")) < deadline
        async with h.factory() as session:
            remaining = (deadline - await session.scalar(select(func.clock_timestamp()))).total_seconds()
        await asyncio.sleep(max(0, remaining) + 0.5)
        submission_id = await finalize_retained_intake(h.factory, SimpleNamespace(
            operation_id=UUID(created.json()["operation_id"]), store=h.store.wrapped,
            namespace=h.namespace, settings=settings))
        async with h.factory() as session:
            h.created = (await session.get(SubmissionDispatch, submission_id)).result()
            assert h.created.submission_version == 2
            operation = await session.get(SubmissionIntakeOperation, UUID(created.json()["operation_id"]))
            assert operation.finalized_submission_id == str(submission_id)
            assert operation.finalized_at >= deadline
        await _fail_current_submission(h, findings=COVERAGE_GAP, route=False)
        second_source = await _fixture_revision_context(h)
        async with h.factory() as session:
            window = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            # The inherited window has passed: routing commits a blocked preparation.
            assert (window.outcome, window.blocked_reason, window.next_revision_round) == (
                "blocked", "revision_deadline_expired", 0,
            )
            assert (window.requested_at, window.deadline_at) == (
                datetime.fromisoformat(first_window["requested_at"]), deadline,
            )
            second_event = await session.scalar(select(OutboxEvent.event_id).where(
                OutboxEvent.event_type == REVISION_EXPIRY_EVENT,
                OutboxEvent.idempotency_key == f"task.revision.expire:{second_source}",
            ))
        for event_id in (first_event, second_event):
            delivered = await h.expiry_delivery.deliver(
                event_id, h.request.project_id, "shared-deadline-expiry",
            )
            assert delivered is not None
            assert json.loads(delivered.outcome_json)["delivery_state"] == "acknowledged", (
                delivered.outcome_json, getattr(h, "expiry_handler_error", None),
            )
        async with h.factory() as session:
            receipts = (await session.scalars(select(TaskRevisionExpiration))).all()
            assert [receipt.routing_manifest_id for receipt in receipts] == [second_source]
            assert first_source != second_source
            attempts = (await session.execute(text(
                "SELECT id, attempt_status, status_reason FROM public.submissions ORDER BY version"
            ))).all()
            assert [(str(row[0]), row[1], row[2]) for row in attempts] == [
                (str(first_id), "needs_revision", "checker_coverage_incomplete"),
                (str(h.created.submission_id), "rejected", "revision_deadline_expired"),
            ]
            assert await session.scalar(text(
                "SELECT status FROM public.workstream_tasks WHERE id=:id"
            ), {"id": h.request.task_id}) == "ready"


async def test_expiry_replays_one_receipt_when_effect_commits_before_ack(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id, _, event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
            ack_lost=True,
        )
        async with h.factory() as session:
            db_now = await session.scalar(select(func.clock_timestamp()))
        remaining = (h.expiry_claim_expires_at - db_now).total_seconds()
        await asyncio.sleep(max(0, remaining) + 0.2)
        recovered = await h.expiry_delivery.recover(event_id, h.request.project_id)
        assert recovered is not None
        assert json.loads(recovered.outcome_json)["delivery_state"] == "retryable"
        assert json.loads(recovered.outcome_json)["invocation_unknown"] is True
        await asyncio.sleep(1.1)
        redelivered = await h.expiry_delivery.deliver(
            event_id, h.request.project_id, "revision-expiry-replay-proof")
        assert redelivered is not None
        assert json.loads(redelivered.outcome_json)["delivery_state"] == "acknowledged"
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT count(*) FROM public.task_revision_expirations WHERE routing_manifest_id=:source"
            ), {"source": source_id}) == 1
            assert await session.scalar(text(
                "SELECT count(*) FROM public.audit_events "
                "WHERE event_type='TaskRevisionExpired' "
                "AND event_payload->'references'->>'outbox_event_id'=:event"
            ), {"event": str(event_id)}) == 1


async def _wait_until_revision_due(h, event_id):
    """Cross the real PostgreSQL deadline without replacing a production clock."""
    async with h.factory() as session:
        deadline = (await session.get(OutboxEvent, event_id)).not_before_at
        now = await session.scalar(select(func.clock_timestamp()))
    remaining = max(0, (deadline - now).total_seconds())
    assert remaining <= 60
    while remaining > 0:
        await asyncio.sleep(min(remaining, 30))
        async with h.factory() as session:
            now = await session.scalar(select(func.clock_timestamp()))
        remaining = max(0, (deadline - now).total_seconds())
    async with h.factory() as session:
        assert await session.scalar(select(func.clock_timestamp())) >= deadline


async def _ready_expiry_race_replacement(h):
    """Diagnose a real PRE failure before the contenders reach final creation."""
    try:
        return await _ready_replacement(h, revision_archive(h.data))
    except Exception as exc:
        async with h.factory() as session:
            root = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            view = await project_current_revision(session, root)
            now = await session.scalar(select(func.clock_timestamp()))
        raise AssertionError(
            f"race PRE failed: {type(exc).__name__}; "
            f"remaining_database_seconds={(root.deadline_at - now).total_seconds():.3f}; "
            f"disposition={view.disposition}"
        ) from exc


async def _wait_for_staged_submission(staged, final_request, *, timeout=15):
    """Retain an early real POST failure instead of hiding it behind a stage timeout."""
    observed = asyncio.create_task(staged.wait())
    try:
        done, _ = await asyncio.wait(
            (observed, final_request), timeout=timeout, return_when=asyncio.FIRST_COMPLETED,
        )
        if final_request in done:
            response = final_request.result()
            pytest.fail(
                "final POST ended before staged creation: "
                f"status={response.status_code}; body={response.text[:1200]}"
            )
        assert observed in done, f"request did not reach the observed stage within {timeout} seconds"
    finally:
        observed.cancel()
        await asyncio.gather(observed, return_exceptions=True)


def _assert_race_expiry_acknowledged(h, delivered):
    assert delivered is not None
    assert json.loads(delivered.outcome_json)["delivery_state"] == "acknowledged", (
        delivered.outcome_json,
        getattr(h, "expiry_handler_outcome", None),
        getattr(h, "expiry_handler_error", None),
    )


async def _assert_expired_creation_absent(h, source_id, admission_id, before):
    # Delivery changes OUTBOX custody and TASK status. Every finalization owner
    # before those two snapshot columns must remain exactly as before the race.
    after = await _creation_snapshot(h)
    assert after[:8] == before[:8]
    assert [event for event in after[8]
            if event["event_type"] == "PostSubmissionEvaluationRequested"] == [
                event for event in before[8]
                if event["event_type"] == "PostSubmissionEvaluationRequested"
            ]
    assert await _admission_status(h, admission_id) == "ready"
    async with h.factory() as session:
        assert await session.scalar(text(
            "SELECT count(*) FROM public.task_revision_expirations WHERE routing_manifest_id=:source"
        ), {"source": source_id}) == 1
        # Expiry, not the losing final POST, decided the source attempt.
        assert (await session.execute(text(
            "SELECT attempt_status,status_reason FROM public.submissions WHERE id=:id"
        ), {"id": h.created.submission_id})).one() == ("rejected", "revision_deadline_expired")
        assert (await session.execute(text(
            "SELECT status,assigned_to FROM public.workstream_tasks WHERE id=:task"
        ), {"task": h.request.task_id})).one() == ("ready", None)
        assert await session.scalar(text(
            "SELECT status FROM public.task_assignments WHERE id=:assignment"
        ), {"assignment": h.request.assignment_id}) == "revision_expired"
        await no_economic_effects(session)


async def _assert_expired_intake_absent(h, source_id, operation_id, before):
    """Losing T4 keeps sealed-byte cleanup custody without creating product facts."""
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    after = await _creation_snapshot(h)
    assert after[:8] == before[:8]
    assert [e for e in after[8] if e["event_type"] in {"PostSubmissionEvaluationRequested", "SubmissionFinalizationRequested"}] == [
        e for e in before[8] if e["event_type"] in {"PostSubmissionEvaluationRequested", "SubmissionFinalizationRequested"}]
    async with h.factory() as session:
        operation = await session.get(SubmissionIntakeOperation, operation_id)
        assert operation.state == "failed" and operation.acceptance_receipt is None
        assert operation.finalization_event_id is None and operation.finalized_submission_id is None
        charge = await session.get(SubmissionSourceCharge, operation_id)
        assert charge is not None and charge.state == "sealed"
        assert charge.accounted_bytes == operation.raw_byte_count > 0
        assert await session.scalar(text(
            "SELECT count(*) FROM public.task_revision_expirations WHERE routing_manifest_id=:source"
        ), {"source": source_id}) == 1
        assert (await session.execute(text(
            "SELECT attempt_status,status_reason FROM public.submissions WHERE id=:id"
        ), {"id": h.created.submission_id})).one() == ("rejected", "revision_deadline_expired")
        assert (await session.execute(text(
            "SELECT status,assigned_to,active_submission_operation_id FROM public.workstream_tasks WHERE id=:task"
        ), {"task": h.request.task_id})).one() == ("ready", None, None)
        assert await session.scalar(text(
            "SELECT status FROM public.task_assignments WHERE id=:assignment"
        ), {"assignment": h.request.assignment_id}) == "revision_expired"
        await no_economic_effects(session)


async def _redeliver_deferred_expiry(h, source_id, event_id, delivered):
    """Active foreground drains before the same due expiry releases its assignment."""
    assert delivered is not None
    outcome = json.loads(delivered.outcome_json)
    assert outcome["delivery_state"] == "retryable" and outcome["error_code"] == "RETRY_REQUESTED"
    assert outcome["invocation_unknown"] is False
    assert h.expiry_handler_outcome == HandlerOutcome.RETRY.value
    assert getattr(h, "expiry_handler_error", None) is None
    async with h.factory() as session:
        assert await session.scalar(select(func.count(TaskRevisionExpiration.id))) == 0
        assert await session.scalar(select(func.count(OutboxEvent.event_id)).where(
            OutboxEvent.event_type == REVISION_EXPIRED_EVENT)) == 0
        assert (await session.execute(text(
            "SELECT status,active_submission_operation_id FROM public.workstream_tasks WHERE id=:id"
        ), {"id": h.request.task_id})).one() == ("needs_revision", None)
        assert await session.scalar(text(
            "SELECT status FROM public.task_assignments WHERE id=:id"
        ), {"id": h.request.assignment_id}) == "active"
        await no_economic_effects(session)
        event = await session.get(OutboxEvent, str(event_id))
        assert event.idempotency_key == f"task.revision.expire:{source_id}"
        delay = (event.next_attempt_at - await session.scalar(select(func.clock_timestamp()))).total_seconds()
    await asyncio.sleep(max(0, delay) + 0.2)
    retried = await h.expiry_delivery.deliver(event_id, h.request.project_id, "expiry-after-foreground-drain")
    _assert_race_expiry_acknowledged(h, retried)
    assert retried.claim.event_id == delivered.claim.event_id
    assert retried.claim.claim_generation == delivered.claim.claim_generation + 1


async def test_due_expiry_and_ready_final_submission_wait_for_task_lock(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Expiry wins TASK custody after real PRE but before accepted handoff."""
    from contextvars import ContextVar
    from app.modules.artifacts.intake.foreground_admission import ForegroundIntakeAdmission
    from tests.tasks.submission_dispatch.test_revision_capacity import (
        _revision_http_runtime, _revision_upload_headers,
    )
    accepting = ContextVar("expiry_race_accepting", default=False)
    pre_done, release = asyncio.Event(), asyncio.Event()
    original_accept = ForegroundIntakeAdmission.accept
    operations = []

    async def pause_accept(admission, owner, *args, **kwargs):
        operations.append(owner.operation_id)
        pre_done.set()
        await asyncio.wait_for(release.wait(), 90)
        token = accepting.set(True)
        try:
            return await original_accept(admission, owner, *args, **kwargs)
        finally:
            accepting.reset(token)
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id, _, event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
            deliver=False, window_seconds=60,
        )
        expiry_name = f"expiry-final-race-{new_record_id().hex}"
        final_name = f"submission-final-race-{new_record_id().hex}"
        original_expiry_lock = TaskRepository.lock_project_task
        original_final_lock = TaskRepository.get_task

        async def expiry_lock(repository, *args, **kwargs):
            await repository._session.execute(text(
                "SELECT set_config('application_name',:name,true)"
            ), {"name": expiry_name})
            return await original_expiry_lock(repository, *args, **kwargs)

        async def final_lock(repository, *args, **kwargs):
            if accepting.get() and kwargs.get("for_update"):
                await repository._session.execute(text(
                    "SELECT set_config('application_name',:name,true)"
                ), {"name": final_name})
            return await original_final_lock(repository, *args, **kwargs)

        pending = []
        async with _client(h, monkeypatch, isolated_database_env) as client:
            data = revision_archive(h.data)
            _, errors, calls = await _revision_http_runtime(h, client, tmp_path, monkeypatch, data)
            with monkeypatch.context() as patch:
                patch.setattr(ForegroundIntakeAdmission, "accept", pause_accept)
                patch.setattr(TaskRepository, "lock_project_task", expiry_lock)
                patch.setattr(TaskRepository, "get_task", final_lock)
                try:
                    pending.append(asyncio.create_task(client.post(
                        f"/api/v1/tasks/{h.request.task_id}/submissions",
                        headers=_revision_upload_headers(h), content=data)))
                    await _wait_for_staged_submission(pre_done, pending[0], timeout=60)
                    assert len(calls) == 1 and not errors, errors
                    before = await _creation_snapshot(h)
                    await _wait_until_revision_due(h, event_id)
                    async with h.factory() as holder, holder.begin():
                        await holder.execute(text(
                            "SELECT id FROM public.workstream_tasks WHERE id=:task FOR UPDATE"
                        ), {"task": h.request.task_id})
                        pending.append(asyncio.create_task(h.expiry_delivery.deliver(
                            event_id, h.request.project_id, "expiry-ready-final-proof",
                        )))
                        await asyncio.wait_for(wait_for_named_database_lock(
                            isolated_database_env, expiry_name,
                        ), 15)
                        release.set()
                        await asyncio.wait_for(wait_for_named_database_lock(
                            isolated_database_env, final_name,
                        ), 15)
                        assert all(not contender.done() for contender in pending)
                    final, delivered = await asyncio.wait_for(asyncio.gather(*pending), 30)
                finally:
                    release.set()
                    for contender in pending:
                        if not contender.done():
                            contender.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
        assert final.status_code == 409, final.text
        assert final.json()["error"]["code"] == "revision_deadline_expired"
        await _redeliver_deferred_expiry(h, source_id, event_id, delivered)
        assert len(operations) == 1
        await _assert_expired_intake_absent(h, source_id, operations[0], before)


@pytest.mark.parametrize("commit_before_deadline", [True, False])
async def test_final_submission_commit_boundary_serializes_expiry(
    tmp_path, isolated_database_env, monkeypatch, commit_before_deadline,
):
    """A timely final commit wins; a late commit rolls back every staged owner."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id, _, event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
            deliver=False, window_seconds=60,
        )
        prepared, admission_id = await _ready_expiry_race_replacement(h)
        before = await _creation_snapshot(h)
        staged, release = asyncio.Event(), asyncio.Event()
        holder_pid = []
        expiry_name = f"expiry-commit-wait-{new_record_id().hex}"
        original_create = TaskSubmissionCreationService.create
        original_authority = OutboxDelivery._authority

        async def pause_staged_creation(service, request):
            # Execute actual creation, verified consumption, evaluation and
            # outbox append; retain its root transaction before deferred checks.
            result = await original_create(service, request)
            assert result.submission_version == 2
            holder_pid.append(await service._session.scalar(text("SELECT pg_backend_pid()")))
            staged.set()
            await asyncio.wait_for(release.wait(), 75)
            return result

        @asynccontextmanager
        async def named_delivery_authority(delivery, session, **selectors):
            await session.execute(text(
                "SELECT set_config('application_name',:name,true)"
            ), {"name": expiry_name})
            async with original_authority(delivery, session, **selectors) as authority:
                yield authority

        pending = []
        async with _client(h, monkeypatch, isolated_database_env) as client:
            with monkeypatch.context() as patch:
                patch.setattr(TaskSubmissionCreationService, "create", pause_staged_creation)
                patch.setattr(OutboxDelivery, "_authority", named_delivery_authority)
                try:
                    pending.append(asyncio.create_task(client.post(
                        f"/api/v1/tasks/{h.request.task_id}/submissions",
                        json=_payload(prepared, admission_id),
                    )))
                    await _wait_for_staged_submission(staged, pending[0])
                    assert (await _creation_snapshot(h))[:8] == before[:8]
                    assert await _admission_status(h, admission_id) == "ready"
                    if commit_before_deadline:
                        # OUTBOX cannot claim a future expiry. Finalization wins
                        # by committing before the due worker can acquire TASK.
                        assert await h.expiry_delivery.deliver(
                            event_id, h.request.project_id, "predeadline-final-proof",
                        ) is None
                        release.set()
                        final = await asyncio.wait_for(pending[0], 15)
                        assert final.status_code == 201, final.text
                        assert final.json()["submission_version"] == 2
                        await _wait_until_revision_due(h, event_id)
                        delivered = await h.expiry_delivery.deliver(
                            event_id, h.request.project_id, "stale-expiry-final-proof",
                        )
                    else:
                        await _wait_until_revision_due(h, event_id)
                        pending.append(asyncio.create_task(h.expiry_delivery.deliver(
                            event_id, h.request.project_id, "deferred-final-expiry-proof",
                        )))
                        # Fully staged creation also holds owner custody used by
                        # OUTBOX's claim. Observe its real wait before release.
                        await asyncio.wait_for(wait_for_named_database_lock(
                            isolated_database_env, expiry_name,
                            expected_blocker_pid=holder_pid[0],
                        ), 15)
                        assert not pending[1].done()
                        release.set()
                        final, delivered = await asyncio.wait_for(asyncio.gather(*pending), 30)
                        assert final.status_code == 409, final.text
                        assert final.json()["error"]["code"] == "revision_deadline_expired"
                finally:
                    release.set()
                    for contender in pending:
                        if not contender.done():
                            contender.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
        _assert_race_expiry_acknowledged(h, delivered)
        if not commit_before_deadline:
            await _assert_expired_creation_absent(h, source_id, admission_id, before)
            return
        assert await _admission_status(h, admission_id) == "consumed"
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT count(*) FROM public.task_revision_expirations WHERE routing_manifest_id=:source"
            ), {"source": source_id}) == 0
            assert await session.scalar(text(
                "SELECT count(*) FROM public.outbox_events WHERE event_type='TaskRevisionExpired'"
            )) == 0
            assert (await session.execute(text(
                "SELECT status,assigned_to FROM public.workstream_tasks WHERE id=:task"
            ), {"task": h.request.task_id})).one() == (
                "evaluation_pending", h.actor_context.actor_profile_id,
            )
            assert await session.scalar(text(
                "SELECT status FROM public.task_assignments WHERE id=:assignment"
            ), {"assignment": h.request.assignment_id}) == "active"
            assert await session.scalar(text(
                "SELECT count(*) FROM public.submissions WHERE task_id=:task AND version=2"
            ), {"task": h.request.task_id}) == 1
            assert await session.scalar(text(
                "SELECT public.submission_dispatch_valid(d) FROM public.submission_dispatches d "
                "WHERE d.submission_id=:submission"
            ), {"submission": final.json()["submission_id"]}) is True
            assert await session.scalar(text(
                "SELECT to_jsonb(s)-ARRAY['attempt_status','status_reason','decided_at','updated_at'] "
                "FROM public.submissions s WHERE id=:submission"
            ), {"submission": h.created.submission_id}) == before[0][0]
            await no_economic_effects(session)


async def test_expired_notice_retries_after_unknown_ack_without_new_effect(
    tmp_path, isolated_database_env, monkeypatch,
):
    """The outcome notice revalidates one committed receipt after a lost ACK."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id, _, _ = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
        )
        async with h.factory() as session:
            receipt = await session.scalar(select(TaskRevisionExpiration).where(
                TaskRevisionExpiration.routing_manifest_id == source_id,
            ))
            assert receipt is not None
            notice_id = receipt.outcome_event_id
        notice_handler = TransactionalTaskRevisionExpiredNoticeHandler(
            h.factory, observer=CommittedInvocationReader(h.factory),
        )
        delivery = outbox_delivery(
            h.factory, authorization_factory=outbox_dispatch_authorization,
            registry=HandlerRegistry(
                [(REVISION_EXPIRED_EVENT, 1, notice_handler)],
                replay_safe=frozenset({(REVISION_EXPIRED_EVENT, 1)}),
            ),
            options=DeliveryOptions(lease_seconds=30, handler_timeout_seconds=25,
                                    retry_base_seconds=1, retry_cap_seconds=1),
        )
        claim = await delivery.claim(notice_id, h.request.project_id, "revision-notice-ack-loss")
        assert claim is not None
        envelope = await delivery._begin_invocation(claim)
        assert envelope is not None
        assert await notice_handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        async with h.factory() as session:
            db_now = await session.scalar(select(func.clock_timestamp()))
        await asyncio.sleep(max(0, (claim.claim_expires_at - db_now).total_seconds()) + 0.2)
        recovered = await delivery.recover(notice_id, h.request.project_id)
        assert recovered is not None
        assert json.loads(recovered.outcome_json)["invocation_unknown"] is True
        assert json.loads(recovered.outcome_json)["delivery_state"] == "retryable"
        await asyncio.sleep(1.1)
        acknowledged = await delivery.deliver(
            notice_id, h.request.project_id, "revision-notice-replay",
        )
        assert acknowledged is not None
        assert json.loads(acknowledged.outcome_json)["delivery_state"] == "acknowledged"
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT count(*) FROM public.task_revision_expirations "
                "WHERE routing_manifest_id=:source"
            ), {"source": source_id}) == 1
            assert await session.scalar(text(
                "SELECT count(*) FROM public.audit_events "
                "WHERE event_type='TaskRevisionExpired' "
                "AND event_payload->'references'->>'routing_manifest_id'=:source"
            ), {"source": str(source_id)}) == 1
