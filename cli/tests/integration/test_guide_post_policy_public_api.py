"""Real Flow/socket/worker/SQL observation, not queued delivery or live inference."""

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
from tests.projects.guide_activation.source_fixtures import source_case  # noqa: E402
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor  # noqa: E402


@pytest.mark.asyncio
async def test_post_policy_public_socket_history_and_fresh_authority(
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
            str(actor.actor_profile_id), [], issuer=issuer, audience=audience, secret=secret
        )

    # Canonical retained source/compilation prerequisites, not a provider-inference claim.
    async with source_case(clean_postgres_database) as (_, factory, command, actor, grant):
        outsider, _ = await seed_review_actor(factory, None, role="audit_authority", scope="system")
        creator, _ = await seed_review_actor(factory, None, role="project_manager", scope="system")
        administrator, _ = await seed_review_actor(
            factory, None, role="access_administrator", scope="system"
        )
        origin = f"http://127.0.0.1:{find_free_port()}"
        log = (tmp_path / "post-policy-api.log").open("wb")
        process = subprocess.Popen(  # noqa: S603 - fixed owned production API
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
                str(x) for x in (command.project_id, command.guide_id, command.compilation_id)
            )
            caller = token(actor)
            headers = {"Authorization": "Bearer " + caller}
            admin = {"Authorization": "Bearer " + token(administrator)}
            prefix = "/api/v1/projects/{}/guides/{}/compilations/{}".format(*selectors)

            def read(policy, *, presented=caller, target=selectors):
                return cli(
                    origin,
                    presented,
                    "-o",
                    "json",
                    "project",
                    "guide",
                    "post-policy",
                    *target,
                    policy,
                )

            def success(result):
                assert result.returncode == 0 and result.stderr == "", result.stderr
                return json.loads(result.stdout)

            def denied(result, statuses=(404,)):
                assert result.returncode == 1 and result.stdout == "", result.stderr
                error = json.loads(result.stderr)["error"]
                assert error["status"] in statuses and not error.get("outcome_unknown", False)

            async def unchanged(expected_operations):
                async with factory() as session:
                    assert (
                        await session.scalar(
                            text("SELECT count(*) FROM project_post_policy_operations")
                        )
                        == expected_operations
                    )
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM project_guides WHERE activation_operation_id IS NOT NULL"
                            )
                        )
                        == 0
                    )

            async with httpx.AsyncClient(base_url=origin, trust_env=False, timeout=20) as direct:
                spec = (await direct.get("/openapi.json", timeout=60)).json()
                route = "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/post-submission-policies/{policy_id}"
                assert (
                    spec["paths"][route]["get"]["x-workstream-action-id"]
                    == "project.guide_compilation.review_package.read"
                )
                proposal = await direct.get(prefix + "/proposal", headers=headers)
                assert proposal.status_code == 200, proposal.text
                proposal = proposal.json()
                approved = await direct.post(
                    prefix + "/pre-submission-approval",
                    headers=headers | {"Idempotency-Key": str(uuid4())},
                    json={
                        "target": proposal["target"],
                        "acknowledged_warning_hashes": proposal["warning_hashes"],
                    },
                )
                assert approved.status_code == 200, approved.text
                approval_id = approved.json()["operation_id"]
                # Explicit execution of the canonical task/identity. Memory publication
                # is not delivered between processes and no queued-delivery claim is made.
                worker = await asyncio.to_thread(
                    subprocess.run,  # noqa: S603 - fixed actual worker entrypoint
                    [
                        sys.executable,
                        "-c",
                        "from uuid import UUID; import json,sys; from app.workers.post_policy import derive_post_policy; from app.modules.projects.api.post_policy import post_policy_task_id; print(json.dumps(derive_post_policy.apply(args=(sys.argv[1],), task_id=str(post_policy_task_id(UUID(sys.argv[1]))), throw=True).get()))",
                        approval_id,
                    ],
                    cwd=BACKEND,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                assert worker.returncode == 0, worker.stderr
                assert json.loads(worker.stdout)["status"] == "policy_draft_ready", worker.stdout
                discovery = await direct.get(prefix + "/proposal", headers=headers)
                assert discovery.status_code == 200, discovery.text
                policy_id = discovery.json()["post_submit_policy_id"]
                assert policy_id is not None
                path = prefix + "/post-submission-policies/" + policy_id
                response = await direct.get(path, headers=headers)
                assert response.status_code == 200, response.text
                compiled = success(read(policy_id))
                assert compiled == response.json()
                assert compiled["lifecycle_status"] == "compiled" and compiled["current"] is True
                assert compiled["approval_operation_id"] is None and compiled["correction"] is None
                assert compiled["target"]["upstream"] == approved.json()
                assert (
                    success(
                        read(
                            policy_id.replace("-", ""),
                            target=tuple(x.replace("-", "") for x in selectors),
                        )
                    )
                    == compiled
                )
                async with factory() as session:
                    row = (
                        (
                            await session.execute(
                                text(
                                    "SELECT policy_body,policy_hash FROM checker_policies WHERE id=:id"
                                ),
                                {"id": policy_id},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    assert (
                        row["policy_body"] == compiled["policy"]
                        and row["policy_hash"] == compiled["target"]["policy_hash"]
                    )
                await unchanged(1)
                approval = await direct.post(
                    path + "/approval",
                    headers=headers | {"Idempotency-Key": str(uuid4())},
                    json={"target": compiled["target"]},
                )
                assert approval.status_code == 200, approval.text
                observed = success(read(policy_id))
                assert observed["lifecycle_status"] == "approved"
                assert observed["approval_operation_id"] == approval.json()["operation_id"]
                assert (
                    observed["activation_context"]["post_approval_operation_id"]
                    == observed["approval_operation_id"]
                )
                # Missing activation selections must not turn an authorized read into readiness logic.
                assert observed["activation_context"]["review"] is None
                await unchanged(2)
                correction = await direct.post(
                    path + "/corrections",
                    headers=headers | {"Idempotency-Key": str(uuid4())},
                    json={
                        "target": observed["target"],
                        "reason": "Clarify the evaluation evidence required from contributors.",
                    },
                )
                assert correction.status_code == 201, correction.text
                historical = success(read(policy_id))
                assert (
                    historical["lifecycle_status"] == "superseded"
                    and historical["current"] is False
                )
                assert historical["correction"] == correction.json()["correction"]
                assert historical == (await direct.get(path, headers=headers)).json()
                latest = await direct.get(
                    f"/api/v1/projects/{selectors[0]}/guides/{selectors[1]}/setup-runs/latest",
                    headers=headers,
                )
                assert latest.status_code == 200, latest.text
                assert latest.json()["id"] == historical["correction"]["successor_setup_run_id"]
                assert (
                    latest.json()["setup_generation"]
                    == historical["correction"]["successor_setup_generation"]
                )
                await unchanged(3)
                denied(read(policy_id, presented=token(outsider)))
                denied(read(policy_id, presented="not-issued"), (401,))
                assert (await direct.get(path)).status_code == 401
                denied(read(str(uuid4())))
                denied(read(policy_id, target=(selectors[0], selectors[1], str(uuid4()))))
                foreign = await direct.post(
                    "/api/v1/projects",
                    headers={
                        "Authorization": "Bearer " + token(creator),
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={
                        "name": "Foreign post-policy project",
                        "slug": "foreign-post-policy-" + uuid4().hex,
                    },
                )
                assert foreign.status_code == 201, foreign.text
                denied(read(policy_id, target=(foreign.json()["id"], *selectors[1:])))
                assert success(read(policy_id)) == historical
                suspended = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/suspend",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Policy read suspension proof"},
                )
                assert suspended.status_code == 200, suspended.text
                denied(read(policy_id), (403, 404))
                restored = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/reactivate",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Restore policy manager"},
                )
                assert restored.status_code == 200, restored.text
                assert success(read(policy_id)) == historical
                revoked = await direct.post(
                    f"/api/v1/admin-role-grants/{grant}/revoke",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Policy read revoked grant proof"},
                )
                assert revoked.status_code == 200, revoked.text
                denied(read(policy_id))
                await unchanged(3)
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
            log.close()
