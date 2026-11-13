"""Real CLI/socket/Flow/PREP/PostgreSQL reads of canonical retained evidence.

The existing authorized source fixture arranges the acceptance; this does not
claim a public submission/acceptance journey. No API or AUTH dependency is mocked.
Only the fixture issuer's JWKS transport is local.
"""

import asyncio
import json
import socket
from uuid import uuid4

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
    signed_access as _signed_access,
    admin_access as _admin_access,
    live_acceptance_lifecycle as _live_acceptance_lifecycle,
)
from tests.conftest import (
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.authorization.admin_access.support import create_project
from tests.contributions.exports.support import source_actor, export_path
from tests.contributions.records.support import authorized_submitter_source, rows

# The CLI pytest root uses strict asyncio mode; the backend fixtures are
# authored for its auto-mode root. Keep their actual bodies and dependencies.
signed_access = pytest_asyncio.fixture(_signed_access.__wrapped__)
admin_access = pytest_asyncio.fixture(_admin_access.__wrapped__)
live_acceptance_lifecycle = pytest_asyncio.fixture(
    _live_acceptance_lifecycle.__wrapped__
)


@pytest.mark.asyncio
async def test_contribution_evidence_real_socket_exact_export_and_fresh_authority(
    tmp_path,
    cli,
    auth_database_env,
    admin_access,
    live_acceptance_lifecycle,
):
    signed = admin_access.signed
    async with authorized_submitter_source(
        tmp_path,
        auth_database_env,
        contribution_awards=("money",),
    ) as h:
        owner = await source_actor(signed, h)
        project = h.submitter_record.project_id
        foreign = await create_project("Foreign contribution export")
        manager = await signed.actor("cli-evidence-manager")
        finance = await signed.actor("cli-evidence-finance")
        stranger = await signed.actor("cli-evidence-stranger")
        await signed.grant(
            admin_access.admin, manager, role="project_manager", project_id=project
        )
        finance_grant = await signed.grant(
            admin_access.admin, finance, role="finance_authority", project_id=project
        )
        tables = ("contribution_records", "compensation_awards", "final_acceptances")
        async with h.factory() as session:
            before = {table: await rows(session, table) for table in tables}

        # Reuse the actual app/verifier that admitted the fixture's signed actors.
        # A real bound socket removes free-port races; the CLI is a subprocess.
        app = signed.client._transport.app
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

            async def call(actor, *args, status=None):
                result = await asyncio.to_thread(
                    cli, origin, actor.token, "-o", "json", *args
                )
                if status is not None:
                    assert result.returncode == 1 and result.stdout == "", result.stderr
                    assert json.loads(result.stderr)["error"]["status"] == status
                    return None
                assert result.returncode == 0 and result.stderr == "", result.stderr
                return json.loads(result.stdout)

            spec = (await signed.client.get("/openapi.json")).json()["paths"]
            assert "get" in spec["/api/v1/actors/me/contributions"]
            assert "get" in spec["/api/v1/projects/{project_id}/contributions/export"]
            own = await call(
                owner, "contributions", "--project", str(project).replace("-", "")
            )
            direct = await signed.client.get(
                "/api/v1/actors/me/contributions", headers=owner.headers
            )
            assert direct.status_code == 200 and own["items"] == direct.json()["items"]
            (item,) = own["items"]
            assert item["contribution_id"] == str(h.submitter_record.id)
            assert item["source_final_acceptance_id"] == str(h.acceptance.id)
            assert {award["instrument"] for award in item["awards"]} == {"money"}
            empty = await call(stranger, "contributions")
            assert empty["items"] == []
            excluded = await call(
                owner, "contributions", "--recorded-before", item["recorded_at"]
            )
            assert excluded["items"] == []
            for actor in (manager, finance):
                exported = await call(
                    actor, "project", "contributions", str(project).replace("-", "")
                )
                assert exported["items"] == own["items"]
            for actor, args in (
                (owner, ("contributions",)),
                (finance, ("project", "contributions", str(project))),
            ):
                output = tmp_path / f"{actor.id}.csv"
                await call(actor, *args, "--csv", str(output))
                path = (
                    "/api/v1/actors/me/contributions"
                    if actor == owner
                    else export_path(project)
                )
                direct_csv = await signed.client.get(
                    path, headers=actor.headers, params={"format": "csv"}
                )
                assert (
                    direct_csv.status_code == 200
                    and output.read_bytes() == direct_csv.content
                )
                assert output.stat().st_mode & 0o777 == 0o600
            await call(stranger, "project", "contributions", str(project), status=404)
            await call(finance, "project", "contributions", str(foreign), status=404)
            revoked = await signed.revoke(admin_access.admin, finance_grant)
            assert revoked.status_code == 200, revoked.text
            await call(finance, "project", "contributions", str(project), status=404)
            suspended = await signed.client.post(
                f"/api/v1/actors/{owner.id}/suspend",
                headers=admin_access.admin.headers | {"Idempotency-Key": str(uuid4())},
                json={"reason": "Prove CLI evidence rechecks actor lifecycle"},
            )
            assert suspended.status_code == 200, suspended.text
            await call(owner, "contributions", status=404)
            async with h.factory() as session:
                assert {table: await rows(session, table) for table in tables} == before
        finally:
            server.should_exit = True
            try:
                await asyncio.wait_for(serve, timeout=15)
            finally:
                sock.close()
