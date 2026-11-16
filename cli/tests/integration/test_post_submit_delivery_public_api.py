"""Built CLI against signed public API and owner-produced UNKNOWN PostgreSQL facts.

This proves API exposure and exact CLI consumption, not a hosted interruption,
S3 custody, or an end-to-end checker runtime delivery.
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
from tests.conftest import (
    configured_source_instance_id as configured_source_instance_id,
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    signed_access as _signed_access,
    admin_access as _admin_access,
)
from tests.post_submit_materialization_helpers import material_fixture
from tests.tasks.evaluation_delivery.support import delivery_fixture, invoked
from app.modules.outbox.api import FinalizationCause

signed_access = pytest_asyncio.fixture(_signed_access.__wrapped__)
admin_access = pytest_asyncio.fixture(_admin_access.__wrapped__)


@pytest.mark.asyncio
async def test_delivery_discovery_reconciliation_replay_and_revocation_real_api(
    tmp_path,
    cli,
    auth_database_env,
    admin_access,
):
    signed = admin_access.signed
    grant_id = await signed.grant(admin_access.admin, admin_access.target)
    outsider = await signed.actor("cli-delivery-outsider")

    async with material_fixture(tmp_path, auth_database_env) as material:
        prepared = await delivery_fixture(material)
        original = await invoked(material, prepared)
        await prepared.delivery.finalize(original.claim, FinalizationCause.UNKNOWN)
        project = str(material.request.project_id)
        event = str(original.claim.event_id)
        key = str(uuid4())

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(
            uvicorn.Config(
                signed.client._transport.app,
                lifespan="off",
                log_level="error",
                access_log=False,
            )
        )
        running = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(30):
                while not server.started:
                    assert not running.done(), "real API exited"
                    await asyncio.sleep(0.01)

            async def call(actor, *args, status=None):
                process = await asyncio.to_thread(
                    cli,
                    origin,
                    actor.token,
                    "-o",
                    "json",
                    "operations",
                    "delivery",
                    *args,
                    process_timeout=90,
                )
                if status is not None:
                    assert process.returncode == 1 and process.stdout == "", (
                        process.stderr
                    )
                    assert json.loads(process.stderr)["error"]["status"] == status
                    return None
                assert process.returncode == 0 and process.stderr == "", process.stderr
                return json.loads(process.stdout)

            page = await call(admin_access.target, "list", project, "--limit", "1")
            assert page["project_id"] == project and page["next_cursor"] is None
            assert len(page["items"]) == 1
            assert page["items"][0]["event_id"] == event
            assert page["items"][0]["classification"] == "retry_safe"
            await call(outsider, "list", project, status=404)

            command = (
                "reconcile",
                project,
                event,
                "--reason",
                "Exact UNKNOWN source check",
                "--idempotency-key",
                key,
            )
            created = await call(admin_access.target, *command)
            child = created["successor"]["event_id"]
            assert child != event
            assert created["source"]["event_id"] == event
            assert created["source"]["reconciliation_event_id"] == child
            assert created["successor"]["classification"] == "retry_safe"
            replay = await call(admin_access.target, *command)
            assert replay["successor"] == created["successor"]
            await call(
                admin_access.target,
                "reconcile",
                project,
                event,
                "--reason",
                "Different reason",
                "--idempotency-key",
                key,
                status=409,
            )
            await call(outsider, *command, status=404)

            revoked = await signed.revoke(
                admin_access.admin,
                grant_id,
                reason="End delivery reconciliation duty",
            )
            assert revoked.status_code == 200, revoked.text
            await call(admin_access.target, "list", project, status=404)
            await call(admin_access.target, *command, status=404)
        finally:
            server.should_exit = True
            await running
