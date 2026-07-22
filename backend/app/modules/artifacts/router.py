"""Hidden Operator HTTP surfaces for provider-neutral artifact diagnosis."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.authorization import (
    _authorization_context,
    get_authorization_actor,
)
from app.core.api_controls import request_ids
from app.db.session import get_db_session
from app.interfaces.artifact_operations import (
    ArtifactAuditResourceType,
    ArtifactBindingResourceType,
    ArtifactRecoveryRequest,
)
from app.modules.actors.service import ResolvedActor
from app.modules.artifacts.operator import (
    ArtifactOperatorEvidenceError,
    ArtifactOperatorInputError,
    ArtifactOperatorNotFound,
    ArtifactOperatorService,
    InProcessArtifactAdmissionMetrics,
    artifact_provider_readiness,
)
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    ArtifactOperatorAuthority,
    ArtifactRecoveryAuthority,
    ArtifactRecoveryAuthorityFacts,
    ArtifactRecoveryConflictError,
    ArtifactRecoveryIneligibleError,
    DenyArtifactOperatorAuthority,
    DenyArtifactRecoveryAuthority,
)
from app.modules.artifacts.service import ArtifactRecoveryService
from app.modules.authorization.runtime import AuthorizationContext
from app.modules.authorization.catalogue import ActionId, PermissionId

router = APIRouter(prefix="/operator/artifacts", tags=["operator-artifacts"])
_metrics = InProcessArtifactAdmissionMetrics()


class OperatorPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[dict[str, Any]]
    next_cursor: str | None = None


class ArtifactRecoveryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    project_id: UUID
    task_id: UUID | None = None
    submission_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=1000)
    client_idempotency_key: str = Field(min_length=1, max_length=200)
    expected_source_job_cas_version: int = Field(ge=0)


class ArtifactRecoveryCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recovery_attempt_id: UUID
    source_verification_job_id: UUID
    retry_verification_job_id: UUID
    replayed: bool


class ArtifactReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: str
    provider_profile: str | None
    configured: bool
    active: bool
    status: str
    prerequisites: dict[str, bool]


def get_artifact_operator_authority() -> ArtifactOperatorAuthority:
    """Keep every Operator read unavailable until AUTH activation."""
    return DenyArtifactOperatorAuthority()


def get_artifact_recovery_authority() -> ArtifactRecoveryAuthority:
    """Keep retry unavailable until its independent AUTH activation."""
    return DenyArtifactRecoveryAuthority()


async def get_artifact_authorization_context(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
) -> AuthorizationContext:
    """Project the request's canonical actor rows into exact authority facts."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    return _authorization_context(resolved, request_id, correlation_id)


def _service(
    request: Request,
    session: AsyncSession,
    authority: ArtifactOperatorAuthority,
) -> ArtifactOperatorService:
    return ArtifactOperatorService(session, authority, request.app.state.settings, _metrics)


def _concealed(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Artifact resource not found"
    )


def _page(result) -> OperatorPageResponse:
    return OperatorPageResponse(items=list(result.items), next_cursor=result.next_cursor)


