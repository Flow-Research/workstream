"""FastAPI routes for project and guide lifecycle operations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_registered_actor
from app.core.permissions import PermissionDenied
from app.db.session import get_db_session
from app.modules.projects.schemas import (
    ActiveGuideResponse,
    EffectiveProjectSubmissionArtifactPolicyResponse,
    GuideSourceSnapshotCreate,
    GuideSourceSnapshotResponse,
    GuideSufficiencyAcknowledgement,
    GuideSufficiencyReportCreate,
    GuideSufficiencyReportResponse,
    PreSubmitCheckerPolicySummaryResponse,
    ProjectCreate,
    ProjectGuideCreate,
    ProjectGuideResponse,
    ProjectGuideUpdate,
    ProjectResponse,
    ProjectSetupRunResponse,
    SubmissionArtifactPolicyApprove,
    SubmissionArtifactPolicyCreate,
    SubmissionArtifactPolicyResponse,
    SubmissionArtifactPolicyUpdate,
)
from app.modules.projects.service import ProjectService, ProjectServiceError
from app.schemas.auth import ActorContext

router = APIRouter(prefix="/projects", tags=["projects"])


def project_http_error(exc: ProjectServiceError) -> HTTPException:
    """Convert a service-layer project error into an HTTP error.

    Args:
        exc: Project service exception with an API status code.

    Returns:
        HTTP exception carrying the service error details.
    """
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def permission_http_error(exc: PermissionDenied) -> HTTPException:
    """Convert a permission failure into a 403 HTTP error.

    Args:
        exc: Permission exception raised by the service layer.

    Returns:
        HTTP exception with a forbidden status.
    """
    return HTTPException(status_code=403, detail=str(exc))


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    payload: ProjectCreate,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectResponse:
    """Create a draft project shell for future guide versions."""
    try:
        return await ProjectService(session).create_project(actor, payload)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectResponse:
    """Return one project by id."""
    try:
        return await ProjectService(session).get_project(actor, project_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.post("/{project_id}/guides", response_model=ProjectGuideResponse, status_code=201)
async def create_guide(
    project_id: str,
    payload: ProjectGuideCreate,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectGuideResponse:
    """Create a draft guide and enqueue automatic pre-submit setup."""
    try:
        return await ProjectService(session).create_guide(actor, project_id, payload)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.patch("/{project_id}/guides/{guide_id}", response_model=ProjectGuideResponse)
async def update_guide(
    project_id: str,
    guide_id: str,
    payload: ProjectGuideUpdate,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectGuideResponse:
    """Update a draft guide and optional post-submit/review/revision/payment policies."""
    try:
        return await ProjectService(session).update_draft_guide(
            actor,
            project_id,
            guide_id,
            payload,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.post(
    "/{project_id}/guides/{guide_id}/source-snapshots",
    response_model=GuideSourceSnapshotResponse,
    status_code=201,
)
async def create_guide_source_snapshot(
    project_id: str,
    guide_id: str,
    payload: GuideSourceSnapshotCreate,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GuideSourceSnapshotResponse:
    """Create an immutable source-material snapshot for a draft guide."""
    try:
        return await ProjectService(session).create_guide_source_snapshot(
            actor,
            project_id,
            guide_id,
            payload,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.get(
    "/{project_id}/guides/{guide_id}/setup-runs/latest",
    response_model=ProjectSetupRunResponse,
)
async def get_latest_project_setup_run(
    project_id: str,
    guide_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectSetupRunResponse:
    """Return the latest automatic setup run for one project guide."""
    try:
        return await ProjectService(session).get_latest_project_setup_run(
            actor,
            project_id,
            guide_id,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.get(
    "/{project_id}/guides/{guide_id}/sufficiency-reports",
    response_model=list[GuideSufficiencyReportResponse],
)
async def list_guide_sufficiency_reports(
    project_id: str,
    guide_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[GuideSufficiencyReportResponse]:
    """List guide sufficiency reports for one project guide."""
    try:
        return await ProjectService(session).list_guide_sufficiency_reports(
            actor,
            project_id,
            guide_id,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.get(
    "/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}",
    response_model=GuideSufficiencyReportResponse,
)
async def get_guide_sufficiency_report(
    project_id: str,
    guide_id: str,
    report_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GuideSufficiencyReportResponse:
    """Return one guide sufficiency report for one project guide."""
    try:
        return await ProjectService(session).get_guide_sufficiency_report(
            actor,
            project_id,
            guide_id,
            report_id,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.post(
    "/{project_id}/guides/{guide_id}/sufficiency-reports",
    response_model=GuideSufficiencyReportResponse,
    status_code=201,
)
async def create_guide_sufficiency_report(
    project_id: str,
    guide_id: str,
    payload: GuideSufficiencyReportCreate,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GuideSufficiencyReportResponse:
    """Record Workstream's sufficiency assessment for a guide snapshot."""
    try:
        return await ProjectService(session).create_guide_sufficiency_report(
            actor,
            project_id,
            guide_id,
            payload,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.get(
    "/{project_id}/guides/{guide_id}/submission-artifact-policies",
    response_model=list[SubmissionArtifactPolicyResponse],
)
async def list_submission_artifact_policies(
    project_id: str,
    guide_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[SubmissionArtifactPolicyResponse]:
    """List submission artifact policies for one project guide."""
    try:
        return await ProjectService(session).list_submission_artifact_policies(
            actor,
            project_id,
            guide_id,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.get(
    "/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}",
    response_model=SubmissionArtifactPolicyResponse,
)
async def get_submission_artifact_policy(
    project_id: str,
    guide_id: str,
    policy_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionArtifactPolicyResponse:
    """Return one submission artifact policy for one project guide."""
    try:
        return await ProjectService(session).get_submission_artifact_policy(
            actor,
            project_id,
            guide_id,
            policy_id,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.post(
    "/{project_id}/guides/{guide_id}/source-snapshots/{source_snapshot_id}/run-sufficiency-agent",
    response_model=GuideSufficiencyReportResponse,
    status_code=201,
    responses={
        200: {
            "model": GuideSufficiencyReportResponse,
            "description": "Existing guide sufficiency report reused.",
        }
    },
)
async def run_guide_sufficiency_agent(
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GuideSufficiencyReportResponse:
    """Run Workstream's guide sufficiency agent for a source snapshot."""
    try:
        result, created = await ProjectService(session).run_guide_sufficiency_agent(
            actor,
            project_id,
            guide_id,
            source_snapshot_id,
        )
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return result
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.post(
    "/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}/acknowledge-warnings",
    response_model=GuideSufficiencyReportResponse,
)
async def acknowledge_guide_sufficiency_warnings(
    project_id: str,
    guide_id: str,
    report_id: str,
    payload: GuideSufficiencyAcknowledgement,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GuideSufficiencyReportResponse:
    """Acknowledge non-blocking guide sufficiency warnings."""
    try:
        return await ProjectService(session).acknowledge_guide_sufficiency_warnings(
            actor,
            project_id,
            guide_id,
            report_id,
            payload,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.post(
    "/{project_id}/guides/{guide_id}/submission-artifact-policies",
    response_model=SubmissionArtifactPolicyResponse,
    status_code=201,
)
async def create_submission_artifact_policy(
    project_id: str,
    guide_id: str,
    payload: SubmissionArtifactPolicyCreate,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionArtifactPolicyResponse:
    """Create a draft Workstream-derived submission artifact policy."""
    try:
        return await ProjectService(session).create_submission_artifact_policy(
            actor,
            project_id,
            guide_id,
            payload,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.post(
    "/{project_id}/guides/{guide_id}/source-snapshots/{source_snapshot_id}/derive-submission-artifact-policy",
    response_model=SubmissionArtifactPolicyResponse,
    status_code=201,
    responses={
        200: {
            "model": SubmissionArtifactPolicyResponse,
            "description": "Existing agent-derived submission artifact policy reused.",
        }
    },
)
async def run_submission_artifact_policy_derivation_agent(
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionArtifactPolicyResponse:
    """Run Workstream's submission artifact policy derivation agent."""
    try:
        result, created = await ProjectService(session).run_submission_artifact_policy_derivation_agent(
            actor,
            project_id,
            guide_id,
            source_snapshot_id,
        )
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return result
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.patch(
    "/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}",
    response_model=SubmissionArtifactPolicyResponse,
)
async def update_submission_artifact_policy(
    project_id: str,
    guide_id: str,
    policy_id: str,
    payload: SubmissionArtifactPolicyUpdate,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionArtifactPolicyResponse:
    """Update a draft submission artifact policy."""
    try:
        return await ProjectService(session).update_submission_artifact_policy(
            actor,
            project_id,
            guide_id,
            policy_id,
            payload,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.post(
    "/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}/approve",
    response_model=EffectiveProjectSubmissionArtifactPolicyResponse,
)
async def approve_submission_artifact_policy(
    project_id: str,
    guide_id: str,
    policy_id: str,
    payload: SubmissionArtifactPolicyApprove,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EffectiveProjectSubmissionArtifactPolicyResponse:
    """Approve a draft submission artifact policy and persist the effective policy."""
    try:
        return await ProjectService(session).approve_submission_artifact_policy(
            actor,
            project_id,
            guide_id,
            policy_id,
            payload,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.get(
    "/{project_id}/guides/{guide_id}/effective-submission-artifact-policy",
    response_model=EffectiveProjectSubmissionArtifactPolicyResponse,
)
async def get_current_effective_submission_artifact_policy(
    project_id: str,
    guide_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EffectiveProjectSubmissionArtifactPolicyResponse:
    """Return the current effective submission artifact policy for a guide."""
    try:
        return await ProjectService(session).get_current_effective_submission_artifact_policy(
            actor,
            project_id,
            guide_id,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.get(
    "/{project_id}/guides/{guide_id}/pre-submit-checker-policy",
    response_model=PreSubmitCheckerPolicySummaryResponse,
)
async def get_current_pre_submit_checker_policy(
    project_id: str,
    guide_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreSubmitCheckerPolicySummaryResponse:
    """Return the current project pre-submit checker policy summary."""
    try:
        return await ProjectService(session).get_current_pre_submit_checker_policy(
            actor,
            project_id,
            guide_id,
        )
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.post("/{project_id}/guides/{guide_id}/activate", response_model=ActiveGuideResponse)
async def activate_guide(
    project_id: str,
    guide_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActiveGuideResponse:
    """Activate a complete draft guide for a project."""
    try:
        return await ProjectService(session).activate_guide(actor, project_id, guide_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


@router.get("/{project_id}/active-guide", response_model=ActiveGuideResponse)
async def get_active_guide(
    project_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActiveGuideResponse:
    """Return the current active guide and policy context for a project."""
    try:
        return await ProjectService(session).get_active_guide(actor, project_id)
    except PermissionDenied as exc:
        raise permission_http_error(exc) from exc
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc
