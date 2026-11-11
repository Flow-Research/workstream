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
BINARY = Path(os.environ.get("DEMO_IDENTITY_TEST_BINARY", str(ROOT / "experiments/demo_identity/target/release/workstream-demo-identity")))


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo-identity")
    data = root / "private"
    bootstrap = subprocess.Popen(
        [str(BINARY), "init", str(data), "admin@example.test"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
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
    finally:
        if bootstrap.poll() is None:
            bootstrap.kill()
            bootstrap.wait(timeout=5)
        bootstrap.stdin.close()
        bootstrap.stdout.close()
        bootstrap.stderr.close()
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
    process = None

    def stop():
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            process.stderr.close()

    def start():
        nonlocal process
        process = subprocess.Popen([str(BINARY), "serve", str(data)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
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

    def restart():
        stop()
        start()

    try:
        start()
        yield issuer, cert, data, restart
    finally:
        stop()


def test_login_admin_provision_and_real_verifier(service, monkeypatch):
    issuer, cert, data, _restart = service
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
        duplicate = client.post(f"{issuer}/admin/accounts", headers={"Authorization": f"Bearer {admin['admin_token']}"}, json={"email": "USER@example.test", "password": "different-password-123"})
        assert duplicate.status_code == 409
        user = client.post(f"{issuer}/login", json={"email": "user@example.test", "password": "user-password-123"}).json()
        assert "admin_token" not in user
        assert "access_token" not in user
        assert user["must_change_password"] is True
        rotation = user["password_change_token"]
        denied = client.post(f"{issuer}/admin/accounts", headers={"Authorization": f"Bearer {rotation}"}, json={"email": "blocked@example.test", "password": "blocked-password-123"})
        assert denied.status_code == 401
        assert client.post(f"{issuer}/login", json={"email": "blocked@example.test", "password": "blocked-password-123"}).status_code == 401
        change = {"current_password": "user-password-123", "new_password": "chosen-password-123"}
        rotation_claims = jwt.decode(rotation, options={"verify_signature": False})
        signer = (data / "signer.pem").read_bytes()
        jwks = client.get(f"{issuer}/jwks.json").json()
        kid = jwks["keys"][0]["kid"]
        # These mutations must fail while the account is still pending and its
        # current password is correct; the unchanged credential then succeeds.
        for variant in ({"aud": "workstream-demo"}, {"purpose": "issuer_admin"}, {"purpose": None}, {"exp": int(time.time()) - 30}):
            altered = jwt.encode({**rotation_claims, **variant}, signer, algorithm="RS256", headers={"kid": kid})
            denial = client.post(f"{issuer}/me/password", headers={"Authorization": f"Bearer {altered}"}, json=change)
            assert denial.status_code == 401
        assert client.post(f"{issuer}/me/password", headers={"Authorization": f"Bearer {rotation}"}, json=change).status_code == 204
        user = client.post(f"{issuer}/login", json={"email": "user@example.test", "password": "chosen-password-123"}).json()
        assert user["must_change_password"] is False
        assert "password_change_token" not in user
        jwks = client.get(f"{issuer}/jwks.json").json()
        assert set(jwks["keys"][0]) == {"kty", "kid", "use", "key_ops", "alg", "n", "e"}
    verifier = FlowAuthVerifier(Settings(environment="test", auth_provider="flow", token_issuer=issuer,
        token_audience="workstream-demo", token_jwks_url=f"{issuer}/jwks.json", token_algorithms="RS256",
        token_clock_skew_seconds=0, token_introspection_mode="disabled",
        token_introspection_disabled_reason="demo issuer tokens expire without revocation"))
    with pytest.raises(AuthVerificationError):
        asyncio.run(verifier.verify(rotation))
    rotation_claims = jwt.decode(rotation, options={"verify_signature": False})
    assert rotation_claims["aud"] == "workstream-demo:password-change"
    assert rotation_claims["purpose"] == "password_change"
    assert rotation_claims["exp"] - rotation_claims["iat"] == 300
    assert "scope" not in rotation_claims and "subject_kind" not in rotation_claims
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


def test_password_change_and_identity_survive_process_restart(service, monkeypatch):
    issuer, cert, _data, restart = service
    bundle = cert.parent / "restart-trust.pem"
    bundle.write_bytes(Path(certifi.where()).read_bytes() + cert.read_bytes())
    monkeypatch.setattr(certifi, "where", lambda: str(bundle))
    settings = Settings(environment="test", auth_provider="flow", token_issuer=issuer,
        token_audience="workstream-demo", token_jwks_url=f"{issuer}/jwks.json", token_algorithms="RS256",
        token_clock_skew_seconds=0, token_introspection_mode="disabled",
        token_introspection_disabled_reason="demo issuer tokens expire without revocation")
    account = {"email": "password-user@example.test", "password": "original-password-123"}
    replacement = {**account, "password": "replacement-password-123"}
    with httpx.Client(verify=str(cert), trust_env=False) as client:
        admin = client.post(f"{issuer}/login", json={"email": "admin@example.test", "password": "bootstrap-password-123"})
        assert admin.status_code == 200
        created = client.post(f"{issuer}/admin/accounts", headers={"Authorization": f"Bearer {admin.json()['admin_token']}"}, json=account)
        assert created.status_code == 201
        login = client.post(f"{issuer}/login", json=account)
        assert login.status_code == 200
        assert "access_token" not in login.json()
        original_token = login.json()["password_change_token"]
        authorization = {"Authorization": f"Bearer {original_token}"}
        change = {"current_password": account["password"], "new_password": replacement["password"]}
        assert client.post(f"{issuer}/me/password", json=change).status_code == 401
        wrong = client.post(f"{issuer}/me/password", headers=authorization, json={**change, "current_password": "incorrect-password-123"})
        assert wrong.status_code == 401
        assert client.post(f"{issuer}/login", json=account).status_code == 200
        assert client.post(f"{issuer}/login", json=replacement).status_code == 401
        assert client.post(f"{issuer}/me/password", headers=authorization, json={**change, "new_password": account["password"]}).status_code == 401
        assert client.post(f"{issuer}/me/password", headers=authorization, json=change).status_code == 204
        replay = {"current_password": replacement["password"], "new_password": "replayed-password-123"}
        assert client.post(f"{issuer}/me/password", headers=authorization, json=replay).status_code == 401
        assert client.post(f"{issuer}/login", json=account).status_code == 401
        updated = client.post(f"{issuer}/login", json=replacement)
        assert updated.status_code == 200
        updated_token = updated.json()["access_token"]
        jwks = client.get(f"{issuer}/jwks.json").json()
    before = FlowAuthVerifier(settings)
    with pytest.raises(AuthVerificationError):
        asyncio.run(before.verify(original_token))
    assert asyncio.run(before.verify(updated_token)).token.subject == created.json()["subject"]

    restart()

    with httpx.Client(verify=str(cert), trust_env=False) as client:
        assert client.get(f"{issuer}/jwks.json").json() == jwks
        assert client.post(f"{issuer}/login", json=account).status_code == 401
        reopened = client.post(f"{issuer}/login", json=replacement)
        assert reopened.status_code == 200
        assert "admin_token" not in reopened.json()
    # A fresh verifier fetches the restarted issuer's JWKS over HTTPS.
    # Completed rotation persists and the signing key remains unchanged.
    after = FlowAuthVerifier(settings)
    for token in (updated_token, reopened.json()["access_token"]):
        assert asyncio.run(after.verify(token)).token.subject == created.json()["subject"]


def test_proxy_peer_does_not_collapse_participant_login_limits(service):
    issuer, cert, _data, restart = service
    # Start a fresh limiter window; never credit a slow run that crossed reset.
    started = time.monotonic()
    restart()
    with httpx.Client(verify=str(cert), trust_env=False) as client:
        # All proxy requests share a socket peer. Unknown valid-format identities must not
        # fill a peer-wide bucket that prevents another participant signing in.
        for number in range(61):
            response = client.post(
                f"{issuer}/login",
                json={"email": f"unknown-{number}@example.test", "password": "untrusted-password-123"},
                headers={"X-Real-IP": f"192.0.2.{number + 1}"},
            )
            assert response.status_code == 401
        response = client.post(f"{issuer}/login", json={
            "email": "admin@example.test", "password": "bootstrap-password-123",
        })
        assert response.status_code == 200
        assert "admin_token" in response.json()
    assert time.monotonic() - started < 60, "throttle proof crossed its fresh window"
