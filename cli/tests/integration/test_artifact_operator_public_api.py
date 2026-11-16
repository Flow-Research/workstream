"""Built CLI through signed ART Operator API and real PostgreSQL custody.

The source job is made retry-eligible by a controlled provider-read failure in
the production artifact orchestrator. Authorization is never overridden.
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
from tests.authorization.admin_access.fixtures import signed_access as _signed_access
from tests.test_artifact_recovery import _context, _exhausted_job, _settings
from app.db import session as db_session
from scripts.bootstrap_access_administrator import _run as run_bootstrap


signed_access = pytest_asyncio.fixture(_signed_access.__wrapped__)


@pytest.mark.asyncio
async def test_signed_operator_cli_retry_exact_replay_and_revocation(
    tmp_path, cli, auth_database_env, signed_access
):
    admin = await signed_access.actor("cli-artifact-admin")
    operator = await signed_access.actor("cli-artifact-operator")
    outsider = await signed_access.actor("cli-artifact-outsider")
    code, bootstrap_result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap_result
    grant_id = await signed_access.grant(admin, operator)

    async with db_session.get_session_factory()() as session:
        project, task, submission, source, _, bootstrap = await _exhausted_job(
            session, _settings(tmp_path), tmp_path, _context()
        )
        source_id, source_cas = source.id, source.cas_version
        await session.rollback()

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(
            signed_access.client._transport.app,
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
                "artifact",
                *args,
                process_timeout=90,
            )
            if status is not None:
                assert process.returncode == 1 and process.stdout == "", process.stderr
                failure = json.loads(process.stderr)["error"]
                assert failure["status"] == status
                return failure
            assert process.returncode == 0 and process.stderr == "", process.stderr
            return json.loads(process.stdout)

        observed = await call(operator, "verification-job", source_id)
        assert observed["id"] == source_id
        assert observed["cas_version"] == source_cas
        assert observed["status"] == "provider_unavailable"
        receipt_path = (
            f"/api/v1/operator/artifacts/replicas/{observed['replica_id']}/receipts"
        )
        signed_receipts = await signed_access.client.get(
            receipt_path, headers=operator.headers
        )
        assert signed_receipts.status_code == 200, signed_receipts.text
        signed_receipt_page = signed_receipts.json()
        assert "next_cursor" not in signed_receipt_page
        receipt_page = await call(operator, "receipts", observed["replica_id"])
        assert receipt_page == signed_receipt_page
        assert receipt_page["items"]
        await call(outsider, "verification-job", source_id, status=404)

        reason = "Provider-read failure investigated; explicitly retry source"
        key = str(uuid4())
        args = (
            "retry",
            source_id,
            "--project-id",
            project,
            "--task-id",
            task,
            "--submission-id",
            submission,
            "--reason",
            reason,
            "--idempotency-key",
            key,
            "--expected-source-job-cas-version",
            str(source_cas),
        )
        wrong_binding = list(args)
        wrong_binding[wrong_binding.index(project)] = str(uuid4())
        wrong_binding[wrong_binding.index(key)] = str(uuid4())
        await call(operator, *wrong_binding, status=409)

        created = await call(operator, *args)
        assert created["source_verification_job_id"] == source_id
        assert created["replayed"] is False
        assert created["recovery_attempt_id"] != key
        assert created["retry_verification_job_id"] != source_id
        assert created["recovery_attempt_id"] not in {
            source_id,
            created["retry_verification_job_id"],
        }
        recovery = await call(
            operator, "recovery-attempt", created["recovery_attempt_id"]
        )
        assert recovery["source_verification_job_id"] == source_id
        assert (
            recovery["retry_verification_job_id"]
            == created["retry_verification_job_id"]
        )
        replay = await call(operator, *args)
        assert replay == created | {"replayed": True}

        revoked = await signed_access.revoke(admin, grant_id)
        assert revoked.status_code == 200, revoked.text
        await call(operator, "verification-job", source_id, status=404)
        await call(operator, *args, status=404)
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(running, timeout=20)
        finally:
            listener.close()
            bootstrap.close()
