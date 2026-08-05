"""Hidden authorized materialization for one prepared contributor bundle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, final
from uuid import UUID

from app.interfaces.artifact_operations import PreparedBundleMaterializationRequest
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.artifacts.submission_archive import SubmissionArchiveInspector
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.checkers.catalogue import PreSubmissionCheckerCatalogue
from app.modules.checkers.pre_submit_execution import (
    DefaultPreSubmissionExecutionInput,
    EffectivePreSubmissionProcessor,
    PreSubmissionExecutionResult,
    PreSubmissionInfrastructureUnavailable,
)


@final
@dataclass(frozen=True, slots=True)
class PreSubmitMaterializationAuthorityFacts:
    """Exact process-local resource facts bound to fixed materializer authority."""

    task_id: UUID
    assignment_id: UUID
    project_id: UUID
    submission_artifact_policy_id: UUID
    checker_policy_id: UUID
    prepared_generation_id: UUID
    plan_sha256: str
    catalogue_manifest_sha256: str
    archive_sha256: str
    archive_byte_count: int
    semantic_manifest_sha256: str
    storage_scheme: str


class PreSubmitMaterializationAuthorization(Protocol):
    """Adapter over AUTH's opaque transaction-bound prepared capability."""

    async def consume(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: PreSubmitMaterializationAuthorityFacts,
    ) -> None: ...


class DenyPreSubmitMaterializationAuthorization:
    """Keep production byte access unavailable until XINT-06A activation."""

    async def consume(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: PreSubmitMaterializationAuthorityFacts,
    ) -> None:
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
    ) -> None:
        self._authorization = authorization
        self._preparation = preparation
        self._archive_inspector = archive_inspector
        self._catalogue = catalogue

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
                storage_scheme=request.storage_scheme,
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

    def _authority_facts(
        self,
        request: PreparedBundleMaterializationRequest,
    ) -> PreSubmitMaterializationAuthorityFacts:
        plan = request.effective_plan
        if (
            request.submission_artifact_policy_id != plan.lineage.effective_policy_id
            or request.checker_policy_id != plan.lineage.pre_submit_policy_id
        ):
            raise PreSubmissionInfrastructureUnavailable(
                "pre_submission_materialization_context_invalid"
            )
        commitment = request.prepared_artifact.commitment
        return PreSubmitMaterializationAuthorityFacts(
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            project_id=plan.lineage.project_id,
            submission_artifact_policy_id=request.submission_artifact_policy_id,
            checker_policy_id=request.checker_policy_id,
            prepared_generation_id=request.prepared_artifact.generation_id,
            plan_sha256=plan.plan_sha256,
            catalogue_manifest_sha256=plan.catalogue_manifest_sha256,
            archive_sha256=commitment.sha256,
            archive_byte_count=commitment.byte_count,
            semantic_manifest_sha256=request.manifest.sha256,
            storage_scheme=request.storage_scheme,
        )
