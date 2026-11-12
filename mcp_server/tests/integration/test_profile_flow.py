from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import IO, Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from integration.oauth_fixture import IdentityFixture, IdentityTokens
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from workstream_mcp.tools.profile import normalize_update_input

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
BACKEND_PYTHON = str(BACKEND / ".venv" / "bin" / "python")


def api_environment() -> dict[str, str]:
    """Use the backend's fixture and isolation guard in its own locked environment."""
    command = (
        "import json, os, sys; sys.path.insert(0, 'scripts'); "
        "from api_contract_e2e import api_environment, assert_isolated_database_url; "
        "before = os.environ.copy(); "
        "env = api_environment(); "
        "assert_isolated_database_url(env['WORKSTREAM_DATABASE_URL']); "
        "print(json.dumps({key: value for key, value in env.items() "
        "if before.get(key) != value}))"
    )
    environment = os.environ.copy()
    environment["VIRTUAL_ENV"] = str(BACKEND / ".venv")
    result = subprocess.run(  # noqa: S603 - fixed local fixture command
        [BACKEND_PYTHON, "-c", command],
        cwd=BACKEND,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    environment.update(json.loads(result.stdout))
    return environment


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


async def _ready(url: str, process: subprocess.Popen[str]) -> None:
    async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
        for _ in range(160):
            assert process.poll() is None, "subprocess exited before readiness"
            try:
                if (await client.head(url)).status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    raise AssertionError("subprocess readiness timeout")


async def _call(
    mcp_url: str,
    token: IdentityTokens,
    *,
    name: str = "workstream_profile_get",
    arguments: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token.mcp}"},
        follow_redirects=False,
        trust_env=False,
        timeout=20,
    ) as http_client:
        transport = streamable_http_client(mcp_url + "/mcp", http_client=http_client)
        async with Client(server=transport, mode="2026-07-28") as client:
            assert client.protocol_version == "2026-07-28"
            result = await client.call_tool(name, arguments or {})
    dump = result.model_dump()
    if "structuredContent" in dump and dump["structuredContent"] is not None:
        content = dump["structuredContent"]
    elif "structured_content" in dump and dump["structured_content"] is not None:
        content = dump["structured_content"]
    else:
        import json

        content = json.loads(dump["content"][0]["text"])

    is_error = dump.get("isError", dump.get("is_error", False))
    return content, bool(is_error)


