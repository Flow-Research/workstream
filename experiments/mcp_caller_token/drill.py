"""Real HTTP/OpenAI SDK probe, run under the existing isolated database runner."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

import httpx
from mcp.types import CallToolResult

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))
from api_contract_e2e import (  # noqa: E402
    api_environment, assert_isolated_database_url, find_free_port,
    flow_settings, issue_flow_token,
)
from client import connection  # noqa: E402
from server import INPUT, TOOL  # noqa: E402


def require(value, label):
    if not value:
        raise AssertionError(label)


async def ready(url, process):
    async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
        for _ in range(160):
            require(process.poll() is None, "subprocess exited before readiness")
            try:
                response = await client.get(url)
                if response.status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    raise AssertionError("subprocess readiness timeout")


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def profile(result):
    require(not result.isError, "expected successful MCP profile")
    payload = json.loads(result.content[0].text)
    require(result.structuredContent == payload, "structured/text result mismatch")
    return payload


def denial(result, status):
    require(result.isError and not result.structuredContent, "denial leaked profile")
    require(json.loads(result.content[0].text) == {
        "error": "profile_request_failed", "status": status,
    }, "denial status changed")


async def exercise(api, mcp, env):
    """Exercise caller-token isolation and profile behavior across direct API and MCP calls."""
    issuer, audience, secret = flow_settings(env)

    def token(subject, **changes):
        return issue_flow_token(subject, [], **{
            "issuer": issuer, "audience": audience, "secret": secret, **changes})

    subjects = ("mcp-alice", "mcp-bob")
    tokens = [token(subject) for subject in subjects]
    checks = []
    async with httpx.AsyncClient(base_url=api, trust_env=False, timeout=10) as direct:
        expected = []
        for subject, bearer in zip(subjects, tokens):
            response = await direct.get("/api/v1/actors/me", headers={"Authorization": "Bearer " + bearer})
            require(response.status_code == 200, "direct positive rejected")
            payload = response.json()
            # The shared local signer includes both claims on human tokens.
            require(payload["contact_email"] == f"{subject}@flow.local"
                    and payload["display_name"] == subject.replace("-", " ").title(),
                    "first admission did not seed the signed issuer profile claims")
            require(payload["admin_roles"] == [] and payload["project_role_grants"] == [],
                    "fixture unexpectedly privileged")
            expected.append(payload)
        require(expected[0]["actor_profile_id"] != expected[1]["actor_profile_id"], "actors collapsed")

        async def caller(bearer, known):
            async with connection(mcp, bearer) as sdk:
                tools = await sdk.list_tools()
                require(len(tools) == 1 and tools[0].name == TOOL and tools[0].inputSchema == INPUT,
                        "unexpected tool catalogue")
                for _ in range(3):
                    actual = profile(await sdk.call_tool(TOOL, {}))
                    require(set(actual) == set(known), "profile field loss")
                    for field in set(known) - {"last_seen_at", "updated_at"}:
                        require(actual[field] == known[field], "caller/field isolation failed: " + field)
                bad = await sdk.call_tool(TOOL, {"actor_id": "not-the-caller"})
                require(bad.isError, "extra tool argument accepted")
                require((await sdk.call_tool("unknown_tool", {})).isError, "unknown tool accepted")
        await asyncio.gather(*(caller(t, p) for t, p in zip(tokens, expected)))
        checks += ["two_real_actors", "all_profile_fields", "concurrent_caller_isolation",
                   "closed_tool_input", "unknown_tool_rejected"]

        # Unlike A/B, this actor's FIRST API access is through the MCP tool.
        new_token = token("mcp-carol")
        async with connection(mcp, new_token) as sdk:
            admitted = profile(await sdk.call_tool(TOOL, {}))
        require(admitted["actor_profile_id"] not in {p["actor_profile_id"] for p in expected},
                "MCP first admission reused another actor")
        require(admitted["admin_roles"] == [] and admitted["project_role_grants"] == [],
                "MCP first admission created authority")
        response = await direct.get("/api/v1/actors/me", headers={"Authorization": "Bearer " + new_token})
        require(response.status_code == 200, "direct lookup after MCP admission rejected")
        require(response.json()["actor_profile_id"] == admitted["actor_profile_id"],
                "REST did not resolve the MCP-admitted actor")
        checks.append("mcp_first_admission_same_rest_actor")

        now = datetime.now(UTC)
        invalid = {
            "missing": None, "malformed": "not-a-jwt",
            "wrong_signature": token("mcp-alice", secret="not-the-signing-secret"),
            "wrong_issuer": token("mcp-alice", issuer="https://wrong.invalid"),
            "wrong_audience": token("mcp-alice", audience="mcp-only"),
            "expired": token("mcp-alice", issued_at=now-timedelta(hours=2),
                             expires_at=now-timedelta(hours=1)),
            "future": token("mcp-alice", not_before=now+timedelta(hours=1)),
        }
        for label, bearer in invalid.items():
            headers = {"Authorization": "Bearer " + bearer} if bearer else {}
            response = await direct.get("/api/v1/actors/me", headers=headers)
            require(response.status_code == 401, "direct invalid credential did not deny: " + label)
            async with connection(mcp, bearer) as sdk:
                denial(await sdk.call_tool(TOOL, {}), 401)
            checks.append(label + "_denied")

        # One HTTP client, changing only the request credential. An established
        # transport must never stand in for the current caller's authentication.
        async with httpx.AsyncClient(base_url=mcp, trust_env=False, timeout=20,
                                     headers={"Accept": "application/json, text/event-stream"}) as transport:
            initialized = await transport.post("/mcp", headers={"Authorization": "Bearer " + tokens[0]},
                json={"jsonrpc": "2.0", "id": 100, "method": "initialize", "params": {
                    "protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "caller-switch-drill", "version": "0.1"}}})
            require(initialized.status_code == 200, "raw MCP initialization rejected")
            transport.headers["MCP-Protocol-Version"] = initialized.json()["result"]["protocolVersion"]
            notified = await transport.post("/mcp", headers={"Authorization": "Bearer " + tokens[0]},
                                            json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            require(notified.status_code == 202, "MCP initialized notification rejected")
            sequence = [(tokens[0], expected[0]), (tokens[1], expected[1]),
                        (None, None), (invalid["expired"], None), (tokens[0], expected[0])]
            for index, (bearer, known) in enumerate(sequence):
                response = await transport.post("/mcp",
                    headers={"Authorization": "Bearer " + bearer} if bearer else {},
                    json={"jsonrpc": "2.0", "id": 101 + index, "method": "tools/call",
                          "params": {"name": TOOL, "arguments": {}}})
                require(response.status_code == 200, "MCP tool envelope missing")
                require(response.headers.get("cache-control") == "no-store", "private response cacheable")
                result = CallToolResult.model_validate(response.json()["result"])
                if known is None:
                    denial(result, 401)
                else:
                    require(profile(result)["actor_profile_id"] == known["actor_profile_id"],
                            "HTTP client reused a prior caller identity")
        checks.append("same_http_client_reauthenticates_each_request")

        # Warm samples exclude SDK handshake and first actor admission.
        timings = {"direct": [], "mcp": []}
        async with connection(mcp, tokens[0]) as sdk:
            for _ in range(12):
                start = time.perf_counter()
                response = await direct.get("/api/v1/actors/me", headers={"Authorization": "Bearer " + tokens[0]})
                require(response.status_code == 200, "timed direct call failed")
                timings["direct"].append((time.perf_counter()-start)*1000)
                start = time.perf_counter()
                require(profile(await sdk.call_tool(TOOL, {}))["actor_profile_id"] == expected[0]["actor_profile_id"],
                        "timed MCP identity mismatch")
                timings["mcp"].append((time.perf_counter()-start)*1000)

        # Run the standalone client executable as well, with no model involvement.
        child_env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL"}}
        child_env.update(MCP_EXPERIMENT_URL=mcp, MCP_EXPERIMENT_CALLER_TOKEN=tokens[1])
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name("client.py")), env=child_env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 45)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        require(process.returncode == 0, "standalone SDK client failed")
        require(not any(t.encode() in stdout + stderr for t in tokens), "credential in client output")
        returned = json.loads(stdout)
        require(returned["structuredContent"]["actor_profile_id"] == expected[1]["actor_profile_id"],
                "standalone SDK client identity mismatch")
        checks.append("separate_client_process")
    return {"checks": checks, "versions": {p: importlib.metadata.version(p)
            for p in ("openai-agents", "openai", "mcp", "httpx")},
            "warm_latency_ms": {name: {"samples": len(values), "median": round(statistics.median(values), 2),
                                      "max": round(max(values), 2)} for name, values in timings.items()},
            "limits": ["local signed fixture, not live Flow OAuth",
                       "no model inference; real OpenAI Agents SDK transport",
                       "passthrough success is not remote MCP OAuth conformance",
                       "self-profile only; no project permission or lifecycle certification"]}


async def main():
    env = api_environment()
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    api_port, mcp_port = find_free_port(), find_free_port()
    while mcp_port == api_port:
        mcp_port = find_free_port()
    api, mcp = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{mcp_port}"
    with tempfile.TemporaryDirectory(prefix="ws-mcp-probe-") as scratch, ExitStack() as stack:
        api_log = stack.enter_context(open(Path(scratch)/"api.log", "w"))
        api_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(api_port), "--log-level", "error", "--no-access-log"],
            cwd=ROOT/"backend", env=env, stdout=api_log, stderr=subprocess.STDOUT)
        stack.callback(stop, api_process)
        await ready(api+"/api/v1/health", api_process)
        # MCP receives no database URL, issuer secret or OpenAI credential.
        mcp_env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL"}}
        mcp_env.update(MCP_EXPERIMENT_API_URL=api, MCP_EXPERIMENT_PORT=str(mcp_port))
        mcp_log = stack.enter_context(open(Path(scratch)/"mcp.log", "w"))
        mcp_process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("server.py"))],
                                      env=mcp_env, stdout=mcp_log, stderr=subprocess.STDOUT)
        stack.callback(stop, mcp_process)
        await ready(mcp+"/mcp", mcp_process)
        result = await exercise(api, mcp, env)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
