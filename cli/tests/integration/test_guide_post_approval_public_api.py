"""Actual socket/Flow/PREP/SQL decisions, exact replay and fresh authority."""

import asyncio
from copy import deepcopy
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
from app.core.hashing import canonical_json_hash  # noqa: E402
from app.modules.projects.api.post_policy import PostPolicyTarget  # noqa: E402


@pytest.mark.asyncio
async def test_post_approval_public_socket_replay_and_fresh_authority(
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

    # Retained prerequisites use canonical owner fixtures, not live setup inference.
    async with source_case(clean_postgres_database) as (
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
        log = (tmp_path / "post-approval-api.log").open("wb")
        process = subprocess.Popen(  # noqa: S603 - owned production API
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
            headers = {"Authorization": "Bearer " + caller}
            admin = {"Authorization": "Bearer " + token(administrator)}
            prefix = "/api/v1/projects/{}/guides/{}/compilations/{}".format(*selectors)
            path = tmp_path / "post-approval.json"
            key = str(uuid4())

            def approve(
                policy, *, presented=caller, selected=selectors, replay_key=key
            ):
                return cli(
                    origin,
                    presented,
                    "-o",
                    "json",
                    "project",
                    "guide",
                    "approve-post",
                    *selected,
                    policy,
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

            async def stored(expected, policy_id, original):
                async with factory() as session:
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM project_post_policy_operations WHERE kind='approve'"
                            )
                        )
                        == expected
                    )
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM audit_events WHERE action_id='project.post_submit_checker_policy.approve'"
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
                        row["policy_body"] == original["policy"]
                        and row["policy_hash"] == original["target"]["policy_hash"]
                    )

            async with httpx.AsyncClient(
                base_url=origin, trust_env=False, timeout=20
            ) as direct:
                spec = (await direct.get("/openapi.json", timeout=60)).json()
                route = "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/post-submission-policies/{policy_id}/approval"
                operation = spec["paths"][route]["post"]
                assert (
                    operation["x-workstream-action-id"]
                    == "project.post_submit_checker_policy.approve"
                )
                assert any(
                    p["name"] == "Idempotency-Key" and p["required"]
                    for p in operation["parameters"]
                )
                response = await direct.get(prefix + "/proposal", headers=headers)
                assert response.status_code == 200, response.text
                proposal = response.json()
                upstream = await direct.post(
                    prefix + "/pre-submission-approval",
                    headers=headers | {"Idempotency-Key": str(uuid4())},
                    json={
                        "target": proposal["target"],
                        "acknowledged_warning_hashes": proposal["warning_hashes"],
                    },
                )
                assert upstream.status_code == 200, upstream.text
                # Apply the real canonical task explicitly; no queued delivery claim.
                worker = await asyncio.to_thread(
                    subprocess.run,  # noqa: S603 - fixed worker entrypoint
                    [
                        sys.executable,
                        "-c",
                        "from uuid import UUID; import json,sys; from app.workers.post_policy import derive_post_policy; from app.modules.projects.api.post_policy import post_policy_task_id; print(json.dumps(derive_post_policy.apply(args=(sys.argv[1],), task_id=str(post_policy_task_id(UUID(sys.argv[1]))), throw=True).get()))",
                        upstream.json()["operation_id"],
                    ],
                    cwd=BACKEND,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                assert worker.returncode == 0, worker.stderr
                assert json.loads(worker.stdout)["status"] == "policy_draft_ready"
                response = await direct.get(prefix + "/proposal", headers=headers)
                assert response.status_code == 200, response.text
                policy_id = response.json()["post_submit_policy_id"]
                assert policy_id is not None
                policy_path = prefix + "/post-submission-policies/" + policy_id
                response = await direct.get(policy_path, headers=headers)
                assert response.status_code == 200, response.text
                original = response.json()
                body = {"target": original["target"]}
                path.write_text(json.dumps(body), encoding="utf-8")
                denied(approve(policy_id, presented=token(outsider)))
                denied(approve(policy_id, presented="not-issued"), (401,))
                response = await direct.post(
                    policy_path + "/approval",
                    headers={"Idempotency-Key": key},
                    json=body,
                )
                assert response.status_code == 401, response.text
                changed = deepcopy(body)
                changed["target"]["policy_hash"] = "sha256:" + "f" * 64
                path.write_text(json.dumps(changed), encoding="utf-8")
                denied(approve(policy_id, replay_key=str(uuid4())), (409,))
                await stored(0, policy_id, original)
                path.write_text(json.dumps(body), encoding="utf-8")
                approved = success(approve(policy_id))
                assert approved["kind"] == "approve" and approved["correction"] is None
                assert approved["target"] == original["target"]
                assert (
                    success(
                        approve(
                            policy_id.replace("-", ""),
                            selected=tuple(x.replace("-", "") for x in selectors),
                        )
                    )
                    == approved
                )
                response = await direct.post(
                    policy_path + "/approval",
                    headers=headers | {"Idempotency-Key": key},
                    json=body,
                )
                assert response.status_code == 200 and response.json() == approved, (
                    response.text
                )
                await stored(1, policy_id, original)
                async with factory() as session:
                    row = (
                        (
                            await session.execute(
                                text(
                                    "SELECT receipt_json,actor_profile_id,admin_role_grant_id FROM project_post_policy_operations WHERE kind='approve'"
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
                response = await direct.get(policy_path, headers=headers)
                assert response.status_code == 200, response.text
                assert response.json()["lifecycle_status"] == "approved"
                assert (
                    response.json()["approval_operation_id"] == approved["operation_id"]
                )
                denied(approve(policy_id, replay_key=str(uuid4())), (409,))
                # Changed request with the old key cannot return the old success.
                path.write_text(json.dumps(changed), encoding="utf-8")
                denied(approve(policy_id), (409,))
                foreign = await direct.post(
                    "/api/v1/projects",
                    headers={
                        "Authorization": "Bearer " + token(creator),
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={
                        "name": "Foreign post-approval project",
                        "slug": "foreign-post-approval-" + uuid4().hex,
                    },
                )
                assert foreign.status_code == 201, foreign.text
                changed = deepcopy(body)
                changed["target"]["proposal"]["project_id"] = foreign.json()["id"]
                # Keep the public target structurally valid so this actually reaches
                # resource ownership, rather than stopping at Pydantic hash validation.
                changed["target"]["upstream"]["target_digest"] = canonical_json_hash(
                    changed["target"]["proposal"]
                )
                changed["target"]["upstream_output_digest"] = canonical_json_hash(
                    changed["target"]["upstream"]
                )
                PostPolicyTarget.model_validate(changed["target"])
                path.write_text(json.dumps(changed), encoding="utf-8")
                denied(
                    approve(
                        policy_id,
                        selected=(foreign.json()["id"], *selectors[1:]),
                        replay_key=str(uuid4()),
                    )
                )
                path.write_text(json.dumps(body), encoding="utf-8")
                assert success(approve(policy_id)) == approved
                response = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/suspend",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Post-policy replay suspension proof"},
                )
                assert response.status_code == 200, response.text
                denied(approve(policy_id), (403, 404))
                response = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/reactivate",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Restore policy manager"},
                )
                assert response.status_code == 200, response.text
                assert success(approve(policy_id)) == approved
                response = await direct.post(
                    f"/api/v1/admin-role-grants/{grant}/revoke",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Post-policy replay revocation proof"},
                )
                assert response.status_code == 200, response.text
                denied(approve(policy_id))
                await stored(1, policy_id, original)
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
            log.close()
