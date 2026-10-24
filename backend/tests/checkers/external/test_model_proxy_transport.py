"""The private model proxy transport is bounded and retains dispatched work."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import socket
import stat
import struct

import pytest

from app.adapters.checkers.model_proxy_transport import (
    ModelProxyCleanupError,
    ModelProxyCustodyError,
    ModelProxyTransport,
)
from app.interfaces.checker_model_proxy import (
    MODEL_PROXY_MAXIMUM_FRAME_BYTES,
    MODEL_PROXY_PROTOCOL,
    ModelProxyReply,
    ModelProxyRequest,
)


GRANT_ID = "model_" + "a" * 32
REQUEST_DIGEST = "sha256:" + "b" * 64
RECEIPT_DIGEST = "sha256:" + "c" * 64


def request_value(*, prompt: str = "Judge this bounded artifact.") -> dict[str, object]:
    """Build the exact Rust relay request root."""
    return {
        "protocol_version": MODEL_PROXY_PROTOCOL,
        "grant_id": GRANT_ID,
        "request_digest": REQUEST_DIGEST,
        "call_index": 0,
        "prompt": prompt,
        "resolved_receipts": [],
    }


def frame(value: object) -> bytes:
    """Encode one private protocol frame."""
    body = json.dumps(value, separators=(",", ":")).encode()
    return struct.pack(">I", len(body)) + body


async def read_frame(reader: asyncio.StreamReader) -> object:
    """Read one private protocol frame."""
    size = struct.unpack(">I", await reader.readexactly(4))[0]
    return json.loads(await reader.readexactly(size))


@asynccontextmanager
async def connection(
    path: Path,
) -> AsyncIterator[tuple[asyncio.StreamReader, asyncio.StreamWriter]]:
    """Open and close one real Unix connection."""
    reader, writer = await asyncio.open_unix_connection(path)
    try:
        yield reader, writer
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 1)
        except (TimeoutError, OSError):
            pass


def private_socket_path(tmp_path: Path) -> Path:
    """Create a canonical same-identity private listener parent."""
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    return parent / "proxy.sock"


@pytest.mark.asyncio
async def test_real_socket_round_trip_has_exact_contract_and_private_custody(tmp_path):
    path = private_socket_path(tmp_path)
    received: list[ModelProxyRequest] = []

    async def handle(request: ModelProxyRequest) -> ModelProxyReply:
        received.append(request)
        return ModelProxyReply(
            outcome="completed",
            output="bounded result",
            receipt_digest=RECEIPT_DIGEST,
            failure_code=None,
            call_index=0,
            session_exhausted=False,
        )

    transport = ModelProxyTransport(socket_path=path, handler=handle)
    async with transport:
        metadata = os.lstat(path)
        assert stat.S_ISSOCK(metadata.st_mode)
        assert stat.S_IMODE(metadata.st_mode) == 0o600
        assert (metadata.st_uid, metadata.st_gid) == (os.geteuid(), os.getegid())
        async with connection(path) as (reader, writer):
            writer.write(frame(request_value()))
            await writer.drain()
            assert await read_frame(reader) == {
                "protocol_version": MODEL_PROXY_PROTOCOL,
                "outcome": "completed",
                "output": "bounded result",
                "receipt_digest": RECEIPT_DIGEST,
                "failure_code": None,
                "call_index": 0,
                "session_exhausted": False,
            }

    assert received == [
        ModelProxyRequest(
            grant_id=GRANT_ID,
            request_digest=REQUEST_DIGEST,
            call_index=0,
            prompt="Judge this bounded artifact.",
        )
    ]
    assert GRANT_ID not in repr(received[0])
    assert received[0].prompt not in repr(received[0])
    assert "bounded result" not in repr(
        ModelProxyReply("completed", "bounded result", RECEIPT_DIGEST, None, 0, False)
    )
    assert not path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        json.dumps({**request_value(), "provider": "secret"}).encode(),
        json.dumps(
            {key: value for key, value in request_value().items() if key != "prompt"}
        ).encode(),
        (
            b'{"protocol_version":"workstream.model_session.v2",'
            b'"grant_id":"model_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            b'"request_digest":"sha256:' + b"b" * 64 + b'","call_index":0,'
            b'"prompt":"first","prompt":"second","resolved_receipts":[]}'
        ),
        json.dumps({**request_value(), "grant_id": "model_" + "A" * 32}).encode(),
        json.dumps({**request_value(), "protocol_version": "model_proxy.v0"}).encode(),
        json.dumps({**request_value(), "prompt": None}).encode(),
    ],
)
async def test_malformed_or_open_request_is_closed_without_dispatch(tmp_path, payload):
    path = private_socket_path(tmp_path)
    calls = 0

    async def handle(_: ModelProxyRequest) -> ModelProxyReply:
        nonlocal calls
        calls += 1
        return ModelProxyReply("unavailable", None, None, "provider_unavailable", 0, True)

    async with ModelProxyTransport(socket_path=path, handler=handle):
        async with connection(path) as (reader, writer):
            writer.write(struct.pack(">I", len(payload)) + payload)
            await writer.drain()
            assert await asyncio.wait_for(reader.read(), 1) == b""

    assert calls == 0


@pytest.mark.asyncio
async def test_oversize_and_incomplete_frames_close_within_read_deadline(tmp_path):
    path = private_socket_path(tmp_path)

    async def handle(_: ModelProxyRequest) -> ModelProxyReply:
        raise AssertionError("invalid frame reached the handler")

    async with ModelProxyTransport(
        socket_path=path,
        handler=handle,
        read_timeout_seconds=0.05,
    ):
        async with connection(path) as (reader, writer):
            writer.write(struct.pack(">I", MODEL_PROXY_MAXIMUM_FRAME_BYTES + 1))
            await writer.drain()
            assert await asyncio.wait_for(reader.read(), 1) == b""
        async with connection(path) as (reader, writer):
            writer.write(struct.pack(">I", 10) + b"ab")
            await writer.drain()
            assert await asyncio.wait_for(reader.read(), 1) == b""


@pytest.mark.asyncio
async def test_oversize_handler_reply_is_closed_without_writing_a_frame(tmp_path):
    path = private_socket_path(tmp_path)

    async def handle(_: ModelProxyRequest) -> ModelProxyReply:
        return ModelProxyReply(
            "completed",
            "x" * MODEL_PROXY_MAXIMUM_FRAME_BYTES,
            RECEIPT_DIGEST,
            None,
            0,
            False,
        )

    async with ModelProxyTransport(socket_path=path, handler=handle):
        async with connection(path) as (reader, writer):
            writer.write(frame(request_value()))
            await writer.drain()
            assert await asyncio.wait_for(reader.read(), 1) == b""


@pytest.mark.asyncio
async def test_connection_bound_rejects_another_dispatch(tmp_path):
    path = private_socket_path(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def handle(_: ModelProxyRequest) -> ModelProxyReply:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return ModelProxyReply("unavailable", None, None, "budget_unavailable", 0, True)

    async with ModelProxyTransport(
        socket_path=path,
        handler=handle,
        maximum_connections=1,
    ):
        async with connection(path) as (first_reader, first_writer):
            first_writer.write(frame(request_value(prompt="first")))
            await first_writer.drain()
            await asyncio.wait_for(entered.wait(), 1)
            async with connection(path) as (_, second_writer):
                second_writer.write(frame(request_value(prompt="second")))
                await second_writer.drain()
                await asyncio.sleep(0.05)
                assert calls == 1
            release.set()
            assert await read_frame(first_reader) == {
                "protocol_version": MODEL_PROXY_PROTOCOL,
                "outcome": "unavailable",
                "output": None,
                "receipt_digest": None,
                "failure_code": "budget_unavailable",
                "call_index": 0,
                "session_exhausted": True,
            }

    assert calls == 1


@pytest.mark.asyncio
async def test_client_disconnect_does_not_cancel_or_reissue_dispatched_handler(tmp_path):
    path = private_socket_path(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()
    cancelled = False
    calls = 0

    async def handle(_: ModelProxyRequest) -> ModelProxyReply:
        nonlocal calls, cancelled
        calls += 1
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled = True
            raise
        completed.set()
        return ModelProxyReply("unavailable", None, None, "provider_unavailable", 0, True)

    transport = ModelProxyTransport(
        socket_path=path,
        handler=handle,
        shutdown_timeout_seconds=0.05,
    )
    await transport.start()
    _, writer = await asyncio.open_unix_connection(path)
    writer.write(frame(request_value()))
    await writer.drain()
    await asyncio.wait_for(entered.wait(), 1)
    writer.close()
    await writer.wait_closed()

    with pytest.raises(TimeoutError, match="handler drain"):
        await transport.close()
    assert path.exists()
    assert calls == 1
    assert not cancelled
    release.set()
    await asyncio.wait_for(completed.wait(), 1)
    await transport.close()
    assert calls == 1
    assert not cancelled
    assert not path.exists()


@pytest.mark.asyncio
async def test_start_refuses_nonprivate_symlink_and_occupied_paths(tmp_path):
    public_parent = tmp_path / "public"
    public_parent.mkdir(mode=0o755)

    async def handle(_: ModelProxyRequest) -> ModelProxyReply:
        return ModelProxyReply("unavailable", None, None, "provider_unavailable", 0, True)

    with pytest.raises(ModelProxyCustodyError, match="parent custody"):
        await ModelProxyTransport(socket_path=public_parent / "proxy.sock", handler=handle).start()

    private_parent = tmp_path / "private"
    private_parent.mkdir(mode=0o700)
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(private_parent, target_is_directory=True)
    with pytest.raises(ModelProxyCustodyError, match="parent custody"):
        await ModelProxyTransport(socket_path=linked_parent / "proxy.sock", handler=handle).start()

    occupied = private_parent / "occupied.sock"
    occupied.write_text("not a socket")
    with pytest.raises(ModelProxyCustodyError, match="occupied"):
        await ModelProxyTransport(socket_path=occupied, handler=handle).start()
    assert occupied.read_text() == "not a socket"

    stale = private_parent / "stale.sock"
    stale_socket = socket.socket(socket.AF_UNIX)
    stale_socket.bind(str(stale))
    stale_socket.close()
    with pytest.raises(ModelProxyCustodyError, match="occupied"):
        await ModelProxyTransport(socket_path=stale, handler=handle).start()
    assert stat.S_ISSOCK(os.lstat(stale).st_mode)


@pytest.mark.asyncio
async def test_cleanup_refuses_replaced_socket_and_leaves_it_in_place(tmp_path):
    path = private_socket_path(tmp_path)

    async def handle(_: ModelProxyRequest) -> ModelProxyReply:
        return ModelProxyReply("unavailable", None, None, "provider_unavailable", 0, True)

    transport = ModelProxyTransport(socket_path=path, handler=handle)
    await transport.start()
    path.unlink()
    replacement = socket.socket(socket.AF_UNIX)
    replacement.bind(str(path))
    os.chmod(path, 0o600)
    try:
        with pytest.raises(ModelProxyCleanupError, match="identity changed"):
            await transport.close()
        assert stat.S_ISSOCK(os.lstat(path).st_mode)
    finally:
        replacement.close()
        path.unlink()


@pytest.mark.parametrize(
    "reply",
    [
        ("completed", "", RECEIPT_DIGEST, None, 0, False),
        ("completed", "output", None, None, 0, False),
        ("unavailable", "output", None, "provider_unavailable", 0, True),
        ("unavailable", None, None, "Provider-Unavailable", 0, True),
        ("unavailable", None, None, "a" * 65, 0, True),
    ],
)
def test_reply_rejects_invalid_closed_outcomes(reply):
    with pytest.raises(ValueError, match="reply is invalid"):
        ModelProxyReply(*reply)


async def test_trial_protocol_shares_listener_without_enlarging_model_limit(tmp_path):
    """A large trial callback cannot enlarge the model protocol's allowance."""
    from app.interfaces.checker_trial_proxy import TRIAL_PROXY_PROTOCOL

    path = private_socket_path(tmp_path)
    model_requests, trial_requests = [], []

    async def model(request):
        model_requests.append(request)
        return ModelProxyReply("completed", "ok", RECEIPT_DIGEST, None, 0, False)

    async def trial(request):
        trial_requests.append(request)
        return {
            "protocol_version": TRIAL_PROXY_PROTOCOL,
            "operation": "publish",
            "outcome": "unavailable",
            "failure_code": "trial_request_invalid",
        }

    async with ModelProxyTransport(socket_path=path, handler=model, trial_handler=trial):
        # Framing owns a separate trial ceiling; its typed handler owns its body.
        value = {
            "protocol_version": TRIAL_PROXY_PROTOCOL,
            "padding": "x" * (MODEL_PROXY_MAXIMUM_FRAME_BYTES + 1),
        }
        async with connection(path) as (reader, writer):
            writer.write(frame(value))
            await writer.drain()
            assert (await read_frame(reader))["failure_code"] == "trial_request_invalid"
        async with connection(path) as (reader, writer):
            writer.write(frame(request_value(prompt="x" * MODEL_PROXY_MAXIMUM_FRAME_BYTES)))
            await writer.drain()
            assert await reader.read() == b""
        # A duplicate protocol tag is denied before either handler can act.
        raw = (
            '{"protocol_version":"'
            + MODEL_PROXY_PROTOCOL
            + '","protocol_version":"'
            + TRIAL_PROXY_PROTOCOL
            + '"}'
        ).encode()
        async with connection(path) as (reader, writer):
            writer.write(struct.pack(">I", len(raw)) + raw)
            await writer.drain()
            assert await reader.read() == b""
        async with connection(path) as (reader, writer):
            writer.write(frame(request_value()))
            await writer.drain()
            assert (await read_frame(reader))["output"] == "ok"
    assert len(trial_requests) == len(model_requests) == 1
    assert not path.exists()


