"""Immutable persistence for one exact effective pre-submit execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import threading
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.models import PreSubmitEvidenceResult, PreSubmitEvidenceSet
from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.checkers.api import (
    EffectivePreSubmissionExecutionPlan,
    PreSubmissionExecutionEntryFacts,
    PreSubmissionExecutionFacts,
)
from app.modules.projects.api import (
    ProjectLockedPolicyContextPort,
    ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
)
from app.modules.tasks.api import (
    TaskSubmissionContextPort,
    TaskSubmissionContextRequest,
    TaskSubmissionContextUnavailable,
)

ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES = frozenset({"local", "s3"})
_CHECKER_EXECUTION_STATUSES = frozenset(
    {"passed", "warning", "advisory_disabled", "dependency_not_run", "failed"}
)


@dataclass(frozen=True, slots=True)
class PreSubmitExecutionCustody:
    """ART-owned custody observed around one CHECKER execution."""

    prepared_generation_id: UUID
    archive_sha256: str
    archive_byte_count: int
    semantic_manifest_sha256: str
    storage_scheme: str


@dataclass(frozen=True, slots=True)
class PreSubmitExecutionResult:
    """ART custody combined with dependency-safe CHECKER result facts."""

    custody: PreSubmitExecutionCustody
    checker_facts: PreSubmissionExecutionFacts

    @property
    def plan_sha256(self) -> str:
        return self.checker_facts.plan_sha256

    @property
    def eligible(self) -> bool:
        return self.checker_facts.eligible

    @property
    def entries(self) -> tuple[PreSubmissionExecutionEntryFacts, ...]:
        return self.checker_facts.entries


class PreSubmitEvidenceConflict(RuntimeError):
    """Reject reuse of one operation identity with different server-owned facts."""


@dataclass(frozen=True, slots=True)
class PreSubmitEvidenceContext:
    """Exact locked facts revalidated by the transaction-owning caller."""

    actor_profile_id: UUID
    identity_link_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None
    predecessor_submission_version: int | None
    prepared_generation_id: UUID
    archive_sha256: str
    archive_byte_count: int
    semantic_manifest_id: UUID
    semantic_manifest_sha256: str
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_sha256: str
    locked_guide_sha256: str
    effective_policy_id: UUID
    locked_artifact_policy_sha256: str
    pre_submit_policy_id: UUID
    locked_checker_policy_sha256: str
    catalogue_id: str
    catalogue_version: str
    catalogue_manifest_sha256: str
    storage_scheme: str

    def __post_init__(self) -> None:
        identifiers = (
            self.actor_profile_id,
            self.identity_link_id,
            self.project_id,
            self.task_id,
            self.assignment_id,
            self.prepared_generation_id,
            self.semantic_manifest_id,
            self.guide_id,
            self.source_snapshot_id,
            self.effective_policy_id,
            self.pre_submit_policy_id,
        )
        if any(type(value) is not UUID for value in identifiers) or (
            self.predecessor_submission_id is not None
            and type(self.predecessor_submission_id) is not UUID
        ):
            raise ValueError("pre-submit evidence identity is invalid")
        if type(self.archive_byte_count) is not int or self.archive_byte_count < 0:
            raise ValueError("pre-submit evidence archive size is invalid")
        if (self.predecessor_submission_id is None) != (
            self.predecessor_submission_version is None
        ) or (
            self.predecessor_submission_version is not None
            and (
                type(self.predecessor_submission_version) is not int
                or self.predecessor_submission_version < 1
            )
        ):
            raise ValueError("pre-submit evidence predecessor lineage is invalid")
        for digest in (
            self.archive_sha256,
            self.semantic_manifest_sha256,
            self.locked_guide_sha256,
            self.source_snapshot_sha256,
            self.locked_artifact_policy_sha256,
            self.locked_checker_policy_sha256,
            self.catalogue_manifest_sha256,
        ):
            ArtifactCommitment.validate_sha256(digest)
        if any(
            type(value) is not str or not value
            for value in (
                self.guide_version,
                self.catalogue_id,
                self.catalogue_version,
                self.storage_scheme,
            )
        ):
            raise ValueError("pre-submit evidence catalogue identity is invalid")
        if self.storage_scheme not in ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES:
            raise ValueError("pre-submit evidence storage scheme is invalid")

    def operation_identity(self, *, effective_plan_sha256: str) -> str:
        """Derive the sole replay namespace from every custody and policy fact."""
        return canonical_json_hash(
            {
                "domain": "workstream.pre_submit_evidence_operation.v1",
                **{
                    key: str(value) if isinstance(value, UUID) else value
                    for key, value in asdict(self).items()
                },
                "effective_plan_sha256": effective_plan_sha256,
            }
        )


@dataclass(frozen=True, slots=True)
class PersistedPreSubmitEvidence:
    evidence_set_id: UUID
    operation_identity: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class PreSubmitEvidencePersistenceRequest:
    """Process-local execution and custody facts supplied after scratch cleanup."""

    actor_profile_id: UUID
    identity_link_id: UUID
    task_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None
    prepared_generation_id: UUID
    archive_sha256: str
    archive_byte_count: int
    semantic_manifest_sha256: str
    plan: EffectivePreSubmissionExecutionPlan
    execution: PreSubmitExecutionResult


@dataclass(frozen=True, slots=True)
class PreSubmitEvidencePersistenceResult:
    """Durable evidence identity plus optional process-local pass capability."""

    evidence: PersistedPreSubmitEvidence
    pass_capability: PreSubmitPassCapability | None
    failure_audit: dict[str, object] | None


def pre_submit_failure_audit_payload(
    *,
    actor_profile_id: UUID,
    project_id: UUID,
    task_id: UUID,
    prepared_generation_id: UUID,
    evidence: PersistedPreSubmitEvidence,
    execution: PreSubmitExecutionResult,
    catalogue_id: str,
    catalogue_version: str,
) -> dict[str, object]:
    """Return the sole bounded, path-free audit projection for a blocked attempt."""
    if execution.eligible:
        raise ValueError("passing pre-submit execution has no failure audit projection")
    counts = {"failed": 0, "warning": 0, "not_run": 0}
    categories: set[str] = set()
    failure_codes: set[str] = set()
    result_outcomes: list[dict[str, str]] = []
    for result in execution.entries:
        result_outcomes.append(
            {
                "definition_id": result.definition_id,
                "definition_version": result.definition_version,
                "status": result.checker_execution_status,
                "message_code": result.message_code,
            }
        )
        if result.checker_execution_status == "failed":
            counts["failed"] += 1
            categories.add(result.classification)
            if result.failure_code is not None:
                failure_codes.add(result.failure_code)
        elif result.checker_execution_status == "warning":
            counts["warning"] += 1
        elif result.checker_execution_status == "dependency_not_run":
            counts["not_run"] += 1
    return {
        "event_type": "pre_submission_check_failed",
        "actor_profile_id": str(actor_profile_id),
        "project_id": str(project_id),
        "task_id": str(task_id),
        "preparation_attempt_id": str(prepared_generation_id),
        "pre_submit_evidence_set_id": str(evidence.evidence_set_id),
        "effective_plan_sha256": execution.plan_sha256,
        "terminal_status": "blocked",
        "catalogue_id": catalogue_id,
        "catalogue_version": catalogue_version,
        "failed_count": counts["failed"],
        "warning_count": counts["warning"],
        "not_run_count": counts["not_run"],
        "failure_categories": sorted(categories),
        "failure_codes": sorted(failure_codes),
        "result_outcomes": result_outcomes,
        "outcome_code": "pre_submission_checker_failed",
    }


def semantic_manifest_identity(semantic_manifest_sha256: str) -> UUID:
    """Derive one provider-neutral identity from the canonical manifest digest."""
    ArtifactCommitment.validate_sha256(semantic_manifest_sha256)
    return uuid5(
        NAMESPACE_URL,
        f"workstream:submission-semantic-manifest:v1:{semantic_manifest_sha256}",
    )


def _validate_execution(
    plan: EffectivePreSubmissionExecutionPlan,
    execution: PreSubmitExecutionResult,
) -> None:
    """Reject custody or CHECKER facts not bound to the exact immutable plan."""
    custody = execution.custody
    try:
        ArtifactCommitment.validate_sha256(custody.archive_sha256)
        ArtifactCommitment.validate_sha256(custody.semantic_manifest_sha256)
    except ValueError as exc:
        raise PreSubmitEvidenceConflict("pre_submission_result_context_invalid") from exc
    if (
        type(custody.prepared_generation_id) is not UUID
        or type(custody.archive_byte_count) is not int
        or custody.archive_byte_count < 0
        or custody.storage_scheme not in ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES
        or type(execution.eligible) is not bool
        or execution.plan_sha256 != plan.plan_sha256
        or len(execution.entries) != len(plan.entries)
    ):
        raise PreSubmitEvidenceConflict("pre_submission_result_context_invalid")
    disqualified = False
    for plan_entry, result in zip(plan.entries, execution.entries, strict=True):
        expected_severity = (
            "warning" if plan_entry.classification == "advisory" else "blocking"
        )
        status = result.checker_execution_status
        if (
            result.dispatch_authority != "workstream.pre_submission_checker_catalogue"
            or result.definition_id != plan_entry.definition_id
            or result.definition_version != plan_entry.definition_version
            or result.public_name != plan_entry.public_name
            or result.policy_source != plan_entry.policy_trace_source
            or result.effective_plan_sha256 != plan.plan_sha256
            or result.rule_instance_id != plan_entry.rule_instance_id
            or result.locked_policy_sha256 != plan.lineage.effective_policy_hash
            or result.phase != plan_entry.phase
            or result.order != plan_entry.order
            or result.classification != plan_entry.classification
            or result.severity != expected_severity
            or status not in _CHECKER_EXECUTION_STATUSES
            or not result.message_code
            or result.failure_code
            != (plan_entry.failure_code if status == "failed" else None)
            or len(result.metadata) != len({key for key, _ in result.metadata})
            or any(type(value) is not int or value < 0 for _, value in result.metadata)
        ):
            raise PreSubmitEvidenceConflict("pre_submission_result_context_invalid")
        disqualified = disqualified or status in {"failed", "dependency_not_run"}
    if execution.eligible == disqualified:
        raise PreSubmitEvidenceConflict("pre_submission_result_context_invalid")


_PRE_SUBMIT_PASS_CAPABILITY_SEAL = object()


class PreSubmitPassCapability:
    """Single-use process-local proof for immediate 04C continuation only."""

    __slots__ = (
        "_consumed",
        "_binding",
        "_lock",
        "_owner",
        "_seal",
        "evidence_set_id",
        "prepared_generation_id",
        "predecessor_submission_id",
        "effective_plan_sha256",
        "archive_sha256",
        "semantic_manifest_sha256",
        "storage_scheme",
    )

    def __init__(self, *_: object, **__: object) -> None:
        """Reject direct construction outside the evidence service."""
        raise TypeError("PreSubmitPassCapability can only be created by pre-submit evidence")

    @classmethod
    def _from_evidence_service(
        cls,
        *,
        owner: PreSubmitEvidenceService,
        binding: object,
        evidence_set_id: UUID,
        prepared_generation_id: UUID,
        predecessor_submission_id: UUID | None,
        effective_plan_sha256: str,
        archive_sha256: str,
        semantic_manifest_sha256: str,
        storage_scheme: str,
    ) -> PreSubmitPassCapability:
        """Mint only from the service that persisted fresh passing evidence."""
        if type(owner) is not PreSubmitEvidenceService or not owner._claims_pass_binding(binding):
            raise TypeError("PreSubmitPassCapability can only be created by pre-submit evidence")
        capability = object.__new__(cls)
        capability._owner = owner
        capability._binding = binding
        capability.evidence_set_id = evidence_set_id
        capability.prepared_generation_id = prepared_generation_id
        capability.predecessor_submission_id = predecessor_submission_id
        capability.effective_plan_sha256 = effective_plan_sha256
        capability.archive_sha256 = archive_sha256
        capability.semantic_manifest_sha256 = semantic_manifest_sha256
        capability.storage_scheme = storage_scheme
        capability._consumed = False
        capability._lock = threading.Lock()
        capability._seal = _PRE_SUBMIT_PASS_CAPABILITY_SEAL
        return capability

    def consume(
        self,
        *,
        prepared_generation_id: UUID,
        predecessor_submission_id: UUID | None,
        effective_plan_sha256: str,
        archive_sha256: str,
        semantic_manifest_sha256: str,
        storage_scheme: str,
    ) -> UUID:
        """Consume once only when the immediate continuation facts still match."""
        with self._lock:
            if (
                self._seal is not _PRE_SUBMIT_PASS_CAPABILITY_SEAL
                or self._consumed
                or (
                    prepared_generation_id != self.prepared_generation_id
                    or predecessor_submission_id != self.predecessor_submission_id
                    or effective_plan_sha256 != self.effective_plan_sha256
                    or archive_sha256 != self.archive_sha256
                    or semantic_manifest_sha256 != self.semantic_manifest_sha256
                    or storage_scheme != self.storage_scheme
                )
            ):
                raise PreSubmitEvidenceConflict("pre_submit_pass_capability_invalid")
            if not self._owner._consume_pass_binding(self._binding):
                raise PreSubmitEvidenceConflict("pre_submit_pass_capability_invalid")
            self._consumed = True
            return self.evidence_set_id

    def _assert_live_prepared_custody(
        self,
        *,
        prepared_generation_id: UUID,
        archive_sha256: str,
    ) -> None:
        """Fail before handoff when this capability is spent or for other bytes."""
        with self._lock:
            if (
                self._seal is not _PRE_SUBMIT_PASS_CAPABILITY_SEAL
                or self._consumed
                or not self._owner._claims_pass_binding(self._binding)
                or prepared_generation_id != self.prepared_generation_id
                or archive_sha256 != self.archive_sha256
            ):
                raise PreSubmitEvidenceConflict("pre_submit_pass_capability_invalid")


class _PreSubmitEvidenceRepository:
    """Insert or replay one immutable evidence set in the caller transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        task_contexts: TaskSubmissionContextPort,
        project_contexts: ProjectLockedPolicyContextPort,
    ) -> None:
        self._session = session
        self._task_contexts = task_contexts
        self._project_contexts = project_contexts

    async def persist(
        self,
        *,
        context: PreSubmitEvidenceContext,
        plan: EffectivePreSubmissionExecutionPlan,
        execution: PreSubmitExecutionResult,
    ) -> PersistedPreSubmitEvidence:
        """Persist exact results once; changed facts under the identity fail closed."""
        transaction = self._session.sync_session.get_transaction()
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
        ):
            raise RuntimeError("pre-submit evidence requires one root transaction")
        _validate_execution(plan, execution)
        operation_identity = context.operation_identity(effective_plan_sha256=execution.plan_sha256)
        values = self._set_values(context, plan, execution, operation_identity)
        evidence_set_id = uuid4()
        inserted_id = await self._session.scalar(
            insert(PreSubmitEvidenceSet)
            .values(id=str(evidence_set_id), **values)
            .on_conflict_do_nothing(index_elements=["operation_identity"])
            .returning(PreSubmitEvidenceSet.id)
        )
        if inserted_id is None:
            existing = await self._session.scalar(
                select(PreSubmitEvidenceSet).where(
                    PreSubmitEvidenceSet.operation_identity == operation_identity
                )
            )
            if existing is None or any(
                getattr(existing, key) != value for key, value in values.items()
            ):
                raise PreSubmitEvidenceConflict("pre_submit_evidence_operation_conflict")
            persisted_results = tuple(
                (
                    await self._session.scalars(
                        select(PreSubmitEvidenceResult)
                        .where(PreSubmitEvidenceResult.evidence_set_id == existing.id)
                        .order_by(PreSubmitEvidenceResult.result_order)
                    )
                ).all()
            )
            expected_results = tuple(
                self._result_values(result_order, result, plan_entry.result_schema)
                for result_order, (plan_entry, result) in enumerate(
                    zip(plan.entries, execution.entries, strict=True)
                )
            )
            if len(persisted_results) != len(expected_results) or any(
                any(getattr(persisted, key) != value for key, value in expected.items())
                for persisted, expected in zip(persisted_results, expected_results, strict=True)
            ):
                raise PreSubmitEvidenceConflict("pre_submit_evidence_result_conflict")
            return PersistedPreSubmitEvidence(
                evidence_set_id=UUID(existing.id),
                operation_identity=operation_identity,
                replayed=True,
            )
        for result_order, (plan_entry, result) in enumerate(
            zip(plan.entries, execution.entries, strict=True)
        ):
            self._session.add(
                PreSubmitEvidenceResult(
                    id=str(uuid4()),
                    evidence_set_id=str(evidence_set_id),
                    **self._result_values(result_order, result, plan_entry.result_schema),
                )
            )
        await self._session.flush()
        return PersistedPreSubmitEvidence(
            evidence_set_id=evidence_set_id,
            operation_identity=operation_identity,
            replayed=False,
        )

    @staticmethod
    def _result_values(
        result_order: int,
        result: PreSubmissionExecutionEntryFacts,
        schema_version: str,
    ) -> dict[str, object]:
        return {
            "result_order": result_order,
            "schema_version": schema_version,
            "dispatch_authority": result.dispatch_authority,
            "definition_id": result.definition_id,
            "definition_version": result.definition_version,
            "public_name": result.public_name,
            "source": result.policy_source,
            "phase": result.phase,
            "classification": result.classification,
            "severity": result.severity,
            "status": result.checker_execution_status,
            "failure_code": result.failure_code,
            "message_code": result.message_code,
            "effective_plan_sha256": result.effective_plan_sha256,
            "rule_instance_id": result.rule_instance_id,
            "locked_policy_sha256": result.locked_policy_sha256,
        }

    @staticmethod
    def _set_values(
        context: PreSubmitEvidenceContext,
        plan: EffectivePreSubmissionExecutionPlan,
        execution: PreSubmitExecutionResult,
        operation_identity: str,
    ) -> dict[str, object]:
        values = {
            key: str(value) if isinstance(value, UUID) else value
            for key, value in asdict(context).items()
        }
        values = {
            "operation_identity": operation_identity,
            **values,
            "effective_plan_sha256": execution.plan_sha256,
            "terminal_status": "passed" if execution.eligible else "blocked",
            "eligible": execution.eligible,
            "result_count": len(execution.entries),
            "result_manifest_sha256": canonical_json_hash(
                {
                    "schema_version": "pre_submit_evidence_result_manifest.v1",
                    "entries": [
                        {
                            "schema_version": plan_entry.result_schema,
                            "dispatch_authority": result.dispatch_authority,
                            "definition_id": result.definition_id,
                            "definition_version": result.definition_version,
                            "public_name": result.public_name,
                            "policy_source": result.policy_source,
                            "effective_plan_sha256": result.effective_plan_sha256,
                            "rule_instance_id": result.rule_instance_id,
                            "locked_policy_sha256": result.locked_policy_sha256,
                            "phase": result.phase,
                            "order": result.order,
                            "classification": result.classification,
                            "severity": result.severity,
                            "status": result.checker_execution_status,
                            "failure_code": result.failure_code,
                            "message_code": result.message_code,
                            "metadata": [list(item) for item in result.metadata],
                        }
                        for plan_entry, result in zip(
                            plan.entries, execution.entries, strict=True
                        )
                    ],
                }
            ),
        }
        values["locked_policy_context_hash"] = canonical_json_hash(
            {
                "guide_id": values["guide_id"],
                "guide_version": values["guide_version"],
                "source_snapshot_id": values["source_snapshot_id"],
                "source_snapshot_sha256": values["source_snapshot_sha256"],
                "locked_guide_sha256": values["locked_guide_sha256"],
                "effective_policy_id": values["effective_policy_id"],
                "locked_artifact_policy_sha256": values["locked_artifact_policy_sha256"],
                "pre_submit_policy_id": values["pre_submit_policy_id"],
                "locked_checker_policy_sha256": values["locked_checker_policy_sha256"],
                "effective_plan_sha256": values["effective_plan_sha256"],
            }
        )
        return values


