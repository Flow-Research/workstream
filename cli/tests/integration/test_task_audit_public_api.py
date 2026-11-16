"""Built CLI against signed public audit routes and real PostgreSQL authority.

Backend fixture helpers arrange activated task prerequisites only. No backend
operation is mocked and the shipped Go client uses public HTTP exclusively.
"""

import asyncio
import json
import socket

import pytest
import pytest_asyncio
import uvicorn

from test_public_self_service import (
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
)
from tests.contributions.exports.conftest import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.conftest import (
    configured_source_instance_id as configured_source_instance_id,
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.authorization.admin_access.fixtures import (
    signed_access as _signed_access,
    admin_access as _admin_access,
)
from tests.authorization.admin_access.support import create_project
from tests.authorization.task_reads.support import task_case
from tests.authorization.task_locked_context.support import grant_for
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.tasks.models import WorkstreamTask

signed_access = pytest_asyncio.fixture(_signed_access.__wrapped__)
admin_access = pytest_asyncio.fixture(_admin_access.__wrapped__)


@pytest.mark.asyncio
async def test_audit_task_reads_real_public_api_scope_and_fresh_authority(
    cli,
    auth_database_env,
    admin_access,
):
    project, manager, task = await task_case(admin_access)
    other = await create_project("Existing foreign audit project")
    auditor = admin_access.target
    grant = await grant_for(admin_access, project, "audit")
    foreign_auditor = await admin_access.signed.actor("foreign-auditor")
    await admin_access.signed.grant(
        admin_access.admin, foreign_auditor, role="audit_authority", project_id=other
    )
    outsider = await admin_access.signed.actor("no-audit-role")

    # This persisted draft is intentionally without a lifecycle event. It
    # exercises the public empty-page contract without inventing an audit write.
    async with db_session.get_session_factory()() as session, session.begin():
        ready = await session.get(WorkstreamTask, str(task))
        empty_task = new_record_id()
        session.add(
            WorkstreamTask(
                id=str(empty_task),
                task_size="small",
                project_id=str(project),
                title="Empty evidence",
                description="Fixture task",
                source_type=ready.source_type,
                status="draft",
                created_by=ready.created_by,
            )
        )

    app = admin_access.signed.client._transport.app
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(app, lifespan="off", log_level="error", access_log=False)
    )
    serve = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(30):
            while not server.started:
                assert not serve.done(), "real API server exited"
                await asyncio.sleep(0.01)

        async def call(
            actor, operation, project_id=project, task_id=task, *flags, status=None
        ):
            result = await asyncio.to_thread(
                cli,
                origin,
                actor.token,
                "-o",
                "json",
                "audit",
                "task",
                operation,
                str(project_id),
                str(task_id),
                *flags,
            )
            if status is not None:
                assert result.returncode == 1 and result.stdout == "", result.stderr
                assert json.loads(result.stderr)["error"]["status"] == status
                return None
            assert result.returncode == 0 and result.stderr == "", result.stderr
            return json.loads(result.stdout)

        spec = (await admin_access.signed.client.get("/openapi.json")).json()["paths"]
        for suffix in ("locked-context", "evidence"):
            assert (
                "get"
                in spec[
                    f"/api/v1/audit/projects/{{project_id}}/tasks/{{task_id}}/{suffix}"
                ]
            )

        context = await call(auditor, "locked-context")
        direct = await admin_access.signed.client.get(
            f"/api/v1/audit/projects/{project}/tasks/{task}/locked-context",
            headers=auditor.headers,
        )
        assert direct.status_code == 200 and context == direct.json()
        assert context["project_id"] == str(project) and context["task_id"] == str(task)
        assert "locked_post_submit_checker_policy_body_summary" not in context

        page = await call(auditor, "evidence", project, task, "--limit", "1")
        assert page["project_id"] == str(project) and page["task_id"] == str(task)
        assert len(page["items"]) == 1 and page["next_cursor"] is not None
        cursor = json.dumps(page["next_cursor"], separators=(",", ":"))
        continued = await call(
            auditor, "evidence", project, task, "--limit", "1", "--cursor", cursor
        )
        direct_next = await admin_access.signed.client.get(
            f"/api/v1/audit/projects/{project}/tasks/{task}/evidence",
            headers=auditor.headers,
            params={"limit": 1, "cursor": cursor},
        )
        assert direct_next.status_code == 200 and continued == direct_next.json()
        assert continued["items"][0]["event_id"] != page["items"][0]["event_id"]

        empty = await call(auditor, "evidence", project, empty_task)
        assert empty == {
            "project_id": str(project),
            "task_id": str(empty_task),
            "items": [],
            "next_cursor": None,
        }
        for actor, scope in (
            (manager, project),
            (outsider, project),
            (foreign_auditor, project),
            (auditor, other),
        ):
            await call(actor, "locked-context", scope, task, status=404)
            await call(actor, "evidence", scope, task, status=404)

        revoked = await admin_access.signed.revoke(admin_access.admin, grant)
        assert revoked.status_code == 200, revoked.text
        await call(auditor, "locked-context", status=404)
        await call(
            auditor,
            "evidence",
            project,
            task,
            "--limit",
            "1",
            "--cursor",
            cursor,
            status=404,
        )
    finally:
        server.should_exit = True
        await asyncio.wait_for(serve, 30)
