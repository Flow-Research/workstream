"""Connect the built CLI and installed MCP to the existing owned native journey."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
from pathlib import Path
import sys
from uuid import uuid4

import httpx

from cli.tests.journey.client import JourneyClient

_MCP_FIXTURES = Path(__file__).resolve().parents[2] / "mcp_server" / "tests" / "integration"
sys.path.insert(0, str(_MCP_FIXTURES))
try:
    from oauth_fixture import IdentityFixture, call_mcp
finally:
    sys.path.remove(str(_MCP_FIXTURES))


class ConnectedEnvironment(dict[str, str]):
    """Pass normal process settings and expose the isolated issuer to fixture callers."""

    def __init__(self, env, identity):
        super().__init__(env)
        self.identity = identity


def seeded_issuer(env):
    """Use the same canonical issuer for stored links and signed proof tokens."""
    return env.identity.issuer if isinstance(env, ConnectedEnvironment) else "https://identity.flowresearch.tech"


class ContributorClients:
    def __init__(self, cli_executable: Path, mcp_executable: Path, scratch: Path):
        self.cli_executable = cli_executable.resolve(strict=True)
        self.mcp_executable = mcp_executable.resolve(strict=True)
        self.scratch = scratch
        scratch.mkdir(mode=0o700, parents=True)
        self.identity = IdentityFixture()
        self.mcp_env = {
            key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}
        }
        self.cli = None
        self.mcp_origin = None

    def setup_authority(self, env):
        """Use the existing signed issuer and exchange without adapting product auth."""
        authority = ConnectedEnvironment(env, self.identity)
        python_path = authority["PYTHONPATH"]
        self.identity.configure_processes(authority, self.mcp_env)
        authority["PYTHONPATH"] = os.pathsep.join((authority["PYTHONPATH"], python_path))
        # Preserve standard roots for the native runner and storage connections.
        # The fixture adds its own trust only to the HTTPS identity clients.
        return authority

    def configure_processes(self, origin, port):
        self.cli = JourneyClient(self.cli_executable, origin, self.scratch)
        self.mcp_origin = f"http://127.0.0.1:{port}"
        self.mcp_env.update(
            WORKSTREAM_API_URL=origin,
            WORKSTREAM_MCP_HOST="127.0.0.1",
            WORKSTREAM_MCP_PORT=str(port),
            WORKSTREAM_MCP_READ_TIMEOUT_SECONDS="120",
            WORKSTREAM_MCP_TOTAL_TIMEOUT_SECONDS="180",
        )

    async def wait_ready(self, process):
        path = self.mcp_origin + "/.well-known/oauth-protected-resource/mcp"
        async with asyncio.timeout(60), httpx.AsyncClient(timeout=2, trust_env=False) as client:
            while process.poll() is None:
                try:
                    response = await client.get(path)
                    if response.status_code == 200 and response.json()["authorization_servers"] == [self.identity.issuer]:
                        return
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.25)
        raise RuntimeError("installed MCP exited before readiness")

    async def mcp(self, contributor, name, arguments, *, failed=False):
        token = self.identity.issue(str(contributor.actor_profile_id))
        data, error = await call_mcp(self.mcp_origin, token, name="workstream_" + name,
                                    arguments=arguments, http_deadline_seconds=185)
        if error is not failed:
            raise AssertionError(f"MCP {name} had unexpected success or failure")
        return data

    async def guide(self, contributor, token, project, expected):
        destination = self.scratch / project
        destination.mkdir(mode=0o700)
        cli = await asyncio.to_thread(self.cli.call, token, "project", "guide", "approved", project,
                                      "--download", str(destination))
        mcp = await self.mcp(contributor, "project_contributor_guide_get", {"project_id": project})
        if cli != expected or mcp != expected:
            raise AssertionError("CLI or MCP approved guide manifest differs from the public read")
        downloaded = sorted("sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in destination.iterdir())
        if downloaded != sorted(document["sha256"] for document in expected["documents"]):
            raise AssertionError("CLI did not download the approved original bytes")
        for document in expected["documents"]:
            read = await self.mcp(contributor, "project_contributor_guide_document_get", {
                "project_id": project, "guide_id": expected["guide_id"], "document_id": document["document_id"],
            })
            content = base64.b64decode(read["content_base64"], validate=True)
            if "sha256:" + hashlib.sha256(content).hexdigest() != document["sha256"]:
                raise AssertionError("MCP did not download the approved original bytes")

    async def submit(self, contributor, token, task, assignment, key, archive, *, client, failed=False):
        if client == "mcp":
            result = await self.mcp(contributor, "submission_create", {
                "task_id": task, "assignment_id": assignment, "idempotency_key": key,
                "zip_base64": base64.b64encode(archive).decode("ascii"),
            }, failed=failed)
            return {"error": result} if failed else result
        path = self.scratch / f"{uuid4()}.zip"
        with path.open("xb") as stream:
            path.chmod(0o600)
            stream.write(archive)
        try:
            return await asyncio.to_thread(
                self.cli.call, token, "task", "submit", task, "--assignment", assignment,
                "--file", str(path), "--idempotency-key", key, expected_exit=1 if failed else 0,
            )
        finally:
            path.unlink()

    async def status(self, contributor, token, assignment, expected):
        cli = await asyncio.to_thread(self.cli.call, token, "task", "status", assignment)
        mcp = await self.mcp(contributor, "task_assignment_get", {"assignment_id": assignment})
        if cli != expected or mcp != expected:
            raise AssertionError("CLI or MCP exact assignment status differs from the governed public response")
