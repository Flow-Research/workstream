"""Typed ART capability for prepared, trusted guest ZIP/default processing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import BinaryIO, Literal, Protocol
from uuid import UUID

from app.interfaces.external_services import ExternalServiceAdapter
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveEntry,
    SubmissionArchiveInspectionResult,
    SubmissionArchiveLimits,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WorkstreamDefaultCheckerInput,
    WorkstreamDefaultCheckerResult,
)


def _digest(value: str) -> bool:
    """Recognize a complete canonical SHA-256 identity without coercion."""
    return type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


@dataclass(frozen=True, slots=True)
class TrustedIntakePreparation:
    """Authorized pre-upload context; it carries no execution or ART grant."""

    phase: Literal["pre_submit", "post_submit"]
    policy_sha256: str
    limits: SubmissionArchiveLimits
    deadline_ms: int

    def __post_init__(self) -> None:
        """Reject invalid phases, limits and deadlines before a lease can be requested."""
        if (
            self.phase not in {"pre_submit", "post_submit"}
            or not _digest(self.policy_sha256)
            or type(self.limits) is not SubmissionArchiveLimits
            or type(self.deadline_ms) is not int
            or not 1 <= self.deadline_ms <= 7_200_000
        ):
            raise ValueError("trusted intake preparation is invalid")


@dataclass(frozen=True, slots=True)
class TrustedIntakeIdentity:
    """Node-owned trusted image and enforcement identity, never project-selected."""

    image_digest: str
    config_digest: str
    default_behavior_sha256: str
    runtime: str
    isolation_mode: str
    cpu_millis: int
    memory_bytes: int

    def __post_init__(self) -> None:
        """Require the supported behavior, Smol isolation and positive resource limits."""
        if (
            not _digest(self.image_digest)
            or not _digest(self.config_digest)
            or self.default_behavior_sha256 != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
            or (self.runtime, self.isolation_mode) != ("smolvm", "smol-microvm")
            or type(self.cpu_millis) is not int
            or self.cpu_millis <= 0
            or type(self.memory_bytes) is not int
            or self.memory_bytes <= 0
        ):
            raise ValueError("trusted intake identity is invalid")


@dataclass(frozen=True, slots=True)
class TrustedDefaultBinding:
    """Exact committed selected PRE custody supplied by the authorized owner."""

    attempt_id: UUID
    attempt_request_digest: str
    policy_sha256: str
    semantic_manifest_sha256: str
    default_input_sha256: str

    def __post_init__(self) -> None:
        """Require exact record identity and complete hashes for committed default custody."""
        if type(self.attempt_id) is not UUID or not all(
            _digest(value)
            for value in (
                self.attempt_request_digest,
                self.policy_sha256,
                self.semantic_manifest_sha256,
                self.default_input_sha256,
            )
        ):
            raise ValueError("trusted default binding is invalid")


class TrustedIntakeSession(Protocol):
    """One nonserializable process-local lease; methods never expose host paths."""

    @property
    def identity(self) -> TrustedIntakeIdentity: ...

    def inspect(
        self,
        reader: BinaryIO,
        *,
        archive_sha256: str,
        archive_byte_count: int,
    ) -> SubmissionArchiveInspectionResult:
        """Send sealed bytes through PreparedArtifact.inspect's retained reader."""

    def export(self, sink: Callable[[SubmissionArchiveEntry, bytes], None]) -> None:
        """Stream the inspected files into an ART-owned bounded scratch sink."""

    async def evaluate_default(
        self,
        binding: TrustedDefaultBinding,
        value: WorkstreamDefaultCheckerInput,
    ) -> WorkstreamDefaultCheckerResult:
        """Evaluate once after committed PRE reservation and verified material export."""

    def abort(self) -> None:
        """Immediately interrupt socket I/O; close must still drain owned cleanup."""

    async def close(self) -> None:
        """Confirm cleanup before project execution; lost/aborted transport raises.

        The node retains capacity through guardian cleanup even when its ACK
        cannot reach this process. A missing ACK never establishes completion.
        """


class TrustedSubmissionIntakeAdapter(ExternalServiceAdapter, Protocol):
    """ART's sole external processing capability, separate from CHECKERS execute."""

    async def health(self) -> TrustedIntakeIdentity: ...

    async def prepare(self, request: TrustedIntakePreparation) -> TrustedIntakeSession: ...
