"""Mutually authenticated remote adapter for the dedicated checker node."""

from __future__ import annotations

from app.modules.checkers.api.source_contracts import SelectedPreSubmitSourceContracts

import asyncio
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import re
import ssl
import struct
from typing import Literal

from app.core.cancellation import await_cancellation_resistant

from app.interfaces.external_checker_execution import (
    ExternalCheckerExecutionOutcomeUnknown,
    ExternalCheckerExecutionResponse,
    ExternalPreSubmitSourceGrant,
    MAXIMUM_PRE_SOURCE_CHUNK_BYTES,
    ExternalCheckerForgeLocatorResponse,
    ExternalCheckerIsolationReceipt,
    ExternalCheckerMaterialGrant,
    ExternalCheckerModelGrant,
    ExternalCheckerServiceHealth,
)
from workstream_external_services import (
    ExternalServiceAdapterIdentity,
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)
from app.modules.checkers.api.external import (
    EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS,
    MAX_RESULT_BYTES,
    ExternalCheckerExecutionRequest,
    ExternalCheckerExecutionResult,
)

from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitLeaseFacts, SelectedPreSubmitInvocationResult,
    SelectedPreSubmitInfrastructureUnavailable,
)

from app.modules.checkers.api.forge_locator import (
    FORGE_LOCATOR_STAGE_KEY,
    ExternalCheckerForgeLocator,
    require_forge_locator_request,
)

EXTERNAL_CHECKER_CAPABILITY_KEY = "external_checker_execution"
EXTERNAL_CHECKER_PROVIDER_KEY = "remote_tls"
_PROTOCOL = "external_checker_service.v1"
_REMOTE_PROTOCOL = "workstream.remote_runner.v1"
_MAXIMUM_RESPONSE_BYTES = MAX_RESULT_BYTES + 16_384
_EXECUTION_OVERHEAD_SECONDS = EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS / 1000
_CHANNEL_ID = re.compile(r"[0-9a-f]{32}")


