"""Production socket/Flow/PREP/PostgreSQL activation and fresh-authority replay."""

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
from app.core.identifiers import new_record_id
from app.modules.projects.api.guide_activation import GuideActivationInput
from tests.project_create_fixtures import seed_historical_project
from tests.projects.guide_compilation.proposals.pg_support import (
    seed_selected_review_revision_inputs,
)
from tests.projects.public_activation.support import activation_body
from contribution_policy_read_journey import publish_with_policy_reads


@pytest.mark.asyncio
async def test_guide_activation_public_socket_replay_and_fresh_authority(
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

    # Canonical source/compilation prerequisites, not live inference certification.
    async with source_case(clean_postgres_database) as (
        _,
        factory,
        command,
        actor,
        grant,
    ):
        await seed_selected_review_revision_inputs(factory, command, actor)
        finance, finance_grant = await seed_review_actor(
            factory, command.project_id, role="finance_authority"
        )
        outsider, _ = await seed_review_actor(
            factory, None, role="audit_authority", scope="system"
        )
        administrator, _ = await seed_review_actor(
            factory, None, role="access_administrator", scope="system"
        )
        foreign_id = new_record_id()
        async with factory() as session, session.begin():
            await seed_historical_project(
                session,
                project_id=foreign_id,
                name="Foreign activation project",
                slug="foreign-activation-" + uuid4().hex,
            )
        foreign, _ = await seed_review_actor(factory, foreign_id)
        foreign_finance, _ = await seed_review_actor(
            factory, foreign_id, role="finance_authority"
        )
        origin = f"http://127.0.0.1:{find_free_port()}"
        log = (tmp_path / "activation-api.log").open("wb")
        process = subprocess.Popen(  # noqa: S603 - fixed production API
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
            selectors = (str(command.project_id), str(command.guide_id))
            caller = token(actor)
            headers = {"Authorization": "Bearer " + caller}
            admin = {"Authorization": "Bearer " + token(administrator)}
            prefix = "/api/v1/projects/{}/guides/{}/compilations/{}".format(
                *selectors, command.compilation_id
            )
            api_path = "/api/v1/projects/{}/guides/{}/activate".format(*selectors)
            path = tmp_path / "activation.json"
            key = str(uuid4())

            def call(*, presented=caller, selected=selectors, replay_key=key):
                return cli(
                    origin,
                    presented,
                    "-o",
                    "json",
                    "project",
                    "guide",
                    "activate",
                    *selected,
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
                ), error

            async def stored(expected, saved=None):
                async with factory() as session:
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                            )
                        )
                        == expected
                    )
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM audit_events WHERE action_id='project.guide.activate'"
                            )
                        )
                        == expected
                    )
                    guide = (
                        (
                            await session.execute(
                                text(
                                    "SELECT status,activation_operation_id,mutation_generation,contribution_policy_id,contribution_policy_version_id,selected_review_policy_id,selected_review_policy_generation,selected_review_policy_hash,selected_revision_policy_id,selected_revision_policy_generation,selected_revision_policy_hash FROM project_guides WHERE id=:id"
                                ),
                                {"id": command.guide_id},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    assert guide["status"] == ("active" if saved else "draft")
                    assert await session.scalar(
                        text("SELECT status FROM projects WHERE id=:id"),
                        {"id": command.project_id},
                    ) == ("active" if saved else "draft")
                    if saved:
                        assert (
                            str(guide["activation_operation_id"])
                            == saved["operation_id"]
                        )
                        assert (
                            guide["mutation_generation"]
                            == saved["activation_generation"]
                        )
                        for name in (
                            "contribution_policy_id",
                            "contribution_policy_version_id",
                        ):
                            assert str(guide[name]) == saved["command"][name]
                        for kind in ("review", "revision"):
                            selected = saved["command"][kind]
                            assert (
                                str(guide[f"selected_{kind}_policy_id"])
                                == selected["policy_id"]
                            )
                            assert (
                                guide[f"selected_{kind}_policy_generation"]
                                == selected["generation"]
                            )
                            assert (
                                guide[f"selected_{kind}_policy_hash"]
                                == selected["policy_hash"]
                            )
                        row = (
                            (
                                await session.execute(
                                    text(
                                        "SELECT response_json,actor_profile_id FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                                    )
                                )
                            )
                            .mappings()
                            .one()
                        )
                        assert row["response_json"] == saved and str(
                            row["actor_profile_id"]
                        ) == str(actor.actor_profile_id)

            async with httpx.AsyncClient(
                base_url=origin, trust_env=False, timeout=20
            ) as direct:
                spec = (await direct.get("/openapi.json", timeout=60)).json()
                operation = spec["paths"][
                    "/api/v1/projects/{project_id}/guides/{guide_id}/activate"
                ]["post"]
                assert (
                    operation["x-workstream-action-id"] == "project.guide.activate"
                    and "200" in operation["responses"]
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
                        "pre_submit_attachments": [],
                        "post_submit_attachments": [],
                        "acknowledged_warning_hashes": proposal["warning_hashes"],
                    },
                )
                assert upstream.status_code == 200, upstream.text
                # Explicit real task execution; this is not broker-delivery proof.
                worker = await asyncio.to_thread(
                    subprocess.run,  # noqa: S603 - canonical fixed worker
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
                policy_path = (
                    prefix
                    + "/post-submission-policies/"
                    + response.json()["post_submit_policy_id"]
                )
                response = await direct.get(policy_path, headers=headers)
                assert response.status_code == 200, response.text
                approved = await direct.post(
                    policy_path + "/approval",
                    headers=headers | {"Idempotency-Key": str(uuid4())},
                    json={"target": response.json()["target"]},
                )
                assert approved.status_code == 200, approved.text
                (
                    published,
                    inspect_retired_policy,
                ) = await publish_with_policy_reads(
                    direct,
                    cli,
                    origin,
                    factory,
                    command.project_id,
                    foreign_id,
                    token(finance),
                    finance.actor_profile_id,
                    finance_grant,
                    caller,
                    token(outsider),
                    token(foreign_finance),
                    admin,
                    tmp_path,
                )
                response = await direct.get(policy_path, headers=headers)
                assert response.status_code == 200, response.text
                body = activation_body(response.json())
                GuideActivationInput.model_validate(body)
                path.write_text(json.dumps(body), encoding="utf-8")
                for presented, statuses in (
                    (token(outsider), (404,)),
                    (token(foreign), (404,)),
                    ("invalid-token", (401,)),
                ):
                    denied(call(presented=presented), statuses)
                assert (
                    await direct.post(
                        api_path, headers={"Idempotency-Key": key}, json=body
                    )
                ).status_code == 401
                stale = deepcopy(body)
                stale["guide_mutation_generation"] += 1
                path.write_text(json.dumps(stale))
                denied(call(replay_key=str(uuid4())), (409,))
                foreign_body = deepcopy(body)
                foreign_body["target"]["proposal"]["project_id"] = str(foreign_id)
                foreign_body["target"]["upstream"]["target_digest"] = (
                    canonical_json_hash(foreign_body["target"]["proposal"])
                )
                foreign_body["target"]["upstream_output_digest"] = canonical_json_hash(
                    foreign_body["target"]["upstream"]
                )
                GuideActivationInput.model_validate(foreign_body)
                path.write_text(json.dumps(foreign_body))
                denied(
                    call(
                        presented=token(foreign),
                        selected=(str(foreign_id), selectors[1]),
                        replay_key=str(uuid4()),
                    )
                )
                await stored(0)
                path.write_text(json.dumps(body))
                saved = success(call())
                assert saved["command"] == body | {"idempotency_key": key}
                assert (
                    saved["contribution"]["contribution_policy_version_id"]
                    == published["contribution_policy_version_id"]
                )
                assert (
                    saved["activation_generation"]
                    == body["guide_mutation_generation"] + 1
                )
                assert saved["prior_project_status"] == "draft"
                assert (
                    success(
                        call(
                            selected=tuple(x.replace("-", "") for x in selectors),
                            replay_key=key.replace("-", ""),
                        )
                    )
                    == saved
                )
                await stored(1, saved)
                path.write_text(json.dumps(stale))
                denied(call(), (409,))
                path.write_text(json.dumps(body))
                denied(call(replay_key=str(uuid4())), (404, 409))
                # Published-policy retirement cannot rewrite a retained activation.
                await inspect_retired_policy()
                assert success(call()) == saved
                suspended = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/suspend",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Activation replay suspension proof"},
                )
                assert suspended.status_code == 200, suspended.text
                denied(call(), (403, 404))
                restored = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/reactivate",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Restore activation manager"},
                )
                assert restored.status_code == 200, restored.text
                assert success(call()) == saved
                revoked = await direct.post(
                    f"/api/v1/admin-role-grants/{grant}/revoke",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Activation replay revocation proof"},
                )
                assert revoked.status_code == 200, revoked.text
                denied(call())
                await stored(1, saved)
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
            log.close()
