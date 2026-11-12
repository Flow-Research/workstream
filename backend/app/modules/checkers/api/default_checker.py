"""Closed contract for the one Workstream-owned default checker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.material import SubmissionMaterialEntry
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView


WORKSTREAM_DEFAULT_CHECKER_ID = "workstream.default"
WORKSTREAM_DEFAULT_CHECKER_VERSION = "v1"
WORKSTREAM_DEFAULT_CHECK_IDS = (
    "archive_safe",
    "received_identity_exact",
    "high_confidence_secrets_absent",
    "submission_changed_for_current_rules",
)
WORKSTREAM_DEFAULT_WARNING_CODES = (
    "submission_summary_missing",
    "submission_attestation_missing",
)
WORKSTREAM_DEFAULT_SECRET_SIGNATURES = (
    (
        "pem_private_key",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        0,
    ),
    ("aws_access_key_id", r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])", 0),
    ("github_token", r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{36}(?![A-Za-z0-9])", 0),
    (
        "github_fine_grained_token",
        r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{80,255}(?![A-Za-z0-9_])",
        0,
    ),
    ("gitlab_token", r"(?<![A-Za-z0-9])glpat-[A-Za-z0-9_-]{20,255}(?![A-Za-z0-9])", 0),
    ("google_api_key", r"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{35}(?![A-Za-z0-9_-])", 0),
    ("slack_token", r"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{20,255}(?![A-Za-z0-9-])", 0),
    ("stripe_live_secret", r"(?<![A-Za-z0-9])sk_live_[0-9A-Za-z]{16,255}(?![A-Za-z0-9])", 0),
)

WORKSTREAM_DEFAULT_BEHAVIOR_MANIFEST = {
    "schema_version": "workstream.default_checker_behavior.v1",
    "checker_id": WORKSTREAM_DEFAULT_CHECKER_ID,
    "checker_version": WORKSTREAM_DEFAULT_CHECKER_VERSION,
    "blocking_checks": list(WORKSTREAM_DEFAULT_CHECK_IDS),
    "warning_only": list(WORKSTREAM_DEFAULT_WARNING_CODES),
    "secret_signatures": [
        {"signature_id": signature_id, "pattern": pattern, "flags": flags}
        for signature_id, pattern, flags in WORKSTREAM_DEFAULT_SECRET_SIGNATURES
    ],
}
WORKSTREAM_DEFAULT_BEHAVIOR_SHA256 = canonical_json_hash(
    WORKSTREAM_DEFAULT_BEHAVIOR_MANIFEST
)

WorkstreamDefaultCheckId = Literal[
    "archive_safe",
    "received_identity_exact",
    "high_confidence_secrets_absent",
    "submission_changed_for_current_rules",
]
WorkstreamDefaultCheckStatus = Literal["passed", "failed", "not_run"]
WorkstreamDefaultFailureCode = Literal[
    "submission_archive_malformed",
    "submission_archive_limit_exceeded",
    "submission_archive_unsafe_entry",
    "submission_archive_collision",
    "submission_archive_encrypted",
    "high_confidence_secret_detected",
    "submission_archive_unchanged",
    "submission_manifest_unchanged",
]
WorkstreamDefaultWarningCode = Literal[
    "submission_summary_missing",
    "submission_attestation_missing",
]
WorkstreamDefaultArchiveFailureCode = Literal[
    "submission_archive_malformed",
    "submission_archive_limit_exceeded",
    "submission_archive_unsafe_entry",
    "submission_archive_collision",
    "submission_archive_encrypted",
    "submission_archive_integrity_failure",
    "submission_archive_timeout",
]


def _require_sha256(value: str) -> None:
    if (
        type(value) is not str
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError("default checker digest is invalid")


@dataclass(frozen=True, slots=True)
class WorkstreamDefaultPredecessor:
    """Detached canonical predecessor identity supplied by the TASK/ART owners."""

    submission_id: UUID
    submission_version: int
    archive_sha256: str
    semantic_manifest_sha256: str

    def __post_init__(self) -> None:
        """Reject incomplete or caller-shaped predecessor identities."""
        if type(self.submission_id) is not UUID:
            raise ValueError("default checker predecessor id is invalid")
        if type(self.submission_version) is not int or self.submission_version <= 0:
            raise ValueError("default checker predecessor version is invalid")
        _require_sha256(self.archive_sha256)
        _require_sha256(self.semantic_manifest_sha256)


@dataclass(frozen=True, slots=True)
class WorkstreamDefaultContext:
    """Locked facts known before source inspection; no derived input identity.

    This value confers no authority. The owner must recover it from the locked
    request, and bind only independently verified raw and manifest evidence.
    """

    predecessor: WorkstreamDefaultPredecessor | None
    predecessor_exists: bool
    current_predecessor: WorkstreamDefaultPredecessor | None
    current_rules_sha256: str
    predecessor_rules_sha256: str | None
    packet: SubmissionPacketView

    def __post_init__(self) -> None:
        """Validate detached rule and predecessor facts before any source read."""
        _require_sha256(self.current_rules_sha256)
        if (
            (self.predecessor is not None
             and type(self.predecessor) is not WorkstreamDefaultPredecessor)
            or (self.current_predecessor is not None
                and type(self.current_predecessor) is not WorkstreamDefaultPredecessor)
            or type(self.predecessor_exists) is not bool
            or type(self.packet) is not SubmissionPacketView
            or (self.predecessor_rules_sha256 is None) != (self.predecessor is None)
        ):
            raise ValueError("default checker context is invalid")
        if self.predecessor_rules_sha256 is not None:
            _require_sha256(self.predecessor_rules_sha256)

    def canonical_body(self) -> dict[str, object]:
        """Serialize locked inputs without claiming an inspected current source."""
        def predecessor_body(value: WorkstreamDefaultPredecessor | None):
            if value is None:
                return None
            return {
                "submission_id": str(value.submission_id),
                "submission_version": value.submission_version,
                "archive_sha256": value.archive_sha256,
                "semantic_manifest_sha256": value.semantic_manifest_sha256,
            }
        return {
            "predecessor": predecessor_body(self.predecessor),
            "predecessor_exists": self.predecessor_exists,
            "current_predecessor": predecessor_body(self.current_predecessor),
            "current_rules_sha256": self.current_rules_sha256,
            "predecessor_rules_sha256": self.predecessor_rules_sha256,
            "packet": {"summary": self.packet.summary,
                       "contributor_attestation": self.packet.contributor_attestation},
        }

    @classmethod
    def from_canonical_body(cls, body: object) -> WorkstreamDefaultContext:
        """Decode a closed locked context independently of derived default input."""
        def predecessor(value):
            if value is None:
                return None
            return WorkstreamDefaultPredecessor(
                **(value | {"submission_id": UUID(value["submission_id"])})
            )
        if type(body) is not dict:
            raise ValueError("default checker context is invalid")
        try:
            value = cls(
                predecessor=predecessor(body["predecessor"]),
                predecessor_exists=body["predecessor_exists"],
                current_predecessor=predecessor(body["current_predecessor"]),
                current_rules_sha256=body["current_rules_sha256"],
                predecessor_rules_sha256=body["predecessor_rules_sha256"],
                packet=SubmissionPacketView(**body["packet"]),
            )
            if value.canonical_body() != body:
                raise ValueError("default checker context is not canonical")
            return value
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("default checker context is invalid") from exc

    def bind_verified_input(
        self, *, archive_sha256: str, archive_byte_count: int,
        archive_media_type: str, semantic_manifest_sha256: str,
        entries: tuple[SubmissionMaterialEntry, ...],
    ) -> WorkstreamDefaultCheckerInput:
        """Derive the canonical input after the owner verifies source and manifest.

        Neither this constructor nor a matching digest proves observation of
        bytes. Guest and CHECKERS must independently supply their verified facts.
        """
        return WorkstreamDefaultCheckerInput(
            archive_sha256=archive_sha256, archive_byte_count=archive_byte_count,
            archive_media_type=archive_media_type,
            semantic_manifest_sha256=semantic_manifest_sha256, entries=entries,
            predecessor=self.predecessor, predecessor_exists=self.predecessor_exists,
            current_predecessor=self.current_predecessor,
            current_rules_sha256=self.current_rules_sha256,
            predecessor_rules_sha256=self.predecessor_rules_sha256, packet=self.packet,
        )


@dataclass(frozen=True, slots=True)
class WorkstreamDefaultCheckerInput:
    """Detached exact custody and task-rule facts; never storage authority."""

    archive_sha256: str
    archive_byte_count: int
    archive_media_type: str
    semantic_manifest_sha256: str
    entries: tuple[SubmissionMaterialEntry, ...]
    predecessor: WorkstreamDefaultPredecessor | None
    predecessor_exists: bool
    current_predecessor: WorkstreamDefaultPredecessor | None
    current_rules_sha256: str
    predecessor_rules_sha256: str | None
    packet: SubmissionPacketView

    def __post_init__(self) -> None:
        """Reject malformed detached facts before any callback-scoped byte read."""
        _require_sha256(self.archive_sha256)
        _require_sha256(self.semantic_manifest_sha256)
        if (
            type(self.archive_byte_count) is not int
            or self.archive_byte_count <= 0
            or self.archive_media_type != "application/zip"
            or type(self.entries) is not tuple
            or any(type(item) is not SubmissionMaterialEntry for item in self.entries)
        ):
            raise ValueError("default checker input is invalid")
        try:
            WorkstreamDefaultContext(
                predecessor=self.predecessor, predecessor_exists=self.predecessor_exists,
                current_predecessor=self.current_predecessor,
                current_rules_sha256=self.current_rules_sha256,
                predecessor_rules_sha256=self.predecessor_rules_sha256, packet=self.packet,
            )
        except ValueError as exc:
            raise ValueError("default checker input is invalid") from exc


def workstream_default_input_body(
    value: WorkstreamDefaultCheckerInput,
) -> dict[str, object]:
    """Return the exact detached input committed by durable PRE reservation."""
    if type(value) is not WorkstreamDefaultCheckerInput:
        raise ValueError("default checker input is invalid")

    def predecessor_body(item: WorkstreamDefaultPredecessor | None):
        return (
            None
            if item is None
            else {
                "submission_id": str(item.submission_id),
                "submission_version": item.submission_version,
                "archive_sha256": item.archive_sha256,
                "semantic_manifest_sha256": item.semantic_manifest_sha256,
            }
        )

    return {
        "schema_version": "workstream.default_checker_input.v1",
        "archive_sha256": value.archive_sha256,
        "archive_byte_count": value.archive_byte_count,
        "archive_media_type": value.archive_media_type,
        "semantic_manifest_sha256": value.semantic_manifest_sha256,
        "entries": [
            {
                "normalized_path": item.normalized_path,
                "entry_type": item.entry_type,
                "byte_count": item.byte_count,
                "sha256": item.sha256,
                "executable": item.executable,
            }
            for item in value.entries
        ],
        "predecessor": predecessor_body(value.predecessor),
        "predecessor_exists": value.predecessor_exists,
        "current_predecessor": predecessor_body(value.current_predecessor),
        "current_rules_sha256": value.current_rules_sha256,
        "predecessor_rules_sha256": value.predecessor_rules_sha256,
        "packet_sha256": value.packet.sha256,
    }


def workstream_default_input_sha256(value: WorkstreamDefaultCheckerInput) -> str:
    """Bind every executable default-checker input without private file bytes."""
    return canonical_json_hash(workstream_default_input_body(value))


class WorkstreamDefaultCheckerValue(BaseModel):
    """Strict immutable value emitted by the default checker."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class WorkstreamDefaultCheck(WorkstreamDefaultCheckerValue):
    """One of the four ordered blocking default outcomes."""

    check_id: WorkstreamDefaultCheckId
    status: WorkstreamDefaultCheckStatus
    failure_code: WorkstreamDefaultFailureCode | None = None
    finding_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        """Keep failures explicit and passes/not-run values finding-free."""
        if (self.status == "failed") != (
            self.failure_code is not None and self.finding_count > 0
        ):
            raise ValueError("default checker outcome shape is invalid")
        if self.status != "failed" and (
            self.failure_code is not None or self.finding_count != 0
        ):
            raise ValueError("default checker non-failure outcome is invalid")
        if self.status == "failed" and not _failure_matches_check(
            self.check_id, self.failure_code
        ):
            raise ValueError("default checker failure does not match its check")
        return self


