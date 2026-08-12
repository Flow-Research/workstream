"""Hidden authorized materialization for one prepared contributor bundle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.artifacts.sources import PreparedArtifact
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitExecutionCustody,
    PreSubmitExecutionResult,
    PreSubmitEvidencePersistenceRequest,
    PreSubmitEvidencePersistenceResult,
    PreSubmitEvidenceService,
)
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspectionResult,
)
from app.modules.artifacts.submission_manifest import (
    SubmissionChangeGateResult,
    SubmissionManifest,
    build_submission_manifest,
)
from app.modules.artifacts.submission_authorization import (
    SubmissionBundlePreparationAuthorization,
)
from app.modules.checkers.api import (
    ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES,
    EffectivePreSubmissionExecutionPlan,
    PreSubmissionExecutionFacts,
    PreSubmissionInfrastructureUnavailableError,
    SubmissionPacketView,
)
from app.modules.projects.api import ProjectLockedPolicyContextPort
from app.modules.tasks.api import TaskSubmissionContextPort

@dataclass(frozen=True, slots=True)
class PreparedBundleMaterializationRequest:
    """ART-private process-local prepared bytes and exact execution facts."""

    prepared_authorization: object
    task_id: UUID
    assignment_id: UUID
    submission_artifact_policy_id: UUID
    checker_policy_id: UUID
    predecessor_submission_version: int | None
    prepared_artifact: PreparedArtifact
    effective_plan: EffectivePreSubmissionExecutionPlan
    inspection: SubmissionArchiveInspectionResult
    manifest: SubmissionManifest
    change_gate: SubmissionChangeGateResult
    packet: SubmissionPacketView


@dataclass(frozen=True, slots=True)
class PreSubmitCheckerExecutionRequest:
    """Exact process-local input supplied to the composition CHECKER adapter."""

    plan: EffectivePreSubmissionExecutionPlan
    commitment: object
    inspection: SubmissionArchiveInspectionResult
    manifest: SubmissionManifest
    change_gate: SubmissionChangeGateResult
    packet: SubmissionPacketView
    prepared_generation_id: UUID
    storage_scheme: str


class PreSubmitCheckerProcessor(Protocol):
    """Async processor built by the composition-root CHECKER adapter."""

    def abort(self) -> None: ...

    async def process(
        self, reader: object, workspace: object
    ) -> PreSubmissionExecutionFacts: ...


class PreSubmitCheckerExecutionFactory(Protocol):
    """Build one process-local CHECKER processor without private imports in ART."""

    @property
    def catalogue_manifest_sha256(self) -> str: ...

    def build(self, request: PreSubmitCheckerExecutionRequest) -> PreSubmitCheckerProcessor: ...


@dataclass(frozen=True, slots=True)
class PreSubmitMaterializationPreparationFacts:
    """Exact scalar facts available before any ZIP inspection."""

    task_id: UUID
    assignment_id: UUID
    project_id: UUID
    guide_id: UUID
    guide_version: int
    source_snapshot_id: UUID
    source_snapshot_hash: str
    submission_artifact_policy_id: UUID
    submission_artifact_policy_hash: str
    checker_policy_id: UUID
    checker_policy_hash: str
    prepared_generation_id: UUID
    plan_sha256: str
    catalogue_manifest_sha256: str
    archive_sha256: str
    archive_byte_count: int
    storage_scheme: str


@final
@dataclass(frozen=True, slots=True)
class PreSubmitMaterializationAuthorityFacts(PreSubmitMaterializationPreparationFacts):
    """Exact inspected resource facts consumed before scratch exposure."""

    semantic_manifest_sha256: str

    @property
    def preparation(self) -> PreSubmitMaterializationPreparationFacts:
        """Return the exact pre-inspection projection of the final facts."""
        return PreSubmitMaterializationPreparationFacts(
            task_id=self.task_id,
            assignment_id=self.assignment_id,
            project_id=self.project_id,
            guide_id=self.guide_id,
            guide_version=self.guide_version,
            source_snapshot_id=self.source_snapshot_id,
            source_snapshot_hash=self.source_snapshot_hash,
            submission_artifact_policy_id=self.submission_artifact_policy_id,
            submission_artifact_policy_hash=self.submission_artifact_policy_hash,
            checker_policy_id=self.checker_policy_id,
            checker_policy_hash=self.checker_policy_hash,
            prepared_generation_id=self.prepared_generation_id,
            plan_sha256=self.plan_sha256,
            catalogue_manifest_sha256=self.catalogue_manifest_sha256,
            archive_sha256=self.archive_sha256,
            archive_byte_count=self.archive_byte_count,
            storage_scheme=self.storage_scheme,
        )


class PreSubmitMaterializationAuthorization(Protocol):
    """Adapter over AUTH's opaque transaction-bound prepared capability."""

    async def prepare(
        self,
        *,
        facts: PreSubmitMaterializationPreparationFacts,
        idempotency_key: UUID,
    ) -> object:
        """Prepare an opaque capability before any submitted byte is inspected."""
        ...

    async def consume(
        self,
        *,
        prepared_authorization: object,
        facts: PreSubmitMaterializationAuthorityFacts,
    ) -> None:
        """Consume the capability against the server-computed final facts."""
        ...


