"""FastAPI routes for project and guide lifecycle operations."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.artifacts import (
    get_guide_artifact_ingest_command, get_guide_artifact_prepared_authorization,
    get_artifact_internal_authority, GuideArtifactPreparedAuthorization, ArtifactInternalAuthority,
)
from app.modules.projects.document_upload import ProjectGuideDocumentUploadTargets
from app.api.deps.authorization import (
    enforce_human_authorization_read,
    get_authorization_actor,
    get_authorization_service,
    prepared_authorization_service,
)
from app.core.permissions import PermissionDenied
from app.core.api_controls import ApiErrorResponse, StructuredHTTPException
from app.db.session import get_db_session
from app.interfaces.artifacts import ArtifactLimitExceededError, ArtifactInputMismatchError, ArtifactStoreError
from app.interfaces.artifact_operations import (
    GuideArtifactIngestCommand,
)
from app.modules.artifacts.authorization import get_artifact_authorization_context
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.service import ArtifactAdmissionRelationshipError, ArtifactAdmissionConflictError
from app.modules.projects.schemas import (
    ActiveGuideReadResponse,
    EffectiveProjectSubmissionArtifactPolicyResponse,
    GuideArtifactIngestResponse,
    GuideSufficiencyAcknowledgement,
    GuideSufficiencyReportCreate,
    GuideSufficiencyReportResponse,
    PreSubmitCheckerPolicySummaryResponse,
    ContributorProjectResponse,
    ProjectResponse,
    ProjectSetupRunResponse,
    SubmissionArtifactPolicyCreate,
    SubmissionArtifactPolicyResponse,
    SubmissionArtifactPolicyUpdate,
)
from app.modules.projects.service import ProjectService, ProjectServiceError
from app.modules.projects.guide_mutation_router import (
    mutation_conflict_error,
    require_guide_mutation_key,
    guide_authorization_actor,
    sufficiency_authorization,
)
from app.modules.projects.sufficiency_mutation_service import (
    GuideSufficiencyMutationConflict,
    GuideSufficiencyMutationService,
)
from app.modules.projects.submission_policy_mutation_service import (
    SubmissionPolicyMutationConflict,
    SubmissionPolicyMutationService,
)
from app.modules.actors.service import ResolvedActor
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.projects.authorization_reads import (
    authorize_project_active_guide_read,
    authorize_project_diagnostic_read,
    authorize_project_policy_read,
)
from app.modules.projects.api.guide_documents import DOCUMENT_EXTENSIONS
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.guide_compilation.diagnostics import compilation_setup_response
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    MatchedAuthorityKind,
    ProjectReadResourceContext,
    authorization_resource_selector_id,
)

LOGGER = logging.getLogger(__name__)
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


def submission_policy_conflict_error(code: str) -> StructuredHTTPException:
    """Return a bounded manual-policy conflict without guide-mutation wording."""
    messages = {
        "idempotency_mismatch": "Idempotency key does not match",
        "idempotency_pending": "Submission policy mutation is already in progress",
        "submission_policy_precondition_failed": "Submission policy precondition failed",
        "submission_policy_lineage_stale": "Submission policy lineage is stale",
        "submission_policy_version_conflict": "Submission policy version already exists",
    }
    return StructuredHTTPException(
        status_code=409,
        detail=code,
        error_code=code,
        error_message=messages.get(code, "Submission policy mutation conflicts with current state"),
        retryable=code == "idempotency_pending",
    )


def require_submission_policy_mutation_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> UUID:
    """Validate manual policy replay custody before actor provisioning."""
    if idempotency_key is None:
        raise StructuredHTTPException(
            status_code=422,
            detail="Idempotency-Key must be a UUID",
            error_code="validation_error",
            error_message="Idempotency-Key must be a UUID",
        )
    try:
        return UUID(idempotency_key)
    except ValueError as exc:
        raise StructuredHTTPException(
            status_code=422,
            detail="Idempotency-Key must be a UUID",
            error_code="validation_error",
            error_message="Idempotency-Key must be a UUID",
        ) from exc


async def require_submission_policy_human(
    key: Annotated[UUID, Depends(require_submission_policy_mutation_key)],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
) -> ResolvedActor:
    """Conceal the public manual-policy surface from service principals."""
    del key
    if resolved.profile.actor_kind != "human":
        raise StructuredHTTPException(
            status_code=404,
            detail="Project authorization resource not found",
            error_code="project_authorization_resource_not_found",
            error_message="Project authorization resource not found",
        )
    return resolved


async def get_submission_policy_prepared_authorization_service(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(require_submission_policy_human)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Compose submission-policy PREP from its dedicated admitted actor."""
    async with prepared_authorization_service(request, resolved, session) as service:
        yield service


