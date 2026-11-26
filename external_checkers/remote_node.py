#!/usr/bin/env python3
"""Authenticated network edge for one dedicated native checker node."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import ssl
import stat
import struct
import sys
import time
from typing import Any
import uuid


PROTOCOL = "workstream.remote_runner.v1"
CHECKER_CAPABILITY = "external_checker_execution"
INTAKE_CAPABILITY = "trusted_submission_intake"
GRANT_PROTOCOL = "workstream.external_checker_material_grant.v2"
MAXIMUM_CONTROL_BYTES = 2 * 1024 * 1024
MAXIMUM_FRAME_BYTES = 64 * 1024 * 1024
MAXIMUM_MATERIAL_BYTES = 1024 * 1024 * 1024
MAXIMUM_FILES = 4_000
_GRANT_ID = re.compile(r"extract_[0-9a-f]{32}")
_INCOMING_ID = re.compile(r"\.incoming-[0-9a-f]{32}")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


class ProtocolError(Exception):
    """A remote peer sent a malformed or unbound request."""


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ProtocolError("duplicate JSON member")
        value[key] = item
    return value


def _decode_object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda _: (_ for _ in ()).throw(ProtocolError("JSON constant")),
            object_pairs_hook=_closed_object,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProtocolError("invalid JSON") from exc
    if type(value) is not dict:
        raise ProtocolError("JSON root is not an object")
    return value


async def _read_frame(
    reader: asyncio.StreamReader,
    maximum: int,
    *,
    allow_empty: bool = False,
) -> bytes:
    size = struct.unpack(">I", await reader.readexactly(4))[0]
    if size == 0 and allow_empty:
        return b""
    if size == 0 or size > maximum:
        raise ProtocolError("frame is unbounded")
    return await reader.readexactly(size)


async def _write_frame(writer: asyncio.StreamWriter, body: bytes) -> None:
    if not body or len(body) > MAXIMUM_FRAME_BYTES:
        raise ProtocolError("response frame is unbounded")
    writer.write(struct.pack(">I", len(body)) + body)
    await writer.drain()


def _epoch_binding(control: dict[str, Any]) -> bytes:
    epoch, config = control.get("epoch"), control.get("config_sha256")
    if (type(epoch) is not str or re.fullmatch(r"[0-9a-f]{64}", epoch) is None
            or type(config) is not str or _SHA256.fullmatch(config) is None):
        raise ProtocolError("runner epoch binding is invalid")
    return json.dumps({
        "protocol_version": "external_checker_service.v1", "operation": "bind_epoch",
        "epoch": epoch, "config_sha256": config,
    }, separators=(",", ":")).encode()


class ExecutionChannel:
    """Multiplex native callback frames over the exact owning execute connection."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader, self.writer = reader, writer
        self.closed = asyncio.Event()
        self._write_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[bytes]] = {}
        self._router = asyncio.create_task(self._route_responses())

    async def callback(self, request: bytes) -> bytes:
        channel_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[channel_id] = future
        try:
            async with self._write_lock:
                if self.closed.is_set():
                    raise ProtocolError("execute channel is unavailable")
                await _write_frame(
                    self.writer,
                    json.dumps(
                        {
                            "protocol_version": PROTOCOL,
                            "operation": "callback_request",
                            "channel_id": channel_id,
                        },
                        separators=(",", ":"),
                    ).encode(),
                )
                await _write_frame(self.writer, request)
            return await future
        finally:
            self._pending.pop(channel_id, None)

    async def result(self, response: bytes) -> None:
        async with self._write_lock:
            if self.closed.is_set():
                raise ProtocolError("execute channel is unavailable")
            await _write_frame(
                self.writer,
                json.dumps(
                    {"protocol_version": PROTOCOL, "operation": "execution_result"},
                    separators=(",", ":"),
                ).encode(),
            )
            await _write_frame(self.writer, response)

    async def _route_responses(self) -> None:
        failure: BaseException = ProtocolError("execute channel closed")
        try:
            while True:
                header = _decode_object(await _read_frame(self.reader, 16_384))
                if (
                    set(header) != {"protocol_version", "operation", "channel_id"}
                    or header.get("protocol_version") != PROTOCOL
                    or header.get("operation") != "callback_response"
                    or type(header.get("channel_id")) is not str
                ):
                    raise ProtocolError("callback response header is invalid")
                future = self._pending.get(header["channel_id"])
                if future is None or future.done():
                    raise ProtocolError("callback response has no owner")
                future.set_result(await _read_frame(self.reader, MAXIMUM_FRAME_BYTES))
        except asyncio.CancelledError as exc:
            failure = exc
            raise
        except (ProtocolError, OSError, ssl.SSLError, asyncio.IncompleteReadError) as exc:
            failure = exc
        finally:
            self.closed.set()
            for future in tuple(self._pending.values()):
                if not future.done():
                    future.set_exception(failure)

    async def close(self) -> None:
        if not self._router.done():
            self._router.cancel()
        await asyncio.gather(self._router, return_exceptions=True)
        self.closed.set()


