"""Hidden authorized materialization for one prepared contributor bundle."""

from __future__ import annotations

import asyncio
from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol, final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.cancellation import await_cancellation_resistant
from app.interfaces.trusted_submission_intake import TrustedIntakeSession, TrustedDefaultBinding
from app.interfaces.external_services import ExternalServiceAdapterError
from app.modules.artifacts.submission_archive import exported_submission_tree
from app.modules.checkers.api.materialization import PreSubmitMaterialView, SubmissionMaterialEntry
from app.interfaces.external_checker_execution import (
    ExternalCheckerMaterialGrant,
)
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.preparation import (
    ArtifactPreparationService,
    ArtifactPreparationDeadlineError,
    ExternalMaterialFile,
    ExternalMaterialGrantRequest,
)
from app.modules.artifacts.sources import PreparedArtifact
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveInspectionResult,
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_manifest import (
    SubmissionChangeGateResult,
    SubmissionManifest,
    build_submission_manifest,
)
from app.modules.checkers.api.pre_submit_material import (
    ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES,
    SubmissionPacketView,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WorkstreamDefaultCheckerInput,
    WorkstreamDefaultCheckerResult,
    workstream_default_input_body,
)
from app.modules.checkers.api.external import (
    ExternalCheckerExecutionRequest,
    PreSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
)
from app.modules.checkers.api.external_policy import LockedExternalPreSubmitPolicy
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitExecutionAuthority,
    SelectedPreSubmitExecutionFacts,
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
    SelectedPreSubmitInfrastructureUnavailable,
)
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.tasks.api import TaskSubmissionContextFacts


@dataclass(frozen=True, slots=True)
class PreparedBundleMaterializationRequest:
    """ART-private process-local prepared bytes and exact execution facts."""

    prepared_authorization: object
    task_id: UUID
    assignment_id: UUID
    submission_artifact_policy_id: UUID
    checker_policy_id: UUID
    predecessor_submission_version: int | None
    checker_remediation_manifest_id: UUID | None = field(default=None, kw_only=True)
    prepared_artifact: PreparedArtifact
    inspection: SubmissionArchiveInspectionResult
    manifest: SubmissionManifest
    change_gate: SubmissionChangeGateResult
    packet: SubmissionPacketView
    external_policy: LockedExternalPreSubmitPolicy
    default_checker_input: WorkstreamDefaultCheckerInput
    selected_reservation: SelectedPreSubmitReservationFacts
    intake: TrustedIntakeSession


@dataclass(frozen=True, slots=True)
class PreSubmitCheckerExecutionRequest:
    """Exact process-local input supplied to the composition CHECKER adapter."""

    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    commitment: object
    inspection: SubmissionArchiveInspectionResult
    manifest: SubmissionManifest
    change_gate: SubmissionChangeGateResult
    packet: SubmissionPacketView
    prepared_generation_id: UUID
    storage_scheme: str
    external_policy: LockedExternalPreSubmitPolicy
    default_checker_input: WorkstreamDefaultCheckerInput
    attempt_id: UUID
    attempt_request_digest: str


class PreSubmitExternalGrantPort(Protocol):
    """Issue one callback-scoped grant from genuine prepared ART custody."""

    def issue(
        self,
        request: ExternalCheckerExecutionRequest,
        workspace: Path,
    ) -> AbstractContextManager[ExternalCheckerMaterialGrant]: ...


@dataclass(frozen=True, slots=True)
class _SelectedGrantClaim:
    """Minimum genuine selected-run identity required by the ART grant issuer."""

    attempt_id: UUID
    request_digest: str


