"""Private framed transport for ART's one prepared trusted-intake lease."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict, fields
import hashlib
import json
from pathlib import Path
import re
import socket
import struct
import threading
import time
from typing import BinaryIO, TypeVar

from pydantic import TypeAdapter

from app.core.cancellation import await_cancellation_resistant
from app.interfaces.external_services import (
    ExternalServiceAdapterIdentity,
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)
from app.interfaces.trusted_submission_intake import (
    TrustedDefaultBinding,
    TrustedIntakeIdentity,
    TrustedIntakePreparation,
)
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveEntry,
    SubmissionArchiveEntryType,
    SubmissionArchiveFailureCode,
    SubmissionArchiveInspectionResult,
    SubmissionArchiveRejectedError,
)
from app.modules.checkers.api.default_checker import (
    WorkstreamDefaultCheckerInput,
    WorkstreamDefaultCheckerResult,
    workstream_default_input_sha256,
)

CAPABILITY = "trusted_submission_intake"
PROVIDER = "unix_socket"
_PROTOCOL = "trusted_submission_intake.v1"
_MAX_FRAME = 64 * 1024 * 1024
_MAX_COMMAND = 4 * 1024 * 1024
_MAX_ARCHIVE = 512 * 1024 * 1024
_CHUNK = 64 * 1024
_CLEANUP_SECONDS = 15.0
_T = TypeVar("_T")
_INPUT = TypeAdapter(WorkstreamDefaultCheckerInput)


def _object(value: object, keys: set[str]) -> dict:
    """Require the exact wire object shape before interpreting any fields."""
    if type(value) is not dict or set(value) != keys:
        raise ExternalServiceProtocolError()
    return value


def _entry(value: object) -> SubmissionArchiveEntry:
    """Validate one bounded exported-file descriptor from the trusted guest."""
    body = _object(value, {field.name for field in fields(SubmissionArchiveEntry)})
    if (
        type(body["normalized_path"]) is not str
        or type(body["byte_count"]) is not int
        or body["byte_count"] < 0
        or type(body["entry_type"]) is not str
        or body["entry_type"] not in {"file", "directory"}
    ):
        raise ExternalServiceProtocolError()
    if body["entry_type"] == "file":
        if (
            type(body["sha256"]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", body["sha256"]) is None
            or type(body["executable"]) is not bool
        ):
            raise ExternalServiceProtocolError()
    elif body["sha256"] is not None or body["executable"] is not None or body["byte_count"] != 0:
        raise ExternalServiceProtocolError()
    return SubmissionArchiveEntry(
        **{**body, "entry_type": SubmissionArchiveEntryType(body["entry_type"])}
    )


class UnixSocketTrustedIntakeAdapter:
    """Construct one local session; the node owns all preparation retry decisions."""

    def __init__(self, *, socket_path: Path, image_digest: str, config_digest: str) -> None:
        """Bind an absolute private socket to operator-pinned image and config identities."""
        if (
            not socket_path.is_absolute()
            or socket_path.is_symlink()
            or any(
                type(v) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", v) is None
                for v in (image_digest, config_digest)
            )
        ):
            raise ValueError("trusted intake configuration invalid")
        self._path = socket_path
        self._image = image_digest
        self._config = config_digest

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Identify this typed capability and its explicitly registered provider."""
        return ExternalServiceAdapterIdentity(CAPABILITY, PROVIDER)

    def _validate_identity(self, raw: object) -> TrustedIntakeIdentity:
        """Reject image, configuration, behavior or isolation identity drift."""
        try:
            identity = TrustedIntakeIdentity(
                **_object(
                    raw,
                    {field.name for field in fields(TrustedIntakeIdentity)},
                )
            )
        except (ValueError, TypeError) as exc:
            raise ExternalServiceProtocolError(self.identity) from exc
        if (identity.image_digest, identity.config_digest) != (self._image, self._config):
            raise ExternalServiceProtocolError(self.identity)
        return identity

    async def health(self) -> TrustedIntakeIdentity:
        """Check the pinned node identity without reserving a VM."""
        session = _Session(self, time.monotonic() + 10)
        try:
            return await session._async(session._health)
        finally:
            session.abort()

    async def prepare(self, request: TrustedIntakePreparation) -> _Session:
        """Acquire one lease within the original deadline and abort failed preparation."""
        if type(request) is not TrustedIntakePreparation:
            raise ExternalServiceProtocolError(self.identity)
        session = _Session(self, time.monotonic() + request.deadline_ms / 1000, request)
        try:
            await session._async(session._prepare)
            return session
        except BaseException:
            session.abort()
            raise


