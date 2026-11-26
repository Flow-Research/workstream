"""Built-binary journey driver; never substitutes private product operations."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4


class JourneyClient:
    def __init__(self, executable: Path, origin: str, directory: Path):
        self.executable = executable.resolve(strict=True)
        self.origin = origin
        self.directory = directory
        self.steps: list[dict[str, object]] = []
        self.completed_stages: list[str] = []
        self.evidence = None
        if location := os.environ.get("WORKSTREAM_CLI_JOURNEY_EVIDENCE"):
            self.evidence = Path(location) / "cli-receipts"
            self.evidence.mkdir(mode=0o700, parents=True)

    def complete_stage(self, stage: str):
        self.completed_stages.append(stage)
        print(json.dumps({"stage": stage, "result": "passed"}), flush=True)

    def call(
        self,
        token: str | Callable[[], str],
        *arguments: str,
        expected_exit: int | None = 0,
    ):
        token = token() if callable(token) else token
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "LANG", "LC_ALL"}
        }
        environment.update(WORKSTREAM_API_URL=self.origin, WORKSTREAM_TOKEN=token)
        started = time.monotonic()
        result = subprocess.run(
            [str(self.executable), *arguments, "--output", "json"],
            env=environment,
            cwd=self.directory,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        elapsed_seconds = time.monotonic() - started
        if token and token in result.stdout + result.stderr:
            raise AssertionError("CLI credential disclosure; output withheld")
        # Never print input contents, credentials, or arbitrary server output.
        self.steps.append({"command": arguments[:3], "exit_code": result.returncode})
        if self.evidence is not None:
            path = self.evidence / f"{len(self.steps):04d}.json"
            with path.open("x", encoding="utf-8") as stream:
                path.chmod(0o600)
                json.dump(
                    {
                        "arguments": arguments,
                        "exit_code": result.returncode,
                        "elapsed_seconds": elapsed_seconds,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                    stream,
                )
        if result.returncode not in (
            {0, 1} if expected_exit is None else {expected_exit}
        ):
            evidence = Path(tempfile.mkdtemp(prefix="workstream-cli-failure-"))
            (evidence / "stdout.json").write_text(result.stdout)
            (evidence / "stderr.json").write_text(result.stderr)
            raise AssertionError(
                f"CLI stage {arguments[:3]!r}: exit {result.returncode}, "
                f"expected {expected_exit}; private local evidence: {evidence}"
            )
        document = json.loads(
            result.stdout if result.returncode == 0 else result.stderr
        )
        if result.returncode and result.stdout:
            raise AssertionError("failed CLI command emitted success output")
        return document

    def body(self, document: dict) -> str:
        path = self.directory / f"input-{uuid4().hex}.json"
        with path.open("x", encoding="utf-8") as stream:
            path.chmod(0o600)
            json.dump(document, stream)
        return str(path)

    def write(self, token: str, *arguments: str, body: dict, key: str):
        return self.call(
            token, *arguments, "--input", self.body(body), "--idempotency-key", key
        )

    def write_and_replay(self, token: str, *arguments: str, body: dict):
        key = str(uuid4())
        path = self.body(body)
        command = (*arguments, "--input", path, "--idempotency-key", key)
        first = self.call(token, *command)
        replay = self.call(token, *command)
        if replay != first:
            raise AssertionError(f"exact replay changed receipt at {arguments[:3]!r}")
        return first


class RefreshingToken:
    """Use the provider's existing rotating refresh grant in this isolated proof."""

    def __init__(
        self,
        provider,
        client_id: str,
        refresh_token: str,
        *,
        resource: str | None = None,
        scope: str | None = None,
    ):
        self.provider = provider
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.resource = resource
        self.scope = scope
        self.access_token = ""
        self.expires_at = 0.0

    def __call__(self) -> str:
        now = time.monotonic()
        if self.expires_at - now < 150:
            grant = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": self.refresh_token,
            }
            if self.resource is not None:
                grant["resource"] = self.resource
                grant["scope"] = self.scope
            result = self.provider.request(
                "/realms/flow/protocol/openid-connect/token", grant, form=True
            )
            access = result["access_token"]
            refreshed = result["refresh_token"]
            expires = result["expires_in"]
            if (
                type(expires) is not int
                or expires <= 0
                or any(
                    type(value) is not str or not value for value in (access, refreshed)
                )
            ):
                raise RuntimeError("identity provider returned unusable credentials")
            self.access_token, self.refresh_token = access, refreshed
            self.expires_at = now + expires
        return self.access_token


class McpJourneyClient:
    """Drive the installed OAuth-protected MCP server through the SDK's HTTP transport."""

    def __init__(self, origin: str, token: Callable[[], str]):
        self.origin = origin
        self.token = token

    async def _call(self, name: str, arguments: dict, rejected: bool):
        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
        from mcp.types import CallToolResult

        bearer = self.token()
        async with (
            asyncio.timeout(135),
            httpx2.AsyncClient(
                headers={"Authorization": "Bearer " + bearer},
                follow_redirects=False,
                timeout=130,
                trust_env=False,
            ) as http_client,
        ):
            transport = streamable_http_client(
                self.origin + "/mcp", http_client=http_client
            )
            async with Client(server=transport, mode="2026-07-28") as client:
                if client.protocol_version != "2026-07-28":
                    raise AssertionError(
                        "installed MCP negotiated a different protocol"
                    )
                result = await client.call_tool(name, arguments)
        if (
            not isinstance(result, CallToolResult)
            or result.is_error is not rejected
            or not isinstance(result.structured_content, dict)
        ):
            raise AssertionError(
                f"installed MCP tool returned an unexpected outcome for {name}"
            )
        if bearer in result.model_dump_json():
            raise AssertionError("MCP credential disclosure; output withheld")
        return result.structured_content

    def call(self, name: str, arguments: dict, *, rejected: bool = False):
        return asyncio.run(self._call(name, arguments, rejected))

    def submit(self, task_id, assignment_id, archive, key, *, rejected=False):
        return self.call(
            "workstream_submission_create",
            {
                "task_id": task_id,
                "assignment_id": assignment_id,
                "idempotency_key": key,
                "zip_base64": base64.b64encode(archive.read_bytes()).decode("ascii"),
            },
            rejected=rejected,
        )


@contextmanager
def installed_mcp(
    executable: Path, api_origin: str, directory: Path, environment: dict, token
):
    """Start and reap only the fixture's installed MCP process on loopback."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    child = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LANG", "LC_ALL"}
    }
    child.update(
        WORKSTREAM_API_URL=api_origin,
        WORKSTREAM_MCP_HOST="127.0.0.1",
        WORKSTREAM_MCP_PORT=str(port),
        WORKSTREAM_MCP_TOKEN_ISSUER=environment["WORKSTREAM_TOKEN_ISSUER"],
        WORKSTREAM_MCP_RESOURCE_URL=environment["WORKSTREAM_MCP_RESOURCE_URL"],
        WORKSTREAM_MCP_EXCHANGE_SECRET_FILE=environment[
            "WORKSTREAM_MCP_EXCHANGE_SECRET_FILE"
        ],
    )
    opener = build_opener(ProxyHandler({}))
    with (
        (directory / "mcp.log").open("wb") as log,
        subprocess.Popen(
            [str(executable.resolve(strict=True))],
            cwd=directory,
            env=child,
            stdout=log,
            stderr=subprocess.STDOUT,
        ) as process,
    ):
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with opener.open(
                        origin + "/.well-known/oauth-protected-resource/mcp", timeout=1
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("installed MCP did not become ready")
            yield McpJourneyClient(origin, token)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
