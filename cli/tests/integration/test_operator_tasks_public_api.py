"""Focused real Flow/PostgreSQL proof of Operator task CLI authority."""

import asyncio
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest

from test_public_self_service import _ready
from operator_task_journey import exercise_operator_task_journey

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
from app.core.identifiers import new_record_id  # noqa: E402
from tests.conftest import (  # noqa: E402
    configured_source_instance_id as configured_source_instance_id,
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
)
from tests.project_create_fixtures import seed_historical_project  # noqa: E402
from tests.projects.guide_activation.pg_support import activation_case  # noqa: E402
from tests.authorization.guide_activation.pg_support import activate  # noqa: E402
from tests.projects.guide_compilation.proposals.pg_support import (  # noqa: E402
    seed_review_actor,
)


@pytest.mark.asyncio
async def test_operator_task_cli_public_socket_and_fresh_authority(
    clean_postgres_database, tmp_path, cli
):
    env = api_environment()
    env["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env["WORKSTREAM_FLOW_AUTH_ISSUER"] = env["WORKSTREAM_E2E_FLOW_ISSUER"]
    assert env["WORKSTREAM_DATABASE_URL"] == clean_postgres_database
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    issuer, audience, secret = flow_settings(env)

    def token(subject):
        return issue_flow_token(
            str(subject), [], issuer=issuer, audience=audience, secret=secret
        )

    # Reuse canonical guide activation; only task and grant actions below use
    # the public API. No hidden task or assignment rows are manufactured.
    async with activation_case(clean_postgres_database) as (
        factory,
        command,
        manager,
        *_rest,
    ):
        await activate(factory, manager, command)
        project = str(command.target.proposal.project_id)
        administrator, _ = await seed_review_actor(
            factory, None, role="access_administrator", scope="system"
        )
        foreign_project = str(new_record_id())
        async with factory() as session, session.begin():
            await seed_historical_project(
                session,
                project_id=foreign_project,
                name="Foreign Operator cursor control",
                slug="foreign-operator-" + uuid4().hex,
            )

        tokens = {
            "cli-admin": token(administrator.actor_profile_id),
            "cli-manager": token(manager.actor_profile_id),
            "cli-outsider": token("operator-task-contributor"),
        }
        origin = f"http://127.0.0.1:{find_free_port()}"
        log = (tmp_path / "operator-api.log").open("wb")
        api = subprocess.Popen(  # noqa: S603 - fixed local API fixture
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
            await _ready(origin + "/api/v1/health", api)
            async with httpx.AsyncClient(
                base_url=origin,
                trust_env=False,
                timeout=10,
                limits=httpx.Limits(max_keepalive_connections=0),
            ) as direct:
                manager_headers = {"Authorization": "Bearer " + tokens["cli-manager"]}
                contributor_headers = {
                    "Authorization": "Bearer " + tokens["cli-outsider"]
                }
                admitted = await direct.get(
                    "/api/v1/actors/me", headers=contributor_headers
                )
                assert admitted.status_code == 200, admitted.text
                contributor = admitted.json()["actor_profile_id"]
                granted = await direct.post(
                    f"/api/v1/projects/{project}/role-grants",
                    headers=manager_headers | {"Idempotency-Key": str(uuid4())},
                    json={
                        "target_actor_profile_id": contributor,
                        "role": "submitter",
                        "qualification": {
                            "skills_snapshot": {
                                "availability": "available",
                                "reference_ids": ["skill:operator-cli-proof"],
                                "unavailable_reason": None,
                            },
                            "reputation_snapshot": {
                                "availability": "unavailable",
                                "reference_ids": [],
                                "unavailable_reason": "no_record",
                            },
                            "prior_project_work_refs": [],
                            "external_expertise_refs": [],
                        },
                        "reason": "Prepare Operator task CLI public proof",
                    },
                )
                assert granted.status_code == 201, granted.text
                tasks = []
                for index in range(2):
                    created = await direct.post(
                        f"/api/v1/projects/{project}/tasks",
                        headers=manager_headers | {"Idempotency-Key": str(uuid4())},
                        json={
                            "title": f"Operator task {index}",
                            "description": "Inspect the assigned evidence.",
                            "task_type": "evaluation",
                            "difficulty": "medium",
                            "skill_tags": ["analysis"],
                            "estimated_time_minutes": 17,
                            "acceptance_criteria": "Evidence is complete.",
                            "rejection_criteria": "Evidence is missing.",
                        },
                    )
                    assert created.status_code == 201, created.text
                    task = created.json()["id"]
                    for action in ("screen", "release"):
                        transitioned = await direct.post(
                            f"/api/v1/tasks/{task}/{action}",
                            headers=manager_headers | {"Idempotency-Key": str(uuid4())},
                            json={"reason": "Prepare Operator task CLI public proof"},
                        )
                        assert transitioned.status_code in (200, 201), transitioned.text
                    tasks.append(task)
                claimed = await direct.post(
                    f"/api/v1/tasks/{tasks[0]}/claim",
                    headers=contributor_headers | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Assignment for Operator task CLI proof"},
                )
                assert claimed.status_code == 200, claimed.text
                assert claimed.json()["assignment"]["contributor_id"] == contributor
                await exercise_operator_task_journey(
                    direct,
                    cli,
                    origin,
                    tokens,
                    env,
                    project,
                    foreign_project,
                    tasks[0],
                    contributor,
                )
        finally:
            api.terminate()
            try:
                await asyncio.to_thread(api.wait, timeout=10)
            except subprocess.TimeoutExpired:
                api.kill()
                await asyncio.to_thread(api.wait, timeout=10)
            log.close()
