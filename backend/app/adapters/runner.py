"""Authenticated read-only placement for the existing remote runner transports."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import ssl
import struct
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.runner_endpoints import ExternalRunnerEndpoint, ExternalRunnerEndpoints, RunnerDigest
from app.interfaces.external_checker_execution import ExternalCheckerServiceHealth
from app.interfaces.trusted_submission_intake import TrustedIntakeIdentity


_PROBE_SECONDS = 2.0
_MAXIMUM_PLACEMENT_BYTES = 32_768


class RunnerImage(BaseModel):
    """One exact image cached by the native service."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    platform_manifest_digest: RunnerDigest
    config_image_id: RunnerDigest


class RunnerPreProfile(BaseModel):
    """The source-bound PRE profile enforced by the native service."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    profile_sha256: RunnerDigest
    root_sha256: RunnerDigest


class RunnerReadiness(BaseModel):
    """Closed native placement facts, observed over the authenticated runner connection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    protocol_version: Literal["external_checker_service.v1"]
    operation: Literal["placement"]
    config_sha256: RunnerDigest
    epoch: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    health: ExternalCheckerServiceHealth
    draining: bool
    drained: bool
    fits_admission: bool | None
    images: tuple[RunnerImage, ...] = Field(min_length=1, max_length=64)
    pre: RunnerPreProfile | None
    intake: TrustedIntakeIdentity | None
    callback_relay: bool
    trial_authority_manifest_sha256: RunnerDigest | None

    def image(self, platform_manifest_digest: str) -> RunnerImage | None:
        return next((image for image in self.images if image.platform_manifest_digest == platform_manifest_digest), None)

    @model_validator(mode="after")
    def exact_readiness(self) -> Self:
        if (
            (self.health.runtime, self.health.isolation_mode) != ("smolvm", "smol-microvm")
            or self.health.cached_platform_manifests != len(self.images)
            or len({image.platform_manifest_digest for image in self.images}) != len(self.images)
            or self.draining and self.fits_admission is True
            or self.drained and not self.draining
            or self.trial_authority_manifest_sha256 is not None and not self.callback_relay
        ):
            raise ValueError("external runner readiness disagrees with its capabilities")
        return self


@dataclass(frozen=True, slots=True)
class RunnerPlacement:
    """An authenticated endpoint and its observed native boot epoch."""

    endpoint: ExternalRunnerEndpoint
    readiness: RunnerReadiness

    def binding(self) -> dict[str, str]:
        return {"epoch": self.readiness.epoch, "config_sha256": self.readiness.config_sha256}


@dataclass(frozen=True, slots=True)
class RunnerTransport:
    """Share exact mTLS and a bounded read-only selection across CHECKERS and ART."""

    endpoints: ExternalRunnerEndpoints
    ca_path: Path
    certificate_path: Path
    private_key_path: Path

    def __post_init__(self) -> None:
        if any(not path.is_absolute() or path.is_symlink() for path in (
            self.ca_path, self.certificate_path, self.private_key_path,
        )):
            raise ValueError("external runner credential paths are invalid")

    def tls_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(self.ca_path))
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.check_hostname = True
        context.load_cert_chain(certfile=str(self.certificate_path), keyfile=str(self.private_key_path))
        return context

    @staticmethod
    def require_peer(transport: ssl.SSLObject | ssl.SSLSocket, endpoint: ExternalRunnerEndpoint) -> None:
        """Require the exact DNS SAN independently of TLS wildcard matching."""
        certificate = transport.getpeercert()
        if not certificate or ("DNS", endpoint.server_name) not in certificate.get("subjectAltName", ()):
            raise ssl.SSLError("external runner certificate identity differs")

    async def open(self, endpoint: ExternalRunnerEndpoint) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.open_connection(
            endpoint.host, endpoint.port, ssl=self.tls_context(), server_hostname=endpoint.server_name,
        )
        try:
            self.require_peer(writer.get_extra_info("ssl_object"), endpoint)
        except BaseException:
            writer.transport.abort()
            raise
        return reader, writer

    async def probe(
        self, endpoint: ExternalRunnerEndpoint, *, demand: dict[str, object] | None,
    ) -> RunnerPlacement | None:
        """Observe authenticated readiness without sending an execution or a grant."""
        try:
            request = json.dumps({
                "protocol_version": "workstream.remote_runner.v1", "operation": "placement", "demand": demand,
            }, allow_nan=False, separators=(",", ":")).encode()
            async with asyncio.timeout(_PROBE_SECONDS):
                reader, writer = await self.open(endpoint)
                try:
                    writer.write(struct.pack(">I", len(request)) + request)
                    await writer.drain()
                    size = struct.unpack(">I", await reader.readexactly(4))[0]
                    if not 0 < size <= _MAXIMUM_PLACEMENT_BYTES:
                        return None
                    readiness = RunnerReadiness.model_validate_json(await reader.readexactly(size))
                    if (
                        await reader.read(1)
                        or readiness.config_sha256 != endpoint.config_sha256
                        or (readiness.fits_admission is None) != (demand is None)
                    ):
                        return None
                finally:
                    # A read-only probe has no remote lease to settle. Do not let
                    # SSL shutdown extend either the probe cap or original caller budget.
                    writer.transport.abort()
        except (OSError, TimeoutError, asyncio.IncompleteReadError, ValueError):
            return None
        return RunnerPlacement(endpoint, readiness)

    async def select(
        self, claim_key: str, *, qualifies: Callable[[RunnerReadiness], bool],
        demand: dict[str, object] | None = None,
    ) -> RunnerPlacement | None:
        """Pick one qualified node deterministically, independent of probe arrival order."""
        observed = await asyncio.gather(*(self.probe(endpoint, demand=demand) for endpoint in self.endpoints.root))
        return min(
            (placement for placement in observed if placement is not None
             and not placement.readiness.draining
             and (demand is None or placement.readiness.fits_admission is True)
             and qualifies(placement.readiness)),
            key=lambda placement: hashlib.sha256(
                f"{claim_key}\0{placement.endpoint.server_name}".encode()
            ).digest(),
            default=None,
        )
