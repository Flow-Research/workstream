"""Hidden Operator HTTP surfaces for provider-neutral artifact diagnosis."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.interfaces.artifact_operations import (
    ArtifactAuditResourceType,
    ArtifactBindingResourceType,
    ArtifactOperatorRecoveryPort,
    ArtifactRecoveryRequest,
)
from app.modules.artifacts.authorization import get_artifact_authorization_context
from app.modules.artifacts.operator import (
    ArtifactOperatorEvidenceError,
    ArtifactOperatorInputError,
    ArtifactOperatorNotFound,
    ArtifactOperatorService,
    artifact_provider_readiness,
)
from app.modules.artifacts.metrics import artifact_admission_metrics
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    ArtifactOperatorAuthority,
    ArtifactRecoveryAuthority,
    ArtifactRecoveryConflictError,
    ArtifactRecoveryIneligibleError,
    ArtifactRecoveryNotFoundError,
    DenyArtifactOperatorAuthority,
    DenyArtifactRecoveryAuthority,
)
from app.modules.artifacts.service import ArtifactRecoveryService
from app.modules.authorization.runtime import AuthorizationContext

router = APIRouter(prefix="/operator/artifacts", tags=["operator-artifacts"])


class StrictOperatorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactBindingResponse(StrictOperatorResponse):
    id: UUID
    content_id: UUID
    project_id: UUID
    resource_type: ArtifactBindingResourceType
    resource_id: str
    logical_role: str
    scope_version: int
    supersedes_binding_id: UUID | None
    created_at: datetime


class ArtifactReplicaResponse(StrictOperatorResponse):
    id: UUID
    content_id: UUID
    verification_state: str
    availability_state: str
    integrity_state: str
    last_reconciled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ArtifactReceiptResponse(StrictOperatorResponse):
    id: UUID
    receipt_type: Literal["put", "put_observation", "verification"]
    replica_id: UUID
    outcome: str
    replayed: bool | None = None
    attempt_number: int | None = None
    execution_generation: int | None = None
    verification_job_id: UUID | None = None
    created_at: datetime


class ArtifactVerificationJobResponse(StrictOperatorResponse):
    id: UUID
    replica_id: UUID
    parent_verification_job_id: UUID | None
    status: str
    attempt_count: int
    maximum_attempts: int
    next_run_at: datetime | None
    cas_version: int
    terminal_result_code: str | None
    terminal_at: datetime | None
    receipt_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ArtifactRecoveryAttemptResponse(StrictOperatorResponse):
    id: UUID
    project_id: UUID
    task_id: UUID | None
    submission_id: UUID | None
    source_verification_job_id: UUID
    source_verification_job_status: str
    retry_verification_job_id: UUID
    retry_verification_job_status: str
    parent_recovery_attempt_id: UUID | None
    status: str
    terminal_result_code: str | None
    initiation_audit_event_id: UUID
    terminal_audit_event_id: UUID | None
    cas_version: int
    created_at: datetime
    terminal_at: datetime | None
    updated_at: datetime


class ArtifactAuditEventResponse(StrictOperatorResponse):
    id: UUID
    entity_type: ArtifactAuditResourceType
    entity_id: UUID
    event_type: str
    from_status: str | None
    to_status: str | None
    reason: str | None
    occurred_at: datetime | None
    created_at: datetime
    request_id: UUID | None
    correlation_id: UUID | None


class ArtifactAdmissionUsageResponse(StrictOperatorResponse):
    scope_type: Literal["deployment", "project", "task"]
    scope_id: str
    counted_bytes: int
    limit_bytes: int
    remaining_bytes: int
    configured_limit_bytes: int
    cas_version: int
    updated_at: datetime


PageItem = TypeVar("PageItem", bound=StrictOperatorResponse)


class OperatorPageResponse(StrictOperatorResponse, Generic[PageItem]):
    items: list[PageItem]
    next_cursor: str | None = None


class ArtifactRecoveryCreateRequest(StrictOperatorResponse):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    project_id: UUID
    task_id: UUID | None = None
    submission_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=1000)
    client_idempotency_key: str = Field(min_length=1, max_length=200)
    expected_source_job_cas_version: int = Field(ge=0)


class ArtifactRecoveryCreateResponse(StrictOperatorResponse):
    recovery_attempt_id: UUID
    source_verification_job_id: UUID
    retry_verification_job_id: UUID
    replayed: bool


class ArtifactReadinessResponse(StrictOperatorResponse):
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


def get_artifact_recovery_port(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactRecoveryAuthority, Depends(get_artifact_recovery_authority)],
) -> ArtifactOperatorRecoveryPort:
    """Compose the approved recovery port without a second factory path."""
    return ArtifactRecoveryService(session, request.app.state.settings, authority)


def _service(
    request: Request,
    session: AsyncSession,
    authority: ArtifactOperatorAuthority,
) -> ArtifactOperatorService:
    return ArtifactOperatorService(
        session, authority, request.app.state.settings, artifact_admission_metrics
    )


def _concealed(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Artifact resource not found"
    )


def _page(result) -> dict[str, object]:
    return {"items": list(result.items), "next_cursor": result.next_cursor}


@router.get("/bindings", response_model=OperatorPageResponse[ArtifactBindingResponse])
async def list_artifact_bindings(
    request: Request,
    resource_type: ArtifactBindingResourceType,
    resource_id: UUID,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
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
    except ArtifactOperatorInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/contents/{content_id}/replicas",
    response_model=OperatorPageResponse[ArtifactReplicaResponse],
)
async def list_artifact_replicas(
    content_id: UUID,
    request: Request,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
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
    except ArtifactOperatorInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/replicas/{replica_id}/receipts",
    response_model=OperatorPageResponse[ArtifactReceiptResponse],
    response_model_exclude_none=True,
)
async def list_artifact_receipts(
    replica_id: UUID,
    request: Request,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
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
    except ArtifactOperatorInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/verification-jobs/{verification_job_id}",
    response_model=ArtifactVerificationJobResponse,
)
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
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    recovery: Annotated[ArtifactOperatorRecoveryPort, Depends(get_artifact_recovery_port)],
) -> ArtifactRecoveryCreateResponse:
    try:
        result = await recovery.retry_verification(
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
    except ArtifactRecoveryNotFoundError as exc:
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


@router.get(
    "/recovery-attempts/{recovery_attempt_id}",
    response_model=ArtifactRecoveryAttemptResponse,
)
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


@router.get("/audit-events", response_model=OperatorPageResponse[ArtifactAuditEventResponse])
async def list_artifact_audit_events(
    request: Request,
    resource_type: ArtifactAuditResourceType,
    resource_id: UUID,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
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


@router.get(
    "/admission-usage",
    response_model=OperatorPageResponse[ArtifactAdmissionUsageResponse],
)
async def get_artifact_admission_usage(
    request: Request,
    project_id: UUID,
    context: Annotated[AuthorizationContext, Depends(get_artifact_authorization_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[ArtifactOperatorAuthority, Depends(get_artifact_operator_authority)],
    task_id: UUID | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
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
