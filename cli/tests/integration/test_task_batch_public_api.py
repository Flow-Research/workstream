"""Built CLI over real sockets, PostgreSQL and verified MinIO JSON sources.

Active-guide prerequisites and the canonical development identity verifier are
qualified fixture setup. Task membership, AUTH, source bytes and all transitions
use the actual public owners; no route or authority dependency is replaced.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import csv
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from time import monotonic
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import or_, select
import uvicorn

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND / "tests"))
sys.path.insert(0, str(BACKEND / "scripts"))

from app.db import session as db_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.authorization.models import AdminRoleGrant  # noqa: E402
from app.modules.tasks.api.task_import import TaskImportRow  # noqa: E402
from tests.conftest import (  # noqa: E402
    configured_source_instance_id as configured_source_instance_id,
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.authorization.guide_activation.pg_support import revoke_manager_grant  # noqa: E402
from tests.authorization.task_authority.test_concurrency import actor_context  # noqa: E402
from tests.test_task_import_sources import import_source_client as _import_source_client  # noqa: E402
from tests.test_tasks import (  # noqa: E402
    auth_headers,
    create_active_project,
    task_database_env as task_database_env,
)
from tests.tasks.test_task_batch_transitions import _success_facts  # noqa: E402
from tests.tasks.test_task_import_contract import document  # noqa: E402
from tests.tasks.test_task_import_batches import _counts  # noqa: E402

# CLI collection uses strict asyncio mode. Preserve the canonical fixture body.
import_source_client = pytest_asyncio.fixture(_import_source_client.__wrapped__)


@asynccontextmanager
async def socket_api(app):
    """Use real lifespan and a reserved loopback socket without route overrides."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(app, lifespan="on", log_level="error", access_log=False)
    )
    running = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        deadline = monotonic() + 30
        while not server.started:
            assert not running.done(), "canonical API startup failed"
            assert monotonic() < deadline, "API startup exceeded its bound"
            await asyncio.sleep(0.02)
        yield origin
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(running, timeout=20)
        finally:
            listener.close()


