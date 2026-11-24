"""Dedicated runner authentication, material binding and cleanup proofs."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import ssl
import struct
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

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


@asynccontextmanager
async def remote_adapter_endpoint(
    tmp_path: Path,
    native_socket_path: Path,
    *,
    model_proxy_socket_path: Path | None = None,
):
    """Expose one test-native Unix service through the production TLS edge."""
    certificates = _certificate_files(tmp_path)
    material_root = tmp_path / f"runner-materials-{uuid4().hex}"
    material_root.mkdir(mode=0o700)
    runner_proxy_root = Path("/tmp") / f"ws-rm-{uuid4().hex[:12]}"
    runner_proxy_root.mkdir(mode=0o700)
    runner_proxy_path = runner_proxy_root / "model.sock"
    node = _REMOTE.RemoteNode(
        {
            "listen_host": "127.0.0.1",
            "listen_port": 1,
            "client_name": "app.test",
            "socket_path": str(native_socket_path),
            "model_proxy_socket_path": str(runner_proxy_path),
            "material_root": str(material_root),
            "tls_certificate_path": str(certificates["server_certificate"]),
            "tls_private_key_path": str(certificates["server_key"]),
            "tls_ca_path": str(certificates["ca"]),
            "session_timeout_seconds": 10,
        }
    )
    await node.start_model_proxy()
    remote = await asyncio.start_server(
        node.handle, "127.0.0.1", 0, ssl=node.ssl_context
    )
    try:
        yield {
            "host": "127.0.0.1",
            "port": remote.sockets[0].getsockname()[1],
            "server_name": "runner.test",
            "ca_path": certificates["ca"],
            "certificate_path": certificates["client_certificate"],
            "private_key_path": certificates["client_key"],
            "model_proxy_socket_path": model_proxy_socket_path,
        }
    finally:
        remote.close()
        await remote.wait_closed()
        await node.close()
        runner_proxy_root.rmdir()


@pytest.mark.asyncio
async def test_remote_post_stages_bound_material_and_removes_session(tmp_path: Path):
    certificates = _certificate_files(tmp_path)
    material_root = tmp_path / "materials"
    material_root.mkdir(mode=0o700)
    socket_path = tmp_path / "native.sock"
    runner_proxy_path = tmp_path / "runner-model.sock"
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
        callback_reader, callback_writer = await asyncio.open_unix_connection(runner_proxy_path)
        callback_writer.write(_frame(b'{"protocol_version":"workstream.setup_model_proxy.v1"}'))
        await callback_writer.drain()
        assert await _read_frame(callback_reader) == b'{"callback":"ok"}'
        callback_writer.close()
        await callback_writer.wait_closed()
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
        callback_header = json.loads(await _read_frame(reader))
        assert callback_header["operation"] == "callback_request"
        assert await _read_frame(reader) == b'{"protocol_version":"workstream.setup_model_proxy.v1"}'
        writer.write(
            _frame(json.dumps({
                "protocol_version": _REMOTE.PROTOCOL,
                "operation": "callback_response",
                "channel_id": callback_header["channel_id"],
            }, separators=(",", ":")).encode())
            + _frame(b'{"callback":"ok"}')
        )
        await writer.drain()
        assert json.loads(await _read_frame(reader)) == {
            "protocol_version": _REMOTE.PROTOCOL,
            "operation": "execution_result",
        }
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
        await node.close()


@pytest.mark.asyncio
async def test_callback_is_pinned_to_exact_active_execute_connection(tmp_path: Path):
    certificates = _certificate_files(tmp_path)
    material_root = tmp_path / "materials"
    material_root.mkdir(mode=0o700)
    native_path = tmp_path / "native.sock"
    runner_proxy_path = tmp_path / "runner-model.sock"
    native_server = await asyncio.start_unix_server(
        lambda _reader, writer: writer.close(), native_path
    )
    node = _REMOTE.RemoteNode(
        {
            "listen_host": "127.0.0.1", "listen_port": 1, "client_name": "app.test",
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

    async def stream_pair():
        first, second = socket.socketpair()
        return (
            await asyncio.open_connection(sock=first),
            await asyncio.open_connection(sock=second),
        )

    (a_reader, a_writer), (a_peer_reader, a_peer_writer) = await stream_pair()
    (b_reader, b_writer), (b_peer_reader, b_peer_writer) = await stream_pair()
    channel_a = _REMOTE.ExecutionChannel(a_reader, a_writer)
    channel_b = _REMOTE.ExecutionChannel(b_reader, b_writer)

    async def answer(reader, writer, prefix):
        header = json.loads(await _read_frame(reader))
        payload = await _read_frame(reader)
        writer.write(
            _frame(json.dumps({
                "protocol_version": _REMOTE.PROTOCOL,
                "operation": "callback_response",
                "channel_id": header["channel_id"],
            }, separators=(",", ":")).encode())
            + _frame(prefix + payload)
        )
        await writer.drain()

    try:
        node._active_channel = channel_a
        answer_a = asyncio.create_task(answer(a_peer_reader, a_peer_writer, b"a:"))
        reader, writer = await asyncio.open_unix_connection(runner_proxy_path)
        writer.write(_frame(b"bound callback"))
        await writer.drain()
        assert await _read_frame(reader) == b"a:bound callback"
        await answer_a
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(_read_frame(b_peer_reader), 0.05)
        writer.close()
        await writer.wait_closed()

        a_peer_writer.close()
        await a_peer_writer.wait_closed()
        await asyncio.wait_for(channel_a.closed.wait(), 1)
        reader, writer = await asyncio.open_unix_connection(runner_proxy_path)
        writer.write(_frame(b"lost owner"))
        await writer.drain()
        assert await reader.read() == b""
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(_read_frame(b_peer_reader), 0.05)
        writer.close()
        await writer.wait_closed()

        node._active_channel = channel_b
        answer_b = asyncio.create_task(answer(b_peer_reader, b_peer_writer, b"b:"))
        reader, writer = await asyncio.open_unix_connection(runner_proxy_path)
        writer.write(_frame(b"next invocation"))
        await writer.drain()
        assert await _read_frame(reader) == b"b:next invocation"
        await answer_b
        writer.close()
        await writer.wait_closed()
    finally:
        node._active_channel = None
        await channel_a.close()
        await channel_b.close()
        for writer in (a_peer_writer, b_peer_writer):
            writer.close()
            await writer.wait_closed()
        native_server.close()
        await native_server.wait_closed()
        await node.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_kind", ["disconnect", "timeout"])
async def test_proxy_exit_closes_native_connection_and_copy_tasks(
    tmp_path: Path, exit_kind: str,
):
    certificates = _certificate_files(tmp_path)
    material_root = tmp_path / "materials"
    material_root.mkdir(mode=0o700)
    native_path = tmp_path / "native.sock"
    native_started = asyncio.Event()
    native_closed = asyncio.Event()

    async def native(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        native_started.set()
        await reader.read()
        native_closed.set()
        writer.close()
        await writer.wait_closed()

    native_server = await asyncio.start_unix_server(native, native_path)
    node = _REMOTE.RemoteNode(
        {
            "listen_host": "127.0.0.1", "listen_port": 1, "client_name": "app.test",
            "socket_path": str(native_path),
            "model_proxy_socket_path": str(tmp_path / "runner-model.sock"),
            "material_root": str(material_root),
            "tls_certificate_path": str(certificates["server_certificate"]),
            "tls_private_key_path": str(certificates["server_key"]),
            "tls_ca_path": str(certificates["ca"]),
            "session_timeout_seconds": 1,
        }
    )
    server = await asyncio.start_server(node.handle, "127.0.0.1", 0, ssl=node.ssl_context)
    client_context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH, cafile=str(certificates["ca"])
    )
    client_context.minimum_version = ssl.TLSVersion.TLSv1_3
    client_context.load_cert_chain(
        certificates["client_certificate"], certificates["client_key"]
    )
    try:
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", server.sockets[0].getsockname()[1],
            ssl=client_context, server_hostname="runner.test",
        )
        control = json.dumps({
            "protocol_version": _REMOTE.PROTOCOL,
            "operation": "proxy",
            "capability": _REMOTE.CHECKER_CAPABILITY,
        }, separators=(",", ":")).encode()
        writer.write(_frame(control))
        await writer.drain()
        await asyncio.wait_for(native_started.wait(), 1)
        if exit_kind == "disconnect":
            writer.close()
            await writer.wait_closed()
        else:
            assert await asyncio.wait_for(reader.read(), 2) == b""
            writer.close()
            await writer.wait_closed()
        await asyncio.wait_for(native_closed.wait(), 1)
    finally:
        server.close()
        native_server.close()
        await server.wait_closed()
        await native_server.wait_closed()


@pytest.mark.parametrize("residue_name", [".incoming-" + "a" * 32, "extract_" + "b" * 32])
def test_restart_fails_closed_until_stopped_native_residue_is_reconciled(
    tmp_path: Path, residue_name: str,
):
    certificates = _certificate_files(tmp_path)
    material_root = tmp_path / "materials"
    workspaces = material_root / "workspaces"
    workspaces.mkdir(parents=True, mode=0o700)
    material_root.chmod(0o700)
    residue = workspaces / residue_name
    residue.mkdir(mode=0o700)
    retained = residue / "retained.bin"
    retained.write_bytes(b"sensitive staged bytes")
    retained.chmod(0o400)
    native_path = tmp_path / "native.sock"
    native = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    native.bind(str(native_path))
    config = {
        "listen_host": "127.0.0.1", "listen_port": 1, "client_name": "app.test",
        "socket_path": str(native_path),
        "model_proxy_socket_path": str(tmp_path / "runner-model.sock"),
        "material_root": str(material_root),
        "tls_certificate_path": str(certificates["server_certificate"]),
        "tls_private_key_path": str(certificates["server_key"]),
        "tls_ca_path": str(certificates["ca"]),
        "session_timeout_seconds": 10,
    }
    with pytest.raises(ValueError, match="requires reconciliation"):
        _REMOTE.RemoteNode(config)
    with pytest.raises(ValueError, match="native service must be stopped"):
        _REMOTE._reconcile_stale_workspaces(config)
    native.close()
    native_path.unlink()
    assert _REMOTE._reconcile_stale_workspaces(config) == 1
    assert list(workspaces.iterdir()) == []
    _REMOTE.RemoteNode(config)
