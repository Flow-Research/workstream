"""ART-owned exact admitted-material selection, without provider I/O or locks."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.artifacts import ArtifactStore, artifact_provider_object_ref
from app.modules.checkers.api.materialization import PostSubmissionMaterializationUnavailable
from app.modules.artifacts.models import (
    ArtifactBinding, ArtifactContent, ArtifactReplica, ArtifactStorageNamespace,
    ArtifactVerificationJob, ArtifactVerificationReceipt,
    SubmissionBundleAdmission,
)
from app.modules.artifacts.service import (
    ArtifactStorageNamespaceSpec, validate_artifact_replica_execution_namespace,
)
from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService
from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionRequest,
)
from app.modules.tasks.api.submitted_bundle import (
    SubmittedBundleFacts, SubmittedBundlePort, SubmittedBundleRequest,
)
from app.modules.tasks.api.evaluation_revision import (
    TaskEvaluationRevisionContext, TaskEvaluationRevisionRequest,
)
from app.modules.checkers.api.external_policy import validate_stored_external_post_policy


@dataclass(frozen=True, slots=True)
class PostSubmissionMaterialSelection:
    """Private detached snapshot; storage coordinates never leave ART."""

    submission: SubmittedBundleFacts
    evidence_id: UUID
    replica_id: UUID
    verification_receipt_id: UUID
    verification_job_id: UUID
    verification_generation: int
    namespace_fingerprint: str
    adapter: str
    provider_profile: str
    provider_object_ref: str
    sha256: str
    byte_count: int
    media_type: str
    semantic_manifest_id: UUID
    semantic_manifest_sha256: str
    revision_preparation_id: UUID | None
    revision_preparation_sha256: str | None


async def read_post_submission_facts(
    tasks: SubmittedBundlePort, request: PostSubmissionExecutionRequest,
) -> SubmittedBundleFacts:
    """Read and validate immutable TASK facts before acquiring CHECKERS custody."""
    facts = await tasks.read(SubmittedBundleRequest(
        project_id=request.project_id, task_id=request.task_id, submission_id=request.submission_id,
    ))
    context = facts.context
    context_matches = (
        context.guide_version == request.expected_context.guide_version
        and context.source_id == request.expected_context.source_id
        and context.source_hash == request.expected_context.source_hash
        and context.effective_policy_id
        == request.expected_context.effective_policy_id
        and context.effective_policy_hash
        == request.expected_context.effective_policy_hash
        and context.pre_policy_id == request.expected_context.pre_policy_id
        and context.pre_policy_hash == request.expected_context.pre_policy_hash
        and context.post_policy_id
        == request.expected_context.post_policy_id
        and context.post_policy_version
        == request.expected_context.post_policy_version
        and context.post_policy_hash
        == request.expected_context.post_policy_hash
        and context.selected_post_policy_hash
        == request.expected_context.post_policy_hash
        and context.selected_post_policy_body == request.policy.model_dump(mode="json")
        and context.review_policy_id == request.expected_context.review_policy_id
        and context.review_generation == request.expected_context.review_generation
        and context.review_hash == request.expected_context.review_hash
        and context.revision_policy_id == request.expected_context.revision_policy_id
        and context.revision_generation
        == request.expected_context.revision_generation
        and context.revision_hash == request.expected_context.revision_hash
    )
    if (
        facts.status != "submitted"
        or (facts.project_id, facts.task_id, facts.assignment_id, facts.submission_id,
            facts.submission_version, facts.binding_id, facts.content_id) != (
                request.project_id, request.task_id, request.assignment_id, request.submission_id,
                request.submission_version, request.binding_id, request.content_id)
        or not context_matches
    ):
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    return facts


async def read_consumed_revision_selector(
    session: AsyncSession, facts: SubmittedBundleFacts,
) -> TaskEvaluationRevisionRequest:
    """Project only ART's consumed preparation pointer, without locks or byte authority."""
    admission = await session.scalar(select(SubmissionBundleAdmission).where(
        SubmissionBundleAdmission.id == str(facts.admission_id),
        SubmissionBundleAdmission.project_id == str(facts.project_id),
        SubmissionBundleAdmission.task_id == str(facts.task_id),
        SubmissionBundleAdmission.assignment_id == str(facts.assignment_id),
        SubmissionBundleAdmission.actor_profile_id == str(facts.contributor_id),
        SubmissionBundleAdmission.status == "consumed",
        SubmissionBundleAdmission.consumed_by_submission_id == str(facts.submission_id),
        SubmissionBundleAdmission.consumed_by_submission_version == facts.submission_version,
        SubmissionBundleAdmission.artifact_content_id == str(facts.content_id),
    ).execution_options(populate_existing=True))
    if admission is None:
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    return TaskEvaluationRevisionRequest(
        project_id=facts.project_id, task_id=facts.task_id, assignment_id=facts.assignment_id,
        submission_id=facts.submission_id, submission_version=facts.submission_version,
        admission_id=facts.admission_id, preparation_id=admission.revision_preparation_id,
        preparation_sha256=admission.revision_preparation_sha256,
    )


async def select_post_submission_material(
    session: AsyncSession, *, tasks: SubmittedBundlePort,
    request: PostSubmissionExecutionRequest, namespace: ArtifactStorageNamespaceSpec,
    store: ArtifactStore,
) -> PostSubmissionMaterialSelection:
    """Resolve one current input through the same admitted-material selector as prior work."""
    facts = await read_post_submission_facts(tasks, request)
    selected = await select_admitted_post_material(session, facts=facts, namespace=namespace, store=store)
    if (selected.sha256, selected.byte_count) != (request.content_sha256, request.byte_count):
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    return selected


