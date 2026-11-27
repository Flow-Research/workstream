"""Built CLI -> signed HTTP -> raw source custody and OUTBOX finalization.

Policy/task setup is arranged; portable PRE does not qualify native Smol, and
direct delivery invocation does not qualify broker scheduling or public setup.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import json
import hashlib
from pathlib import Path
import socket
import sys
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
import uvicorn

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND / "tests"))
from tests.conftest import (  # noqa: E402
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    isolated_database_env as isolated_database_env,
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.artifacts.test_submission_intake_admission import (  # noqa: E402
    admission_intake as _admission_intake,
    admin_access as _admin_access,
    signed_access as _signed_access,
    rsa_signing_material as rsa_signing_material,
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
)
from tests.artifacts.test_submission_pre_source import _source_runtime  # noqa: E402
from tests.checkers.external.test_selected_pre_submit_coordination import (  # noqa: E402
    _source_reservation,
)
from tests.checkers.execution.support import provision_post_submit_service  # noqa: E402
from tests.authorization.test_pre_submit_attempt_authority import _seed_materializer  # noqa: E402
from tests.test_trusted_intake import _archive  # noqa: E402
from tests.test_artifact_admission import _settings  # noqa: E402
from app.adapters import artifacts as composition  # noqa: E402
from app.adapters.checkers import SelectedPreSubmitCheckerExecutionAdapter  # noqa: E402
from app.modules.actors.api import ServiceIdentity  # noqa: E402
from app.modules.artifacts.intake.models import SubmissionIntakeOperation  # noqa: E402
from tests.authorization.admin_access.support import AdminAccess, create_project  # noqa: E402
from tests.authorization.task_authority.test_postgresql import grant, project_manager  # noqa: E402
from app.modules.actors.models import ActorProfile  # noqa: E402
from app.modules.tasks.models import Submission  # noqa: E402
from app.modules.checkers.models import CheckerRun  # noqa: E402
from app.modules.artifacts.models import SubmissionBundleAdmission  # noqa: E402
from app.modules.authorization.models import AdminRoleGrant, ProjectRoleGrant  # noqa: E402


admission_intake = pytest_asyncio.fixture(_admission_intake.__wrapped__)
admin_access = pytest_asyncio.fixture(_admin_access.__wrapped__)
signed_access = pytest_asyncio.fixture(_signed_access.__wrapped__)


@asynccontextmanager
async def socket_api(app):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(app, lifespan="off", log_level="error", access_log=False)
    )
    running = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(30):
            while not server.started:
                assert not running.done(), "real API failed to start"
                await asyncio.sleep(0.01)
        yield origin
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(running, timeout=20)
        finally:
            listener.close()


async def _remove_setup_management(f):
    # ART's task seed needs management to screen/release, but this drill must
    # exercise only contributor authority. Retain and revoke the setup grant.
    async with f.factory() as session:
        [role] = list(
            await session.scalars(
                select(AdminRoleGrant).where(
                    AdminRoleGrant.target_actor_profile_id
                    == str(f.actor.actor_profile_id),
                    AdminRoleGrant.status == "active",
                )
            )
        )
        assert role.role == "project_manager" and role.scope_project_id == str(
            f.project
        )
        role_id = str(role.id)
    response = await f.access.signed.revoke(f.access.admin, role_id)
    assert response.status_code == 200, response.text
    await _assert_submitter_only(f)


async def _assert_submitter_only(f):
    async with f.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AdminRoleGrant)
                .where(
                    AdminRoleGrant.target_actor_profile_id
                    == str(f.actor.actor_profile_id),
                    AdminRoleGrant.status == "active",
                )
            )
            == 0
        )


async def _configure(f, tmp_path, monkeypatch, payload):
    runtime, errors = _source_runtime(payload, tmp_path, "completed")
    calls, original = [], runtime.execute_pre

    async def execute(lease, request):
        calls.append(lease.reservation.attempt_id)
        return await original(lease, request)

    runtime.execute_pre = execute
    monkeypatch.setattr(
        composition,
        "selected_pre_submit_checker_execution",
        lambda **kwargs: SelectedPreSubmitCheckerExecutionAdapter(
            external_execution=runtime
        ),
    )
    await provision_post_submit_service(f.factory, ServiceIdentity.CHECKER_PRE_SUBMIT)
    await _seed_materializer(f.factory)
    app = f.access.signed.client._transport.app
    storage = {
        k: v
        for k, v in _settings(tmp_path).model_dump().items()
        if k.startswith("artifact_")
    }
    settings = app.state.settings.model_copy(
        update=storage
        | {
            "submission_execution_profile": {
                "capacity": {"maximum_total_bytes": 4 * 1024 * 1024},
                "runtime": _source_reservation().runtime_profile.model_dump(
                    mode="json"
                ),
                "upload_total_seconds": 300.0,
                "upload_idle_seconds": 10.0,
                "foreground_lease_seconds": 60.0,
                "heartbeat_seconds": 10.0,
                "replay_total_seconds": 30.0,
                "part_bytes": 5 * 1024**2,
            }
        }
    )
    monkeypatch.setattr(app.state, "settings", settings)
    return app, settings, calls, errors


async def _finalize(f, tmp_path, settings, operation_id):
    from datetime import timedelta
    from uuid import UUID
    from app.adapters.auth import outbox_dispatch_authorization
    from app.adapters.outbox import outbox_delivery
    from app.modules.outbox.api import DeliveryOptions
    from app.modules.outbox.registry import HandlerRegistry
    from tests.artifact_store_helpers import initialize_local_store

    for identity in (
        ServiceIdentity.ARTIFACT_BINDING,
        ServiceIdentity.OUTBOX_DISPATCHER,
    ):
        await provision_post_submit_service(f.factory, identity)
    store = initialize_local_store(root=tmp_path / "durable", buffer_bytes=256 * 1024)
    try:
        handler = composition.submission_finalization_handler(
            sessions=f.factory,
            settings=settings,
            store=store,
            lease_duration=timedelta(seconds=30),
        )
        event_type = "SubmissionFinalizationRequested"
        delivery = outbox_delivery(
            f.factory,
            authorization_factory=outbox_dispatch_authorization,
            registry=HandlerRegistry(
                [(event_type, 1, handler)], replay_safe=frozenset({(event_type, 1)})
            ),
            options=DeliveryOptions(lease_seconds=30, handler_timeout_seconds=25),
        )
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, operation_id)
            event_id = UUID(row.finalization_event_id)
        assert await delivery.deliver(event_id, f.project, "cli-finalizer") is not None
    finally:
        store.close()


async def _inspect(call, f, receipt, payload):
    progress = await call(
        "task",
        "submission-operation",
        str(f.task),
        "--operation-id",
        receipt["operation_id"],
    )
    submission_id = progress["submission_id"]
    assert progress["operation_state"] == "finalized"
    assert progress["processing_stage"] == "evaluation_pending"
    assert progress["submission_version"] == 1
    history = await call("task", "submissions", str(f.task), "--limit", "1")
    assert [v["id"] for v in history["items"]] == [submission_id]
    detail = await call("submission", "show", submission_id)
    assert detail == history["items"][0]
    assert (
        detail["feedback"]
        == "Completed the required project work and included evidence."
    )
    [run] = (await call("submission", "findings", submission_id))["items"]
    assert run["submission_id"] == submission_id and run["status"] == "queued"
    assert (
        await call("submission", "findings", submission_id, "--run", run["id"]) == run
    )
    [assignment] = (await call("me", "assignments"))["items"]
    assert assignment["task_id"] == str(f.task)
    assert assignment["latest_submission"]["submission_id"] == submission_id
    assert assignment["next_action"] == "awaiting_evaluation"
    [attempt] = (await call("me", "submissions", "--task", str(f.task)))["items"]
    assert (
        attempt["submission_id"] == submission_id
        and attempt["status"] == detail["status"]
    )
    assert (await call("me", "summary"))["assignments"] == {"active": 1, "closed": 0}
    [project] = (await call("me", "projects"))["items"]
    assert project["project_id"] == assignment["project_id"]
    assert project["project_roles"] == ["submitter"]
    await call("submission", "show", str(uuid4()), denied=404)
    await call(
        "task",
        "submission-operation",
        str(f.task),
        "--operation-id",
        str(uuid4()),
        denied=404,
    )
    async with f.factory() as session:
        for model in (Submission, CheckerRun):
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.task_id == str(f.task))
                )
                == 1
            )
        row = await session.get(SubmissionIntakeOperation, receipt["operation_id"])
        admission = await session.scalar(
            select(SubmissionBundleAdmission).where(
                SubmissionBundleAdmission.source_operation_id == row.id
            )
        )
        assert admission.status == "consumed"
        assert (
            admission.archive_sha256 == "sha256:" + hashlib.sha256(payload).hexdigest()
        )
        assert admission.archive_byte_count == len(payload)
        assert admission.consumed_by_submission_id == submission_id
        assert (
            await session.get(CheckerRun, run["id"])
        ).evaluation_request_id == progress["evaluation_request_id"]
    return submission_id


async def _conceal_foreign(call, f, commands):
    same = await f.access.signed.actor("cli-same-project")
    other = await f.access.signed.actor("cli-other-project")
    same_access = AdminAccess(
        f.access.signed, f.access.admin, same, f.access.bootstrap_grant_id
    )
    await grant(same_access, f.manager, f.project)
    other_project = await create_project("cli-other-project")
    other_access = AdminAccess(
        f.access.signed, f.access.admin, other, f.access.bootstrap_grant_id
    )
    other_manager = await project_manager(other_access, other_project)
    await grant(other_access, other_manager, other_project)
    for actor in (same, other):
        for args in commands:
            await call(*args, token=actor.token, denied=404)


async def _invalidate(call, f, commands):
    async with f.factory.begin() as session:
        profile = await session.get(ActorProfile, str(f.actor.actor_profile_id))
        profile.status, profile.suspended_by = "suspended", "cli-test"
        profile.suspended_at, profile.suspension_reason = (
            datetime.now(UTC),
            "fresh authority regression",
        )
    for state in ("suspended", "revoked"):
        if state == "revoked":
            async with f.factory.begin() as session:
                profile = await session.get(ActorProfile, str(f.actor.actor_profile_id))
                profile.status = "active"
                profile.suspended_by = profile.suspended_at = (
                    profile.suspension_reason
                ) = None
                profile.reactivated_by, profile.reactivated_at = (
                    "cli-test",
                    datetime.now(UTC),
                )
                profile.reactivation_reason = "Isolate revoked-grant proof"
                role = await session.get(ProjectRoleGrant, f.grant_id)
                role.status, role.version = "revoked", 2
                role.revoked_by_actor_profile_id = role.granted_by_actor_profile_id
                role.revoked_by_admin_role_grant_id = (
                    role.granted_by_admin_role_grant_id
                )
                role.revoked_reason, role.revoked_at = (
                    "CLI fresh replay authority regression",
                    datetime.now(UTC),
                )
        for args in commands:
            await call(*args, denied=404)


@pytest.mark.asyncio
async def test_cli_public_submission_progress_replay_history_and_suspension(
    admission_intake,
    tmp_path,
    monkeypatch,
    cli,
):
    f, key, payload = admission_intake, str(uuid4()), _archive()
    await _remove_setup_management(f)
    app, settings, calls, errors = await _configure(f, tmp_path, monkeypatch, payload)
    await _assert_submitter_only(f)
    archive = tmp_path / "work.zip"
    archive.write_bytes(payload)
    submit = (
        "task",
        "submit",
        str(f.task),
        "--assignment",
        str(f.assignment),
        "--file",
        str(archive),
        "--idempotency-key",
        key,
        "--feedback",
        "Completed the required project work and included evidence.",
    )
    async with socket_api(app) as origin:

        async def call(*args, denied=None, token=None):
            result = await asyncio.to_thread(
                cli,
                origin,
                token or f.access.target.token,
                "-o",
                "json",
                *args,
                process_timeout=90 if args[:2] == ("task", "submit") else 20,
            )
            if denied is not None:
                assert result.returncode == 1 and result.stdout == "", result.stderr
                assert json.loads(result.stderr)["error"]["status"] == denied, (
                    result.stderr
                )
                return None
            assert result.returncode == 0 and result.stderr == "", result.stderr
            return json.loads(result.stdout)

        paths = (await f.access.signed.client.get("/openapi.json")).json()["paths"]
        assert "post" not in paths.get(
            "/api/v1/tasks/{task_id}/submission-bundle-preparations", {}
        )
        assert "post" in paths["/api/v1/tasks/{task_id}/submissions"]
        receipt = await call(*submit)
        assert receipt["status"] == "accepted" and receipt["replayed"] is False
        assert receipt["pre_submission_results"]
        assert all(
            item["status"] in {"passed", "warning"}
            for item in receipt["pre_submission_results"]
        )
        assert await call(*submit) == dict(receipt, replayed=True)
        changed = list(submit)
        changed[changed.index("--feedback") + 1] += " changed"
        await call(*changed, denied=409)
        status_args = ("task", "status", str(f.assignment))
        status = await call(*status_args)
        assert status["current_status"] == "evaluation_pending"
        assert status["next_action"] == "awaiting_evaluation"
        assert status["assignment"]["latest_submission"] is None
        assert (
            status["intake"]["pre_submission_results"]
            == receipt["pre_submission_results"]
        )
        by_key = await call(
            "task", "submission-operation", str(f.task), "--idempotency-key", key
        )
        by_id = await call(
            "task",
            "submission-operation",
            str(f.task),
            "--operation-id",
            receipt["operation_id"],
        )
        assert by_key == by_id
        assert by_id["processing_stage"] == "finalization_pending"
        assert by_id["submission_id"] is by_id["evaluation_request_id"] is None
        assert by_id["pre_submission_results"] == receipt["pre_submission_results"]
        async with f.factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Submission)
                    .where(Submission.task_id == str(f.task))
                )
                == 0
            )
        await _finalize(f, tmp_path, settings, receipt["operation_id"])
        submission_id = await _inspect(call, f, receipt, payload)
        assert await call(*submit) == dict(receipt, replayed=True)
        assert len(calls) == 1 and not errors, errors
        commands = (
            submit,
            ("submission", "show", submission_id),
            status_args,
            ("submission", "findings", submission_id),
            ("task", "submissions", str(f.task)),
            (
                "task",
                "submission-operation",
                str(f.task),
                "--operation-id",
                receipt["operation_id"],
            ),
        )
        await _conceal_foreign(call, f, commands)
        await _assert_submitter_only(f)
        await _invalidate(call, f, commands)
