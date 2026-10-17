"""Closed facts from the selected default-plus-external PRE execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from contextlib import AbstractAsyncContextManager
from typing import Literal, Protocol
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.default_checker import WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
from app.modules.checkers.api.default_checker import WorkstreamDefaultCheckerResult
from app.modules.checkers.api.external import ExternalCheckerExecutionResult


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitAdmissionLineage:
    """Immutable TASK, PROJECT, packet and manifest facts needed after verification."""

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
    semantic_manifest_id: UUID
    semantic_manifest_body: dict[str, object]
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
            self.semantic_manifest_id,
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
            or type(self.semantic_manifest_body) is not dict
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
            "semantic_manifest_id": str(self.semantic_manifest_id),
            "semantic_manifest_body": self.semantic_manifest_body,
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
            "semantic_manifest_id",
            "semantic_manifest_body",
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
            semantic_manifest_id=UUID(str(body["semantic_manifest_id"])),
            semantic_manifest_body=body["semantic_manifest_body"],
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
    """One default result followed by the executed required external prefix."""

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
            or self.required_external_count < 0
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


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitReservationFacts:
    """Complete durable PRE request reserved before any external work starts."""

    actor_profile_id: UUID
    identity_link_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    attempt_id: UUID
    idempotency_key: UUID
    attempt_request_digest: str
    prepared_generation_id: UUID
    policy_sha256: str
    default_behavior_sha256: str
    default_input_sha256: str
    archive_sha256: str
    archive_byte_count: int
    semantic_manifest_sha256: str
    execution_budget_ms: int
    admission_lineage: SelectedPreSubmitAdmissionLineage | None = None

    def __post_init__(self) -> None:
        """Reject partial authority, material, policy or default-input custody."""
        identifiers = (
            self.actor_profile_id,
            self.identity_link_id,
            self.project_id,
            self.task_id,
            self.assignment_id,
            self.attempt_id,
            self.idempotency_key,
            self.prepared_generation_id,
        )
        digests = (
            self.attempt_request_digest,
            self.policy_sha256,
            self.default_behavior_sha256,
            self.default_input_sha256,
            self.archive_sha256,
            self.semantic_manifest_sha256,
        )
        if (
            any(type(value) is not UUID for value in identifiers)
            or any(
                type(value) is not str or len(value) != 71 or not value.startswith("sha256:")
                for value in digests
            )
            or self.default_behavior_sha256 != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
            or type(self.archive_byte_count) is not int
            or self.archive_byte_count < 0
            or type(self.execution_budget_ms) is not int
            or not 100 <= self.execution_budget_ms <= 14_400_000
            or (
                self.admission_lineage is not None
                and type(self.admission_lineage) is not SelectedPreSubmitAdmissionLineage
            )
            or (
                self.admission_lineage is not None
                and (
                    canonical_json_hash(self.admission_lineage.semantic_manifest_body)
                    != self.semantic_manifest_sha256
                    or self.admission_lineage.effective_plan_sha256 != self.policy_sha256
                )
            )
        ):
            raise ValueError("selected PRE reservation facts are invalid")

    def canonical_body(self) -> dict[str, object]:
        """Bind the actual contributor, task, ART generation, policy and bytes."""
        return {
            "schema_version": "workstream.selected_pre_submit_reservation.v1",
            "actor_profile_id": str(self.actor_profile_id),
            "identity_link_id": str(self.identity_link_id),
            "project_id": str(self.project_id),
            "task_id": str(self.task_id),
            "assignment_id": str(self.assignment_id),
            "attempt_id": str(self.attempt_id),
            "idempotency_key": str(self.idempotency_key),
            "attempt_request_digest": self.attempt_request_digest,
            "prepared_generation_id": str(self.prepared_generation_id),
            "policy_sha256": self.policy_sha256,
            "default_behavior_sha256": self.default_behavior_sha256,
            "default_input_sha256": self.default_input_sha256,
            "archive_sha256": self.archive_sha256,
            "archive_byte_count": self.archive_byte_count,
            "semantic_manifest_sha256": self.semantic_manifest_sha256,
            "execution_budget_ms": self.execution_budget_ms,
            "admission_lineage": (
                self.admission_lineage.canonical_body()
                if self.admission_lineage is not None
                else None
            ),
        }

    @classmethod
    def from_canonical_body(cls, body: object) -> SelectedPreSubmitReservationFacts:
        """Recover and validate the durable request snapshot at ART publication."""
        if (
            type(body) is not dict
            or set(body)
            != {
                "schema_version",
                "actor_profile_id",
                "identity_link_id",
                "project_id",
                "task_id",
                "assignment_id",
                "attempt_id",
                "idempotency_key",
                "attempt_request_digest",
                "prepared_generation_id",
                "policy_sha256",
                "default_behavior_sha256",
                "default_input_sha256",
                "archive_sha256",
                "archive_byte_count",
                "semantic_manifest_sha256",
                "execution_budget_ms",
                "admission_lineage",
            }
            or body["schema_version"] != "workstream.selected_pre_submit_reservation.v1"
        ):
            raise ValueError("selected PRE reservation facts are invalid")
        lineage_body = body["admission_lineage"]
        return cls(
            actor_profile_id=UUID(str(body["actor_profile_id"])),
            identity_link_id=UUID(str(body["identity_link_id"])),
            project_id=UUID(str(body["project_id"])),
            task_id=UUID(str(body["task_id"])),
            assignment_id=UUID(str(body["assignment_id"])),
            attempt_id=UUID(str(body["attempt_id"])),
            idempotency_key=UUID(str(body["idempotency_key"])),
            attempt_request_digest=body["attempt_request_digest"],
            prepared_generation_id=UUID(str(body["prepared_generation_id"])),
            policy_sha256=body["policy_sha256"],
            default_behavior_sha256=body["default_behavior_sha256"],
            default_input_sha256=body["default_input_sha256"],
            archive_sha256=body["archive_sha256"],
            archive_byte_count=body["archive_byte_count"],
            semantic_manifest_sha256=body["semantic_manifest_sha256"],
            execution_budget_ms=body["execution_budget_ms"],
            admission_lineage=(
                SelectedPreSubmitAdmissionLineage.from_canonical_body(lineage_body)
                if lineage_body is not None
                else None
            ),
        )

    @property
    def request_digest(self) -> str:
        """Return the immutable request identity used by reserve and replay."""
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
            or self.lease_expires_at.tzinfo is None
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
                "schema_version": "workstream.selected_pre_submit_execute.v1",
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
            if self.execution.policy_sha256 != self.lease.reservation.policy_sha256:
                raise ValueError("selected PRE finalize policy is invalid")
        else:
            SelectedPreSubmitInfrastructureUnavailable(self.infrastructure_failure_code or "")

    @property
    def facts_digest(self) -> str:
        """Bind the lease to either exact results or one closed infrastructure code."""
        return canonical_json_hash(
            {
                "schema_version": "workstream.selected_pre_submit_finalize.v1",
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
        elif self.execution is not None or self.infrastructure_failure_code not in {
            "capacity_exceeded",
            "deadline_exceeded",
            "material_unavailable",
            "implementation_unavailable",
            "invalid_output",
        }:
            raise ValueError("selected PRE infrastructure outcome is invalid")

    def canonical_body(self) -> dict[str, object]:
        """Return persisted latency, lease and terminal facts without private paths."""
        return {
            "schema_version": "workstream.selected_pre_submit_terminal.v1",
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
            "queue_latency_ms": int((self.started_at - self.queued_at).total_seconds() * 1000),
            "execution_latency_ms": int(
                (self.completed_at - self.started_at).total_seconds() * 1000
            ),
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
            or body["schema_version"] != "workstream.selected_pre_submit_terminal.v1"
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
    terminal: SelectedPreSubmitTerminalFacts | None


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
