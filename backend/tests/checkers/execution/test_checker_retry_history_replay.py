"""A retry receipt remains replayable after real remediation creates a later Submission."""

import pytest
from sqlalchemy import text

from app.adapters.checkers import checker_retry_service
from app.adapters.tasks import evaluation_completion_handler, task_submission_context_port
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import CheckerRetrySourceUnavailable
from app.modules.outbox.api import HandlerOutcome
from app.modules.tasks.api import TaskSubmissionContextRequest
from tests.authorization.post_submit_routing.support import provision_router
from tests.checkers.external.support import post_registry_spec
from app.modules.checkers.models import CheckerRun
from tests.checkers.execution.test_checker_retry import _command, _failed_source, _operator_for
from tests.tasks.evaluation_delivery.support import outcome
from tests.tasks.post_submit_routing.outcome_support import invoked_completion
from tests.tasks.post_submit_routing.support import revision_archive, source_values
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
from tests.post_submit_materialization_helpers import create_source_submission


async def test_retry_replays_after_real_later_submission_without_reopening_old_source(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(
        tmp_path,
        isolated_database_env,
        monkeypatch,
        post_submit_registry_spec=post_registry_spec(),
    ) as (h, delivery):
        from app.adapters.artifacts.local import LocalStorageAdapter

        selected_execution = delivery.selected
        assert selected_execution.requests == []
        selected_execution.verdict = "failed"

        operator = await _operator_for(h)
        command = _command(h, operator)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(command)

        # The replacement cause comes from the retry successor's exact selected
        # policy completion and governed route.
        delivered = await delivery.delivery.deliver(
            created.successor.event_id, h.request.project_id, "retry-remediation",
        )
        assert outcome(delivered)["delivery_state"] == "acknowledged"
        assert len(selected_execution.requests) == 1
        async with h.factory() as session:
            successor = await session.get(CheckerRun, str(created.successor.run_id))
            assert successor.status == "completed"
            assert successor.routing_recommendation == "needs_revision"
            assert successor.completion_event_id is not None
        async with h.factory.begin() as session:
            accepted = await session.execute(text(
                "UPDATE public.task_assignments SET accepted_at=clock_timestamp() "
                "WHERE id=:id AND accepted_at IS NULL"
            ), {"id": str(h.request.assignment_id)})
            assert accepted.rowcount == 1
        h.source = await source_values(h, run_id=created.successor.run_id)
        await provision_router(h.factory)
        completion = await invoked_completion(h)
        assert await evaluation_completion_handler(sessions=h.factory)(completion) is HandlerOutcome.ACKNOWLEDGE
        async with h.factory() as session:
            remediation = (await session.execute(text("""
                SELECT m.id, m.submission_id, m.routing_recommendation,
                       t.status AS task_status,
                       public.task_routing_outcome_complete(m) AS complete
                  FROM public.task_post_submit_routing_manifests m
                  JOIN public.workstream_tasks t ON t.id=m.task_id
                 WHERE m.checker_run_id=:run_id
            """), {"run_id": str(created.successor.run_id)})).one()
            assert str(remediation.submission_id) == str(h.created.submission_id)
            assert remediation.routing_recommendation == remediation.task_status == "needs_revision"
            assert remediation.complete is True

        async with h.factory.begin() as session:
            current = await task_submission_context_port(session).lock_submission_context(
                TaskSubmissionContextRequest(
                    task_id=h.request.task_id, assignment_id=h.request.assignment_id,
                    contributor_id=h.actor_context.actor_profile_id,
                    predecessor_submission_id=h.created.submission_id,
                )
            )
            assert current.revision_context is not None
            h.revision_preparation_id = current.revision_context.preparation_id
            h.revision_preparation_sha256 = current.revision_context.preparation_sha256
        metadata = SubmissionIntakeMetadata(
            task_id=h.request.task_id, assignment_id=h.request.assignment_id,
            predecessor_submission_id=h.created.submission_id,
            revision_preparation_id=current.revision_context.preparation_id,
            revision_preparation_sha256=current.revision_context.preparation_sha256,
            summary=h.creation_request.summary,
            contributor_attestation=h.creation_request.contributor_attestation,
        )
        later = await create_source_submission(
            h.factory, h.actor_context, h.store.wrapped, h.namespace, h.settings,
            metadata, revision_archive(h.data),
        )
        assert later.submission_version == 2

        async def retained_state():
            async with h.factory() as session:
                return tuple((await session.execute(text("""
                    SELECT
                      (SELECT to_jsonb(s) FROM public.submissions s WHERE s.id=:later_id),
                      (SELECT jsonb_agg(to_jsonb(d) ORDER BY d.submission_id)
                         FROM public.submission_dispatches d),
                      (SELECT jsonb_agg(to_jsonb(f) ORDER BY f.submission_id)
                         FROM public.checker_submission_fences f),
                      (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id)
                         FROM public.checker_runs r),
                      (SELECT jsonb_agg(to_jsonb(e) ORDER BY e.event_id)
                         FROM public.outbox_events e),
                      (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id)
                         FROM public.checker_retry_receipts r),
                      (SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id)
                         FROM public.audit_events a),
                      (SELECT to_jsonb(t) FROM public.workstream_tasks t WHERE t.id=:task_id)
                """), {
                    "later_id": str(later.submission_id), "task_id": str(h.request.task_id),
                })).one())

        before = await retained_state()
        assert before[0]["id"] == str(later.submission_id)
        assert before[0]["supersedes_submission_id"] == str(h.created.submission_id)
        assert next(
            row for row in before[1] if row["submission_id"] == str(later.submission_id)
        )["checker_remediation_manifest_id"] == str(remediation.id)
        assert {
            row["submission_id"]: row["current_run_id"] for row in before[2]
        }[str(h.created.submission_id)] == str(created.successor.run_id)
        assert str(later.submission_id) in {row["submission_id"] for row in before[2]}
        assert before[-1]["status"] == "evaluation_pending"
        provider_opens = len(h.store.opens)

        def forbidden_open(*args, **kwargs):
            pytest.fail("historical retry replay touched artifact bytes")

        with monkeypatch.context() as patch:
            for method in ("open", "open_source", "observe_sealed_source"):
                patch.setattr(LocalStorageAdapter, method, forbidden_open)
            async with h.factory.begin() as session:
                replay = await checker_retry_service(session, operator).retry(command)
        assert replay == created
        assert await retained_state() == before
        assert len(h.store.opens) == provider_opens

        other_key = new_record_id()
        other_operator = operator.model_copy(update={
            "request_id": other_key, "correlation_id": other_key,
        })
        with monkeypatch.context() as patch:
            for method in ("open", "open_source", "observe_sealed_source"):
                patch.setattr(LocalStorageAdapter, method, forbidden_open)
            # A new key must pass current TASK ownership; the later Submission
            # makes the old source fail the shared latest-Submission guard.
            with pytest.raises(
                CheckerRetrySourceUnavailable,
                match="checker_retry_source_unavailable",
            ):
                async with h.factory.begin() as session:
                    await checker_retry_service(session, other_operator).retry(
                        command.model_copy(update={"request_key": other_key})
                    )
        assert await retained_state() == before
        assert len(h.store.opens) == provider_opens
