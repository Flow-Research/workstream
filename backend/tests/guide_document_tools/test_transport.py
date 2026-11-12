"""Transport, cancellation, and socket-custody proof for the parser service."""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from app.adapters.guide_document_tools import (
    GUIDE_DOCUMENT_PARSER_PROTOCOL,
    GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    GuideDocumentParserRequest,
    UnixSocketGuideDocumentParserAdapter,
    guide_document_parser_factory,
)
from app.adapters.guide_document_tools.parsing import parse_document
from app.adapters.guide_document_tools.service import (
    GuideDocumentParserService,
    _healthcheck,
    _remove_owned_stale_socket,
)
import app.adapters.guide_document_tools.service as service_module
from workstream_external_services import (
    ExternalServiceAdapterIdentity,
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)


@pytest.fixture(autouse=True)
def _unprivileged_service_seam(monkeypatch: pytest.MonkeyPatch):
    """Keep unit transport proof unprivileged without a production identity fallback."""
    monkeypatch.setattr(
        service_module,
        "_FIXED_CHILD_COMMAND",
        (
            sys.executable,
            "-c",
            "from app.adapters.guide_document_tools.child import _run_protocol;"
            "raise SystemExit(_run_protocol())",
        ),
    )
    monkeypatch.setattr(
        service_module,
        "_service_socket_identity",
        lambda: (os.geteuid(), os.getegid()),
    )
    monkeypatch.setattr(
        service_module,
        "_prepare_child_process",
        lambda _identity: None,
    )


def _request(source: bytes, *, offset: int = 0) -> GuideDocumentParserRequest:
    return GuideDocumentParserRequest(
        request_id=uuid4(),
        source_sha256=f"sha256:{sha256(source).hexdigest()}",
        source_byte_count=len(source),
        media_type="text/markdown",
        operation="read",
        offset=offset,
        limit=65_536,
    )


def _adapter(path: Path, *, timeout: float = 15.0) -> UnixSocketGuideDocumentParserAdapter:
    return UnixSocketGuideDocumentParserAdapter(
        socket_path=path,
        timeout_seconds=timeout,
        expected_socket_uid=os.geteuid(),
        expected_socket_gid=os.getegid(),
    )


def _service(
    path: Path,
    *,
    child_timeout: float = 8.0,
    read_timeout: float = 2.0,
) -> GuideDocumentParserService:
    path.parent.chmod(0o750)
    return GuideDocumentParserService(
        socket_path=path,
        child_timeout_seconds=child_timeout,
        request_read_timeout_seconds=read_timeout,
    )


async def _fake_server(path: Path, response: bytes) -> asyncio.AbstractServer:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            size = struct.unpack(">I", await reader.readexactly(4))[0]
            metadata = json.loads(await reader.readexactly(size))
            request = GuideDocumentParserRequest.model_validate(metadata["request"])
            await reader.readexactly(request.source_byte_count)
            writer.write(response)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, path)
    path.chmod(0o660)
    return server


def _response_frame(body: object) -> bytes:
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    return struct.pack(">I", len(raw)) + raw


def test_factory_uses_the_typed_external_service_identity(tmp_path: Path) -> None:
    adapter = guide_document_parser_factory(
        socket_path=tmp_path / "guide.sock",
        timeout_seconds=2.0,
        expected_socket_uid=os.geteuid(),
        expected_socket_gid=os.getegid(),
    ).create(GUIDE_DOCUMENT_PARSER_PROVIDER_KEY)

    assert adapter.identity == ExternalServiceAdapterIdentity(
        "guide_document_parser",
        "unix_socket",
    )


def test_request_contract_rejects_unknown_fields() -> None:
    source = b"guide"
    body = _request(source).model_dump(mode="json")
    body["source_path"] = "/forbidden"

    with pytest.raises(ValueError):
        GuideDocumentParserRequest.model_validate(body)


def test_child_environment_is_fixed_and_contains_no_parent_secrets() -> None:
    assert service_module._CHILD_ENVIRONMENT == {
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
    }
    first, second = service_module.CHILD_IDENTITIES
    assert service_module._child_environment(first) == {
        **service_module._CHILD_ENVIRONMENT,
        "WORKSTREAM_GUIDE_PARSER_CHILD_UID": "10003",
        "WORKSTREAM_GUIDE_PARSER_CHILD_GID": "10003",
    }
    assert (second.uid, second.gid) == (10004, 10004)


