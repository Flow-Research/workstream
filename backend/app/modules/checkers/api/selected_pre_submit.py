"""Closed facts from the selected default-plus-external PRE execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from contextlib import AbstractAsyncContextManager
from typing import Literal, Protocol
from uuid import UUID

import json

from pydantic import BaseModel, ConfigDict, Field

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.api.submission_intake import SealedSubmissionSource
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.checkers.api.default_checker import WorkstreamDefaultContext
from app.modules.checkers.api.external_policy import LockedExternalPreSubmitPolicy
from app.modules.checkers.api.default_checker import WorkstreamDefaultCheckerResult
from app.modules.checkers.api.external import ExternalCheckerExecutionResult
from app.modules.checkers.api.historical_selected_pre_submit import HistoricalSelectedPreSubmitTerminal


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitAdmissionLineage:
    """Immutable TASK, PROJECT and packet facts known before source inspection."""

    predecessor_submission_id: UUID | None
    predecessor_submission_version: int | None
    checker_remediation_manifest_id: UUID | None
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_sha256: str
    locked_guide_sha256: str
    effective_policy_id: UUID
    effective_policy_sha256: str
    pre_submit_policy_id: UUID
    pre_submit_policy_sha256: str
    effective_plan_sha256: str
    rules_sha256: str
    external_checker_policies_sha256: str
    post_submit_policy_sha256: str
    post_submit_policy_body: dict[str, object]
    locked_policy_context_hash: str
    packet_sha256: str
    storage_scheme: str
    revision_preparation_id: UUID | None = None
    revision_preparation_sha256: str | None = None

    def __post_init__(self) -> None:
        identifiers = (
            self.guide_id,
            self.source_snapshot_id,
            self.effective_policy_id,
            self.pre_submit_policy_id,
        )
        digests = (
            self.source_snapshot_sha256,
            self.locked_guide_sha256,
            self.effective_policy_sha256,
            self.pre_submit_policy_sha256,
            self.effective_plan_sha256,
            self.rules_sha256,
            self.external_checker_policies_sha256,
            self.post_submit_policy_sha256,
            self.locked_policy_context_hash,
            self.packet_sha256,
        )
        if (
            any(type(value) is not UUID for value in identifiers)
            or (self.predecessor_submission_id is None)
            != (self.predecessor_submission_version is None)
            or (
                self.predecessor_submission_id is not None
                and type(self.predecessor_submission_id) is not UUID
            )
            or (
                self.predecessor_submission_version is not None
                and (
                    type(self.predecessor_submission_version) is not int
                    or self.predecessor_submission_version < 1
                )
            )
            or (self.predecessor_submission_id is None)
            != (self.checker_remediation_manifest_id is None)
            or (self.revision_preparation_id is None)
            != (self.revision_preparation_sha256 is None)
            or (self.revision_preparation_id is not None and (
                type(self.revision_preparation_id) is not UUID
                or self.predecessor_submission_id is None
            ))
            or (self.revision_preparation_sha256 is not None and (
                type(self.revision_preparation_sha256) is not str
                or len(self.revision_preparation_sha256) != 71
                or not self.revision_preparation_sha256.startswith("sha256:")
                or any(character not in "0123456789abcdef"
                       for character in self.revision_preparation_sha256[7:])
            ))
            or (
                self.checker_remediation_manifest_id is not None
                and type(self.checker_remediation_manifest_id) is not UUID
            )
            or not self.guide_version.strip()
            or any(
                type(value) is not str or len(value) != 71 or not value.startswith("sha256:")
                for value in digests
            )
            or type(self.post_submit_policy_body) is not dict
            or canonical_json_hash(
                {
                    key: value
                    for key, value in self.post_submit_policy_body.items()
                    if key != "policy_sha256"
                }
            )
            != self.post_submit_policy_sha256
            or self.post_submit_policy_body.get("policy_sha256") != self.post_submit_policy_sha256
            or self.storage_scheme not in {"local", "s3"}
        ):
            raise ValueError("selected PRE admission lineage is invalid")

    def canonical_body(self) -> dict[str, object]:
        """Return every fact later copied into verified admission custody."""
        body = {
            "predecessor_submission_id": (
                str(self.predecessor_submission_id)
                if self.predecessor_submission_id is not None
                else None
            ),
            "predecessor_submission_version": self.predecessor_submission_version,
            "checker_remediation_manifest_id": (
                str(self.checker_remediation_manifest_id)
                if self.checker_remediation_manifest_id is not None
                else None
            ),
            "guide_id": str(self.guide_id),
            "guide_version": self.guide_version,
            "source_snapshot_id": str(self.source_snapshot_id),
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "locked_guide_sha256": self.locked_guide_sha256,
            "effective_policy_id": str(self.effective_policy_id),
            "effective_policy_sha256": self.effective_policy_sha256,
            "pre_submit_policy_id": str(self.pre_submit_policy_id),
            "pre_submit_policy_sha256": self.pre_submit_policy_sha256,
            "effective_plan_sha256": self.effective_plan_sha256,
            "rules_sha256": self.rules_sha256,
            "external_checker_policies_sha256": (self.external_checker_policies_sha256),
            "post_submit_policy_sha256": self.post_submit_policy_sha256,
            "post_submit_policy_body": self.post_submit_policy_body,
            "locked_policy_context_hash": self.locked_policy_context_hash,
            "packet_sha256": self.packet_sha256,
            "storage_scheme": self.storage_scheme,
        }
        # Preserve the exact canonical bytes of retained requests without an
        # acknowledgement; new revision requests include both frozen facts.
        if self.revision_preparation_id is not None:
            body["revision_preparation_id"] = str(self.revision_preparation_id)
            body["revision_preparation_sha256"] = self.revision_preparation_sha256
        return body

    @classmethod
    def from_canonical_body(cls, body: object) -> SelectedPreSubmitAdmissionLineage:
        """Parse the exact closed body copied into ART's durable intent."""
        required = {
            "predecessor_submission_id",
            "predecessor_submission_version",
            "checker_remediation_manifest_id",
            "guide_id",
            "guide_version",
            "source_snapshot_id",
            "source_snapshot_sha256",
            "locked_guide_sha256",
            "effective_policy_id",
            "effective_policy_sha256",
            "pre_submit_policy_id",
            "pre_submit_policy_sha256",
            "effective_plan_sha256",
            "rules_sha256",
            "external_checker_policies_sha256",
            "post_submit_policy_sha256",
            "post_submit_policy_body",
            "locked_policy_context_hash",
            "packet_sha256",
            "storage_scheme",
        }
        if type(body) is not dict or set(body) not in (
            required, required | {"revision_preparation_id", "revision_preparation_sha256"},
        ):
            raise ValueError("selected PRE admission lineage is invalid")
        if "revision_preparation_id" in body and (
            body["revision_preparation_id"] is None
            or body["revision_preparation_sha256"] is None
        ):
            raise ValueError("selected PRE admission lineage is invalid")
        predecessor = body["predecessor_submission_id"]
        return cls(
            predecessor_submission_id=(UUID(str(predecessor)) if predecessor is not None else None),
            predecessor_submission_version=body["predecessor_submission_version"],
            checker_remediation_manifest_id=(
                UUID(str(body["checker_remediation_manifest_id"]))
                if body["checker_remediation_manifest_id"] is not None
                else None
            ),
            guide_id=UUID(str(body["guide_id"])),
            guide_version=body["guide_version"],
            source_snapshot_id=UUID(str(body["source_snapshot_id"])),
            source_snapshot_sha256=body["source_snapshot_sha256"],
            locked_guide_sha256=body["locked_guide_sha256"],
            effective_policy_id=UUID(str(body["effective_policy_id"])),
            effective_policy_sha256=body["effective_policy_sha256"],
            pre_submit_policy_id=UUID(str(body["pre_submit_policy_id"])),
            pre_submit_policy_sha256=body["pre_submit_policy_sha256"],
            effective_plan_sha256=body["effective_plan_sha256"],
            rules_sha256=body["rules_sha256"],
            external_checker_policies_sha256=body["external_checker_policies_sha256"],
            post_submit_policy_sha256=body["post_submit_policy_sha256"],
            post_submit_policy_body=body["post_submit_policy_body"],
            locked_policy_context_hash=body["locked_policy_context_hash"],
            packet_sha256=body["packet_sha256"],
            storage_scheme=body["storage_scheme"],
            revision_preparation_id=(
                UUID(str(body["revision_preparation_id"]))
                if body.get("revision_preparation_id") is not None else None
            ),
            revision_preparation_sha256=body.get("revision_preparation_sha256"),
        )


