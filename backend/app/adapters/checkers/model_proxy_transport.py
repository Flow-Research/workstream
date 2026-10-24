"""Private bounded Unix transport for request-bound checker model calls."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import struct
from pathlib import Path
from typing import Any
from collections.abc import Awaitable, Callable

from app.interfaces.checker_trial_proxy import TRIAL_PROXY_PROTOCOL, TRIAL_PROXY_MAXIMUM_FRAME_BYTES

from app.interfaces.checker_model_proxy import (
    MODEL_PROXY_MAXIMUM_FRAME_BYTES,
    MODEL_PROXY_PROTOCOL,
    ModelProxyHandler,
    ModelProxyReply,
    ModelProxyRequest,
    ModelProxyResolvedReceipt,
)
from app.interfaces.setup_model_proxy import (
    SETUP_MODEL_PROXY_PROTOCOL,
    SetupModelProxyHandler,
    SetupModelProxyReply,
    setup_model_proxy_request_from_wire,
)


class ModelProxyTransportError(RuntimeError):
    """Base error for model-proxy transport ownership and lifecycle failures."""


class ModelProxyCustodyError(ModelProxyTransportError):
    """The configured private socket path is not safe to own."""


class ModelProxyCleanupError(ModelProxyTransportError):
    """The transport cannot prove that the remaining socket path is its own."""


class ModelProxyTransport:
    """Own one private AF_UNIX listener and retain every dispatched handler."""

    def __init__(
        self,
        *,
        socket_path: Path,
        handler: ModelProxyHandler,
        trial_handler: Callable[[dict], Awaitable[dict]] | None = None,
        setup_handler: SetupModelProxyHandler | None = None,
        maximum_connections: int = 16,
        read_timeout_seconds: float = 2.0,
        write_timeout_seconds: float = 2.0,
        shutdown_timeout_seconds: float = 30.0,
    ) -> None:
        if (
            not isinstance(socket_path, Path)
            or not callable(handler)
            or (trial_handler is not None and not callable(trial_handler))
            or (setup_handler is not None and not callable(setup_handler))
            or type(maximum_connections) is not int
            or not 1 <= maximum_connections <= 256
            or type(read_timeout_seconds) is not float
            or not 0.01 <= read_timeout_seconds <= 60.0
            or type(write_timeout_seconds) is not float
            or not 0.01 <= write_timeout_seconds <= 60.0
            or type(shutdown_timeout_seconds) is not float
            or not 0.01 <= shutdown_timeout_seconds <= 7_200.0
        ):
            raise ValueError("model proxy transport configuration is invalid")
        self._socket_path = socket_path
        self._handler = handler
        self._trial_handler = trial_handler
        self._maximum_frame_bytes = (
            TRIAL_PROXY_MAXIMUM_FRAME_BYTES
            if trial_handler is not None
            else MODEL_PROXY_MAXIMUM_FRAME_BYTES
        )
        self._setup_handler = setup_handler
        self._maximum_connections = maximum_connections
        self._read_timeout_seconds = read_timeout_seconds
        self._write_timeout_seconds = write_timeout_seconds
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._server: asyncio.AbstractServer | None = None
        self._connection_tasks: set[asyncio.Task[None]] = set()
        self._handler_tasks: set[asyncio.Task[Any]] = set()
        self._parent_identity: tuple[int, int] | None = None
        self._socket_identity: tuple[int, int] | None = None
        self._closing = False

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    async def start(self) -> None:
        """Bind only an absent path beneath its canonical same-UID private parent."""
        if self._server is not None or self._closing:
            raise ModelProxyTransportError("model proxy transport already started")
        parent = self._validated_parent()
        try:
            os.lstat(self._socket_path)
        except FileNotFoundError:
            pass
        else:
            raise ModelProxyCustodyError("model proxy socket path is occupied")

        server: asyncio.AbstractServer | None = None
        created_identity: tuple[int, int] | None = None
        try:
            server = await asyncio.start_unix_server(
                self._admit_connection,
                path=self._socket_path,
                backlog=self._maximum_connections,
                limit=self._maximum_frame_bytes + 4,
            )
            metadata = os.lstat(self._socket_path)
            created_identity = (metadata.st_dev, metadata.st_ino)
            if not stat.S_ISSOCK(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise ModelProxyCustodyError("model proxy socket identity is invalid")
            os.chmod(self._socket_path, 0o600, follow_symlinks=False)
            metadata = os.lstat(self._socket_path)
            if not _private_socket(metadata):
                raise ModelProxyCustodyError("model proxy socket custody is invalid")
            if created_identity != (metadata.st_dev, metadata.st_ino):
                raise ModelProxyCustodyError("model proxy socket identity changed")
        except BaseException:
            if server is not None:
                server.close()
                await server.wait_closed()
            if created_identity is not None:
                self._unlink_owned(created_identity, parent)
            raise
        self._parent_identity = parent
        self._socket_identity = created_identity
        self._server = server

    async def close(self) -> None:
        """Stop admission, drain retained work, then unlink only the owned inode."""
        self._closing = True
        if self._server is not None:
            self._server.close()
        deadline = asyncio.get_running_loop().time() + self._shutdown_timeout_seconds
        while self._connection_tasks or self._handler_tasks:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("model proxy handler drain timed out")
            tasks: set[asyncio.Task[Any]] = {
                *self._connection_tasks,
                *self._handler_tasks,
            }
            done, pending = await asyncio.wait(tasks, timeout=remaining)
            self._connection_tasks.difference_update(done)
            self._handler_tasks.difference_update(done)
            if pending:
                raise TimeoutError("model proxy handler drain timed out")
        if self._server is not None:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("model proxy listener drain timed out")
            async with asyncio.timeout(remaining):
                await self._server.wait_closed()
            self._server = None
        if self._socket_identity is not None and self._parent_identity is not None:
            self._unlink_owned(self._socket_identity, self._parent_identity)
        self._socket_identity = None
        self._parent_identity = None

    async def __aenter__(self) -> ModelProxyTransport:
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    def _validated_parent(self) -> tuple[int, int]:
        path = self._socket_path
        encoded = os.fsencode(path)
        if (
            not path.is_absolute()
            or not encoded
            or b"\0" in encoded
            or len(encoded) >= 108
            or path.name in {"", ".", ".."}
        ):
            raise ModelProxyCustodyError("model proxy socket path is invalid")
        parent = path.parent
        try:
            metadata = os.lstat(parent)
            canonical = parent.resolve(strict=True)
        except OSError as exc:
            raise ModelProxyCustodyError("model proxy parent is unavailable") from exc
        if canonical != parent or not _private_directory(metadata):
            raise ModelProxyCustodyError("model proxy parent custody is invalid")
        return (metadata.st_dev, metadata.st_ino)

    def _admit_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if (
            self._closing
            or len(self._connection_tasks) >= self._maximum_connections
            or len(self._handler_tasks) >= self._maximum_connections
        ):
            writer.close()
            return
        task = asyncio.create_task(
            self._serve_connection(reader, writer),
            name="checker-model-proxy-connection",
        )
        self._connection_tasks.add(task)
        task.add_done_callback(self._connection_finished)

    def _connection_finished(self, task: asyncio.Task[None]) -> None:
        self._connection_tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def _handler_finished(self, task: asyncio.Task[Any]) -> None:
        self._handler_tasks.discard(task)
        if not task.cancelled():
            task.exception()

    async def _serve_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            async with asyncio.timeout(self._read_timeout_seconds):
                header = await reader.readexactly(4)
                size = struct.unpack(">I", header)[0]
                if size == 0 or size > self._maximum_frame_bytes:
                    return
                payload = await reader.readexactly(size)
            awaitable, reply_type = self._dispatch(payload)
            is_trial = reply_type is dict
            handler_task = asyncio.create_task(
                awaitable,
                name="checker-model-proxy-handler",
            )
            self._handler_tasks.add(handler_task)
            handler_task.add_done_callback(self._handler_finished)
            try:
                reply = await asyncio.shield(handler_task)
            except BaseException:
                return
            if type(reply) is not reply_type:
                return
            body = json.dumps(
                reply if is_trial else reply.wire_value(),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            reply_limit = (
                TRIAL_PROXY_MAXIMUM_FRAME_BYTES if is_trial else MODEL_PROXY_MAXIMUM_FRAME_BYTES
            )
            if not body or len(body) > reply_limit:
                return
            frame = struct.pack(">I", len(body)) + body
            writer.write(frame)
            async with asyncio.timeout(self._write_timeout_seconds):
                await writer.drain()
        except (
            TimeoutError,
            OSError,
            asyncio.IncompleteReadError,
            UnicodeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return
        finally:
            writer.close()
            try:
                async with asyncio.timeout(self._write_timeout_seconds):
                    await writer.wait_closed()
            except (TimeoutError, OSError):
                pass

    def _dispatch(self, payload: bytes) -> tuple[Awaitable[Any], type]:
        """Route the three closed protocols with exact reply types and frame ceilings."""
        value = json.loads(
            payload.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_closed_json_object,
        )
        if type(value) is not dict:
            raise ValueError("checker proxy request root is invalid")
        if value.get("protocol_version") == TRIAL_PROXY_PROTOCOL:
            if self._trial_handler is None:
                raise ValueError("trial proxy is not configured")
            return self._trial_handler(value), dict
        if len(payload) > MODEL_PROXY_MAXIMUM_FRAME_BYTES:
            raise ValueError("model proxy frame exceeds its limit")
        if value.get("protocol_version") == SETUP_MODEL_PROXY_PROTOCOL:
            if self._setup_handler is None:
                raise ValueError("setup proxy is not configured")
            return self._setup_handler(setup_model_proxy_request_from_wire(value)), SetupModelProxyReply
        return self._handler(_decode_request(payload)), ModelProxyReply

    def _unlink_owned(
        self,
        socket_identity: tuple[int, int],
        parent_identity: tuple[int, int],
    ) -> None:
        try:
            parent = os.lstat(self._socket_path.parent)
        except FileNotFoundError:
            raise ModelProxyCleanupError("model proxy parent disappeared") from None
        if (parent.st_dev, parent.st_ino) != parent_identity or not _private_directory(parent):
            raise ModelProxyCleanupError("model proxy parent identity changed")
        try:
            current = os.lstat(self._socket_path)
        except FileNotFoundError:
            return
        if (current.st_dev, current.st_ino) != socket_identity or not _private_socket(current):
            raise ModelProxyCleanupError("model proxy socket identity changed")
        try:
            self._socket_path.unlink()
        except OSError as exc:
            raise ModelProxyCleanupError("model proxy socket cleanup failed") from exc


def _decode_request(payload: bytes) -> ModelProxyRequest:
    value = json.loads(
        payload.decode("utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_closed_json_object,
    )
    expected = {
        "protocol_version",
        "grant_id",
        "request_digest",
        "call_index",
        "prompt",
        "resolved_receipts",
    }
    if type(value) is not dict or set(value) != expected:
        raise ValueError("model proxy request root is invalid")
    if value["protocol_version"] != MODEL_PROXY_PROTOCOL:
        raise ValueError("model proxy protocol version is invalid")
    return ModelProxyRequest(
        grant_id=value["grant_id"],
        request_digest=value["request_digest"],
        call_index=value["call_index"],
        prompt=value["prompt"],
        resolved_receipts=tuple(
            ModelProxyResolvedReceipt(
                receipt_sha256=item["receipt_sha256"],
                canonical_receipt_utf8=item["canonical_receipt_utf8"],
            )
            for item in _resolved_receipt_values(value["resolved_receipts"])
        ),
    )


def _resolved_receipt_values(value: object) -> list[dict[str, object]]:
    """Reject open or duplicate receipt objects before constructing trusted values."""
    if type(value) is not list:
        raise ValueError("model proxy resolved receipts are invalid")
    expected = {"receipt_sha256", "canonical_receipt_utf8"}
    if any(type(item) is not dict or set(item) != expected for item in value):
        raise ValueError("model proxy resolved receipts are invalid")
    return value


def _closed_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate model proxy field")
        value[key] = item
    return value


def _reject_json_constant(_: str) -> None:
    raise ValueError("non-finite model proxy number")


def _private_directory(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and stat.S_IMODE(metadata.st_mode) == 0o700
        and metadata.st_uid == os.geteuid()
        and metadata.st_gid == os.getegid()
    )


def _private_socket(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISSOCK(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and stat.S_IMODE(metadata.st_mode) == 0o600
        and metadata.st_uid == os.geteuid()
        and metadata.st_gid == os.getegid()
    )


__all__ = (
    "ModelProxyCleanupError",
    "ModelProxyCustodyError",
    "ModelProxyTransport",
    "ModelProxyTransportError",
)
