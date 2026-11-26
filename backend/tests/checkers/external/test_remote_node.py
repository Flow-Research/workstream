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


def _placement_body():
    return {
        "protocol_version": "external_checker_service.v1", "operation": "placement",
        "config_sha256": "sha256:" + "a" * 64, "epoch": "e" * 64,
        "health": {"operating_system": "linux", "architecture": "amd64", "runtime": "smolvm",
                   "isolation_mode": "smol-microvm", "cached_platform_manifests": 1,
                   "sandbox_uid": 10001, "sandbox_gid": 10001},
        "draining": False, "drained": False, "fits_admission": None,
        "images": [{"platform_manifest_digest": "sha256:" + "b" * 64,
                    "config_image_id": "sha256:" + "c" * 64}],
        "pre": {"profile_sha256": "sha256:" + "d" * 64, "root_sha256": "sha256:" + "f" * 64},
        "intake": None, "callback_relay": False, "trial_authority_manifest_sha256": None,
    }


def fixture_runner_endpoints(port=1, *, config_sha256=None):
    from app.core.runner_endpoints import ExternalRunnerEndpoints

    return ExternalRunnerEndpoints.model_validate([{
        "host": "127.0.0.1", "port": port, "server_name": "runner.test",
        "config_sha256": config_sha256 or _placement_body()["config_sha256"],
    }])


def fixture_placement(image_digest=None, config_image_id=None, **changes):
    data = _placement_body() | changes
    if image_digest is not None:
        data["images"][0]["platform_manifest_digest"] = image_digest
    if config_image_id is not None:
        data["images"][0]["config_image_id"] = config_image_id
    return data


async def read_fixture_native_request(reader, writer, placement):
    """Distinguish the read-only native projection from one epoch-bound execution."""
    control = json.loads(await _read_frame(reader))
    if control["operation"] == "placement":
        assert set(control) == {"protocol_version", "operation", "demand"}
        assert control["protocol_version"] == "external_checker_service.v1"
        body = placement | {"fits_admission": None if control["demand"] is None else True}
        writer.write(_frame(json.dumps(body).encode()))
        await writer.drain()
        return None
    assert control == {
        "protocol_version": "external_checker_service.v1", "operation": "bind_epoch",
        "config_sha256": placement["config_sha256"], "epoch": placement["epoch"],
    }
    return json.loads(await _read_frame(reader))


def test_external_runner_endpoint_set_is_closed_and_unique():
    from pydantic import ValidationError

    from app.core.runner_endpoints import ExternalRunnerEndpoints

    endpoint = {"host": "127.0.0.1", "port": 9443, "server_name": "runner.test",
                "config_sha256": "sha256:" + "a" * 64}
    assert ExternalRunnerEndpoints.model_validate_json(json.dumps([endpoint])).root[0].port == 9443
    for invalid in ([], [endpoint] * 9, [endpoint | {"port": "9443"}],
                    [endpoint | {"host": "127.0.0.1 "}], [endpoint | {"server_name": "*.test"}],
                    [endpoint | {"config_sha256": "stale"}], [endpoint | {"legacy_name": "x"}],
                    [endpoint, endpoint | {"server_name": "others.test"}],
                    [endpoint, endpoint | {"port": 9444}]):
        with pytest.raises(ValidationError):
            ExternalRunnerEndpoints.model_validate_json(json.dumps(invalid))


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [None, "config", "epoch", "extra", "trailing"])
async def test_runner_placement_probe_authenticates_loaded_identity(tmp_path, changed):
    from app.adapters.runner import RunnerTransport
    from app.core.runner_endpoints import ExternalRunnerEndpoints

    certificates = _certificate_files(tmp_path)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(certificates["server_certificate"], certificates["server_key"])
    context.load_verify_locations(certificates["ca"])
    body = _placement_body()
    expected_config = body["config_sha256"]
    if changed == "config":
        body["config_sha256"] = "sha256:" + "0" * 64
    if changed == "epoch":
        body["epoch"] = "unbound"
    if changed == "extra":
        body["unexpected"] = "value"
    requests = []

    async def observe(reader, writer):
        try:
            requests.append(json.loads(await _read_frame(reader)))
            writer.write(_frame(json.dumps(body).encode()) + (b"x" if changed == "trailing" else b""))
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(observe, "127.0.0.1", 0, ssl=context)
    async with server:
        endpoints = ExternalRunnerEndpoints.model_validate([{
            "host": "127.0.0.1", "port": server.sockets[0].getsockname()[1], "server_name": "runner.test",
            "config_sha256": expected_config,
        }])
        transport = RunnerTransport(endpoints, certificates["ca"], certificates["client_certificate"],
                                    certificates["client_key"])
        matched = await transport.select("attempt-1", qualifies=lambda readiness: readiness.pre is not None)
        if changed is None:
            assert matched is not None and matched.readiness.epoch == body["epoch"]
            assert matched.readiness.images[0].config_image_id == body["images"][0]["config_image_id"]
        else:
            assert matched is None
    assert requests == [{"protocol_version": "workstream.remote_runner.v1", "operation": "placement", "demand": None}]