@dataclass(frozen=True, slots=True)
class ExternalPreSubmitIsolationFacts:
    """Observed sandbox identity detached from the trusted service response."""

    repository: str
    platform_manifest_digest: str
    platform_manifest_media_type: str
    platform_manifest_byte_count: int
    operating_system: str
    architecture: str
    config_image_id: str
    runtime: str
    isolation_mode: str
    sandbox_uid: int
    sandbox_gid: int


@dataclass(frozen=True, slots=True)
class ExternalPreSubmitMemberFacts:
    """One completed required project PRE image in canonical policy order."""

    order: int
    requirement_id: str
    registry_entry_id: UUID
    registry_entry_digest: str
    request_digest: str
    result: ExternalCheckerExecutionResult
    isolation: ExternalPreSubmitIsolationFacts

    def __post_init__(self) -> None:
        if (
            type(self.order) is not int
            or self.order < 0
            or not self.requirement_id
            or self.result.outcome != "completed"
            or self.result.request_digest != self.request_digest
            or self.result.registry_entry_id != self.registry_entry_id
            or self.result.registry_entry_digest != self.registry_entry_digest
        ):
            raise ValueError("external PRE member facts are invalid")


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitExecutionFacts:
    """Platform defaults and the single selected project PRE result, if run."""

    policy_sha256: str
    workstream_default: WorkstreamDefaultCheckerResult
    required_external_count: int
    external_members: tuple[ExternalPreSubmitMemberFacts, ...]
    eligible: bool

    def __post_init__(self) -> None:
        members = self.external_members
        if (
            not self.policy_sha256.startswith("sha256:")
            or len(self.policy_sha256) != 71
            or type(self.required_external_count) is not int
            or self.required_external_count != 1
            or tuple(item.order for item in members) != tuple(range(len(members)))
            or len({item.requirement_id for item in members}) != len(members)
            or len(members) > self.required_external_count
        ):
            raise ValueError("selected PRE execution facts are invalid")
        external_passed = all(item.result.verdict == "passed" for item in members)
        complete = len(members) == self.required_external_count
        if self.eligible != (self.workstream_default.eligible and complete and external_passed):
            raise ValueError("selected PRE eligibility differs from required results")
        if (
            not self.workstream_default.eligible
            and members
            or any(item.result.verdict == "failed" for item in members[:-1])
        ):
            raise ValueError("selected PRE execution continued after a blocker")

    def validate_reservation(self, reservation: SelectedPreSubmitReservationFacts) -> None:
        """Bind returned policy members to locked selection, independently of echoes.

        This is selection validation only. Source observation and the derived
        project request must also be verified before accepted custody is issued.
        """
        if (
            self.policy_sha256 != reservation.policy_sha256
            or self.workstream_default.behavior_sha256 != reservation.default_behavior_sha256
            or self.required_external_count != len(reservation.policy.entries)
            or (self.workstream_default.eligible and len(self.external_members) != 1)
        ):
            raise ValueError("selected PRE execution selection is invalid")
        for member, selected in zip(self.external_members, reservation.policy.entries, strict=False):
            registry = selected.registry
            if (
                member.requirement_id != selected.requirement_id
                or member.registry_entry_id != registry.registry_entry_id
                or member.registry_entry_digest != registry.entry_digest
                or member.result.phase != "pre_submit"
                or member.isolation.platform_manifest_digest != registry.image_digest
            ):
                raise ValueError("selected PRE execution selection is invalid")
            member.result.validate_registry(registry)

    def canonical_body(self) -> dict[str, object]:
        """Return the complete bounded result body retained by the durable owner."""
        return {
            "schema_version": "workstream.selected_pre_submit_execution.v1",
            "policy_sha256": self.policy_sha256,
            "workstream_default": self.workstream_default.model_dump(mode="json"),
            "required_external_count": self.required_external_count,
            "external_members": [
                {
                    "order": member.order,
                    "requirement_id": member.requirement_id,
                    "registry_entry_id": str(member.registry_entry_id),
                    "registry_entry_digest": member.registry_entry_digest,
                    "request_digest": member.request_digest,
                    "result": member.result.model_dump(mode="json"),
                    "isolation": asdict(member.isolation),
                }
                for member in self.external_members
            ],
            "eligible": self.eligible,
        }

    @classmethod
    def from_canonical_body(cls, body: object) -> SelectedPreSubmitExecutionFacts:
        """Parse the exact bounded result retained for idempotent work replay."""
        if (
            type(body) is not dict
            or set(body)
            != {
                "schema_version",
                "policy_sha256",
                "workstream_default",
                "required_external_count",
                "external_members",
                "eligible",
            }
            or body["schema_version"] != "workstream.selected_pre_submit_execution.v1"
        ):
            raise ValueError("selected PRE execution facts are invalid")
        members = body["external_members"]
        if type(members) is not list:
            raise ValueError("selected PRE execution facts are invalid")
        return cls(
            policy_sha256=body["policy_sha256"],
            workstream_default=WorkstreamDefaultCheckerResult.model_validate(
                body["workstream_default"]
            ),
            required_external_count=body["required_external_count"],
            external_members=tuple(
                ExternalPreSubmitMemberFacts(
                    order=item["order"],
                    requirement_id=item["requirement_id"],
                    registry_entry_id=UUID(str(item["registry_entry_id"])),
                    registry_entry_digest=item["registry_entry_digest"],
                    request_digest=item["request_digest"],
                    result=ExternalCheckerExecutionResult.model_validate(
                        item["result"]
                        | {"registry_entry_id": UUID(str(item["result"]["registry_entry_id"]))}
                    ),
                    isolation=ExternalPreSubmitIsolationFacts(**item["isolation"]),
                )
                for item in members
            ),
            eligible=body["eligible"],
        )

    @property
    def result_digest(self) -> str:
        """Bind every default, project-image and observed-isolation result fact."""
        return canonical_json_hash(self.canonical_body())


