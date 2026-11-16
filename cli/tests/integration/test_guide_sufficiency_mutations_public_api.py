"""Real public HTTP/PostgreSQL authority and replay proof for sufficiency writes."""

import asyncio
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
)
from tests.project_create_fixtures import seed_authorized_project  # noqa: E402
from tests.projects.guide_compilation.proposals.pg_support import (  # noqa: E402
    revoke_review_grant,
    seed_review_actor,
)
from tests.projects.guide_activation.source_fixtures import source_case  # noqa: E402
from tests.projects.submission_policy_fixtures import (  # noqa: E402
    project_submission_artifact_policy_body,
)


def output(result, status=0):
    assert result.returncode == status, result.stderr
    assert (result.stdout == "") == (status != 0)
    return json.loads(result.stdout if status == 0 else result.stderr)


async def ready_with_diagnostics(url, process, log_path, env):
    try:
        await _ready(url, process)
    except AssertionError as exc:
        log = log_path.read_text(encoding="utf-8", errors="replace")
        for name, value in env.items():
            if (
                value
                and len(value) >= 6
                and any(
                    marker in name
                    for marker in ("PASSWORD", "SECRET", "TOKEN", "KEY", "DATABASE_URL")
                )
            ):
                log = log.replace(value, "[REDACTED]")
        raise AssertionError(
            f"{exc}; API startup log tail ({len(log)} chars): {log[-4096:]!r}"
        ) from exc