@pytest.mark.asyncio
async def test_runner_selection_uses_only_qualified_ready_targets(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.adapters.runner import RunnerPlacement, RunnerReadiness, RunnerTransport
    from app.core.runner_endpoints import ExternalRunnerEndpoints

    endpoints = ExternalRunnerEndpoints.model_validate([
        {"host": "127.0.0.1", "port": 9443 + index, "server_name": f"{name}.test",
         "config_sha256": "sha256:" + "a" * 64}
        for index, name in enumerate(("qualified-a", "qualified-b", "drained", "other-profile", "full", "unreachable"))
    ])
    calls = []

    demand = {"kind": "pre", "source_bytes": 200}

    async def probe(_transport, endpoint, *, demand):
        assert demand == {"kind": "pre", "source_bytes": 200}
        calls.append(endpoint.server_name)
        state = _placement_body()
        state["fits_admission"] = True
        if endpoint.server_name == "drained.test":
            state.update(draining=True, fits_admission=False)
        if endpoint.server_name == "full.test":
            state.update(fits_admission=False)
        if endpoint.server_name == "other-profile.test":
            state["pre"]["profile_sha256"] = "sha256:" + "0" * 64
        if endpoint.server_name == "unreachable.test":
            return None
        return RunnerPlacement(endpoint, RunnerReadiness.model_validate_json(json.dumps(state)))

    monkeypatch.setattr(RunnerTransport, "probe", probe)
    transport = RunnerTransport(endpoints, tmp_path, tmp_path, tmp_path)
    reordered = RunnerTransport(ExternalRunnerEndpoints(tuple(reversed(endpoints.root))), tmp_path, tmp_path, tmp_path)

    def qualifies(readiness):
        return readiness.pre.profile_sha256 == "sha256:" + "d" * 64

    chosen = await transport.select("stable-attempt", qualifies=qualifies, demand=demand)
    assert chosen == await reordered.select("stable-attempt", qualifies=qualifies, demand=demand)
    assert chosen.endpoint.server_name in {"qualified-a.test", "qualified-b.test"}
    assert len(calls) == 2 * len(endpoints.root)
    cert = SimpleNamespace(getpeercert=lambda: {"subjectAltName": (("DNS", "*.test"),)})
    with pytest.raises(ssl.SSLError, match="certificate identity differs"):
        transport.require_peer(cert, chosen.endpoint)


@pytest.mark.asyncio
async def test_runner_probe_aborts_without_waiting_for_tls_shutdown(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, Mock

    from app.adapters import runner
    from app.core.runner_endpoints import ExternalRunnerEndpoints

    async def no_result(*_args):
        await asyncio.Future()

    endpoints = ExternalRunnerEndpoints.model_validate([{
        "host": "127.0.0.1", "port": 9443, "server_name": "runner.test",
        "config_sha256": _placement_body()["config_sha256"],
    }])
    reader = Mock(readexactly=AsyncMock(side_effect=no_result))
    writer = Mock(drain=AsyncMock(), wait_closed=AsyncMock(side_effect=no_result))
    monkeypatch.setattr(runner.RunnerTransport, "open", AsyncMock(return_value=(reader, writer)))
    monkeypatch.setattr(runner, "_PROBE_SECONDS", 0.02)
    transport = runner.RunnerTransport(endpoints, tmp_path, tmp_path, tmp_path)
    assert await asyncio.wait_for(transport.select("claim", qualifies=lambda _state: True), 1) is None
    writer.transport.abort.assert_called_once_with()
    writer.wait_closed.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_claim_pins_first_runner_epoch(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from app.adapters.artifacts import selected_pre_submit_source_contracts
    from app.adapters.checkers.external_service import RemoteTlsExternalCheckerAdapter
    from app.adapters.runner import RunnerPlacement, RunnerReadiness, RunnerTransport
    from tests.checkers.external.test_model_transport import request
    from workstream_external_services import ExternalServiceUnavailableError

    value = request()
    endpoints = fixture_runner_endpoints()
    observed = RunnerReadiness.model_validate_json(json.dumps(fixture_placement(
        value.registry.image_digest, fits_admission=True,
    )))
    first = RunnerPlacement(endpoints.root[0], observed)
    restarted = RunnerPlacement(endpoints.root[0], observed.model_copy(update={"epoch": "a" * 64}))
    select = AsyncMock(side_effect=[first, restarted])
    monkeypatch.setattr(RunnerTransport, "select", select)
    adapter = RemoteTlsExternalCheckerAdapter(
        endpoints=endpoints, ca_path=tmp_path / "ca.pem", certificate_path=tmp_path / "client.pem",
        private_key_path=tmp_path / "key.pem", model_proxy_socket_path=None, timeout_seconds=90.0,
        source_contracts=selected_pre_submit_source_contracts(),
    )
    with pytest.raises(ExternalServiceUnavailableError):
        await adapter._place_post(value, with_model_grant=True)
    select.assert_not_awaited()
    assert await adapter._place_post(value, with_model_grant=False) is first
    assert await adapter._place_post(value, with_model_grant=False) is first
    assert select.await_count == 1
    with pytest.raises(ValueError, match="bound to another claim"):
        await adapter._place_post(request(), with_model_grant=False)
    assert select.await_count == 1


@asynccontextmanager
async def remote_adapter_endpoint(
    tmp_path: Path,
    native_socket_path: Path,
    *,
    model_proxy_socket_path: Path | None = None,
    material_root: Path | None = None,
    native_model_proxy_socket_path: Path | None = None,
    session_timeout_seconds: float = 10.0,
    config_sha256: str | None = None,
):
    """Expose one test-native service with explicit finite owner roots/windows."""
    certificates = _certificate_files(tmp_path)
    if material_root is None:
        material_root = tmp_path / f"runner-materials-{uuid4().hex}"
        material_root.mkdir(mode=0o700)
    runner_proxy_root = Path("/tmp") / f"ws-rm-{uuid4().hex[:12]}"
    runner_proxy_root.mkdir(mode=0o700)
    runner_proxy_path = native_model_proxy_socket_path or runner_proxy_root / "model.sock"
    node, remote = None, None
    try:
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
                "session_timeout_seconds": session_timeout_seconds,
            }
        )
        await node.start_model_proxy()
        remote = await asyncio.start_server(
            node.handle, "127.0.0.1", 0, ssl=node.ssl_context
        )
        yield {
            "endpoints": fixture_runner_endpoints(remote.sockets[0].getsockname()[1], config_sha256=config_sha256),
            "ca_path": certificates["ca"],
            "certificate_path": certificates["client_certificate"],
            "private_key_path": certificates["client_key"],
            "model_proxy_socket_path": model_proxy_socket_path,
        }
    finally:
        if remote is not None:
            remote.close()
            await remote.wait_closed()
        if node is not None:
            await node.close()
        runner_proxy_root.rmdir()


@pytest.mark.asyncio
async def test_remote_adapter_endpoint_preserves_explicit_roots_and_callback_routes(tmp_path, monkeypatch):
    """Actual production TLS forwards both callback frames on the owning execute."""
    import tempfile
    from app.adapters.artifacts import selected_pre_submit_source_contracts
    from app.adapters.checkers.external_service import RemoteTlsExternalCheckerAdapter
    from app.interfaces.external_checker_execution import ExternalCheckerModelGrant
    from app.modules.checkers.api.external import make_external_checker_execution_result
    from tests.checkers.external.support import empty_external_material_grant
    from tests.checkers.external.test_model_transport import request

    value = request()
    result = make_external_checker_execution_result(
        request_digest=value.request_digest, registry_entry_id=value.registry.registry_entry_id,
        registry_entry_digest=value.registry.entry_digest, phase="post_submit", outcome="infrastructure_failed",
        verdict=None, findings=(), infrastructure_failure_code="implementation_unavailable",
    )
    material = tmp_path / "runner-material"
    material.mkdir(mode=0o700)
    captured, callbacks, failures = [], [], []
    original_node = _REMOTE.RemoteNode
    def node(config):
        instance = original_node(config)
        captured.append(instance)
        return instance
    monkeypatch.setattr(_REMOTE, "RemoteNode", node)
    with tempfile.TemporaryDirectory(prefix="ws-ts-tls-") as temporary:
        sockets = Path(temporary)
        app_proxy, native_proxy, native_socket = (sockets / name for name in ("app", "runner", "native"))
        async def app(reader, writer):
            try:
                payload = await _read_frame(reader)
                callbacks.append(payload)
                writer.write(_frame(payload))
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        async def native(reader, writer):
            try:
                wire = await read_fixture_native_request(
                    reader, writer, fixture_placement(value.registry.image_digest, callback_relay=True),
                )
                if wire is None:
                    return
                grant_id = wire["grant"]["grant_id"]
                assert (material / "workspaces" / grant_id).is_dir()
                assert wire["model_grant"]["grant_id"] == "model_" + "a" * 32
                for payload in (b'{"callback":"model"}', b'{"callback":"trial"}'):
                    callback_reader, callback_writer = await asyncio.open_unix_connection(native_proxy)
                    callback_writer.write(_frame(payload))
                    await callback_writer.drain()
                    assert await _read_frame(callback_reader) == payload
                    callback_writer.close()
                    await callback_writer.wait_closed()
                writer.write(_frame(json.dumps({"protocol_version": "external_checker_service.v1",
                    "result": result.model_dump(mode="json"), "isolation": None}).encode()))
                await writer.drain()
            except BaseException as error:
                failures.append(error)
            finally:
                writer.close()
                await writer.wait_closed()
        native_server = await asyncio.start_unix_server(native, native_socket)
        app_server = await asyncio.start_unix_server(app, app_proxy)
        try:
            async with remote_adapter_endpoint(tmp_path, native_socket, model_proxy_socket_path=app_proxy,
                    material_root=material, native_model_proxy_socket_path=native_proxy,
                    session_timeout_seconds=720.0) as endpoint:
                assert captured[0].timeout == 720.0
                assert captured[0].material_root == material
                assert captured[0].model_proxy_socket_path == native_proxy
                adapter = RemoteTlsExternalCheckerAdapter(**endpoint, timeout_seconds=90.0,
                    source_contracts=selected_pre_submit_source_contracts())
                observed = await adapter.execute(value, empty_external_material_grant(value, suffix="c"),
                    model_grant=ExternalCheckerModelGrant("model_" + "a" * 32, value.request_digest))
                assert observed.result == result
            assert not native_proxy.exists()
            assert list((material / "workspaces").iterdir()) == []
            assert callbacks == [b'{"callback":"model"}', b'{"callback":"trial"}']
            assert failures == []
        finally:
            native_server.close()
            app_server.close()
            await native_server.wait_closed()
            await app_server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault,started", [("connect", False)] + [
    (fault, started) for fault in ("write", "eof", "invalid_result", "timeout", "cancel")
    for started in (False, True)
])
async def test_remote_post_failure_preserves_possible_invocation(tmp_path, monkeypatch, fault, started):
    from unittest.mock import AsyncMock, Mock

    from app.adapters.artifacts import selected_pre_submit_source_contracts
    from app.adapters.checkers.external_service import RemoteTlsExternalCheckerAdapter
    from app.adapters.runner import RunnerPlacement, RunnerReadiness, RunnerTransport
    from app.interfaces.external_checker_execution import ExternalCheckerExecutionOutcomeUnknown
    from tests.checkers.external.support import empty_external_material_grant
    from tests.checkers.external.test_model_transport import request
    from workstream_external_services import ExternalServiceProtocolError, ExternalServiceUnavailableError

    adapter = RemoteTlsExternalCheckerAdapter(
        endpoints=fixture_runner_endpoints(),
        ca_path=tmp_path / "ca.pem", certificate_path=tmp_path / "client.pem",
        private_key_path=tmp_path / "key.pem", model_proxy_socket_path=None,
        timeout_seconds=90.0, source_contracts=selected_pre_submit_source_contracts(),
    )
    reader = asyncio.StreamReader()
    writer = Mock(spec=asyncio.StreamWriter)
    drains = 0

    async def drain():
        nonlocal drains
        drains += 1
        if fault == "write" and drains == (3 if started else 1):
            raise OSError

    writer.drain = AsyncMock(side_effect=drain)
    writer.wait_closed = AsyncMock()
    connect = AsyncMock(return_value=(reader, writer), side_effect=OSError if fault == "connect" else None)
    monkeypatch.setattr(adapter, "_open", connect)
    waiting = asyncio.Event()
    value = request()
    grant = empty_external_material_grant(value, suffix="c")
    if started:
        reader.feed_data(_frame(json.dumps({
            "protocol_version": "workstream.remote_runner.v1", "operation": "material_ready",
            "grant_id": grant.grant_id, "binding_digest": grant.binding_digest,
        }).encode()))
    original_read = reader.readexactly
    reads = 0

    async def interrupt_read(size):
        nonlocal reads
        reads += 1
        if started and reads <= 2:
            return await original_read(size)
        waiting.set()
        if fault == "timeout":
            raise TimeoutError
        await asyncio.Future()

    if fault in {"timeout", "cancel"}:
        monkeypatch.setattr(reader, "readexactly", interrupt_read)
    elif fault == "invalid_result":
        reader.feed_data(_frame(b'{"protocol_version":"workstream.remote_runner.v1",'
                                b'"operation":"execution_result"}') + _frame(b'{}'))
    reader.feed_eof()

    placement = RunnerPlacement(adapter._transport.endpoints.root[0], RunnerReadiness.model_validate_json(
        json.dumps(fixture_placement(value.registry.image_digest, fits_admission=True)),
    ))
    monkeypatch.setattr(RunnerTransport, "select", AsyncMock(return_value=placement))
    task = asyncio.create_task(adapter.execute(value, grant))
    if fault == "cancel":
        await asyncio.wait_for(waiting.wait(), 1)
        task.cancel()
    expected = (
        ExternalCheckerExecutionOutcomeUnknown if started
        else asyncio.CancelledError if fault == "cancel"
        else ExternalServiceProtocolError if fault == "invalid_result"
        else ExternalServiceUnavailableError
    )
    with pytest.raises(expected):
        await asyncio.wait_for(task, 2)
    connect.assert_awaited_once_with(placement)
    if fault == "connect":
        writer.write.assert_not_called()
    else:
        control = json.loads(writer.write.call_args_list[0].args[0][4:])
        assert control["service_request"]["request"]["request_digest"] == value.request_digest
        writer.close.assert_called_once_with()
        writer.wait_closed.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_remote_adapter_endpoint_invalid_explicit_root_cleans_helper_socket_root(tmp_path, monkeypatch):
    """Fail before native contact and leave no helper-owned directory on rejection."""
    identity = uuid4()
    monkeypatch.setitem(remote_adapter_endpoint.__wrapped__.__globals__, "uuid4", lambda: identity)
    material = tmp_path / "public-material"
    material.mkdir(mode=0o755)
    root = Path("/tmp") / f"ws-rm-{identity.hex[:12]}"
    assert not root.exists()
    private = tmp_path / "private-material"
    private.mkdir(mode=0o700)
    async with remote_adapter_endpoint(tmp_path, tmp_path / "no-native.sock", material_root=private):
        assert root.is_dir()
    assert not root.exists()
    with pytest.raises(ValueError, match="material root is not private"):
        async with remote_adapter_endpoint(tmp_path, tmp_path / "no-native.sock", material_root=material):
            raise AssertionError("invalid material root entered native execution")
    assert not root.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("start_mode", ["execute", "disconnect", "wrong_binding"])
