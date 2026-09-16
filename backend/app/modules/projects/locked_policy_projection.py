"""Detach complete validated PROJECTS custody into the sole immutable port result."""

from uuid import UUID

from app.modules.projects.api.locked_policy import (
    CanonicalJsonObject,
    ProjectLockedPolicyContextFacts,
    ProjectDisplayFacts,
    GuideDisplayFacts,
)
from app.modules.projects.guide_compilation.approval_custody import approved_projection_digest
from app.modules.projects.api.policy_lineage import (
    ReviewPolicySemantics,
    RevisionPolicySemantics,
    require_complete_policy,
)


def _policy_body(kind, row, selection, guide):
    if row is None or (
        row.project_id != guide.project_id
        or row.guide_version != guide.version
        or (row.id, row.policy_generation, row.policy_hash)
        != (str(selection.policy_id), selection.generation, selection.policy_hash)
    ):
        raise ValueError("selected policy unavailable")
    model = ReviewPolicySemantics if kind == "review" else RevisionPolicySemantics
    values = {name: getattr(row, name) for name in model.model_fields}
    options = {"review_semantics_format": row.semantics_format} if kind == "review" else {}
    require_complete_policy(
        kind=kind,
        status=row.semantics_status,
        policy_hash=row.policy_hash,
        semantic_values=values,
        **options,
    )
    return CanonicalJsonObject.from_mapping(model.model_validate(values).model_dump(mode="json"))


def complete_context(locked, post_policy, post_custody, receipt, review, revision, project):
    """Require exact activation and each approved output, without rerunning eligibility."""
    view = locked.view
    command = receipt.command
    if (
        command.target != post_custody.target
        or command.target.proposal != locked.target
        or post_custody.approval is None
        or post_custody.approval.operation_id != command.post_approval_operation_id
        or post_custody.approval.output_digest != command.post_approval_output_digest
    ):
        raise ValueError("activation post-policy custody mismatch")
    approved_projection_digest(view)
    approval = view.approval_custody
    snapshot = CanonicalJsonObject.from_mapping(view.snapshot.manifest_json)
    if snapshot.sha256 != locked.target.source_snapshot_hash:
        raise ValueError("source manifest hash mismatch")
    return ProjectLockedPolicyContextFacts(
        project_id=locked.target.project_id,
        guide_id=locked.target.guide_id,
        guide_version=view.guide.version,
        guide_status=view.guide.status,
        source_snapshot_id=UUID(view.snapshot.id),
        source_snapshot_hash=view.snapshot.bundle_hash,
        effective_policy_id=UUID(approval.effective.id),
        effective_policy_hash=approval.effective.effective_policy_hash,
        effective_policy_status=approval.effective.lifecycle_status,
        effective_policy=CanonicalJsonObject.from_mapping(approval.effective.effective_policy),
        pre_submit_policy_id=UUID(approval.pre.id),
        pre_submit_policy_bundle_hash=approval.pre.compiled_bundle_hash,
        pre_submit_policy_status=approval.pre.lifecycle_status,
        pre_submit_compiler_version=approval.pre.compiler_version,
        compiled_pre_submit_bundle=CanonicalJsonObject.from_mapping(approval.pre.compiled_bundle),
        activation_receipt=receipt,
        artifact_policy=CanonicalJsonObject.from_mapping(view.policy.policy_body),
        compiled_post_submit_policy=CanonicalJsonObject.from_mapping(post_policy.policy_body),
        review_policy=_policy_body("review", review, command.review, view.guide),
        review_semantics_format=review.semantics_format,
        revision_policy=_policy_body("revision", revision, command.revision, view.guide),
        project=ProjectDisplayFacts(
            id=UUID(project.id), name=project.name, slug=project.slug,
            description=project.description,
        ),
        guide=GuideDisplayFacts(
            id=UUID(view.guide.id), project_id=UUID(view.guide.project_id),
            version=view.guide.version, change_summary=view.guide.change_summary,
            effective_at=view.guide.effective_at,
        ),
    )
