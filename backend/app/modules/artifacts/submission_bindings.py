"""ART-owned ready-admission consumption and immutable Submission binding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, cast
from uuid import UUID
from app.core.identifiers import new_record_id

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api import (
    SubmissionAdmissionConsumptionError,
    SubmissionAdmissionConsumptionRequest,
    SubmissionAdmissionConsumptionResult,
    SubmissionAdmissionConsumptionStatus,
    SubmissionAdmissionMaterial,
)
from app.modules.artifacts.api.submission_admission import ConsumedSubmissionAdmissionRequest
from app.modules.artifacts.submission_manifest import SubmissionManifest
from app.modules.checkers.api.external_policy import validate_stored_external_post_policy
from app.modules.artifacts.models import (
    ArtifactBinding,
    ArtifactContent,
    SubmissionBundleAdmission,
    SubmissionBindingReceipt,
)

_LOGICAL_ROLE = "submission_bundle_original"


@dataclass(frozen=True, slots=True)
class SubmissionBindingAuthorityFacts:
    """Exact ART-owned facts consumed before binding and terminal mutation."""

    admission_id: UUID
    evidence_set_id: UUID | None
    selected_pre_submit_run_id: UUID | None
    actor_profile_id: UUID
    identity_link_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None
    predecessor_submission_version: int | None
    checker_remediation_manifest_id: UUID | None = field(default=None, kw_only=True)
    submission_id: UUID
    submission_version: int
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_sha256: str
    effective_policy_id: UUID
    effective_policy_sha256: str
    pre_submit_policy_id: UUID
    pre_submit_policy_sha256: str
    locked_policy_context_hash: str
    semantic_manifest_id: UUID
    semantic_manifest_sha256: str
    content_id: UUID
    sha256: str
    byte_count: int
    logical_role: str


class SubmissionAdmissionConsumptionAuthorization(Protocol):
    """Authorize one hidden transaction without exposing AUTH handles publicly."""

    async def authorize(self, request: SubmissionAdmissionConsumptionRequest) -> None:
        """Deny before ART reveals or mutates admission state."""

    async def consume(self, facts: SubmissionBindingAuthorityFacts) -> UUID:
        """Consume exact binding authority in the protected transaction."""

    async def validate_replay(self, facts: SubmissionBindingAuthorityFacts, decision_id: UUID) -> None:
        """Verify a retained binding allow under fresh authority without consuming."""


class SubmissionAdmissionConsumptionService:
    """Consume exactly one ready admission in the caller-owned root transaction."""

    def __init__(
        self,
        session: AsyncSession,
        authorization: SubmissionAdmissionConsumptionAuthorization,
    ) -> None:
        self._session = session
        self._authorization = authorization

    async def consume(
        self,
        request: SubmissionAdmissionConsumptionRequest,
    ) -> SubmissionAdmissionConsumptionResult:
        """Authorize, lock ART lineage, then bind and consume or mark stale."""
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
        if admission.source_operation_id != (
            str(request.accepted_operation_id) if request.accepted_operation_id else None
        ):
            raise SubmissionAdmissionConsumptionError("submission_bundle_admission_unavailable")
        if admission.source_operation_id is not None:
            await self._session.execute(text("SELECT public.require_source_submission_admission(a) "
                "FROM public.submission_bundle_admissions a WHERE id=:id"), {"id": admission.id})
        if admission.status == "stale":
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_stale"
            )
        if (
            admission.status == "consumed"
            and admission.consumed_by_submission_id != str(request.submission_id)
        ):
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_already_consumed"
            )
        content = await self._session.scalar(
            select(ArtifactContent)
            .where(ArtifactContent.id == admission.artifact_content_id)
            .with_for_update()
        )
        if content is None:
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_unavailable"
            )
        if not self._art_lineage_is_intact(admission, content):
            raise SubmissionAdmissionConsumptionError(
                "submission_bundle_admission_unavailable"
            )
        try:
            SubmissionManifest.from_dict(
                admission.semantic_manifest_body,
                sha256=admission.semantic_manifest_sha256,
            )
        except (TypeError, ValueError) as exc:
            raise SubmissionAdmissionConsumptionError("submission_bundle_admission_unavailable") from exc
        if admission.packet_sha256 != request.packet_sha256:
            raise SubmissionAdmissionConsumptionError("submission_bundle_admission_unavailable")
        if admission.status == "consumed":
            raise SubmissionAdmissionConsumptionError("submission_bundle_admission_already_consumed")
        if not self._task_lineage_matches(admission, request):
            now = await self._session.scalar(select(func.now()))
            admission.status = "stale"
            admission.stale_at = now
            admission.stale_reason = "locked_submission_context_changed"
            await self._session.flush()
            return self._result(admission, request, binding=None, replayed=False)

        await self._lock_binding_scope(admission, request)
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
            now = await self._session.scalar(select(func.now()))
            admission.status = "stale"
            admission.stale_at = now
            admission.stale_reason = "submission_binding_scope_already_consumed"
            await self._session.flush()
            return self._result(
                admission,
                request,
                binding=None,
                replayed=False,
            )

        binding_decision_id = await self._authorization.consume(
            self._authority_facts(admission, request)
        )

        binding = ArtifactBinding(
            id=str(new_record_id()),
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
        admission.consumed_by_submission_version = request.submission_version
        await self._session.flush()
        self._session.add(SubmissionBindingReceipt(
            admission_id=str(request.admission_id), binding_id=binding.id, decision_id=str(binding_decision_id),
        ))
        await self._session.flush()
        return self._result(admission, request, binding=binding, replayed=False,
                            binding_decision_id=binding_decision_id)

    async def _lock_binding_scope(
        self,
        admission: SubmissionBundleAdmission,
        request: SubmissionAdmissionConsumptionRequest,
    ) -> None:
        key = ":".join(
            (
                admission.project_id,
                "submission",
                str(request.submission_id),
                _LOGICAL_ROLE,
                "1",
            )
        )
        await self._session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": key},
        )

    async def read_consumed(
        self, request: ConsumedSubmissionAdmissionRequest,
    ) -> SubmissionAdmissionConsumptionResult:
        """Verify retained ownership first, then freshly authorize its original receipt."""
        if (not self._session.in_transaction() or self._session.in_nested_transaction()
                or type(request) is not ConsumedSubmissionAdmissionRequest):
            raise SubmissionAdmissionConsumptionError("submission_bundle_admission_unavailable")
        await self._authorization.authorize(request)
        admission = await self._session.scalar(select(SubmissionBundleAdmission).where(
            SubmissionBundleAdmission.id == str(request.admission_id),
            SubmissionBundleAdmission.project_id == str(request.project_id),
            SubmissionBundleAdmission.task_id == str(request.task_id),
            SubmissionBundleAdmission.assignment_id == str(request.assignment_id),
            SubmissionBundleAdmission.actor_profile_id == str(request.contributor_id),
            SubmissionBundleAdmission.consumed_by_submission_id == str(request.submission_id),
            SubmissionBundleAdmission.consumed_by_submission_version == request.submission_version,
            SubmissionBundleAdmission.status == "consumed",
        ).with_for_update().execution_options(populate_existing=True))
        if admission is None:
            raise SubmissionAdmissionConsumptionError("submission_bundle_admission_unavailable")
        receipt = await self._session.get(SubmissionBindingReceipt, str(request.admission_id),
                                          populate_existing=True)
        if receipt is None:
            raise SubmissionAdmissionConsumptionError("submission_bundle_admission_unavailable")
        content = await self._session.scalar(select(ArtifactContent).where(
            ArtifactContent.id == admission.artifact_content_id,
        ).with_for_update().execution_options(populate_existing=True))
        binding = await self._session.scalar(select(ArtifactBinding).where(
            ArtifactBinding.project_id == str(request.project_id),
            ArtifactBinding.resource_type == "submission",
            ArtifactBinding.resource_id == str(request.submission_id),
            ArtifactBinding.logical_role == _LOGICAL_ROLE,
            ArtifactBinding.scope_version == 1,
        ).execution_options(populate_existing=True))
        if (
            content is None or binding is None
            or binding.content_id != admission.artifact_content_id
            or binding.id != receipt.binding_id
            or not self._art_lineage_is_intact(admission, content)
            or admission.packet_sha256 != request.packet_sha256
        ):
            raise SubmissionAdmissionConsumptionError("submission_bundle_admission_context_changed")
        await self._authorization.validate_replay(
            self._authority_facts(admission, request), UUID(receipt.decision_id),
        )
        return self._result(admission, request, binding=binding, replayed=True,
                            binding_decision_id=UUID(receipt.decision_id))

    @staticmethod
    def _art_lineage_is_intact(
        admission: SubmissionBundleAdmission, content: ArtifactContent,
    ) -> bool:
        try:
            policy = validate_stored_external_post_policy(admission.selected_post_submit_policy_body)
        except (TypeError, ValueError):
            return False
        return bool(
            admission.pre_submit_evidence_set_id is None
            and admission.selected_pre_submit_run_id is not None
            and policy.policy_sha256 == admission.selected_post_submit_policy_sha256
            and content.id == admission.artifact_content_id
            and content.sha256 == admission.archive_sha256
            and content.byte_count == admission.archive_byte_count
        )

    @staticmethod
    def _task_lineage_matches(
        admission: SubmissionBundleAdmission,
        request: SubmissionAdmissionConsumptionRequest,
    ) -> bool:
        context = request.task_context
        references = context.locked_project_context
        predecessor = context.predecessor
        revision = context.revision_context
        return bool(
            admission.actor_profile_id == str(context.contributor_id)
            and admission.project_id == str(references.project_id)
            and admission.task_id == str(context.task_id)
            and admission.assignment_id == str(context.assignment_id)
            and admission.predecessor_submission_id
            == (str(predecessor.submission_id) if predecessor is not None else None)
            and admission.predecessor_submission_version
            == (predecessor.version if predecessor is not None else None)
            and admission.checker_remediation_manifest_id
            == context.checker_remediation_manifest_id
            and (admission.source_operation_id is not None or predecessor is None or (
                revision is not None and revision.disposition == "ready"
                and revision.source_submission_id == predecessor.submission_id
                and revision.source_routing_manifest_id == context.checker_remediation_manifest_id
            ))
            and (admission.source_operation_id is not None or (
                admission.revision_preparation_id == (revision.preparation_id if revision is not None else None)
                and admission.revision_preparation_sha256 == (revision.preparation_sha256 if revision is not None else None)
            ))
            and admission.guide_version == references.guide_version
            and admission.source_snapshot_id == str(references.source_snapshot_id)
            and admission.source_snapshot_sha256 == references.source_snapshot_hash
            and admission.effective_policy_id == str(references.effective_policy_id)
            and admission.effective_policy_sha256 == references.effective_policy_hash
            and admission.pre_submit_policy_id == str(references.pre_submit_policy_id)
            and admission.pre_submit_policy_sha256
            == references.pre_submit_policy_bundle_hash
        )

    @staticmethod
    def _authority_facts(
        admission: SubmissionBundleAdmission,
        request: SubmissionAdmissionConsumptionRequest | ConsumedSubmissionAdmissionRequest,
    ) -> SubmissionBindingAuthorityFacts:
        return SubmissionBindingAuthorityFacts(
            admission_id=request.admission_id,
            evidence_set_id=None,
            selected_pre_submit_run_id=UUID(admission.selected_pre_submit_run_id),
            actor_profile_id=UUID(admission.actor_profile_id),
            identity_link_id=UUID(admission.identity_link_id),
            project_id=UUID(admission.project_id),
            task_id=UUID(admission.task_id),
            assignment_id=UUID(admission.assignment_id),
            predecessor_submission_id=(
                UUID(admission.predecessor_submission_id)
                if admission.predecessor_submission_id is not None
                else None
            ),
            predecessor_submission_version=admission.predecessor_submission_version,
            checker_remediation_manifest_id=admission.checker_remediation_manifest_id,
            submission_id=request.submission_id,
            submission_version=request.submission_version,
            guide_id=UUID(admission.guide_id),
            guide_version=admission.guide_version,
            source_snapshot_id=UUID(admission.source_snapshot_id),
            source_snapshot_sha256=admission.source_snapshot_sha256,
            effective_policy_id=UUID(admission.effective_policy_id),
            effective_policy_sha256=admission.effective_policy_sha256,
            pre_submit_policy_id=UUID(admission.pre_submit_policy_id),
            pre_submit_policy_sha256=admission.pre_submit_policy_sha256,
            locked_policy_context_hash=admission.locked_policy_context_hash,
            semantic_manifest_id=UUID(admission.semantic_manifest_id),
            semantic_manifest_sha256=admission.semantic_manifest_sha256,
            content_id=UUID(admission.artifact_content_id),
            sha256=admission.archive_sha256,
            byte_count=admission.archive_byte_count,
            logical_role=_LOGICAL_ROLE,
        )

    @staticmethod
    def _result(
        admission: SubmissionBundleAdmission,
        request: SubmissionAdmissionConsumptionRequest | ConsumedSubmissionAdmissionRequest,
        *,
        binding: ArtifactBinding | None,
        replayed: bool,
        binding_decision_id: UUID | None = None,
    ) -> SubmissionAdmissionConsumptionResult:
        material = None
        if admission.status == "consumed":
            manifest = SubmissionManifest.from_dict(
                admission.semantic_manifest_body,
                sha256=admission.semantic_manifest_sha256,
            )
            material = SubmissionAdmissionMaterial(
                archive_sha256=admission.archive_sha256,
                archive_byte_count=admission.archive_byte_count,
                semantic_manifest_sha256=manifest.sha256,
                files=manifest.file_facts(),
            )
        return SubmissionAdmissionConsumptionResult(
            admission_id=UUID(admission.id),
            binding_id=UUID(binding.id) if binding is not None else None,
            content_id=UUID(admission.artifact_content_id),
            submission_id=request.submission_id,
            submission_version=request.submission_version,
            status=cast("SubmissionAdmissionConsumptionStatus", admission.status),
            replayed=replayed,
            material=material,
            binding_decision_id=binding_decision_id,
            selected_post_submit_policy_sha256=(
                admission.selected_post_submit_policy_sha256
            ),
            selected_post_submit_policy_body=(
                admission.selected_post_submit_policy_body
            ),
        )
