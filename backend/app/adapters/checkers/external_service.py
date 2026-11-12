"""Unix-socket adapter for the privileged external checker service."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import struct

from pydantic import ValidationError

from app.interfaces.external_checker_execution import (
    ExternalCheckerExecutionResponse,
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
    ExternalCheckerContractError,
    ExternalCheckerExecutionRequest,
    ExternalCheckerExecutionResult,
)

from app.modules.checkers.api.forge_locator import (
    FORGE_LOCATOR_STAGE_KEY,
    ExternalCheckerForgeLocator,
    require_forge_locator_request,
)

EXTERNAL_CHECKER_CAPABILITY_KEY = "external_checker_execution"
EXTERNAL_CHECKER_PROVIDER_KEY = "unix_socket"
_PROTOCOL = "external_checker_service.v1"
_MAXIMUM_RESPONSE_BYTES = MAX_RESULT_BYTES + 16_384
_EXECUTION_OVERHEAD_SECONDS = EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS / 1000


class UnixSocketExternalCheckerAdapter:
    """Speak one length-framed strict request over a private Unix socket."""

    def __init__(self, *, socket_path: Path, timeout_seconds: float) -> None:
        """Validate immutable local transport settings without opening the socket."""
        if (
            not socket_path.is_absolute()
            or socket_path.is_symlink()
            or type(timeout_seconds) is not float
            or not 0.1 <= timeout_seconds <= 3_700.0
        ):
            raise ValueError("external checker service configuration is invalid")
        self._socket_path = socket_path
        self._timeout_seconds = timeout_seconds
        self._identity = ExternalServiceAdapterIdentity(
            EXTERNAL_CHECKER_CAPABILITY_KEY,
            EXTERNAL_CHECKER_PROVIDER_KEY,
        )

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return the exact explicitly registered provider identity."""
        return self._identity

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
                reader, writer = await asyncio.open_unix_connection(self._socket_path)
                try:
                    writer.write(struct.pack(">I", len(payload)) + payload)
                    await writer.drain()
                    size = struct.unpack(">I", await reader.readexactly(4))[0]
                    if size == 0 or size > _MAXIMUM_RESPONSE_BYTES:
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
        except (TypeError, ValueError, ValidationError, UnicodeError, json.JSONDecodeError) as exc:
            raise ExternalServiceProtocolError(self._identity) from exc

        try:
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
        except (TypeError, ValueError, ValidationError, ExternalCheckerContractError) as exc:
            raise ExternalServiceProtocolError(self._identity) from exc

    async def health(self) -> ExternalCheckerServiceHealth:
        """Require the service to recheck its configured engine and report readiness."""
        payload = json.dumps(
            {"protocol_version": _PROTOCOL, "operation": "health"},
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_unix_connection(self._socket_path)
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
    "UnixSocketExternalCheckerAdapter",
)
