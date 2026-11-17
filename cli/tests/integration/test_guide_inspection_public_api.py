"""Seven CLI inspections over actual public HTTP, Flow-token verification and SQL."""

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
from app.core.identifiers import new_record_id  # noqa: E402
from tests.conftest import (  # noqa: E402
    configured_source_instance_id as configured_source_instance_id,
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.project_create_fixtures import seed_historical_project  # noqa: E402
from tests.projects.guide_compilation.proposals.pg_support import (  # noqa: E402
    revoke_review_grant,
    seed_review_actor,
)
from tests.projects.post_policy.public_support import (  # noqa: E402
    post_policy_worker as post_policy_worker,
)
from tests.projects.public_activation.support import activation_case  # noqa: E402


@pytest.mark.asyncio
async def test_seven_real_public_reads_preserve_backend_authority_and_chain(
    clean_postgres_database, monkeypatch, post_policy_worker, tmp_path, cli
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

    # Canonical source/compilation prerequisites are fixture-arranged. The
    # server—not the CLI—approves and activates the chain before these reads.
    async with activation_case(
        clean_postgres_database, monkeypatch, post_policy_worker
    ) as (
        factory,
        command,
        actor,
        grant,
        manager,
        _finance_client,
        _policy_path,
        activate_path,
        body,
        _published,
        _version_path,
    ):
        activated = await manager.post(
            activate_path, json=body, headers={"Idempotency-Key": str(uuid4())}
        )
        assert activated.status_code == 200, activated.text
        auditor, _ = await seed_review_actor(
            factory, None, role="audit_authority", scope="system"
        )
        administrator, _ = await seed_review_actor(
            factory, None, role="access_administrator", scope="system"
        )
        finance, _ = await seed_review_actor(
            factory, command.project_id, role="finance_authority"
        )
        foreign_project = new_record_id()
        async with factory() as session, session.begin():
            await seed_historical_project(
                session,
                project_id=foreign_project,
                name="Foreign guide inspection project",
                slug="foreign-guide-inspection-" + uuid4().hex,
            )
        foreign, _ = await seed_review_actor(
            factory, foreign_project, role="project_manager"
        )
        project, guide = str(command.project_id), str(command.guide_id)
        guide_path = f"/api/v1/projects/{project}/guides/{guide}"
        origin = f"http://127.0.0.1:{find_free_port()}"
        log = (tmp_path / "guide-inspection-api.log").open("wb")
        process = subprocess.Popen(  # noqa: S603 - fixed real local API
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
            async with httpx.AsyncClient(
                base_url=origin, trust_env=False, timeout=20
            ) as direct:
                manager_headers = {"Authorization": "Bearer " + token(actor)}
                sufficiency = await direct.get(
                    guide_path + "/sufficiency-reports", headers=manager_headers
                )
                artifact = await direct.get(
                    guide_path + "/submission-artifact-policies",
                    headers=manager_headers,
                )
                assert sufficiency.status_code == artifact.status_code == 200
                assert sufficiency.json() and artifact.json()
                report_id = sufficiency.json()[0]["id"]
                policy_id = artifact.json()[0]["id"]
                cases = [
                    (
                        "/api/v1/projects/" + project + "/active-guide",
                        ("project", "active-guide", project),
                    ),
                    (
                        guide_path + "/sufficiency-reports",
                        ("project", "guide", "sufficiency", "list", project, guide),
                    ),
                    (
                        guide_path + "/sufficiency-reports/" + report_id,
                        (
                            "project",
                            "guide",
                            "sufficiency",
                            "show",
                            project,
                            guide,
                            report_id,
                        ),
                    ),
                    (
                        guide_path + "/submission-artifact-policies",
                        ("project", "guide", "artifact-policy", "list", project, guide),
                    ),
                    (
                        guide_path + "/submission-artifact-policies/" + policy_id,
                        (
                            "project",
                            "guide",
                            "artifact-policy",
                            "show",
                            project,
                            guide,
                            policy_id,
                        ),
                    ),
                    (
                        guide_path + "/effective-submission-artifact-policy",
                        (
                            "project",
                            "guide",
                            "artifact-policy",
                            "effective",
                            project,
                            guide,
                        ),
                    ),
                    (
                        guide_path + "/pre-submit-checker-policy",
                        ("project", "guide", "pre-submit-policy", project, guide),
                    ),
                ]
                specification = (await direct.get("/openapi.json", timeout=60)).json()
                for path, args in cases:
                    template = path.replace(project, "{project_id}").replace(
                        guide, "{guide_id}"
                    )
                    if report_id in template:
                        template = template.replace(report_id, "{report_id}")
                    if policy_id in template:
                        template = template.replace(policy_id, "{policy_id}")
                    assert "get" in specification["paths"][template]
                    expected = await direct.get(path, headers=manager_headers)
                    assert expected.status_code == 200, expected.text
                    result = cli(origin, token(actor), "-o", "json", *args)
                    assert result.returncode == 0 and result.stderr == "", result.stderr
                    assert json.loads(result.stdout) == expected.json()
                    auditor_result = cli(origin, token(auditor), "-o", "json", *args)
                    assert auditor_result.returncode == 0, auditor_result.stderr
                    assert json.loads(auditor_result.stdout) == expected.json()
                    for denied_token in (
                        token(finance),
                        token(administrator),
                        token(foreign),
                    ):
                        denied = cli(origin, denied_token, "-o", "json", *args)
                        assert denied.returncode == 1 and denied.stdout == "", (
                            denied.stderr
                        )
                        assert json.loads(denied.stderr)["error"]["status"] == 404
                active = (await direct.get(cases[0][0], headers=manager_headers)).json()
                assert active["guide"]["id"] == guide
                assert (
                    active["guide_source_snapshot"]["id"]
                    == active["guide_sufficiency_report"]["source_snapshot_id"]
                )
                assert (
                    active["submission_artifact_policy"]["id"]
                    == active["effective_submission_artifact_policy"][
                        "submission_artifact_policy_id"
                    ]
                )
                async with factory() as session:
                    assert (
                        await session.scalar(
                            text(
                                "SELECT count(*) FROM project_guides WHERE project_id=:id AND status='active'"
                            ),
                            {"id": project},
                        )
                        == 1
                    )
                await revoke_review_grant(factory, actor, grant)
                for _path, args in cases:
                    denied = cli(origin, token(actor), "-o", "json", *args)
                    assert denied.returncode == 1 and denied.stdout == "", denied.stderr
                    assert json.loads(denied.stderr)["error"]["status"] == 404
        finally:
            process.terminate()
            await asyncio.to_thread(process.wait, timeout=10)
            log.close()