class WorkstreamDefaultWarning(WorkstreamDefaultCheckerValue):
    """One warning-only packet observation."""

    code: WorkstreamDefaultWarningCode


class WorkstreamDefaultCheckerResult(WorkstreamDefaultCheckerValue):
    """Complete result from the one versioned Workstream default checker."""

    schema_version: Literal["workstream.default_checker_result.v1"] = (
        "workstream.default_checker_result.v1"
    )
    checker_id: Literal["workstream.default"] = WORKSTREAM_DEFAULT_CHECKER_ID
    checker_version: Literal["v1"] = WORKSTREAM_DEFAULT_CHECKER_VERSION
    behavior_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    eligible: bool
    checks: tuple[WorkstreamDefaultCheck, ...] = Field(min_length=4, max_length=4)
    warnings: tuple[WorkstreamDefaultWarning, ...] = Field(max_length=2)

    @model_validator(mode="after")
    def validate_complete_result(self) -> Self:
        """Require the exact four defaults, stable behavior and derived eligibility."""
        if self.behavior_sha256 != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256:
            raise ValueError("default checker behavior identity differs")
        if tuple(item.check_id for item in self.checks) != WORKSTREAM_DEFAULT_CHECK_IDS:
            raise ValueError("default checker result is incomplete or reordered")
        warning_codes = tuple(item.code for item in self.warnings)
        if (
            len(warning_codes) != len(set(warning_codes))
            or warning_codes != tuple(
                code for code in WORKSTREAM_DEFAULT_WARNING_CODES if code in warning_codes
            )
        ):
            raise ValueError("default checker warnings are duplicated or reordered")
        if self.eligible != all(item.status == "passed" for item in self.checks):
            raise ValueError("default checker eligibility differs from blocking checks")
        return self


