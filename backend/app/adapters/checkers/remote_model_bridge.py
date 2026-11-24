"""Outbound authenticated bridge for runner-local checker model callbacks."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import ssl
import struct


_PROTOCOL = "workstream.remote_runner.v1"
_MAXIMUM_FRAME_BYTES = 64 * 1024 * 1024


async def _read_frame(reader: asyncio.StreamReader) -> bytes:
    size = struct.unpack(">I", await reader.readexactly(4))[0]
    if size == 0 or size > _MAXIMUM_FRAME_BYTES:
        raise ValueError("remote model bridge frame is invalid")
    return await reader.readexactly(size)


async def _write_frame(writer: asyncio.StreamWriter, body: bytes) -> None:
    if not body or len(body) > _MAXIMUM_FRAME_BYTES:
        raise ValueError("remote model bridge frame is invalid")
    writer.write(struct.pack(">I", len(body)) + body)
    await writer.drain()


class RemoteModelProxyBridge:
    """Reconnect one app-owned Unix model proxy to the dedicated runner edge."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        server_name: str,
        ca_path: Path,
        certificate_path: Path,
        private_key_path: Path,
        socket_path: Path,
    ) -> None:
        self._host, self._port, self._server_name = host, port, server_name
        self._ca_path = ca_path
        self._certificate_path = certificate_path
        self._private_key_path = private_key_path
        self._socket_path = socket_path
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def _tls_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(self._ca_path))
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.check_hostname = True
        context.load_cert_chain(
            certfile=str(self._certificate_path), keyfile=str(self._private_key_path)
        )
        return context

    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("remote model bridge is already started")
        self._task = asyncio.create_task(self._run(), name="remote-model-proxy-bridge")

    async def close(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def __aenter__(self) -> "RemoteModelProxyBridge":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _run(self) -> None:
        delay = 0.25
        while not self._stopping.is_set():
            try:
                await self._session()
                delay = 0.25
            except asyncio.CancelledError:
                raise
            except (OSError, ssl.SSLError, asyncio.IncompleteReadError, ValueError):
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=delay)
                except TimeoutError:
                    pass
                delay = min(5.0, delay * 2)

    async def _session(self) -> None:
        reader, writer = await asyncio.open_connection(
            self._host,
            self._port,
            ssl=self._tls_context(),
            server_hostname=self._server_name,
        )
        try:
            control = json.dumps(
                {
                    "protocol_version": _PROTOCOL,
                    "operation": "model_bridge",
                    "capability": "external_checker_execution",
                },
                separators=(",", ":"),
            ).encode()
            await _write_frame(writer, control)
            acknowledgement = json.loads(await _read_frame(reader))
            if acknowledgement != {
                "protocol_version": _PROTOCOL,
                "operation": "model_bridge",
                "status": "ready",
            }:
                raise ValueError("remote model bridge acknowledgement is invalid")
            while not self._stopping.is_set():
                header = json.loads(await _read_frame(reader))
                if (
                    type(header) is not dict
                    or set(header) != {"protocol_version", "operation", "channel_id"}
                    or header.get("protocol_version") != _PROTOCOL
                    or header.get("operation") != "model_request"
                    or type(header.get("channel_id")) is not str
                ):
                    raise ValueError("remote model request header is invalid")
                request = await _read_frame(reader)
                response = await self._exchange_local(request)
                response_header = json.dumps(
                    {
                        "protocol_version": _PROTOCOL,
                        "operation": "model_response",
                        "channel_id": header["channel_id"],
                    },
                    separators=(",", ":"),
                ).encode()
                await _write_frame(writer, response_header)
                await _write_frame(writer, response)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ssl.SSLError):
                pass

    async def _exchange_local(self, request: bytes) -> bytes:
        reader, writer = await asyncio.open_unix_connection(self._socket_path)
        try:
            await _write_frame(writer, request)
            return await _read_frame(reader)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


__all__ = ("RemoteModelProxyBridge",)
