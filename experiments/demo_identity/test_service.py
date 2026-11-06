"""Real HTTPS compatibility proof with the unchanged Workstream token verifier."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import socket
import subprocess
import time

import certifi
import httpx
import jwt
import pytest

from app.adapters.auth.flow import FlowAuthVerifier
from app.core.config import Settings
from app.interfaces.auth import AuthVerificationError

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "experiments/demo_identity/target/debug/workstream-demo-identity"


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo-identity")
    data = root / "private"
    bootstrap = subprocess.Popen(
        [str(BINARY), "init", str(data), "admin@example.test"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    bootstrap.stdin.write("bootstrap-password-123\n")
    bootstrap.stdin.flush()  # Keep stdin open: a terminal operator need not send EOF.
    for _ in range(300):
        if data.exists():
            break
        if bootstrap.poll() is not None:
            raise AssertionError("issuer initialization exited before creating state")
        time.sleep(0.1)
    else:
        raise AssertionError("issuer initialization waited for stdin EOF")
    assert bootstrap.wait(timeout=240) == 0
    bootstrap.stdin.close()
    cert = root / "cert.pem"
    key = root / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
         "-keyout", str(key), "-out", str(cert)],
        capture_output=True, check=True,
    )
    key.chmod(0o600)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    issuer = f"https://127.0.0.1:{port}"
    env = {**os.environ, "DEMO_IDENTITY_ISSUER": issuer, "DEMO_IDENTITY_AUDIENCE": "workstream-demo",
           "DEMO_IDENTITY_TLS_CERT": str(cert), "DEMO_IDENTITY_TLS_KEY": str(key),
           "DEMO_IDENTITY_BIND": f"127.0.0.1:{port}"}
    process = subprocess.Popen([str(BINARY), "serve", str(data)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        with httpx.Client(verify=str(cert), trust_env=False) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise AssertionError("issuer exited during startup")
                try:
                    response = client.get(f"{issuer}/jwks.json", timeout=0.5)
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.1)
            else:
                raise AssertionError("issuer did not start")
        yield issuer, cert, data
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_login_admin_provision_and_real_verifier(service, monkeypatch):
    issuer, cert, data = service
    bundle = cert.parent / "trust.pem"
    bundle.write_bytes(Path(certifi.where()).read_bytes() + cert.read_bytes())
    monkeypatch.setattr(certifi, "where", lambda: str(bundle))
    with httpx.Client(verify=str(cert), trust_env=False) as client:
        unknown = client.post(f"{issuer}/login", json={"email": "missing@example.test", "password": "wrong-password-123"})
        wrong = client.post(f"{issuer}/login", json={"email": "admin@example.test", "password": "wrong-password-123"})
        assert (unknown.status_code, unknown.text) == (wrong.status_code, wrong.text) == (401, "invalid credentials")
        oversized = client.post(f"{issuer}/login", content=b"x" * 4097, headers={"Content-Type": "application/json"})
        assert oversized.status_code == 413
        admin = client.post(f"{issuer}/login", json={"email": "admin@example.test", "password": "bootstrap-password-123"}).json()
        assert "admin_token" in admin
        assert client.post(f"{issuer}/admin/accounts", headers={"Authorization": f"Bearer {admin['access_token']}"}, json={"email": "user@example.test", "password": "user-password-123"}).status_code == 401
        created = client.post(f"{issuer}/admin/accounts", headers={"Authorization": f"Bearer {admin['admin_token']}"}, json={"email": "user@example.test", "password": "user-password-123"})
        assert created.status_code == 201
        user = client.post(f"{issuer}/login", json={"email": "user@example.test", "password": "user-password-123"}).json()
        assert "admin_token" not in user
        jwks = client.get(f"{issuer}/jwks.json").json()
        assert set(jwks["keys"][0]) == {"kty", "kid", "use", "key_ops", "alg", "n", "e"}
    verifier = FlowAuthVerifier(Settings(environment="test", auth_provider="flow", token_issuer=issuer,
        token_audience="workstream-demo", token_jwks_url=f"{issuer}/jwks.json", token_algorithms="RS256",
        token_clock_skew_seconds=0, token_introspection_mode="disabled",
        token_introspection_disabled_reason="demo issuer tokens expire without revocation"))
    verified = asyncio.run(verifier.verify(user["access_token"])).token
    assert verified.subject == created.json()["subject"]
    assert verified.subject_kind == "human"
    assert verified.scopes == frozenset({"workstream:access"})
    with pytest.raises(AuthVerificationError):
        asyncio.run(verifier.verify(admin["admin_token"]))
    claims = jwt.decode(user["access_token"], options={"verify_signature": False})
    assert set(claims) == {"iss", "sub", "aud", "iat", "nbf", "exp", "jti", "subject_kind", "scope"}
    signer = (data / "signer.pem").read_bytes()
    kid = jwks["keys"][0]["kid"]
    for change in ({"aud": "wrong"}, {"iss": "https://wrong.example"}, {"exp": int(time.time()) - 1}):
        altered = jwt.encode({**claims, **change}, signer, algorithm="RS256", headers={"kid": kid})
        with pytest.raises(AuthVerificationError):
            asyncio.run(verifier.verify(altered))
    foreign_key = subprocess.run(["openssl", "genrsa", "2048"], capture_output=True, check=True).stdout
    forged = jwt.encode(claims, foreign_key, algorithm="RS256", headers={"kid": kid})
    with pytest.raises(AuthVerificationError):
        asyncio.run(verifier.verify(forged))
    admin_claims = jwt.decode(admin["admin_token"], options={"verify_signature": False})
    with httpx.Client(verify=str(cert), trust_env=False) as client:
        for change in ({"exp": int(time.time()) - 30}, {"nbf": int(time.time()) + 600}, {"iat": int(time.time()) + 600}):
            altered = jwt.encode({**admin_claims, **change}, signer, algorithm="RS256", headers={"kid": kid})
            denial = client.post(f"{issuer}/admin/accounts", headers={"Authorization": f"Bearer {altered}"}, json={"email": "blocked@example.test", "password": "blocked-password-123"})
            assert denial.status_code == 401