async def submission_policy_authorization(
    key: Annotated[UUID, Depends(require_submission_policy_mutation_key)],
    resolved: Annotated[ResolvedActor, Depends(require_submission_policy_human)],
    prepared: Annotated[
        PreparedAuthorizationService,
        Depends(get_submission_policy_prepared_authorization_service),
    ],
):
    """Return the exact actor, key, and PREP service for manual policy mutation."""
    return key, resolved, prepared


@router.get(
    "/{project_id}",
    response_model=ProjectResponse | ContributorProjectResponse,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_READ.value},
    dependencies=[Depends(enforce_human_authorization_read)],
)
async def get_project(
    project_id: str,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectResponse | ContributorProjectResponse:
    """Return one project by id."""
    try:
        service = ProjectService(session)
        project = await service.find_project(project_id)
        project_uuid = (
            UUID(project.id)
            if project is not None
            else authorization_resource_selector_id("project", project_id)
        )
        decision = await authorization.require(
            ActionId.PROJECT_READ,
            ProjectReadResourceContext(
                resource_type="project",
                resource_id=project_uuid,
                scope_project_id=project_uuid,
                project_exists=project is not None,
                project_status=project.status if project is not None else None,
            ),
        )
        if project is None:
            raise RuntimeError("missing project authorization unexpectedly allowed")
        response = service.project_identity_response(
            project,
            contributor_only=(
                decision.matched_authority_kind is MatchedAuthorityKind.PROJECT_ROLE_GRANT
            ),
        )
        await session.commit()
        return response
    except ProjectServiceError as exc:
        raise project_http_error(exc) from exc


async def guide_upload_context(
    key: Annotated[UUID, Depends(require_guide_mutation_key)],
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(guide_authorization_actor)],
):
    """Reuse the key-gated actor dependency before composing ingest context."""
    return key, await get_artifact_authorization_context(request, resolved)


def guide_document_upload_command(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[GuideArtifactPreparedAuthorization, Depends(get_guide_artifact_prepared_authorization)],
    internal_authority: Annotated[ArtifactInternalAuthority, Depends(get_artifact_internal_authority)],
) -> GuideArtifactIngestCommand:
    """Compose the PROJECTS-owned selector lookup with the existing ART command."""
    return get_guide_artifact_ingest_command(
        request, session, authority, internal_authority, ProjectGuideDocumentUploadTargets(session),
    )