async def select_predecessor_material(
    session: AsyncSession, *, facts: SubmittedBundleFacts, context: TaskEvaluationRevisionContext,
    namespace: ArtifactStorageNamespaceSpec, store: ArtifactStore,
) -> PostSubmissionMaterialSelection:
    """Resolve only the predecessor whose same-assignment revision TASK already proved."""
    context = TaskEvaluationRevisionContext.model_validate(context)
    reference = context.predecessor
    if context.kind != "checker_remediation" or reference is None:
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    if facts.status != "submitted" or any(
        getattr(facts, name) != getattr(reference, name) for name in type(reference).model_fields
    ):
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    return await select_admitted_post_material(session, facts=facts, namespace=namespace, store=store)


async def select_admitted_post_material(
    session: AsyncSession, *, facts: SubmittedBundleFacts,
    namespace: ArtifactStorageNamespaceSpec, store: ArtifactStore,
) -> PostSubmissionMaterialSelection:
    """Validate complete consumed ART custody against the Submission's own locked policy."""
    policy = validate_stored_external_post_policy(facts.context.selected_post_policy_body)
    if facts.status != "submitted" or policy.policy_sha256 != facts.context.selected_post_policy_hash or (
        policy.policy_sha256 != facts.context.post_policy_hash
    ):
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    row = (await session.execute(
        select(SubmissionBundleAdmission, ArtifactBinding,
               ArtifactContent, ArtifactReplica, ArtifactVerificationReceipt,
               ArtifactVerificationJob, ArtifactStorageNamespace)
        .select_from(SubmissionBundleAdmission)
        .join(ArtifactBinding, ArtifactBinding.id == str(facts.binding_id))
        .join(ArtifactContent, ArtifactContent.id == SubmissionBundleAdmission.artifact_content_id)
        .join(ArtifactReplica, ArtifactReplica.id == SubmissionBundleAdmission.verified_replica_id)
        .join(ArtifactVerificationReceipt, ArtifactVerificationReceipt.id == SubmissionBundleAdmission.verification_receipt_id)
        .join(ArtifactVerificationJob, ArtifactVerificationJob.id == ArtifactVerificationReceipt.verification_job_id)
        .join(ArtifactStorageNamespace, ArtifactStorageNamespace.id == ArtifactReplica.storage_namespace_id)
        .where(SubmissionBundleAdmission.id == str(facts.admission_id),
               SubmissionBundleAdmission.project_id == str(facts.project_id),
               SubmissionBundleAdmission.task_id == str(facts.task_id))
        .execution_options(populate_existing=True)
    )).one_or_none()
    if row is None:
        raise PostSubmissionMaterializationUnavailable("post_submit_material_unavailable")
    admission, binding, content, replica, receipt, job, persisted = row
    selected_lineage = (
        admission.selected_pre_submit_run_id is not None
        and admission.pre_submit_evidence_set_id is None
        and admission.selected_post_submit_policy_sha256
        == policy.policy_sha256
        and admission.selected_post_submit_policy_body
        == policy.model_dump(mode="json")
    )
    if not (
        SubmissionAdmissionConsumptionService._art_lineage_is_intact(admission, content)
        and admission.status == "consumed"
        and admission.consumed_by_submission_id == str(facts.submission_id)
        and admission.consumed_by_submission_version == facts.submission_version
        and admission.assignment_id == str(facts.assignment_id)
        and admission.actor_profile_id == str(facts.contributor_id)
        and admission.predecessor_submission_id == (str(facts.predecessor_id) if facts.predecessor_id else None)
        and admission.predecessor_submission_version == facts.predecessor_version
        and binding.project_id == str(facts.project_id)
        and binding.resource_type == "submission"
        and binding.resource_id == str(facts.submission_id)
        and binding.logical_role == "submission_bundle_original"
        and binding.scope_version == 1
        and binding.content_id == content.id == str(facts.content_id)
        and selected_lineage
        and content.media_type == "application/zip"
        and replica.content_id == content.id
        and (replica.verification_state, replica.availability_state, replica.integrity_state)
        == ("verified", "available", "valid")
        and receipt.outcome == "verified"
        and receipt.observed_sha256 == content.sha256
        and receipt.observed_byte_count == content.byte_count
        and job.replica_id == replica.id
        and job.originating_put_attempt_id == admission.put_attempt_id
    ):
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    validate_artifact_replica_execution_namespace(
        replica=replica, persisted=persisted, namespace=namespace, store=store,
    )
    commitment = ArtifactCommitment(content.sha256, content.byte_count, content.media_type)
    if replica.provider_object_ref != artifact_provider_object_ref(commitment):
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    return PostSubmissionMaterialSelection(
        submission=facts,
        evidence_id=UUID(admission.selected_pre_submit_run_id),
        replica_id=UUID(replica.id),
        verification_receipt_id=UUID(receipt.id), verification_job_id=UUID(job.id),
        verification_generation=receipt.execution_generation,
        namespace_fingerprint=persisted.namespace_fingerprint, adapter=replica.adapter,
        provider_profile=replica.provider_profile, provider_object_ref=replica.provider_object_ref,
        sha256=content.sha256, byte_count=content.byte_count, media_type=content.media_type,
        semantic_manifest_id=UUID(admission.semantic_manifest_id),
        semantic_manifest_sha256=admission.semantic_manifest_sha256,
        revision_preparation_id=admission.revision_preparation_id,
        revision_preparation_sha256=admission.revision_preparation_sha256,
    )
