"""ART-owned ready-admission consumption and immutable Submission binding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api import (
    SubmissionAdmissionConsumptionError,
    SubmissionAdmissionConsumptionRequest,
    SubmissionAdmissionConsumptionResult,
)
from app.modules.artifacts.models import (
    ArtifactBinding,
    ArtifactContent,
    PreSubmitEvidenceSet,
    SubmissionBundleAdmission,
)

_LOGICAL_ROLE = "submission_bundle_original"


@dataclass(frozen=True, slots=True)
class SubmissionBindingAuthorityFacts:
    """Exact ART-owned facts consumed before binding and terminal mutation."""

    admission_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    submission_id: UUID
    submission_version: int
    content_id: UUID
    sha256: str
    byte_count: int
    logical_role: str


class SubmissionAdmissionConsumptionAuthorization(Protocol):
    """Authorize one hidden transaction without exposing AUTH handles publicly."""

    async def authorize(self, request: SubmissionAdmissionConsumptionRequest) -> None:
        """Deny before ART reveals or mutates admission state."""

    async def consume(self, facts: SubmissionBindingAuthorityFacts) -> None:
        """Consume exact binding authority in the protected transaction."""


class DenySubmissionAdmissionConsumptionAuthorization:
    """Keep consumption unavailable until the later AUTH activation chunk."""

    async def authorize(self, request: SubmissionAdmissionConsumptionRequest) -> None:
        del request
        raise SubmissionAdmissionConsumptionError(
            "submission_bundle_admission_unavailable"
        )

    async def consume(self, facts: SubmissionBindingAuthorityFacts) -> None:
        del facts
        raise SubmissionAdmissionConsumptionError(
            "submission_bundle_admission_unavailable"
        )


class SubmissionAdmissionConsumptionService:
    """Consume exactly one ready admission in the caller-owned root transaction."""

    def __init__(
        self,
        session: AsyncSession,
        authorization: SubmissionAdmissionConsumptionAuthorization | None = None,
    ) -> None:
        self._session = session
        self._authorization = (
            authorization or DenySubmissionAdmissionConsumptionAuthorization()
        )

    async def consume(
        self,
        request: SubmissionAdmissionConsumptionRequest,
    ) -> SubmissionAdmissionConsumptionResult:
        """Authorize, lock ART lineage, then bind, consume, replay, or stale."""
        if (
            not self._session.in_transaction()
            or self._session.in_nested_transaction()
            or type(request) is not SubmissionAdmissionConsumptionRequest
        ):
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_unavailable"
            )
        await self._authorization.authorize(request)

        admission = await self._session.scalar(
            select(SubmissionBundleAdmission)
            .where(SubmissionBundleAdmission.id == str(request.admission_id))
            .with_for_update()
        )
        if admission is None:
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_unavailable"
            )
        if admission.status == "stale":
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_stale"
            )
        if admission.status == "consumed":
            return await self._consumed_replay(admission, request)

        evidence = await self._session.scalar(
            select(PreSubmitEvidenceSet)
            .where(PreSubmitEvidenceSet.id == admission.pre_submit_evidence_set_id)
            .with_for_update()
        )
        content = await self._session.scalar(
            select(ArtifactContent)
            .where(ArtifactContent.id == admission.artifact_content_id)
            .with_for_update()
        )
        if evidence is None or content is None:
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_unavailable"
            )
        if not self._lineage_matches(admission, evidence, content, request):
            now = await self._session.scalar(select(func.now()))
            admission.status = "stale"
            admission.stale_at = now
            admission.stale_reason = "locked_submission_context_changed"
            await self._session.flush()
            return self._result(admission, request, binding=None, replayed=False)

        existing = await self._session.scalar(
            select(ArtifactBinding)
            .where(
                ArtifactBinding.project_id == admission.project_id,
                ArtifactBinding.resource_type == "submission",
                ArtifactBinding.resource_id == str(request.submission_id),
                ArtifactBinding.logical_role == _LOGICAL_ROLE,
                ArtifactBinding.scope_version == 1,
            )
            .with_for_update()
        )
        if existing is not None:
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_context_changed"
            )

        await self._authorization.consume(
            SubmissionBindingAuthorityFacts(
                admission_id=request.admission_id,
                project_id=UUID(admission.project_id),
                task_id=UUID(admission.task_id),
                assignment_id=UUID(admission.assignment_id),
                submission_id=request.submission_id,
                submission_version=request.submission_version,
                content_id=UUID(admission.artifact_content_id),
                sha256=admission.archive_sha256,
                byte_count=admission.archive_byte_count,
                logical_role=_LOGICAL_ROLE,
            )
        )

        binding = ArtifactBinding(
            id=str(uuid4()),
            content_id=admission.artifact_content_id,
            project_id=admission.project_id,
            resource_type="submission",
            resource_id=str(request.submission_id),
            logical_role=_LOGICAL_ROLE,
            scope_version=1,
            actor_id=admission.actor_profile_id,
            attribution_type="contributor",
            supersedes_binding_id=None,
        )
        now = await self._session.scalar(select(func.now()))
        self._session.add(binding)
        admission.status = "consumed"
        admission.consumed_at = now
        admission.consumed_by_submission_id = str(request.submission_id)
        await self._session.flush()
        return self._result(admission, request, binding=binding, replayed=False)

    async def _consumed_replay(
        self,
        admission: SubmissionBundleAdmission,
        request: SubmissionAdmissionConsumptionRequest,
    ) -> SubmissionAdmissionConsumptionResult:
        if admission.consumed_by_submission_id != str(request.submission_id):
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_already_consumed"
            )
        binding = await self._session.scalar(
            select(ArtifactBinding).where(
                ArtifactBinding.project_id == admission.project_id,
                ArtifactBinding.resource_type == "submission",
                ArtifactBinding.resource_id == str(request.submission_id),
                ArtifactBinding.logical_role == _LOGICAL_ROLE,
                ArtifactBinding.scope_version == 1,
            )
        )
        if binding is None or binding.content_id != admission.artifact_content_id:
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_context_changed"
            )
        return self._result(admission, request, binding=binding, replayed=True)

    @staticmethod
    def _lineage_matches(
        admission: SubmissionBundleAdmission,
        evidence: PreSubmitEvidenceSet,
        content: ArtifactContent,
        request: SubmissionAdmissionConsumptionRequest,
    ) -> bool:
        context = request.task_context
        references = context.locked_project_context
        predecessor = context.predecessor
        return bool(
            admission.status == "ready"
            and admission.actor_profile_id == str(context.contributor_id)
            and admission.project_id == str(references.project_id)
            and admission.task_id == str(context.task_id)
            and admission.assignment_id == str(context.assignment_id)
            and admission.predecessor_submission_id
            == (str(predecessor.submission_id) if predecessor is not None else None)
            and admission.predecessor_submission_version
            == (predecessor.version if predecessor is not None else None)
            and evidence.id == admission.pre_submit_evidence_set_id
            and evidence.project_id == admission.project_id
            and evidence.task_id == admission.task_id
            and evidence.assignment_id == admission.assignment_id
            and evidence.guide_version == references.guide_version
            and evidence.source_snapshot_id == str(references.source_snapshot_id)
            and evidence.source_snapshot_sha256 == references.source_snapshot_hash
            and evidence.effective_policy_id == str(references.effective_policy_id)
            and evidence.locked_artifact_policy_sha256 == references.effective_policy_hash
            and evidence.pre_submit_policy_id == str(references.pre_submit_policy_id)
            and evidence.locked_checker_policy_sha256
            == references.pre_submit_policy_bundle_hash
            and evidence.terminal_status == "passed"
            and evidence.eligible is True
            and content.id == admission.artifact_content_id
            and content.sha256 == admission.archive_sha256
            and content.byte_count == admission.archive_byte_count
        )

    @staticmethod
    def _result(
        admission: SubmissionBundleAdmission,
        request: SubmissionAdmissionConsumptionRequest,
        *,
        binding: ArtifactBinding | None,
        replayed: bool,
    ) -> SubmissionAdmissionConsumptionResult:
        return SubmissionAdmissionConsumptionResult(
            admission_id=UUID(admission.id),
            binding_id=UUID(binding.id) if binding is not None else None,
            content_id=UUID(admission.artifact_content_id),
            submission_id=request.submission_id,
            submission_version=request.submission_version,
            status=admission.status,  # type: ignore[arg-type]
            replayed=replayed,
        )
