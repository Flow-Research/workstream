"""Canonical composition for project setup diagnostic authorization reads."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    PROJECT_DIAGNOSTIC_TARGET_KIND_BY_ACTION,
    ProjectDiagnosticReadResourceContext,
    authorization_resource_selector_id,
)
from app.modules.projects.models import (
    GuideSufficiencyReport,
    PostSubmitCheckerPolicy,
    ProjectSetupRun,
    SubmissionArtifactPolicy,
)
from app.modules.projects.repository import ProjectRepository

DiagnosticRecord: TypeAlias = ProjectSetupRun | GuideSufficiencyReport | SubmissionArtifactPolicy
DiagnosticResult: TypeAlias = (
    DiagnosticRecord
    | Sequence[DiagnosticRecord]
    | tuple[ProjectSetupRun, PostSubmitCheckerPolicy | None]
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