def test_trial_manifest_configuration_requires_exact_pair_and_private_proxy(tmp_path):
    """Selected authority is explicit and never falls back to a guessed profile."""
    from pydantic import ValidationError
    from app.core.config import Settings
    from tests.test_s3_artifact_store import minio_settings

    original = minio_settings(private_prefix="trial-config")
    base = original.model_dump() | {
        # Settings deliberately excludes credentials from model_dump.
        "artifact_s3_access_key_id": original.artifact_s3_access_key_id.get_secret_value(),
        "artifact_s3_secret_access_key": original.artifact_s3_secret_access_key.get_secret_value(),
    }
    selected = {
        "checker_trial_authority_manifest_path": tmp_path / "trial-authority.json",
        "checker_trial_authority_manifest_digest": "sha256:" + "a" * 64,
        "checker_model_proxy_socket": tmp_path / "proxy.sock",
    }
    assert Settings.model_validate(base | selected).checker_trial_authority_manifest_path == selected[
        "checker_trial_authority_manifest_path"
    ]
    for field, value in (
        ("checker_trial_authority_manifest_path", None),
        ("checker_trial_authority_manifest_digest", None),
        ("checker_trial_authority_manifest_digest", "latest"),
        ("checker_trial_authority_manifest_path", Path("relative.json")),
        ("checker_model_proxy_socket", None),
    ):
        with pytest.raises(ValidationError):
            Settings.model_validate(base | selected | {field: value})
