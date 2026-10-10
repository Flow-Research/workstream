"""Real socket/Flow/PREP/SQL approval; no setup-provider or worker-delivery claim."""

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
from tests.projects.guide_compilation.helpers import result as compilation_result  # noqa: E402


@pytest.mark.asyncio
async def test_approval_public_socket_replay_and_fresh_authority(
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

    # Seed canonical retained compilation/finalization only. Every decision below
    # uses the public socket with production auth/compiler/persistence owners.
    outcome = compilation_result().model_dump(mode="json")
    outcome["status"] = "draft_ready_with_warnings"
    outcome["findings"][0]["severity"] = "warning"
    validated = type(compilation_result()).model_validate(outcome)
    async with proposal_case(
        clean_postgres_database,
        classification="draft_ready_with_warnings",
        outcome=validated,
    ) as (_, factory, command, actor, grant):
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
        log = (tmp_path / "approval-api.log").open("wb")
        process = subprocess.Popen(  # noqa: S603 - fixed local real API process
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
            prefix = "/api/v1/projects/{}/guides/{}/compilations/{}".format(*selectors)
            path = tmp_path / "approval.json"
            key = str(uuid4())
            admin = {"Authorization": "Bearer " + token(administrator)}

            def approve(*, presented=caller, target=selectors, replay_key=key):
                return cli(
                    origin,
                    presented,
                    "-o",
                    "json",
                    "project",
                    "guide",
                    "approve-pre",
                    *target,
                    "--input",
                    str(path),
                    "--idempotency-key",
                    replay_key,
                )

            def success(result):
                assert result.returncode == 0 and result.stderr == "", result.stderr
                return json.loads(result.stdout)

            def denied(result, statuses=(404,)):
                assert result.returncode == 1 and result.stdout == "", result.stderr
                error = json.loads(result.stderr)["error"]
                assert error["status"] in statuses and not error.get(
                    "outcome_unknown", False
                )

            async def stored(expected):
                async with factory() as session:
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM project_guide_proposal_approvals"
                            )
                        )
                        == expected
                    )
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM audit_events WHERE action_id='project.submission_artifact_policy.approve'"
                            )
                        )
                        == expected
                    )
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM project_guides WHERE activation_operation_id IS NOT NULL"
                            )
                        )
                        == 0
                    )

            async with httpx.AsyncClient(
                base_url=origin, trust_env=False, timeout=20
            ) as direct:
                spec = (await direct.get("/openapi.json", timeout=60)).json()
                route = "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/pre-submission-approval"
                operation = spec["paths"][route]["post"]
                assert (
                    operation["x-workstream-action-id"]
                    == "project.submission_artifact_policy.approve"
                )
                assert any(
                    p["name"] == "Idempotency-Key" and p["required"]
                    for p in operation["parameters"]
                )
                package_response = await direct.get(
                    prefix + "/proposal", headers={"Authorization": "Bearer " + caller}
                )
                assert package_response.status_code == 200, package_response.text
                package = package_response.json()
                assert len(package["warning_hashes"]) == 1
                body = {
                    "target": package["target"],
                    "acknowledged_warning_hashes": package["warning_hashes"],
                }
                for warnings in ([], ["sha256:" + "f" * 64]):
                    path.write_text(
                        json.dumps(body | {"acknowledged_warning_hashes": warnings}),
                        encoding="utf-8",
                    )
                    denied(approve(replay_key=str(uuid4())), (409,))
                    await stored(0)
                changed = body | {
                    "target": body["target"] | {"result_hash": "sha256:" + "f" * 64}
                }
                path.write_text(json.dumps(changed), encoding="utf-8")
                denied(approve(replay_key=str(uuid4())), (409,))
                await stored(0)
                path.write_text(json.dumps(body), encoding="utf-8")
                denied(approve(presented=token(outsider)))
                denied(approve(presented="not-issued"), (401,))
                unauthenticated = await direct.post(
                    prefix + "/pre-submission-approval",
                    headers={"Idempotency-Key": str(uuid4())},
                    json=body,
                )
                assert unauthenticated.status_code == 401, unauthenticated.text
                approved = success(approve())
                assert approved["target_digest"] == package["target_digest"]
                assert (
                    approved["artifact_policy_id"]
                    == package["target"]["artifact_policy_id"]
                )
                assert (
                    approved["acknowledged_warning_hashes"] == package["warning_hashes"]
                )
                assert (
                    success(
                        approve(target=tuple(x.replace("-", "") for x in selectors))
                    )
                    == approved
                )
                replay = await direct.post(
                    prefix + "/pre-submission-approval",
                    headers={
                        "Authorization": "Bearer " + caller,
                        "Idempotency-Key": key,
                    },
                    json=body,
                )
                assert replay.status_code == 200 and replay.json() == approved, (
                    replay.text
                )
                await stored(1)
                async with factory() as session:
                    row = (
                        (
                            await session.execute(
                                text(
                                    "SELECT receipt_json,actor_profile_id,admin_role_grant_id FROM project_guide_proposal_approvals"
                                )
                            )
                        )
                        .mappings()
                        .one()
                    )
                    assert row["receipt_json"] == approved and str(
                        row["actor_profile_id"]
                    ) == str(actor.actor_profile_id)
                    assert str(row["admin_role_grant_id"]) == str(grant)
                reread = await direct.get(
                    prefix + "/proposal", headers={"Authorization": "Bearer " + caller}
                )
                assert (
                    reread.status_code == 200
                    and reread.json()["post_submit_policy_id"] is None
                )

                foreign = await direct.post(
                    "/api/v1/projects",
                    headers={
                        "Authorization": "Bearer " + token(creator),
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={
                        "name": "Foreign approval project",
                        "slug": "foreign-approval-" + uuid4().hex,
                    },
                )
                assert foreign.status_code == 201, foreign.text
                foreign_id = foreign.json()["id"]
                path.write_text(
                    json.dumps(
                        body | {"target": body["target"] | {"project_id": foreign_id}}
                    ),
                    encoding="utf-8",
                )
                denied(
                    approve(
                        target=(foreign_id, selectors[1], selectors[2]),
                        replay_key=str(uuid4()),
                    )
                )
                path.write_text(json.dumps(body), encoding="utf-8")
                assert success(approve()) == approved
                suspended = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/suspend",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Approval replay suspension proof"},
                )
                assert suspended.status_code == 200, suspended.text
                denied(approve(), (403, 404))
                restored = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/reactivate",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Restore approval manager"},
                )
                assert restored.status_code == 200, restored.text
                assert success(approve()) == approved
                revoked = await direct.post(
                    f"/api/v1/admin-role-grants/{grant}/revoke",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Approval replay revoked grant proof"},
                )
                assert revoked.status_code == 200, revoked.text
                denied(approve())
                await stored(1)
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
            log.close()
