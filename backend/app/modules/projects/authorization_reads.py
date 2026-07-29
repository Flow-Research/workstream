"""Canonical composition for project setup diagnostic authorization reads."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    PROJECT_DIAGNOSTIC_TARGET_KIND_BY_ACTION,
    PROJECT_POLICY_READ_TARGET_KIND_BY_ACTION,
    ProjectActiveGuideReadResourceContext,
    ProjectDiagnosticReadResourceContext,
    ProjectPolicyReadResourceContext,
    authorization_resource_selector_id,
)
from app.modules.projects.models import (
    GuideSufficiencyReport,
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    ProjectGuide,
    ProjectSetupRun,
    RevisionPolicy,
    ReviewPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError
from app.modules.projects.service import (
    GuideActivationBlocked,
    ProjectService,
    ProjectServiceError,
)

DiagnosticRecord: TypeAlias = ProjectSetupRun | GuideSufficiencyReport | SubmissionArtifactPolicy
DiagnosticResult: TypeAlias = (
    DiagnosticRecord
    | Sequence[DiagnosticRecord]
    | tuple[ProjectSetupRun, PostSubmitCheckerPolicy | None]
)


@dataclass(frozen=True)
class ActiveGuideReadBundle:
    """Locked non-compensation active-guide rows approved for projection."""

    guide: ProjectGuide
    source_snapshot: GuideSourceSnapshot
    source_items: tuple[GuideSourceSnapshotItem, ...]
    sufficiency_report: GuideSufficiencyReport
    submission_artifact_policy: SubmissionArtifactPolicy
    effective_policy: EffectiveProjectSubmissionArtifactPolicy
    pre_submit_checker_policy: PreSubmitCheckerPolicy
    post_submit_checker_policy: PostSubmitCheckerPolicy
    review_policy: ReviewPolicy
    revision_policy: RevisionPolicy


async def authorize_project_policy_read(
    *,
    authorization: AuthorizationService,
    repository: ProjectRepository,
    action_id: ActionId,
    project_id: str,
    guide_id: str,
) -> EffectiveProjectSubmissionArtifactPolicy | PreSubmitCheckerPolicy:
    """Lock and authorize one current active-guide policy-chain target."""
    if action_id not in PROJECT_POLICY_READ_TARGET_KIND_BY_ACTION:
        raise ValueError("unsupported project policy read action")

    project = await repository.get_project(project_id, for_update=True)
    guide = await repository.lock_project_guide(guide_id) if project is not None else None
    if guide is not None and (guide.project_id != project_id or guide.status != "active"):
        guide = None

    snapshot = submission = effective = checker = None
    try:
        if guide is not None:
            snapshot = await repository.lock_latest_guide_source_snapshot(
                project_id, guide.id, guide.version
            )
        if snapshot is not None:
            effective = await repository.lock_effective_submission_artifact_policy(
                project_id, guide.version, snapshot.id
            )
        if effective is not None:
            submission = await repository.lock_submission_artifact_policy(
                effective.submission_artifact_policy_id
            )
        if (
            effective is not None
            and effective.guide_id == guide_id
            and effective.source_snapshot_hash == snapshot.bundle_hash
            and action_id is ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ
        ):
            checker = await repository.lock_compiled_pre_submit_checker_policy(effective.id)
    except ProjectRepositoryIntegrityError:
        snapshot = submission = effective = checker = None

    target = checker if action_id is ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ else effective
    target_exists = (
        project is not None
        and project.status == "active"
        and guide is not None
        and guide.project_id == project_id
        and guide.status == "active"
        and target is not None
        and submission is not None
        and effective is not None
        and snapshot is not None
    )
    if checker is not None and any(
        (
            checker.project_id != project_id,
            checker.guide_id != guide_id,
            checker.guide_version != guide.version,
            checker.source_snapshot_id != snapshot.id,
            checker.source_snapshot_hash != snapshot.bundle_hash,
            checker.effective_policy_id != effective.id,
            checker.effective_policy_hash != effective.effective_policy_hash,
        )
    ):
        target_exists = False
        target = None
    if target_exists:
        try:
            target_exists = all(
                (
                    effective.project_id == project_id,
                    effective.guide_id == guide_id,
                    effective.guide_version == guide.version,
                    effective.source_snapshot_id == snapshot.id,
                    effective.source_snapshot_hash == snapshot.bundle_hash,
                    effective.lifecycle_status == "approved",
                    submission.project_id == project_id,
                    submission.guide_id == guide_id,
                    submission.guide_version == guide.version,
                    submission.source_snapshot_id == snapshot.id,
                    submission.source_snapshot_hash == snapshot.bundle_hash,
                    submission.lifecycle_status == "approved",
                    submission.id == effective.submission_artifact_policy_id,
                    submission.policy_hash == effective.submission_artifact_policy_hash,
                    canonical_json_hash(submission.policy_body) == submission.policy_hash,
                    canonical_json_hash(effective.effective_policy)
                    == effective.effective_policy_hash,
                    checker is None
                    or (
                        isinstance(checker.compiled_bundle, dict)
                        and canonical_json_hash(checker.compiled_bundle)
                        == checker.compiled_bundle_hash
                    ),
                )
            )
        except (AttributeError, TypeError, ValueError):
            target_exists = False
        if not target_exists:
            target = None

    binding_digest = (
        canonical_json_hash(
            {
                "guide": [guide.id, guide.version, guide.status],
                "snapshot": [snapshot.id, snapshot.bundle_hash],
                "effective": [
                    effective.id,
                    effective.effective_policy_hash,
                    effective.lifecycle_status,
                ],
                "submission": [submission.id, submission.policy_hash],
                "checker": (
                    [checker.id, checker.lifecycle_status, checker.compiled_bundle_hash]
                    if checker is not None
                    else None
                ),
            }
        )
        if target_exists
        else None
    )
    project_uuid = (
        UUID(project.id)
        if project is not None
        else authorization_resource_selector_id("project", project_id)
    )
    guide_uuid = (
        UUID(guide.id)
        if guide is not None
        else authorization_resource_selector_id("project_guide", guide_id)
    )
    await authorization.require(
        action_id,
        ProjectPolicyReadResourceContext(
            resource_type="project_policy_read",
            resource_id=(
                UUID(target.id)
                if target is not None
                else authorization_resource_selector_id(
                    PROJECT_POLICY_READ_TARGET_KIND_BY_ACTION[action_id],
                    f"{project_id}:{guide_id}",
                )
            ),
            scope_project_id=project_uuid,
            guide_id=guide_uuid,
            guide_version=guide.version if guide is not None else None,
            guide_status=guide.status if guide is not None else None,
            target_kind=PROJECT_POLICY_READ_TARGET_KIND_BY_ACTION[action_id],
            project_exists=project is not None,
            project_status=project.status if project is not None else None,
            guide_exists=guide is not None,
            target_exists=target_exists,
            source_snapshot_id=UUID(snapshot.id) if target_exists else None,
            source_snapshot_hash=snapshot.bundle_hash if target_exists else None,
            effective_policy_id=UUID(effective.id) if target_exists else None,
            effective_policy_hash=effective.effective_policy_hash if target_exists else None,
            effective_policy_status=effective.lifecycle_status if target_exists else None,
            checker_policy_id=UUID(checker.id) if checker is not None and target_exists else None,
            checker_policy_status=(checker.lifecycle_status if checker is not None and target_exists else None),
            checker_bundle_hash=(checker.compiled_bundle_hash if checker is not None and target_exists else None),
            target_binding_digest=binding_digest,
        ),
    )
    if target is None:
        raise RuntimeError("missing policy authorization unexpectedly allowed")
    return target


async def authorize_project_active_guide_read(
    *,
    authorization: AuthorizationService,
    repository: ProjectRepository,
    project_service: ProjectService,
    project_id: str,
) -> ActiveGuideReadBundle:
    """Lock and authorize the current active guide's non-compensation bundle."""
    project = await repository.get_project(project_id, for_update=True)
    guide = snapshot = sufficiency = submission = effective = checker = None
    source_items: tuple[GuideSourceSnapshotItem, ...] = ()
    post_submit = review = revision = None
    try:
        if project is not None:
            guide = await repository.lock_active_guide(project_id)
        if guide is not None:
            snapshot = await repository.lock_latest_guide_source_snapshot(
                project_id, guide.id, guide.version
            )
        if snapshot is not None:
            source_items = tuple(
                await repository.lock_guide_source_snapshot_items(snapshot.id)
            )
            effective = await repository.lock_effective_submission_artifact_policy(
                project_id, guide.version, snapshot.id
            )
            sufficiency_candidate = await repository.get_sufficiency_report_for_snapshot(
                snapshot.id
            )
            if sufficiency_candidate is not None:
                sufficiency = await repository.lock_guide_sufficiency_report(
                    sufficiency_candidate.id, project_id, guide.id, guide.version
                )
        if effective is not None:
            submission = await repository.lock_submission_artifact_policy(
                effective.submission_artifact_policy_id
            )
            checker = await repository.lock_compiled_pre_submit_checker_policy(effective.id)
        if guide is not None:
            post_submit = await repository.lock_post_submit_checker_policy_for_guide(
                project_id, guide.version
            )
            review = await repository.lock_review_policy(project_id, guide.version)
            revision = await repository.lock_revision_policy(project_id, guide.version)
    except ProjectRepositoryIntegrityError:
        guide = snapshot = sufficiency = submission = effective = checker = None
        post_submit = review = revision = None

    rows = (
        guide,
        snapshot,
        *source_items,
        sufficiency,
        submission,
        effective,
        checker,
        post_submit,
        review,
        revision,
    )
    target_exists = (
        project is not None and project.status == "active" and all(row is not None for row in rows)
    )
    if target_exists:
        target_exists = all(
            (
                snapshot.project_id == project_id,
                snapshot.guide_id == guide.id,
                snapshot.guide_version == guide.version,
                sufficiency.source_snapshot_id == snapshot.id,
                sufficiency.source_snapshot_hash == snapshot.bundle_hash,
                sufficiency.status in {"passed", "passed_with_warnings"},
                sufficiency.status != "passed_with_warnings"
                or (
                    sufficiency.warnings_acknowledged_by_actor is not None
                    and sufficiency.warnings_acknowledged_at is not None
                    and sufficiency.warnings_acknowledged_by_role in {"admin", "project_manager"}
                ),
                submission.project_id == project_id,
                submission.guide_id == guide.id,
                submission.guide_version == guide.version,
                submission.source_snapshot_id == snapshot.id,
                submission.source_snapshot_hash == snapshot.bundle_hash,
                submission.id == effective.submission_artifact_policy_id,
                submission.policy_hash == effective.submission_artifact_policy_hash,
                submission.lifecycle_status == "approved",
                submission.approved_by_actor is not None,
                submission.approved_at is not None,
                submission.approved_by_role in {"admin", "project_manager"},
                effective.guide_id == guide.id,
                effective.source_snapshot_hash == snapshot.bundle_hash,
                checker.effective_policy_id == effective.id,
                checker.effective_policy_hash == effective.effective_policy_hash,
                checker.compiled_bundle_hash is not None,
                checker.lifecycle_status == "compiled",
                post_submit.guide_id == guide.id,
                post_submit.source_snapshot_id == snapshot.id,
                post_submit.source_snapshot_hash == snapshot.bundle_hash,
                post_submit.effective_policy_id == effective.id,
                post_submit.effective_policy_hash == effective.effective_policy_hash,
                post_submit.pre_submit_checker_policy_id == checker.id,
                post_submit.pre_submit_checker_bundle_hash == checker.compiled_bundle_hash,
                post_submit.lifecycle_status == "approved",
                post_submit.approved_by_actor is not None,
                post_submit.approved_at is not None,
                post_submit.approved_by_role in {"admin", "project_manager"},
                review.project_id == project_id,
                review.guide_version == guide.version,
                bool(review.allowed_decisions),
                set(review.allowed_decisions).issubset({"accept", "needs_revision", "reject"}),
                revision.project_id == project_id,
                revision.guide_version == guide.version,
                revision.max_revision_rounds >= 0,
            )
        ) and all(item.source_snapshot_id == snapshot.id for item in source_items)
    if target_exists:
        try:
            await project_service.validate_source_snapshot_integrity(
                snapshot,
                GuideActivationBlocked,
                persisted_items=source_items,
            )
            project_service.validate_activation_ready(
                guide,
                snapshot,
                sufficiency,
                submission,
                effective,
                checker,
                post_submit,
                review,
                revision,
                None,
                require_payment_policy=False,
            )
        except ProjectServiceError:
            target_exists = False
    binding_digest = (
        canonical_json_hash(
            [
                {"type": type(row).__name__, "id": row.id}
                | {
                    key: getattr(row, key)
                    for key in (
                        "status",
                        "lifecycle_status",
                        "bundle_hash",
                        "source_snapshot_hash",
                        "policy_hash",
                        "effective_policy_hash",
                        "compiled_bundle_hash",
                    )
                    if hasattr(row, key)
                }
                for row in rows
            ]
        )
        if target_exists
        else None
    )
    project_uuid = (
        UUID(project.id)
        if project is not None
        else authorization_resource_selector_id("project", project_id)
    )
    guide_uuid = (
        UUID(guide.id)
        if guide is not None
        else authorization_resource_selector_id("active_guide", project_id)
    )
    await authorization.require(
        ActionId.PROJECT_ACTIVE_GUIDE_READ,
        ProjectActiveGuideReadResourceContext(
            resource_type="project_active_guide_read",
            resource_id=guide_uuid,
            scope_project_id=project_uuid,
            guide_id=guide_uuid,
            guide_version=guide.version if guide is not None else None,
            guide_status=guide.status if guide is not None else None,
            project_exists=project is not None,
            project_status=project.status if project is not None else None,
            guide_exists=guide is not None,
            target_exists=target_exists,
            source_snapshot_id=UUID(snapshot.id) if target_exists else None,
            source_snapshot_hash=snapshot.bundle_hash if target_exists else None,
            sufficiency_report_id=UUID(sufficiency.id) if target_exists else None,
            sufficiency_report_status=sufficiency.status if target_exists else None,
            submission_artifact_policy_id=UUID(submission.id) if target_exists else None,
            submission_artifact_policy_hash=submission.policy_hash if target_exists else None,
            submission_artifact_policy_status=(
                submission.lifecycle_status if target_exists else None
            ),
            effective_policy_id=UUID(effective.id) if target_exists else None,
            effective_policy_hash=effective.effective_policy_hash if target_exists else None,
            effective_policy_status=effective.lifecycle_status if target_exists else None,
            pre_submit_checker_policy_id=UUID(checker.id) if target_exists else None,
            pre_submit_checker_bundle_hash=(
                checker.compiled_bundle_hash if target_exists else None
            ),
            pre_submit_checker_policy_status=(checker.lifecycle_status if target_exists else None),
            post_submit_checker_policy_id=UUID(post_submit.id) if target_exists else None,
            post_submit_checker_policy_status=(
                post_submit.lifecycle_status if target_exists else None
            ),
            review_policy_id=UUID(review.id) if target_exists else None,
            revision_policy_id=UUID(revision.id) if target_exists else None,
            policy_binding_digest=binding_digest,
        ),
    )
    if not target_exists:
        raise RuntimeError("missing active-guide authorization unexpectedly allowed")
    return ActiveGuideReadBundle(
        guide=guide,
        source_snapshot=snapshot,
        source_items=source_items,
        sufficiency_report=sufficiency,
        submission_artifact_policy=submission,
        effective_policy=effective,
        pre_submit_checker_policy=checker,
        post_submit_checker_policy=post_submit,
        review_policy=review,
        revision_policy=revision,
    )