class _PreSubmitExternalGrantIssuer:
    """Keep private prepared-artifact authority behind a typed callback port."""

    def __init__(
        self,
        *,
        preparation: ArtifactPreparationService,
        prepared: PreparedArtifact,
        request: PreparedBundleMaterializationRequest,
        claim: _SelectedGrantClaim,
    ) -> None:
        self._preparation = preparation
        self._prepared = prepared
        self._request = request
        self._claim = claim

    @contextmanager
    def issue(
        self,
        request: ExternalCheckerExecutionRequest,
        workspace: Path,
    ):
        """Bind the service grant to exact claim, manifest and prepared bytes."""
        checked = ExternalCheckerExecutionRequest.model_validate(request)
        identity = checked.identity
        source = self._request
        project_id = source.selected_reservation.project_id
        if (
            not isinstance(identity, PreSubmitExternalCheckerIdentity)
            or identity.project_id != project_id
            or identity.task_id != source.task_id
            or identity.assignment_id != source.assignment_id
            or identity.prepared_generation_id != source.prepared_artifact.generation_id
            or identity.attempt_id != self._claim.attempt_id
            or identity.attempt_request_digest != self._claim.request_digest
            or len(checked.materials) != 1
            or not isinstance(checked.materials[0], PreSubmitExternalCheckerMaterial)
        ):
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        material = checked.materials[0]
        commitment = source.prepared_artifact.commitment
        if (
            material.prepared_generation_id != source.prepared_artifact.generation_id
            or material.attempt_id != self._claim.attempt_id
            or material.attempt_request_digest != self._claim.request_digest
            or material.archive_sha256 != commitment.sha256
            or material.archive_byte_count != commitment.byte_count
            or material.semantic_manifest_sha256 != source.manifest.sha256
            or material.media_type != commitment.media_type
        ):
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        directories = tuple(
            item.normalized_path
            for item in source.manifest.entries
            if item.entry_type.value == "directory"
        )
        files = tuple(
            ExternalMaterialFile(
                normalized_path=item.normalized_path,
                byte_count=item.byte_count,
                sha256=item.sha256 or "",
                executable=bool(item.executable),
            )
            for item in source.manifest.entries
            if item.entry_type.value == "file"
        )
        grant_request = ExternalMaterialGrantRequest(
            request_digest=checked.request_digest,
            prepared_generation_id=str(identity.prepared_generation_id),
            attempt_id=str(identity.attempt_id),
            attempt_request_digest=identity.attempt_request_digest,
            archive_sha256=material.archive_sha256,
            archive_byte_count=material.archive_byte_count,
            semantic_manifest_sha256=material.semantic_manifest_sha256,
            directories=directories,
            files=files,
        )
        with self._preparation.external_material_grant(
            self._prepared, workspace, grant_request
        ) as grant:
            yield ExternalCheckerMaterialGrant(
                grant_id=grant.grant_id,
                binding_digest=grant.binding_digest,
            )


class _PreSubmitMaterialView:
    """Keep verified reads and the opaque PRE grant inside one ART callback."""

    def __init__(self, tree, *, grants, workspace) -> None:
        self._tree, self._grants, self._workspace = tree, grants, workspace
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("pre-submit material view is closed")

    @property
    def entries(self) -> tuple[SubmissionMaterialEntry, ...]:
        self._require_open()
        return tuple(
            SubmissionMaterialEntry(
                item.normalized_path,
                item.entry_type.value,
                item.byte_count,
                item.sha256,
                item.executable,
            )
            for item in self._tree.entries
        )

    def read_file(self, normalized_path: str, *, maximum_bytes: int) -> bytes:
        self._require_open()
        return self._tree.read_file(normalized_path, maximum_bytes=maximum_bytes)

    def external_checker_grant(self, request):
        self._require_open()
        return self._grants.issue(request, self._workspace)


class PreSubmitCheckerProcessor(Protocol):
    """Async processor built by the composition-root CHECKER adapter."""

    def abort(self) -> None: ...

    async def process(
        self, material: PreSubmitMaterialView, default: WorkstreamDefaultCheckerResult,
    ) -> SelectedPreSubmitExecutionFacts: ...


class PreSubmitCheckerExecutionFactory(Protocol):
    """Build one process-local CHECKER processor without private imports in ART."""

    def build(self, request: PreSubmitCheckerExecutionRequest) -> PreSubmitCheckerProcessor: ...


class _TrustedPreSubmitProcessor:
    """Keep export, default, cleanup and project execution in one ART callback."""

    def __init__(self, *, request, checker, limits, grants) -> None:
        self._request, self._checker, self._limits, self._grants = request, checker, limits, grants
        self._aborted = False
        self._view = None
        self._active = None
        self.intake_cleanup_confirmed = False

    def abort(self) -> None:
        self._aborted = True
        self._request.intake.abort()
        self._checker.abort()
        if self._view is not None:
            self._view.close()
        if self._active is not None:
            self._active.cancel()

    async def process(self, reader, workspace) -> SelectedPreSubmitExecutionFacts:
        del reader  # The retained ZIP is never parsed by the host projection.
        request = self._request
        projection = exported_submission_tree(
            request.intake.export, workspace, expected=request.inspection, limits=self._limits,
        )
        tree = await asyncio.to_thread(projection.__enter__)
        try:
            if self._aborted:
                raise asyncio.CancelledError
            self._view = _PreSubmitMaterialView(tree, grants=self._grants, workspace=workspace)
            reservation = request.selected_reservation
            binding = TrustedDefaultBinding(
                attempt_id=reservation.attempt_id,
                attempt_request_digest=reservation.request_digest,
                policy_sha256=reservation.policy_sha256,
                semantic_manifest_sha256=reservation.semantic_manifest_sha256,
                default_input_sha256=reservation.default_input_sha256,
            )
            self._active = asyncio.create_task(request.intake.evaluate_default(binding, request.default_checker_input))
            default = await self._active
            await request.intake.close()
            self.intake_cleanup_confirmed = True
            if self._aborted:
                raise asyncio.CancelledError
            return await self._checker.process(self._view, default)
        except ExternalServiceAdapterError as exc:
            raise SelectedPreSubmitInfrastructureUnavailable("implementation_unavailable") from exc
        finally:
            self._active = None
            if self._view is not None:
                self._view.close()
            await await_cancellation_resistant(asyncio.to_thread(projection.__exit__, None, None, None))