@router.post(
    "/{project_id}/guides/{guide_id}/documents/{document_id}/content",
    response_model=GuideArtifactIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        "x-workstream-action-id": ActionId.ARTIFACT_GUIDE_SOURCE_INGEST.value,
        "requestBody": {"required": True, "content": {
            media_type: {"schema": {"type": "string", "format": "binary"}}
            for media_type in DOCUMENT_EXTENSIONS
        }},
    },
    responses={404: {"model": ApiErrorResponse, "description": "Document unavailable"},
               409: {"model": ApiErrorResponse, "description": "Upload conflicts with committed document"},
               413: {"model": ApiErrorResponse, "description": "Document exceeds configured byte limit"},
               422: {"model": ApiErrorResponse, "description": "Invalid upload metadata or bytes"},
               503: {"model": ApiErrorResponse, "description": "Artifact storage unavailable"}},
)
async def upload_guide_document(
    project_id: UUID,
    guide_id: UUID,
    document_id: UUID,
    request: Request,
    authorization: Annotated[tuple, Depends(guide_upload_context)],
    ingest: Annotated[GuideArtifactIngestCommand, Depends(guide_document_upload_command)],
    content_type: Annotated[str, Header(alias="Content-Type", min_length=1)],
    content_length: Annotated[int | None, Header(alias="Content-Length", ge=0)] = None,
) -> GuideArtifactIngestResponse:
    """Store one declared original; complete membership gates automatic setup."""
    key, context = authorization
    try:
        result = await ingest.ingest(
            authorization_context=context, project_id=project_id, guide_id=guide_id,
            source_item_id=document_id, idempotency_key=key,
            content_type=content_type.partition(";")[0].strip().lower(),
            content_length=content_length,
            byte_source=request.stream(),
        )
    except (ArtifactAdmissionRelationshipError, ArtifactAuthorityDeniedError) as exc:
        raise HTTPException(status_code=404, detail="Guide document not found") from exc
    except ArtifactAdmissionConflictError as exc:
        raise HTTPException(status_code=409, detail="Guide document upload conflicts") from exc
    except ArtifactLimitExceededError as exc:
        raise HTTPException(status_code=413, detail="Guide document exceeds byte limit") from exc
    except ArtifactInputMismatchError as exc:
        raise HTTPException(status_code=422, detail="Invalid guide document bytes") from exc
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=503, detail="Guide document storage unavailable") from exc
    return GuideArtifactIngestResponse(
        document_id=document_id, sha256=result.sha256, byte_count=result.byte_count,
        status=result.status, replayed=result.replayed,
    )


