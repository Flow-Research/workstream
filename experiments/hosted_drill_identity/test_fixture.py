"""Real HTTPS tests: no mock transport or replacement verifier client factory."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import threading

import certifi
import httpx
import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from app.adapters.auth.flow import FlowAuthVerifier
from app.core.config import Settings
from app.interfaces.auth import AuthVerificationError, AuthVerificationUnavailableError
from fixture import (
    AUDIENCE,
    IDENTITIES,
    ISSUER,
    REASON,
    initialize,
    main,
    make_server,
    mint,
    read_private,
)


@pytest.fixture(scope="module")
def material(tmp_path_factory):
    root = tmp_path_factory.mktemp("issuer") / "private"
    initialize(root)
    return root


@pytest.fixture
def tls(material, monkeypatch, tmp_path):
    server = make_server(
        material / "jwks.json",
        material / "tls.pem",
        material / "tls-key.pem",
        "127.0.0.1",
        0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    bundle = tmp_path / "trust.pem"
    bundle.write_bytes(
        Path(certifi.where()).read_bytes() + read_private(material / "ca.pem")
    )
    monkeypatch.setattr(certifi, "where", lambda: str(bundle))
    try:
        yield f"https://127.0.0.1:{server.server_port}/jwks.json"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def verifier(url):
    return FlowAuthVerifier(
        Settings(
            environment="test",
            auth_provider="flow",
            token_issuer=ISSUER,
            token_audience=AUDIENCE,
            token_jwks_url=url,
            token_algorithms="RS256",
            token_clock_skew_seconds=0,
            token_introspection_mode="disabled",
            token_introspection_disabled_reason=REASON,
        )
    )


def issued(material, tmp_path):
    output = tmp_path / "token.jwt"
    mint(material, "contributor", output)
    return read_private(output).decode()


def test_real_https_identity_contract_and_replay(material, tls, tmp_path):
    token = issued(material, tmp_path)
    claims = jwt.decode(token, options={"verify_signature": False})
    assert set(claims) == {
        "iss",
        "sub",
        "aud",
        "iat",
        "nbf",
        "exp",
        "jti",
        "subject_kind",
        "scope",
    }
    assert claims["exp"] - claims["iat"] == 900
    assert (
        claims["sub"]
        == json.loads(read_private(material / "subjects.json"))["contributor"]
    )
    assert claims["scope"] == "workstream:access"
    assert claims["subject_kind"] == "human"
    subjects = json.loads(read_private(material / "subjects.json"))
    assert set(subjects) == set(IDENTITIES)
    assert len(set(subjects.values())) == len(IDENTITIES)
    first = asyncio.run(verifier(tls).verify(token)).token
    second = asyncio.run(verifier(tls).verify(token)).token
    assert first == second  # Bearer replay is deliberately possible until expiry.
    assert first.subject == claims["sub"]
    mint(material, "contributor", tmp_path / "second.jwt")
    other = jwt.decode(
        read_private(tmp_path / "second.jwt"), options={"verify_signature": False}
    )
    assert other["sub"] == claims["sub"] and other["jti"] != claims["jti"]


@pytest.mark.parametrize(
    "change", ["signature", "issuer", "audience", "expired", "scope", "jti"]
)
def test_invalid_tokens_reject_across_real_https(material, tls, tmp_path, change):
    token = issued(material, tmp_path)
    claims = jwt.decode(token, options={"verify_signature": False})
    key = read_private(material / "signer.pem")
    if change == "signature":
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    elif change == "issuer":
        claims["iss"] = "https://foreign.test"
    elif change == "audience":
        claims["aud"] = "foreign"
    elif change == "expired":
        claims["exp"] = claims["iat"] - 1
    elif change == "scope":
        claims["scope"] = "workstream:service"
    else:
        del claims["jti"]
    altered = jwt.encode(
        claims, key, algorithm="RS256", headers=jwt.get_unverified_header(token)
    )
    with pytest.raises(AuthVerificationError) as denied:
        asyncio.run(verifier(tls).verify(altered))
    assert type(denied.value) is AuthVerificationError


def test_untrusted_tls_rejects(material, tls, tmp_path, monkeypatch):
    # Restore the packaged trust bundle, which does not trust the isolated CA.
    monkeypatch.setattr(
        certifi, "where", lambda: str(Path(certifi.__file__).with_name("cacert.pem"))
    )
    with pytest.raises(AuthVerificationUnavailableError):
        asyncio.run(verifier(tls).verify(issued(material, tmp_path)))


def test_roles_cannot_enter_verified_authority_contract(material, tls, tmp_path):
    token = issued(material, tmp_path)
    claims = jwt.decode(token, options={"verify_signature": False})
    claims["roles"] = ["Operator", "AccessAdministrator", "ProjectManager"]
    altered = jwt.encode(
        claims,
        read_private(material / "signer.pem"),
        algorithm="RS256",
        headers=jwt.get_unverified_header(token),
    )
    result = asyncio.run(verifier(tls).verify(altered))
    assert "roles" not in result.token.model_dump()
    assert set(result.model_dump()) == {"token"}


def test_jwks_only_and_no_request_logging(material, tls, capsys):
    with httpx.Client(trust_env=False) as client:
        response = client.get(tls)
        assert response.status_code == 200
        assert response.json() == json.loads(read_private(material / "jwks.json"))
        assert set(response.json()["keys"][0]) == {
            "kty",
            "kid",
            "use",
            "key_ops",
            "alg",
            "n",
            "e",
        }
        for method, path in [
            ("GET", "/signer.pem"),
            ("GET", "/mint?private-token"),
            ("POST", "/mint"),
        ]:
            denied = client.request(
                method,
                tls.replace("/jwks.json", path),
                headers={"Authorization": "Bearer private-token"},
            )
            assert denied.status_code in {404, 501}
            assert denied.content == b""
    assert "private-token" not in "".join(capsys.readouterr())


def test_server_requires_no_signer(material, tmp_path):
    for name in ("jwks.json", "tls.pem", "tls-key.pem"):
        path = tmp_path / name
        path.write_bytes(read_private(material / name))
        path.chmod(0o400)
    with make_server(
        tmp_path / "jwks.json",
        tmp_path / "tls.pem",
        tmp_path / "tls-key.pem",
        "127.0.0.1",
        0,
    ):
        assert not (tmp_path / "signer.pem").exists()


def test_exclusive_private_files_and_no_token_output(material, tmp_path, capsys):
    output = tmp_path / "token.jwt"
    mint(material, "manager", output)
    original = read_private(output)
    assert output.stat().st_mode & 0o777 == 0o400
    with pytest.raises(FileExistsError):
        mint(material, "manager", output)
    assert read_private(output) == original
    assert capsys.readouterr() == ("", "")
    with pytest.raises(FileExistsError):
        initialize(material)
    with pytest.raises(ValueError, match="unknown"):
        mint(material, "service", tmp_path / "service.jwt")
    symlink = tmp_path / "link"
    symlink.symlink_to(output)
    with pytest.raises(OSError):
        read_private(symlink)
    output.chmod(0o644)
    with pytest.raises(ValueError, match="unsafe"):
        read_private(output)
    output.chmod(0o400)
    os.link(output, tmp_path / "hardlink")
    with pytest.raises(ValueError, match="unsafe"):
        read_private(output)


def test_unsafe_output_parent_creates_no_token(material, tmp_path):
    directory = tmp_path / "public"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)  # Make the adversarial mode independent of operator umask.
    output = directory / "token.jwt"
    with pytest.raises(ValueError, match="output directory must be private and owned"):
        mint(material, "contributor", output)
    assert not output.exists()


def test_private_jwk_is_rejected_before_serving(material, tmp_path):
    document = json.loads(read_private(material / "jwks.json"))
    document["keys"][0]["d"] = "private-material-must-not-be-served"
    path = tmp_path / "private-jwk.json"
    path.write_text(json.dumps(document))
    path.chmod(0o400)
    with pytest.raises(ValueError, match="expected one public RSA key"):
        make_server(
            path, material / "tls.pem", material / "tls-key.pem", "127.0.0.1", 0
        )


def test_transport_command_preserves_identity_and_requires_new_directory(
    material, tmp_path, monkeypatch, capsys
):
    original = {path.name: read_private(path) for path in material.iterdir()}
    directory = tmp_path / "transport"
    monkeypatch.setattr(
        sys,
        "argv",
        ["fixture.py", "init-transport", "--directory", str(directory)],
    )
    assert main() == 0
    assert capsys.readouterr() == ("", "")
    assert {path.name for path in directory.iterdir()} == {
        "ca.pem",
        "tls.pem",
        "tls-key.pem",
    }
    assert directory.stat().st_mode & 0o777 == 0o700
    transport = {path.name: read_private(path) for path in directory.iterdir()}
    assert all(path.stat().st_mode & 0o777 == 0o400 for path in directory.iterdir())
    for name, days in (("ca.pem", 7), ("tls.pem", 3)):
        certificate = x509.load_pem_x509_certificate(transport[name])
        assert certificate.not_valid_after_utc - certificate.not_valid_before_utc == (
            timedelta(days=days, minutes=1)
        )
    with pytest.raises(SystemExit) as denied:
        main()
    assert denied.value.code == 1
    assert capsys.readouterr() == (
        "",
        "Drill fixture failed; inspect private inputs without exposing their contents.\n",
    )
    assert {path.name: read_private(path) for path in directory.iterdir()} == transport
    assert {path.name: read_private(path) for path in material.iterdir()} == original


def test_new_transport_serves_original_jwks_with_new_ca_only(
    material, tmp_path, monkeypatch
):
    original = {path.name: read_private(path) for path in material.iterdir()}
    token = issued(material, tmp_path)
    transport = tmp_path / "transport"
    monkeypatch.setattr(
        sys,
        "argv",
        ["fixture.py", "init-transport", "--directory", str(transport)],
    )
    assert main() == 0
    roots = Path(certifi.where()).read_bytes()
    old_trust, new_trust = tmp_path / "old-trust.pem", tmp_path / "new-trust.pem"
    old_trust.write_bytes(roots + original["ca.pem"])
    new_trust.write_bytes(roots + read_private(transport / "ca.pem"))
    server = make_server(
        material / "jwks.json",
        transport / "tls.pem",
        transport / "tls-key.pem",
        "127.0.0.1",
        0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"https://127.0.0.1:{server.server_port}/jwks.json"
    try:
        monkeypatch.setattr(certifi, "where", lambda: str(old_trust))
        with pytest.raises(AuthVerificationUnavailableError):
            asyncio.run(verifier(url).verify(token))
        monkeypatch.setattr(certifi, "where", lambda: str(new_trust))
        with httpx.Client(trust_env=False) as client:
            response = client.get(url)
            assert response.status_code == 200
            assert response.json() == json.loads(original["jwks.json"])
        verified = asyncio.run(verifier(url).verify(token)).token
        assert verified.subject == json.loads(original["subjects.json"])["contributor"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert {path.name: read_private(path) for path in material.iterdir()} == original