@router.get("/bindings", response_model=OperatorPageResponse)
async def list_artifact_bindings(
    request: Request,
    resource_type: ArtifactBindingResourceType,
    resource_id: UUID,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> OperatorPageResponse:
    try:
        return _page(
            await _service(request, session, authority).list_bindings(
                authorization_context=context,
                resource_type=resource_type,
                resource_id=resource_id,
                cursor=cursor,
                limit=limit,
            )
        )
    except (
        ArtifactAuthorityDeniedError,
        ArtifactOperatorNotFound,
        ArtifactOperatorEvidenceError,
    ) as exc:
        raise _concealed(exc) from exc


@router.get("/contents/{content_id}/replicas", response_model=OperatorPageResponse)
async def list_artifact_replicas(
    content_id: UUID,
    request: Request,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> OperatorPageResponse:
    try:
        return _page(
            await _service(request, session, authority).list_replicas(
                authorization_context=context, content_id=content_id, cursor=cursor, limit=limit
            )
        )
    except (
        ArtifactAuthorityDeniedError,
        ArtifactOperatorNotFound,
        ArtifactOperatorEvidenceError,
    ) as exc:
        raise _concealed(exc) from exc


@router.get("/replicas/{replica_id}/receipts", response_model=OperatorPageResponse)
async def list_artifact_receipts(
    replica_id: UUID,
    request: Request,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> OperatorPageResponse:
    try:
        return _page(
            await _service(request, session, authority).list_receipts(
                authorization_context=context, replica_id=replica_id, cursor=cursor, limit=limit
            )
        )
    except (
        ArtifactAuthorityDeniedError,
        ArtifactOperatorNotFound,
        ArtifactOperatorEvidenceError,
    ) as exc:
        raise _concealed(exc) from exc


@router.get("/verification-jobs/{verification_job_id}")
async def get_artifact_verification_job(
    verification_job_id: UUID,
    request: Request,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
) -> dict[str, object]:
    try:
        return await _service(request, session, authority).get_verification_job(
            authorization_context=context, verification_job_id=verification_job_id
        )
    except (
        ArtifactAuthorityDeniedError,
        ArtifactOperatorNotFound,
        ArtifactOperatorEvidenceError,
    ) as exc:
        raise _concealed(exc) from exc


@router.post(
    "/verification-jobs/{verification_job_id}/retry",
    response_model=ArtifactRecoveryCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_artifact_verification(
    verification_job_id: UUID,
    payload: ArtifactRecoveryCreateRequest,
    request: Request,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactRecoveryAuthority, Depends(get_artifact_recovery_authority)],
) -> ArtifactRecoveryCreateResponse:
    try:
        preflight = await authority.authorize(
            authorization_context=context,
            facts=ArtifactRecoveryAuthorityFacts(
                project_id=payload.project_id,
                task_id=payload.task_id,
                submission_id=payload.submission_id,
                source_verification_job_id=verification_job_id,
                expected_source_job_cas_version=payload.expected_source_job_cas_version,
            ),
        )
        if (
            preflight.action_id is not ActionId.ARTIFACT_VERIFICATION_JOB_RETRY
            or preflight.permission_id != PermissionId.ARTIFACT_VERIFICATION_JOB_RETRY.value
        ):
            raise ArtifactAuthorityDeniedError("artifact recovery action is unavailable")
        result = await ArtifactRecoveryService(
            session, request.app.state.settings, authority
        ).create(
            ArtifactRecoveryRequest(
                authorization_context=context,
                project_id=payload.project_id,
                task_id=payload.task_id,
                submission_id=payload.submission_id,
                source_verification_job_id=verification_job_id,
                reason=payload.reason,
                client_idempotency_key=payload.client_idempotency_key,
                expected_source_job_cas_version=payload.expected_source_job_cas_version,
            )
        )
        return ArtifactRecoveryCreateResponse(
            recovery_attempt_id=result.recovery_attempt_id,
            source_verification_job_id=result.source_verification_job_id,
            retry_verification_job_id=result.retry_verification_job_id,
            replayed=result.replayed,
        )
    except ArtifactAuthorityDeniedError as exc:
        raise _concealed(exc) from exc
    except ArtifactRecoveryConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ArtifactRecoveryIneligibleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid recovery request"
        ) from exc


@router.get("/recovery-attempts/{recovery_attempt_id}")
async def get_artifact_recovery_attempt(
    recovery_attempt_id: UUID,
    request: Request,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
) -> dict[str, object]:
    try:
        return await _service(request, session, authority).get_recovery_attempt(
            authorization_context=context, recovery_attempt_id=recovery_attempt_id
        )
    except (
        ArtifactAuthorityDeniedError,
        ArtifactOperatorNotFound,
        ArtifactOperatorEvidenceError,
    ) as exc:
        raise _concealed(exc) from exc


@router.get("/audit-events", response_model=OperatorPageResponse)
async def list_artifact_audit_events(
    request: Request,
    resource_type: ArtifactAuditResourceType,
    resource_id: UUID,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> OperatorPageResponse:
    try:
        return _page(
            await _service(request, session, authority).list_audit_events(
                authorization_context=context,
                resource_type=resource_type,
                resource_id=resource_id,
                cursor=cursor,
                limit=limit,
            )
        )
    except (
        ArtifactAuthorityDeniedError,
        ArtifactOperatorNotFound,
        ArtifactOperatorEvidenceError,
    ) as exc:
        raise _concealed(exc) from exc


@router.get("/admission-usage", response_model=OperatorPageResponse)
async def get_artifact_admission_usage(
    request: Request,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
    project_id: UUID | None = None,
    task_id: UUID | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> OperatorPageResponse:
    try:
        return _page(
            await _service(request, session, authority).admission_usage(
                authorization_context=context,
                project_id=project_id,
                task_id=task_id,
                cursor=cursor,
                limit=limit,
            )
        )
    except (
        ArtifactAuthorityDeniedError,
        ArtifactOperatorNotFound,
        ArtifactOperatorEvidenceError,
    ) as exc:
        raise _concealed(exc) from exc
    except ArtifactOperatorInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get("/readiness", response_model=ArtifactReadinessResponse)
async def get_artifact_readiness(
    request: Request,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
) -> ArtifactReadinessResponse:
    service = _service(request, session, authority)
    try:
        # Reuse the exact operations-status permission without querying mutable usage.
        await service.authorize_readiness(context)
    except (ArtifactAuthorityDeniedError, ArtifactOperatorEvidenceError) as exc:
        raise _concealed(exc) from exc
    return ArtifactReadinessResponse(**artifact_provider_readiness(request.app.state.settings))
