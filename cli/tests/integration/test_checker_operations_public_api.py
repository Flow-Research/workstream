"""Built CLI through signed public API and PostgreSQL Operator authority.

The existing worker fixture produces one real terminal infrastructure failure;
the CLI itself performs the tested registry and recovery requests. This is not
an external OCI runtime/S3 proof or a public setup-to-Submission journey.
"""

import asyncio
import json
import socket
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
import uvicorn

from test_public_self_service import (
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
)
from tests.conftest import (
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
from tests.authorization.admin_access.support import create_project
from tests.checkers.external.support import registry_spec
from tests.checkers.execution.test_checker_retry import _failed_source
from app.modules.checkers.api.external import external_checker_json_hash
from app.modules.checkers.models import (
    CheckerRetryReceipt,
    ExternalCheckerRegistryEntryRecord,
)

signed_access = pytest_asyncio.fixture(_signed_access.__wrapped__)
admin_access = pytest_asyncio.fixture(_admin_access.__wrapped__)


@pytest.mark.asyncio
async def test_operator_registry_and_exact_terminal_retry_through_real_api(
    tmp_path,
    monkeypatch,
    cli,
    auth_database_env,
    admin_access,
):
    signed = admin_access.signed
    operator_grant = await signed.grant(admin_access.admin, admin_access.target)
    outsider = await signed.actor("cli-checker-outsider")
    payload = registry_spec().model_dump(mode="json")
    payload["capability_version"] = "v1.2.4"
    input_file = tmp_path / "checker.json"
    input_file.write_text(json.dumps(payload, ensure_ascii=False))
    key = str(uuid4())

    async with _failed_source(tmp_path, auth_database_env, monkeypatch) as (
        h,
        _delivery,
    ):
        project = str(h.request.project_id)
        run = str(h.created.evaluation_attempt_id)
        foreign = str(await create_project("Foreign CLI checker recovery"))
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
                    "checker",
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

            registered = await call(
                admin_access.target,
                "registry",
                "register",
                "--input",
                str(input_file),
                "--idempotency-key",
                key,
            )
            assert registered["registry_entry_id"] != key
            assert registered["registration_operation_id"] == key
            assert registered["phase"] == "pre_submit"
            assert (
                registered["input_schema"]["schema_sha256"]
                == payload["input_schema"]["schema_sha256"]
            )
            assert (
                await call(
                    admin_access.target,
                    "registry",
                    "read",
                    registered["registry_entry_id"],
                )
                == registered
            )
            assert (
                await call(
                    admin_access.target,
                    "registry",
                    "register",
                    "--input",
                    str(input_file),
                    "--idempotency-key",
                    key,
                )
                == registered
            )
            await call(
                outsider,
                "registry",
                "read",
                registered["registry_entry_id"],
                status=404,
            )

            numeric_payload = registry_spec().model_dump(mode="json")
            numeric_payload["capability_version"] = "v1.2.5"
            document = numeric_payload["configuration_schema"]["document"]
            document["examples"] = [9007199254740993, -0.0, 1e20]
            numeric_payload["configuration_schema"]["schema_sha256"] = (
                external_checker_json_hash(document)
            )
            numeric_file = tmp_path / "numeric-checker.json"
            numeric_file.write_text(json.dumps(numeric_payload))
            numeric_key = str(uuid4())
            numeric_entry = await call(
                admin_access.target,
                "registry",
                "register",
                "--input",
                str(numeric_file),
                "--idempotency-key",
                numeric_key,
            )
            assert (
                numeric_entry["configuration_schema"]["document"]["examples"]
                == document["examples"]
            )
            assert (
                await call(
                    admin_access.target,
                    "registry",
                    "read",
                    numeric_entry["registry_entry_id"],
                )
                == numeric_entry
            )
            assert (
                await call(
                    admin_access.target,
                    "registry",
                    "register",
                    "--input",
                    str(numeric_file),
                    "--idempotency-key",
                    numeric_key,
                )
                == numeric_entry
            )

            page = await call(
                admin_access.target, "retry-sources", project, "--limit", "1"
            )
            assert page["project_id"] == project and len(page["items"]) == 1
            assert page["items"][0]["source"]["source_run_id"] == run
            assert page["items"][0]["recovery_state"] == "eligible"
            await call(outsider, "retry-sources", project, status=404)
            foreign_page = await call(admin_access.target, "retry-sources", foreign)
            assert foreign_page == {
                "project_id": foreign,
                "items": [],
                "next_cursor": None,
            }
            await call(
                admin_access.target,
                "retry",
                foreign,
                run,
                "--reason",
                "Wrong project",
                "--idempotency-key",
                str(uuid4()),
                status=404,
            )
            reason = "Verified artifact storage has been restored"
            retry_key = str(uuid4())
            receipt = await call(
                admin_access.target,
                "retry",
                project,
                run,
                "--reason",
                reason,
                "--idempotency-key",
                retry_key,
            )
            assert receipt["source"] == page["items"][0]["source"]
            assert receipt["successor"]["run_id"] != run
            assert (
                await call(
                    admin_access.target,
                    "retry",
                    project,
                    run,
                    "--reason",
                    reason,
                    "--idempotency-key",
                    retry_key,
                )
                == receipt
            )
            await call(
                admin_access.target,
                "retry",
                project,
                run,
                "--reason",
                "Different repair assertion",
                "--idempotency-key",
                retry_key,
                status=409,
            )
            await call(
                admin_access.target,
                "retry",
                project,
                run,
                "--reason",
                reason,
                "--idempotency-key",
                str(uuid4()),
                status=404,
            )
            after = await call(admin_access.target, "retry-sources", project)
            assert after["items"][0]["recovery_state"] == "retried"
            assert after["items"][0]["retry_receipt_id"] == receipt["receipt_id"]
            async with h.factory() as session:
                assert (
                    await session.scalar(
                        select(func.count()).select_from(CheckerRetryReceipt)
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count()).select_from(
                            ExternalCheckerRegistryEntryRecord
                        )
                    )
                    == 4  # Two locked fixture images and two CLI registrations.
                )

            revoked = await signed.revoke(admin_access.admin, operator_grant)
            assert revoked.status_code == 200, revoked.text
            await call(admin_access.target, "retry-sources", project, status=404)
            await call(
                admin_access.target,
                "registry",
                "read",
                registered["registry_entry_id"],
                status=404,
            )
            await call(
                admin_access.target,
                "registry",
                "register",
                "--input",
                str(input_file),
                "--idempotency-key",
                key,
                status=403,
            )
            await call(
                admin_access.target,
                "retry",
                project,
                run,
                "--reason",
                reason,
                "--idempotency-key",
                retry_key,
                status=404,
            )
        finally:
            server.should_exit = True
            try:
                await asyncio.wait_for(running, timeout=20)
            finally:
                listener.close()
