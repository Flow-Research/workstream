"""Built CLI -> real socket/API -> PostgreSQL and local ART custody.

Fixtures arrange approved policy, a started assignment and development identity.
The CLI creates the tested preparation and Submission. The actual independent ART
verifier is invoked directly; distributed worker scheduling and full public setup
are #552's separate proof, not claims of this test.
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
from sqlalchemy import func, select
import uvicorn

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND / "tests"))
from tests.conftest import (  # noqa: E402
    configured_source_instance_id as configured_source_instance_id,
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    isolated_database_env as isolated_database_env,
)
from tests.tasks.test_submission_lineage import _prepared_packet  # noqa: E402
from tests.tasks.test_public_submission_intake import _client  # noqa: E402
from tests.tasks.submission_lineage_support import _verify_put_attempt  # noqa: E402
from app.modules.actors.models import ActorProfile  # noqa: E402
from app.modules.tasks.models import Submission  # noqa: E402
from app.modules.checkers.models import CheckerRun  # noqa: E402
from app.modules.artifacts.models import SubmissionBundleAdmission  # noqa: E402
from app.modules.authorization.models import ProjectRoleGrant  # noqa: E402
from tests.test_artifact_admission import _context, _seed_human_actor  # noqa: E402
from tests.submission_preparation_auth_helpers import install_submitter_grant  # noqa: E402
from tests.project_create_fixtures import seed_historical_project  # noqa: E402
from app.core.identifiers import new_record_id  # noqa: E402


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


@pytest.mark.asyncio
async def test_cli_public_preparation_creation_replay_history_and_suspension(
    isolated_database_env,
    tmp_path,
    monkeypatch,
    cli,
):
    async with _prepared_packet(isolated_database_env, tmp_path) as h:
        archive = tmp_path / "work.zip"
        archive.write_bytes(h.archive_bytes)
        key = str(uuid4())
        packet = (
            "--assignment",
            str(h.assignment_id),
            "--summary",
            h.preparation_request.summary,
            "--attestation",
            h.preparation_request.contributor_attestation,
        )
        prepare = (
            "task",
            "prepare",
            str(h.task_id),
            *packet,
            "--file",
            str(archive),
            "--idempotency-key",
            key,
        )
        async with _client(h, monkeypatch, isolated_database_env) as direct:
            async with socket_api(direct._transport.app) as origin:

                async def call(*args, denied=None):
                    # PRE runs real bounded intake work before responding; the
                    # default 20s fake-peer budget is not its processing contract.
                    result = await asyncio.to_thread(
                        cli,
                        origin,
                        "public-intake-token",
                        "-o",
                        "json",
                        *args,
                        process_timeout=90 if args[:2] == ("task", "prepare") else 20,
                    )
                    if denied is not None:
                        assert result.returncode == 1 and result.stdout == "", (
                            result.stderr
                        )
                        assert json.loads(result.stderr)["error"]["status"] == denied
                        return None
                    assert result.returncode == 0 and result.stderr == "", result.stderr
                    return json.loads(result.stdout)

                paths = (await direct.get("/openapi.json")).json()["paths"]
                assert (
                    "post"
                    in paths["/api/v1/tasks/{task_id}/submission-bundle-preparations"]
                )
                assert "post" in paths["/api/v1/tasks/{task_id}/submissions"]
                prepared = await call(*prepare)
                assert (
                    prepared["submission_bundle_preparation_status"]
                    == "stored_pending_verification"
                )
                assert prepared["admission_id"] is None
                # The admitted attempt's intake feedback is returned, not dropped.
                assert prepared["pre_submission_results"]
                assert all(
                    item["status"] in {"passed", "warning"}
                    for item in prepared["pre_submission_results"]
                )
                async with h.factory() as session:
                    assert (
                        await session.scalar(
                            select(func.count()).select_from(Submission)
                        )
                        == 0
                    )
                admission_id = await _verify_put_attempt(
                    h.factory,
                    h.store,
                    h.namespace,
                    h.settings,
                    prepared["put_attempt_id"],
                )
                ready = await call(*prepare)
                assert ready == prepared | {
                    "submission_bundle_preparation_status": "ready",
                    "admission_id": str(admission_id),
                    "replayed": True,
                }
                submit = (
                    "task",
                    "submit",
                    str(h.task_id),
                    *packet,
                    "--admission",
                    str(admission_id),
                )
                receipt = await call(*submit)
                assert receipt["admission_id"] == str(admission_id)
                assert receipt["submission_version"] == 1
                assert await call(*submit) == receipt
                changed = list(submit)
                changed[changed.index("--summary") + 1] += " changed"
                await call(*changed, denied=404)
                submission_id = receipt["submission_id"]
                history = await call(
                    "task", "submissions", str(h.task_id), "--limit", "1"
                )
                assert [v["id"] for v in history["items"]] == [submission_id]
                detail = await call("submission", "show", submission_id)
                assert detail == history["items"][0]
                assert detail["summary"] == h.preparation_request.summary
                findings = await call("submission", "findings", submission_id)
                assert len(findings["items"]) == 1
                run = findings["items"][0]
                assert (
                    run["submission_id"] == submission_id and run["status"] == "queued"
                )
                assert (
                    await call(
                        "submission", "findings", submission_id, "--run", run["id"]
                    )
                    == run
                )
                # The caller's own-work reads decode the same real records.
                [assignment] = (await call("me", "assignments"))["items"]
                assert assignment["task_id"] == str(h.task_id)
                assert assignment["latest_submission"]["submission_id"] == submission_id
                assert assignment["next_action"] == "awaiting_evaluation"
                [attempt] = (await call("me", "submissions", "--task", str(h.task_id)))[
                    "items"
                ]
                assert attempt["submission_id"] == submission_id
                assert attempt["status"] == detail["status"]
                summary = await call("me", "summary")
                assert summary["assignments"] == {"active": 1, "closed": 0}
                [project] = (await call("me", "projects"))["items"]
                assert project["project_id"] == assignment["project_id"]
                assert project["project_roles"] == ["submitter"]
                preparations = (await call("task", "preparations", str(h.task_id)))[
                    "items"
                ]
                [preparation] = [
                    item for item in preparations if item["state"] == "submitted"
                ]
                assert preparation["submission_id"] == submission_id
                one = await call(
                    "task", "preparation", str(h.task_id), preparation["preparation_id"]
                )
                assert {k: v for k, v in one.items() if k != "findings"} == preparation
                assert one["findings"] == prepared["pre_submission_results"]
                await call(
                    "task", "preparation", str(h.task_id), str(uuid4()), denied=404
                )
                await call("submission", "show", str(uuid4()), denied=404)
                async with h.factory() as session:
                    assert (
                        await session.scalar(
                            select(func.count()).select_from(Submission)
                        )
                        == 1
                    )
                    assert (
                        await session.scalar(
                            select(func.count()).select_from(CheckerRun)
                        )
                        == 1
                    )
                    admission = await session.get(
                        SubmissionBundleAdmission, str(admission_id)
                    )
                    assert admission.status == "consumed"
                    assert (
                        admission.archive_sha256
                        == "sha256:" + hashlib.sha256(h.archive_bytes).hexdigest()
                    )
                    assert admission.archive_byte_count == len(h.archive_bytes)
                    assert admission.consumed_by_submission_id == submission_id
                    stored_run = await session.get(CheckerRun, run["id"])
                    assert (
                        stored_run.evaluation_request_id
                        == receipt["evaluation_request_id"]
                    )
                foreign_context = _context()
                other_project_context = _context()
                other_project = new_record_id()
                async with h.factory.begin() as session:
                    await _seed_human_actor(session, foreign_context)
                    await _seed_human_actor(session, other_project_context)
                    await seed_historical_project(
                        session,
                        project_id=str(other_project),
                        name="Other CLI project",
                        slug=f"cli-other-{other_project}",
                    )
                    await install_submitter_grant(
                        await session.connection(),
                        {
                            "project": str(h.project_id),
                            "actor": str(foreign_context.actor_profile_id),
                        },
                    )
                    await install_submitter_grant(
                        await session.connection(),
                        {
                            "project": str(other_project),
                            "actor": str(other_project_context.actor_profile_id),
                        },
                    )
                # A different authenticated actor with a real same-project
                # Submitter grant still cannot reuse this assignment/history.
                for actor in (foreign_context, other_project_context):
                    with monkeypatch.context() as foreign_patch:
                        async with _client(
                            h,
                            foreign_patch,
                            isolated_database_env,
                            subject=f"human-{actor.actor_profile_id}",
                        ) as foreign:
                            async with socket_api(
                                foreign._transport.app
                            ) as foreign_origin:
                                for args in (
                                    submit,
                                    ("submission", "show", submission_id),
                                    ("submission", "findings", submission_id),
                                    ("task", "submissions", str(h.task_id)),
                                ):
                                    result = await asyncio.to_thread(
                                        cli,
                                        foreign_origin,
                                        "public-intake-token",
                                        "-o",
                                        "json",
                                        *args,
                                    )
                                    assert (
                                        result.returncode == 1 and result.stdout == ""
                                    ), result.stderr
                                    assert (
                                        json.loads(result.stderr)["error"]["status"]
                                        == 404
                                    )
                async with h.factory.begin() as session:
                    profile = await session.get(
                        ActorProfile, str(h.context.actor_profile_id)
                    )
                    profile.status = "suspended"
                    profile.suspended_by = "cli-test"
                    profile.suspended_at = datetime.now(UTC)
                    profile.suspension_reason = "fresh authority regression"
                await call(*submit, denied=404)
                await call("submission", "show", submission_id, denied=404)
                await call("submission", "findings", submission_id, denied=404)
                await call("task", "submissions", str(h.task_id), denied=404)
                # Arrange a different invalidation independently: restore the
                # actor and revoke its exact project grant, preserving provenance.
                async with h.factory.begin() as session:
                    profile = await session.get(
                        ActorProfile, str(h.context.actor_profile_id)
                    )
                    profile.status = "active"
                    profile.suspended_by = profile.suspended_at = (
                        profile.suspension_reason
                    ) = None
                    profile.reactivated_by = "cli-test"
                    profile.reactivated_at = datetime.now(UTC)
                    profile.reactivation_reason = "Isolate revoked-grant proof"
                    grant = (
                        await session.scalars(
                            select(ProjectRoleGrant).where(
                                ProjectRoleGrant.actor_profile_id
                                == str(h.context.actor_profile_id),
                                ProjectRoleGrant.project_id == str(h.project_id),
                                ProjectRoleGrant.role == "submitter",
                            )
                        )
                    ).one()
                    grant.status, grant.version = "revoked", 2
                    grant.revoked_by_actor_profile_id = (
                        grant.granted_by_actor_profile_id
                    )
                    grant.revoked_by_admin_role_grant_id = (
                        grant.granted_by_admin_role_grant_id
                    )
                    grant.revoked_reason = "CLI fresh replay authority regression"
                    grant.revoked_at = datetime.now(UTC)
                await call(*submit, denied=404)
                await call("submission", "show", submission_id, denied=404)
                await call("submission", "findings", submission_id, denied=404)
                await call("task", "submissions", str(h.task_id), denied=404)