async def invoke(origin, operation, *args):
    """Allow only this native caller the measured three-minute write budget."""
    executable = os.environ["WORKSTREAM_CLI_EXECUTABLE"]
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LANG", "LC_ALL"}
    }
    env.update(WORKSTREAM_API_URL=origin, WORKSTREAM_TOKEN="task-token")
    result = await asyncio.to_thread(
        subprocess.run,  # noqa: S603 - built executable and bounded owned arguments
        [executable, "-o", "json", "project", "task-batch", operation, *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=200,
    )
    assert "task-token" not in result.stdout + result.stderr, "credential leaked"
    return result


async def successful(origin, operation, *args):
    result = await invoke(origin, operation, *args)
    assert result.returncode == 0 and result.stderr == "", result.stderr
    return json.loads(result.stdout)


@pytest.mark.asyncio
async def test_equivalent_verified_source_recovers_original_and_changed_key_conflicts(
    import_source_client,
    tmp_path,
):
    """Actual distinct verified selectors preserve one native batch and its originals."""
    path = tmp_path / "briefs.json"
    path.write_text(json.dumps(document(2), ensure_ascii=False), encoding="utf-8")
    project_response = await import_source_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={"name": "Equivalent source", "slug": "cli-recovery-" + uuid4().hex},
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()["id"]
    async with socket_api(create_app()) as origin:
        sources = []
        for _ in range(2):
            source = await successful(
                origin,
                "source-declare",
                project,
                "--input",
                str(path),
                "--idempotency-key",
                str(uuid4()),
            )
            await successful(
                origin,
                "source-upload",
                project,
                source["source_id"],
                "--input",
                str(path),
            )
            sources.append(source["source_id"])
        assert sources[0] != sources[1]
        key = str(uuid4())
        original = await successful(
            origin, "import", project, sources[0], "--idempotency-key", key
        )
        recovered = await successful(
            origin, "import", project, sources[1], "--idempotency-key", str(uuid4())
        )
        assert recovered == original and recovered["source_id"] == sources[0]
        before = await _counts(project)
        assert before == (1, 2, 2, 2, 2, 2)
        changed = await invoke(
            origin, "import", project, sources[1], "--idempotency-key", key
        )
        assert changed.returncode == 1 and changed.stdout == ""
        error = json.loads(changed.stderr)["error"]
        assert (
            error["status"] == 409
            and error["code"] == "task_import_idempotency_mismatch"
        )
        assert not error.get("outcome_unknown", False)
        assert await _counts(project) == before


@pytest.mark.asyncio
async def test_source_download_verifies_public_custody_and_fresh_read_authority(
    import_source_client,
    tmp_path,
):
    original = json.dumps(document(1), ensure_ascii=False).encode()
    source_file = tmp_path / "briefs.json"
    source_file.write_bytes(original)
    project_response = await import_source_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={"name": "CLI source download", "slug": "cli-download-" + uuid4().hex},
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()["id"]
    profile_response = await import_source_client.get(
        "/api/v1/actors/me",
        headers=auth_headers(),
    )
    assert profile_response.status_code == 200, profile_response.text
    actor_id = profile_response.json()["actor_profile_id"]

    async with socket_api(create_app()) as origin:
        declared = await successful(
            origin,
            "source-declare",
            project,
            "--input",
            str(source_file),
            "--idempotency-key",
            str(uuid4()),
        )
        source_id = declared["source_id"]
        uploaded = await successful(
            origin,
            "source-upload",
            project,
            source_id,
            "--input",
            str(source_file),
        )
        assert uploaded["status"] == "verified"
        destination = tmp_path / "download"
        destination.mkdir()
        receipt = await successful(
            origin,
            "source-download",
            project,
            source_id,
            "--download",
            str(destination),
        )
        assert receipt == {"downloaded": source_id + ".json", "source": uploaded}
        assert (destination / receipt["downloaded"]).read_bytes() == original

        async with db_session.get_session_factory()() as session:
            grants = list(
                await session.scalars(
                    select(AdminRoleGrant)
                    .where(
                        AdminRoleGrant.target_actor_profile_id == actor_id,
                        AdminRoleGrant.role == "project_manager",
                        AdminRoleGrant.status == "active",
                        or_(
                            AdminRoleGrant.scope_type == "system",
                            AdminRoleGrant.scope_project_id == project,
                        ),
                    )
                    .order_by(AdminRoleGrant.id)
                )
            )
            references = [
                (grant.id, grant.granted_by_actor_profile_id) for grant in grants
            ]
        assert references
        for grant_id, administrator_id in references:
            context = await actor_context(administrator_id)
            async with db_session.get_session_factory()() as session, session.begin():
                await revoke_manager_grant(session, context, UUID(str(grant_id)))

        revoked_destination = tmp_path / "revoked-download"
        revoked_destination.mkdir()
        denied = await invoke(
            origin,
            "source-download",
            project,
            source_id,
            "--download",
            str(revoked_destination),
        )
        assert denied.returncode == 1 and denied.stdout == ""
        error = json.loads(denied.stderr)["error"]
        assert (
            error["status"] == 404 and error["code"] == "task_import_source_not_found"
        )
        assert not error.get("outcome_unknown", False)
        assert list(revoked_destination.iterdir()) == []


@pytest.mark.asyncio
async def test_200_row_csv_source_import_screen_release_and_fresh_denial(
    import_source_client,
    tmp_path,
    record_property,
):
    """Real complete membership and exact bytes survive replay and denied late calls."""
    csv_path, json_path = tmp_path / "briefs.csv", tmp_path / "briefs.json"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(TaskImportRow.model_fields))
        writer.writeheader()
        for index, row in enumerate(document(200)["tasks"]):
            row.update(
                title=f'Caption café, "{index}"',
                description="Quoted\nmultilingual brief",
                skill_tags="French;Arabic",
                acceptance_criteria="Accurate, complete work" if index % 2 else "",
                rejection_criteria="Incomplete work",
            )
            writer.writerow(row)

    # The canonical source fixture claims the configured provider namespace
    # before any hidden guide setup; genuine lifespan validates that same claim.
    async with socket_api(create_app()) as origin:
        project = (
            await create_active_project(
                import_source_client, slug="cli-bulk-" + uuid4().hex
            )
        )["id"]
        converted = await successful(
            origin, "convert-csv", "--input", str(csv_path), "--out", str(json_path)
        )
        raw = json_path.read_bytes()
        converted_rows = json.loads(raw)["tasks"]
        assert all("acceptance_criteria" not in row for row in converted_rows[::2])
        assert all(
            row["acceptance_criteria"] == "Accurate, complete work"
            for row in converted_rows[1::2]
        )
        commitment = "sha256:" + hashlib.sha256(raw).hexdigest()
        assert converted["sha256"] == commitment and converted["byte_count"] == len(raw)
        source = await successful(
            origin,
            "source-declare",
            project,
            "--input",
            str(json_path),
            "--idempotency-key",
            str(uuid4()),
        )
        source_id = source["source_id"]
        uploaded = await successful(
            origin, "source-upload", project, source_id, "--input", str(json_path)
        )
        assert uploaded["status"] == "verified" and uploaded["sha256"] == commitment
        async with httpx.AsyncClient(
            base_url=origin, timeout=12, trust_env=False
        ) as client:
            download = await client.get(
                f"/api/v1/projects/{project}/task-import-sources/{source_id}/content",
                headers=auth_headers(),
            )
            assert download.status_code == 200 and download.content == raw

        started = monotonic()
        original = await successful(
            origin, "import", project, source_id, "--idempotency-key", str(uuid4())
        )
        record_property("cli_200_import_seconds", monotonic() - started)
        batch_id = original["batch_id"]
        assert original["row_count"] == 200 and original["sha256"] == commitment
        assert all(
            row["status"] == "draft" and row["skill_tags"] == ["French", "Arabic"]
            for row in original["tasks"]
        )
        assert [row["acceptance_criteria"] for row in original["tasks"]] == [
            "Accurate, complete work" if index % 2 else None for index in range(200)
        ]
        keys = {}
        for operation, state in (("screen", "screening"), ("release", "ready")):
            keys[operation] = str(uuid4())
            arguments = (
                project,
                batch_id,
                "--idempotency-key",
                keys[operation],
                "--reason",
                "All briefs approved",
            )
            started = monotonic()
            response = await successful(origin, operation, *arguments)
            record_property(f"cli_200_{operation}_seconds", monotonic() - started)
            assert response["row_count"] == 200
            assert [row["task_id"] for row in response["tasks"]] == [
                row["id"] for row in original["tasks"]
            ]
            assert all(
                row["status"] == state and row["locked_guide_version"]
                for row in response["tasks"]
            )
            before = await _success_facts(project)
            replay = await successful(origin, operation, *arguments)
            assert replay == response
            after = await _success_facts(project)
            assert before[:-1] == after[:-1] and len(after[-1] - before[-1]) == 200
        observed = await successful(origin, "status", project, batch_id)
        assert (
            observed["creation"] == original and len(observed["current_tasks"]) == 200
        )
        assert all(row["status"] == "ready" for row in observed["current_tasks"])
        before = await _success_facts(project)
        assert len(before[1]) == 2 and all(len(rows) == 400 for rows in before[2:5])
        stale = await invoke(
            origin,
            "screen",
            project,
            batch_id,
            "--idempotency-key",
            keys["screen"],
            "--reason",
            "All briefs approved",
        )
        assert stale.returncode == 1 and stale.stdout == ""
        assert json.loads(stale.stderr)["error"]["status"] == 409
        assert await _success_facts(project) == before

        async with db_session.get_session_factory()() as session:
            grants = list(
                await session.scalars(
                    select(AdminRoleGrant)
                    .where(
                        AdminRoleGrant.target_actor_profile_id
                        == original["tasks"][0]["created_by"],
                        AdminRoleGrant.role == "project_manager",
                        AdminRoleGrant.status == "active",
                        or_(
                            AdminRoleGrant.scope_type == "system",
                            AdminRoleGrant.scope_project_id == project,
                        ),
                    )
                    .order_by(AdminRoleGrant.id)
                )
            )
            references = [
                (grant.id, grant.granted_by_actor_profile_id) for grant in grants
            ]
        assert references
        for grant_id, administrator_id in references:
            context = await actor_context(administrator_id)
            async with db_session.get_session_factory()() as session, session.begin():
                await revoke_manager_grant(session, context, UUID(str(grant_id)))
        denied = await invoke(
            origin,
            "release",
            project,
            batch_id,
            "--idempotency-key",
            keys["release"],
            "--reason",
            "All briefs approved",
        )
        assert denied.returncode == 1 and denied.stdout == ""
        error = json.loads(denied.stderr)["error"]
        assert error["status"] == 403 and error["code"] == "permission_not_granted"
        assert not error.get("outcome_unknown", False)
        assert await _success_facts(project) == before
