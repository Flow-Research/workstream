"""Selected PRE replacement evidence fixtures; no alternate execution owner."""

from app.adapters.artifacts import selected_pre_submit_source_contracts

from dataclasses import replace
from io import BytesIO
from uuid import UUID
import json
from zipfile import ZipFile

from sqlalchemy import select, text

from app.core.identifiers import new_record_id
from app.modules.artifacts.selected_pre_submit_admission import (
    selected_pre_submit_attempt_request_digest,
)
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitReservationFacts,
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


async def _assert_default_failure(h, request, failure, before, code: str) -> None:
    """Allow only the exact terminal selected run while ART remains untouched."""
    assert failure.facts.eligible is False
    failed = tuple(
        check for check in failure.facts.workstream_default.checks if check.status == "failed"
    )
    assert tuple(check.failure_code for check in failed) == (code,)
    assert failure.facts.external_members == ()
    after = dict(await _snapshot(h))
    expected = dict(before)
    expected["selected_pre_submit_runs"] += 1
    assert after == expected
    async with h.factory() as session:
        run = (
            await session.scalars(
                select(SelectedPreSubmitRun).where(
                    SelectedPreSubmitRun.actor_profile_id == str(request.actor.actor_profile_id),
                    SelectedPreSubmitRun.idempotency_key == str(request.idempotency_key),
                )
            )
        ).one()
        terminal = SelectedPreSubmitTerminalFacts.from_canonical_body(run.terminal_json, source_contracts=selected_pre_submit_source_contracts())
        reservation = terminal.lease.reservation
        assert run.status == terminal.outcome == "completed"
        assert run.eligible is False and terminal.execution == failure.facts
        assert terminal.terminal_digest == run.terminal_digest
        assert reservation.request_digest == run.request_digest
        assert reservation.task_id == request.task_id
        assert reservation.assignment_id == request.assignment_id
        assert reservation.actor_profile_id == request.actor.actor_profile_id
        assert (
            reservation.admission_lineage.predecessor_submission_id
            == request.predecessor_submission_id
        )
        assert (
            await session.scalar(
                text("""
            SELECT public.selected_pre_submit_receipt_valid(r,'execute',false)
               AND public.selected_pre_submit_receipt_valid(r,'finalize',false)
            FROM public.selected_pre_submit_runs r WHERE id=:id
        """),
                {"id": run.id},
            )
            is True
        )


async def _queued_selected_body(h, admission_id, *, cause=None) -> dict:
    """Build a valid fresh reservation from one actual selected admission."""
    async with h.factory() as session:
        body = await session.scalar(
            text("""
            SELECT to_jsonb(r) FROM public.selected_pre_submit_runs r
            JOIN public.submission_bundle_admissions a ON a.selected_pre_submit_run_id=r.id
            WHERE a.id=:id
        """),
            {"id": admission_id},
        )
    assert body is not None and body["status"] == "completed" and body["eligible"] is True
    facts = SelectedPreSubmitReservationFacts.from_canonical_body(body["request_json"], source_contracts=selected_pre_submit_source_contracts())
    lineage = facts.admission_lineage
    assert lineage is not None
    key = new_record_id()
    facts = replace(
        facts,
        attempt_id=new_record_id(),
        idempotency_key=key,
        prepared_generation_id=new_record_id(),
        admission_lineage=(
            replace(lineage, checker_remediation_manifest_id=UUID(str(cause)))
            if cause is not None
            else lineage
        ),
        attempt_request_digest=selected_pre_submit_attempt_request_digest(
            actor_profile_id=facts.actor_profile_id,
            identity_link_id=facts.identity_link_id,
            task_id=facts.task_id,
            assignment_id=facts.assignment_id,
            predecessor_submission_id=lineage.predecessor_submission_id,
            idempotency_key=key,
            archive_sha256=facts.archive_sha256,
            archive_byte_count=facts.archive_byte_count,
            packet_sha256=lineage.packet_sha256,
        ),
    )
    return body | {
        "id": str(facts.attempt_id),
        "idempotency_key": str(key),
        "prepared_generation_id": str(facts.prepared_generation_id),
        "request_json": facts.canonical_body(),
        "request_digest": facts.request_digest,
        "status": "queued",
        "lease_id": None,
        "lease_generation": 0,
        "lease_expires_at": None,
        "execute_evidence_id": None,
        "finalize_evidence_id": None,
        "terminal_json": None,
        "terminal_digest": None,
        "eligible": None,
        "started_at": None,
        "completed_at": None,
    }


async def _insert_selected_reservation(h, body) -> None:
    """Exercise installed native INSERT guards without disabling any custody."""
    async with h.factory.begin() as session:
        await session.execute(
            text("""
            INSERT INTO public.selected_pre_submit_runs
            SELECT (pg_catalog.jsonb_populate_record(
                NULL::public.selected_pre_submit_runs, CAST(:body AS jsonb)
                || pg_catalog.jsonb_build_object('queued_at',clock_timestamp())
            )).*
        """),
            {"body": json.dumps(body)},
        )
