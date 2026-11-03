"""Validate approved lifecycle custody without rewriting a draft projection digest."""

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.guide_proposals import (
    GuideProposalApprovalReceipt,
    GuideProposalTarget,
)
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    PreSubmitCheckerPolicy,
    SubmissionPolicyMutationIdempotencyRecord,
    SubmissionArtifactPolicy,
)
from app.modules.checkers.api.external_policy import (
    validate_stored_external_checker_policies,
)

from .custody_payloads import policy_digest
from .models import ProjectGuideProposalApproval
from .retained_evidence import retained_target


def _stored_approval_target(view, operation):
    """Read an old approval commitment solely for existing custody proof."""
    if view.compilation.result_schema_version is not None:
        return GuideProposalTarget.model_validate(operation.target_json)
    return retained_target(operation.target_json)


@dataclass(frozen=True)
class ApprovalCustody:
    """All relations needed to prove a downstream lifecycle transition."""

    operation: ProjectGuideProposalApproval
    reservation: SubmissionPolicyMutationIdempotencyRecord
    effective: EffectiveProjectSubmissionArtifactPolicy
    pre: PreSubmitCheckerPolicy
    successor: ProjectGuideProposalApproval | None = None


async def load_approval_custody(session, policy_id: str | None) -> ApprovalCustody | None:
    """Load the single immutable approval and all independently required outputs."""
    if policy_id is None:
        return None
    operation = await session.scalar(
        select(ProjectGuideProposalApproval)
        .where(
            ProjectGuideProposalApproval.artifact_policy_id == policy_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if operation is None:
        return None
    reservation = await session.scalar(
        select(SubmissionPolicyMutationIdempotencyRecord)
        .where(
            SubmissionPolicyMutationIdempotencyRecord.operation_id == operation.operation_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    effective = await session.get(
        EffectiveProjectSubmissionArtifactPolicy,
        operation.effective_policy_id,
        populate_existing=True,
        with_for_update=True,
    )
    pre = await session.get(
        PreSubmitCheckerPolicy,
        operation.pre_submit_policy_id,
        populate_existing=True,
        with_for_update=True,
    )
    if reservation is None or effective is None or pre is None:
        raise ValueError("approval custody is incomplete")
    successor = await session.scalar(
        select(ProjectGuideProposalApproval)
        .where(
            ProjectGuideProposalApproval.prior_approval_operation_id == operation.operation_id,
        )
        .execution_options(populate_existing=True)
    )
    if successor is not None:
        next_policy = await session.get(
            SubmissionArtifactPolicy, successor.artifact_policy_id, populate_existing=True
        )
        next_effective = await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            successor.effective_policy_id,
            populate_existing=True,
        )
        next_pre = await session.get(
            PreSubmitCheckerPolicy, successor.pre_submit_policy_id, populate_existing=True
        )
        if (
            next_policy is None
            or next_effective is None
            or next_pre is None
            or successor.project_id != operation.project_id
            or successor.guide_id != operation.guide_id
            or next_policy.supersedes_policy_id != operation.artifact_policy_id
            or next_effective.supersedes_effective_policy_id != effective.id
            or next_pre.supersedes_pre_submit_checker_policy_id != pre.id
        ):
            raise ValueError("approval successor custody mismatch")
    return ApprovalCustody(operation, reservation, effective, pre, successor)


def _approval_projection_matches(view, custody, target, receipt, policy, external_policies) -> bool:
    """Compare every immutable target, receipt, reservation and policy fact."""
    operation, reservation, effective, pre = (
        custody.operation,
        custody.reservation,
        custody.effective,
        custody.pre,
    )
    target_hashes = (
        vars(target.component_hashes)
        if view.compilation.result_schema_version is None
        else target.component_hashes.model_dump()
    )
    if (
        target.digest != operation.target_digest
        or target.compilation_id != view.compilation.id
        or target.result_hash != view.compilation.result_hash
        or (
            view.compilation.result_schema_version is not None
            and target.result_schema_version != view.compilation.result_schema_version
        )
        or target_hashes != view.compilation.component_hashes
        or target.setup_run_id != UUID(view.setup.id)
        or target.setup_generation != view.setup.setup_generation
        or target.artifact_policy_id != UUID(policy.id)
        or target.artifact_policy_hash != policy.policy_hash
        or target.finalization_id != operation.finalization_id
        or target.project_id != UUID(operation.project_id)
        or target.guide_id != UUID(operation.guide_id)
        or reservation.status != "committed"
        or reservation.operation_id != operation.operation_id
        or reservation.action_id != "project.submission_artifact_policy.approve"
        or reservation.request_digest != operation.request_digest
        or reservation.resource_context_digest != operation.resource_context_digest
        or reservation.actor_profile_id != operation.actor_profile_id
        or reservation.identity_link_id != operation.identity_link_id
        or reservation.committed_policy_id != policy.id
        or reservation.committed_effective_policy_id != effective.id
        or reservation.committed_pre_submit_policy_id != pre.id
        or reservation.response_json != operation.receipt_json
        or receipt.operation_id != operation.operation_id
        or receipt.acknowledged_warning_hashes
        != tuple(
            sorted(
                canonical_json_hash(finding)
                for finding in view.compilation.canonical_result["findings"]
                if finding["severity"] == "warning"
            )
        )
        or receipt.target_digest != target.digest
        or str(receipt.artifact_policy_id) != policy.id
        or str(receipt.effective_policy_id) != effective.id
        or str(receipt.pre_submit_policy_id) != pre.id
        or canonical_json_hash(operation.receipt_json) != operation.output_digest
        or effective.effective_policy_hash != receipt.effective_policy_hash
        or canonical_json_hash(effective.effective_policy) != receipt.effective_policy_hash
        or pre.compiled_bundle_hash != receipt.pre_submit_bundle_hash
        or external_policies.pre_submit.policy_sha256 != receipt.pre_submit_bundle_hash
        or effective.submission_artifact_policy_id != policy.id
        or effective.submission_artifact_policy_hash != policy.policy_hash
        or pre.effective_policy_id != effective.id
        or pre.effective_policy_hash != effective.effective_policy_hash
        or operation.effective_pre_submit_plan_hash != receipt.effective_pre_submit_plan_hash
        or external_policies.policies_sha256 != receipt.effective_pre_submit_plan_hash
    ):
        return False
    return True


def approved_projection_digest(view) -> str:
    """Return the original digest only after proving the exact approved transition."""
    custody = view.approval_custody
    policy = view.policy
    if custody is None or policy is None:
        raise ValueError("approval custody is unavailable")
    operation, effective, pre = (
        custody.operation,
        custody.effective,
        custody.pre,
    )
    target = _stored_approval_target(view, operation)
    receipt = GuideProposalApprovalReceipt.model_validate(operation.receipt_json)
    external_policies = validate_stored_external_checker_policies(
        operation.effective_pre_submit_plan
    )
    if not _approval_projection_matches(view, custody, target, receipt, policy, external_policies):
        raise ValueError("approved proposal custody mismatch")
    lifecycle = (policy.lifecycle_status, effective.lifecycle_status, pre.lifecycle_status)
    if custody.successor is None:
        if lifecycle != ("approved", "approved", "compiled") or any(
            row.superseded_at is not None for row in (policy, effective, pre)
        ):
            raise ValueError("approved proposal lifecycle mismatch")
    elif (
        lifecycle != ("superseded", "superseded", "superseded")
        or policy.superseded_at is None
        or effective.superseded_at != policy.superseded_at
        or pre.superseded_at != policy.superseded_at
    ):
        raise ValueError("superseded proposal lifecycle mismatch")
    approved = SimpleNamespace(
        **{column.key: getattr(policy, column.key) for column in policy.__table__.columns}
    )
    approved.lifecycle_status = "approved"
    if policy_digest(approved) != operation.approved_policy_output_digest:
        raise ValueError("approved proposal content changed")
    _require_plan_and_provenance(view, custody, target)
    # The operation above proves the one accepted lifecycle change. Every other
    # projected field is still compared against the original immutable digest.
    approved.lifecycle_status = "draft"
    digest = policy_digest(approved)
    if digest != target.artifact_projection_output_digest:
        raise ValueError("original proposal content changed after approval")
    return digest


def _require_plan_and_provenance(view, custody, target) -> None:
    operation, effective, pre, policy = (
        custody.operation,
        custody.effective,
        custody.pre,
        view.policy,
    )
    policies = validate_stored_external_checker_policies(operation.effective_pre_submit_plan)
    if policies.pre_submit.model_dump(mode="json") != pre.compiled_bundle:
        raise ValueError("approved external checker policy mismatch")
    for name in (
        "pre_catalogue_id",
        "pre_catalogue_version",
        "pre_catalogue_schema_version",
        "pre_catalogue_manifest_hash",
        "post_catalogue_id",
        "post_catalogue_version",
        "post_catalogue_schema_version",
        "post_catalogue_manifest_hash",
    ):
        if view.compilation.result_schema_version is None and (
            getattr(target, name) != getattr(view.attempt, name)
        ):
            raise ValueError("approved proposal catalogue mismatch")
    for row, prefix in ((policy, "approval"), (effective, "creation"), (pre, "creation")):
        actor_prefix = "approved" if row is policy else "created"
        if (
            row.project_id != operation.project_id
            or row.guide_id != operation.guide_id
            or row.source_snapshot_id != str(target.source_snapshot_id)
            or row.source_snapshot_hash != target.source_snapshot_hash
            or getattr(row, f"{actor_prefix}_by_actor_profile_id") != operation.actor_profile_id
            or getattr(row, f"{actor_prefix}_via_identity_link_id") != operation.identity_link_id
            or getattr(row, f"{actor_prefix}_by_admin_role_grant_id")
            != operation.admin_role_grant_id
            or getattr(row, f"{prefix}_action_id") != "project.submission_artifact_policy.approve"
            or getattr(row, f"{prefix}_decision_event_id")
            != operation.authorization_decision_event_id
            or getattr(row, f"{prefix}_scope_project_id") != operation.project_id
        ):
            raise ValueError("approved proposal provenance mismatch")


async def lock_policy_approval(session, guide, snapshot, policy, effective, pre):
    """Reuse finalization proof for the current, already locked approval chain."""
    from .models import (
        ProjectGuideCompilation,
        ProjectGuideCompilationAttempt,
        ProjectGuideSetupFinalization,
        ProjectGuideCompilationRequestOperation,
        ProjectGuideComponentProjectionOperation,
    )
    from .finalization_payloads import (
        LockedFinalization,
        require_lineage,
        compose_facts,
        require_replay,
    )
    from app.modules.projects.models import ProjectSetupRun, GuideSufficiencyReport
    from app.modules.projects.api.guide_compilation import ProjectGuideSetupFinalizationCommand

    custody = await load_approval_custody(session, policy.id)
    if (
        custody is None
        or custody.effective is not effective
        or custody.pre is not pre
        or custody.successor is not None
        or policy.lifecycle_status != "approved"
    ):
        raise ValueError("current guide approval custody missing")
    operation = custody.operation
    compilation = await session.get(ProjectGuideCompilation, operation.compilation_id)
    finalization = await session.get(ProjectGuideSetupFinalization, operation.finalization_id)
    if compilation is None or finalization is None:
        raise ValueError("current guide finalization custody missing")
    setup = await session.get(ProjectSetupRun, compilation.setup_run_id)
    attempt = await session.get(ProjectGuideCompilationAttempt, compilation.attempt_id)
    request = await session.scalar(
        select(ProjectGuideCompilationRequestOperation).where(
            ProjectGuideCompilationRequestOperation.attempt_id == compilation.attempt_id,
        )
    )
    report = await session.get(GuideSufficiencyReport, finalization.sufficiency_report_id)
    operations = tuple(
        await session.scalars(
            select(ProjectGuideComponentProjectionOperation).where(
                ProjectGuideComponentProjectionOperation.compilation_id == compilation.id,
            )
        )
    )
    view = LockedFinalization(
        attempt,
        request,
        guide,
        snapshot,
        setup,
        compilation,
        False,
        operations,
        report,
        policy,
        custody,
    )
    target = _stored_approval_target(view, operation)
    command = ProjectGuideSetupFinalizationCommand(
        project_id=target.project_id,
        guide_id=target.guide_id,
        setup_run_id=target.setup_run_id,
        setup_generation=target.setup_generation,
        compilation_id=target.compilation_id,
    )
    require_lineage(
        view, command, require_current=False, allowed_guide_statuses=frozenset({"draft", "active"})
    )
    require_replay(
        view,
        finalization,
        compose_facts(
            view,
            finalization.source_state_digest,
            finalization_id=finalization.id,
            operation_id=finalization.operation_id,
            correlation_id=finalization.correlation_id,
        ),
    )
    if (
        target.finalization_facts_digest != finalization.facts_digest
        or target.artifact_projection_output_digest != finalization.artifact_policy_output_digest
        or target.artifact_projection_operation_id != finalization.artifact_policy_operation_id
    ):
        raise ValueError("current guide finalized approval mismatch")
    return custody