class SelectedPreSubmitRuntimeProfile(BaseModel):
    """Explicit deployment bounds; structural validity is not qualification."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    profile_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")
    platform_root_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    cpu_millis: int = Field(gt=0)
    memory_bytes: int = Field(gt=0)
    temporary_disk_bytes: int = Field(gt=0)
    maximum_processes: int = Field(gt=0)
    maximum_output_bytes: int = Field(gt=0)
    maximum_log_bytes: int = Field(gt=0)
    aggregate_deadline_ms: int = Field(ge=100, le=14_400_000)
    archive_limits: SubmissionArchiveLimits


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitReservationFacts:
    """T3 request containing only facts known before guest source inspection."""

    actor_profile_id: UUID
    identity_link_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    attempt_id: UUID
    idempotency_key: UUID
    source: SealedSubmissionSource
    metadata_sha256: str
    locked_context_sha256: str
    foreground_lease_id: UUID
    foreground_lease_generation: int
    pre_deadline_at: datetime
    policy: LockedExternalPreSubmitPolicy
    default_context: WorkstreamDefaultContext
    runtime_profile: SelectedPreSubmitRuntimeProfile
    admission_lineage: SelectedPreSubmitAdmissionLineage

    def __post_init__(self) -> None:
        """Reject missing source, locked context, selected image or fence facts."""
        identifiers = (self.actor_profile_id, self.identity_link_id, self.project_id,
                       self.task_id, self.assignment_id, self.attempt_id,
                       self.idempotency_key, self.foreground_lease_id)
        digests = (self.metadata_sha256, self.locked_context_sha256)
        if (
            any(type(value) is not UUID for value in identifiers)
            or any(type(value) is not str or len(value) != 71
                   or not value.startswith("sha256:")
                   or any(char not in "0123456789abcdef" for char in value[7:])
                   for value in digests)
            or type(self.source) is not SealedSubmissionSource
            or type(self.policy) is not LockedExternalPreSubmitPolicy
            or type(self.default_context) is not WorkstreamDefaultContext
            or type(self.runtime_profile) is not SelectedPreSubmitRuntimeProfile
            or type(self.admission_lineage) is not SelectedPreSubmitAdmissionLineage
            or type(self.foreground_lease_generation) is not int
            or self.foreground_lease_generation < self.source.sealed_upload_fence
            or type(self.pre_deadline_at) is not datetime
            or self.pre_deadline_at.utcoffset() is None
        ):
            raise ValueError("selected PRE reservation facts are invalid")
        lineage = self.admission_lineage
        predecessor = self.default_context.predecessor
        if (
            len(self.policy.entries) != 1
            or lineage.effective_plan_sha256 != self.policy_sha256
            or lineage.rules_sha256 != self.default_context.current_rules_sha256
            or lineage.packet_sha256 != self.default_context.packet.sha256
            or lineage.predecessor_submission_id != (
                predecessor.submission_id if predecessor else None)
            or lineage.predecessor_submission_version != (
                predecessor.submission_version if predecessor else None)
            or self.runtime_profile.archive_limits.maximum_inspection_seconds * 1000
            > self.execution_budget_ms
        ):
            raise ValueError("selected PRE locked context differs")
        resources = self.policy.entries[0].registry.resources
        if (resources.cpu_millis > self.runtime_profile.cpu_millis
                or resources.memory_bytes > self.runtime_profile.memory_bytes
                or resources.maximum_output_bytes > self.runtime_profile.maximum_output_bytes):
            raise ValueError("selected PRE runtime cannot support selected policy")

    @property
    def policy_sha256(self) -> str:
        """Return the validated exact selected policy digest."""
        return self.policy.policy_sha256

    @property
    def default_behavior_sha256(self) -> str:
        """Return the locked code-owned default identity."""
        return self.policy.workstream_default.behavior_sha256

    @property
    def archive_sha256(self) -> str:
        """Return the sealed original ZIP identity, never a semantic digest."""
        return self.source.raw_sha256

    @property
    def archive_byte_count(self) -> int:
        """Return the sealed original ZIP byte count."""
        return self.source.raw_byte_count

    @property
    def execution_budget_ms(self) -> int:
        """Return the aggregate ceiling; the absolute deadline may shorten it."""
        return self.runtime_profile.aggregate_deadline_ms

    def canonical_body(self) -> dict[str, object]:
        """Bind source, operation, fence and immutable context without credentials."""
        return {
            "schema_version": "workstream.selected_pre_submit_reservation.v2",
            **{name: str(getattr(self, name)) for name in (
                "actor_profile_id", "identity_link_id", "project_id", "task_id",
                "assignment_id", "attempt_id", "idempotency_key", "foreground_lease_id")},
            "source": self.source.model_dump(mode="json"),
            "source_sha256": self.source.source_sha256(),
            "metadata_sha256": self.metadata_sha256,
            "locked_context_sha256": self.locked_context_sha256,
            "foreground_lease_generation": self.foreground_lease_generation,
            "pre_deadline_at": self.pre_deadline_at.astimezone(timezone.utc).isoformat(),
            "policy": self.policy.model_dump(mode="json"),
            "default_context": self.default_context.canonical_body(),
            "runtime_profile": self.runtime_profile.model_dump(mode="json"),
            "admission_lineage": self.admission_lineage.canonical_body(),
        }

    @classmethod
    def from_canonical_body(cls, body: object) -> SelectedPreSubmitReservationFacts:
        """Decode only the live source-first schema; historical data is read-only."""
        if type(body) is not dict or body.get("schema_version") != (
            "workstream.selected_pre_submit_reservation.v2"
        ):
            raise ValueError("selected PRE reservation facts are invalid")
        try:
            value = cls(
                **{name: UUID(body[name]) for name in (
                    "actor_profile_id", "identity_link_id", "project_id", "task_id",
                    "assignment_id", "attempt_id", "idempotency_key", "foreground_lease_id")},
                source=SealedSubmissionSource.model_validate_json(json.dumps(body["source"])),
                metadata_sha256=body["metadata_sha256"],
                locked_context_sha256=body["locked_context_sha256"],
                foreground_lease_generation=body["foreground_lease_generation"],
                pre_deadline_at=datetime.fromisoformat(body["pre_deadline_at"]),
                policy=LockedExternalPreSubmitPolicy.model_validate_json(json.dumps(body["policy"])),
                default_context=WorkstreamDefaultContext.from_canonical_body(body["default_context"]),
                runtime_profile=SelectedPreSubmitRuntimeProfile.model_validate_json(
                    json.dumps(body["runtime_profile"])),
                admission_lineage=SelectedPreSubmitAdmissionLineage.from_canonical_body(
                    body["admission_lineage"]),
            )
            if value.canonical_body() != body:
                raise ValueError("selected PRE reservation facts are not canonical")
            return value
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("selected PRE reservation facts are invalid") from exc

    @property
    def request_digest(self) -> str:
        """Return the exact immutable source-first execution request identity."""
        return canonical_json_hash(self.canonical_body())


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitLeaseFacts:
    """Database-timed generation for one genuine pre-admission ART attempt."""

    reservation: SelectedPreSubmitReservationFacts
    lease_id: UUID
    lease_generation: int
    lease_expires_at: datetime

    def __post_init__(self) -> None:
        """Reject a copied identifier or an unbounded/non-current lease shape."""
        if (
            type(self.reservation) is not SelectedPreSubmitReservationFacts
            or type(self.lease_id) is not UUID
            or type(self.lease_generation) is not int
            or self.lease_generation < 1
            or type(self.lease_expires_at) is not datetime
            or self.lease_expires_at.utcoffset() is None
            or self.lease_expires_at > self.reservation.pre_deadline_at
        ):
            raise ValueError("selected PRE lease facts are invalid")


class SelectedPreSubmitExecutionAuthority(Protocol):
    """Process-local capability for one committed durable PRE lease."""

    def consume(
        self,
        *,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
    ) -> SelectedPreSubmitLeaseFacts:
        """Return the exact lease once, or refuse stale/substituted execution."""


class SelectedPreSubmitAdmissionAuthority(Protocol):
    """Process-local authority for immediate selected admission."""

    def consume(
        self,
        *,
        run_id: UUID,
        terminal_digest: str,
        attempt_id: UUID,
        prepared_generation_id: UUID,
        archive_sha256: str,
        semantic_manifest_sha256: str,
    ) -> UUID:
        """Consume only for the exact pass and still-live prepared bytes."""


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitExecuteFacts:
    """Exact committed lease consumed by the fixed PRE executor."""

    lease: SelectedPreSubmitLeaseFacts

    def __post_init__(self) -> None:
        if type(self.lease) is not SelectedPreSubmitLeaseFacts:
            raise ValueError("selected PRE execute facts are invalid")

    @property
    def facts_digest(self) -> str:
        """Bind reservation, lease generation and database expiry."""
        return canonical_json_hash(
            {
                "schema_version": "workstream.selected_pre_submit_execute.v2",
                "reservation": self.lease.reservation.canonical_body(),
                "lease_id": str(self.lease.lease_id),
                "lease_generation": self.lease.lease_generation,
                "lease_expires_at": self.lease.lease_expires_at.isoformat(),
            }
        )


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitFinalizeFacts:
    """Deterministic terminal input consumed before database-timed finalization."""

    lease: SelectedPreSubmitLeaseFacts
    execution: SelectedPreSubmitExecutionFacts | None
    infrastructure_failure_code: str | None

    def __post_init__(self) -> None:
        if type(self.lease) is not SelectedPreSubmitLeaseFacts:
            raise ValueError("selected PRE finalize lease is invalid")
        if (self.execution is None) == (self.infrastructure_failure_code is None):
            raise ValueError("selected PRE finalize outcome is invalid")
        if self.execution is not None:
            if type(self.execution) is not SelectedPreSubmitExecutionFacts:
                raise ValueError("selected PRE finalize execution is invalid")
            self.execution.validate_reservation(self.lease.reservation)
        else:
            SelectedPreSubmitInfrastructureUnavailable(self.infrastructure_failure_code or "")

    @property
    def facts_digest(self) -> str:
        """Bind the lease to either exact results or one closed infrastructure code."""
        return canonical_json_hash(
            {
                "schema_version": "workstream.selected_pre_submit_finalize.v2",
                "execute_facts_digest": SelectedPreSubmitExecuteFacts(self.lease).facts_digest,
                "execution": (
                    self.execution.canonical_body() if self.execution is not None else None
                ),
                "infrastructure_failure_code": self.infrastructure_failure_code,
            }
        )


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitAuthorityEvidence:
    """One retained AUTH decision bound to exact phase facts."""

    evidence_id: UUID
    facts_digest: str

    def __post_init__(self) -> None:
        if (
            type(self.evidence_id) is not UUID
            or len(self.facts_digest) != 71
            or not self.facts_digest.startswith("sha256:")
        ):
            raise ValueError("selected PRE authority evidence is invalid")


class PreparedSelectedPreSubmitExecution(Protocol):
    """Transaction-bound fixed-service execution authority."""

    async def consume(
        self, facts: SelectedPreSubmitExecuteFacts
    ) -> SelectedPreSubmitAuthorityEvidence:
        """Consume the exact committed lease once."""


class PreparedSelectedPreSubmitFinalization(Protocol):
    """Transaction-bound fixed-service finalization authority."""

    async def consume(
        self, facts: SelectedPreSubmitFinalizeFacts
    ) -> SelectedPreSubmitAuthorityEvidence:
        """Consume the exact result or infrastructure outcome once."""


class SelectedPreSubmitAuthorityPort(Protocol):
    """Prepare separate execute and finalize authority before owner locks."""

    def prepare_execution(
        self, reservation: SelectedPreSubmitReservationFacts
    ) -> AbstractAsyncContextManager[PreparedSelectedPreSubmitExecution]:
        """Prepare execution authority before TASK/CHECKERS locks in the claim root."""

    def prepare_finalization(
        self, facts: SelectedPreSubmitFinalizeFacts
    ) -> AbstractAsyncContextManager[PreparedSelectedPreSubmitFinalization]:
        """Prepare exact finalization authority in the terminal root."""


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitCompletion:
    """Terminal facts and immediate admission authority from finalization."""

    terminal: SelectedPreSubmitTerminalFacts
    capability: SelectedPreSubmitAdmissionAuthority | None


class SelectedPreSubmitCoordinationPort(Protocol):
    """CHECKERS-owned durable lease operations used by the ART workflow."""

    async def read_current(
        self, facts: SelectedPreSubmitReservationFacts
    ) -> SelectedPreSubmitCurrentFacts | None:
        """Read one exact actor/key result after TASK custody is locked."""

    async def reserve(self, facts: SelectedPreSubmitReservationFacts) -> UUID:
        """Reserve one exact actor/key request after TASK custody is locked."""

    async def claim(
        self,
        *,
        run_id: UUID,
        facts: SelectedPreSubmitReservationFacts,
        authority: PreparedSelectedPreSubmitExecution,
    ) -> SelectedPreSubmitLeaseFacts:
        """Claim one queued run under TASK-first custody."""

    async def committed_execution(
        self, *, run_id: UUID, lease: SelectedPreSubmitLeaseFacts
    ) -> SelectedPreSubmitExecutionAuthority:
        """Mint process-local execution authority for a committed lease."""

    async def read_expired_lease(
        self, *, run_id: UUID, facts: SelectedPreSubmitReservationFacts
    ) -> SelectedPreSubmitLeaseFacts:
        """Read one expired committed lease under TASK-first custody."""

    async def finalize(
        self,
        *,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
        authority: PreparedSelectedPreSubmitFinalization,
        execution: SelectedPreSubmitExecutionFacts | None,
        infrastructure_failure_code: str | None,
    ) -> SelectedPreSubmitCompletion:
        """Persist one terminal result and return pass authority when eligible."""


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitTerminalFacts:
    """Exact terminal value finalized under a fresh TASK-first transaction."""

    lease: SelectedPreSubmitLeaseFacts
    outcome: Literal["completed", "infrastructure_failed"]
    execution: SelectedPreSubmitExecutionFacts | None
    infrastructure_failure_code: str | None
    queued_at: datetime
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        """Keep work findings separate from recoverable infrastructure outcomes."""
        if type(self.lease) is not SelectedPreSubmitLeaseFacts:
            raise ValueError("selected PRE terminal lease is invalid")
        if any(
            value.tzinfo is None
            for value in (
                self.queued_at,
                self.started_at,
                self.completed_at,
            )
        ) or not (self.queued_at <= self.started_at <= self.completed_at):
            raise ValueError("selected PRE terminal timing is invalid")
        if self.outcome == "completed":
            if (
                type(self.execution) is not SelectedPreSubmitExecutionFacts
                or self.infrastructure_failure_code is not None
                or self.execution.policy_sha256 != self.lease.reservation.policy_sha256
            ):
                raise ValueError("selected PRE completed outcome is invalid")
            self.execution.validate_reservation(self.lease.reservation)
        elif (self.outcome != "infrastructure_failed" or self.execution is not None
              or self.infrastructure_failure_code not in {
            "capacity_exceeded",
            "deadline_exceeded",
            "material_unavailable",
            "implementation_unavailable",
            "invalid_output",
        }):
            raise ValueError("selected PRE infrastructure outcome is invalid")

    def canonical_body(self) -> dict[str, object]:
        """Return persisted latency, lease and terminal facts without private paths."""
        return {
            "schema_version": "workstream.selected_pre_submit_terminal.v2",
            "reservation": self.lease.reservation.canonical_body(),
            "request_digest": self.lease.reservation.request_digest,
            "lease_id": str(self.lease.lease_id),
            "lease_generation": self.lease.lease_generation,
            "lease_expires_at": self.lease.lease_expires_at.isoformat(),
            "outcome": self.outcome,
            "execution": self.execution.canonical_body() if self.execution else None,
            "infrastructure_failure_code": self.infrastructure_failure_code,
            "queued_at": self.queued_at.isoformat(),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "queue_latency_ms": (self.started_at - self.queued_at) // timedelta(milliseconds=1),
            "execution_latency_ms": (self.completed_at - self.started_at) // timedelta(milliseconds=1),
        }

    @classmethod
    def from_canonical_body(cls, body: object) -> SelectedPreSubmitTerminalFacts:
        """Parse and revalidate every persisted lease, result and timing fact."""
        if (
            type(body) is not dict
            or set(body)
            != {
                "schema_version",
                "reservation",
                "request_digest",
                "lease_id",
                "lease_generation",
                "lease_expires_at",
                "outcome",
                "execution",
                "infrastructure_failure_code",
                "queued_at",
                "started_at",
                "completed_at",
                "queue_latency_ms",
                "execution_latency_ms",
            }
            or body["schema_version"] != "workstream.selected_pre_submit_terminal.v2"
        ):
            raise ValueError("selected PRE terminal facts are invalid")
        reservation = SelectedPreSubmitReservationFacts.from_canonical_body(body["reservation"])
        if body["request_digest"] != reservation.request_digest:
            raise ValueError("selected PRE terminal request is invalid")
        execution_body = body["execution"]
        value = cls(
            lease=SelectedPreSubmitLeaseFacts(
                reservation=reservation,
                lease_id=UUID(str(body["lease_id"])),
                lease_generation=body["lease_generation"],
                lease_expires_at=datetime.fromisoformat(body["lease_expires_at"]),
            ),
            outcome=body["outcome"],
            execution=(
                SelectedPreSubmitExecutionFacts.from_canonical_body(execution_body)
                if execution_body is not None
                else None
            ),
            infrastructure_failure_code=body["infrastructure_failure_code"],
            queued_at=datetime.fromisoformat(body["queued_at"]),
            started_at=datetime.fromisoformat(body["started_at"]),
            completed_at=datetime.fromisoformat(body["completed_at"]),
        )
        if value.canonical_body() != body:
            raise ValueError("selected PRE terminal facts are invalid")
        return value

    @property
    def terminal_digest(self) -> str:
        """Bind the exact terminal body used by replay and admission."""
        return canonical_json_hash(self.canonical_body())


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitCurrentFacts:
    """One exact actor/key namespace result safe for bounded ART replay."""

    run_id: UUID
    reservation: SelectedPreSubmitReservationFacts
    status: Literal["queued", "running", "completed", "infrastructure_failed"]
    terminal: SelectedPreSubmitTerminalFacts | None

    def __post_init__(self) -> None:
        terminal_status = self.terminal.outcome if self.terminal is not None else None
        if (
            type(self.run_id) is not UUID
            or type(self.reservation) is not SelectedPreSubmitReservationFacts
            or self.run_id != self.reservation.attempt_id
            or self.status
            not in {
                "queued",
                "running",
                "completed",
                "infrastructure_failed",
            }
            or (self.status in {"queued", "running"}) != (self.terminal is None)
            or (
                self.terminal is not None
                and (
                    self.terminal.lease.reservation != self.reservation
                    or terminal_status != self.status
                )
            )
        ):
            raise ValueError("selected PRE current facts are invalid")


class SelectedPreSubmitInfrastructureUnavailable(RuntimeError):
    """Retain a recoverable PRE infrastructure category, never a work failure."""

    def __init__(self, code: str) -> None:
        if code not in {
            "capacity_exceeded",
            "deadline_exceeded",
            "material_unavailable",
            "implementation_unavailable",
            "invalid_output",
        }:
            raise ValueError("selected PRE infrastructure failure is invalid")
        self.code = code
        super().__init__(code)


class SelectedPreSubmitRequestConflict(RuntimeError):
    """Refuse one actor/key namespace reused with changed stable facts."""


class SelectedPreSubmitUnavailable(RuntimeError):
    """Conceal absent, stale or conflicting durable selected PRE custody."""


class SelectedPreSubmitAuthorityUnavailable(RuntimeError):
    """Conceal fixed-service PRE authorization loss without product facts."""


SelectedPreSubmitRunStatus = Literal["queued", "running", "completed", "infrastructure_failed"]


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitRunView:
    """One retained selected PRE run and its contributor, with revalidated terminal facts."""

    run_id: UUID
    actor_profile_id: UUID
    task_id: UUID
    assignment_id: UUID
    status: SelectedPreSubmitRunStatus
    archive_sha256: str
    archive_byte_count: int
    queued_at: datetime
    completed_at: datetime | None
    terminal: SelectedPreSubmitTerminalFacts | HistoricalSelectedPreSubmitTerminal | None


class SelectedPreSubmitRunReadPort(Protocol):
    """Read retained runs newest first; the caller authorizes."""

    async def read_contributor_runs(
        self, *, actor_profile_id: UUID, task_id: UUID, run_id: UUID | None,
        limit: int, before: tuple[datetime, UUID] | None,
    ) -> tuple[tuple[SelectedPreSubmitRunView, ...], bool]:
        """One contributor's runs for one task, optionally one exact run."""
        ...

    async def read_project_runs(
        self, *, project_id: UUID, statuses: tuple[SelectedPreSubmitRunStatus, ...] | None,
        eligible: bool | None, limit: int, before: tuple[datetime, UUID] | None,
    ) -> tuple[tuple[SelectedPreSubmitRunView, ...], bool]:
        """Every contributor's runs in one project, by stored status and eligibility."""
        ...


__all__ = (
    "ExternalPreSubmitIsolationFacts",
    "ExternalPreSubmitMemberFacts",
    "PreparedSelectedPreSubmitExecution",
    "PreparedSelectedPreSubmitFinalization",
    "SelectedPreSubmitAdmissionAuthority",
    "SelectedPreSubmitAuthorityEvidence",
    "SelectedPreSubmitAuthorityUnavailable",
    "SelectedPreSubmitAuthorityPort",
    "SelectedPreSubmitCompletion",
    "SelectedPreSubmitCoordinationPort",
    "SelectedPreSubmitCurrentFacts",
    "SelectedPreSubmitExecuteFacts",
    "SelectedPreSubmitExecutionFacts",
    "SelectedPreSubmitInfrastructureUnavailable",
    "SelectedPreSubmitFinalizeFacts",
    "SelectedPreSubmitLeaseFacts",
    "SelectedPreSubmitReservationFacts",
    "SelectedPreSubmitRequestConflict",
    "SelectedPreSubmitRunReadPort",
    "SelectedPreSubmitRunStatus",
    "SelectedPreSubmitRunView",
    "SelectedPreSubmitTerminalFacts",
    "SelectedPreSubmitUnavailable",
)
