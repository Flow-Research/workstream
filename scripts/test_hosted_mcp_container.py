"""Exercise the shipped hosted MCP overlay with a real container/API transport fixture.

This checks container networking and signed per-caller OAuth exchange against a
fixture HTTPS provider. Real Keycloak semantics have a separate provider proof.
Requires Docker Compose >=2.24.4 and an explicitly built MCP image.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
import uuid


ROOT = Path(__file__).resolve().parents[1]
API_FIXTURE = r'''
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import threading
import time
from urllib.parse import parse_qs
import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key

ISSUER = "https://127.0.0.1:8443/realms/flow"
RESOURCE = "https://workstream.example/mcp"
KEY = Path('/fixture/key.pem').read_text()
PUBLIC = load_pem_private_key(KEY.encode(), password=None).public_key()
JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(PUBLIC))
JWK.update(kid="fixture-key", use="sig", alg="RS256")

def claims(raw, audience):
    return jwt.decode(raw, PUBLIC, algorithms=['RS256'], issuer=ISSUER, audience=audience)

class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.reply(200, {'keys': [JWK]}) if self.path == '/realms/flow/protocol/openid-connect/certs' else self.reply(404, {})

    def do_POST(self):
        try:
            if self.path != '/realms/flow/protocol/openid-connect/token':
                raise ValueError()
            if self.headers.get('Authorization') != 'Basic d29ya3N0cmVhbS1tY3A6Zml4dHVyZS1leGNoYW5nZS1zZWNyZXQ=':
                raise ValueError()
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 32768:
                raise ValueError()
            form = parse_qs(self.rfile.read(length).decode(), max_num_fields=10)
            source = claims(form['subject_token'][0], RESOURCE)
            if (set(source['aud']) != {RESOURCE, 'workstream-mcp'} or source['sub'] not in {'alice', 'bob'}
                    or form.get('audience') != ['workstream-api']
                    or form.get('scope') != ['workstream:access']
                    or form.get('grant_type') != ['urn:ietf:params:oauth:grant-type:token-exchange']):
                raise ValueError()
            now = int(time.time())
            token = jwt.encode({**source, 'aud': 'workstream-api', 'azp': 'workstream-mcp',
                'iat': now, 'exp': min(now + 120, source['exp']), 'jti': 'exchange-' + source['jti']},
                KEY, algorithm='RS256', headers={'kid': 'fixture-key'})
            self.reply(200, {'access_token': token, 'token_type': 'Bearer', 'expires_in': 120,
                            'issued_token_type': 'urn:ietf:params:oauth:token-type:access_token'})
        except (KeyError, ValueError, jwt.PyJWTError):
            self.reply(400, {'error': 'invalid_grant'})

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        status = 200
        if self.path == "/api/v1/health":
            body = {"status": "healthy"}
        elif self.path == "/api/v1/actors/me":
            try:
                token = claims(self.headers.get('Authorization', '')[7:], 'workstream-api')
                caller = token['sub'] if token['azp'] == 'workstream-mcp' and token['aud'] == 'workstream-api' else None
            except (jwt.PyJWTError, KeyError):
                caller = None
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

provider = ThreadingHTTPServer(('127.0.0.1', 8443), Provider)
tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
tls.load_cert_chain('/fixture/cert.pem', '/fixture/key.pem')
provider.socket = tls.wrap_socket(provider.socket, server_side=True)
threading.Thread(target=provider.serve_forever, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
'''

TOKEN_FIXTURE = r'''
import jwt,sys,time,uuid
from pathlib import Path
now=int(time.time())
print(jwt.encode({'iss':'https://127.0.0.1:8443/realms/flow', 'sub':sys.argv[1],
 'aud':['workstream-mcp','https://workstream.example/mcp'], 'azp':'fixture-client',
 'typ':'Bearer','subject_kind':'human','scope':'workstream:access',
 'iat':now,'exp':now+300,'jti':str(uuid.uuid4())},Path('/fixture/key.pem').read_text(),
 algorithm='RS256',headers={'kid':'fixture-key'}))
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
        private = Path(temporary)
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1',
            '-keyout', str(private / 'key.pem'), '-out', str(private / 'cert.pem'),
        ], check=True, capture_output=True, timeout=30)
        (private / 'key.pem').chmod(0o444)
        secret = private / 'exchange-secret'
        secret.write_text('fixture-exchange-secret')
        secret.chmod(0o400)
        if os.getuid() != 1000:
            run('docker', 'run', '--rm', '--network', 'none', '--read-only', '--user', '0:0',
                '--entrypoint', 'python', '--mount',
                f'type=bind,source={secret},target=/fixture-secret', args.image,
                '-c', "import os; os.chown('/fixture-secret',1000,1000)", env=env)
        trust_path = run('docker', 'run', '--rm', '--entrypoint', 'python', args.image,
                         '-c', 'import certifi; print(certifi.where())', env=env)
        env.update({
            'WORKSTREAM_TOKEN_ISSUER': 'https://127.0.0.1:8443/realms/flow',
            'WORKSTREAM_TOKEN_AUDIENCE': 'workstream-api',
            'WORKSTREAM_MCP_RESOURCE_URL': 'https://workstream.example/mcp',
            'WORKSTREAM_MCP_EXCHANGE_SECRET_FILE': str(secret),
        })
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
            base.write_text(json.dumps({"services": {"mcp": {"volumes": [{
                "type": "bind", "source": str(private / 'cert.pem'),
                "target": trust_path, "read_only": True,
            }]}, "api": {
                "image": args.image,
                "entrypoint": ["python", "-c", API_FIXTURE],
                "environment": {"FIXTURE_GENERATION": generation},
                "volumes": [
                    {"type": "bind", "source": str(private / name),
                     "target": '/fixture/' + name, "read_only": True}
                    for name in ('key.pem', 'cert.pem')
                ],
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
            api = compose("ps", "--quiet", "api")

            def bearer(caller: str) -> str:
                return run('docker', 'exec', api, 'python', '-c', TOKEN_FIXTURE, caller, env=env)

            tools = rpc("tools/list", {}, bearer('alice'))["tools"]
            assert len(tools) == len({tool["name"] for tool in tools}) == 132
            assert [tool["name"] for tool in tools][-23:] == ['workstream_projects_list', 'workstream_service_actor_create', 'workstream_task_import_batch_create', 'workstream_management_tasks_list', 'workstream_management_task_create', 'workstream_operational_tasks_list', 'workstream_task_import_batch_screen', 'workstream_task_import_batch_release', 'workstream_task_import_batch_get', 'workstream_management_task_get', 'workstream_management_task_locked_context_get', 'workstream_operational_task_locked_context_get', 'workstream_audit_task_locked_context_get', 'workstream_task_revision_context_repair', 'workstream_audit_task_evidence_get', 'workstream_project_model_profile_provision', 'workstream_project_model_budget_configure', 'workstream_project_model_usage_effect_get', 'workstream_project_model_recovery_child_create', 'workstream_task_import_source_declare', 'workstream_task_import_source_content_upload', 'workstream_task_import_source_content_get', 'workstream_task_import_source_get']
            params = {"name": "workstream_profile_get", "arguments": {}}
            for caller in ("alice", "bob"):
                result = rpc("tools/call", params, bearer(caller))
                assert not result.get("isError", False), result.get('structuredContent', {}).get('error')
                assert result["structuredContent"]["actor_profile_id"] == "profile-" + caller
                assert result["structuredContent"]["display_name"] == caller + "-" + generation
            try:
                rpc("tools/call", params)
            except HTTPError as error:
                assert error.code == 401
                assert 'resource_metadata=' in error.headers['www-authenticate']
                error.close()
            else:
                raise AssertionError('Unauthenticated MCP call did not reject')
            again = rpc("tools/call", params, bearer('alice'))
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
            except HTTPError as error:
                error.close()
                raise AssertionError("MCP unexpectedly answered in the replacement namespace") from None
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
