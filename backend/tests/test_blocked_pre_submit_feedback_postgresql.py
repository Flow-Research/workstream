"""Real blocked preparation feedback, replay, and no-product-effect proof."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.adapters.artifacts import CheckerPhaseService
from app.adapters.checkers import submission_evaluation_content
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.artifacts.api import SubmissionBundlePreparationCheckFailed
from app.modules.artifacts.authorization import (
    PreparedPreSubmitMaterializationAuthorization,
)
from app.modules.artifacts.models import (
    PreSubmitEvidenceResult,
    PreSubmitEvidenceSet,
    PreSubmitExecutionAttempt,
)
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand,
    SubmissionBundlePreparationRuntime,
)
from app.modules.checkers.api.execution import REQUEST_EVENT
from app.modules.outbox.api import OutboxAppendDisposition, OutboxAppendInput
from app.modules.outbox.service import OutboxService
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.tasks.repository import TaskRepository
from tests.authorization.test_pre_submit_attempt_authority import _seed_materializer
from tests.checkers.execution.support import forbidden_post_submission
from tests.test_default_pre_submit_execution import _archive, _bytes
from tests.test_pre_submit_attempt_recovery import _harness


async def _authorized_harness(tmp_path: Path, database_url: str):
    harness = await _harness(tmp_path, database_url)
    await harness.request.prepared_artifact.close()
    await _seed_materializer(harness.factory)
    return harness


async def _product_state(harness) -> dict[str, object]:
    async with harness.factory() as session:
        values = (
            await session.execute(
                text(
                    "select "
                    "(select status from workstream_tasks where id=:task) as task_status,"
                    "(select count(*) from submissions) as submissions,"
                    "(select max(version) from submissions) as max_version,"
                    "(select count(*) from submission_bundle_admissions) as admissions,"
                    "(select count(*) from submission_bundle_admissions "
                    " where status='ready') as ready_admissions,"
                    "(select count(*) from checker_runs) as checker_runs,"
                    "(select count(*) from audit_events "
                    " where event_domain<>'authority') as lifecycle_audit_events,"
                    "(select count(*) from outbox_events) as outbox_events"
                ),
                {"task": str(harness.request.task_id)},
            )
        ).mappings().one()
        await session.rollback()
        return dict(values)


def _assert_no_product_effects(
    actual: dict[str, object], expected: dict[str, object]
) -> None:
    for field, expected_value in expected.items():
        assert actual[field] == expected_value, f"{field} changed"
    assert set(actual) == set(expected)


async def _evidence_state(harness):
    async with harness.factory() as session:
        attempt = await session.scalar(
            select(PreSubmitExecutionAttempt).where(
                PreSubmitExecutionAttempt.task_id == str(harness.request.task_id)
            )
        )
        assert attempt is not None and attempt.status == "completed"
        evidence = await session.get(PreSubmitEvidenceSet, attempt.evidence_set_id)
        assert evidence is not None and evidence.eligible is False
        result_ids = tuple(
            await session.scalars(
                select(PreSubmitEvidenceResult.id)
                .where(PreSubmitEvidenceResult.evidence_set_id == evidence.id)
                .order_by(PreSubmitEvidenceResult.result_order)
            )
        )
        counts = (
            await session.scalar(select(func.count()).select_from(PreSubmitEvidenceSet)),
            await session.scalar(select(func.count()).select_from(PreSubmitEvidenceResult)),
            await session.scalar(text("select count(*) from checker_runs")),
        )
        identity = evidence.id, result_ids, counts
        await session.rollback()
        return identity


async def _invoke_blocked(harness, calls: list[int]):
    async with harness.factory() as session:
        contributor = harness.contributor_authority(session)
        materializer = PreparedPreSubmitMaterializationAuthorization(
            session,
            request_id=harness.preparation_request.request_id,
            correlation_id=harness.preparation_request.correlation_id,
        )
        workflow = harness.workflow(
            session,
            calls,
            preparation_authorization=contributor,
        )
        workflow._materialization._authorization = materializer

        @asynccontextmanager
        async def runtime():
            try:
                yield SubmissionBundlePreparationRuntime(
                    preparation=harness.preparation,
                    inspector=harness.inspector,
                    catalogue=harness.catalogue,
                    materialization=workflow._materialization,
                    evidence=workflow,
                    checker_service=CheckerPhaseService(
                        pre_submission=workflow,
                        post_submission=forbidden_post_submission(),
                    ),
                    durable_put=object(),
                    evaluation_content=submission_evaluation_content,
                )
            finally:
                materializer.close()

        command = PreparedSubmissionBundlePreparationCommand(
            session=session,
            authority=contributor,
            task_contexts=TaskRepository(session),
            project_contexts=ProjectLockedPolicyRepository(session),
            runtime_factory=runtime,
        )
        request = replace(
            harness.preparation_request,
            contributor_attestation="",
            byte_source=_bytes(_archive(evidence_path=harness.evidence_path)),
        )
        with pytest.raises(SubmissionBundlePreparationCheckFailed) as failure:
            await command.prepare(request)
        return failure.value.facts


def _submission_event(harness) -> OutboxAppendInput:
    submission_id = new_record_id()
    request_id = new_record_id()
    digest = canonical_json_hash({"submission_id": str(submission_id)})
    return OutboxAppendInput(
        event_type=REQUEST_EVENT,
        event_version=1,
        aggregate_type="submission",
        aggregate_id=submission_id,
        project_id=harness.request.effective_plan.lineage.project_id,
        correlation_id=str(request_id),
        idempotency_key=f"submission-evaluation:{submission_id}",
        payload={
            "project_id": str(harness.request.effective_plan.lineage.project_id),
            "task_id": str(harness.request.task_id),
            "submission_id": str(submission_id),
            "submission_version": 1,
            "request_id": str(request_id),
            "request_digest": digest,
            "evaluation_generation": 1,
            "attempt_id": str(new_record_id()),
            "result_id": str(new_record_id()),
            "creation_decision_id": str(new_record_id()),
            "binding_decision_id": str(new_record_id()),
        },
    )


@pytest.mark.asyncio
async def test_authorized_blocked_command_replays_exact_feedback_without_product_effects(
    tmp_path: Path,
    isolated_database_env: str,
) -> None:
    harness = await _authorized_harness(tmp_path, isolated_database_env)
    calls: list[int] = []
    try:
        before = await _product_state(harness)
        assert before["task_status"] == "in_progress"
        assert before["submissions"] == 0
        assert before["max_version"] is None

        first_feedback = await _invoke_blocked(harness, calls)
        assert first_feedback.eligible is False
        assert any(entry.failure_code is not None for entry in first_feedback.entries)
        assert calls == [1]

        first_identity = await _evidence_state(harness)
        _assert_no_product_effects(await _product_state(harness), before)

        replay_feedback = await _invoke_blocked(harness, calls)
        assert replay_feedback == first_feedback
        assert calls == [1]
        assert await _evidence_state(harness) == first_identity
        _assert_no_product_effects(await _product_state(harness), before)
    finally:
        await harness.close()


@pytest.mark.asyncio
async def test_no_product_effect_snapshot_detects_submission_aggregate_outbox(
    tmp_path: Path,
    isolated_database_env: str,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    try:
        before = await _product_state(harness)
        async with harness.factory() as session, session.begin():
            result = await OutboxService(session).append(_submission_event(harness))
            assert result.disposition is OutboxAppendDisposition.CREATED

        after = await _product_state(harness)
        assert after["outbox_events"] == before["outbox_events"] + 1
        with pytest.raises(AssertionError, match="outbox_events changed"):
            _assert_no_product_effects(after, before)
    finally:
        await harness.close()