@pytest.mark.asyncio
async def test_manual_sufficiency_cli_uses_current_public_authority_and_exact_replay(
    clean_postgres_database, tmp_path, cli
):
    env = api_environment()
    env["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env["WORKSTREAM_FLOW_AUTH_ISSUER"] = env["WORKSTREAM_E2E_FLOW_ISSUER"]
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    issuer, audience, secret = flow_settings(env)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    project = str(new_record_id())
    try:
        async with factory() as session, session.begin():
            await seed_authorized_project(
                session,
                project_id=project,
                name="Manual sufficiency CLI",
                slug="manual-sufficiency-" + uuid4().hex,
            )
        manager, grant = await seed_review_actor(factory, project)
        outsider, _ = await seed_review_actor(
            factory, None, role="audit_authority", scope="system"
        )

        def token(actor):
            return issue_flow_token(
                str(actor.actor_profile_id),
                [],
                issuer=issuer,
                audience=audience,
                secret=secret,
            )

        origin = f"http://127.0.0.1:{find_free_port()}"
        with (tmp_path / "sufficiency-api.log").open("wb") as log:
            process = subprocess.Popen(  # noqa: S603 - fixed isolated public API
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
                await ready_with_diagnostics(
                    origin + "/api/v1/health",
                    process,
                    tmp_path / "sufficiency-api.log",
                    env,
                )
                async with httpx.AsyncClient(
                    base_url=origin, trust_env=False, timeout=20
                ) as direct:
                    manager_headers = {"Authorization": "Bearer " + token(manager)}
                    guide_created = await direct.post(
                        f"/api/v1/projects/{project}/guides",
                        headers=manager_headers | {"Idempotency-Key": str(uuid4())},
                        json={
                            "version": "v1",
                            "change_summary": "Manual diagnostic source",
                            "task_examples": [
                                {"content": "Review a claim using the guide."}
                            ],
                            "documents": [
                                {"label": "guide.pdf", "media_type": "application/pdf"},
                                {
                                    "label": "rubric.pdf",
                                    "media_type": "application/pdf",
                                },
                            ],
                        },
                    )
                    assert guide_created.status_code == 201, guide_created.text
                    guide = guide_created.json()["id"]
                    root = f"/api/v1/projects/{project}/guides/{guide}"
                    setup = await direct.get(
                        root + "/setup-runs/latest", headers=manager_headers
                    )
                    assert setup.status_code == 200, setup.text
                    snapshot = setup.json()["source_snapshot_id"]
                    specification = (
                        await direct.get("/openapi.json", timeout=60)
                    ).json()["paths"]
                    template = "/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports"
                    assert "post" in specification[template]
                    assert (
                        "post"
                        in specification[template + "/{report_id}/acknowledge-warnings"]
                    )

                    create_body = {
                        "source_snapshot_id": snapshot,
                        "status": "passed_with_warnings",
                        "findings": [
                            {
                                "severity": "warning",
                                "code": "thin_examples",
                                "message": "Examples need a human note.",
                            }
                        ],
                        "summary": "Manual diagnostic only",
                    }
                    create_path = tmp_path / "report.json"
                    create_path.write_text(json.dumps(create_body), encoding="utf-8")
                    create_key = str(uuid4())

                    def create(presented, key=create_key):
                        return cli(
                            origin,
                            presented,
                            "-o",
                            "json",
                            "project",
                            "guide",
                            "sufficiency",
                            "create",
                            project,
                            guide,
                            "--input",
                            str(create_path),
                            "--idempotency-key",
                            key,
                        )

                    # An Audit Authority may inspect reports, not write diagnostics.
                    denied = output(create(token(outsider)), 1)["error"]
                    assert denied["status"] in (403, 404)
                    created = output(create(token(manager)))
                    assert (
                        created["project_id"] == project
                        and created["guide_id"] == guide
                    )
                    assert created["source_snapshot_id"] == snapshot
                    assert created["project_setup_run_id"] is None
                    assert output(create(token(manager))) == created
                    assert (
                        output(create(token(manager), str(uuid4())), 1)["error"][
                            "status"
                        ]
                        == 409
                    )
                    create_path.write_text(
                        json.dumps(create_body | {"summary": "Changed"}),
                        encoding="utf-8",
                    )
                    assert (
                        output(create(token(manager)), 1)["error"]["code"]
                        == "idempotency_mismatch"
                    )
                    create_path.write_text(json.dumps(create_body), encoding="utf-8")

                    note = {
                        "acknowledgement_note": "Warnings read; not policy approval"
                    }
                    note_path = tmp_path / "acknowledgement.json"
                    note_path.write_text(json.dumps(note), encoding="utf-8")
                    acknowledge_key = str(uuid4())

                    def acknowledge(presented, key=acknowledge_key):
                        return cli(
                            origin,
                            presented,
                            "-o",
                            "json",
                            "project",
                            "guide",
                            "sufficiency",
                            "acknowledge-warnings",
                            project,
                            guide,
                            created["id"],
                            "--input",
                            str(note_path),
                            "--idempotency-key",
                            key,
                        )

                    denied = output(acknowledge(token(outsider)), 1)["error"]
                    assert denied["status"] in (403, 404)
                    acknowledged = output(acknowledge(token(manager)))
                    assert acknowledged["id"] == created["id"]
                    assert (
                        acknowledged["warnings_acknowledged_by_role"]
                        == "project_manager"
                    )
                    assert acknowledged["warnings_acknowledged_by_actor"] == str(
                        manager.actor_profile_id
                    )
                    assert (
                        acknowledged["acknowledgement_note"]
                        == note["acknowledgement_note"]
                    )
                    assert output(acknowledge(token(manager))) == acknowledged
                    assert (
                        output(acknowledge(token(manager), str(uuid4())), 1)["error"][
                            "status"
                        ]
                        == 409
                    )
                    note_path.write_text(
                        json.dumps({"acknowledgement_note": "Changed acknowledgement"}),
                        encoding="utf-8",
                    )
                    assert (
                        output(acknowledge(token(manager)), 1)["error"]["code"]
                        == "idempotency_mismatch"
                    )
                    note_path.write_text(json.dumps(note), encoding="utf-8")
                    async with factory() as session:
                        stored = (
                            await session.execute(
                                text(
                                    "SELECT id,project_setup_run_id,warnings_acknowledged_by_actor_profile_id "
                                    "FROM guide_sufficiency_reports WHERE source_snapshot_id=:snapshot"
                                ),
                                {"snapshot": snapshot},
                            )
                        ).all()
                        assert len(stored) == 1
                        assert str(stored[0].id) == created["id"]
                        assert stored[0].project_setup_run_id is None
                        assert (
                            stored[0].warnings_acknowledged_by_actor_profile_id
                            == manager.actor_profile_id
                        )

                    await revoke_review_grant(factory, manager, grant)
                    for attempt in (
                        create(token(manager)),
                        acknowledge(token(manager)),
                    ):
                        denied = output(attempt, 1)["error"]
                        assert denied["status"] in (403, 404)
            finally:
                process.terminate()
                await asyncio.to_thread(process.wait, timeout=10)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_manual_policy_cli_after_owner_finalization_and_fresh_authority(
    clean_postgres_database, tmp_path, cli
):
    """Use the built CLI after genuine setup; manual drafts do not activate it."""
    env = api_environment()
    env["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env["WORKSTREAM_FLOW_AUTH_ISSUER"] = env["WORKSTREAM_E2E_FLOW_ISSUER"]
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    issuer, audience, secret = flow_settings(env)
    async with source_case(clean_postgres_database) as (
        values,
        factory,
        _finalization,
        actor,
        grant,
    ):
        project, guide, snapshot = (
            str(values[name]) for name in ("project", "guide", "snapshot")
        )
        async with factory() as session:
            setup = (
                await session.execute(
                    text(
                        "SELECT status,output_sufficiency_report_id "
                        "FROM project_setup_runs WHERE id=:id"
                    ),
                    {"id": str(values["setup_1"])},
                )
            ).one()
            assert setup.status == "policy_draft_ready"
            assert setup.output_sufficiency_report_id is not None
        token = issue_flow_token(
            str(actor.actor_profile_id),
            [],
            issuer=issuer,
            audience=audience,
            secret=secret,
        )
        origin = f"http://127.0.0.1:{find_free_port()}"
        with (tmp_path / "manual-policy-api.log").open("wb") as log:
            process = subprocess.Popen(  # noqa: S603 - fixed isolated public API
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
                await ready_with_diagnostics(
                    origin + "/api/v1/health",
                    process,
                    tmp_path / "manual-policy-api.log",
                    env,
                )
                create_path = tmp_path / "manual-create.json"
                create_body = {
                    "source_snapshot_id": snapshot,
                    "policy_version": "manual-v1",
                    "policy_body": project_submission_artifact_policy_body(),
                    "change_summary": "Manual draft, not the compiled proposal",
                }
                create_path.write_text(json.dumps(create_body), encoding="utf-8")
                create_key = str(uuid4())

                def create(
                    presented=token,
                    key=create_key,
                    selected_project=project,
                    selected_guide=guide,
                ):
                    return cli(
                        origin,
                        presented,
                        "-o",
                        "json",
                        "project",
                        "guide",
                        "artifact-policy",
                        "create",
                        selected_project,
                        selected_guide,
                        "--input",
                        str(create_path),
                        "--idempotency-key",
                        key,
                    )

                manual = output(create())
                assert manual["derivation_source"] == "manual_admin_derivation"
                assert manual["lifecycle_status"] == "draft"
                assert manual["source_snapshot_id"] == snapshot
                assert output(create()) == manual
                assert output(create(key=str(uuid4())), 1)["error"]["status"] == 409
                assert (
                    output(create(selected_guide=str(uuid4())), 1)["error"]["code"]
                    == "idempotency_mismatch"
                )
                assert output(create(selected_guide=str(uuid4()), key=str(uuid4())), 1)[
                    "error"
                ]["status"] in (403, 404)
                create_path.write_text(
                    json.dumps(create_body | {"policy_version": "manual-v1-changed"}),
                    encoding="utf-8",
                )
                assert output(create(), 1)["error"]["code"] == "idempotency_mismatch"
                create_path.write_text(json.dumps(create_body), encoding="utf-8")

                # A stored second project's guide and draft are real foreign
                # resources, not missing UUIDs that merely exercise 404.
                async with source_case(clean_postgres_database) as (
                    foreign_values,
                    _foreign_factory,
                    _foreign_finalization,
                    foreign_actor,
                    _foreign_grant,
                ):
                    foreign_project, foreign_guide, foreign_snapshot = (
                        str(foreign_values[name])
                        for name in ("project", "guide", "snapshot")
                    )
                    foreign_token = issue_flow_token(
                        str(foreign_actor.actor_profile_id),
                        [],
                        issuer=issuer,
                        audience=audience,
                        secret=secret,
                    )
                    foreign_path = tmp_path / "foreign-manual-create.json"
                    foreign_path.write_text(
                        json.dumps(
                            create_body
                            | {
                                "source_snapshot_id": foreign_snapshot,
                                "policy_version": "foreign-manual-v1",
                            }
                        ),
                        encoding="utf-8",
                    )
                    foreign_result = cli(
                        origin,
                        foreign_token,
                        "-o",
                        "json",
                        "project",
                        "guide",
                        "artifact-policy",
                        "create",
                        foreign_project,
                        foreign_guide,
                        "--input",
                        str(foreign_path),
                        "--idempotency-key",
                        str(uuid4()),
                    )
                    foreign_manual = output(foreign_result)
                    assert foreign_manual["project_id"] == foreign_project
                    assert foreign_manual["guide_id"] == foreign_guide
                    assert output(
                        create(key=str(uuid4()), selected_guide=foreign_guide), 1
                    )["error"]["status"] in (403, 404)
                    assert output(
                        create(
                            key=str(uuid4()),
                            selected_project=foreign_project,
                            selected_guide=foreign_guide,
                        ),
                        1,
                    )["error"]["status"] in (403, 404)
                    async with factory() as session:
                        foreign_count = await session.scalar(
                            text(
                                "SELECT COUNT(*) FROM submission_artifact_policies "
                                "WHERE guide_id=:guide AND derivation_source='manual_admin_derivation'"
                            ),
                            {"guide": foreign_guide},
                        )
                        assert foreign_count == 1

                update_path = tmp_path / "manual-update.json"
                update_body = {
                    "expected_policy_hash": manual["policy_hash"],
                    "successor_policy_version": "manual-v2",
                    "change_summary": "A replacement manual draft",
                }
                update_path.write_text(json.dumps(update_body), encoding="utf-8")
                update_key = str(uuid4())

                def update(
                    presented=token, key=update_key, selected_policy=manual["id"]
                ):
                    return cli(
                        origin,
                        presented,
                        "-o",
                        "json",
                        "project",
                        "guide",
                        "artifact-policy",
                        "update",
                        project,
                        guide,
                        selected_policy,
                        "--input",
                        str(update_path),
                        "--idempotency-key",
                        key,
                    )

                wrong_hash = (
                    "sha256:"
                    + ("0" if manual["policy_hash"][-64:] != "0" * 64 else "1") * 64
                )
                update_path.write_text(
                    json.dumps(update_body | {"expected_policy_hash": wrong_hash}),
                    encoding="utf-8",
                )
                assert output(update(key=str(uuid4())), 1)["error"]["code"] == (
                    "submission_policy_precondition_failed"
                )
                async with factory() as session:
                    assert (
                        await session.scalar(
                            text(
                                "SELECT lifecycle_status FROM submission_artifact_policies "
                                "WHERE id=:id"
                            ),
                            {"id": manual["id"]},
                        )
                        == "draft"
                    )
                    assert (
                        await session.scalar(
                            text(
                                "SELECT COUNT(*) FROM submission_artifact_policies "
                                "WHERE guide_id=:guide AND derivation_source='manual_admin_derivation'"
                            ),
                            {"guide": guide},
                        )
                        == 1
                    )
                update_path.write_text(json.dumps(update_body), encoding="utf-8")
                assert output(
                    update(key=str(uuid4()), selected_policy=foreign_manual["id"]), 1
                )["error"]["status"] in (403, 404)
                successor = output(update())
                assert successor["supersedes_policy_id"] == manual["id"]
                assert successor["derivation_source"] == "manual_admin_derivation"
                assert successor["lifecycle_status"] == "draft"
                assert output(update()) == successor
                assert output(update(key=str(uuid4())), 1)["error"]["status"] == 409
                assert (
                    output(update(selected_policy=str(uuid4())), 1)["error"]["code"]
                    == "idempotency_mismatch"
                )
                assert output(
                    update(selected_policy=str(uuid4()), key=str(uuid4())), 1
                )["error"]["status"] in (403, 404)
                update_path.write_text(
                    json.dumps(update_body | {"change_summary": "Changed"}),
                    encoding="utf-8",
                )
                assert output(update(), 1)["error"]["code"] == "idempotency_mismatch"
                update_path.write_text(json.dumps(update_body), encoding="utf-8")
                async with factory() as session:
                    predecessor = await session.scalar(
                        text(
                            "SELECT lifecycle_status FROM submission_artifact_policies "
                            "WHERE id=:id"
                        ),
                        {"id": manual["id"]},
                    )
                    assert predecessor == "superseded"
                    retained = await session.scalar(
                        text(
                            "SELECT COUNT(*) FROM submission_artifact_policies WHERE guide_id=:guide AND derivation_source='manual_admin_derivation'"
                        ),
                        {"guide": guide},
                    )
                    assert retained == 2
                    foreign_status = await session.scalar(
                        text(
                            "SELECT lifecycle_status FROM submission_artifact_policies "
                            "WHERE id=:id"
                        ),
                        {"id": foreign_manual["id"]},
                    )
                    assert foreign_status == "draft"
                    foreign_count = await session.scalar(
                        text(
                            "SELECT COUNT(*) FROM submission_artifact_policies "
                            "WHERE guide_id=:guide AND derivation_source='manual_admin_derivation'"
                        ),
                        {"guide": foreign_guide},
                    )
                    assert foreign_count == 1
                await revoke_review_grant(factory, actor, grant)
                for attempt in (create(), update()):
                    assert output(attempt, 1)["error"]["status"] in (403, 404)
            finally:
                process.terminate()
                await asyncio.to_thread(process.wait, timeout=10)