def _bootstrap_access_administrator(actor_id: str, environment: dict[str, str]) -> None:
    """Run the documented local trust-root command; never seed authority by SQL."""
    completed = subprocess.run(  # noqa: S603 - fixed repository command and generated UUID
        [
            BACKEND_PYTHON,
            "scripts/bootstrap_access_administrator.py",
            "--actor-profile-id",
            actor_id,
            "--execute",
        ],
        cwd=BACKEND,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout


async def _admin_transition(
    client: httpx.AsyncClient,
    *,
    token: IdentityTokens,
    path: str,
) -> None:
    response = await client.post(
        path,
        headers={"Authorization": f"Bearer {token.api}", "Idempotency-Key": str(uuid4())},
        json={"reason": "MCP integration lifecycle proof"},
    )
    assert response.status_code == 200, response.text


def _start_processes(
    *,
    identity: IdentityFixture,
    api_port: int,
    api_env: dict[str, str],
    mcp_port: int,
    mcp_env: dict[str, str],
    executable: str,
    scratch: str,
) -> tuple[subprocess.Popen[str], subprocess.Popen[str], IO[str], IO[str]]:
    identity.configure_processes(api_env, mcp_env)
    api_log = open(Path(scratch) / "api.log", "w", encoding="utf-8")  # noqa: PTH123
    mcp_log = open(Path(scratch) / "mcp.log", "w", encoding="utf-8")  # noqa: PTH123
    api = subprocess.Popen(  # noqa: S603
        [
            BACKEND_PYTHON,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--log-level",
            "error",
            "--no-access-log",
        ],
        cwd=BACKEND,
        env=api_env,
        stdout=api_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    mcp = subprocess.Popen(  # noqa: S603
        [executable],
        cwd=scratch,
        env=mcp_env,
        stdout=mcp_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return api, mcp, api_log, mcp_log


@pytest.mark.asyncio
async def test_installed_mcp_preserves_profile_and_lifecycle_parity(
    identity: IdentityFixture,
) -> None:
    """Exercise installed MCP profile and lifecycle tools against the real backend."""
    env = api_environment()
    tokens = {
        name: identity.issue(name)
        for name in (
            "mcp-first-a",
            "mcp-first-b",
            "mcp-admin",
            "mcp-suspended",
            "mcp-revoked",
            "mcp-deactivated",
        )
    }
    api_port, mcp_port = find_free_port(), find_free_port()
    proxy_port = find_free_port()
    while api_port == mcp_port or proxy_port in (api_port, mcp_port):
        mcp_port = find_free_port()
        proxy_port = find_free_port()
    api_url = f"http://127.0.0.1:{api_port}"
    mcp_url = f"http://127.0.0.1:{mcp_port}"
    proxy_url = f"http://127.0.0.1:{proxy_port}"
    executable = os.environ.get("WORKSTREAM_MCP_EXECUTABLE") or shutil.which("workstream-mcp")
    assert executable, "install the workstream-mcp wheel before running integration tests"

    with tempfile.TemporaryDirectory(prefix="workstream-mcp-integration-") as scratch:
        clean_mcp_env = {
            key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}
        }
        clean_mcp_env.update(
            WORKSTREAM_API_URL=proxy_url,
            WORKSTREAM_MCP_HOST="127.0.0.1",
            WORKSTREAM_MCP_PORT=str(mcp_port),
        )
        api, mcp, api_log, mcp_log = _start_processes(
            identity=identity,
            api_port=api_port,
            api_env=env,
            mcp_port=mcp_port,
            mcp_env=clean_mcp_env,
            executable=executable,
            scratch=scratch,
        )
        proxy_task: asyncio.Task[Any] | None = None
        try:
            import uvicorn
            from starlette.applications import Starlette
            from starlette.requests import Request
            from starlette.responses import Response

            proxy_in_flight = 0
            proxy_max_in_flight = 0
            proxy_barrier = asyncio.Barrier(2)

            async def proxy_forward(request: Request) -> Response:
                nonlocal proxy_in_flight, proxy_max_in_flight

                # Intercept the target profile request
                if request.url.path == "/api/v1/actors/me" and request.method == "GET":
                    proxy_in_flight += 1
                    if proxy_in_flight > proxy_max_in_flight:
                        proxy_max_in_flight = proxy_in_flight

                    try:
                        await asyncio.wait_for(proxy_barrier.wait(), timeout=5.0)
                    except (TimeoutError, asyncio.BrokenBarrierError):
                        pass

                    proxy_in_flight -= 1

                async with httpx.AsyncClient() as client:
                    headers = dict(request.headers)
                    headers.pop("host", None)
                    url = f"{api_url}{request.url.path}"
                    if request.url.query:
                        url += f"?{request.url.query}"

                    response = await client.request(
                        method=request.method,
                        url=url,
                        headers=headers,
                        content=await request.body(),
                    )
                    return Response(
                        content=response.content,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                    )

            from starlette.routing import Route

            proxy_app = Starlette(
                routes=[
                    Route(
                        "/{path:path}",
                        proxy_forward,
                        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
                    )
                ]
            )

            config = uvicorn.Config(
                app=proxy_app, host="127.0.0.1", port=proxy_port, log_level="critical"
            )
            proxy_server = uvicorn.Server(config)
            proxy_task = asyncio.create_task(proxy_server.serve())

            # Wait for proxy to bind
            async with httpx.AsyncClient() as client:
                for _ in range(20):
                    try:
                        await client.get(proxy_url)
                        break
                    except httpx.HTTPError:
                        await asyncio.sleep(0.1)

            await _ready(api_url + "/api/v1/health", api)
            await _ready(mcp_url + "/mcp", mcp)
            async with httpx.AsyncClient(base_url=api_url, trust_env=False, timeout=10) as direct:
                first: dict[str, dict[str, Any]] = {}
                names = list(tokens.keys())

                # Prove overlapping concurrency: start all requests in parallel
                tasks = [asyncio.create_task(_call(mcp_url, tokens[name])) for name in names]
                results = await asyncio.gather(*tasks)
                assert proxy_max_in_flight >= 2, (
                    f"Expected overlapping backend requests, but max was {proxy_max_in_flight}"
                )

                for name, (profile, failed) in zip(names, results, strict=True):
                    assert not failed
                    assert profile["display_name"] == name.replace("-", " ").title()
                    assert profile["contact_email"] == f"{name}@flow.local"
                    assert profile["admin_roles"] == [] and profile["project_role_grants"] == []
                    first[name] = profile
                    response = await direct.get(
                        "/api/v1/actors/me",
                        headers={"Authorization": f"Bearer {tokens[name].api}"},
                    )
                    assert response.status_code == 200
                    assert response.json()["actor_profile_id"] == profile["actor_profile_id"]

                profile_ids = {profile["actor_profile_id"] for profile in first.values()}
                assert len(profile_ids) == len(first)

                _bootstrap_access_administrator(first["mcp-admin"]["actor_profile_id"], env)
                admin_token = tokens["mcp-admin"]

                for arguments, expected_name in (
                    ({"display_name": "Initial Owner"}, "Initial Owner"),
                    ({"display_name": "  MCP Profile Owner  "}, "MCP Profile Owner"),
                    ({"display_name": None}, None),
                ):
                    updated, failed = await _call(
                        mcp_url,
                        tokens["mcp-first-b"],
                        name="workstream_profile_update",
                        arguments=arguments,
                    )
                    assert not failed
                    assert updated["display_name"] == expected_name
                    assert updated["contact_email"] == "mcp-first-b@flow.local"
                    direct_updated = await direct.get(
                        "/api/v1/actors/me",
                        headers={"Authorization": f"Bearer {tokens['mcp-first-b'].api}"},
                    )
                    assert direct_updated.status_code == 200
                    assert direct_updated.json()["display_name"] == expected_name
                    assert direct_updated.json()["contact_email"] == "mcp-first-b@flow.local"

                for arguments in (
                    {"contact_email": "changed@example.test"},
                    {"contact_email": None},
                ):
                    rejected, failed = await _call(
                        mcp_url,
                        tokens["mcp-first-b"],
                        name="workstream_profile_update",
                        arguments=arguments,
                    )
                    assert failed and rejected["error"] == "invalid_tool_input"
                saved = await direct.get(
                    "/api/v1/actors/me",
                    headers={"Authorization": f"Bearer {tokens['mcp-first-b'].api}"},
                )
                assert saved.json()["contact_email"] == "mcp-first-b@flow.local"
                manager_grant = await direct.post(
                    "/api/v1/admin-role-grants",
                    headers={
                        "Authorization": f"Bearer {admin_token.api}",
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={
                        "target_actor_profile_id": first["mcp-first-a"]["actor_profile_id"],
                        "role": "project_manager",
                        "scope_type": "system",
                        "reason": "MCP authorization-context integration proof",
                    },
                )
                assert manager_grant.status_code == 201, manager_grant.text
                project = await direct.post(
                    "/api/v1/projects",
                    headers={
                        "Authorization": f"Bearer {tokens['mcp-first-a'].api}",
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={
                        "name": "MCP Context Integration",
                        "slug": f"mcp-context-{uuid4().hex}",
                        "description": "Exact-project MCP authorization context proof",
                    },
                )
                assert project.status_code == 201, project.text
                context, failed = await _call(
                    mcp_url,
                    tokens["mcp-first-a"],
                    name="workstream_authorization_context_get",
                    arguments={"project_id": project.json()["id"]},
                )
                assert not failed
                assert context["actor_profile_id"] == first["mcp-first-a"]["actor_profile_id"]
                assert context["project_id"] == project.json()["id"]
                assert context["admin_roles"] == ["project_manager"]
                assert context["project_roles"] == []
                assert context["effective_action_ids"] == [
                    "project.contributor_candidate.list",
                    "project.guide_sufficiency_report.list",
                    "project.guide_sufficiency_report.read",
                    "project.read",
                    "project.setup_run.read",
                    "project.submission_artifact_policy.list",
                    "project.submission_artifact_policy.read",
                    "project_role_grant.issue",
                    "project_role_grant.list",
                    "project_role_grant.read",
                    "project_role_grant.revoke",
                ]
                assert "task.claim" not in context["effective_action_ids"]

                concealed, failed = await _call(
                    mcp_url,
                    tokens["mcp-first-b"],
                    name="workstream_authorization_context_get",
                    arguments={"project_id": project.json()["id"]},
                )
                assert failed
                assert concealed["status"] == 404
                assert concealed["code"] == "project_authorization_resource_not_found"

                revoked_manager = await direct.post(
                    f"/api/v1/admin-role-grants/{manager_grant.json()['resource_id']}/revoke",
                    headers={
                        "Authorization": f"Bearer {admin_token.api}",
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={"reason": "MCP context revocation proof complete"},
                )
                assert revoked_manager.status_code == 200, revoked_manager.text
                direct_revoked_context = await direct.get(
                    "/api/v1/actors/me/authorization-context",
                    headers={"Authorization": f"Bearer {tokens['mcp-first-a'].api}"},
                    params={"project_id": project.json()["id"]},
                )
                assert direct_revoked_context.status_code == 404
                assert (
                    direct_revoked_context.json()["error"]["code"]
                    == "project_authorization_resource_not_found"
                )
                revoked_context, failed = await _call(
                    mcp_url,
                    tokens["mcp-first-a"],
                    name="workstream_authorization_context_get",
                    arguments={"project_id": project.json()["id"]},
                )
                assert failed
                assert revoked_context["status"] == 404
                assert revoked_context["code"] == direct_revoked_context.json()["error"]["code"]
                assert "project_roles" not in revoked_context
                assert "effective_action_ids" not in revoked_context

                await _admin_transition(
                    direct,
                    token=admin_token,
                    path=f"/api/v1/actors/{first['mcp-suspended']['actor_profile_id']}/suspend",
                )

                revoked_link = await direct.get(
                    f"/api/v1/actors/{first['mcp-revoked']['actor_profile_id']}/identity-links",
                    headers={"Authorization": f"Bearer {admin_token.api}"},
                )
                assert revoked_link.status_code == 200, revoked_link.text
                await _admin_transition(
                    direct,
                    token=admin_token,
                    path=(
                        "/api/v1/actor-identity-links/"
                        f"{revoked_link.json()['identity_link_id']}/revoke"
                    ),
                )
                await _admin_transition(
                    direct,
                    token=admin_token,
                    path=f"/api/v1/actors/{first['mcp-deactivated']['actor_profile_id']}/deactivate",
                )

                for name, code in (
                    ("mcp-suspended", "actor_suspended"),
                    ("mcp-revoked", "identity_link_revoked"),
                    ("mcp-deactivated", "actor_deactivated"),
                ):
                    direct_response = await direct.get(
                        "/api/v1/actors/me",
                        headers={"Authorization": f"Bearer {tokens[name].api}"},
                    )
                    assert direct_response.status_code == 403
                    assert direct_response.json()["error"]["code"] == code
                    failure, failed = await _call(mcp_url, tokens[name])
                    assert failed
                    assert failure["status"] == 403 and failure["code"] == code
        finally:
            if proxy_task:
                proxy_task.cancel()
            _stop(mcp)
            _stop(api)
            api_log.close()
            mcp_log.close()


@pytest.mark.parametrize("field", ["display_name"])
@pytest.mark.parametrize(
    ("value", "expected", "valid"),
    [
        (" \tOwner\r\n", "Owner", True),
        ("\u2003Owner\u00a0", "Owner", True),
        ("Owner  Name", "Owner  Name", True),
        (None, None, True),
        ("", None, False),
        (" \t\r\n", None, False),
        ("\u2003\u00a0", None, False),
        ("Owner\x00Name", None, False),
        ("\x00Owner", None, False),
        ("Owner\x00", None, False),
    ],
)
def test_profile_normalization_matches_backend(
    field: str, value: str | None, expected: str | None, valid: bool
) -> None:
    """Compare non-OpenAPI normalization semantics with the authoritative model."""
    from app.modules.actors.schemas import ActorProfileUpdateRequest

    arguments = {field: value}
    if not valid:
        with pytest.raises(ValueError):
            ActorProfileUpdateRequest.model_validate(arguments)
        with pytest.raises(ValueError):
            normalize_update_input(arguments)
        return

    backend = ActorProfileUpdateRequest.model_validate(arguments).model_dump(exclude_unset=True)
    assert backend == {field: expected}
    assert normalize_update_input(arguments) == backend