class DenyPreSubmitMaterializationAuthorization:
    """Keep production byte access unavailable until XINT-06A activation."""

    async def prepare(
        self,
        *,
        facts: PreSubmitMaterializationPreparationFacts,
        idempotency_key: UUID,
    ) -> object:
        """Deny capability preparation while the production adapter is absent."""
        del facts, idempotency_key
        raise ArtifactAuthorityDeniedError(
            "pre-submit checker input materialization is unavailable"
        )

    async def consume(
        self,
        *,
        prepared_authorization: object,
        facts: PreSubmitMaterializationAuthorityFacts,
    ) -> None:
        """Deny capability consumption while the production adapter is absent."""
        del prepared_authorization, facts
        raise ArtifactAuthorityDeniedError(
            "pre-submit checker input materialization is unavailable"
        )


class PreparedBundleMaterializationService:
    """Authorize, project, execute, and clean one process-local bundle."""

    def __init__(
        self,
        *,
        authorization: PreSubmitMaterializationAuthorization,
        preparation: ArtifactPreparationService,
        checker_execution: PreSubmitCheckerExecutionFactory,
        storage_scheme: str,
    ) -> None:
        """Compose the bounded materializer from its AUTH and ART dependencies."""
        self._authorization = authorization
        self._preparation = preparation
        self._checker_execution = checker_execution
        if storage_scheme not in ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES:
            raise ValueError("pre-submit materializer storage scheme is invalid")
        self._storage_scheme = storage_scheme

    async def materialize_prepared_bundle(
        self,
        request: PreparedBundleMaterializationRequest,
    ) -> PreSubmitExecutionResult:
        """Consume fixed-service authority before any byte or workspace access."""
        facts = self._authority_facts(request)
        await self._authorization.consume(
            prepared_authorization=request.prepared_authorization,
            facts=facts,
        )
        processor = self._checker_execution.build(
            PreSubmitCheckerExecutionRequest(
                plan=request.effective_plan,
                commitment=request.prepared_artifact.commitment,
                inspection=request.inspection,
                manifest=request.manifest,
                change_gate=request.change_gate,
                packet=request.packet,
                prepared_generation_id=request.prepared_artifact.generation_id,
                storage_scheme=self._storage_scheme,
            ),
        )
        # Intentional friend call: this is the sole authority-gated caller, and
        # the preparation byte-access surface must remain private.
        checker_facts = await self._preparation._process_prepared_submission(
            request.prepared_artifact,
            processor,
            reserved_bytes=request.manifest.total_expanded_bytes,
            maximum_entries=request.manifest.entry_count,
        )
        return PreSubmitExecutionResult(
            custody=PreSubmitExecutionCustody(
                prepared_generation_id=request.prepared_artifact.generation_id,
                archive_sha256=request.prepared_artifact.commitment.sha256,
                archive_byte_count=request.prepared_artifact.commitment.byte_count,
                semantic_manifest_sha256=request.manifest.sha256,
                storage_scheme=self._storage_scheme,
            ),
            checker_facts=checker_facts,
        )

    async def prepare_authorization(
        self,
        *,
        task_id: UUID,
        assignment_id: UUID,
        submission_artifact_policy_id: UUID,
        checker_policy_id: UUID,
        prepared_artifact: PreparedArtifact,
        effective_plan: EffectivePreSubmissionExecutionPlan,
        idempotency_key: UUID,
    ) -> object:
        """Deny unavailable service authority before inspecting the ZIP."""
        facts = self._preparation_facts(
            task_id=task_id,
            assignment_id=assignment_id,
            submission_artifact_policy_id=submission_artifact_policy_id,
            checker_policy_id=checker_policy_id,
            prepared_artifact=prepared_artifact,
            effective_plan=effective_plan,
        )
        return await self._authorization.prepare(
            facts=facts,
            idempotency_key=idempotency_key,
        )

    def _authority_facts(
        self,
        request: PreparedBundleMaterializationRequest,
    ) -> PreSubmitMaterializationAuthorityFacts:
        """Build final authority facts from the canonical inspected manifest."""
        plan = request.effective_plan
        preparation = self._preparation_facts(
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            submission_artifact_policy_id=request.submission_artifact_policy_id,
            checker_policy_id=request.checker_policy_id,
            prepared_artifact=request.prepared_artifact,
            effective_plan=plan,
        )
        if (
            request.manifest != request.change_gate.manifest
            or build_submission_manifest(request.inspection) != request.manifest
            or request.prepared_artifact.commitment.sha256 != request.change_gate.archive_sha256
            or request.prepared_artifact.commitment.byte_count
            != request.change_gate.archive_byte_count
        ):
            raise PreSubmissionInfrastructureUnavailableError(
                "pre_submission_materialization_context_invalid"
            )
        return PreSubmitMaterializationAuthorityFacts(
            **asdict(preparation),
            semantic_manifest_sha256=request.manifest.sha256,
        )

    def _preparation_facts(
        self,
        *,
        task_id: UUID,
        assignment_id: UUID,
        submission_artifact_policy_id: UUID,
        checker_policy_id: UUID,
        prepared_artifact: PreparedArtifact,
        effective_plan: EffectivePreSubmissionExecutionPlan,
    ) -> PreSubmitMaterializationPreparationFacts:
        """Build pre-inspection facts from locked lineage and byte commitment."""
        plan = effective_plan
        if plan.plan_sha256 != canonical_json_hash(plan.as_dict()):
            raise PreSubmissionInfrastructureUnavailableError(
                "pre_submission_plan_identity_invalid"
            )
        if (
            submission_artifact_policy_id != plan.lineage.effective_policy_id
            or checker_policy_id != plan.lineage.pre_submit_policy_id
            or plan.catalogue_manifest_sha256
            != self._checker_execution.catalogue_manifest_sha256
        ):
            raise PreSubmissionInfrastructureUnavailableError(
                "pre_submission_materialization_context_invalid"
            )
        commitment = prepared_artifact.commitment
        return PreSubmitMaterializationPreparationFacts(
            task_id=task_id,
            assignment_id=assignment_id,
            project_id=plan.lineage.project_id,
            guide_id=plan.lineage.guide_id,
            guide_version=plan.lineage.guide_version,
            source_snapshot_id=plan.lineage.source_snapshot_id,
            source_snapshot_hash=plan.lineage.source_snapshot_hash,
            submission_artifact_policy_id=submission_artifact_policy_id,
            submission_artifact_policy_hash=plan.lineage.effective_policy_hash,
            checker_policy_id=checker_policy_id,
            checker_policy_hash=plan.lineage.pre_submit_policy_bundle_hash,
            prepared_generation_id=prepared_artifact.generation_id,
            plan_sha256=plan.plan_sha256,
            catalogue_manifest_sha256=plan.catalogue_manifest_sha256,
            archive_sha256=commitment.sha256,
            archive_byte_count=commitment.byte_count,
            storage_scheme=self._storage_scheme,
        )


