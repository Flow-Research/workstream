"""Typed boundary for the hidden external checker execution service."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from app.interfaces.external_services import ExternalServiceAdapter
from app.modules.checkers.api.external import (
    ExternalCheckerExecutionRequest,
    ExternalCheckerExecutionResult,
    Identifier,
    Sha256,
)


_REPOSITORY = re.compile(
    r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?(?::[0-9]+)?"
    r"(?:/[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?)*"
)


@dataclass(frozen=True, slots=True)
class ExternalCheckerMaterialGrant:
    """Opaque callback-scoped ART capability; never a filesystem path."""

    grant_id: Identifier
    binding_digest: Sha256

    def __post_init__(self) -> None:
        """Reject path-like identifiers and malformed binding digests."""
        if (
            re.fullmatch(r"extract_[0-9a-f]{32}", self.grant_id) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.binding_digest) is None
        ):
            raise ValueError("external checker material grant is invalid")


@dataclass(frozen=True, slots=True)
class ExternalCheckerIsolationReceipt:
    """Observed service-owned image and sandbox identity for one execution."""

    repository: str
    platform_manifest_digest: Sha256
    platform_manifest_media_type: str
    platform_manifest_byte_count: int
    operating_system: str
    architecture: str
    config_image_id: Sha256
    runtime: str
    isolation_mode: str
    sandbox_uid: int
    sandbox_gid: int

    def __post_init__(self) -> None:
        """Keep image identity and sandbox vocabulary closed and bounded."""
        if (
            len(self.repository) > 255
            or _REPOSITORY.fullmatch(self.repository) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.platform_manifest_digest) is None
            or self.platform_manifest_media_type
            not in {
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.docker.distribution.manifest.v2+json",
            }
            or type(self.platform_manifest_byte_count) is not int
            or not 0 < self.platform_manifest_byte_count <= 10 * 1024 * 1024
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.config_image_id) is None
            or re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,31}", self.operating_system) is None
            or re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,31}", self.architecture) is None
            or self.runtime not in {"runsc", "runc"}
            or self.isolation_mode not in {"gvisor", "docker-dev"}
            or type(self.sandbox_uid) is not int
            or type(self.sandbox_gid) is not int
            or self.sandbox_uid <= 0
            or self.sandbox_gid <= 0
        ):
            raise ValueError("external checker isolation receipt is invalid")


@dataclass(frozen=True, slots=True)
class ExternalCheckerExecutionResponse:
    """Strict normalized result plus the service's bounded isolation receipt."""

    result: ExternalCheckerExecutionResult
    isolation: ExternalCheckerIsolationReceipt | None


@dataclass(frozen=True, slots=True)
class ExternalCheckerServiceHealth:
    """Validated readiness facts returned by the trusted node service."""

    operating_system: str
    architecture: str
    runtime: str
    isolation_mode: str
    cached_platform_manifests: int
    sandbox_uid: int
    sandbox_gid: int

    def __post_init__(self) -> None:
        """Reject open vocabulary and empty-cache readiness claims."""
        if (
            re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,31}", self.operating_system) is None
            or re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,31}", self.architecture) is None
            or self.runtime not in {"runsc", "runc"}
            or self.isolation_mode not in {"gvisor", "docker-dev"}
            or (self.isolation_mode == "gvisor") != (self.runtime == "runsc")
            or type(self.cached_platform_manifests) is not int
            or self.cached_platform_manifests <= 0
            or type(self.sandbox_uid) is not int
            or type(self.sandbox_gid) is not int
            or self.sandbox_uid <= 0
            or self.sandbox_gid <= 0
        ):
            raise ValueError("external checker service health is invalid")


class ExternalCheckerExecutionAdapter(ExternalServiceAdapter, Protocol):
    """Execute one normalized request through the trusted checker service."""

    async def execute(
        self,
        request: ExternalCheckerExecutionRequest,
        grant: ExternalCheckerMaterialGrant,
    ) -> ExternalCheckerExecutionResponse:
        """Return a request-bound result or a sanitized transport failure."""

    async def health(self) -> ExternalCheckerServiceHealth:
        """Return current runtime and cache readiness from the service."""


__all__ = (
    "ExternalCheckerExecutionAdapter",
    "ExternalCheckerExecutionResponse",
    "ExternalCheckerIsolationReceipt",
    "ExternalCheckerMaterialGrant",
    "ExternalCheckerServiceHealth",
)