def _peer_name(writer: asyncio.StreamWriter) -> set[str]:
    certificate = writer.get_extra_info("peercert")
    if type(certificate) is not dict:
        return set()
    return {
        value
        for kind, value in certificate.get("subjectAltName", ())
        if kind == "DNS" and type(value) is str
    }


def _relative_path(value: object) -> PurePosixPath:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 4_096:
        raise ProtocolError("material path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or "\\" in value or any(part in {"", ".", ".."} for part in path.parts):
        raise ProtocolError("material path is invalid")
    return path


def _manifest_files(
    manifest: dict[str, Any],
) -> tuple[tuple[PurePosixPath, int, str, bool], ...]:
    if manifest.get("protocol_version") != GRANT_PROTOCOL:
        raise ProtocolError("material protocol differs")
    materials = manifest.get("materials")
    if type(materials) is not list or not 1 <= len(materials) <= 2:
        raise ProtocolError("material inventory is invalid")
    values: list[tuple[PurePosixPath, int, str, bool]] = []
    roles: set[str] = set()
    inventory_entries = 0
    for item in materials:
        if type(item) is not dict or set(item) != {"material", "directories", "files"}:
            raise ProtocolError("material descriptor is invalid")
        material = item["material"]
        if type(material) is not dict or material.get("role") not in {
            "submission_archive", "predecessor_submission_archive"
        }:
            raise ProtocolError("material role is invalid")
        role = material["role"]
        if role in roles:
            raise ProtocolError("material role is duplicated")
        roles.add(role)
        directories = item["directories"]
        files = item["files"]
        if type(directories) is not list or type(files) is not list:
            raise ProtocolError("material inventory is invalid")
        inventory_entries += len(directories) + len(files)
        if inventory_entries > MAXIMUM_FILES:
            raise ProtocolError("material inventory is unbounded")
        seen: set[str] = set()
        for value in directories:
            path = _relative_path(value)
            if str(path) in seen:
                raise ProtocolError("material path is duplicated")
            seen.add(str(path))
        for entry in files:
            if type(entry) is not dict or set(entry) != {
                "normalized_path", "byte_count", "sha256", "executable"
            }:
                raise ProtocolError("material file is invalid")
            path = _relative_path(entry["normalized_path"])
            count, digest, executable = (
                entry["byte_count"], entry["sha256"], entry["executable"]
            )
            if (
                str(path) in seen
                or type(count) is not int
                or count < 0
                or type(digest) is not str
                or _SHA256.fullmatch(digest) is None
                or type(executable) is not bool
            ):
                raise ProtocolError("material file is invalid")
            seen.add(str(path))
            values.append((PurePosixPath("materials", role, *path.parts), count, digest, executable))
    return tuple(values)


def _mkdir_inventory(root: Path, manifest: dict[str, Any]) -> None:
    materials_root = root / "materials"
    materials_root.mkdir(mode=0o700)
    for item in manifest["materials"]:
        role_root = materials_root / item["material"]["role"]
        role_root.mkdir(mode=0o700)
        for value in item["directories"]:
            path = _relative_path(value)
            (role_root / Path(*path.parts)).mkdir(mode=0o700, parents=True, exist_ok=True)


def _seal_directories(root: Path) -> None:
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for path in directories:
        os.chmod(path, 0o500, follow_symlinks=False)


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for current, directories, files in os.walk(path, topdown=False, followlinks=False):
        for name in files:
            os.chmod(Path(current, name), 0o600, follow_symlinks=False)
        for name in directories:
            os.chmod(Path(current, name), 0o700, follow_symlinks=False)
    os.chmod(path, 0o700, follow_symlinks=False)
    shutil.rmtree(path)


def _reconcile_stale_workspaces(config: dict[str, Any]) -> int:
    """Remove only bounded edge-owned residue while the native service is stopped."""
    socket_path = Path(config.get("socket_path", ""))
    material_root = Path(config.get("material_root", ""))
    workspaces = material_root / "workspaces"
    if not socket_path.is_absolute() or socket_path.exists():
        raise ValueError("native service must be stopped before reconciliation")
    metadata = workspaces.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o077
        or workspaces.resolve() != workspaces
    ):
        raise ValueError("workspace root custody is invalid")
    entries = sorted(workspaces.iterdir())
    # One exclusive execution can leave at most one renamed or incoming tree.
    # More residue cannot be attributed safely to one crashed edge process.
    if len(entries) > 1:
        raise ValueError("workspace residue ownership is uncertain")
    removed = 0
    for entry in entries:
        if (
            not (_GRANT_ID.fullmatch(entry.name) or _INCOMING_ID.fullmatch(entry.name))
            or entry.is_symlink()
            or not entry.is_dir()
        ):
            raise ValueError("workspace residue ownership is uncertain")
        count, total = 0, 0
        for current, directories, files in os.walk(entry, followlinks=False):
            for name in (*directories, *files):
                item = Path(current, name)
                observed = item.lstat()
                if (
                    observed.st_uid != os.getuid()
                    or stat.S_ISLNK(observed.st_mode)
                    or not (stat.S_ISDIR(observed.st_mode) or stat.S_ISREG(observed.st_mode))
                ):
                    raise ValueError("workspace residue ownership is uncertain")
                count += 1
                if stat.S_ISREG(observed.st_mode):
                    total += observed.st_size
                if count > MAXIMUM_FILES + 10_000 or total > MAXIMUM_MATERIAL_BYTES + MAXIMUM_CONTROL_BYTES:
                    raise ValueError("workspace residue is unbounded")
        _remove_tree(entry)
        removed += 1
    return removed


