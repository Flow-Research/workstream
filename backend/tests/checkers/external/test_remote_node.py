"""Dedicated runner authentication, material binding and cleanup proofs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import ssl
import struct

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

from app.adapters.checkers.remote_model_bridge import RemoteModelProxyBridge


_SPEC = importlib.util.spec_from_file_location(
    "workstream_remote_node",
    Path(__file__).resolve().parents[4] / "external_checkers/remote_node.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_REMOTE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_REMOTE)


def _certificate_files(tmp_path: Path) -> dict[str, Path]:
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "runner-test-ca")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    def issue(name: str, usage: ExtendedKeyUsageOID) -> tuple[bytes, bytes]:
        key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        return (
            certificate.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        )

    values = {"ca": ca.public_bytes(serialization.Encoding.PEM)}
    server_certificate, server_key = issue("runner.test", ExtendedKeyUsageOID.SERVER_AUTH)
    client_certificate, client_key = issue("app.test", ExtendedKeyUsageOID.CLIENT_AUTH)
    values.update(
        server_certificate=server_certificate,
        server_key=server_key,
        client_certificate=client_certificate,
        client_key=client_key,
    )
    paths = {}
    for name, value in values.items():
        path = tmp_path / f"{name}.pem"
        path.write_bytes(value)
        path.chmod(0o600)
        paths[name] = path
    return paths


async def _read_frame(reader: asyncio.StreamReader) -> bytes:
    size = struct.unpack(">I", await reader.readexactly(4))[0]
    return await reader.readexactly(size)


def _frame(value: bytes) -> bytes:
    return struct.pack(">I", len(value)) + value


@pytest.mark.asyncio
async def test_remote_post_stages_bound_material_and_removes_session(tmp_path: Path):
    certificates = _certificate_files(tmp_path)
    material_root = tmp_path / "materials"
    material_root.mkdir(mode=0o700)
    socket_path = tmp_path / "native.sock"
    grant_id = "extract_" + "a" * 32
    request_digest = "sha256:" + "b" * 64
    content = b"remote material\n"
    content_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    observed = asyncio.Event()

    async def native(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = json.loads(await _read_frame(reader))
        root = material_root / "workspaces" / grant_id
        path = root / "materials" / "submission_archive" / "work.txt"
        assert request["request"]["request_digest"] == request_digest
        assert path.read_bytes() == content
        assert path.stat().st_mode & 0o777 == 0o400
        assert (root / ".external-checker-grant.json").stat().st_mode & 0o777 == 0o400
        observed.set()
        writer.write(_frame(b'{"native":"ok"}'))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    native_server = await asyncio.start_unix_server(native, socket_path)
    node = _REMOTE.RemoteNode(
        {
            "listen_host": "127.0.0.1",
            "listen_port": 1,
            "client_name": "app.test",
            "socket_path": str(socket_path),
            "model_proxy_socket_path": str(tmp_path / "model-proxy.sock"),
            "material_root": str(material_root),
            "tls_certificate_path": str(certificates["server_certificate"]),
            "tls_private_key_path": str(certificates["server_key"]),
            "tls_ca_path": str(certificates["ca"]),
            "session_timeout_seconds": 10,
        }
    )
    server = await asyncio.start_server(
        node.handle, "127.0.0.1", 0, ssl=node.ssl_context,
    )
    port = server.sockets[0].getsockname()[1]
    client_context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH, cafile=str(certificates["ca"])
    )
    client_context.minimum_version = ssl.TLSVersion.TLSv1_3
    client_context.load_cert_chain(
        certificates["client_certificate"], certificates["client_key"]
    )

    material = {
        "phase": "post_submit",
        "role": "submission_archive",
    }
    manifest_body = {
        "protocol_version": _REMOTE.GRANT_PROTOCOL,
        "grant_id": grant_id,
        "request_digest": request_digest,
        "phase": "post_submit",
        "identity": {},
        "evaluation_context_sha256": None,
        "materials": [
            {
                "material": material,
                "directories": [],
                "files": [
                    {
                        "normalized_path": "work.txt",
                        "byte_count": len(content),
                        "sha256": content_digest,
                        "executable": False,
                    }
                ],
            }
        ],
        "visible_roles": ["submission_archive"],
    }
    canonical = json.dumps(
        manifest_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    binding = "sha256:" + hashlib.sha256(canonical).hexdigest()
    manifest = json.dumps(
        {**manifest_body, "binding_digest": binding},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    service_request = {
        "protocol_version": "external_checker_service.v1",
        "operation": "execute",
        "request": {"request_digest": request_digest},
        "grant": {"grant_id": grant_id, "binding_digest": binding},
        "model_grant": None,
    }
    control = json.dumps(
        {
            "protocol_version": _REMOTE.PROTOCOL,
            "operation": "execute",
            "capability": _REMOTE.CHECKER_CAPABILITY,
            "service_request": service_request,
            "manifest_byte_count": len(manifest),
            "file_count": 1,
            "total_byte_count": len(content),
        },
        separators=(",", ":"),
    ).encode()

    try:
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port, ssl=client_context, server_hostname="runner.test"
        )
        writer.write(_frame(control) + _frame(manifest) + _frame(content) + struct.pack(">I", 0))
        await writer.drain()
        assert await _read_frame(reader) == b'{"native":"ok"}'
        await asyncio.wait_for(observed.wait(), 1)
        writer.close()
        await writer.wait_closed()
        for _ in range(100):
            if not list((material_root / "workspaces").iterdir()):
                break
            await asyncio.sleep(0.01)
        assert list((material_root / "workspaces").iterdir()) == []
    finally:
        server.close()
        native_server.close()
        await server.wait_closed()
        await native_server.wait_closed()


@pytest.mark.asyncio
async def test_model_callback_uses_outbound_authenticated_bridge(tmp_path: Path):
    certificates = _certificate_files(tmp_path)
    material_root = tmp_path / "materials"
    material_root.mkdir(mode=0o700)
    native_path = tmp_path / "native.sock"
    app_proxy_path = tmp_path / "app-model.sock"
    runner_proxy_path = tmp_path / "runner-model.sock"

    async def app_proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await _read_frame(reader)
        writer.write(_frame(b"app:" + request))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    native_server = await asyncio.start_unix_server(
        lambda _reader, writer: writer.close(), native_path
    )
    app_server = await asyncio.start_unix_server(app_proxy, app_proxy_path)
    node = _REMOTE.RemoteNode(
        {
            "listen_host": "127.0.0.1",
            "listen_port": 1,
            "client_name": "app.test",
            "socket_path": str(native_path),
            "model_proxy_socket_path": str(runner_proxy_path),
            "material_root": str(material_root),
            "tls_certificate_path": str(certificates["server_certificate"]),
            "tls_private_key_path": str(certificates["server_key"]),
            "tls_ca_path": str(certificates["ca"]),
            "session_timeout_seconds": 10,
        }
    )
    await node.start_model_proxy()
    server = await asyncio.start_server(
        node.handle, "127.0.0.1", 0, ssl=node.ssl_context,
    )
    port = server.sockets[0].getsockname()[1]
    bridge = RemoteModelProxyBridge(
        host="127.0.0.1",
        port=port,
        server_name="runner.test",
        ca_path=certificates["ca"],
        certificate_path=certificates["client_certificate"],
        private_key_path=certificates["client_key"],
        socket_path=app_proxy_path,
    )
    try:
        await bridge.start()
        for _ in range(100):
            if node._model_bridge is not None:
                break
            await asyncio.sleep(0.01)
        assert node._model_bridge is not None
        reader, writer = await asyncio.open_unix_connection(runner_proxy_path)
        writer.write(_frame(b"bound model call"))
        await writer.drain()
        assert await _read_frame(reader) == b"app:bound model call"
        writer.close()
        await writer.wait_closed()
    finally:
        await bridge.close()
        server.close()
        native_server.close()
        app_server.close()
        await server.wait_closed()
        await native_server.wait_closed()
        await app_server.wait_closed()
        await node.close()