class RemoteTlsExternalCheckerAdapter:
    """Speak the existing service protocol through one authenticated remote node."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        server_name: str,
        ca_path: Path,
        certificate_path: Path,
        private_key_path: Path,
        model_proxy_socket_path: Path | None,
        timeout_seconds: float,
        source_contracts: SelectedPreSubmitSourceContracts,
    ) -> None:
        """Validate immutable endpoint settings without opening a connection."""
        if (
            type(host) is not str
            or not host
            or len(host) > 255
            or type(port) is not int
            or not 1 <= port <= 65_535
            or type(server_name) is not str
            or not server_name
            or len(server_name) > 255
            or any(not path.is_absolute() or path.is_symlink() for path in (
                ca_path, certificate_path, private_key_path
            ))
            or model_proxy_socket_path is not None
            and (not model_proxy_socket_path.is_absolute() or model_proxy_socket_path.is_symlink())
            or type(timeout_seconds) is not float
            or not 0.1 <= timeout_seconds <= 3_700.0
        ):
            raise ValueError("external checker service configuration is invalid")
        self._source_contracts = source_contracts
        self._host, self._port, self._server_name = host, port, server_name
        self._ca_path = ca_path
        self._certificate_path = certificate_path
        self._private_key_path = private_key_path
        self._model_proxy_socket_path = model_proxy_socket_path
        self._timeout_seconds = timeout_seconds
        self._identity = ExternalServiceAdapterIdentity(
            EXTERNAL_CHECKER_CAPABILITY_KEY,
            EXTERNAL_CHECKER_PROVIDER_KEY,
        )

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return the exact explicitly registered provider identity."""
        return self._identity

    @property
    def pre_runtime_provider(self) -> Literal["smolvm"]:
        """The dedicated native node accepts only Smol runtime evidence."""
        return "smolvm"

    def _tls_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context(
            ssl.Purpose.SERVER_AUTH,
            cafile=str(self._ca_path),
        )
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.check_hostname = True
        context.load_cert_chain(
            certfile=str(self._certificate_path),
            keyfile=str(self._private_key_path),
        )
        return context

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await asyncio.open_connection(
            self._host,
            self._port,
            ssl=self._tls_context(),
            server_hostname=self._server_name,
        )

    @staticmethod
    async def _send_frame(writer: asyncio.StreamWriter, payload: bytes) -> None:
        if not payload or len(payload) > 64 * 1024 * 1024:
            raise ValueError("remote runner frame is invalid")
        writer.write(struct.pack(">I", len(payload)) + payload)
        await writer.drain()

    async def _proxy_connection(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await self._open()
        control = json.dumps(
            {
                "protocol_version": _REMOTE_PROTOCOL,
                "operation": "proxy",
                "capability": EXTERNAL_CHECKER_CAPABILITY_KEY,
            },
            separators=(",", ":"),
        ).encode()
        await self._send_frame(writer, control)
        return reader, writer

    @staticmethod
    async def _read_frame(reader: asyncio.StreamReader, maximum: int) -> bytes:
        size = struct.unpack(">I", await reader.readexactly(4))[0]
        if size == 0 or size > maximum:
            raise ValueError("remote runner frame is invalid")
        return await reader.readexactly(size)

    async def _exchange_local_callback(self, payload: bytes) -> bytes:
        if self._model_proxy_socket_path is None:
            raise ValueError("model proxy callback is unavailable")
        reader, writer = await asyncio.open_unix_connection(self._model_proxy_socket_path)
        try:
            await self._send_frame(writer, payload)
            return await self._read_frame(reader, 64 * 1024 * 1024)
        finally:
            writer.close()
            await await_cancellation_resistant(writer.wait_closed())

    async def execute_pre(
        self, lease: SelectedPreSubmitLeaseFacts, grant: ExternalPreSubmitSourceGrant,
    ) -> SelectedPreSubmitInvocationResult:
        """Stream authorized source bytes into one PRE call without a host spool."""
        try:
            if type(lease) is not SelectedPreSubmitLeaseFacts:
                raise ValueError("PRE lease is invalid")
            reservation = lease.reservation
            payload = json.dumps({
                "protocol_version": _PROTOCOL, "operation": "execute_pre",
                "reservation": reservation.canonical_body(),
                "request_digest": reservation.request_digest,
                "lease_id": str(lease.lease_id), "lease_generation": lease.lease_generation,
                "lease_expires_at": lease.lease_expires_at.isoformat(),
            }, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            if len(payload) > 2 * 1024 * 1024:
                raise ValueError("PRE request is too large")
            remaining = (lease.lease_expires_at - datetime.now(timezone.utc)).total_seconds()
            timeout = min(remaining, reservation.execution_budget_ms / 1000, self._timeout_seconds)
            if timeout <= 0:
                raise SelectedPreSubmitInfrastructureUnavailable("deadline_exceeded")
            deadline = asyncio.get_running_loop().time() + timeout
            async with asyncio.timeout_at(deadline):
                reader, writer = await self._proxy_connection()
                try:
                    writer.write(struct.pack(">I", len(payload)) + payload)
                    await writer.drain()
                    digest, count = hashlib.sha256(), 0
                    stream = grant.open_source(lease=lease)
                    try:
                        async for chunk in stream:
                            if type(chunk) is not bytes or not 0 < len(chunk) <= MAXIMUM_PRE_SOURCE_CHUNK_BYTES:
                                raise ValueError("PRE source chunk is invalid")
                            count += len(chunk)
                            if count > reservation.source.raw_byte_count:
                                raise ValueError("PRE source identity differs")
                            digest.update(chunk)
                            writer.write(struct.pack(">I", len(chunk)) + chunk)
                            await writer.drain()
                    finally:
                        await await_cancellation_resistant(stream.aclose())
                    if (count != reservation.source.raw_byte_count
                            or "sha256:" + digest.hexdigest() != reservation.source.raw_sha256):
                        raise ValueError("PRE source identity differs")
                    writer.write(struct.pack(">I", 0))
                    await writer.drain()
                    size = struct.unpack(">I", await reader.readexactly(4))[0]
                    if size == 0 or size > 64 * 1024 * 1024:
                        raise ValueError("PRE response is too large")
                    raw = await reader.readexactly(size)
                    if await reader.read(1):
                        raise ValueError("PRE response contains trailing data")
                finally:
                    writer.close()
                    await await_cancellation_resistant(writer.wait_closed())
            body = json.loads(raw)
            if type(body) is not dict or "adapter_provider_key" in body:
                raise ValueError("PRE provider context is invalid")
            body["adapter_provider_key"] = self.identity.provider_key
            result = SelectedPreSubmitInvocationResult.from_canonical_body(body, source_contracts=self._source_contracts)
            if result.receipt.runtime.provider != "smolvm":
                raise ValueError("PRE runtime provider differs")
            result.validate_lease(lease, source_contracts=self._source_contracts)
            if (asyncio.get_running_loop().time() >= deadline
                    or datetime.now(timezone.utc) >= lease.lease_expires_at):
                raise SelectedPreSubmitInfrastructureUnavailable("deadline_exceeded")
            return result
        except ExternalServiceProtocolError:
            raise
        except TimeoutError as exc:
            raise SelectedPreSubmitInfrastructureUnavailable("deadline_exceeded") from exc
        except (OSError, asyncio.IncompleteReadError) as exc:
            raise ExternalServiceUnavailableError(self._identity) from exc
        except (TypeError, ValueError, KeyError, UnicodeError, RecursionError) as exc:
            raise ExternalServiceProtocolError(self._identity) from exc

    async def execute(
        self,
        request: ExternalCheckerExecutionRequest,
        grant: ExternalCheckerMaterialGrant,
        *,
        model_grant: ExternalCheckerModelGrant | None = None,
    ) -> ExternalCheckerExecutionResponse:
        """Execute evaluation only; locator messages cannot become work verdicts."""
        if FORGE_LOCATOR_STAGE_KEY in request.input:
            raise ExternalServiceProtocolError(self._identity)
        return await self._exchange(request, grant, model_grant=model_grant, locate=False)

    async def locate_forge_change(self, request, grant) -> ExternalCheckerForgeLocatorResponse:
        """Use the same bounded transport without issuing model or trial authority."""
        return await self._exchange(request, grant, model_grant=None, locate=True)

    async def _exchange(self, request, grant, *, model_grant, locate):
        """Exchange one bounded request and revalidate every returned fact."""
        possibly_invoked = False
        try:
            checked = ExternalCheckerExecutionRequest.model_validate(request)
            if locate:
                require_forge_locator_request(checked)
            if type(grant) is not ExternalCheckerMaterialGrant:
                raise ValueError("external checker material grant is invalid")
            if model_grant is not None and (
                type(model_grant) is not ExternalCheckerModelGrant
                or checked.identity.phase != "post_submit"
                or model_grant.binding_digest != checked.request_digest
            ):
                raise ValueError("external checker model grant is invalid")
            payload = json.dumps(
                {
                    "protocol_version": _PROTOCOL,
                    "operation": "locate_forge_change" if locate else "execute",
                    "request": checked.model_dump(mode="json"),
                    "grant": {
                        "grant_id": grant.grant_id,
                        "binding_digest": grant.binding_digest,
                    },
                    "model_grant": (
                        None
                        if model_grant is None
                        else {
                            "grant_id": model_grant.grant_id,
                            "binding_digest": model_grant.binding_digest,
                        }
                    ),
                },
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(payload) > 2 * 1024 * 1024:
                raise ExternalServiceProtocolError(self._identity)
            required_timeout = (
                checked.registry.resources.deadline_ms / 1000 + _EXECUTION_OVERHEAD_SECONDS
            )
            if self._timeout_seconds < required_timeout:
                raise ExternalServiceUnavailableError(self._identity)
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await self._open()
                try:
                    manifest = grant.source.manifest
                    files = grant.source.files
                    if (
                        type(manifest) is not bytes
                        or not 0 < len(manifest) <= 2 * 1024 * 1024
                        or len(files) > 4_000
                    ):
                        raise ValueError("external material export is invalid")
                    total_bytes = sum(item.byte_count for item in files)
                    if total_bytes > 1024 * 1024 * 1024:
                        raise ValueError("external material export is too large")
                    control = json.dumps(
                        {
                            "protocol_version": _REMOTE_PROTOCOL,
                            "operation": "execute",
                            "capability": EXTERNAL_CHECKER_CAPABILITY_KEY,
                            "service_request": json.loads(payload),
                            "manifest_byte_count": len(manifest),
                            "file_count": len(files),
                            "total_byte_count": total_bytes,
                        },
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    ).encode()
                    # A failed drain can follow successful transmission. Treat
                    # this call as possibly invoked before its first write.
                    possibly_invoked = True
                    await self._send_frame(writer, control)
                    await self._send_frame(writer, manifest)
                    for item in files:
                        stream = grant.source.open_file(item)
                        try:
                            async for chunk in stream:
                                if type(chunk) is not bytes or not 0 < len(chunk) <= 64 * 1024:
                                    raise ValueError("external material export chunk is invalid")
                                await self._send_frame(writer, chunk)
                        finally:
                            await await_cancellation_resistant(stream.aclose())
                        writer.write(struct.pack(">I", 0))
                        await writer.drain()
                    while True:
                        header = json.loads(await self._read_frame(reader, 16_384))
                        if (
                            type(header) is not dict
                            or header.get("protocol_version") != _REMOTE_PROTOCOL
                        ):
                            raise ValueError("remote runner response header is invalid")
                        operation = header.get("operation")
                        if operation == "callback_request":
                            if (
                                set(header)
                                != {"protocol_version", "operation", "channel_id"}
                                or type(header["channel_id"]) is not str
                                or _CHANNEL_ID.fullmatch(header["channel_id"]) is None
                            ):
                                raise ValueError("remote callback header is invalid")
                            callback = await self._read_frame(reader, 64 * 1024 * 1024)
                            response = await self._exchange_local_callback(callback)
                            await self._send_frame(
                                writer,
                                json.dumps(
                                    {
                                        "protocol_version": _REMOTE_PROTOCOL,
                                        "operation": "callback_response",
                                        "channel_id": header["channel_id"],
                                    },
                                    separators=(",", ":"),
                                ).encode(),
                            )
                            await self._send_frame(writer, response)
                            continue
                        if operation != "execution_result" or set(header) != {
                            "protocol_version", "operation"
                        }:
                            raise ValueError("remote execution result header is invalid")
                        raw = await self._read_frame(reader, _MAXIMUM_RESPONSE_BYTES)
                        if await reader.read(1):
                            raise ValueError("remote execution result contains trailing data")
                        break
                finally:
                    writer.close()
                    await await_cancellation_resistant(writer.wait_closed())
            body = json.loads(raw)
            if (
                type(body) is not dict
                or set(body) != {"protocol_version", "result", "isolation"}
                or body["protocol_version"] != _PROTOCOL
                or not isinstance(body["result"], dict)
            ):
                raise ValueError("external checker service response is invalid")
            locator = (
                locate
                and body["result"].get("schema_version") == "external_checker_forge_locator.v1"
            )
            result_type = ExternalCheckerForgeLocator if locator else ExternalCheckerExecutionResult
            result = result_type.model_validate_json(
                json.dumps(body["result"], ensure_ascii=False, allow_nan=False)
            )
            result.validate_request(checked)
            if locate and not locator and result.outcome != "infrastructure_failed":
                raise ValueError("forge locator returned a work verdict")
            isolation = (
                None
                if body["isolation"] is None
                else ExternalCheckerIsolationReceipt(**body["isolation"])
            )
            if isolation is not None and (
                isolation.platform_manifest_digest != checked.registry.image_digest
            ):
                raise ValueError("external checker isolation receipt is invalid")
            if (locator or result.outcome == "completed") and isolation is None:
                raise ValueError("completed checker result lacks isolation receipt")
            response_type = (
                ExternalCheckerForgeLocatorResponse if locate else ExternalCheckerExecutionResponse
            )
            return response_type(result=result, isolation=isolation)
        except (Exception, asyncio.CancelledError) as exc:
            if possibly_invoked:
                raise ExternalCheckerExecutionOutcomeUnknown() from None
            if isinstance(exc, (TimeoutError, OSError, asyncio.IncompleteReadError)):
                raise ExternalServiceUnavailableError(self._identity) from exc
            if isinstance(exc, (TypeError, ValueError)):
                raise ExternalServiceProtocolError(self._identity) from exc
            raise

    async def health(self) -> ExternalCheckerServiceHealth:
        """Require the service to recheck its configured engine and report readiness."""
        payload = json.dumps(
            {"protocol_version": _PROTOCOL, "operation": "health"},
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await self._proxy_connection()
                try:
                    writer.write(struct.pack(">I", len(payload)) + payload)
                    await writer.drain()
                    size = struct.unpack(">I", await reader.readexactly(4))[0]
                    if size == 0 or size > 16_384:
                        raise ExternalServiceProtocolError(self._identity)
                    raw = await reader.readexactly(size)
                    if await reader.read(1):
                        raise ExternalServiceProtocolError(self._identity)
                finally:
                    writer.close()
                    await writer.wait_closed()
        except ExternalServiceProtocolError:
            raise
        except (TimeoutError, OSError, asyncio.IncompleteReadError) as exc:
            raise ExternalServiceUnavailableError(self._identity) from exc
        try:
            body = json.loads(raw)
            expected = {
                "protocol_version",
                "operation",
                "status",
                "operating_system",
                "architecture",
                "runtime",
                "isolation_mode",
                "cached_platform_manifests",
                "sandbox_uid",
                "sandbox_gid",
            }
            if (
                type(body) is not dict
                or set(body) != expected
                or body["protocol_version"] != _PROTOCOL
                or body["operation"] != "health"
                or body["status"] != "ready"
            ):
                raise ValueError("external checker health response is invalid")
            return ExternalCheckerServiceHealth(
                operating_system=body["operating_system"],
                architecture=body["architecture"],
                runtime=body["runtime"],
                isolation_mode=body["isolation_mode"],
                cached_platform_manifests=body["cached_platform_manifests"],
                sandbox_uid=body["sandbox_uid"],
                sandbox_gid=body["sandbox_gid"],
            )
        except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise ExternalServiceProtocolError(self._identity) from exc


__all__ = (
    "EXTERNAL_CHECKER_CAPABILITY_KEY",
    "EXTERNAL_CHECKER_PROVIDER_KEY",
    "RemoteTlsExternalCheckerAdapter",
)