class PreparedBundlePreSubmitEvidenceService:
    """Execute in scratch, then persist exact evidence in a fresh transaction."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        materialization: PreparedBundleMaterializationService,
        preparation_authorization: SubmissionBundlePreparationAuthorization,
        task_contexts: TaskSubmissionContextPort,
        project_contexts: ProjectLockedPolicyContextPort,
    ) -> None:
        """Bind execution to the transaction used for durable evidence."""
        self._session = session
        self._materialization = materialization
        self._preparation_authorization = preparation_authorization
        self._task_contexts = task_contexts
        self._project_contexts = project_contexts

    async def execute(
        self,
        request: PreparedBundleMaterializationRequest,
        *,
        preparation_request: SubmissionBundlePreparationRequest,
    ) -> PreSubmitEvidencePersistenceResult:
        """Persist only after materialization has returned and cleaned its scratch lease."""
        if self._session.in_transaction():
            raise RuntimeError(
                "pre-submit evidence orchestration requires a transaction-free session"
            )
        execution = await self.materialize(request)
        return await self.persist(
            request,
            execution=execution,
            preparation_request=preparation_request,
        )

    async def materialize(
        self, request: PreparedBundleMaterializationRequest
    ) -> PreSubmitExecutionResult:
        """Consume fixed-service authority while its owning transaction is active."""
        return await self._materialization.materialize_prepared_bundle(request)

    async def persist(
        self,
        request: PreparedBundleMaterializationRequest,
        *,
        execution: PreSubmitExecutionResult,
        preparation_request: SubmissionBundlePreparationRequest,
    ) -> PreSubmitEvidencePersistenceResult:
        """Persist completed, cleaned execution evidence in a fresh transaction."""
        if self._session.in_transaction():
            raise RuntimeError(
                "pre-submit evidence persistence requires a transaction-free session"
            )
        commitment = request.prepared_artifact.commitment
        prepared_generation_id = request.prepared_artifact.generation_id
        async with self._session.begin():
            await self._session.execute(text("set transaction isolation level read committed"))
            await self._preparation_authorization.revalidate(request=preparation_request)
            return await PreSubmitEvidenceService(
                self._session,
                task_contexts=self._task_contexts,
                project_contexts=self._project_contexts,
            ).persist(
                PreSubmitEvidencePersistenceRequest(
                    actor_profile_id=preparation_request.actor.actor_profile_id,
                    identity_link_id=preparation_request.actor.identity_link_id,
                    task_id=request.task_id,
                    assignment_id=request.assignment_id,
                    predecessor_submission_id=(
                        preparation_request.predecessor_submission_id
                    ),
                    expected_predecessor_submission_version=(
                        request.predecessor_submission_version
                    ),
                    prepared_generation_id=prepared_generation_id,
                    archive_sha256=commitment.sha256,
                    archive_byte_count=commitment.byte_count,
                    semantic_manifest_sha256=request.manifest.sha256,
                    plan=request.effective_plan,
                    execution=execution,
                )
            )