def test_service_rejects_more_concurrency_than_closed_child_slots(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="configuration"):
        GuideDocumentParserService(
            socket_path=tmp_path / "guide.sock",
            maximum_concurrency=3,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong", ["hash", "length"])
async def test_client_rejects_wrong_source_identity_before_transport(
    tmp_path: Path,
    wrong: str,
) -> None:
    source = b"guide"
    request = _request(source)
    if wrong == "hash":
        request = request.model_copy(update={"source_sha256": "sha256:" + "0" * 64})
    else:
        request = request.model_copy(update={"source_byte_count": len(source) + 1})

    with pytest.raises(ExternalServiceProtocolError):
        await _adapter(tmp_path / "absent.sock").parse(request, source)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    ["unknown_field", "mismatched_binding", "wrong_response_hash", "partial_frame"],
)
async def test_client_rejects_malformed_or_truncated_responses(
    tmp_path: Path,
    invalid: str,
) -> None:
    source = b"guide"
    request = _request(source)
    result = parse_document(request, source).model_dump(mode="json")
    body: dict[str, object] = {
        "protocol_version": GUIDE_DOCUMENT_PARSER_PROTOCOL,
        "status": "ok",
        "result": result,
    }
    if invalid == "unknown_field":
        body["unexpected"] = True
        response = _response_frame(body)
    elif invalid == "mismatched_binding":
        result["source_sha256"] = "sha256:" + "0" * 64
        response = _response_frame(body)
    elif invalid == "wrong_response_hash":
        result["response_hash"] = "sha256:" + "0" * 64
        response = _response_frame(body)
    else:
        response = struct.pack(">I", 100) + b"{"
    path = tmp_path / "guide.sock"
    server = await _fake_server(path, response)
    try:
        with pytest.raises((ExternalServiceProtocolError, ExternalServiceUnavailableError)):
            await _adapter(path).parse(request, source)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_service_parses_concurrent_sources_without_cross_request_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime" / "guide.sock"
    path.parent.mkdir()
    service = _service(path)
    await service.start()
    try:
        first_source = b"first private guide"
        second_source = b"second isolated guide"
        first, second = await asyncio.gather(
            _adapter(path).parse(_request(first_source), first_source),
            _adapter(path).parse(_request(second_source), second_source),
        )
        assert first.text == first_source.decode()
        assert second.text == second_source.decode()
        assert first.source_sha256 != second.source_sha256
        assert await _healthcheck(path) == 0
    finally:
        await service.close()
    assert not path.exists()


