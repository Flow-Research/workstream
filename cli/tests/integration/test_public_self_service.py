"""Installed CLI parity with public Workstream self-service operations."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest

from task_journey import exercise_manager_task_reads
from project_create_journey import exercise_project_creation
from guide_create_journey import exercise_guide_creation

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
# Canonical backend test helpers also use their pytest-root sibling imports.
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
)
from contributor_task_journey import exercise_contributor_task_reads  # noqa: E402


async def _ready(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = asyncio.get_running_loop().time() + 90
    async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
        while asyncio.get_running_loop().time() < deadline:
            assert process.poll() is None, "API exited before readiness"
            try:
                if (await client.get(url)).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    raise AssertionError("API readiness timeout")


def _bootstrap(actor_id: str, env: dict[str, str]) -> None:
    result = subprocess.run(  # noqa: S603 - documented local initial trust-root operation
        [
            sys.executable,
            "scripts/bootstrap_access_administrator.py",
            "--actor-profile-id",
            actor_id,
            "--execute",
        ],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout


@pytest.mark.asyncio
async def test_installed_cli_uses_only_public_profile_and_project_context(
    tmp_path: Path, cli, clean_postgres_database
) -> None:
    # Bootstrap requires an empty authority baseline, not accidental collection
    # order before every other PostgreSQL-backed CLI journey.
    env = api_environment()
    assert env["WORKSTREAM_DATABASE_URL"] == clean_postgres_database
    # Reused canonical activation fixtures arrange identities at this issuer.
    # This remains a local HMAC verifier, not a deployed Flow certification.
    env["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env["WORKSTREAM_FLOW_AUTH_ISSUER"] = env["WORKSTREAM_E2E_FLOW_ISSUER"]
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    issuer, audience, secret = flow_settings(env)
    tokens = {
        name: issue_flow_token(
            name, [], issuer=issuer, audience=audience, secret=secret
        )
        for name in ("cli-admin", "cli-manager", "cli-outsider", "cli-project-manager")
    }
    origin = f"http://127.0.0.1:{find_free_port()}"
    log = (tmp_path / "api.log").open("wb")
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
            base_url=origin, trust_env=False, timeout=10
        ) as direct:
            # Initial schema generation is API-fixture startup, not a CLI
            # request. Keep it bounded separately from command deadlines.
            specification = await direct.get("/openapi.json", timeout=60)
            assert specification.status_code == 200
            for path in (
                "/api/v1/actors/me",
                "/api/v1/actors/me/authorization-context",
            ):
                assert "get" in specification.json()["paths"][path], (
                    "CLI route must remain public"
                )
            assert "patch" in specification.json()["paths"]["/api/v1/actors/me"]
            assert (
                "get" in specification.json()["paths"]["/api/v1/projects/{project_id}"]
            )
            assert "post" in specification.json()["paths"]["/api/v1/projects"]
            for path in (
                "/api/v1/projects/{project_id}/tasks",
                "/api/v1/projects/{project_id}/tasks/{task_id}",
                "/api/v1/projects/{project_id}/tasks/ready",
                "/api/v1/tasks/{task_id}",
            ):
                assert "get" in specification.json()["paths"][path]
            for operation in ("claim", "start"):
                assert (
                    "post"
                    in specification.json()["paths"][
                        f"/api/v1/tasks/{{task_id}}/{operation}"
                    ]
                )
            profiles: dict[str, dict] = {}
            for name, token in tokens.items():
                result = cli(origin, token, "whoami", "--output", "json")
                assert result.returncode == 0, result.stderr
                direct_response = await direct.get(
                    "/api/v1/actors/me", headers={"Authorization": f"Bearer {token}"}
                )
                assert direct_response.status_code == 200
                actual = json.loads(result.stdout)
                expected = direct_response.json()
                touched = {"updated_at", "last_seen_at"}
                assert {k: v for k, v in actual.items() if k not in touched} == {
                    k: v for k, v in expected.items() if k not in touched
                }
                for field in touched:
                    assert datetime.fromisoformat(
                        actual[field]
                    ) <= datetime.fromisoformat(expected[field])
                profiles[name] = direct_response.json()
            assert (
                len({profile["actor_profile_id"] for profile in profiles.values()}) == 4
            )

            manager_headers = {"Authorization": f"Bearer {tokens['cli-manager']}"}
            # No project/admin grant is required for these caller-owned fields.
            for flags, name, email in (
                (
                    (
                        "--display-name",
                        "  Ada é  ",
                        "--contact-email",
                        "  contact@example.test  ",
                    ),
                    "Ada é",
                    "contact@example.test",
                ),
                (("--display-name", "N" * 200), "N" * 200, "contact@example.test"),
                (("--contact-email", "E" * 320), "N" * 200, "E" * 320),
                (("--clear-display-name",), None, "E" * 320),
                (("--clear-contact-email",), None, None),
            ):
                edited = cli(
                    origin,
                    tokens["cli-manager"],
                    "profile",
                    "update",
                    *flags,
                    "-o",
                    "json",
                )
                assert edited.returncode == 0, edited.stderr
                saved = await direct.get("/api/v1/actors/me", headers=manager_headers)
                assert saved.status_code == 200
                actual = json.loads(edited.stdout)
                assert (
                    actual["actor_profile_id"]
                    == profiles["cli-manager"]["actor_profile_id"]
                )
                assert actual["display_name"] == saved.json()["display_name"] == name
                assert actual["contact_email"] == saved.json()["contact_email"] == email
                assert {k: v for k, v in actual.items() if k not in touched} == {
                    k: v for k, v in saved.json().items() if k not in touched
                }
                assert (
                    actual["admin_roles"] == [] and actual["project_role_grants"] == []
                )
            for flags in (
                ("--display-name", ""),
                ("--display-name", "   "),
                ("--display-name", "N" * 201),
                ("--contact-email", "E" * 321),
            ):
                rejected = cli(
                    origin,
                    tokens["cli-manager"],
                    "profile",
                    "update",
                    *flags,
                    "-o",
                    "json",
                )
                assert rejected.returncode == 1 and rejected.stdout == ""
                assert json.loads(rejected.stderr)["error"]["status"] == 422
                assert "outcome_unknown" not in json.loads(rejected.stderr)["error"]
                saved = await direct.get("/api/v1/actors/me", headers=manager_headers)
                assert (
                    saved.json()["display_name"] is None
                    and saved.json()["contact_email"] is None
                )
            outsider_profile = await direct.get(
                "/api/v1/actors/me",
                headers={"Authorization": f"Bearer {tokens['cli-outsider']}"},
            )
            assert {
                k: v for k, v in outsider_profile.json().items() if k not in touched
            } == {k: v for k, v in profiles["cli-outsider"].items() if k not in touched}

            _bootstrap(profiles["cli-admin"]["actor_profile_id"], env)
            grant = await direct.post(
                "/api/v1/admin-role-grants",
                headers={
                    "Authorization": f"Bearer {tokens['cli-admin']}",
                    "Idempotency-Key": str(uuid4()),
                },
                json={
                    "target_actor_profile_id": profiles["cli-manager"][
                        "actor_profile_id"
                    ],
                    "role": "project_manager",
                    "scope_type": "system",
                    "reason": "CLI exact public project-context proof",
                },
            )
            assert grant.status_code == 201, grant.text
            project = await direct.post(
                "/api/v1/projects",
                headers={
                    "Authorization": f"Bearer {tokens['cli-manager']}",
                    "Idempotency-Key": str(uuid4()),
                },
                json={"name": "CLI API Parity", "slug": f"cli-parity-{uuid4().hex}"},
            )
            assert project.status_code == 201, project.text
            project_id = project.json()["id"]

            await exercise_project_creation(
                direct, cli, origin, tokens, profiles, project_id
            )
            await exercise_guide_creation(
                direct, cli, origin, tokens, profiles, project_id, tmp_path
            )

            for selector in (project_id, project_id.replace("-", "")):
                shown = cli(
                    origin,
                    tokens["cli-manager"],
                    "project",
                    "show",
                    selector,
                    "-o",
                    "json",
                )
                direct_project = await direct.get(
                    f"/api/v1/projects/{selector}", headers=manager_headers
                )
                assert direct_project.status_code == 200
                assert shown.returncode == 0 and shown.stderr == ""
                assert (
                    json.loads(shown.stdout) == direct_project.json() == project.json()
                )

            manager = cli(
                origin,
                tokens["cli-manager"],
                "project",
                "access",
                project_id,
                "-o",
                "json",
            )
            direct_manager = await direct.get(
                "/api/v1/actors/me/authorization-context",
                params={"project_id": project_id},
                headers={"Authorization": f"Bearer {tokens['cli-manager']}"},
            )
            assert manager.returncode == 0, manager.stderr
            assert direct_manager.status_code == 200
            assert json.loads(manager.stdout) == direct_manager.json()
            assert json.loads(manager.stdout)["project_id"] == project_id
            assert (
                json.loads(manager.stdout)["actor_profile_id"]
                == profiles["cli-manager"]["actor_profile_id"]
            )

            compact_project_id = project_id.replace("-", "")
            compact_manager = cli(
                origin,
                tokens["cli-manager"],
                "project",
                "access",
                compact_project_id,
                "-o",
                "json",
            )
            direct_compact_manager = await direct.get(
                "/api/v1/actors/me/authorization-context",
                params={"project_id": compact_project_id},
                headers={"Authorization": f"Bearer {tokens['cli-manager']}"},
            )
            assert direct_compact_manager.status_code == 200
            assert compact_manager.returncode == 0, compact_manager.stderr
            assert json.loads(compact_manager.stdout) == direct_compact_manager.json()
            assert json.loads(compact_manager.stdout)["project_id"] == project_id

            outsider = cli(
                origin,
                tokens["cli-outsider"],
                "project",
                "access",
                project_id,
                "-o",
                "json",
            )
            direct_outsider = await direct.get(
                "/api/v1/actors/me/authorization-context",
                params={"project_id": project_id},
                headers={"Authorization": f"Bearer {tokens['cli-outsider']}"},
            )
            assert outsider.returncode == 1 and outsider.stdout == ""
            assert direct_outsider.status_code == 404
            assert (
                json.loads(outsider.stderr)["error"]["code"]
                == direct_outsider.json()["error"]["code"]
            )
            other_project = await direct.post(
                "/api/v1/projects",
                headers=manager_headers | {"Idempotency-Key": str(uuid4())},
                json={"name": "Foreign project", "slug": f"cli-foreign-{uuid4().hex}"},
            )
            assert other_project.status_code == 201, other_project.text
            task_ids = await exercise_manager_task_reads(
                direct,
                cli,
                origin,
                tokens,
                profiles,
                project_id,
                other_project.json()["id"],
            )
            shown = cli(
                origin,
                tokens["cli-outsider"],
                "project",
                "show",
                project_id,
                "-o",
                "json",
            )
            assert shown.returncode == 1 and shown.stdout == ""
            assert json.loads(shown.stderr)["error"]["status"] == 404

            qualification = {
                "skills_snapshot": {
                    "availability": "available",
                    "reference_ids": ["skill:cli-proof"],
                    "unavailable_reason": None,
                },
                "reputation_snapshot": {
                    "availability": "unavailable",
                    "reference_ids": [],
                    "unavailable_reason": "no_record",
                },
                "prior_project_work_refs": [],
                "external_expertise_refs": [],
            }
            issued = await direct.post(
                f"/api/v1/projects/{project_id}/role-grants",
                headers=manager_headers | {"Idempotency-Key": str(uuid4())},
                json={
                    "target_actor_profile_id": profiles["cli-outsider"][
                        "actor_profile_id"
                    ],
                    "role": "submitter",
                    "qualification": qualification,
                    "reason": "CLI exact project inspection proof",
                },
            )
            assert issued.status_code == 201, issued.text
            assert issued.json()["status"] == "active"
            await exercise_contributor_task_reads(
                direct, cli, origin, tokens, profiles, env, qualification
            )
            for command in (("tasks", project_id), ("task", project_id, task_ids[0])):
                denied_manager_read = cli(
                    origin, tokens["cli-outsider"], "project", *command, "-o", "json"
                )
                assert (
                    denied_manager_read.returncode == 1
                    and denied_manager_read.stdout == ""
                )
                assert json.loads(denied_manager_read.stderr)["error"]["status"] == 404
            shown = cli(
                origin,
                tokens["cli-outsider"],
                "project",
                "show",
                project_id,
                "-o",
                "json",
            )
            direct_project = await direct.get(
                f"/api/v1/projects/{project_id}",
                headers={"Authorization": f"Bearer {tokens['cli-outsider']}"},
            )
            assert direct_project.status_code == 200
            assert shown.returncode == 0 and shown.stderr == ""
            assert (
                json.loads(shown.stdout)
                == direct_project.json()
                == {
                    "id": project_id,
                    "name": project.json()["name"],
                    "status": project.json()["status"],
                }
            )
            foreign = cli(
                origin,
                tokens["cli-outsider"],
                "project",
                "show",
                other_project.json()["id"],
                "-o",
                "json",
            )
            assert foreign.returncode == 1 and foreign.stdout == ""
            assert json.loads(foreign.stderr)["error"]["status"] == 404
            revoked_project_grant = await direct.post(
                f"/api/v1/projects/{project_id}/role-grants/{issued.json()['id']}/revoke",
                headers=manager_headers | {"Idempotency-Key": str(uuid4())},
                json={"reason": "CLI reads must observe project grant revocation"},
            )
            assert revoked_project_grant.status_code == 200, revoked_project_grant.text
            assert revoked_project_grant.json()["status"] == "revoked"
            shown = cli(
                origin,
                tokens["cli-outsider"],
                "project",
                "show",
                project_id,
                "-o",
                "json",
            )
            assert shown.returncode == 1 and shown.stdout == ""
            assert json.loads(shown.stderr)["error"]["status"] == 404
            # Restore exact contributor authority, then suspend that same actor:
            # denial must not pass merely because its grant was already revoked.
            reissued = await direct.post(
                f"/api/v1/projects/{project_id}/role-grants",
                headers=manager_headers | {"Idempotency-Key": str(uuid4())},
                json={
                    "target_actor_profile_id": profiles["cli-outsider"][
                        "actor_profile_id"
                    ],
                    "role": "reviewer",
                    "qualification": qualification,
                    "reason": "CLI lifecycle denial with active grant",
                },
            )
            assert reissued.status_code == 201, reissued.text
            shown = cli(
                origin,
                tokens["cli-outsider"],
                "project",
                "show",
                project_id,
                "-o",
                "json",
            )
            assert shown.returncode == 0, shown.stderr
            suspended_contributor = await direct.post(
                f"/api/v1/actors/{profiles['cli-outsider']['actor_profile_id']}/suspend",
                headers={
                    "Authorization": f"Bearer {tokens['cli-admin']}",
                    "Idempotency-Key": str(uuid4()),
                },
                json={"reason": "CLI project-read lifecycle denial"},
            )
            assert suspended_contributor.status_code == 200, suspended_contributor.text
            shown = cli(
                origin,
                tokens["cli-outsider"],
                "project",
                "show",
                project_id,
                "-o",
                "json",
            )
            assert shown.returncode == 1 and shown.stdout == ""
            assert json.loads(shown.stderr)["error"]["status"] == 404
            revoked = await direct.post(
                f"/api/v1/admin-role-grants/{grant.json()['resource_id']}/revoke",
                headers={
                    "Authorization": f"Bearer {tokens['cli-admin']}",
                    "Idempotency-Key": str(uuid4()),
                },
                json={"reason": "CLI must observe current project authority"},
            )
            assert revoked.status_code == 200, revoked.text
            after_revocation = cli(
                origin,
                tokens["cli-manager"],
                "project",
                "access",
                project_id,
                "-o",
                "json",
            )
            assert after_revocation.returncode == 1 and after_revocation.stdout == ""
            assert json.loads(after_revocation.stderr)["error"]["status"] == 404
            suspended = await direct.post(
                f"/api/v1/actors/{profiles['cli-manager']['actor_profile_id']}/suspend",
                headers={
                    "Authorization": f"Bearer {tokens['cli-admin']}",
                    "Idempotency-Key": str(uuid4()),
                },
                json={"reason": "CLI self-update lifecycle denial proof"},
            )
            assert suspended.status_code == 200, suspended.text
            denied = cli(
                origin,
                tokens["cli-manager"],
                "profile",
                "update",
                "--display-name",
                "must not persist",
                "-o",
                "json",
            )
            assert denied.returncode == 1 and denied.stdout == ""
            assert json.loads(denied.stderr)["error"]["code"] == "actor_suspended"
            assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
            stored = await direct.get(
                f"/api/v1/actors/{profiles['cli-manager']['actor_profile_id']}",
                headers={"Authorization": f"Bearer {tokens['cli-admin']}"},
            )
            assert stored.status_code == 200 and stored.json()["display_name"] is None
    finally:
        api.terminate()
        try:
            api.wait(timeout=5)
        except subprocess.TimeoutExpired:
            api.kill()
            api.wait(timeout=5)
        log.close()