@router.get(
    "/{project_id}/guides/{guide_id}/setup-runs/latest",
    response_model=ProjectSetupRunResponse,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_SETUP_RUN_READ.value},
    dependencies=[Depends(enforce_human_authorization_read)],
)
async def get_latest_project_setup_run(
    project_id: str,
    guide_id: str,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectSetupRunResponse:
    """Return the latest automatic setup run for one project guide."""
    run = await authorize_project_diagnostic_read(
        authorization=authorization,
        repository=ProjectRepository(session),
        action_id=ActionId.PROJECT_SETUP_RUN_READ,
        project_id=project_id,
        guide_id=guide_id,
    )
    response = await compilation_setup_response(session, run)
    await session.commit()
    return response


@router.get(
    "/{project_id}/guides/{guide_id}/sufficiency-reports",
    response_model=list[GuideSufficiencyReportResponse],
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST.value},
    dependencies=[Depends(enforce_human_authorization_read)],
)
async def list_guide_sufficiency_reports(
    project_id: str,
    guide_id: str,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[GuideSufficiencyReportResponse]:
    """List guide sufficiency reports for one project guide."""
    reports = await authorize_project_diagnostic_read(
        authorization=authorization,
        repository=ProjectRepository(session),
        action_id=ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
        project_id=project_id,
        guide_id=guide_id,
    )
    response = [GuideSufficiencyReportResponse.model_validate(report) for report in reports]
    await session.commit()
    return response


@router.get(
    "/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}",
    response_model=GuideSufficiencyReportResponse,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ.value},
    dependencies=[Depends(enforce_human_authorization_read)],
)
async def get_guide_sufficiency_report(
    project_id: str,
    guide_id: str,
    report_id: str,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GuideSufficiencyReportResponse:
    """Return one guide sufficiency report for one project guide."""
    report = await authorize_project_diagnostic_read(
        authorization=authorization,
        repository=ProjectRepository(session),
        action_id=ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
        project_id=project_id,
        guide_id=guide_id,
        target_id=report_id,
    )
    response = GuideSufficiencyReportResponse.model_validate(report)
    await session.commit()
    return response


@router.post(
    "/{project_id}/guides/{guide_id}/sufficiency-reports",
    response_model=GuideSufficiencyReportResponse,
    status_code=201,
    openapi_extra={
        "x-workstream-action-id": ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE.value
    },
)
async def create_guide_sufficiency_report(
    project_id: UUID,
    guide_id: UUID,
    payload: GuideSufficiencyReportCreate,
    authorization: Annotated[
        tuple[UUID, ResolvedActor, PreparedAuthorizationService],
        Depends(sufficiency_authorization),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GuideSufficiencyReportResponse:
    """Record Workstream's sufficiency assessment for a guide snapshot."""
    key, resolved, prepared = authorization
    try:
        outcome = await GuideSufficiencyMutationService(session).create_report(
            resolved, prepared, key, project_id, guide_id, payload
        )
        await (session.rollback() if outcome.replayed else session.commit())
        return outcome.response
    except GuideSufficiencyMutationConflict as exc:
        await session.rollback()
        raise mutation_conflict_error(str(exc)) from exc
    except ProjectServiceError as exc:
        await session.rollback()
        raise project_http_error(exc) from exc


@router.get(
    "/{project_id}/guides/{guide_id}/submission-artifact-policies",
    response_model=list[SubmissionArtifactPolicyResponse],
    openapi_extra={
        "x-workstream-action-id": ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST.value
    },
    dependencies=[Depends(enforce_human_authorization_read)],
)
async def list_submission_artifact_policies(
    project_id: str,
    guide_id: str,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[SubmissionArtifactPolicyResponse]:
    """List submission artifact policies for one project guide."""
    policies = await authorize_project_diagnostic_read(
        authorization=authorization,
        repository=ProjectRepository(session),
        action_id=ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
        project_id=project_id,
        guide_id=guide_id,
    )
    response = [SubmissionArtifactPolicyResponse.model_validate(policy) for policy in policies]
    await session.commit()
    return response


@router.get(
    "/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}",
    response_model=SubmissionArtifactPolicyResponse,
    openapi_extra={
        "x-workstream-action-id": ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ.value
    },
    dependencies=[Depends(enforce_human_authorization_read)],
)
async def get_submission_artifact_policy(
    project_id: str,
    guide_id: str,
    policy_id: str,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionArtifactPolicyResponse:
    """Return one submission artifact policy for one project guide."""
    policy = await authorize_project_diagnostic_read(
        authorization=authorization,
        repository=ProjectRepository(session),
        action_id=ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
        project_id=project_id,
        guide_id=guide_id,
        target_id=policy_id,
    )
    response = SubmissionArtifactPolicyResponse.model_validate(policy)
    await session.commit()
    return response


@router.post(
    "/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}/acknowledge-warnings",
    response_model=GuideSufficiencyReportResponse,
    openapi_extra={
        "x-workstream-action-id": (ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE.value)
    },
)
async def acknowledge_guide_sufficiency_warnings(
    project_id: UUID,
    guide_id: UUID,
    report_id: UUID,
    payload: GuideSufficiencyAcknowledgement,
    authorization: Annotated[
        tuple[UUID, ResolvedActor, PreparedAuthorizationService],
        Depends(sufficiency_authorization),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GuideSufficiencyReportResponse:
    """Acknowledge non-blocking guide sufficiency warnings."""
    key, resolved, prepared = authorization
    try:
        outcome = await GuideSufficiencyMutationService(session).acknowledge_warnings(
            resolved, prepared, key, project_id, guide_id, report_id, payload
        )
        await (session.rollback() if outcome.replayed else session.commit())
        return outcome.response
    except GuideSufficiencyMutationConflict as exc:
        await session.rollback()
        raise mutation_conflict_error(str(exc)) from exc
    except ProjectServiceError as exc:
        await session.rollback()
        raise project_http_error(exc) from exc


@router.post(
    "/{project_id}/guides/{guide_id}/submission-artifact-policies",
    response_model=SubmissionArtifactPolicyResponse,
    status_code=201,
    openapi_extra={
        "x-workstream-action-id": ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE.value
    },
)
async def create_submission_artifact_policy(
    project_id: UUID,
    guide_id: UUID,
    payload: SubmissionArtifactPolicyCreate,
    authorization: Annotated[
        tuple[UUID, ResolvedActor, PreparedAuthorizationService],
        Depends(submission_policy_authorization),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionArtifactPolicyResponse:
    """Create one governed manual submission-policy draft."""
    key, resolved, prepared = authorization
    try:
        outcome = await SubmissionPolicyMutationService(session).create_manual(
            resolved, prepared, key, project_id, guide_id, payload
        )
        await (session.rollback() if outcome.replayed else session.commit())
        return outcome.response
    except SubmissionPolicyMutationConflict as exc:
        await session.rollback()
        raise submission_policy_conflict_error(str(exc)) from exc
    except ProjectServiceError as exc:
        await session.rollback()
        raise project_http_error(exc) from exc


@router.patch(
    "/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}",
    response_model=SubmissionArtifactPolicyResponse,
    openapi_extra={
        "x-workstream-action-id": ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE.value
    },
)
async def update_submission_artifact_policy(
    project_id: UUID,
    guide_id: UUID,
    policy_id: UUID,
    payload: SubmissionArtifactPolicyUpdate,
    authorization: Annotated[
        tuple[UUID, ResolvedActor, PreparedAuthorizationService],
        Depends(submission_policy_authorization),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionArtifactPolicyResponse:
    """Append an authorized replacement for one manual draft policy."""
    key, resolved, prepared = authorization
    try:
        outcome = await SubmissionPolicyMutationService(session).update_manual(
            resolved, prepared, key, project_id, guide_id, policy_id, payload
        )
        await (session.rollback() if outcome.replayed else session.commit())
        return outcome.response
    except SubmissionPolicyMutationConflict as exc:
        await session.rollback()
        raise submission_policy_conflict_error(str(exc)) from exc
    except ProjectServiceError as exc:
        await session.rollback()
        raise project_http_error(exc) from exc


@router.get(
    "/{project_id}/guides/{guide_id}/effective-submission-artifact-policy",
    response_model=EffectiveProjectSubmissionArtifactPolicyResponse,
    openapi_extra={
        "x-workstream-action-id": (ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ.value)
    },
    dependencies=[Depends(enforce_human_authorization_read)],
)
async def get_current_effective_submission_artifact_policy(
    project_id: str,
    guide_id: str,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EffectiveProjectSubmissionArtifactPolicyResponse:
    """Return the current effective submission artifact policy for a guide."""
    policy = await authorize_project_policy_read(
        authorization=authorization,
        repository=ProjectRepository(session),
        action_id=ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
        project_id=project_id,
        guide_id=guide_id,
    )
    response = EffectiveProjectSubmissionArtifactPolicyResponse.model_validate(policy)
    await session.commit()
    return response


@router.get(
    "/{project_id}/guides/{guide_id}/pre-submit-checker-policy",
    response_model=PreSubmitCheckerPolicySummaryResponse,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ.value},
    dependencies=[Depends(enforce_human_authorization_read)],
)
async def get_current_pre_submit_checker_policy(
    project_id: str,
    guide_id: str,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreSubmitCheckerPolicySummaryResponse:
    """Return the current project pre-submit checker policy summary."""
    policy = await authorize_project_policy_read(
        authorization=authorization,
        repository=ProjectRepository(session),
        action_id=ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
        project_id=project_id,
        guide_id=guide_id,
    )
    response = PreSubmitCheckerPolicySummaryResponse.model_validate(policy)
    await session.commit()
    return response








@router.get(
    "/{project_id}/active-guide",
    response_model=ActiveGuideReadResponse,
    openapi_extra={"x-workstream-action-id": ActionId.PROJECT_ACTIVE_GUIDE_READ.value},
    dependencies=[Depends(enforce_human_authorization_read)],
)
async def get_active_guide(
    project_id: str,
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ActiveGuideReadResponse:
    """Return the current active guide and policy context for a project."""
    project_service = ProjectService(session)
    bundle = await authorize_project_active_guide_read(
        authorization=authorization,
        repository=ProjectRepository(session),
        project_service=project_service,
        project_id=project_id,
    )
    response = await project_service.active_guide_read_response(
        bundle.guide,
        bundle.source_snapshot,
        bundle.source_items,
        bundle.sufficiency_report,
        bundle.submission_artifact_policy,
        bundle.effective_policy,
        bundle.pre_submit_checker_policy,
        bundle.post_submit_checker_policy,
        bundle.review_policy,
        bundle.revision_policy,
    )
    await session.commit()
    return response
