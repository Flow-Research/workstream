"""Locked revision caps across real checker completion, intake, creation and SQL."""

import asyncio
import json
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import Submission
from tests.checkers.execution.support import ControlledSelectedExecution, live_executor
from tests.tasks.post_submit_routing.backfill_support import assert_backfill_matches_live
from tests.tasks.post_submit_routing.outcome_support import invoked_completion
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_dispatch.test_replacement_creation import (
    _creation_snapshot, _ready_replacement,
)
from tests.tasks.test_public_submission_intake import _client, _payload
from tests.test_submission_predecessor_custody import _fixture_revision_context


async def _retain_pre_revision_source(h, source_id):
    """Arrange an old source before preparations and expiry scheduling existed."""
    async with h.factory() as session, session.begin():
        # Run referential checks immediately so restoring a guard never races
        # deferred trigger events from the fixture's exact-row deletion.
        await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await session.execute(text("ALTER TABLE public.outbox_events DISABLE TRIGGER outbox_events_custody"))
        removed = await session.execute(text("""
            DELETE FROM public.outbox_events
            WHERE event_type='TaskRevisionExpiryRequested'
              AND idempotency_key=:key AND attempt_count=0
              AND claimed_at IS NULL AND delivery_state='pending'
            RETURNING event_id
        """), {"key": f"task.revision.expire:{source_id}"})
        assert len(removed.all()) == 1
        await session.execute(text("ALTER TABLE public.outbox_events ENABLE TRIGGER outbox_events_custody"))
        await session.execute(text("ALTER TABLE public.task_revision_preparations DISABLE TRIGGER revision_preparation_immutable"))
        await session.execute(text("DELETE FROM public.task_revision_preparations WHERE id=:id"), {"id": h.revision_preparation_id})
        await session.execute(text("ALTER TABLE public.task_revision_preparations ENABLE TRIGGER revision_preparation_immutable"))


COVERAGE_GAP = ({
    "check_id": "coverage.files", "code": "coverage.unreadable",
    "level": "coverage_incomplete", "message": "One file was not evaluated.",
    "path": "src/vendor.bin", "line": None,
},)


async def _fail_current_submission(h, *, findings=None, route=True, terminal=False):
    """Complete the actual reserved successor using controlled external work failure."""
    async with h.factory() as session, session.begin():
        reserved = await evaluation_coordinator(session).read_reserved_evaluation(
            project_id=h.request.project_id, task_id=h.request.task_id,
            submission_id=h.created.submission_id,
            request_id=h.created.evaluation_request_id,
        )
    h.request = reserved.request
    h.result = await live_executor(
        h, selected_execution=ControlledSelectedExecution(
            verdict="passed" if findings else "failed", findings=findings,
        ),
    ).evaluate_post_submission(h.request)
    async with h.factory() as session:
        run = await session.get(CheckerRun, str(h.result.attempt_id))
        assert run.routing_recommendation == "needs_revision"
        event = await session.scalar(select(OutboxEvent).where(
            OutboxEvent.event_id == run.completion_event_id,
        ))
        h.source = {"completion_event_id": event.event_id}
    h.envelope = await invoked_completion(h)
    if terminal:
        from app.adapters.tasks import task_post_submit_outcome

        async with h.factory() as session, session.begin():
            return await task_post_submit_outcome(session, h.factory).apply(
                h.envelope, current_generation=None,
            )
    if route:
        await _fixture_revision_context(h)