class PreSubmitEvidenceService:
    """Revalidate locked state and persist evidence in one caller transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        task_contexts: TaskSubmissionContextPort,
        project_contexts: ProjectLockedPolicyContextPort,
    ) -> None:
        self._session = session
        self._task_contexts = task_contexts
        self._project_contexts = project_contexts
        self._repository = _PreSubmitEvidenceRepository(
            session,
            task_contexts=task_contexts,
            project_contexts=project_contexts,
        )
        self._live_pass_bindings: set[object] = set()

    def _claims_pass_binding(self, binding: object) -> bool:
        """Recognize only an issuance registered by this live service instance."""
        return binding in getattr(self, "_live_pass_bindings", set())

    def _consume_pass_binding(self, binding: object) -> bool:
        """Retire one process-local issuance binding exactly once."""
        if binding not in self._live_pass_bindings:
            return False
        self._live_pass_bindings.remove(binding)
        return True

    def _mint_pass_capability(
        self,
        *,
        evidence_set_id: UUID,
        prepared_generation_id: UUID,
        predecessor_submission_id: UUID | None,
        effective_plan_sha256: str,
        archive_sha256: str,
        semantic_manifest_sha256: str,
        storage_scheme: str,
    ) -> PreSubmitPassCapability:
        """Register one unguessable issuance after fresh passing persistence."""
        binding = object()
        self._live_pass_bindings.add(binding)
        try:
            return PreSubmitPassCapability._from_evidence_service(
                owner=self,
                binding=binding,
                evidence_set_id=evidence_set_id,
                prepared_generation_id=prepared_generation_id,
                predecessor_submission_id=predecessor_submission_id,
                effective_plan_sha256=effective_plan_sha256,
                archive_sha256=archive_sha256,
                semantic_manifest_sha256=semantic_manifest_sha256,
                storage_scheme=storage_scheme,
            )
        except BaseException:
            self._live_pass_bindings.discard(binding)
            raise

    async def persist(
        self, request: PreSubmitEvidencePersistenceRequest
    ) -> PreSubmitEvidencePersistenceResult:
        """Persist only when the post-execution database lineage remains exact."""
        transaction = self._session.sync_session.get_transaction()
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
        ):
            raise RuntimeError("pre-submit evidence requires one root transaction")
        _validate_execution(request.plan, request.execution)
        custody = request.execution.custody
        if (
            request.prepared_generation_id != custody.prepared_generation_id
            or request.archive_sha256 != custody.archive_sha256
            or request.archive_byte_count != custody.archive_byte_count
            or request.semantic_manifest_sha256 != custody.semantic_manifest_sha256
        ):
            raise PreSubmitEvidenceConflict("pre_submit_execution_custody_changed")
        try:
            task_context = await self._task_contexts.lock_submission_context(
                TaskSubmissionContextRequest(
                    task_id=request.task_id,
                    assignment_id=request.assignment_id,
                    contributor_id=request.actor_profile_id,
                    predecessor_submission_id=request.predecessor_submission_id,
                )
            )
            references = task_context.locked_project_context
            project_context = await self._project_contexts.lock_locked_policy_context(
                ProjectLockedPolicyContextRequest(
                    project_id=references.project_id,
                    guide_version=references.guide_version,
                    source_snapshot_id=references.source_snapshot_id,
                    source_snapshot_hash=references.source_snapshot_hash,
                    effective_policy_id=references.effective_policy_id,
                    effective_policy_hash=references.effective_policy_hash,
                    pre_submit_policy_id=references.pre_submit_policy_id,
                    pre_submit_policy_bundle_hash=references.pre_submit_policy_bundle_hash,
                )
            )
        except (TaskSubmissionContextUnavailable, ProjectLockedPolicyContextUnavailable) as exc:
            raise PreSubmitEvidenceConflict("pre_submit_locked_context_changed") from exc
        lineage = request.plan.lineage
        guide_version = project_context.guide_version.removeprefix("v")
        try:
            numeric_guide_version = int(guide_version)
        except ValueError as exc:
            raise PreSubmitEvidenceConflict("pre_submit_locked_context_changed") from exc
        if (
            task_context.contributor_id != request.actor_profile_id
            or task_context.predecessor is None
            and request.predecessor_submission_id is not None
            or task_context.predecessor is not None
            and task_context.predecessor.submission_id != request.predecessor_submission_id
            or project_context.project_id != lineage.project_id
            or project_context.guide_id != lineage.guide_id
            or numeric_guide_version != lineage.guide_version
            or project_context.source_snapshot_id != lineage.source_snapshot_id
            or project_context.source_snapshot_hash != lineage.source_snapshot_hash
            or project_context.effective_policy_id != lineage.effective_policy_id
            or project_context.effective_policy_hash != lineage.effective_policy_hash
            or project_context.pre_submit_policy_id != lineage.pre_submit_policy_id
            or project_context.pre_submit_policy_bundle_hash
            != lineage.pre_submit_policy_bundle_hash
        ):
            raise PreSubmitEvidenceConflict("pre_submit_locked_context_changed")
        locked_guide_sha256 = canonical_json_hash(
            {
                "domain": "workstream.locked_task_guide.v1",
                "project_id": str(project_context.project_id),
                "guide_id": str(project_context.guide_id),
                "guide_version": project_context.guide_version,
                "source_snapshot_id": str(project_context.source_snapshot_id),
                "source_snapshot_sha256": project_context.source_snapshot_hash,
            }
        )
        context = PreSubmitEvidenceContext(
            actor_profile_id=request.actor_profile_id,
            identity_link_id=request.identity_link_id,
            project_id=project_context.project_id,
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            predecessor_submission_id=request.predecessor_submission_id,
            predecessor_submission_version=(
                task_context.predecessor.version
                if task_context.predecessor is not None
                else None
            ),
            prepared_generation_id=request.prepared_generation_id,
            archive_sha256=request.archive_sha256,
            archive_byte_count=request.archive_byte_count,
            semantic_manifest_id=semantic_manifest_identity(request.semantic_manifest_sha256),
            semantic_manifest_sha256=request.semantic_manifest_sha256,
            guide_id=project_context.guide_id,
            guide_version=project_context.guide_version,
            source_snapshot_id=project_context.source_snapshot_id,
            source_snapshot_sha256=project_context.source_snapshot_hash,
            locked_guide_sha256=locked_guide_sha256,
            effective_policy_id=project_context.effective_policy_id,
            locked_artifact_policy_sha256=project_context.effective_policy_hash,
            pre_submit_policy_id=project_context.pre_submit_policy_id,
            locked_checker_policy_sha256=project_context.pre_submit_policy_bundle_hash,
            catalogue_id=request.plan.catalogue_id,
            catalogue_version=request.plan.catalogue_version,
            catalogue_manifest_sha256=request.plan.catalogue_manifest_sha256,
            storage_scheme=custody.storage_scheme,
        )
        evidence = await self._repository.persist(
            context=context,
            plan=request.plan,
            execution=request.execution,
        )
        pass_capability = (
            self._mint_pass_capability(
                evidence_set_id=evidence.evidence_set_id,
                prepared_generation_id=request.prepared_generation_id,
                predecessor_submission_id=request.predecessor_submission_id,
                effective_plan_sha256=request.plan.plan_sha256,
                archive_sha256=custody.archive_sha256,
                semantic_manifest_sha256=custody.semantic_manifest_sha256,
                storage_scheme=custody.storage_scheme,
            )
            if request.execution.eligible and not evidence.replayed
            else None
        )
        failure_audit = (
            None
            if request.execution.eligible
            else pre_submit_failure_audit_payload(
                actor_profile_id=request.actor_profile_id,
                project_id=project_context.project_id,
                task_id=request.task_id,
                prepared_generation_id=request.prepared_generation_id,
                evidence=evidence,
                execution=request.execution,
                catalogue_id=request.plan.catalogue_id,
                catalogue_version=request.plan.catalogue_version,
            )
        )
        return PreSubmitEvidencePersistenceResult(
            evidence=evidence,
            pass_capability=pass_capability,
            failure_audit=failure_audit,
        )