async def test_remote_post_stages_bound_material_and_removes_session(tmp_path: Path, start_mode, capsys):
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
    invoked = asyncio.Event()

    async def native(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        invoked.set()
        request = await read_fixture_native_request(reader, writer, _placement_body())
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
            "epoch": _placement_body()["epoch"], "config_sha256": _placement_body()["config_sha256"],
        },
        separators=(",", ":"),
    ).encode()

    try:
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port, ssl=client_context, server_hostname="runner.test"
        )
        writer.write(_frame(control) + _frame(manifest) + _frame(content) + struct.pack(">I", 0))
        await writer.drain()
        ready = json.loads(await _read_frame(reader))
        assert ready == {
            "protocol_version": _REMOTE.PROTOCOL, "operation": "material_ready",
            "grant_id": grant_id, "binding_digest": binding,
        }
        assert not invoked.is_set()
        if start_mode == "disconnect":
            writer.close()
            await writer.wait_closed()
        else:
            start = dict(ready, operation="start_execution")
            if start_mode == "wrong_binding":
                start["binding_digest"] = "sha256:" + "0" * 64
            writer.write(_frame(json.dumps(start).encode()))
            await writer.drain()
        if start_mode != "execute":
            if start_mode == "wrong_binding":
                assert await asyncio.wait_for(reader.read(), 2) == b""
                writer.close()
                await writer.wait_closed()
            for _ in range(100):
                if not list((material_root / "workspaces").iterdir()):
                    break
                await asyncio.sleep(0.01)
            assert not invoked.is_set()
            assert list((material_root / "workspaces").iterdir()) == []
            records = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
            assert any(row["stage"] == "awaiting_execution_start" and row["disposition"] == "interrupted" for row in records)
            assert records[-1]["stage"] == "material_cleanup"
            return
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
@pytest.mark.parametrize("exit_kind", ["disconnect", "timeout", "unbound"])
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
        control_value = {
            "protocol_version": _REMOTE.PROTOCOL,
            "operation": "proxy",
            "capability": _REMOTE.CHECKER_CAPABILITY,
            "epoch": _placement_body()["epoch"], "config_sha256": _placement_body()["config_sha256"],
        }
        if exit_kind == "unbound":
            del control_value["epoch"], control_value["config_sha256"]
        writer.write(_frame(json.dumps(control_value).encode()))
        await writer.drain()
        if exit_kind == "unbound":
            assert await asyncio.wait_for(reader.read(), 2) == b""
            writer.close()
            await writer.wait_closed()
            assert not native_started.is_set()
            return
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