async def authorize_project_diagnostic_read(
    *,
    authorization: AuthorizationService,
    repository: ProjectRepository,
    action_id: ActionId,
    project_id: str,
    guide_id: str,
    target_id: str | None = None,
) -> DiagnosticResult:
    """Lock canonical facts, require exact scoped authority, and return them."""
    if action_id not in PROJECT_DIAGNOSTIC_TARGET_KIND_BY_ACTION:
        raise ValueError("unsupported project diagnostic read action")

    project = await repository.get_project(project_id, for_update=True)
    guide = await repository.lock_project_guide(guide_id) if project is not None else None
    if guide is not None and guide.project_id != project_id:
        guide = None

    target: DiagnosticResult | None = None
    post_submit_policy = None
    if guide is not None:
        if action_id in {
            ActionId.PROJECT_SETUP_RUN_READ,
            ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ,
        }:
            setup_run = await repository.lock_latest_project_setup_run(
                project_id, guide_id, guide.version
            )
            target = setup_run
            if (
                action_id is ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ
                and setup_run is not None
                and setup_run.output_post_submit_checker_policy_id is not None
            ):
                post_submit_policy = await repository.lock_post_submit_checker_policy(
                    setup_run.output_post_submit_checker_policy_id
                )
                if post_submit_policy is None or any(
                    getattr(post_submit_policy, field) != getattr(setup_run, field)
                    for field in (
                        "project_id",
                        "guide_id",
                        "guide_version",
                        "source_snapshot_id",
                        "source_snapshot_hash",
                    )
                ):
                    target = None
                    post_submit_policy = None
        elif action_id is ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST:
            target = await repository.lock_guide_sufficiency_reports(
                project_id, guide_id, guide.version
            )
        elif action_id is ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ and target_id:
            target = await repository.lock_guide_sufficiency_report(
                target_id, project_id, guide_id, guide.version
            )
        elif action_id is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST:
            target = await repository.lock_submission_artifact_policies(
                project_id, guide_id, guide.version
            )
        elif action_id is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ and target_id:
            target = await repository.lock_submission_artifact_policy_diagnostic(
                target_id, project_id, guide_id, guide.version
            )

    is_collection = action_id in {
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
    }
    target_exists = guide is not None and (is_collection or target is not None)
    record = None if target is None or is_collection else target
    if record is not None and (record.project_id != project_id or record.guide_id != guide_id):
        target_exists = False
        record = None
        target = None

    records = list(target) if is_collection and target is not None else ([record] if record else [])
    if post_submit_policy is not None:
        records.append(post_submit_policy)
    target_binding_digest = (
        canonical_json_hash(
            [
                {
                    "id": item.id,
                    "project_id": item.project_id,
                    "guide_id": item.guide_id,
                    "guide_version": item.guide_version,
                    "source_snapshot_id": item.source_snapshot_id,
                    "source_snapshot_hash": item.source_snapshot_hash,
                }
                for item in records
            ]
        )
        if target_exists
        else None
    )

    project_uuid = (
        UUID(project.id)
        if project is not None
        else authorization_resource_selector_id("project", project_id)
    )
    guide_uuid = (
        UUID(guide.id)
        if guide is not None
        else authorization_resource_selector_id("project_guide", guide_id)
    )
    if record is not None:
        resource_id = UUID(record.id)
    elif is_collection and guide is not None:
        resource_id = guide_uuid
    else:
        resource_id = authorization_resource_selector_id(
            PROJECT_DIAGNOSTIC_TARGET_KIND_BY_ACTION[action_id],
            target_id or f"{project_id}:{guide_id}",
        )

    await authorization.require(
        action_id,
        ProjectDiagnosticReadResourceContext(
            resource_type="project_diagnostic",
            resource_id=resource_id,
            scope_project_id=project_uuid,
            guide_id=guide_uuid,
            guide_version=guide.version if guide is not None else None,
            target_kind=PROJECT_DIAGNOSTIC_TARGET_KIND_BY_ACTION[action_id],
            project_exists=project is not None,
            guide_exists=guide is not None,
            target_exists=target_exists,
            target_binding_digest=target_binding_digest,
            source_snapshot_id=(UUID(record.source_snapshot_id) if record is not None else None),
            source_snapshot_hash=(record.source_snapshot_hash if record is not None else None),
        ),
    )
    if target is None:
        raise RuntimeError("missing diagnostic authorization unexpectedly allowed")
    if action_id is ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ:
        return (target, post_submit_policy)
    return target
