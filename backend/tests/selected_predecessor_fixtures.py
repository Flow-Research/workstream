"""Selected PRE replacement evidence fixtures; no alternate execution owner."""

from app.adapters.artifacts import selected_pre_submit_source_contracts

from io import BytesIO
from uuid import UUID
from zipfile import ZipFile

from sqlalchemy import select, text

from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitTerminalFacts,
)

_PREPARATION_TABLES = (
    "selected_pre_submit_runs",
    "pre_submit_execution_attempts",
    "pre_submit_evidence_sets",
    "pre_submit_evidence_results",
    "submission_bundle_durable_intents",
    "artifact_put_attempts",
    "artifact_put_attempt_charges",
    "artifact_contents",
    "artifact_replicas",
    "artifact_operation_receipts",
    "artifact_put_observation_receipts",
    "artifact_verification_jobs",
    "artifact_verification_receipts",
    "submission_bundle_admissions",
)


async def _snapshot(h) -> tuple[tuple[str, int], ...]:
    async with h.factory() as session:
        rows = []
        for table in _PREPARATION_TABLES:
            count = await session.scalar(text(f"SELECT pg_catalog.count(*) FROM public.{table}"))
            assert count is not None
            rows.append((table, int(count)))
        return tuple(rows)


async def assert_public_revision_rejection(h, response, key, data, before, code):
    """Keep rejected source custody without changing retained submission facts."""
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from app.modules.artifacts.api.submission_preparation import public_pre_submission_results
    assert response.status_code == 422, response.text
    error = response.json()['error']
    assert error['code'] == 'pre_submission_checker_failed'
    assert error['details']['eligible_to_submit'] is False
    results = error['details']['results']
    assert [r['failure_code'] for r in results if r['status'] == 'failed'] == [code]
    assert not any(r['source'] == 'project_external_checker' for r in results)
    expected = dict(before)
    expected['selected_pre_submit_runs'] += 1
    assert dict(await _snapshot(h)) == expected
    async with h.factory() as session:
        operation = (await session.scalars(select(SubmissionIntakeOperation).where(
            SubmissionIntakeOperation.task_id == str(h.request.task_id),
            SubmissionIntakeOperation.idempotency_key == str(key),
        ))).one()
        assert operation.state == 'rejected' and operation.finalized_submission_id is None
        charge = await session.get(SubmissionSourceCharge, operation.id)
        assert charge.accounted_bytes == len(data) and charge.state == 'sealed'
        run = (await session.scalars(select(SelectedPreSubmitRun).where(
            SelectedPreSubmitRun.source_operation_id == operation.id,
        ))).one()
        terminal = SelectedPreSubmitTerminalFacts.from_canonical_body(
            run.terminal_json, source_contracts=selected_pre_submit_source_contracts())
        reservation = terminal.lease.reservation
        assert run.status == terminal.outcome == 'completed' and run.eligible is False
        assert terminal.execution.eligible is False and terminal.execution.external_members == ()
        assert public_pre_submission_results(terminal.execution) == results
        assert terminal.terminal_digest == run.terminal_digest
        assert reservation.request_digest == run.request_digest
        assert reservation.task_id == h.request.task_id
        assert reservation.assignment_id == h.request.assignment_id
        assert reservation.actor_profile_id == h.actor_context.actor_profile_id
        assert reservation.source.location.operation_id == UUID(operation.id)
        assert reservation.admission_lineage.predecessor_submission_id == h.created.submission_id
        assert await session.scalar(text(
            "SELECT public.selected_pre_submit_receipt_valid(r,'execute',false) "
            "AND public.selected_pre_submit_receipt_valid(r,'finalize',false) "
            "FROM selected_pre_submit_runs r WHERE id=:id"), {'id': run.id}) is True
        assert await session.scalar(text('SELECT count(*) FROM submissions')) == 1
        assert await session.scalar(text('SELECT status FROM workstream_tasks WHERE id=:id'),
                                    {'id': h.request.task_id}) == 'needs_revision'
    return results


def _secret_archive(data: bytes) -> bytes:
    """Keep the real changed packet and introduce one known secret signature."""
    output = BytesIO(data)
    with ZipFile(output, "a") as archive:
        archive.writestr("probe.txt", b"-----BEGIN OPENSSH PRIVATE KEY-----\nprobe\n")
    return output.getvalue()
