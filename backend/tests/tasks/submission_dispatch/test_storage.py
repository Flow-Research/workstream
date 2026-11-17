"""Independent SQL checks bind all receipt members and freeze their retained parents."""

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, DBAPIError

from app.core.identifiers import new_record_id
from tests.post_submit_materialization_helpers import material_fixture


async def test_sql_validator_rejects_independently_substituted_dispatch_members(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path / "first", isolated_database_env) as h:
        async with material_fixture(tmp_path / "foreign", isolated_database_env,
                                    provision_services=False, storage_settings=h.settings) as foreign:
            async with h.factory() as session:
                query = text("SELECT to_jsonb(d) FROM public.submission_dispatches d WHERE submission_id=:id")
                first = await session.scalar(query, {"id": h.created.submission_id})
                other = await session.scalar(query, {"id": foreign.created.submission_id})
                validate = text("SELECT public.submission_dispatch_valid(pg_catalog.jsonb_populate_record(NULL::public.submission_dispatches, CAST(:body AS jsonb)))")
                assert await session.scalar(validate, {"body": json.dumps(first)}) is True
                # Valid foreign persisted members, not nonexistent selectors.
                for key in (
                    "project_id", "task_id", "assignment_id", "contributor_id", "admission_id",
                    "artifact_binding_id", "artifact_content_id", "creation_decision_id", "binding_decision_id",
                    "evaluation_request_id", "evaluation_request_digest", "evaluation_attempt_id",
                    "evaluation_result_id", "evaluation_event_id",
                ):
                    assert first[key] != other[key], key
                    assert await session.scalar(validate, {"body": json.dumps(first | {key: other[key]})}) is False, key
                for key in ("creation_decision_id", "binding_decision_id", "evaluation_event_id"):
                    assert await session.scalar(validate, {"body": json.dumps(first | {key: None})}) is False, key


async def test_dispatch_and_bound_submission_remain_immutable(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        cases = (
            ("UPDATE public.submission_dispatches SET evaluation_event_id=:replacement WHERE submission_id=:id", "submission dispatch is immutable"),
            ("DELETE FROM public.submission_dispatches WHERE submission_id=:id", "submission dispatch is immutable"),
            ("UPDATE public.submission_binding_receipts SET decision_id=:replacement WHERE admission_id=:admission", "submission binding receipt is immutable"),
            ("DELETE FROM public.submission_binding_receipts WHERE admission_id=:admission", "submission binding receipt is immutable"),
            ("UPDATE public.submissions SET summary='Changed retained packet' WHERE id=:id", "immutable"),
            ("UPDATE public.submissions SET contribution_policy_version_id=:replacement WHERE id=:id", "submission contribution identity is immutable"),
            ("UPDATE public.submissions SET locked_at=clock_timestamp() WHERE id=:id", "immutable"),
        )
        for statement, message in cases:
            async with h.factory() as session:
                with pytest.raises(DBAPIError, match=message):
                    async with session.begin():
                        await session.execute(text(statement), {"id": h.created.submission_id,
                            "admission": h.created.admission_id, "replacement": new_record_id()})
        async with h.factory() as session:
            assert await session.scalar(text("SELECT public.submission_dispatch_valid(d) FROM public.submission_dispatches d WHERE submission_id=:id"), {"id": h.created.submission_id}) is True


async def test_unrelated_allow_cannot_substitute_for_acceptance_allow_at_commit(tmp_path, isolated_database_env, monkeypatch):
    """T4 rejects a real unrelated allow and leaves no accepted handoff or T5 writes."""
    from uuid import UUID
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.modules.authorization.submission_intake import SubmissionIntakeAuthorization
    from app.modules.artifacts.intake.repository import IntakeCustodyConflict
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from app.modules.artifacts.models import SubmissionBundleAdmission, SubmissionBindingReceipt
    from app.modules.checkers.models import CheckerRun
    from app.modules.outbox.models import OutboxEvent
    from app.modules.tasks.models import AuditEvent, Submission, SubmissionDispatch, WorkstreamTask

    original = SubmissionIntakeAuthorization.consume_acceptance
    substituted = []

    async def wrong_receipt(self, handle, facts):
        real = await original(self, handle, facts)
        unrelated = await self._session.scalar(select(AuditEvent.id).where(
            AuditEvent.event_domain == "authority", AuditEvent.event_type == "SensitiveAuthorizationAllowed",
            AuditEvent.action_id.not_in(("submission.create", "artifact.submission.binding.create")),
        ).order_by(AuditEvent.id).limit(1))
        assert unrelated is not None and unrelated != str(real)
        substituted.append((real, UUID(unrelated)))
        return UUID(unrelated)

    monkeypatch.setattr(SubmissionIntakeAuthorization, "consume_acceptance", wrong_receipt)
    # The complete accepted receipt and event use the unrelated existing allow.
    # No selector is nonexistent; only the authority provenance is wrong.
    with pytest.raises(IntakeCustodyConflict, match="intake_acceptance_conflict") as denied:
        async with material_fixture(tmp_path, isolated_database_env):
            pytest.fail("an unrelated allow was accepted as submission authority")
    assert len(substituted) == 1
    assert isinstance(denied.value.__cause__, IntegrityError)
    assert "accepted authority mismatch" in str(denied.value.__cause__)
    engine = create_async_engine(isolated_database_env)
    try:
        async with async_sessionmaker(engine)() as session:
            operation = (await session.execute(select(SubmissionIntakeOperation))).scalar_one()
            assert operation.state == "failed"
            assert operation.acceptance_decision_id is None
            assert operation.acceptance_receipt is None
            assert operation.finalization_event_id is None
            charge = await session.get(SubmissionSourceCharge, operation.id)
            assert charge.state == "sealed" and charge.accounted_bytes > 0
            task = await session.get(WorkstreamTask, operation.task_id)
            assert task.status == "in_progress" and task.active_submission_operation_id is None
            for model in (Submission, SubmissionDispatch, SubmissionBundleAdmission,
                          SubmissionBindingReceipt, CheckerRun, OutboxEvent):
                assert await session.scalar(select(func.count()).select_from(model)) == 0
            assert await session.get(AuditEvent, str(substituted[0][0])) is None
            assert await session.get(AuditEvent, str(substituted[0][1])) is not None
    finally:
        await engine.dispose()
