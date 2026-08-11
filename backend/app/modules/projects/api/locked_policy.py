"""Public PROJECT contracts for exact task-locked policy lineage."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Literal, Mapping, Protocol, get_args
from uuid import UUID

ProjectLockedPolicyGuideStatus = Literal["active", "superseded"]
ProjectLockedPolicyEffectiveStatus = Literal["approved", "superseded"]
ProjectLockedPolicyPreSubmitStatus = Literal["compiled", "superseded"]
ProjectLockedPolicyFailure = Literal["project_locked_policy_context_changed"]


def _is_sha256_digest(value: str) -> bool:
    """Return whether one value is a canonical Workstream SHA-256 token."""
    return (
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _canonical_json(value: Mapping[str, object]) -> str:
    """Return the Workstream canonical JSON representation of one object."""
    if not isinstance(value, Mapping):
        raise ValueError("canonical JSON object is invalid")
    return json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class CanonicalJsonObject:
    """Deeply immutable canonical JSON object encoded as text."""

    value: str

    def __post_init__(self) -> None:
        """Reject invalid or non-canonical JSON object text."""
        try:
            decoded = json.loads(self.value)
        except (TypeError, ValueError) as exc:
            raise ValueError("canonical JSON object is invalid") from exc
        if not isinstance(decoded, dict) or _canonical_json(decoded) != self.value:
            raise ValueError("canonical JSON object is invalid")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> CanonicalJsonObject:
        """Copy a mapping into an immutable canonical representation."""
        return cls(_canonical_json(value))

    @property
    def sha256(self) -> str:
        """Return the SHA-256 identity of the canonical UTF-8 bytes."""
        return f"sha256:{hashlib.sha256(self.value.encode('utf-8')).hexdigest()}"


class ProjectLockedPolicyContextUnavailable(RuntimeError):
    """Report a stable failure without exposing PROJECT persistence."""

    def __init__(self, code: ProjectLockedPolicyFailure) -> None:
        """Validate and retain one failure from the public closed set."""
        if code not in get_args(ProjectLockedPolicyFailure):
            raise ValueError("project locked policy failure code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProjectLockedPolicyContextRequest:
    """Exact TASK-stamped PROJECT selectors for locked-context resolution."""

    project_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    pre_submit_policy_id: UUID
    pre_submit_policy_bundle_hash: str

    def __post_init__(self) -> None:
        """Reject empty versions and malformed SHA-256 selectors."""
        if not self.guide_version.strip():
            raise ValueError("project locked policy guide version is empty")
        for value in (
            self.source_snapshot_hash,
            self.effective_policy_hash,
            self.pre_submit_policy_bundle_hash,
        ):
            if not _is_sha256_digest(value):
                raise ValueError("project locked policy hash is invalid")


@dataclass(frozen=True, slots=True)
class ProjectLockedPolicyContextFacts:
    """Canonical PROJECT lineage resolved from exact historical locked rows."""

    project_id: UUID
    guide_id: UUID
    guide_version: str
    guide_status: ProjectLockedPolicyGuideStatus
    source_snapshot_id: UUID
    source_snapshot_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    effective_policy_status: ProjectLockedPolicyEffectiveStatus
    effective_policy: CanonicalJsonObject
    pre_submit_policy_id: UUID
    pre_submit_policy_bundle_hash: str
    pre_submit_policy_status: ProjectLockedPolicyPreSubmitStatus
    pre_submit_compiler_version: str
    compiled_pre_submit_bundle: CanonicalJsonObject

    def __post_init__(self) -> None:
        """Reject lifecycle values outside the closed historical sets."""
        if (
            not self.guide_version.strip()
            or not all(
                _is_sha256_digest(value)
                for value in (
                    self.source_snapshot_hash,
                    self.effective_policy_hash,
                    self.pre_submit_policy_bundle_hash,
                )
            )
            or self.guide_status not in get_args(ProjectLockedPolicyGuideStatus)
            or self.effective_policy_status not in get_args(ProjectLockedPolicyEffectiveStatus)
            or self.pre_submit_policy_status not in get_args(ProjectLockedPolicyPreSubmitStatus)
            or not self.pre_submit_compiler_version.strip()
        ):
            raise ValueError("project locked policy facts are invalid")


class ProjectLockedPolicyContextPort(Protocol):
    """Transaction-bound PROJECT capability for exact locked policy facts."""

    async def lock_locked_policy_context(
        self,
        request: ProjectLockedPolicyContextRequest,
    ) -> ProjectLockedPolicyContextFacts:
        """Lock, validate, and return exact historical PROJECT facts."""
