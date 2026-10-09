"""Actual socket, Flow-token verification, production AUTH and retained SQL proposal."""

import asyncio
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from test_public_self_service import _ready

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND / "tests"))

from api_contract_e2e import (  # noqa: E402
    api_environment,
    assert_isolated_database_url,
    find_free_port,
    flow_settings,
    issue_flow_token,
)
from tests.conftest import (  # noqa: E402
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.projects.guide_compilation.proposals.pg_support import (  # noqa: E402
    proposal_case,
    seed_review_actor,
)


@pytest.mark.asyncio
async def test_proposal_public_socket_parity_and_fresh_authority(
    clean_postgres_database, tmp_path, cli
):
    env = api_environment()
    env["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env["WORKSTREAM_FLOW_AUTH_ISSUER"] = env["WORKSTREAM_E2E_FLOW_ISSUER"]
    env["WORKSTREAM_CELERY_TASK_ALWAYS_EAGER"] = "false"
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    issuer, audience, secret = flow_settings(env)

    def token(actor):
        return issue_flow_token(
            str(actor.actor_profile_id),
            [],
            issuer=issuer,
            audience=audience,
            secret=secret,
        )

    # Canonical compilation/finalization arrangements are seeded test custody,
    # not a claim that this CLI executed inference or uploaded these originals.
    # All reads below traverse an actual socket and production AUTH, no overrides.
    async with proposal_case(clean_postgres_database) as (
        _,
        factory,
        command,
        actor,
        grant,
    ):
        outsider, _ = await seed_review_actor(
            factory, None, role="audit_authority", scope="system"
        )
        creator, _ = await seed_review_actor(
            factory, None, role="project_manager", scope="system"
        )
        administrator, _ = await seed_review_actor(
            factory, None, role="access_administrator", scope="system"
        )
        origin = f"http://127.0.0.1:{find_free_port()}"
        log = (tmp_path / "proposal-api.log").open("wb")
        process = subprocess.Popen(  # noqa: S603 - fixed real local API fixture
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                origin.rsplit(":", 1)[1],
                "--log-level",
                "error",
                "--no-access-log",
            ],
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            await _ready(origin + "/api/v1/health", process)
            selectors = tuple(
                str(x)
                for x in (command.project_id, command.guide_id, command.compilation_id)
            )
            caller = token(actor)
            admin = {"Authorization": "Bearer " + token(administrator)}
            path = "/api/v1/projects/{}/guides/{}/compilations/{}/proposal".format(
                *selectors
            )

            def inspect(*, presented=caller, target=selectors):
                return cli(
                    origin,
                    presented,
                    "-o",
                    "json",
                    "project",
                    "guide",
                    "proposal",
                    *target,
                )

            def success(result):
                assert result.returncode == 0 and result.stderr == "", result.stderr
                return json.loads(result.stdout)

            def denied(result, statuses=(404,)):
                assert result.returncode == 1 and result.stdout == "", result.stderr
                assert json.loads(result.stderr)["error"]["status"] in statuses

            async with httpx.AsyncClient(
                base_url=origin, trust_env=False, timeout=10
            ) as direct:
                specification = (await direct.get("/openapi.json", timeout=60)).json()
                operation = specification["paths"][
                    "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/proposal"
                ]["get"]
                assert (
                    operation["x-workstream-action-id"]
                    == "project.guide_compilation.review_package.read"
                )
                expected = await direct.get(
                    path, headers={"Authorization": "Bearer " + caller}
                )
                assert expected.status_code == 200, expected.text
                package = success(inspect())
                assert package == expected.json()
                assert package["target"]["compilation_id"] == str(
                    command.compilation_id
                )
                assert (
                    package["result"]["findings"][0]["evidence_refs"][0][
                        "document_number"
                    ]
                    == 1
                )
                assert (
                    success(
                        inspect(target=tuple(x.replace("-", "") for x in selectors))
                    )
                    == package
                )
                for private in (
                    "source_item_id",
                    "document_version_id",
                    "provider_idempotency_key",
                    "runtime_configuration",
                ):
                    assert private not in expected.text
                denied(inspect(presented=token(outsider)))
                assert (await direct.get(path)).status_code == 401
                denied(inspect(presented="not-issued"), (401,))

                foreign = await direct.post(
                    "/api/v1/projects",
                    headers={
                        "Authorization": "Bearer " + token(creator),
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={
                        "name": "Foreign proposal project",
                        "slug": "foreign-proposal-" + uuid4().hex,
                    },
                )
                assert foreign.status_code == 201, foreign.text
                denied(
                    inspect(target=(foreign.json()["id"], selectors[1], selectors[2]))
                )
                denied(inspect(target=(selectors[0], selectors[1], str(uuid4()))))

                # Fresh lifecycle authority is exercised through public mutations,
                # with a positive read immediately before each deny transition.
                assert success(inspect()) == package
                suspended = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/suspend",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "CLI proposal suspension regression"},
                )
                assert suspended.status_code == 200, suspended.text
                denied(inspect(), (403, 404))
                restored = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/reactivate",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Restore proposal reader"},
                )
                assert restored.status_code == 200, restored.text
                assert success(inspect()) == package
                revoked = await direct.post(
                    f"/api/v1/admin-role-grants/{grant}/revoke",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "CLI proposal grant regression"},
                )
                assert revoked.status_code == 200, revoked.text
                denied(inspect())

                async with factory() as session:
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM project_guide_proposal_approvals"
                            )
                        )
                        == 0
                    )
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM project_guide_proposal_corrections"
                            )
                        )
                        == 0
                    )
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
            log.close()
