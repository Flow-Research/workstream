"""Actual Flow/socket/PREP/SQL correction and fresh-authority replay proof."""

import asyncio
from copy import deepcopy
import json
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from test_guide_post_approval_public_api import (
    BACKEND,
    api_environment,
    assert_isolated_database_url,
    find_free_port,
    flow_settings,
    issue_flow_token,
    seed_review_actor,
    source_case,
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from test_public_self_service import _ready
from app.core.hashing import canonical_json_hash
from app.modules.projects.api.post_policy import PostPolicyTarget


@pytest.mark.asyncio
async def test_post_correction_public_socket_replay_and_authority(
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

    # Canonical retained prerequisite, not live inference or broker-delivery proof.
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
        log = (tmp_path / "post-correction-api.log").open("wb")
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
            path = tmp_path / "correction.json"
            key = str(uuid4())

            def correct(
                policy, *, presented=caller, selected=selectors, replay_key=key
            ):
                return cli(
                    origin,
                    presented,
                    "-o",
                    "json",
                    "project",
                    "guide",
                    "correct-post",
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

            async def stored(expected, policy_id, original, saved=None):
                async with factory() as session:
                    for query in (
                        "SELECT count(*) FROM project_post_policy_operations WHERE kind='correction'",
                        "SELECT count(*) FROM project_guide_proposal_corrections",
                        "SELECT count(*) FROM audit_events WHERE action_id='project.post_submit_checker_policy.correction.request'",
                    ):
                        assert await session.scalar(text(query)) == expected
                    assert (
                        await session.scalar(
                            text("SELECT count(*) FROM project_setup_runs")
                        )
                        == 1 + expected
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
                                    "SELECT policy_body,policy_hash,lifecycle_status FROM checker_policies WHERE id=:id"
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
                    assert row["lifecycle_status"] == (
                        "superseded" if expected else "compiled"
                    )
                    if saved:
                        assert (
                            await session.scalar(
                                text(
                                    "SELECT reason FROM project_guide_proposal_corrections"
                                )
                            )
                            == "Clarify café evidence before evaluation."
                        )
                        row = (
                            (
                                await session.execute(
                                    text(
                                        "SELECT receipt_json,actor_profile_id,admin_role_grant_id FROM project_post_policy_operations WHERE kind='correction'"
                                    )
                                )
                            )
                            .mappings()
                            .one()
                        )
                        assert (
                            row["receipt_json"] == saved
                            and str(row["actor_profile_id"])
                            == str(actor.actor_profile_id)
                            and str(row["admin_role_grant_id"]) == str(grant)
                        )
                        successor = (
                            (
                                await session.execute(
                                    text(
                                        "SELECT project_id,guide_id,source_snapshot_id,source_snapshot_hash,setup_generation,status,current_step FROM project_setup_runs WHERE id=:id"
                                    ),
                                    {
                                        "id": saved["correction"][
                                            "successor_setup_run_id"
                                        ]
                                    },
                                )
                            )
                            .mappings()
                            .one()
                        )
                        target = original["target"]["proposal"]
                        for field in ("project_id", "guide_id", "source_snapshot_id"):
                            assert str(successor[field]) == target[field]
                        assert (
                            successor["source_snapshot_hash"]
                            == target["source_snapshot_hash"]
                        )
                        assert (
                            successor["setup_generation"]
                            == target["setup_generation"] + 1
                        )
                        assert (
                            successor["status"]
                            == successor["current_step"]
                            == "correction_requested"
                        )

            async with httpx.AsyncClient(
                base_url=origin, trust_env=False, timeout=20
            ) as direct:
                spec = (await direct.get("/openapi.json", timeout=60)).json()
                route = "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/post-submission-policies/{policy_id}/corrections"
                operation = spec["paths"][route]["post"]
                assert (
                    operation["x-workstream-action-id"]
                    == "project.post_submit_checker_policy.correction.request"
                )
                assert "201" in operation["responses"]
                proposal = await direct.get(prefix + "/proposal", headers=headers)
                assert proposal.status_code == 200, proposal.text
                source = proposal.json()
                upstream = await direct.post(
                    prefix + "/pre-submission-approval",
                    headers=headers | {"Idempotency-Key": str(uuid4())},
                    json={
                        "target": source["target"],
                        "acknowledged_warning_hashes": source["warning_hashes"],
                    },
                )
                assert upstream.status_code == 200, upstream.text
                worker = await asyncio.to_thread(
                    subprocess.run,  # noqa: S603 - fixed real canonical task, no queued delivery claim
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
                policy_path = prefix + "/post-submission-policies/" + policy_id
                response = await direct.get(policy_path, headers=headers)
                assert response.status_code == 200, response.text
                original = response.json()
                body = {
                    "target": original["target"],
                    "reason": "  Clarify café evidence before evaluation.  ",
                }
                path.write_text(json.dumps(body), encoding="utf-8")
                denied(correct(policy_id, presented=token(outsider)))
                denied(correct(policy_id, presented="invalid-token"), (401,))
                assert (
                    await direct.post(
                        policy_path + "/corrections",
                        headers={"Idempotency-Key": key},
                        json=body,
                    )
                ).status_code == 401
                changed = deepcopy(body)
                changed["target"]["policy_hash"] = "sha256:" + "f" * 64
                path.write_text(json.dumps(changed), encoding="utf-8")
                denied(correct(policy_id, replay_key=str(uuid4())), (409,))
                await stored(0, policy_id, original)
                path.write_text(json.dumps(body), encoding="utf-8")
                saved = success(correct(policy_id))
                assert (
                    saved["kind"] == "correction"
                    and saved["target"] == original["target"]
                )
                assert (
                    saved["correction"]["target_digest"]
                    == original["proposal"]["target_digest"]
                )
                assert (
                    success(
                        correct(
                            policy_id.replace("-", ""),
                            selected=tuple(x.replace("-", "") for x in selectors),
                        )
                    )
                    == saved
                )
                response = await direct.post(
                    policy_path + "/corrections",
                    headers=headers | {"Idempotency-Key": key},
                    json=body,
                )
                assert response.status_code == 201 and response.json() == saved, (
                    response.text
                )
                await stored(1, policy_id, original, saved)
                response = await direct.get(policy_path, headers=headers)
                assert response.status_code == 200, response.text
                assert (
                    response.json()["correction"] == saved["correction"]
                    and response.json()["current"] is False
                )
                denied(correct(policy_id, replay_key=str(uuid4())), (409,))
                changed = body | {
                    "reason": "Different evaluation requirement, not equivalent normalized feedback."
                }
                path.write_text(json.dumps(changed), encoding="utf-8")
                denied(correct(policy_id), (409,))
                # Canonical normalization does not make equivalent feedback a new request.
                path.write_text(
                    json.dumps(
                        body
                        | {"reason": "Clarify cafe\u0301 evidence before evaluation."}
                    ),
                    encoding="utf-8",
                )
                assert success(correct(policy_id)) == saved
                foreign = await direct.post(
                    "/api/v1/projects",
                    headers={
                        "Authorization": "Bearer " + token(creator),
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={
                        "name": "Foreign correction project",
                        "slug": "foreign-correction-" + uuid4().hex,
                    },
                )
                assert foreign.status_code == 201, foreign.text
                changed = deepcopy(body)
                changed["target"]["proposal"]["project_id"] = foreign.json()["id"]
                changed["target"]["upstream"]["target_digest"] = canonical_json_hash(
                    changed["target"]["proposal"]
                )
                changed["target"]["upstream_output_digest"] = canonical_json_hash(
                    changed["target"]["upstream"]
                )
                PostPolicyTarget.model_validate(changed["target"])
                path.write_text(json.dumps(changed), encoding="utf-8")
                denied(
                    correct(
                        policy_id,
                        selected=(foreign.json()["id"], *selectors[1:]),
                        replay_key=str(uuid4()),
                    )
                )
                path.write_text(json.dumps(body), encoding="utf-8")
                response = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/suspend",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Correction replay suspension proof"},
                )
                assert response.status_code == 200, response.text
                denied(correct(policy_id), (403, 404))
                response = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/reactivate",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Restore correction manager"},
                )
                assert response.status_code == 200, response.text
                assert success(correct(policy_id)) == saved
                response = await direct.post(
                    f"/api/v1/admin-role-grants/{grant}/revoke",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Correction replay revocation proof"},
                )
                assert response.status_code == 200, response.text
                denied(correct(policy_id))
                await stored(1, policy_id, original, saved)
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
            log.close()
