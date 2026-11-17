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


async def configure_source_http(factory, client, tmp_path, monkeypatch, payload, outcome, *, project_findings=()):
    """Bind signed HTTP to real intake owners and the controlled guest transport."""
    from app.adapters import artifacts as composition
    from app.adapters.checkers import SelectedPreSubmitCheckerExecutionAdapter
    from app.modules.actors.api import ServiceIdentity
    from tests.artifacts.test_submission_pre_source import _source_runtime
    from tests.checkers.execution.support import provision_post_submit_service
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation
    from tests.test_artifact_admission import _settings
    runtime_root = tmp_path / f"source-http-{new_record_id()}"
    runtime_root.mkdir()
    runtime, errors = _source_runtime(payload, runtime_root, outcome, project_findings=project_findings)
    calls, original = [], runtime.execute_pre
    async def execute(lease, grant):
        calls.append(lease.reservation.attempt_id)
        return await original(lease, grant)
    runtime.execute_pre = execute
    monkeypatch.setattr(composition, "selected_pre_submit_checker_execution",
                        lambda **kwargs: SelectedPreSubmitCheckerExecutionAdapter(external_execution=runtime))
    await provision_post_submit_service(factory, ServiceIdentity.CHECKER_PRE_SUBMIT)
    await provision_post_submit_service(factory, ServiceIdentity.ARTIFACT_MATERIALIZER)
    app = client._transport.app
    storage = {name: value for name, value in _settings(tmp_path).model_dump().items() if name.startswith("artifact_")}
    settings = app.state.settings.model_copy(update=storage | {"submission_execution_profile": {
        "capacity": {"maximum_total_bytes": 4 * 1024 * 1024},
        "runtime": _source_reservation().runtime_profile.model_dump(mode="json"),
        "upload_total_seconds": 300.0, "upload_idle_seconds": 10.0,
        "foreground_lease_seconds": 60.0, "heartbeat_seconds": 10.0,
        "replay_total_seconds": 30.0, "part_bytes": 5 * 1024**2,
    }})
    monkeypatch.setattr(app.state, "settings", settings)
    return client, settings, errors, calls


@pytest.mark.parametrize("outcome,framing", [
    ("completed", "small"), ("rejected", "small"),
    ("completed", "large-single"), ("completed", "large-split"),
])
async def test_public_raw_zip_submission_uses_real_owners_and_stable_replay(admission_intake, tmp_path, monkeypatch, outcome, framing):
    from sqlalchemy import text
    from tests.test_trusted_intake import _archive

    f, key = admission_intake, new_record_id()
    payload = _archive("../escape") if outcome == "rejected" else _archive()
    if framing.startswith("large"):
        payload = _archive(content=b"finished work\n" * 90_000)
        assert 1024 * 1024 < len(payload) < 2 * 1024 * 1024
    def body(split):
        if not split:
            return payload
        async def chunks():
            for start in range(0, len(payload), 64 * 1024):
                yield payload[start:start + 64 * 1024]
        return chunks()
    client, settings, errors, calls = await configure_source_http(
        f.factory, f.access.signed.client, tmp_path, monkeypatch, payload, outcome,
    )
    app = client._transport.app
    headers = f.access.target.headers | {"Content-Type": "application/zip",
        "X-Task-Assignment-Id": str(f.assignment), "Idempotency-Key": str(key),
        "Content-Length": str(len(payload))}
    url = f"/api/v1/tasks/{f.task}/submissions"
    first = await client.post(url, headers=headers, content=body(framing == "large-split"))
    second = await client.post(url, headers=headers, content=body(framing != "large-split"))
    assert not errors, "\n".join(errors)
    assert len(calls) == 1, (first.status_code, first.text, second.status_code, second.text)
    if outcome == "completed":
        assert first.status_code == second.status_code == 202, (first.text, second.text)
        receipt = first.json()
        assert second.json() == dict(receipt, replayed=True)
        assert receipt["status"] == "accepted" and receipt["replayed"] is False
        assert set(receipt) == {"operation_id", "task_id", "assignment_id", "status", "accepted_at",
                                "task_status_at_acceptance", "processing_stage_at_acceptance", "replayed", "pre_submission_results"}
    else:
        assert first.status_code == second.status_code == 422, (first.text, second.text)
        assert first.json()["error"]["code"] == second.json()["error"]["code"] == "pre_submission_checker_failed"
        assert first.json()["error"]["details"] == second.json()["error"]["details"]
        assert first.json()["error"]["details"]["eligible_to_submit"] is False
    if framing == "small":
        # Reads need no writer/runtime deployment configuration or provider bootstrap.
        monkeypatch.setattr(app.state, "settings", settings.model_copy(update={"submission_execution_profile": None}))
        progress_url = f"/api/v1/tasks/{f.task}/submission-operations"
        progress = await client.get(progress_url, headers=f.access.target.headers,
                                    params={"idempotency_key": str(key)})
        assert progress.status_code == 200, progress.text
        observed = progress.json()
        expected = "finalization_pending" if outcome == "completed" else "rejected"
        assert observed["operation_state"] == observed["processing_stage"] == expected
        assert observed["next_action"] == ("wait" if outcome == "completed" else "correct_and_submit_new_key")
        assert observed["operationally_stalled"] is False
        assert observed["current_task_status"] == ("evaluation_pending" if outcome == "completed" else "in_progress")
        assert observed["submission_id"] is observed["submission_version"] is observed["evaluation_request_id"] is None
        assert observed["pre_submission_results"] == (receipt["pre_submission_results"] if outcome == "completed"
                                                       else first.json()["error"]["details"]["results"])
        by_id = await client.get(progress_url, headers=f.access.target.headers,
                                 params={"operation_id": observed["operation_id"]})
        assert by_id.status_code == 200 and by_id.json() == observed, by_id.text
        managed = await client.get(progress_url, headers=f.manager.headers,
                                   params={"operation_id": observed["operation_id"]})
        assert managed.status_code == 200, managed.text
        assert managed.json()["processing_stage"] == expected
        assert managed.json()["next_action"] == ("wait" if outcome == "completed" else "inspect_governed_outcome")
        manager_key = await client.get(progress_url, headers=f.manager.headers,
                                       params={"idempotency_key": str(key)})
        assert manager_key.status_code == 404, manager_key.text
        stranger = await f.access.signed.actor("progress-stranger")
        concealed = await client.get(progress_url, headers=stranger.headers,
                                     params={"operation_id": observed["operation_id"]})
        assert concealed.status_code == 404, concealed.text
        for params in ({}, {"operation_id": observed["operation_id"], "idempotency_key": str(key)},
                       {"operation_id": "invalid"}, {"operation_id": observed["operation_id"], "actor_id": str(f.actor.actor_profile_id)}):
            invalid = await client.get(progress_url, headers=f.access.target.headers, params=params)
            assert invalid.status_code == 422, invalid.text
    async with f.factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM submissions WHERE task_id=:id"), {"id": f.task}) == 0
        assert await session.scalar(text("SELECT count(*) FROM submission_intake_operations WHERE task_id=:id"), {"id": f.task}) == 1


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