def test_sigterm_closes_service_and_removes_owned_socket(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "guide.sock"
    path.parent.mkdir()
    path.parent.chmod(0o750)
    program = """
import os
import sys
from app.adapters.guide_document_tools import service

service.bootstrap_broker_identity = lambda: None
service._service_socket_identity = lambda: (os.geteuid(), os.getegid())
sys.argv = ["guide-parser-sigterm-test", "--socket", sys.argv[1]]
raise SystemExit(service.main())
"""
    process = subprocess.Popen(
        [sys.executable, "-c", program, str(path)],
        cwd=Path(service_module.__file__).resolve().parents[3],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not path.is_socket():
            if process.poll() is not None:
                break
            time.sleep(0.01)
        assert process.poll() is None
        assert path.is_socket()

        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5)

        assert process.returncode == 0, (stdout, stderr)
        assert not path.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if path.exists() or path.is_symlink():
            path.unlink()


@pytest.mark.asyncio
async def test_partial_request_frame_is_aborted(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "guide.sock"
    path.parent.mkdir()
    service = _service(path, read_timeout=0.1)
    await service.start()
    try:
        reader, writer = await asyncio.open_unix_connection(path)
        writer.write(struct.pack(">I", 100) + b"{")
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), timeout=1.0) == b""
        writer.close()
        await writer.wait_closed()
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_admission_limit_closes_excess_connections(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "guide.sock"
    path.parent.mkdir()
    path.parent.chmod(0o750)
    service = GuideDocumentParserService(
        socket_path=path,
        maximum_concurrency=1,
        maximum_admitted_connections=1,
        request_read_timeout_seconds=1.0,
        child_timeout_seconds=1.0,
    )
    await service.start()
    first_reader, first_writer = await asyncio.open_unix_connection(path)
    try:
        first_writer.write(struct.pack(">I", 100) + b"{")
        await first_writer.drain()
        await asyncio.sleep(0.01)
        second_reader, second_writer = await asyncio.open_unix_connection(path)
        try:
            assert await asyncio.wait_for(second_reader.read(), timeout=1.0) == b""
        finally:
            second_writer.close()
            await second_writer.wait_closed()
    finally:
        first_writer.close()
        await first_writer.wait_closed()
        await first_reader.read()
        await service.close()


@pytest.mark.asyncio
async def test_service_timeout_terminates_and_reaps_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped = asyncio.Event()
    original_stop = service_module._stop_child

    async def observed_stop(process) -> None:
        await original_stop(process)
        assert process.returncode is not None
        stopped.set()

    monkeypatch.setattr(
        service_module,
        "_FIXED_CHILD_COMMAND",
        (sys.executable, "-c", "import time; time.sleep(30)"),
    )
    monkeypatch.setattr(service_module, "_stop_child", observed_stop)
    path = tmp_path / "runtime" / "guide.sock"
    path.parent.mkdir()
    service = _service(path, child_timeout=0.1)
    await service.start()
    source = b"timeout"
    try:
        with pytest.raises(ExternalServiceUnavailableError):
            await _adapter(path, timeout=1.0).parse(_request(source), source)
        await asyncio.wait_for(stopped.wait(), timeout=1.0)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_client_cancellation_stops_in_flight_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped = asyncio.Event()
    original_stop = service_module._stop_child

    async def observed_stop(process) -> None:
        await original_stop(process)
        stopped.set()

    monkeypatch.setattr(
        service_module,
        "_FIXED_CHILD_COMMAND",
        (sys.executable, "-c", "import time; time.sleep(30)"),
    )
    monkeypatch.setattr(service_module, "_stop_child", observed_stop)
    path = tmp_path / "runtime" / "guide.sock"
    path.parent.mkdir()
    service = _service(path, child_timeout=5.0)
    await service.start()
    source = b"cancel"
    try:
        task = asyncio.create_task(_adapter(path, timeout=10.0).parse(_request(source), source))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(stopped.wait(), timeout=1.0)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_service_replaces_only_owned_stale_socket(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "guide.sock"
    path.parent.mkdir()
    path.parent.chmod(0o750)
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path))
    stale.close()
    path.chmod(0o660)

    service = _service(path)
    await service.start()
    try:
        assert path.is_socket()
    finally:
        await service.close()


def test_stale_socket_with_foreign_expected_owner_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "guide.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path))
    stale.close()
    path.chmod(0o660)

    with pytest.raises(RuntimeError, match="owned socket"):
        _remove_owned_stale_socket(
            path,
            expected_uid=os.geteuid() + 1,
            expected_gid=os.getegid(),
        )
    assert path.is_socket()
    path.unlink()


@pytest.mark.asyncio
async def test_service_rejects_hard_linked_socket_alias(tmp_path: Path) -> None:
    directory = tmp_path / "runtime"
    directory.mkdir()
    directory.chmod(0o750)
    path = directory / "guide.sock"
    alias = directory / "guide-alias.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path))
    stale.close()
    path.chmod(0o660)
    os.link(path, alias)

    with pytest.raises(RuntimeError, match="owned socket"):
        await _service(path).start()

    path.unlink()
    alias.unlink()


@pytest.mark.asyncio
async def test_service_rejects_symlink_and_live_socket(tmp_path: Path) -> None:
    directory = tmp_path / "runtime"
    directory.mkdir()
    directory.chmod(0o750)
    target = directory / "target"
    target.write_text("not a socket")
    link = directory / "guide.sock"
    link.symlink_to(target)
    with pytest.raises(RuntimeError, match="owned socket"):
        await _service(link).start()
    link.unlink()

    async def close_connection(
        _reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        writer.close()
        await writer.wait_closed()

    live = await asyncio.start_unix_server(close_connection, path=link)
    link.chmod(0o660)
    try:
        with pytest.raises(RuntimeError, match="live listener"):
            await _service(link).start()
    finally:
        live.close()
        await live.wait_closed()
        link.unlink()
