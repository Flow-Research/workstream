"""Exercise the shipped hosted MCP overlay with a real container/API transport fixture.

This checks container networking and caller credential forwarding, not production
authentication. Requires Docker Compose >=2.24.4 and an explicitly built MCP image.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, build_opener, ProxyHandler
import uuid


ROOT = Path(__file__).resolve().parents[1]
API_FIXTURE = r'''
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        status = 200
        if self.path == "/api/v1/health":
            body = {"status": "healthy"}
        elif self.path == "/api/v1/actors/me":
            caller = {"Bearer fixture-alice": "alice", "Bearer fixture-bob": "bob"}.get(
                self.headers.get("Authorization")
            )
            if caller is None:
                status = 401
                body = {"error": {"code": "invalid_token", "message": "denied", "details": {}}}
            else:
                # Same public profile shape as mcp_server/tests/conftest.py:profile_fixture.
                body = {
                    "actor_profile_id": "profile-" + caller, "actor_kind": "human",
                    "status": "active", "domains": ["contributor"], "admin_roles": [],
                    "project_role_grants": [], "contact_email": None,
                    "display_name": caller + "-" + os.environ["FIXTURE_GENERATION"],
                    "created_at": "2026-09-15T10:00:00Z",
                    "updated_at": "2026-09-15T10:00:00Z", "last_seen_at": None,
                }
        else:
            status, body = 404, {}
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
'''


def run(*args: str, env: dict[str, str], timeout: int = 45) -> str:
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Already-built MCP image; never pulled")
    args = parser.parse_args()
    env = {**os.environ, "WORKSTREAM_MCP_IMAGE": args.image}
    image_id = run("docker", "image", "inspect", args.image, "--format", "{{.Id}}", env=env)
    project = "ws-mcp-proof-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix=project) as temporary:
        base = Path(temporary) / "fixture.json"
        overrides = Path(temporary) / "ports.yml"
        # Retain loopback publication while avoiding collisions with a running demo.
        overrides.write_text('services:\n  api:\n    ports: !override ["127.0.0.1::8080"]\n')
        command = [
            "docker", "compose", "--project-name", project,
            "--file", str(base), "--file", str(ROOT / "deploy/hosted/compose.mcp.yml"),
            "--file", str(overrides),
        ]

        def compose(*arguments: str, timeout: int = 120) -> str:
            return run(*command, *arguments, env=env, timeout=timeout)

        def write_fixture(generation: str) -> None:
            base.write_text(json.dumps({"services": {"api": {
                "image": args.image,
                "entrypoint": ["python", "-c", API_FIXTURE],
                "environment": {"FIXTURE_GENERATION": generation},
                "healthcheck": {
                    "test": ["CMD", "python", "-c", "import urllib.request; "
                             "urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"],
                    "interval": "1s", "timeout": "3s", "retries": 10,
                },
            }}}))

        def inspect(container: str) -> dict:
            return json.loads(run("docker", "inspect", container, env=env))[0]

        def healthy() -> tuple[str, str]:
            api, mcp = compose("ps", "--quiet", "api"), compose("ps", "--quiet", "mcp")
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                details = inspect(mcp)
                assert details["Image"] == image_id
                state = details["State"]
                if state["Health"]["Status"] == "healthy":
                    assert details["HostConfig"]["NetworkMode"] == "container:" + api
                    return api, mcp
                if state["Status"] not in {"running", "restarting"}:
                    raise AssertionError("MCP fixture container stopped before becoming healthy")
                time.sleep(1)
            raise AssertionError("Hosted MCP container did not become healthy")

        def rpc(method: str, params: dict, bearer: str | None = None) -> dict:
            api = compose("ps", "--quiet", "api")
            ports = inspect(api)["NetworkSettings"]["Ports"]["8080/tcp"]
            assert len(ports) == 1 and ports[0]["HostIp"] == "127.0.0.1"
            headers = {
                "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                "Host": "127.0.0.1:8080",
            }
            if bearer is not None:
                headers["Authorization"] = "Bearer " + bearer
            request = Request(
                "http://127.0.0.1:" + ports[0]["HostPort"] + "/mcp",
                data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                headers=headers,
            )
            with build_opener(ProxyHandler({})).open(request, timeout=15) as response:
                return json.load(response)["result"]

        def prove_calls(generation: str) -> None:
            tools = rpc("tools/list", {})["tools"]
            assert len(tools) == len({tool["name"] for tool in tools}) == 132
            params = {"name": "workstream_profile_get", "arguments": {}}
            for caller in ("alice", "bob"):
                result = rpc("tools/call", params, "fixture-" + caller)
                assert not result.get("isError", False)
                assert result["structuredContent"]["actor_profile_id"] == "profile-" + caller
                assert result["structuredContent"]["display_name"] == caller + "-" + generation
            missing = rpc("tools/call", params)
            assert missing["isError"] is True
            assert missing["structuredContent"]["error"] == "invalid_credentials"
            assert missing["structuredContent"]["status"] == 401
            again = rpc("tools/call", params, "fixture-alice")
            assert again["structuredContent"]["display_name"] == "alice-" + generation

        write_fixture("initial")
        try:
            compose("up", "--detach", "--pull", "never", "--wait", "--wait-timeout", "90")
            original_api, original_mcp = healthy()
            prove_calls("initial")
            compose("restart", "mcp")
            assert healthy() == (original_api, original_mcp)
            prove_calls("initial")
            write_fixture("replacement")
            compose("up", "--detach", "--pull", "never", "--no-deps", "--force-recreate", "--wait", "--wait-timeout", "90", "api")
            replaced_api = compose("ps", "--quiet", "api")
            assert replaced_api != original_api
            assert inspect(original_mcp)["HostConfig"]["NetworkMode"] == "container:" + original_api
            # A restart cannot move the MCP process into the replacement API's
            # namespace. The new API's published port has no MCP listener yet.
            try:
                rpc("tools/list", {})
            except (URLError, ConnectionResetError):
                # Docker may refuse the empty port or reset its TCP forwarder.
                pass
            else:
                raise AssertionError("MCP unexpectedly followed the replaced API namespace")
            compose("up", "--detach", "--pull", "never", "--no-deps", "--force-recreate", "--wait", "--wait-timeout", "90", "mcp")
            current_api, current_mcp = healthy()
            assert current_api != original_api and current_mcp != original_mcp
            prove_calls("replacement")
            print(json.dumps({"proof": "hosted MCP fixture transport", "image_id": image_id,
                              "tools": 132, "restart": "passed", "replacement": "passed",
                              "stale_namespace_counterexample": "passed"}))
        finally:
            compose("down", "--volumes", "--remove-orphans", "--timeout", "10", timeout=45)


if __name__ == "__main__":
    main()