@dataclass(frozen=True, slots=True)
class PreSubmitMaterializationPreparationFacts:
    """Exact scalar facts available before any ZIP inspection."""

    task_id: UUID
    assignment_id: UUID
    project_id: UUID
    guide_id: UUID
    guide_version: str
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
        session: AsyncSession,
        authorization: PreSubmitMaterializationAuthorization,
        preparation: ArtifactPreparationService,
        checker_execution: PreSubmitCheckerExecutionFactory,
        storage_scheme: str,
        archive_limits: SubmissionArchiveLimits,
    ) -> None:
        """Compose the bounded materializer from its AUTH and ART dependencies."""
        self._session = session
        self._authorization = authorization
        self._preparation = preparation
        self._checker_execution = checker_execution
        if storage_scheme not in ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES:
            raise ValueError("pre-submit materializer storage scheme is invalid")
        self._storage_scheme = storage_scheme
        self._archive_limits = archive_limits


    async def materialize_selected_pre_submit(
        self,
        request: PreparedBundleMaterializationRequest,
        *,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
        execution_authority: SelectedPreSubmitExecutionAuthority,
    ) -> SelectedPreSubmitExecutionFacts:
        """Execute the committed external policy lease against genuine prepared bytes."""
        if self._session.in_transaction():
            raise RuntimeError("selected pre-submit execution requires no transaction")
        checked = execution_authority.consume(run_id=run_id, lease=lease)
        reservation = checked.reservation
        commitment = request.prepared_artifact.commitment
        if (
            run_id != reservation.attempt_id
            or request.task_id != reservation.task_id
            or request.assignment_id != reservation.assignment_id
            or request.selected_reservation != reservation
            or request.prepared_artifact.generation_id != reservation.prepared_generation_id
            or request.external_policy is None
            or request.external_policy.policy_sha256 != reservation.policy_sha256
            or request.default_checker_input is None
            or canonical_json_hash(workstream_default_input_body(request.default_checker_input))
            != reservation.default_input_sha256
            or commitment.sha256 != reservation.archive_sha256
            or commitment.byte_count != reservation.archive_byte_count
            or request.manifest.sha256 != reservation.semantic_manifest_sha256
        ):
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        processor = self._checker_execution.build(
            PreSubmitCheckerExecutionRequest(
                project_id=reservation.project_id,
                task_id=request.task_id,
                assignment_id=request.assignment_id,
                commitment=commitment,
                inspection=request.inspection,
                manifest=request.manifest,
                change_gate=request.change_gate,
                packet=request.packet,
                prepared_generation_id=request.prepared_artifact.generation_id,
                storage_scheme=self._storage_scheme,
                external_policy=request.external_policy,
                default_checker_input=request.default_checker_input,
                attempt_id=run_id,
                attempt_request_digest=reservation.request_digest,
            )
        )
        trusted_processor = _TrustedPreSubmitProcessor(
            request=request, checker=processor, limits=self._archive_limits,
            grants=_PreSubmitExternalGrantIssuer(
                preparation=self._preparation, prepared=request.prepared_artifact,
                request=request, claim=_SelectedGrantClaim(run_id, reservation.request_digest),
            ),
        )
        try:
            result = await self._preparation._process_prepared_submission(
                request.prepared_artifact,
                trusted_processor,
                reserved_bytes=request.manifest.total_expanded_bytes,
                maximum_entries=request.manifest.entry_count + 1,
            )
        except ArtifactPreparationDeadlineError as exc:
            # ART has drained the callback and verified scratch cleanup. Only a
            # confirmed intake close permits immediate terminal finalization.
            if not trusted_processor.intake_cleanup_confirmed:
                raise
            raise SelectedPreSubmitInfrastructureUnavailable("deadline_exceeded") from exc
        if type(result) is not SelectedPreSubmitExecutionFacts:
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        return result

    async def authorize_inspected(self, request: PreparedBundleMaterializationRequest) -> None:
        """Authorize inspected custody for reservation without invoking checker members."""
        await self._authorization.consume(
            prepared_authorization=request.prepared_authorization,
            facts=self._authority_facts(request),
        )


    async def prepare_selected_authorization(
        self,
        *,
        task: TaskSubmissionContextFacts,
        project: ProjectLockedPolicyContextFacts,
        prepared_artifact: PreparedArtifact,
        external_policy: LockedExternalPreSubmitPolicy,
        idempotency_key: UUID,
    ) -> object:
        """Prepare selected material authority before inspecting contributor bytes."""
        references = task.locked_project_context
        commitment = prepared_artifact.commitment
        if (
            task.task_id is None
            or task.assignment_id is None
            or references.project_id != project.project_id
            or references.guide_version != project.guide_version
            or references.source_snapshot_id != project.source_snapshot_id
            or references.source_snapshot_hash != project.source_snapshot_hash
            or references.effective_policy_id != project.effective_policy_id
            or references.effective_policy_hash != project.effective_policy_hash
            or references.pre_submit_policy_id != project.pre_submit_policy_id
            or references.pre_submit_policy_bundle_hash != project.pre_submit_policy_bundle_hash
            or external_policy.policy_sha256
            != canonical_json_hash(
                external_policy.model_dump(mode="json", exclude={"policy_sha256"})
            )
            or external_policy.workstream_default.behavior_sha256
            != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
        ):
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        facts = PreSubmitMaterializationPreparationFacts(
            task_id=task.task_id,
            assignment_id=task.assignment_id,
            project_id=project.project_id,
            guide_id=project.guide_id,
            guide_version=project.guide_version,
            source_snapshot_id=project.source_snapshot_id,
            source_snapshot_hash=project.source_snapshot_hash,
            submission_artifact_policy_id=project.effective_policy_id,
            submission_artifact_policy_hash=project.effective_policy_hash,
            checker_policy_id=project.pre_submit_policy_id,
            checker_policy_hash=project.pre_submit_policy_bundle_hash,
            prepared_generation_id=prepared_artifact.generation_id,
            plan_sha256=external_policy.policy_sha256,
            catalogue_manifest_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
            archive_sha256=commitment.sha256,
            archive_byte_count=commitment.byte_count,
            storage_scheme=self._storage_scheme,
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
        preparation = self._preparation_facts(
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            submission_artifact_policy_id=request.submission_artifact_policy_id,
            checker_policy_id=request.checker_policy_id,
            prepared_artifact=request.prepared_artifact,
            external_policy=request.external_policy,
            selected_reservation=request.selected_reservation,
        )
        if (
            request.manifest != request.change_gate.manifest
            or build_submission_manifest(request.inspection) != request.manifest
            or request.prepared_artifact.commitment.sha256 != request.change_gate.archive_sha256
            or request.prepared_artifact.commitment.byte_count
            != request.change_gate.archive_byte_count
        ):
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
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
        external_policy: LockedExternalPreSubmitPolicy,
        selected_reservation: SelectedPreSubmitReservationFacts,
    ) -> PreSubmitMaterializationPreparationFacts:
        """Build pre-inspection facts from locked lineage and byte commitment."""
        lineage = selected_reservation.admission_lineage
        commitment = prepared_artifact.commitment
        if (
            lineage is None
            or external_policy is None
            or task_id != selected_reservation.task_id
            or assignment_id != selected_reservation.assignment_id
            or prepared_artifact.generation_id != selected_reservation.prepared_generation_id
            or submission_artifact_policy_id != lineage.effective_policy_id
            or checker_policy_id != lineage.pre_submit_policy_id
            or external_policy.policy_sha256 != selected_reservation.policy_sha256
            or commitment.sha256 != selected_reservation.archive_sha256
            or commitment.byte_count != selected_reservation.archive_byte_count
        ):
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        return PreSubmitMaterializationPreparationFacts(
            task_id=task_id,
            assignment_id=assignment_id,
            project_id=selected_reservation.project_id,
            guide_id=lineage.guide_id,
            guide_version=lineage.guide_version,
            source_snapshot_id=lineage.source_snapshot_id,
            source_snapshot_hash=lineage.source_snapshot_sha256,
            submission_artifact_policy_id=submission_artifact_policy_id,
            submission_artifact_policy_hash=lineage.effective_policy_sha256,
            checker_policy_id=checker_policy_id,
            checker_policy_hash=lineage.pre_submit_policy_sha256,
            prepared_generation_id=prepared_artifact.generation_id,
            plan_sha256=selected_reservation.policy_sha256,
            catalogue_manifest_sha256=(selected_reservation.default_behavior_sha256),
            archive_sha256=commitment.sha256,
            archive_byte_count=commitment.byte_count,
            storage_scheme=self._storage_scheme,
        )