def _write_descriptor(descriptor: int, body: bytes) -> None:
    view = memoryview(body)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("material write made no progress")
        view = view[written:]


class RemoteNode:
    """Route authenticated sessions into one private native service socket."""

    def __init__(self, config: dict[str, Any]) -> None:
        expected = {
            "listen_host", "listen_port", "client_name", "socket_path", "material_root",
            "model_proxy_socket_path",
            "tls_certificate_path", "tls_private_key_path", "tls_ca_path", "session_timeout_seconds",
        }
        if set(config) != expected:
            raise ValueError("remote node configuration shape is invalid")
        self.host = config["listen_host"]
        self.port = config["listen_port"]
        self.client_name = config["client_name"]
        self.socket_path = Path(config["socket_path"])
        self.model_proxy_socket_path = Path(config["model_proxy_socket_path"])
        self.material_root = Path(config["material_root"])
        self.timeout = float(config["session_timeout_seconds"])
        if (
            type(self.host) is not str
            or type(self.port) is not int
            or not 1 <= self.port <= 65_535
            or type(self.client_name) is not str
            or not self.client_name
            or not self.socket_path.is_absolute()
            or not self.model_proxy_socket_path.is_absolute()
            or not self.material_root.is_absolute()
            or not 1 <= self.timeout <= 3_700
        ):
            raise ValueError("remote node configuration is invalid")
        self.workspaces = self.material_root / "workspaces"
        metadata = self.material_root.stat()
        if (
            not self.material_root.is_dir()
            or self.material_root.is_symlink()
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
            or self.material_root.resolve() != self.material_root
        ):
            raise ValueError("remote node material root is not private")
        self.workspaces.mkdir(mode=0o700, exist_ok=True)
        workspace_metadata = self.workspaces.lstat()
        if (
            not stat.S_ISDIR(workspace_metadata.st_mode)
            or stat.S_ISLNK(workspace_metadata.st_mode)
            or workspace_metadata.st_uid != os.getuid()
            or workspace_metadata.st_mode & 0o077
            or self.workspaces.resolve() != self.workspaces
            or any(self.workspaces.iterdir())
        ):
            raise ValueError("remote node workspace root requires reconciliation")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_cert_chain(config["tls_certificate_path"], config["tls_private_key_path"])
        context.load_verify_locations(config["tls_ca_path"])
        self.ssl_context = context
        self._execution = asyncio.Lock()
        self._active_channel: ExecutionChannel | None = None
        self._model_server: asyncio.AbstractServer | None = None

    async def start_model_proxy(self) -> None:
        """Own the runner-local socket used by the native model relay."""
        parent = self.model_proxy_socket_path.parent
        metadata = parent.stat()
        if (
            not parent.is_dir()
            or parent.is_symlink()
            or metadata.st_mode & 0o077
            or parent.resolve() != parent
        ):
            raise ValueError("model proxy parent is not private")
        try:
            occupied = self.model_proxy_socket_path.lstat()
        except FileNotFoundError:
            pass
        else:
            if (
                not stat.S_ISSOCK(occupied.st_mode)
                or occupied.st_uid != os.getuid()
                or self.model_proxy_socket_path.is_symlink()
            ):
                raise ValueError("model proxy socket is occupied")
            self.model_proxy_socket_path.unlink()
        self._model_server = await asyncio.start_unix_server(
            self._handle_model_proxy,
            path=self.model_proxy_socket_path,
            limit=MAXIMUM_FRAME_BYTES + 4,
        )
        os.chmod(self.model_proxy_socket_path, 0o600, follow_symlinks=False)

    async def close(self) -> None:
        if self._model_server is not None:
            self._model_server.close()
            await self._model_server.wait_closed()
        try:
            metadata = self.model_proxy_socket_path.lstat()
            if stat.S_ISSOCK(metadata.st_mode) and metadata.st_uid == os.getuid():
                self.model_proxy_socket_path.unlink()
        except FileNotFoundError:
            pass

    async def _handle_model_proxy(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            async with asyncio.timeout(self.timeout):
                request = await _read_frame(reader, MAXIMUM_FRAME_BYTES)
                channel = self._active_channel
                if channel is None:
                    raise ProtocolError("execute callback owner is unavailable")
                response = await channel.callback(request)
                await _write_frame(writer, response)
                if await reader.read(1):
                    raise ProtocolError("model proxy request contains trailing data")
        except (ProtocolError, TimeoutError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout(self.timeout):
                if self.client_name not in _peer_name(writer):
                    raise ProtocolError("client identity differs")
                control = _decode_object(await _read_frame(reader, MAXIMUM_CONTROL_BYTES))
                if control.get("protocol_version") != PROTOCOL:
                    raise ProtocolError("remote protocol differs")
                operation = control.get("operation")
                capability = control.get("capability")
                if operation == "placement":
                    if set(control) != {"protocol_version", "operation", "demand"} or (
                        control["demand"] is not None and type(control["demand"]) is not dict
                    ):
                        raise ProtocolError("placement request is invalid")
                    await self._placement(control["demand"], writer)
                elif operation == "proxy":
                    if set(control) != {"protocol_version", "operation", "capability", "epoch", "config_sha256"} or capability not in {
                        CHECKER_CAPABILITY, INTAKE_CAPABILITY
                    }:
                        raise ProtocolError("proxy request is invalid")
                    await self._proxy(reader, writer, _epoch_binding(control))
                elif operation == "execute":
                    if capability != CHECKER_CAPABILITY:
                        raise ProtocolError("execute capability differs")
                    await self._execute(control, reader, writer)
                else:
                    raise ProtocolError("remote operation is invalid")
        except (ProtocolError, TimeoutError, OSError, ssl.SSLError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ssl.SSLError):
                pass

    async def _placement(self, demand: dict[str, Any] | None, writer: asyncio.StreamWriter) -> None:
        """Forward one closed read-only request without allowing an inner execution frame."""
        native_reader, native_writer = await asyncio.open_unix_connection(self.socket_path)
        try:
            await _write_frame(native_writer, json.dumps({
                "protocol_version": "external_checker_service.v1", "operation": "placement", "demand": demand,
            }, separators=(",", ":")).encode())
            response = await _read_frame(native_reader, 32_768)
            if await native_reader.read(1):
                raise ProtocolError("native placement reply has trailing data")
            await _write_frame(writer, response)
        finally:
            native_writer.close()
            await native_writer.wait_closed()

    async def _proxy(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, binding: bytes) -> None:
        native_reader, native_writer = await asyncio.open_unix_connection(self.socket_path)

        async def copy(source: asyncio.StreamReader, target: asyncio.StreamWriter) -> None:
            while chunk := await source.read(64 * 1024):
                target.write(chunk)
                await target.drain()

        tasks: set[asyncio.Task[None]] = set()
        try:
            await _write_frame(native_writer, binding)
            tasks = {
                asyncio.create_task(copy(reader, native_writer)),
                asyncio.create_task(copy(native_reader, writer)),
            }
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            native_writer.close()
            try:
                await native_writer.wait_closed()
            except OSError:
                pass

    async def _execute(
        self,
        control: dict[str, Any],
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        expected = {
            "protocol_version", "operation", "capability", "service_request",
            "manifest_byte_count", "file_count", "total_byte_count", "epoch", "config_sha256",
        }
        if set(control) != expected or type(control["service_request"]) is not dict:
            raise ProtocolError("execute request is invalid")
        binding_frame = _epoch_binding(control)
        request = control["service_request"]
        if request.get("operation") not in {"execute", "locate_forge_change"}:
            raise ProtocolError("service operation is invalid")
        grant = request.get("grant")
        checked = request.get("request")
        if type(grant) is not dict or type(checked) is not dict:
            raise ProtocolError("service request binding is invalid")
        grant_id = grant.get("grant_id")
        binding = grant.get("binding_digest")
        if (
            type(grant_id) is not str
            or _GRANT_ID.fullmatch(grant_id) is None
            or type(binding) is not str
            or _SHA256.fullmatch(binding) is None
        ):
            raise ProtocolError("grant reference is invalid")
        raw_manifest = await _read_frame(reader, MAXIMUM_CONTROL_BYTES)
        if len(raw_manifest) != control["manifest_byte_count"]:
            raise ProtocolError("manifest byte count differs")
        manifest = _decode_object(raw_manifest)
        body = dict(manifest)
        supplied_binding = body.pop("binding_digest", None)
        canonical = json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
        observed_binding = "sha256:" + hashlib.sha256(canonical).hexdigest()
        if (
            supplied_binding != binding
            or observed_binding != binding
            or manifest.get("grant_id") != grant_id
            or manifest.get("request_digest") != checked.get("request_digest")
        ):
            raise ProtocolError("material binding differs")
        files = _manifest_files(manifest)
        if (
            type(control["file_count"]) is not int
            or control["file_count"] != len(files)
            or type(control["total_byte_count"]) is not int
            or control["total_byte_count"] != sum(item[1] for item in files)
            or control["total_byte_count"] > MAXIMUM_MATERIAL_BYTES
        ):
            raise ProtocolError("material bounds differ")
        async with self._execution:
            await self._stage_and_execute(
                grant_id, raw_manifest, manifest, files, request, reader, writer, binding_frame
            )

    async def _stage_and_execute(
        self,
        grant_id: str,
        raw_manifest: bytes,
        manifest: dict[str, Any],
        files: tuple[tuple[PurePosixPath, int, str, bool], ...],
        request: dict[str, Any],
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        binding_frame: bytes,
    ) -> None:
        target = self.workspaces / grant_id
        incoming = self.workspaces / f".incoming-{uuid.uuid4().hex}"
        native_writer: asyncio.StreamWriter | None = None
        channel: ExecutionChannel | None = None
        wait_tasks: set[asyncio.Task[Any]] = set()
        if target.exists():
            raise ProtocolError("grant is already active")
        incoming.mkdir(mode=0o700)
        started = time.monotonic()
        transferred = 0
        stage = "material_transfer"

        def record(event: str, **facts: Any) -> None:
            # Only owner-generated stages, validated grant identity and counters;
            # never material paths, contents, credentials or exception messages.
            try:
                print(json.dumps({
                    "event": "checker_remote_stage", "grant_id": grant_id,
                    "stage": stage, "disposition": event,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "transferred_bytes": transferred, **facts,
                }, separators=(",", ":")), file=sys.stderr, flush=True)
            except (OSError, ValueError):
                pass  # Diagnostic output never changes execution or cleanup custody.

        record("started", expected_bytes=sum(item[1] for item in files))
        try:
            _mkdir_inventory(incoming, manifest)
            for relative, expected_count, expected_digest, executable in files:
                path = incoming / Path(*relative.parts)
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                digest, count = hashlib.sha256(), 0
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    while chunk := await _read_frame(reader, 64 * 1024, allow_empty=True):
                        count += len(chunk)
                        if count > expected_count:
                            raise ProtocolError("material file is too large")
                        digest.update(chunk)
                        _write_descriptor(descriptor, chunk)
                        transferred += len(chunk)
                    if count != expected_count or "sha256:" + digest.hexdigest() != expected_digest:
                        raise ProtocolError("material file content differs")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.chmod(path, 0o500 if executable else 0o400, follow_symlinks=False)
            manifest_path = incoming / ".external-checker-grant.json"
            descriptor = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
            try:
                _write_descriptor(descriptor, raw_manifest)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            _seal_directories(incoming)
            os.chmod(incoming, 0o700, follow_symlinks=False)
            os.rename(incoming, target)
            record("completed")
            stage = "awaiting_execution_start"
            ready = {
                "protocol_version": PROTOCOL, "operation": "material_ready",
                "grant_id": grant_id, "binding_digest": manifest["binding_digest"],
            }
            await _write_frame(writer, json.dumps(ready, separators=(",", ":")).encode())
            start = _decode_object(await _read_frame(reader, 16_384))
            if start != dict(ready, operation="start_execution"):
                raise ProtocolError("execution start binding differs")
            stage = "native_execution"
            record("started")
            native_reader, native_writer = await asyncio.open_unix_connection(self.socket_path)
            encoded = json.dumps(
                request, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode()
            channel = ExecutionChannel(reader, writer)
            if self._active_channel is not None:
                raise ProtocolError("execute callback owner is already active")
            self._active_channel = channel
            await _write_frame(native_writer, binding_frame)
            await _write_frame(native_writer, encoded)
            response_task = asyncio.create_task(_read_frame(native_reader, MAXIMUM_FRAME_BYTES))
            disconnect_task = asyncio.create_task(channel.closed.wait())
            wait_tasks = {response_task, disconnect_task}
            done, _ = await asyncio.wait(
                wait_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            if disconnect_task in done:
                raise ProtocolError("remote client disconnected")
            response = await response_task
            record("completed")
            stage = "result_delivery"
            await channel.result(response)
            record("completed")
        except BaseException as exc:
            record("interrupted", error_type=type(exc).__name__)
            raise
        finally:
            for task in wait_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*wait_tasks, return_exceptions=True)
            if self._active_channel is channel:
                self._active_channel = None
            if channel is not None:
                await channel.close()
            if native_writer is not None:
                native_writer.close()
                try:
                    await native_writer.wait_closed()
                except OSError:
                    pass
            _remove_tree(target)
            _remove_tree(incoming)
            stage = "material_cleanup"
            record("completed")


async def _main(config_path: Path) -> None:
    node = RemoteNode(_load_config(config_path))
    await node.start_model_proxy()
    try:
        server = await asyncio.start_server(
            node.handle,
            node.host,
            node.port,
            ssl=node.ssl_context,
            limit=MAXIMUM_FRAME_BYTES + 4,
        )
        async with server:
            await server.serve_forever()
    finally:
        await node.close()


def _load_config(config_path: Path) -> dict[str, Any]:
    raw = config_path.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("remote node configuration is too large")
    return _decode_object(raw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--reconcile-stale-workspaces", action="store_true")
    arguments = parser.parse_args()
    if arguments.reconcile_stale_workspaces:
        configuration = _load_config(arguments.config)
        print(_reconcile_stale_workspaces(configuration))
    else:
        asyncio.run(_main(arguments.config))
