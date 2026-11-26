"""Mutually authenticated remote adapter for the dedicated checker node."""

from __future__ import annotations

from app.modules.checkers.api.source_contracts import SelectedPreSubmitSourceContracts

import asyncio
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import re
import struct
from typing import Literal

from app.core.cancellation import await_cancellation_resistant
from app.core.hashing import canonical_json_hash
from app.core.runner_endpoints import ExternalRunnerEndpoints
from app.adapters.runner import RunnerPlacement, RunnerTransport

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
from app.modules.checkers.api.external_policy import validated_trial_configuration
from app.modules.checkers.api.model_profiles import configured_model_profile_selector

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
        endpoints: ExternalRunnerEndpoints,
        ca_path: Path,
        certificate_path: Path,
        private_key_path: Path,
        model_proxy_socket_path: Path | None,
        timeout_seconds: float,
        source_contracts: SelectedPreSubmitSourceContracts,
    ) -> None:
        """Validate immutable endpoint settings without opening a connection."""
        if (
            model_proxy_socket_path is not None
            and (not model_proxy_socket_path.is_absolute() or model_proxy_socket_path.is_symlink())
            or type(timeout_seconds) is not float
            or not 0.1 <= timeout_seconds <= 3_700.0
        ):
            raise ValueError("external checker service configuration is invalid")
        self._source_contracts = source_contracts
        self._transport = RunnerTransport(endpoints, ca_path, certificate_path, private_key_path)
        self._post_claim: tuple | None = None
        self._post_placement: RunnerPlacement | None = None
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

    async def _open(self, placement: RunnerPlacement) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await self._transport.open(placement.endpoint)

    @staticmethod
    async def _send_frame(writer: asyncio.StreamWriter, payload: bytes) -> None:
        if not payload or len(payload) > 64 * 1024 * 1024:
            raise ValueError("remote runner frame is invalid")
        writer.write(struct.pack(">I", len(payload)) + payload)
        await writer.drain()

    async def _proxy_connection(self, placement: RunnerPlacement) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await self._open(placement)
        control = json.dumps(
            {
                "protocol_version": _REMOTE_PROTOCOL,
                "operation": "proxy",
                "capability": EXTERNAL_CHECKER_CAPABILITY_KEY,
                **placement.binding(),
            },
            separators=(",", ":"),
        ).encode()
        try:
            await self._send_frame(writer, control)
        except BaseException:
            writer.close()
            await await_cancellation_resistant(writer.wait_closed())
            raise
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
                image_digest = reservation.policy.entries[0].registry.image_digest
                profile_sha256 = canonical_json_hash(reservation.runtime_profile.model_dump(mode="json"))
                placement = await self._transport.select(
                    str(reservation.attempt_id), demand={"kind": "pre", "source_bytes": reservation.source.raw_byte_count},
                    qualifies=lambda state: state.image(image_digest) is not None
                    and state.pre is not None and state.pre.profile_sha256 == profile_sha256
                    and state.pre.root_sha256 == reservation.runtime_profile.platform_root_sha256,
                )
                if placement is None:
                    raise ExternalServiceUnavailableError(self._identity)
                reader, writer = await self._proxy_connection(placement)
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
            if result.receipt.invocation.config_image_id != placement.readiness.image(image_digest).config_image_id:
                raise ValueError("PRE image configuration differs from placement")
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

    async def _place_post(
        self, request: ExternalCheckerExecutionRequest, *, with_model_grant: bool,
    ) -> RunnerPlacement:
        identity = request.identity
        claim = (identity.attempt_id, identity.lease_id, identity.lease_generation)
        registry = request.registry
        trial = validated_trial_configuration(request.configuration, registry)
        callbacks = with_model_grant or trial is not None or configured_model_profile_selector(
            request.configuration, stage=identity.phase,
        ) is not None
        if callbacks and (self._model_proxy_socket_path is None or not self._model_proxy_socket_path.is_socket()):
            raise ExternalServiceUnavailableError(self._identity)
        if self._post_placement is not None:
            if (self._post_claim != claim
                    or self._post_placement.readiness.image(request.registry.image_digest) is None
                    or callbacks and not self._post_placement.readiness.callback_relay):
                raise ValueError("external checker adapter is bound to another claim")
            return self._post_placement

        trial_binding = None if trial is None else {
            "registry_entry_id": str(registry.registry_entry_id), "registry_entry_digest": registry.entry_digest,
            "image_digest": registry.image_digest, "configuration_sha256": request.configuration_sha256,
            "profile_digest": trial.profile.profile_digest, "projection_digest": trial.projection.projection_digest,
        }
        placement = await self._transport.select(
            str(identity.attempt_id), demand={"kind": "post", "memory_bytes": registry.resources.memory_bytes,
                                             "trial": trial_binding},
            qualifies=lambda state: state.image(registry.image_digest) is not None
            and (not callbacks or state.callback_relay)
            and (trial is None or state.trial_authority_manifest_sha256 is not None),
        )
        if placement is None:
            raise ExternalServiceUnavailableError(self._identity)
        self._post_claim, self._post_placement = claim, placement
        return placement

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
                placement = await self._place_post(checked, with_model_grant=model_grant is not None)
                reader, writer = await self._open(placement)
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
                            **placement.binding(),
                        },
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    ).encode()
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
                    ready = {
                        "protocol_version": _REMOTE_PROTOCOL,
                        "operation": "material_ready",
                        "grant_id": grant.grant_id,
                        "binding_digest": grant.binding_digest,
                    }
                    if json.loads(await self._read_frame(reader, 16_384)) != ready:
                        raise ValueError("remote material readiness differs")
                    # The remote owner cannot invoke native execution before
                    # this explicit start. A failed drain of this write may
                    # still follow successful transmission, so retain uncertainty.
                    possibly_invoked = True
                    await self._send_frame(writer, json.dumps(
                        dict(ready, operation="start_execution"),
                        separators=(",", ":"),
                    ).encode())
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
                or isolation.config_image_id != placement.readiness.image(checked.registry.image_digest).config_image_id
                or any(getattr(isolation, field) != getattr(placement.readiness.health, field) for field in (
                    "operating_system", "architecture", "runtime", "isolation_mode", "sandbox_uid", "sandbox_gid",
                ))
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
        """Return authenticated readiness from one qualified configured node."""
        placement = await self._transport.select("health", qualifies=lambda _state: True)
        if placement is None:
            raise ExternalServiceUnavailableError(self._identity)
        return placement.readiness.health


__all__ = (
    "EXTERNAL_CHECKER_CAPABILITY_KEY",
    "EXTERNAL_CHECKER_PROVIDER_KEY",
    "RemoteTlsExternalCheckerAdapter",
)