def _failure_matches_check(
    check_id: WorkstreamDefaultCheckId,
    failure_code: WorkstreamDefaultFailureCode | None,
) -> bool:
    """Bind every closed failure category to exactly one blocking default."""
    if failure_code is None:
        return False
    if check_id == "archive_safe":
        return failure_code.startswith("submission_archive_") and failure_code not in {
            "submission_archive_unchanged"
        }
    if check_id == "high_confidence_secrets_absent":
        return failure_code == "high_confidence_secret_detected"
    if check_id == "submission_changed_for_current_rules":
        return failure_code in {
            "submission_archive_unchanged",
            "submission_manifest_unchanged",
        }
    return False


__all__ = (
    "WORKSTREAM_DEFAULT_BEHAVIOR_MANIFEST",
    "WORKSTREAM_DEFAULT_BEHAVIOR_SHA256",
    "WORKSTREAM_DEFAULT_CHECKER_ID",
    "WORKSTREAM_DEFAULT_CHECKER_VERSION",
    "WORKSTREAM_DEFAULT_CHECK_IDS",
    "WORKSTREAM_DEFAULT_SECRET_SIGNATURES",
    "WORKSTREAM_DEFAULT_WARNING_CODES",
    "WorkstreamDefaultArchiveFailureCode",
    "WorkstreamDefaultCheck",
    "WorkstreamDefaultCheckId",
    "WorkstreamDefaultCheckerInput",
    "WorkstreamDefaultContext",
    "WorkstreamDefaultCheckerResult",
    "WorkstreamDefaultFailureCode",
    "WorkstreamDefaultPredecessor",
    "WorkstreamDefaultWarning",
    "workstream_default_input_body",
    "workstream_default_input_sha256",
)
