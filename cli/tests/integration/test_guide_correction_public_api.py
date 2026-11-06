"""Production HTTP/Flow/PREP/PostgreSQL save and explicit-dispatch journey."""

import asyncio
from copy import deepcopy
from functools import partial
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
from app.adapters.project_agents import build_project_guide_adapter_profile
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.core.project_agents import project_guide_runtime_configuration
from tests.project_create_fixtures import seed_historical_project
from tests.projects.guide_compilation.runtime_fixtures import (
    scripted_model_profile_spec,
)


@pytest.mark.asyncio
async def test_guide_correction_public_save_dispatch_replay_and_authority(
    clean_postgres_database,
    tmp_path,
    cli,
    monkeypatch,  # noqa: F811
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

    # Canonical stored prerequisites, not live setup inference or broker delivery.
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
        administrator, _ = await seed_review_actor(
            factory, None, role="access_administrator", scope="system"
        )
        model_operator, _ = await seed_review_actor(
            factory, None, role="operator", scope="system"
        )
        foreign_id = new_record_id()
        async with factory() as session, session.begin():
            await seed_historical_project(
                session,
                project_id=foreign_id,
                name="Foreign guide owner",
                slug="foreign-guide-" + uuid4().hex,
            )
        foreign, _ = await seed_review_actor(factory, foreign_id)
        origin = f"http://127.0.0.1:{find_free_port()}"
        log = (tmp_path / "guide-correction-api.log").open("wb")
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
            decision = tmp_path / "correction.json"
            receipt_path = tmp_path / "saved.json"
            key = str(uuid4())

            def call(
                *, dispatch=False, presented=caller, selected=selectors, replay_key=key
            ):
                args = [
                    "project",
                    "guide",
                    "dispatch-correction" if dispatch else "correct",
                    *selected,
                    "--input",
                    str(receipt_path if dispatch else decision),
                    "-o",
                    "json",
                ]
                if not dispatch:
                    args += ["--idempotency-key", replay_key]
                return cli(origin, presented, *args)

            def success(result):
                assert result.returncode == 0 and result.stderr == "", result.stderr
                return json.loads(result.stdout)

            def denied(result, statuses=(404,)):
                assert result.returncode == 1 and result.stdout == "", result.stderr
                error = json.loads(result.stderr)["error"]
                assert error["status"] in statuses and not error.get(
                    "outcome_unknown", False
                )

            async def stored(expected, saved=None, dispatched=None):
                async with factory() as session:
                    for query in (
                        "SELECT count(*) FROM project_guide_proposal_corrections",
                        "SELECT count(*) FROM audit_events WHERE action_id='project.guide_compilation.correction.request'",
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
                    assert await session.scalar(
                        text(
                            "SELECT count(*) FROM project_guide_compilation_request_operations WHERE request_trigger='project_manager' AND expected_predecessor_compilation_id=:id"
                        ),
                        {"id": command.compilation_id},
                    ) == int(dispatched is not None)
                    if saved:
                        row = (
                            (
                                await session.execute(
                                    text(
                                        "SELECT receipt_json,reason,actor_profile_id FROM project_guide_proposal_corrections"
                                    )
                                )
                            )
                            .mappings()
                            .one()
                        )
                        assert (
                            row["receipt_json"] == saved
                            and row["reason"] == "Clarify café evidence."
                        )
                        assert str(row["actor_profile_id"]) == str(
                            actor.actor_profile_id
                        )
                        successor = (
                            (
                                await session.execute(
                                    text(
                                        "SELECT setup_generation,status,celery_task_id,source_snapshot_id FROM project_setup_runs WHERE id=:id"
                                    ),
                                    {"id": saved["successor_setup_run_id"]},
                                )
                            )
                            .mappings()
                            .one()
                        )
                        assert (
                            successor["setup_generation"]
                            == saved["successor_setup_generation"]
                        )
                        assert (
                            str(successor["source_snapshot_id"])
                            == body["target"]["source_snapshot_id"]
                        )
                        assert successor["status"] == (
                            "queued" if dispatched else "correction_requested"
                        )
                        assert (successor["celery_task_id"] is not None) == (
                            dispatched is not None
                        )

            async with httpx.AsyncClient(
                base_url=origin, trust_env=False, timeout=20
            ) as direct:
                spec = (await direct.get("/openapi.json", timeout=60)).json()
                route = "/api/v1/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}/corrections"
                assert (
                    spec["paths"][route]["post"]["x-workstream-action-id"]
                    == "project.guide_compilation.correction.request"
                )
                dispatch_spec = spec["paths"][
                    route + "/{correction_operation_id}/dispatch"
                ]["post"]
                assert (
                    "requestBody" not in dispatch_spec
                    and "202" in dispatch_spec["responses"]
                )
                source = await direct.get(prefix + "/proposal", headers=headers)
                assert source.status_code == 200, source.text
                with monkeypatch.context() as runtime_environment:
                    for name, value in env.items():
                        if name.startswith("WORKSTREAM_"):
                            runtime_environment.setenv(name, value)
                    get_settings.cache_clear()
                    try:
                        runtime_settings = get_settings()
                        configuration = project_guide_runtime_configuration(
                            runtime_settings,
                            adapter_profile_builder=partial(
                                build_project_guide_adapter_profile,
                                runtime_settings.project_agent_runtime,
                            ),
                        )
                    finally:
                        get_settings.cache_clear()
                profile = scripted_model_profile_spec(command.project_id, configuration)
                published = await direct.post(
                    f"/api/v1/operations/projects/{command.project_id}/model-profiles",
                    headers={
                        "Authorization": "Bearer " + token(model_operator),
                        "Idempotency-Key": str(uuid4()),
                    },
                    json=profile.model_dump(mode="json"),
                )
                assert published.status_code == 201, published.text
                body = {
                    "target": source.json()["target"],
                    "reason": "  Clarify café evidence.  ",
                }
                decision.write_text(json.dumps(body), encoding="utf-8")
                for presented, statuses in (
                    (token(outsider), (404,)),
                    (token(foreign), (404,)),
                    ("invalid-token", (401,)),
                ):
                    denied(call(presented=presented), statuses)
                assert (
                    await direct.post(
                        prefix + "/corrections",
                        headers={"Idempotency-Key": key},
                        json=body,
                    )
                ).status_code == 401
                await stored(0)
                saved = success(call())
                assert saved["target_digest"] == source.json()["target_digest"]
                assert (
                    saved["successor_setup_generation"]
                    == body["target"]["setup_generation"] + 1
                )
                receipt_path.write_text(json.dumps(saved))
                assert (
                    success(call(selected=tuple(x.replace("-", "") for x in selectors)))
                    == saved
                )
                await stored(1, saved)
                changed = body | {"reason": "Distinct requirements feedback."}
                decision.write_text(json.dumps(changed))
                denied(call(), (409,))
                decision.write_text(json.dumps(body))
                for presented, statuses in (
                    (token(outsider), (404,)),
                    (token(foreign), (404,)),
                    ("invalid-token", (401,)),
                ):
                    denied(call(dispatch=True, presented=presented), statuses)
                denied(call(dispatch=True, selected=(str(foreign_id), *selectors[1:])))
                unknown = deepcopy(saved)
                unknown["operation_id"] = str(new_record_id())
                receipt_path.write_text(json.dumps(unknown))
                denied(call(dispatch=True))
                receipt_path.write_text(json.dumps(saved))
                await stored(1, saved)
                observed = success(call(dispatch=True))
                assert observed == {
                    "correction_operation_id": saved["operation_id"],
                    "setup_run_id": saved["successor_setup_run_id"],
                    "setup_generation": saved["successor_setup_generation"],
                    # Dispatch reports queue state until the reserved attempt executes.
                    "status": "queued",
                }
                assert success(call(dispatch=True)) == observed
                await stored(1, saved, observed)
                # Both retry paths must still authorize against current lifecycle.
                response = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/suspend",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "CLI correction suspension proof"},
                )
                assert response.status_code == 200, response.text
                for dispatch in (False, True):
                    denied(call(dispatch=dispatch), (403, 404))
                response = await direct.post(
                    f"/api/v1/actors/{actor.actor_profile_id}/reactivate",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "Restore correction manager"},
                )
                assert response.status_code == 200, response.text
                assert (
                    success(call()) == saved
                    and success(call(dispatch=True)) == observed
                )
                response = await direct.post(
                    f"/api/v1/admin-role-grants/{grant}/revoke",
                    headers=admin | {"Idempotency-Key": str(uuid4())},
                    json={"reason": "CLI correction revocation proof"},
                )
                assert response.status_code == 200, response.text
                for dispatch in (False, True):
                    denied(call(dispatch=dispatch))
                await stored(1, saved, observed)
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
            log.close()
