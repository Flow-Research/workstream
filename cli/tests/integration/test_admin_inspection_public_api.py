"""Signed socket/API/PostgreSQL parity for six privileged CLI reads."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4

import httpx
import pytest

from test_public_self_service import _ready

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND / "tests"))
from api_contract_e2e import (  # noqa: E402
    api_environment,
    assert_isolated_database_url,
    find_free_port,
    flow_settings,
    issue_flow_token,
)
from app.db.session import dispose_engine  # noqa: E402
from scripts.bootstrap_access_administrator import _run as run_bootstrap  # noqa: E402
from tests.authorization.admin_access.support import create_project  # noqa: E402
from tests.conftest import (  # noqa: E402
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
)


def inspected(cli, origin: str, token: str, *args: str, status: int = 200) -> dict:
    result = cli(origin, token, "admin", *args, "-o", "json")
    if status == 200:
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)
    assert result.returncode == 1 and result.stdout == "", result.stderr
    error = json.loads(result.stderr)["error"]
    assert error["status"] == status and "outcome_unknown" not in error
    return error


@pytest.mark.asyncio
async def test_admin_inspection_follows_real_authority_and_scope(
    tmp_path: Path, cli, clean_postgres_database
) -> None:
    env = api_environment()
    assert env["WORKSTREAM_DATABASE_URL"] == clean_postgres_database
    env["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env["WORKSTREAM_FLOW_AUTH_ISSUER"] = env["WORKSTREAM_E2E_FLOW_ISSUER"]
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    issuer, audience, secret = flow_settings(env)
    tokens = {
        name: issue_flow_token(
            name + "-cli606", [], issuer=issuer, audience=audience, secret=secret
        )
        for name in ("admin", "auditor", "scoped", "target", "outsider")
    }
    origin = f"http://127.0.0.1:{find_free_port()}"
    with (tmp_path / "admin-api.log").open("wb") as log:
        process = subprocess.Popen(  # noqa: S603 - fixed local API fixture
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
                base_url=origin,
                trust_env=False,
                timeout=20,
                limits=httpx.Limits(max_keepalive_connections=0),
            ) as direct:
                openapi = (await direct.get("/openapi.json", timeout=60)).json()[
                    "paths"
                ]
                for route in (
                    "/api/v1/actors/{actor_profile_id}",
                    "/api/v1/actors/{actor_profile_id}/identity-links",
                    "/api/v1/actors/{actor_profile_id}/admin-role-grants",
                    "/api/v1/admin-role-grants",
                    "/api/v1/authorization/permissions",
                    "/api/v1/authorization/admin-role-definitions",
                ):
                    assert "get" in openapi[route]
                profiles = {}
                for name, token in tokens.items():
                    result = cli(origin, token, "whoami", "-o", "json")
                    assert result.returncode == 0, result.stderr
                    profiles[name] = json.loads(result.stdout)["actor_profile_id"]
                # Canonical local trust-root helper; avoid a second cold Python
                # subprocess while other isolated CLI lanes share this host.
                bootstrap_code, bootstrap = await run_bootstrap(
                    UUID(profiles["admin"]), execute=True
                )
                assert (
                    bootstrap_code == 0 and bootstrap["result_code"] == "bootstrapped"
                )

                def headers(name: str, key: bool = False) -> dict[str, str]:
                    value = {"Authorization": "Bearer " + tokens[name]}
                    if key:
                        value["Idempotency-Key"] = str(uuid4())
                    return value

                async def issue(
                    target: str, role: str, project: str | None = None
                ) -> str:
                    response = await direct.post(
                        "/api/v1/admin-role-grants",
                        headers=headers("admin", True),
                        json={
                            "target_actor_profile_id": profiles[target],
                            "role": role,
                            "scope_type": "project" if project else "system",
                            "scope_project_id": project,
                            "reason": "CLI inspection authority proof",
                        },
                    )
                    assert response.status_code == 201, response.text
                    return response.json()["resource_id"]

                system_grant = await issue("auditor", "audit_authority")
                project = str(await create_project("CLI inspection scope"))
                foreign = str(await create_project("CLI inspection foreign"))
                catalogue = cli(
                    origin,
                    tokens["auditor"],
                    "project",
                    "list",
                    "--limit",
                    "1",
                    "-o",
                    "json",
                )
                assert catalogue.returncode == 0 and catalogue.stderr == "", (
                    catalogue.stderr
                )
                catalogue_page = json.loads(catalogue.stdout)
                direct_catalogue = await direct.get(
                    "/api/v1/projects",
                    headers=headers("auditor"),
                    params={"limit": 1},
                )
                assert direct_catalogue.status_code == 200, direct_catalogue.text
                assert catalogue_page == direct_catalogue.json()
                assert len(catalogue_page["items"]) == 1
                assert catalogue_page["items"][0] == {
                    "project_id": min(project, foreign),
                    "name": "CLI inspection scope"
                    if project < foreign
                    else "CLI inspection foreign",
                    "status": "draft",
                }
                assert catalogue_page["next_cursor"]
                scoped_grant = await issue("scoped", "audit_authority", project)
                target_grant = await issue("target", "project_manager", project)
                target = profiles["target"]
                for command, path in (
                    (
                        ("actor", "show", target.replace("-", "")),
                        f"/api/v1/actors/{target}",
                    ),
                    (
                        ("actor", "identity-links", target),
                        f"/api/v1/actors/{target}/identity-links",
                    ),
                    (("permissions",), "/api/v1/authorization/permissions"),
                    (
                        ("role-definitions",),
                        "/api/v1/authorization/admin-role-definitions",
                    ),
                ):
                    value = inspected(cli, origin, tokens["auditor"], *command)
                    expected = await direct.get(path, headers=headers("auditor"))
                    assert expected.status_code == 200, expected.text
                    assert value == expected.json()
                assert (
                    inspected(cli, origin, tokens["auditor"], "permissions")["total"]
                    == 95
                )
                assert (
                    inspected(cli, origin, tokens["auditor"], "role-definitions")[
                        "total"
                    ]
                    == 5
                )
                for command, path in (
                    (("role-grants",), "/api/v1/admin-role-grants"),
                    (
                        ("actor", "role-grants", profiles["scoped"]),
                        f"/api/v1/actors/{profiles['scoped']}/admin-role-grants",
                    ),
                ):
                    value = inspected(
                        cli,
                        origin,
                        tokens["scoped"],
                        *command,
                        "--scope",
                        "project",
                        "--project-id",
                        project,
                        "--status",
                        "all",
                        "--limit",
                        "1",
                    )
                    expected = await direct.get(
                        path,
                        headers=headers("scoped"),
                        params={
                            "scope_type": "project",
                            "scope_project_id": project,
                            "status": "all",
                            "limit": 1,
                        },
                    )
                    assert expected.status_code == 200 and value == expected.json(), (
                        expected.text
                    )
                    assert value["total"] >= 1
                first = inspected(
                    cli,
                    origin,
                    tokens["scoped"],
                    "role-grants",
                    "--scope",
                    "project",
                    "--project-id",
                    project,
                    "--limit",
                    "1",
                )
                cursor = first["next_cursor"]
                assert cursor and first["total"] == 2
                second = inspected(
                    cli,
                    origin,
                    tokens["scoped"],
                    "role-grants",
                    "--scope",
                    "project",
                    "--project-id",
                    project,
                    "--limit",
                    "1",
                    "--cursor",
                    cursor,
                )
                direct_second = await direct.get(
                    "/api/v1/admin-role-grants",
                    headers=headers("scoped"),
                    params={
                        "scope_type": "project",
                        "scope_project_id": project,
                        "limit": 1,
                        "cursor": cursor,
                    },
                )
                assert (
                    direct_second.status_code == 200 and second == direct_second.json()
                )
                assert {
                    first["items"][0]["grant_id"],
                    second["items"][0]["grant_id"],
                } == {scoped_grant, target_grant}
                system = inspected(
                    cli,
                    origin,
                    tokens["auditor"],
                    "actor",
                    "role-grants",
                    profiles["auditor"],
                    "--scope",
                    "system",
                    "--status",
                    "all",
                )
                assert [row["grant_id"] for row in system["items"]] == [system_grant]
                assert (
                    inspected(
                        cli,
                        origin,
                        tokens["scoped"],
                        "actor",
                        "show",
                        target,
                        status=403,
                    )["code"]
                    == "permission_not_granted"
                )
                assert (
                    inspected(
                        cli,
                        origin,
                        tokens["scoped"],
                        "role-grants",
                        "--scope",
                        "project",
                        "--project-id",
                        foreign,
                        status=403,
                    )["code"]
                    == "scope_not_authorized"
                )
                assert (
                    inspected(
                        cli,
                        origin,
                        tokens["outsider"],
                        "actor",
                        "show",
                        target,
                        status=403,
                    )["code"]
                    == "permission_not_granted"
                )

                revoked = await direct.post(
                    f"/api/v1/admin-role-grants/{scoped_grant}/revoke",
                    headers=headers("admin", True),
                    json={"reason": "End CLI inspection proof"},
                )
                assert revoked.status_code == 200, revoked.text
                assert (
                    inspected(
                        cli,
                        origin,
                        tokens["scoped"],
                        "role-grants",
                        "--scope",
                        "project",
                        "--project-id",
                        project,
                        status=403,
                    )["code"]
                    == "permission_not_granted"
                )
                suspended = await direct.post(
                    f"/api/v1/actors/{profiles['auditor']}/suspend",
                    headers=headers("admin", True),
                    json={"reason": "End CLI inspection proof"},
                )
                assert suspended.status_code == 200, suspended.text
                assert (
                    inspected(
                        cli, origin, tokens["auditor"], "permissions", status=403
                    )["code"]
                    == "actor_suspended"
                )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            await dispose_engine()
