"""Hidden authorized materialization for one prepared contributor bundle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.interfaces.artifact_operations import PreparedBundleMaterializationRequest
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.artifacts.sources import PreparedArtifact
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitEvidencePersistenceRequest,
    PreSubmitEvidencePersistenceResult,
    PreSubmitEvidenceService,
)
from app.modules.artifacts.submission_archive import SubmissionArchiveInspector
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.checkers.catalogue import PreSubmissionCheckerCatalogue
from app.modules.checkers.effective_plan import EffectivePreSubmissionExecutionPlan
from app.modules.checkers.pre_submit_execution import (
    ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES,
    DefaultPreSubmissionExecutionInput,
    EffectivePreSubmissionProcessor,
    PreSubmissionExecutionResult,
    PreSubmissionInfrastructureUnavailable,
)


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
    ) -> PreparedAuthorizationHandle:
        """Prepare an opaque capability before any submitted byte is inspected."""
        ...

    async def consume(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        prepared_authorization: PreparedAuthorizationHandle,
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
    ) -> PreparedAuthorizationHandle:
        """Deny capability preparation while the production adapter is absent."""
        del facts, idempotency_key
        raise ArtifactAuthorityDeniedError(
            "pre-submit checker input materialization is unavailable"
        )

    async def consume(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: PreSubmitMaterializationAuthorityFacts,
    ) -> None:
        """Deny capability consumption while the production adapter is absent."""
        del service_identity, action_id, prepared_authorization, facts
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
        archive_inspector: SubmissionArchiveInspector,
        catalogue: PreSubmissionCheckerCatalogue,
        storage_scheme: str,
    ) -> None:
        """Compose the bounded materializer from its AUTH and ART dependencies."""
        self._authorization = authorization
        self._preparation = preparation
        self._archive_inspector = archive_inspector
        self._catalogue = catalogue
        if storage_scheme not in ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES:
            raise ValueError("pre-submit materializer storage scheme is invalid")
        self._storage_scheme = storage_scheme

    async def materialize_prepared_bundle(
        self,
        request: PreparedBundleMaterializationRequest,
    ) -> PreSubmissionExecutionResult:
        """Consume fixed-service authority before any byte or workspace access."""
        facts = self._authority_facts(request)
        await self._authorization.consume(
            service_identity=ServiceIdentity.ARTIFACT_MATERIALIZER,
            action_id=ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE,
            prepared_authorization=request.prepared_authorization,
            facts=facts,
        )
        processor = EffectivePreSubmissionProcessor(
            archive_inspector=self._archive_inspector,
            catalogue=self._catalogue,
            execution_input=DefaultPreSubmissionExecutionInput(
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
        return await self._preparation._process_prepared_submission(
            request.prepared_artifact,
            processor,
            reserved_bytes=request.manifest.total_expanded_bytes,
            maximum_entries=request.manifest.entry_count,
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
    ) -> PreparedAuthorizationHandle:
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
            raise PreSubmissionInfrastructureUnavailable(
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
            raise PreSubmissionInfrastructureUnavailable("pre_submission_plan_identity_invalid")
        if (
            submission_artifact_policy_id != plan.lineage.effective_policy_id
            or checker_policy_id != plan.lineage.pre_submit_policy_id
            or plan.catalogue_manifest_sha256 != self._catalogue.manifest_sha256
        ):
            raise PreSubmissionInfrastructureUnavailable(
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
    ) -> None:
        """Bind execution to the transaction used for durable evidence."""
        self._session = session
        self._materialization = materialization

    async def execute(
        self,
        request: PreparedBundleMaterializationRequest,
        *,
        actor_profile_id: UUID,
        identity_link_id: UUID,
        predecessor_submission_id: UUID | None,
    ) -> PreSubmitEvidencePersistenceResult:
        """Persist only after materialization has returned and cleaned its scratch lease."""
        if self._session.in_transaction():
            raise RuntimeError(
                "pre-submit evidence orchestration requires a transaction-free session"
            )
        commitment = request.prepared_artifact.commitment
        prepared_generation_id = request.prepared_artifact.generation_id
        execution = await self._materialization.materialize_prepared_bundle(request)
        async with self._session.begin():
            await self._session.execute(text("set transaction isolation level read committed"))
            return await PreSubmitEvidenceService(self._session).persist(
                PreSubmitEvidencePersistenceRequest(
                    actor_profile_id=actor_profile_id,
                    identity_link_id=identity_link_id,
                    task_id=request.task_id,
                    assignment_id=request.assignment_id,
                    predecessor_submission_id=predecessor_submission_id,
                    prepared_generation_id=prepared_generation_id,
                    archive_sha256=commitment.sha256,
                    archive_byte_count=commitment.byte_count,
                    semantic_manifest_sha256=request.manifest.sha256,
                    plan=request.effective_plan,
                    execution=execution,
                )
            )
