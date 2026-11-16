"""Real public Flow/socket/PostgreSQL proof of draft-guide configuration."""

import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from guide_config_journey import exercise_guide_configuration
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
    configured_source_instance_id as configured_source_instance_id,
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.projects.guide_compilation.proposals.pg_support import (  # noqa: E402
    seed_review_actor,
)


@pytest.mark.asyncio
async def test_guide_configuration_public_socket_replay_and_fresh_authority(
    clean_postgres_database, tmp_path, cli
):
    env = api_environment()
    env["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env["WORKSTREAM_FLOW_AUTH_ISSUER"] = env["WORKSTREAM_E2E_FLOW_ISSUER"]
    env["WORKSTREAM_CELERY_TASK_ALWAYS_EAGER"] = "false"
    assert env["WORKSTREAM_CELERY_BROKER_URL"] == "memory://"
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

    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    manager, manager_grant = await seed_review_actor(
        factory, None, role="project_manager", scope="system"
    )
    outsider, _ = await seed_review_actor(
        factory, None, role="audit_authority", scope="system"
    )
    administrator, _ = await seed_review_actor(
        factory, None, role="access_administrator", scope="system"
    )
    tokens = {
        "cli-project-manager": token(manager),
        "cli-outsider": token(outsider),
    }
    origin = f"http://127.0.0.1:{find_free_port()}"
    # pytest's rotating tmp_path can disappear while another isolated runner
    # starts; retain a private startup log only when this journey fails.
    log = tempfile.NamedTemporaryFile(
        prefix="workstream-599-api-", suffix=".log", delete=False
    )
    completed = False
    process = subprocess.Popen(  # noqa: S603 - owned production API process
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
        try:
            await _ready(origin + "/api/v1/health", process)
        except AssertionError as exc:
            raise AssertionError(f"{exc}; API startup log: {log.name}") from exc
        async with httpx.AsyncClient(
            base_url=origin,
            trust_env=False,
            timeout=10,
            limits=httpx.Limits(max_keepalive_connections=0),
        ) as direct:
            manager_header = {
                "Authorization": "Bearer " + tokens["cli-project-manager"]
            }
            project = await direct.post(
                "/api/v1/projects",
                headers=manager_header | {"Idempotency-Key": str(uuid4())},
                json={
                    "name": "CLI policy configuration",
                    "slug": "cli-config-" + uuid4().hex,
                },
            )
            assert project.status_code == 201, project.text
            foreign = await direct.post(
                "/api/v1/projects",
                headers=manager_header | {"Idempotency-Key": str(uuid4())},
                json={
                    "name": "Foreign CLI policy target",
                    "slug": "cli-foreign-" + uuid4().hex,
                },
            )
            assert foreign.status_code == 201, foreign.text
            project_id = project.json()["id"]
            created = await direct.post(
                f"/api/v1/projects/{project_id}/guides",
                headers=manager_header | {"Idempotency-Key": str(uuid4())},
                json={
                    "version": "cli-config-" + uuid4().hex,
                    "task_examples": [{"content": "Review the evidence."}],
                    "documents": [{"label": "Guide.md", "media_type": "text/markdown"}],
                },
            )
            assert created.status_code == 201, created.text
            guide_id = created.json()["id"]
            configure, _, committed = await exercise_guide_configuration(
                direct,
                cli,
                origin,
                tokens,
                project_id,
                guide_id,
                foreign.json()["id"],
                tmp_path,
            )
            revoked = await direct.post(
                f"/api/v1/admin-role-grants/{manager_grant}/revoke",
                headers={
                    "Authorization": "Bearer " + token(administrator),
                    "Idempotency-Key": str(uuid4()),
                },
                json={"reason": "Prove fresh CLI configuration authority"},
            )
            assert revoked.status_code == 200, revoked.text
            observations = []
            for action, body, key, original_match, current_match in committed:
                for case, candidate_key, match in (
                    ("fresh", str(uuid4()), current_match),
                    ("exact_replay", key, original_match),
                ):
                    result = configure(action, body, candidate_key, match=match)
                    error = (
                        json.loads(result.stderr)["error"] if result.stderr else None
                    )
                    observations.append(
                        (action, case, result.returncode, error and error.get("status"))
                    )
            assert all(
                exit_code == 1 and status in (403, 404)
                for _, _, exit_code, status in observations
            ), observations
            # The public read also rechecks authority; no stored guide fact
            # grants this former manager continuing access.
            hidden = await direct.get(
                f"/api/v1/projects/{project_id}/guides/{guide_id}",
                headers=manager_header,
            )
            assert hidden.status_code in (403, 404)
            completed = True
    finally:
        process.terminate()
        try:
            await asyncio.to_thread(process.wait, timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            await asyncio.to_thread(process.wait, timeout=10)
        log.close()
        if completed:
            Path(log.name).unlink(missing_ok=True)
        await engine.dispose()
