"""Foreground command, exact replay and source-owner substitution proof."""
import asyncio

import pytest

from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from tests.artifacts.test_submission_intake_admission import (
    admission_intake as admission_intake,
    admin_access as admin_access,
    signed_access as signed_access,
    rsa_signing_material as rsa_signing_material,
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
)


async def test_foreground_command_upload_timeout_retains_charge(admission_intake, tmp_path):
    from sqlalchemy import text
    from app.modules.artifacts.api.submission_intake import SubmissionIntakeFailure
    from tests.artifacts.intake_acceptance_support import foreground_command

    f, key, drained = admission_intake, new_record_id(), asyncio.Event()
    async def stalled_body():
        try:
            await asyncio.Event().wait()
            yield b"unreachable"
        finally:
            drained.set()
    async with foreground_command(f, tmp_path, idle_timeout_seconds=0.02) as (command, calls):
        with pytest.raises(SubmissionIntakeFailure, match="submission_upload_timeout"):
            await command.submit(
                SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment), stalled_body(),
                actor_id=f.actor.actor_profile_id, identity_link_id=f.actor.identity_link_id,
                idempotency_key=key, declared_raw_bytes=None,
            )
        assert drained.is_set() and calls == []
        async with f.factory() as session:
            row = (await session.execute(text(
                "SELECT id,state,failure_code FROM submission_intake_operations WHERE idempotency_key=:key"), {"key": key})).one()
            assert (row.state, row.failure_code) == ("failed", "submission_upload_timeout")
            assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"), {"id": row.id}) == 1024


@pytest.mark.parametrize("outcome", ["completed", "received_failure", "rejected"])
async def test_foreground_command_accepts_or_fails_and_replays_without_new_pre(admission_intake, tmp_path, outcome):
    from sqlalchemy import text
    from app.modules.artifacts.api.submission_intake import SubmissionIntakeFailure
    from tests.artifacts.intake_acceptance_support import foreground_command
    from tests.test_trusted_intake import _archive

    f, key = admission_intake, new_record_id()
    payload = _archive("../escape") if outcome == "rejected" else _archive()
    async def body():
        yield payload
    arguments = dict(actor_id=f.actor.actor_profile_id, identity_link_id=f.actor.identity_link_id,
                     idempotency_key=key, declared_raw_bytes=len(payload))
    metadata = SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment)
    async with foreground_command(f, tmp_path, runtime_outcome=outcome) as (command, calls):
        if outcome == "completed":
            receipt = await command.submit(metadata, body(), **arguments)
            assert receipt["status"] == "accepted" and receipt["replayed"] is False
            assert await command.submit(metadata, body(), **arguments) == dict(receipt, replayed=True)
        else:
            failures = []
            code = "pre_submission_checker_failed" if outcome == "rejected" else "submission_infrastructure_unavailable"
            for _ in range(2):
                with pytest.raises(SubmissionIntakeFailure, match=code) as caught:
                    await command.submit(metadata, body(), **arguments)
                failures.append(caught.value.pre_submission_results)
            assert failures[0] == failures[1]
            if outcome == "rejected":
                assert failures[0]
        assert len(calls) == 1
        async with f.factory() as session:
            row = (await session.execute(text(
                "SELECT state, failure_code, id FROM submission_intake_operations WHERE idempotency_key=:key"),
                {"key": key})).one()
            assert row.state == {"completed": "finalization_pending", "received_failure": "failed", "rejected": "rejected"}[outcome]
            pointer = await session.scalar(text("SELECT active_submission_operation_id FROM workstream_tasks WHERE id=:id"), {"id": f.task})
            assert pointer == (row.id if outcome == "completed" else None)
            assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"), {"id": row.id}) == len(payload)
            assert await session.scalar(text("SELECT count(*) FROM submissions WHERE task_id=:id"), {"id": f.task}) == 0


async def test_foreground_command_cancellation_drains_and_releases_only_task_guard(admission_intake, tmp_path):
    from sqlalchemy import text
    from tests.artifacts.intake_acceptance_support import foreground_command

    f, key, reading = admission_intake, new_record_id(), asyncio.Event()
    async def body():
        reading.set()
        await asyncio.Event().wait()
        yield b"unreachable"
    async with foreground_command(f, tmp_path) as (command, calls):
        pending = asyncio.create_task(command.submit(
            SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment), body(),
            actor_id=f.actor.actor_profile_id, identity_link_id=f.actor.identity_link_id,
            idempotency_key=key, declared_raw_bytes=None,
        ))
        await asyncio.wait_for(reading.wait(), 20)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(pending, 20)
        assert calls == []
        async with f.factory() as session:
            row = (await session.execute(text(
                "SELECT id,state FROM submission_intake_operations WHERE idempotency_key=:key"), {"key": key})).one()
            assert row.state == "cancelled"
            assert await session.scalar(text("SELECT active_submission_operation_id FROM workstream_tasks WHERE id=:id"), {"id": f.task}) is None
            assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"), {"id": row.id}) == 1024


async def test_foreground_command_unknown_acceptance_never_terminalizes_committed_work(admission_intake, tmp_path, monkeypatch):
    from app.modules.artifacts.intake.foreground_admission import IntakeCommitUnknown
    from tests.artifacts.intake_acceptance_support import foreground_command
    from tests.test_trusted_intake import _archive

    f, key = admission_intake, new_record_id()
    original = f.admission.accept
    async def unknown(*args, **kwargs):
        await original(*args, **kwargs)
        raise IntakeCommitUnknown("response lost after commit")
    monkeypatch.setattr(f.admission, "accept", unknown)
    async def forbidden_finish(*args, **kwargs):
        pytest.fail("Unknown acceptance must retain its durable outcome")
    monkeypatch.setattr(f.admission, "finish", forbidden_finish)
    async def body():
        yield _archive()
    metadata = SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment)
    arguments = dict(actor_id=f.actor.actor_profile_id, identity_link_id=f.actor.identity_link_id,
                     idempotency_key=key, declared_raw_bytes=None)
    async with foreground_command(f, tmp_path) as (command, calls):
        with pytest.raises(IntakeCommitUnknown):
            await command.submit(metadata, body(), **arguments)
        receipt = await command.submit(metadata, body(), **arguments)
        assert receipt["status"] == "accepted" and receipt["replayed"] is True
        assert len(calls) == 1


@pytest.mark.parametrize("substitution", ["operation", "generation", "lease"])
async def test_t3_reservation_rejects_substituted_source_or_owner(admission_intake, tmp_path, substitution):
    from dataclasses import replace
    from sqlalchemy import text
    from app.adapters.checkers import selected_pre_submit_coordinator
    from tests.artifacts.intake_acceptance_support import completed_source

    f = admission_intake
    owner, request, _ = await completed_source(f, tmp_path)
    source = request.source
    if substitution == "operation":
        source = source.model_copy(update={"location": source.location.model_copy(
            update={"operation_id": new_record_id()})})
    elif substitution == "generation":
        source = source.model_copy(update={"provider_generation": "another-generation"})
    else:
        owner = replace(owner, lease_id=new_record_id())
    with pytest.raises(IntakeCustodyConflict):
        await f.admission.reserve_pre(
            owner, source, runtime_profile=request.runtime_profile,
            checkers=selected_pre_submit_coordinator,
        )
    async with f.factory() as session:
        assert await session.scalar(text(
            "SELECT count(*) FROM selected_pre_submit_runs WHERE task_id=:id"), {"id": f.task}) == 1
