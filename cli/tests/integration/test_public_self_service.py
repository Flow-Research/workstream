"""Installed CLI parity with two public Workstream self-service operations."""

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

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
from api_contract_e2e import (  # noqa: E402
    api_environment,
    assert_isolated_database_url,
    find_free_port,
    flow_settings,
    issue_flow_token,
)


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
    tmp_path: Path, cli
) -> None:
    env = api_environment()
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    issuer, audience, secret = flow_settings(env)
    tokens = {
        name: issue_flow_token(
            name, [], issuer=issuer, audience=audience, secret=secret
        )
        for name in ("cli-admin", "cli-manager", "cli-outsider")
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
                len({profile["actor_profile_id"] for profile in profiles.values()}) == 3
            )

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
    finally:
        api.terminate()
        try:
            api.wait(timeout=5)
        except subprocess.TimeoutExpired:
            api.kill()
            api.wait(timeout=5)
        log.close()