async def test_two_revisions_then_public_and_sql_refusal(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Initial0 and revisions1/2 commit; the final failure closes without a window."""
    from app.modules.tasks.schemas import AdmissionBackedSubmissionResponse
    from app.modules.tasks.revision.models import TaskRevisionPreparation

    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        async with h.factory() as session:
            first_window = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            previous_start = first_window.requested_at
            window_length = first_window.deadline_at - previous_start
            assert await session.scalar(text(
                "SELECT p.max_revision_rounds FROM public.revision_policies p "
                "JOIN public.workstream_tasks t ON t.locked_revision_policy_id=p.id "
                "WHERE t.id=:id"
            ), {"id": h.request.task_id}) == 2
        initial_id = h.created.submission_id
        saved_payload = None
        async with _client(h, monkeypatch, isolated_database_env) as client:
            route = f"/api/v1/tasks/{h.request.task_id}/submissions"
            for round_number in (1, 2):
                h.data = revision_archive(h.data)
                prepared, admission = await _ready_replacement(h, h.data)
                payload = _payload(prepared, admission)
                response = await client.post(route, json=payload)
                assert response.status_code == 201, response.text
                assert response.json()["submission_version"] == round_number + 1
                h.created = AdmissionBackedSubmissionResponse.model_validate(response.json())
                saved_payload = payload
                saved_response = response.json()
                outcome = await _fail_current_submission(h, terminal=round_number == 2)
                async with h.factory() as session:
                    if round_number == 1:
                        window = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
                        assert window.requested_at > previous_start
                        assert window.deadline_at - window.requested_at == window_length
                        assert window.next_revision_round == 2
                        previous_start = window.requested_at
                    else:
                        from tests.tasks.submission_dispatch.test_revision_exhaustion import terminal_facts

                        receipt = await terminal_facts(h, outcome, expected_round=2)
                        assert receipt.source_submission_id == str(h.created.submission_id)

            before = await _creation_snapshot(h)
            # The exhausted assignment cannot submit a new ZIP, including with
            # its preceding preparation acknowledgement. No pending window exists.
            denied = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submission-bundle-preparations",
                headers={
                    "Content-Type": "application/zip",
                    "X-Task-Assignment-Id": str(h.request.assignment_id),
                    "X-Predecessor-Submission-Id": str(h.created.submission_id),
                    "Idempotency-Key": str(new_record_id()),
                    "X-Revision-Preparation-Id": str(h.revision_preparation_id),
                    "X-Revision-Preparation-Sha256": h.revision_preparation_sha256,
                }, content=b"not a zip",
            )
            assert denied.status_code == 409, denied.text
            assert denied.json()["error"]["code"] == "conflict"
            assert denied.json()["error"]["message"] == "Request conflict"
            assert denied.json()["detail"] == "submission_bundle_preparation_context_changed"
            assert await _creation_snapshot(h) == before
            replay = await client.post(route, json=saved_payload)
            assert replay.status_code == 201, replay.text
            assert replay.json() == saved_response

        async with h.factory() as session:
            original = await session.scalar(text(
                "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id})
        # Intake now rejects excess rounds at the database boundary too. A raw
        # INSERT cannot bypass the cap even before an admission is selected.
        # A forged successor is a new, undecided attempt.
        fresh = dict(attempt_status="evaluation_pending", status_reason=None, decided_at=None)
        forbidden = dict(original, id=str(new_record_id()), version=4,
                         supersedes_submission_id=str(h.created.submission_id), **fresh)
        with pytest.raises(IntegrityError, match="revision_limit_reached"):
            async with h.factory() as session, session.begin():
                await session.execute(text(
                    "INSERT INTO public.submissions SELECT * FROM "
                    "jsonb_populate_record(NULL::public.submissions, CAST(:row AS jsonb))"
                ), {"row": json.dumps(forbidden)})
        assert await _creation_snapshot(h) == before
        for version in (0, -1):
            forged = dict(original, id=str(new_record_id()), version=version,
                          supersedes_submission_id=str(h.created.submission_id),
                          submission_bundle_admission_id=None, artifact_binding_id=None,
                          artifact_content_id=None, **fresh)
            with pytest.raises(IntegrityError, match="submission_revision_lineage_invalid"):
                async with h.factory() as session, session.begin():
                    await session.execute(text(
                        "INSERT INTO public.submissions SELECT * FROM "
                        "jsonb_populate_record(NULL::public.submissions, CAST(:row AS jsonb))"
                    ), {"row": json.dumps(forged)})
        async with h.factory() as session:
            rows = (await session.scalars(select(Submission).order_by(Submission.version))).all()
            assert [row.version for row in rows] == [1, 2, 3]
            assert rows[0].id == str(initial_id)
            assert rows[1].supersedes_submission_id == rows[0].id
            assert rows[2].supersedes_submission_id == rows[1].id


async def test_coverage_return_spends_no_round_under_a_zero_revision_policy(
    tmp_path, isolated_database_env, monkeypatch,
):
    """With no revisions allowed, a coverage return v1 still returns the work.

    It neither exhausts nor spends round zero, so v2 is the initial attempt and
    its genuine failure exhausts the assignment immediately. Counting the
    coverage return would make v2 a round beyond the policy instead.
    """
    from app.modules.tasks.schemas import AdmissionBackedSubmissionResponse
    from app.modules.tasks.revision.models import TaskRevisionPreparation
    from tests.tasks.submission_dispatch.test_revision_exhaustion import terminal_facts

    async with remediation_source(
        tmp_path, isolated_database_env, human_review_required=False, findings=COVERAGE_GAP,
        max_revision_rounds=0,
    ) as h:
        await _fixture_revision_context(h)
        async with h.factory() as session:
            first = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            assert (first.next_revision_round, first.max_revision_rounds) == (0, 0)
            assert first.deadline_at is not None and first.outcome != "blocked"
        route = f"/api/v1/tasks/{h.request.task_id}/submissions"
        async with _client(h, monkeypatch, isolated_database_env) as client:
            h.data = revision_archive(h.data)
            prepared, admission = await _ready_replacement(h, h.data)
            payload = _payload(prepared, admission)
            response = await client.post(route, json=payload)
            assert response.status_code == 201, response.text
            assert response.json()["submission_version"] == 2
            h.created = AdmissionBackedSubmissionResponse.model_validate(response.json())
            outcome = await _fail_current_submission(h, terminal=True)
            receipt = await terminal_facts(h, outcome, expected_round=0)
            async with h.factory() as session:
                assert (await session.execute(text(
                    "SELECT array_agg(attempt_status ORDER BY version), "
                    "array_agg(coalesce(status_reason, '-') ORDER BY version), "
                    "array_agg(decided_at ORDER BY version) FROM public.submissions"
                ))).one() == (
                    ["needs_revision", "rejected"],
                    ["checker_coverage_incomplete", "revision_limit_reached"],
                    [first.requested_at, receipt.exhausted_at],
                )
            replay = await client.post(route, json=payload)
            assert replay.status_code == 201, replay.text
            assert replay.json() == response.json()
        await assert_backfill_matches_live(h.factory)


def test_revision_projection_preserves_deadline_and_distinguishes_policy_changes():
    """JSON recovery preserves exact UUIDs, deadlines and bounded contributor changes."""
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from app.modules.tasks.api.revision import RevisionCandidate, RevisionContextSnapshot
    from app.modules.tasks.api.transition_audit import TaskPolicyLineage
    from app.modules.tasks.revision.service import project_revision

    start = datetime(2026, 10, 14, tzinfo=UTC)
    fields = {
        name: new_record_id() if name.endswith("_id") else
        1 if name.endswith("_generation") else
        "sha256:" + "a" * 64 if name.endswith(("_hash", "_bundle_hash")) else "v1"
        for name in TaskPolicyLineage.model_fields
    }
    prior = RevisionContextSnapshot(
        guide_id=new_record_id(), activation_operation_id=new_record_id(),
        activation_generation=1, activated_at=start - timedelta(days=1),
        lineage=TaskPolicyLineage(**fields),
    )
    candidate = RevisionCandidate(
        prior=prior, target=prior, target_post_policy_json="{}",
        max_revision_rounds=2, target_max_revision_rounds=2, revision_deadline_hours=24,
    )
    row = SimpleNamespace(
        id=new_record_id(), preparation_sha256="sha256:" + "b" * 64,
        predecessor_id=None, submission_id=str(new_record_id()), routing_manifest_id=new_record_id(),
        sequence=1, next_revision_round=1, max_revision_rounds=2, requested_at=start,
        deadline_at=start + timedelta(hours=24), outcome="kept", blocked_reason=None,
        packet={"candidate": candidate.model_dump(mode="json")},
    )
    first = project_revision(row, row.deadline_at - timedelta(microseconds=1))
    assert first.disposition == "ready" and first.changes == ()
    assert first.direction == "kept"
    boundary = project_revision(row, row.deadline_at)
    assert boundary.disposition == "revision_deadline_expired"
    assert boundary.requested_at == first.requested_at and boundary.deadline_at == first.deadline_at
    assert "target_post_policy_json" not in boundary.model_dump_json()

    target = prior.model_copy(update={
        "activation_operation_id": new_record_id(), "activation_generation": 2,
        "activated_at": start,
        "lineage": prior.lineage.model_copy(update={"locked_contribution_policy_version_id": new_record_id()}),
    })
    row.packet = {"candidate": candidate.model_copy(update={"target": target}).model_dump(mode="json")}
    row.outcome = "rebased"
    row.predecessor_id, row.id = row.id, new_record_id()
    row.sequence = 2
    repaired = project_revision(row, start + timedelta(hours=23))
    assert repaired.deadline_at == first.deadline_at
    assert repaired.direction == "forward"
    assert [change.component for change in repaired.changes] == ["guide", "contribution"]
    assert repaired.prior == prior and repaired.target == target
    row.blocked_reason = "revision_limit_reached"
    row.next_revision_round = 3
    row.outcome = "blocked"
    assert project_revision(row, row.deadline_at).disposition == "revision_limit_reached"


async def test_rebase_keeps_history_and_requires_exact_acknowledgement(
    tmp_path, isolated_database_env, monkeypatch,
):
    """A real v2 activation rebases only the next attempt and preserves v1 evidence."""
    from app.modules.tasks.models import WorkstreamTask, TaskAssignment
    from app.modules.tasks.revision.models import TaskRevisionPreparation
    from tests.tasks.post_submit_routing.support import activate_successor_guide

    async with remediation_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            original = await session.scalar(text(
                "SELECT to_jsonb(s)-ARRAY['attempt_status','status_reason','decided_at','updated_at'] FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id})
            retained_run = await session.scalar(text(
                "SELECT to_jsonb(r) FROM public.checker_runs r WHERE id=:id"
            ), {"id": h.result.attempt_id})
        await activate_successor_guide(h)
        source_id = await _fixture_revision_context(h)
        async with h.factory() as session:
            preparation = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            assert preparation.outcome == "rebased"
            assert preparation.next_revision_round == 1
            task = await session.get(WorkstreamTask, str(h.request.task_id))
            assignment = await session.get(TaskAssignment, str(h.request.assignment_id))
            assert task.locked_guide_version == "v2"
            assert str(task.locked_contribution_policy_version_id) == str(assignment.submitter_contribution_policy_version_id)
            packet = preparation.packet
            assert packet["candidate"]["prior"]["lineage"]["locked_guide_version"] != "v2"
            assert packet["candidate"]["target"]["lineage"]["locked_guide_version"] == "v2"
            frozen = (preparation.id, preparation.preparation_sha256, preparation.requested_at, preparation.deadline_at)
        # Exact worker redelivery never selects a fresh preparation or window.
        assert await _fixture_revision_context(h) == source_id
        async with h.factory() as session:
            rows = (await session.scalars(select(TaskRevisionPreparation))).all()
            assert len(rows) == 1
            assert (rows[0].id, rows[0].preparation_sha256, rows[0].requested_at, rows[0].deadline_at) == frozen
        async with _client(h, monkeypatch, isolated_database_env) as client:
            context = await client.get(f"/api/v1/tasks/{h.request.task_id}/work-context")
            assert context.status_code == 200, context.text
            view = context.json()["revision_context"]
            assert view["preparation_id"] == str(h.revision_preparation_id)
            assert view["outcome"] == "rebased" and view["disposition"] == "ready"
            assert "contribution" in {change["component"] for change in view["changes"]}
            replayed_initial = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submissions",
                json=_payload(h.creation_request, h.creation_request.admission_id),
            )
            assert replayed_initial.status_code == 201, replayed_initial.text
            assert replayed_initial.json()["submission_id"] == str(h.created.submission_id)
            assert replayed_initial.json()["submission_version"] == 1
            before = await _creation_snapshot(h)
            refused = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submission-bundle-preparations",
                headers={
                    "Content-Type": "application/zip",
                    "X-Task-Assignment-Id": str(h.request.assignment_id),
                    "X-Predecessor-Submission-Id": str(h.created.submission_id),
                    "X-Revision-Preparation-Id": str(new_record_id()),
                    "X-Revision-Preparation-Sha256": h.revision_preparation_sha256,
                    "Idempotency-Key": str(new_record_id()),
                }, content=b"not a zip",
            )
            assert refused.status_code == 409, refused.text
            assert refused.json()["error"]["code"] == "revision_context_changed"
            assert await _creation_snapshot(h) == before
            prepared, admission = await _ready_replacement(h, revision_archive(h.data))
            created = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submissions", json=_payload(prepared, admission),
            )
            assert created.status_code == 201, created.text
            assert created.json()["submission_version"] == 2
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT to_jsonb(s)-ARRAY['attempt_status','status_reason','decided_at','updated_at'] FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id}) == original
            assert await session.scalar(text(
                "SELECT to_jsonb(r) FROM public.checker_runs r WHERE id=:id"
            ), {"id": h.result.attempt_id}) == retained_run
            assert await session.scalar(text(
                "SELECT bool_and(public.submission_dispatch_valid(d)) FROM public.submission_dispatches d"
            )) is True
        for mutation in (
            "UPDATE public.task_revision_preparations SET deadline_at=deadline_at+interval '1 hour' WHERE id=:id",
            "DELETE FROM public.task_revision_preparations WHERE id=:id",
        ):
            with pytest.raises(DBAPIError, match="immutable"):
                async with h.factory() as session, session.begin():
                    await session.execute(text(mutation), {"id": h.revision_preparation_id})


async def test_pm_recovers_retained_source_and_repairs_without_resetting_window(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Explicit PM recovery and later rebase keep the original failure's window."""
    from app.modules.tasks.revision.models import TaskRevisionPreparation
    from tests.tasks.post_submit_routing.support import activate_successor_guide

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        async with h.factory() as session:
            original = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            anchor, deadline, limit = original.requested_at, original.deadline_at, original.max_revision_rounds
        # Arrange only the retained pre-preparation schema state in this owned
        # test database. The real source, authority, Task and evidence stay intact.
        # The protection itself is tested above; recovery runs with it enabled.
        await _retain_pre_revision_source(h, source_id)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            route = f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair"
            root_payload = {"routing_manifest_id": str(source_id), "reason": "Recover the retained revision source"}
            root_key = str(new_record_id())
            response = await client.post(route, json=root_payload, headers={"Idempotency-Key": root_key})
            assert response.status_code == 200, response.text
            root = response.json()
            assert root["sequence"] == 1 and root["outcome"] == "kept"
            assert root["source_routing_manifest_id"] == str(source_id)
            async with h.factory() as session:
                restored = await session.get(TaskRevisionPreparation, UUID(root["preparation_id"]))
                assert (restored.requested_at, restored.deadline_at, restored.max_revision_rounds) == (anchor, deadline, limit)
                assert restored.repair_actor_id == h.actor_context.actor_profile_id
            replay = await client.post(route, json=root_payload, headers={"Idempotency-Key": root_key})
            assert replay.status_code == 200, replay.text
            assert replay.json() == root
            await activate_successor_guide(h)
            child_payload = {
                "parent_preparation_id": root["preparation_id"],
                "parent_preparation_sha256": root["preparation_sha256"],
                "reason": "Adopt the complete corrected active guide",
            }
            child_key = str(new_record_id())
            repaired = await client.post(route, json=child_payload, headers={"Idempotency-Key": child_key})
            assert repaired.status_code == 200, repaired.text
            child = repaired.json()
            assert child["sequence"] == 2 and child["outcome"] == "rebased"
            assert child["requested_at"] == root["requested_at"]
            assert child["deadline_at"] == root["deadline_at"]
            assert child["max_revision_rounds"] == root["max_revision_rounds"]
            stale = await client.post(route, json=child_payload, headers={"Idempotency-Key": str(new_record_id())})
            assert stale.status_code == 409, stale.text
            h.revision_preparation_id = UUID(child["preparation_id"])
            h.revision_preparation_sha256 = child["preparation_sha256"]
            prepared, admission = await _ready_replacement(h, revision_archive(h.data))
            created = await client.post(f"/api/v1/tasks/{h.request.task_id}/submissions", json=_payload(prepared, admission))
            assert created.status_code == 201, created.text
            replay = await client.post(route, json=child_payload, headers={"Idempotency-Key": child_key})
            assert replay.status_code == 200, replay.text
            assert replay.json()["preparation_id"] == child["preparation_id"]
            assert replay.json()["deadline_at"] == root["deadline_at"]
            assert replay.json()["disposition"] == "context_blocked"
        async with h.factory() as session:
            rows = (await session.scalars(select(TaskRevisionPreparation).order_by(TaskRevisionPreparation.sequence))).all()
            assert len(rows) == 2
            assert rows[1].predecessor_id == rows[0].id
            assert rows[0].packet["candidate"]["target"]["lineage"]["locked_guide_version"] != "v2"


async def test_pm_repair_refuses_superseded_checker_source(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Both repair forms conceal stale eligibility behind fresh PM authority."""
    from tests.tasks.post_submit_routing.support import next_request

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        successor = await next_request(h)
        async with h.factory() as session, session.begin():
            await evaluation_coordinator(session).reserve_current_evaluation(successor)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            route = f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair"
            payloads = (
                {"parent_preparation_id": str(h.revision_preparation_id),
                 "parent_preparation_sha256": h.revision_preparation_sha256,
                 "reason": "Try to repair a superseded result"},
                {"routing_manifest_id": str(source_id),
                 "reason": "Try to recover a superseded result"},
            )
            for index, payload in enumerate(payloads):
                if index:
                    # Represent a retained source without a preparation. Only
                    # fixture setup bypasses immutability; the request does not.
                    await _retain_pre_revision_source(h, source_id)
                async with h.factory() as session:
                    before = (await session.execute(text(
                        "SELECT (SELECT count(*) FROM public.task_revision_preparations), "
                        "(SELECT count(*) FROM public.audit_events)"
                    ))).one()
                response = await client.post(route, json=payload, headers={"Idempotency-Key": str(new_record_id())})
                assert response.status_code == 409, response.text
                assert response.json()["error"]["code"] == "revision_context_changed"
                async with h.factory() as session:
                    assert (await session.execute(text(
                        "SELECT (SELECT count(*) FROM public.task_revision_preparations), "
                        "(SELECT count(*) FROM public.audit_events)"
                    ))).one() == before


async def test_expired_retained_failure_recovers_without_a_new_window(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Database time blocks intake before the expiry worker delivers rejection."""
    from app.modules.tasks.revision.models import TaskRevisionPreparation

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        # Model a retained source from before preparations existed, already past
        # its policy deadline. Restore every guard before exercising public APIs.
        await _retain_pre_revision_source(h, source_id)
        async with h.factory() as session, session.begin():
            await session.execute(text("ALTER TABLE public.task_post_submit_routing_manifests DISABLE TRIGGER task_routing_manifest_immutable"))
            anchor, deadline = (await session.execute(text("""
                UPDATE public.task_post_submit_routing_manifests m
                SET created_at=clock_timestamp()-make_interval(hours => p.revision_deadline_hours+1)
                FROM public.submissions s JOIN public.revision_policies p ON p.id=s.locked_revision_policy_id
                WHERE m.id=:id AND s.id=m.submission_id
                RETURNING m.created_at, m.created_at+make_interval(hours => p.revision_deadline_hours)
            """), {"id": source_id})).one()
            await session.execute(text("ALTER TABLE public.task_post_submit_routing_manifests ENABLE TRIGGER task_routing_manifest_immutable"))
            assert await session.scalar(text(
                "SELECT public.task_routing_outcome_complete(m) FROM public.task_post_submit_routing_manifests m WHERE id=:id"
            ), {"id": source_id}) is True
        async with _client(h, monkeypatch, isolated_database_env) as client:
            route = f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair"
            payload = {"routing_manifest_id": str(source_id), "reason": "Recover an expired retained failure"}
            headers = {"Idempotency-Key": str(new_record_id())}
            response = await client.post(route, json=payload, headers=headers)
            assert response.status_code == 200, response.text
            receipt = response.json()
            assert receipt["outcome"] == "blocked"
            assert receipt["disposition"] == "revision_deadline_expired"
            async with h.factory() as session:
                row = await session.get(TaskRevisionPreparation, UUID(receipt["preparation_id"]))
                assert (row.requested_at, row.deadline_at) == (anchor, deadline)
            replay = await client.post(route, json=payload, headers=headers)
            assert replay.status_code == 200 and replay.json() == receipt
            before = await _creation_snapshot(h)
            denied = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submission-bundle-preparations",
                headers={
                    "Content-Type": "application/zip",
                    "X-Task-Assignment-Id": str(h.request.assignment_id),
                    "X-Predecessor-Submission-Id": str(h.created.submission_id),
                    "Idempotency-Key": str(new_record_id()),
                    "X-Revision-Preparation-Id": receipt["preparation_id"],
                    "X-Revision-Preparation-Sha256": receipt["preparation_sha256"],
                }, content=b"not a zip",
            )
            assert denied.status_code == 409, denied.text
            assert denied.json()["error"]["code"] == "revision_deadline_expired"
            assert await _creation_snapshot(h) == before
            async with h.factory() as session:
                assert await session.scalar(text("SELECT status FROM public.workstream_tasks WHERE id=:id"), {"id": h.request.task_id}) == "needs_revision"


async def _replay_old_expiry_after_new_failure(h, *, source_id, event_id, new_assignment_id):
    """A lost ACK for the old release cannot affect the new assignment's window."""
    from app.modules.tasks.revision.models import TaskRevisionExpiration, TaskRevisionPreparation

    async with h.factory() as session:
        new_window = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
        frozen = (
            new_window.id, new_window.preparation_sha256,
            new_window.requested_at, new_window.deadline_at,
        )
        before_receipts = await session.scalar(select(func.count(TaskRevisionExpiration.id)).where(
            TaskRevisionExpiration.routing_manifest_id == source_id,
        ))
        assert before_receipts == 1
        db_now = await session.scalar(select(func.clock_timestamp()))
    remaining = (h.expiry_claim_expires_at - db_now).total_seconds()
    await asyncio.sleep(max(0, remaining) + 0.2)
    recovered = await h.expiry_delivery.recover(event_id, h.request.project_id)
    assert recovered is not None
    assert json.loads(recovered.outcome_json)["invocation_unknown"] is True
    async with h.factory() as session:
        event = await session.get(OutboxEvent, str(event_id))
        db_now = await session.scalar(select(func.clock_timestamp()))
        retry_delay = (event.next_attempt_at - db_now).total_seconds()
    await asyncio.sleep(max(0, retry_delay) + 0.2)
    redelivered = await h.expiry_delivery.deliver(
        event_id, h.request.project_id, "old-expiry-after-new-claim",
    )
    assert redelivered is not None
    assert json.loads(redelivered.outcome_json)["delivery_state"] == "acknowledged"
    async with h.factory() as session:
        window = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
        assert (window.id, window.preparation_sha256, window.requested_at, window.deadline_at) == frozen
        assert await session.scalar(text(
            "SELECT status FROM public.workstream_tasks WHERE id=:id"
        ), {"id": h.request.task_id}) == "needs_revision"
        assert (await session.execute(text(
            "SELECT status,released_at FROM public.task_assignments WHERE id=:id"
        ), {"id": new_assignment_id})).one() == ("active", None)
        assert await session.scalar(select(func.count(TaskRevisionExpiration.id)).where(
            TaskRevisionExpiration.routing_manifest_id == source_id,
        )) == 1


async def test_expiry_allows_new_assignment_initial_at_next_global_version(
    tmp_path, isolated_database_env, monkeypatch,
):
    """The same eligible contributor can claim again with a fresh round zero."""
    from app.modules.artifacts.api import SubmissionBundlePreparationRequest
    from app.modules.authorization.api import ActorIdentityFacts, ActorKind
    from app.modules.tasks.revision.models import TaskRevisionPreparation
    from app.modules.tasks.schemas import AdmissionBackedSubmissionResponse
    from tests.archive_fixtures import byte_source
    from tests.tasks.submission_dispatch.test_revision_expiry import expire_retained_revision
    from tests.tasks.submission_lineage_support import _verified_admission

    async with remediation_source(tmp_path, isolated_database_env) as h:
        old_submission_id = h.created.submission_id
        old_assignment_id = h.request.assignment_id
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT public.task_revision_expired_assignment_current(:assignment_id,:submission_id)"
            ), {
                "assignment_id": old_assignment_id,
                "submission_id": old_submission_id,
            }) is False
        old_source_id, old_revision, old_event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
            ack_lost=True,
        )
        async with _client(h, monkeypatch, isolated_database_env) as client:
            claim = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/claim",
                headers={"Idempotency-Key": str(new_record_id())},
            )
            assert claim.status_code == 200, claim.text
            new_assignment_id = UUID(claim.json()["assignment"]["id"])
            assert new_assignment_id != old_assignment_id
            assert claim.json()["task"]["status"] == "in_progress"

            preparation = SubmissionBundlePreparationRequest(
                actor=ActorIdentityFacts(
                    h.actor_context.actor_profile_id,
                    h.actor_context.identity_link_id,
                    ActorKind.HUMAN,
                ),
                request_id=new_record_id(), correlation_id=new_record_id(),
                task_id=h.request.task_id, assignment_id=new_assignment_id,
                predecessor_submission_id=None, idempotency_key=new_record_id(),
                summary=h.creation_request.summary,
                contributor_attestation=h.creation_request.contributor_attestation,
                media_type="application/zip", byte_source=byte_source(h.data),
            )
            admission_id = await _verified_admission(
                h.factory, h.store, h.namespace, h.settings,
                h.actor_context, preparation,
            )
            route = f"/api/v1/tasks/{h.request.task_id}/submissions"
            created = await client.post(route, json=_payload(preparation, admission_id))
            assert created.status_code == 201, created.text
            assert created.json()["submission_version"] == 2
            replay = await client.post(route, json=_payload(preparation, admission_id))
            assert replay.status_code == 201 and replay.json() == created.json()

        async with h.factory() as session:
            submissions = (await session.scalars(select(Submission).where(
                Submission.task_id == str(h.request.task_id),
            ).order_by(Submission.version))).all()
            assert [(row.version, row.task_assignment_id, row.supersedes_submission_id)
                    for row in submissions] == [
                (1, str(old_assignment_id), None),
                (2, str(new_assignment_id), None),
            ]
            assert submissions[0].id == str(old_submission_id)
            assert submissions[1].id == created.json()["submission_id"]
            assert await session.scalar(text(
                "SELECT public.submission_dispatch_valid(d) FROM public.submission_dispatches d "
                "WHERE d.submission_id=:id"
            ), {"id": submissions[1].id}) is True

        h.created = AdmissionBackedSubmissionResponse.model_validate(created.json())
        await _fail_current_submission(h)
        async with h.factory() as session:
            fresh = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            old = await session.get(
                TaskRevisionPreparation, UUID(old_revision["preparation_id"]),
            )
            assert fresh.assignment_id == str(new_assignment_id)
            assert fresh.source_submission_version == 2
            assert fresh.next_revision_round == 1
            assert fresh.max_revision_rounds == old.max_revision_rounds == 2
            assert fresh.requested_at > old.deadline_at
        await _replay_old_expiry_after_new_failure(
            h, source_id=old_source_id, event_id=old_event_id,
            new_assignment_id=new_assignment_id,
        )