class _Session:
    """One connection, one boot-scoped nonce, and one non-renewable deadline."""

    def __init__(
        self,
        adapter: UnixSocketTrustedIntakeAdapter,
        deadline: float,
        request: TrustedIntakePreparation | None = None,
    ) -> None:
        """Own one socket, deadline and serialized state machine for this lease."""
        self._adapter = adapter
        self._deadline = deadline
        self._request = request
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._lock = threading.Lock()
        self._aborted = threading.Event()
        self._state = "new"
        self._lease: str | None = None
        self._identity: TrustedIntakeIdentity | None = None
        self._inspection: SubmissionArchiveInspectionResult | None = None
        self._archive: tuple[str, int] | None = None

    def __reduce__(self):
        """Forbid transferring the process-local lease by serialization."""
        raise TypeError("trusted intake session is process-local")

    @property
    def identity(self) -> TrustedIntakeIdentity:
        """Expose only the identity acknowledged by successful preparation."""
        if self._identity is None:
            raise ExternalServiceProtocolError()
        return self._identity

    async def _async(self, operation: Callable[[], _T]) -> _T:
        """Drain blocking transport work before propagating caller cancellation."""
        task = asyncio.create_task(asyncio.to_thread(operation))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            self.abort()
            try:
                await await_cancellation_resistant(task)
            except BaseException:
                pass
            raise

    def _timeout(self, *, cleanup: bool = False) -> None:
        """Charge I/O to the original deadline with a bounded cleanup allowance."""
        remaining = self._deadline + (_CLEANUP_SECONDS if cleanup else 0) - time.monotonic()
        if remaining <= 0 or self._aborted.is_set():
            raise ExternalServiceUnavailableError(self._adapter.identity)
        try:
            self._socket.settimeout(remaining)
        except OSError as exc:
            raise ExternalServiceUnavailableError(self._adapter.identity) from exc

    def _send(self, data: bytes, *, cleanup: bool = False) -> None:
        """Send bytes within the current lease deadline or report unavailability."""
        self._timeout(cleanup=cleanup)
        try:
            self._socket.sendall(data)
        except OSError as exc:
            raise ExternalServiceUnavailableError(self._adapter.identity) from exc

    def _read(self, size: int, *, cleanup: bool = False) -> bytes:
        """Read exactly the framed byte count without unbounded receive allocation."""
        data = bytearray()
        while len(data) < size:
            self._timeout(cleanup=cleanup)
            try:
                chunk = self._socket.recv(min(_CHUNK, size - len(data)))
            except OSError as exc:
                raise ExternalServiceUnavailableError(self._adapter.identity) from exc
            if not chunk:
                raise ExternalServiceUnavailableError(self._adapter.identity)
            data.extend(chunk)
        return bytes(data)

    def _command(self, operation: str, payload: dict, *, cleanup: bool = False) -> None:
        """Send a bounded command carrying this connection’s exact lease nonce."""
        data = json.dumps(
            {
                "protocol_version": _PROTOCOL,
                "operation": operation,
                "lease": self._lease,
                "payload": payload,
            },
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
        if len(data) > _MAX_COMMAND:
            raise ExternalServiceProtocolError(self._adapter.identity)
        self._send(struct.pack(">I", len(data)) + data, cleanup=cleanup)

    def _response(self, operation: str, *, cleanup: bool = False) -> dict:
        """Validate framing, operation and lease before accepting guest results."""
        length = struct.unpack(">I", self._read(4, cleanup=cleanup))[0]
        if not 0 < length <= _MAX_FRAME:
            raise ExternalServiceProtocolError(self._adapter.identity)
        try:
            body = _object(
                json.loads(self._read(length, cleanup=cleanup)),
                {"protocol_version", "operation", "lease", "status", "payload"},
            )
        except (ValueError, UnicodeError) as exc:
            raise ExternalServiceProtocolError(self._adapter.identity) from exc
        if (
            body["protocol_version"] != _PROTOCOL
            or body["operation"] != operation
            or (operation != "prepare" and body["lease"] != self._lease)
            or type(body["payload"]) is not dict
        ):
            raise ExternalServiceProtocolError(self._adapter.identity)
        if body["status"] == "error":
            code = _object(body["payload"], {"code"})["code"]
            if type(code) is not str:
                raise ExternalServiceProtocolError(self._adapter.identity)
            if operation == "inspect" and code in {
                value.value for value in SubmissionArchiveFailureCode
            }:
                raise SubmissionArchiveRejectedError(SubmissionArchiveFailureCode(code))
            if code in {"runtime_unavailable", "capacity_unavailable", "deadline_exceeded"}:
                raise ExternalServiceUnavailableError(self._adapter.identity)
            raise ExternalServiceProtocolError(self._adapter.identity)
        if body["status"] != "ok":
            raise ExternalServiceProtocolError(self._adapter.identity)
        if operation == "prepare":
            if (
                type(body["lease"]) is not str
                or re.fullmatch(r"[0-9a-f]{128}", body["lease"]) is None
            ):
                raise ExternalServiceProtocolError(self._adapter.identity)
            self._lease = body["lease"]
        return body["payload"]

    def _connect(self) -> None:
        """Connect only to the configured private socket within the lease deadline."""
        self._timeout()
        try:
            self._socket.connect(str(self._adapter._path))
        except OSError as exc:
            raise ExternalServiceUnavailableError(self._adapter.identity) from exc

    def _health(self) -> TrustedIntakeIdentity:
        """Read and verify the node identity on a temporary health connection."""
        self._connect()
        self._command("health", {})
        return self._adapter._validate_identity(self._response("health"))

    def _prepare(self) -> None:
        """Accept the boot-scoped lease only after the node confirms readiness."""
        with self._lock:
            self._connect()
            self._command("prepare", asdict(self._request))
            self._identity = self._adapter._validate_identity(self._response("prepare"))
            self._state = "prepared"

    def inspect(
        self, reader: BinaryIO, *, archive_sha256: str, archive_byte_count: int
    ) -> SubmissionArchiveInspectionResult:
        """Stream the sealed archive and verify its returned digest and bounded manifest."""
        with self._lock:
            if (
                self._state != "prepared"
                or type(archive_byte_count) is not int
                or not 0 < archive_byte_count <= _MAX_ARCHIVE
                or type(archive_sha256) is not str
                or re.fullmatch(r"sha256:[0-9a-f]{64}", archive_sha256) is None
            ):
                raise ExternalServiceProtocolError(self._adapter.identity)
            self._state = "inspecting"
            self._command(
                "inspect",
                {"archive_sha256": archive_sha256, "archive_byte_count": archive_byte_count},
            )
            reader.seek(0)
            remaining = archive_byte_count
            digest = hashlib.sha256()
            while remaining:
                chunk = reader.read(min(remaining, _CHUNK))
                if not chunk or len(chunk) > remaining:
                    raise ExternalServiceProtocolError(self._adapter.identity)
                self._send(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            if reader.read(1) or "sha256:" + digest.hexdigest() != archive_sha256:
                self.abort()
                raise ExternalServiceProtocolError(self._adapter.identity)
            payload = _object(
                self._response("inspect"), {"archive_sha256", "archive_byte_count", "inspection"}
            )
            if (payload["archive_sha256"], payload["archive_byte_count"]) != (
                archive_sha256,
                archive_byte_count,
            ):
                raise ExternalServiceProtocolError(self._adapter.identity)
            raw = _object(
                payload["inspection"],
                {field.name for field in fields(SubmissionArchiveInspectionResult)},
            )
            if (
                type(raw["entries"]) is not list
                or len(raw["entries"]) > self._request.limits.maximum_entries
            ):
                raise ExternalServiceProtocolError(self._adapter.identity)
            entries = tuple(_entry(value) for value in raw["entries"])
            counts = (
                len(entries),
                sum(e.entry_type is SubmissionArchiveEntryType.FILE for e in entries),
                sum(e.entry_type is SubmissionArchiveEntryType.DIRECTORY for e in entries),
                sum(e.byte_count for e in entries),
            )
            for name, expected in zip(
                ("entry_count", "file_count", "directory_count", "total_expanded_bytes"), counts
            ):
                if type(raw[name]) is not int or raw[name] != expected:
                    raise ExternalServiceProtocolError(self._adapter.identity)
            if counts[3] > self._request.limits.maximum_expanded_bytes:
                raise ExternalServiceProtocolError(self._adapter.identity)
            self._inspection = SubmissionArchiveInspectionResult(**{**raw, "entries": entries})
            self._archive = archive_sha256, archive_byte_count
            self._state = "inspected"
            return self._inspection

    def export(self, sink: Callable[[SubmissionArchiveEntry, bytes], None]) -> None:
        """Verify each inspected file while streaming into the owner-provided sink."""
        with self._lock:
            if self._state != "inspected":
                raise ExternalServiceProtocolError(self._adapter.identity)
            self._state = "exporting"
            self._command("export", {})
            for entry in self._inspection.entries:
                if entry.entry_type is not SubmissionArchiveEntryType.FILE:
                    continue
                if _entry(self._response("file")) != entry:
                    raise ExternalServiceProtocolError(self._adapter.identity)
                digest = hashlib.sha256()
                remaining = entry.byte_count
                if remaining == 0:
                    sink(entry, b"")
                while remaining:
                    chunk = self._read(min(remaining, _CHUNK))
                    digest.update(chunk)
                    sink(entry, chunk)
                    remaining -= len(chunk)
                if "sha256:" + digest.hexdigest() != entry.sha256:
                    raise ExternalServiceProtocolError(self._adapter.identity)
            _object(self._response("export"), set())
            self._state = "exported"

    async def evaluate_default(
        self, binding: TrustedDefaultBinding, value: WorkstreamDefaultCheckerInput
    ) -> WorkstreamDefaultCheckerResult:
        """Bind default evaluation to exact committed PRE custody and exported bytes."""
        def evaluate() -> WorkstreamDefaultCheckerResult:
            """Serialize the single default invocation and validate its typed result."""
            with self._lock:
                if (
                    self._state != "exported"
                    or self._request.phase != "pre_submit"
                    or type(binding) is not TrustedDefaultBinding
                    or binding.policy_sha256 != self._request.policy_sha256
                    or binding.semantic_manifest_sha256 != value.semantic_manifest_sha256
                    or binding.default_input_sha256 != workstream_default_input_sha256(value)
                    or self._archive != (value.archive_sha256, value.archive_byte_count)
                ):
                    raise ExternalServiceProtocolError(self._adapter.identity)
                self._state = "evaluating"
                self._command(
                    "default",
                    {
                        "binding": {**asdict(binding), "attempt_id": str(binding.attempt_id)},
                        "input": _INPUT.dump_python(value, mode="json"),
                    },
                )
                try:
                    result = WorkstreamDefaultCheckerResult.model_validate(
                        self._response("default")
                    )
                except (TypeError, ValueError) as exc:
                    raise ExternalServiceProtocolError(self._adapter.identity) from exc
                self._state = "evaluated"
                return result

        return await self._async(evaluate)

    def abort(self) -> None:
        """Interrupt transport immediately without claiming remote cleanup confirmation."""
        self._aborted.set()
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._socket.close()

    async def close(self) -> None:
        """Await the node’s cleanup acknowledgement before releasing local transport."""
        def finish() -> None:
            """Mark the lease closed only after a valid cleanup acknowledgement."""
            with self._lock:
                if self._state == "closed":
                    return
                try:
                    self._command("close", {}, cleanup=True)
                    _object(self._response("close", cleanup=True), set())
                    self._state = "closed"
                finally:
                    self.abort()

        await self._async(finish)
