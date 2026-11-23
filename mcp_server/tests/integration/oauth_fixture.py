"""HTTPS signing/exchange fixture for real API + installed MCP parity tests.

Only the external issuer is simulated here. Both shipped verifiers, exchange
code, API owners and database authorization remain real. Keycloak semantics and
browser behavior have their separate real-provider qualification.
"""

from __future__ import annotations

import base64
import json
import secrets
import shutil
import ssl
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key


@dataclass(frozen=True)
class IdentityTokens:
    api: str = field(repr=False)
    mcp: str = field(repr=False)


class IdentityFixture:
    resource = "https://workstream.flowresearch.tech/mcp"

    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workstream-mcp-oauth-")
        self.root = Path(self.temporary.name)
        self.secret = secrets.token_urlsafe(32)
        self.secret_file = self.root / "exchange-secret"
        self.secret_file.write_text(self.secret)
        self.secret_file.chmod(0o600)
        openssl = shutil.which("openssl")
        if not openssl:
            raise RuntimeError("MCP integration proof requires OpenSSL")
        subprocess.run(  # noqa: S603 - fixed fixture certificate command
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=127.0.0.1",
                "-addext",
                "subjectAltName=IP:127.0.0.1",
                "-keyout",
                str(self.root / "key.pem"),
                "-out",
                str(self.root / "cert.pem"),
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        (self.root / "key.pem").chmod(0o600)
        self.key = load_pem_private_key((self.root / "key.pem").read_bytes(), password=None)
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        public.update(kid="fixture", alg="RS256", use="sig")
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, value):
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802 - HTTP handler interface
                if self.path == "/realms/flow/protocol/openid-connect/certs":
                    self.reply(200, {"keys": [public]})
                else:
                    self.reply(404, {})

            def do_POST(self):  # noqa: N802 - HTTP handler interface
                try:
                    expected = (
                        "Basic "
                        + base64.b64encode(("workstream-mcp:" + fixture.secret).encode()).decode()
                    )
                    if (
                        self.path != "/realms/flow/protocol/openid-connect/token"
                        or self.headers.get("Authorization") != expected
                    ):
                        raise ValueError
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 32768:
                        raise ValueError
                    form = parse_qs(self.rfile.read(size).decode(), max_num_fields=10)
                    source = jwt.decode(
                        form["subject_token"][0],
                        fixture.key.public_key(),
                        algorithms=["RS256"],
                        issuer=fixture.issuer,
                        audience=fixture.resource,
                    )
                    if (
                        set(source["aud"]) != {fixture.resource, "workstream-mcp"}
                        or form.get("audience") != ["workstream-api"]
                        or form.get("scope") != ["workstream:access"]
                        or form.get("grant_type")
                        != ["urn:ietf:params:oauth:grant-type:token-exchange"]
                    ):
                        raise ValueError
                    now = int(time.time())
                    result = jwt.encode(
                        {
                            **source,
                            "aud": "workstream-api",
                            "azp": "workstream-mcp",
                            "iat": now,
                            "exp": min(source["exp"], now + 120),
                            "jti": uuid4().hex,
                        },
                        fixture.key,
                        algorithm="RS256",
                        headers={"kid": "fixture"},
                    )
                    self.reply(
                        200,
                        {
                            "access_token": result,
                            "token_type": "Bearer",
                            "expires_in": 120,
                            "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
                        },
                    )
                except (KeyError, ValueError, jwt.PyJWTError):
                    self.reply(400, {"error": "invalid_grant"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.issuer = f"https://127.0.0.1:{self.server.server_port}/realms/flow"
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.root / "cert.pem", self.root / "key.pem")
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        trust = self.root / "trust"
        trust.mkdir(mode=0o700)
        # Install an isolated test CA at the process boundary, not a permissive
        # verifier or product configuration switch. TLS/signature checks remain
        # enabled. No backend source is added to the installed MCP's sys.path.
        (trust / "sitecustomize.py").write_text(
            "import certifi\ncertifi.where = lambda: " + repr(str(self.root / "cert.pem")) + "\n",
        )
        self.trust = str(trust)

    def issue(self, subject: str) -> IdentityTokens:
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "sub": subject,
            "iat": now,
            "exp": now + 300,
            "jti": uuid4().hex,
            "azp": "fixture-client",
            "typ": "Bearer",
            "subject_kind": "human",
            "email": f"{subject}@flow.local",
            "name": subject.replace("-", " ").title(),
            "scope": "workstream:access",
        }
        return IdentityTokens(
            jwt.encode(
                {**claims, "aud": "workstream-api"},
                self.key,
                algorithm="RS256",
                headers={"kid": "fixture"},
            ),
            jwt.encode(
                {**claims, "aud": ["workstream-mcp", self.resource]},
                self.key,
                algorithm="RS256",
                headers={"kid": "fixture"},
            ),
        )

    def configure_processes(self, api: dict[str, str], mcp: dict[str, str]):
        api.pop("WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET", None)
        api.pop("WORKSTREAM_E2E_FLOW_SECRET", None)
        api.update(
            WORKSTREAM_TOKEN_ISSUER=self.issuer,
            WORKSTREAM_TOKEN_AUDIENCE="workstream-api",
            WORKSTREAM_TOKEN_JWKS_URL=self.issuer + "/protocol/openid-connect/certs",
            WORKSTREAM_TOKEN_ALGORITHMS="RS256",
            WORKSTREAM_TOKEN_INTROSPECTION_MODE="disabled",
            WORKSTREAM_TOKEN_INTROSPECTION_DISABLED_REASON="Fixture tokens; live API authority",
            PYTHONPATH=self.trust,
        )
        mcp.update(
            WORKSTREAM_MCP_TOKEN_ISSUER=self.issuer,
            WORKSTREAM_MCP_RESOURCE_URL=self.resource,
            WORKSTREAM_MCP_API_AUDIENCE="workstream-api",
            WORKSTREAM_MCP_EXCHANGE_SECRET_FILE=str(self.secret_file),
            PYTHONPATH=self.trust,
        )

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()
