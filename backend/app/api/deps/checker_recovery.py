"""HTTP transaction roots for exact Operator checker recovery."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.checkers import checker_retry_service, post_submit_delivery_service
from app.api.deps.auth import get_auth_verification_result
from app.api.deps.authorization import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    ResolvedActor,
    _authorization_context,
    get_authorization_actor,
)
from app.core.api_controls import StructuredHTTPException, parse_idempotency_key, request_ids
from app.db.session import get_db_session, get_session_factory
from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitDeliveryAuthorityDenied,
    PostSubmitDeliveryCommand,
    PostSubmitDeliveryConflict,
    PostSubmitDeliveryCursorInvalid,
    PostSubmitDeliveryOperationUnavailable,
    PostSubmitDeliveryPage,
    PostSubmitDeliveryQuery,
    PostSubmitDeliveryRequest,
    PostSubmitDeliveryResult,
    PostSubmitDeliveryUnavailable,
)
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable,
    CheckerRequestConflict,
    CheckerRetryAuthorityDenied,
    CheckerRetryCommand,
    CheckerRetryCursorInvalid,
    CheckerRetryOperationUnavailable,
    CheckerRetryRequest,
    CheckerRetryResult,
    CheckerRetrySourceUnavailable,
    CheckerRetrySourcePage,
    CheckerRetrySourceQuery,
)
from app.schemas.auth import AuthVerificationResult


def require_checker_retry_key(request: Request) -> UUID:
    """Reject absent, duplicate or malformed retry keys before product mutation."""
    values = request.headers.getlist("Idempotency-Key")
    return parse_idempotency_key(values[0] if len(values) == 1 else "")


def require_post_submit_delivery_key(request: Request) -> UUID:
    """Reject absent, duplicate or malformed reconciliation keys before lookup."""
    values = request.headers.getlist("Idempotency-Key")
    return parse_idempotency_key(values[0] if len(values) == 1 else "")


async def require_checker_retry_human(
    key: Annotated[UUID, Depends(require_checker_retry_key)],
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
) -> None:
    """Conceal nonhuman retry callers before resolving product dependencies."""
    del key
    if result.token.subject_kind != "human":
        raise _concealed()


async def require_post_submit_delivery_human(
    key: Annotated[UUID, Depends(require_post_submit_delivery_key)],
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
) -> None:
    """Conceal nonhuman mutation callers before product or delivery lookup."""
    del key
    if result.token.subject_kind != "human":
        raise _delivery_concealed()


def _concealed() -> StructuredHTTPException:
    return StructuredHTTPException(
        status_code=404,
        detail="Checker recovery source not found",
        error_code="checker_recovery_source_not_found",
        error_message="Checker recovery source not found",
    )


def _unavailable() -> StructuredHTTPException:
    return StructuredHTTPException(
        status_code=503,
        detail="Checker recovery unavailable",
        error_code="checker_recovery_unavailable",
        error_message="Checker recovery unavailable",
        retryable=True,
    )


def _delivery_concealed() -> StructuredHTTPException:
    return StructuredHTTPException(
        status_code=404,
        detail="Post-submit delivery not found",
        error_code="post_submit_delivery_not_found",
        error_message="Post-submit delivery not found",
    )


def _delivery_unavailable() -> StructuredHTTPException:
    return StructuredHTTPException(
        status_code=503,
        detail="Post-submit delivery reconciliation unavailable",
        error_code="post_submit_delivery_reconciliation_unavailable",
        error_message="Post-submit delivery reconciliation unavailable",
        retryable=True,
    )


class CheckerRetryCommands:
    """Bind the public selector/body to CHECKERS's existing atomic writer."""

    def __init__(self, session: AsyncSession, service, key: UUID) -> None:
        self._session, self._service, self._key = session, service, key

    async def retry(
        self, project_id: UUID, source_run_id: UUID, request: CheckerRetryRequest,
    ) -> CheckerRetryResult:
        result = await self._service.retry(CheckerRetryCommand(
            project_id=project_id,
            source_run_id=source_run_id,
            request_key=self._key,
            reason=request.reason,
        ))
        await self._session.commit()
        return result


class CheckerRetryReads:
    """Authorize, project and commit one exact discovery page."""

    def __init__(self, session: AsyncSession, service) -> None:
        self._session, self._service = session, service

    async def discover(
        self, project_id: UUID, *, limit: int, cursor: str | None,
    ) -> CheckerRetrySourcePage:
        result = await self._service.discover(CheckerRetrySourceQuery(
            project_id=project_id, limit=limit, cursor=cursor,
        ))
        await self._session.commit()
        return result


class PostSubmitDeliveryCommands:
    """Bind one public selector/body to the exact reconciliation child append."""

    def __init__(self, session, service, key, actor_profile_id) -> None:
        self._session, self._service = session, service
        self._key, self._actor_profile_id = key, actor_profile_id

    async def reconcile(self, project_id, event_id, payload):
        checked = PostSubmitDeliveryRequest.model_validate(payload)
        result = await self._service.reconcile(
            PostSubmitDeliveryCommand(
                actor_profile_id=self._actor_profile_id,
                project_id=project_id,
                event_id=event_id,
                request_key=self._key,
                reason=checked.reason,
                action=checked.action,
            )
        )
        await self._session.commit()
        return PostSubmitDeliveryResult.model_validate(result)


class PostSubmitDeliveryReads:
    """Authorize, classify and commit one project-bound UNKNOWN page."""

    def __init__(self, session, service) -> None:
        self._session, self._service = session, service

    async def discover(self, project_id, *, limit, cursor):
        result = await self._service.discover(
            PostSubmitDeliveryQuery(
                project_id=project_id, limit=limit, cursor=cursor,
            )
        )
        response = PostSubmitDeliveryPage.model_validate(result)
        await self._session.commit()
        return response


@asynccontextmanager
async def _checker_retry_commands(
    request: Request,
    key: UUID,
    resolved: ResolvedActor,
    session: AsyncSession,
) -> AsyncIterator[CheckerRetryCommands]:
    """Own mutation commit, canonical denial evidence and fail-closed rollback."""
    context = _authorization_context(resolved, key, key)
    await session.rollback()
    service = checker_retry_service(
        session,
        context,
        cursor_secret=request.app.state.settings.pagination_cursor_hmac_secret,
    )
    try:
        await session.begin()
        yield CheckerRetryCommands(session, service, key)
    except CheckerRetryAuthorityDenied as exc:
        await session.rollback()
        try:
            if await service.restage_denial(exc):
                await session.commit()
        except (AuthorizationEvidenceUnavailable, SQLAlchemyError) as evidence_error:
            await session.rollback()
            raise _unavailable() from evidence_error
        raise _concealed() from exc
    except CheckerRequestConflict as exc:
        await session.rollback()
        raise StructuredHTTPException(
            status_code=409,
            detail="Checker retry request conflicts with retained facts",
            error_code="checker_retry_request_conflict",
            error_message="Checker retry request conflicts with retained facts",
        ) from exc
    except CheckerRetrySourceUnavailable as exc:
        await session.rollback()
        raise _concealed() from exc
    except (
        CheckerRetryOperationUnavailable,
        AuthorizationEvidenceUnavailable,
        SQLAlchemyError,
    ) as exc:
        await session.rollback()
        raise _unavailable() from exc
    except BaseException:
        await session.rollback()
        raise
    finally:
        if session.in_transaction():
            await session.rollback()


async def get_checker_retry_commands(
    request: Request,
    key: Annotated[UUID, Depends(require_checker_retry_key)],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CheckerRetryCommands]:
    """Forward endpoint failures through the mutation transaction owner."""
    async with _checker_retry_commands(request, key, resolved, session) as commands:
        yield commands


async def get_checker_retry_reads(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CheckerRetryReads]:
    """Own read decision commit and canonical concealed denial evidence."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    await session.rollback()
    service = checker_retry_service(
        session,
        context,
        cursor_secret=request.app.state.settings.pagination_cursor_hmac_secret,
    )
    try:
        yield CheckerRetryReads(session, service)
    except AuthorizationDenied as exc:
        await session.rollback()
        try:
            if await service.restage_discovery_denial(exc):
                await session.commit()
        except (AuthorizationEvidenceUnavailable, SQLAlchemyError) as evidence_error:
            await session.rollback()
            raise _unavailable() from evidence_error
        raise _concealed() from exc
    except CheckerRetryCursorInvalid as exc:
        await session.rollback()
        raise StructuredHTTPException(
            status_code=422,
            detail="Invalid checker recovery cursor",
            error_code="validation_error",
            error_message="Invalid checker recovery cursor",
        ) from exc
    except (CheckerExecutionUnavailable, AuthorizationEvidenceUnavailable, SQLAlchemyError) as exc:
        await session.rollback()
        raise _unavailable() from exc
    except BaseException:
        await session.rollback()
        raise
    finally:
        if session.in_transaction():
            await session.rollback()


@asynccontextmanager
async def _post_submit_delivery_commands(request, key, resolved, session):
    """Own child append commit, denial restaging and exact public mappings."""
    context = _authorization_context(resolved, key, key)
    await session.rollback()
    service = post_submit_delivery_service(
        session,
        get_session_factory(),
        context,
        cursor_secret=request.app.state.settings.pagination_cursor_hmac_secret,
    )
    try:
        await session.begin()
        yield PostSubmitDeliveryCommands(
            session, service, key, context.actor_profile_id
        )
    except PostSubmitDeliveryAuthorityDenied as exc:
        await session.rollback()
        try:
            if await service.restage_denial(exc):
                await session.commit()
        except (AuthorizationEvidenceUnavailable, SQLAlchemyError) as evidence_error:
            await session.rollback()
            raise _delivery_unavailable() from evidence_error
        raise _delivery_concealed() from exc
    except PostSubmitDeliveryConflict as exc:
        await session.rollback()
        raise StructuredHTTPException(
            status_code=409,
            detail="Post-submit delivery request conflicts with retained facts",
            error_code="post_submit_delivery_request_conflict",
            error_message="Post-submit delivery request conflicts with retained facts",
        ) from exc
    except PostSubmitDeliveryUnavailable as exc:
        await session.rollback()
        raise _delivery_concealed() from exc
    except (
        PostSubmitDeliveryOperationUnavailable,
        AuthorizationEvidenceUnavailable,
        SQLAlchemyError,
    ) as exc:
        await session.rollback()
        raise _delivery_unavailable() from exc
    except BaseException:
        await session.rollback()
        raise
    finally:
        if session.in_transaction():
            await session.rollback()


async def get_post_submit_delivery_commands(
    request: Request,
    key: Annotated[UUID, Depends(require_post_submit_delivery_key)],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[PostSubmitDeliveryCommands]:
    """Forward endpoint exceptions through the mutation transaction owner."""
    async with _post_submit_delivery_commands(
        request, key, resolved, session
    ) as commands:
        yield commands


async def get_post_submit_delivery_reads(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[PostSubmitDeliveryReads]:
    """Own read decision commit and canonical denial evidence."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    await session.rollback()
    service = post_submit_delivery_service(
        session,
        get_session_factory(),
        context,
        cursor_secret=request.app.state.settings.pagination_cursor_hmac_secret,
    )
    try:
        yield PostSubmitDeliveryReads(session, service)
    except AuthorizationDenied as exc:
        await session.rollback()
        try:
            if await service.restage_read_denial(exc):
                await session.commit()
        except (AuthorizationEvidenceUnavailable, SQLAlchemyError) as evidence_error:
            await session.rollback()
            raise _delivery_unavailable() from evidence_error
        raise _delivery_concealed() from exc
    except PostSubmitDeliveryCursorInvalid as exc:
        await session.rollback()
        raise StructuredHTTPException(
            status_code=422,
            detail="Invalid post-submit delivery cursor",
            error_code="validation_error",
            error_message="Invalid post-submit delivery cursor",
        ) from exc
    except (
        PostSubmitDeliveryOperationUnavailable,
        AuthorizationEvidenceUnavailable,
        SQLAlchemyError,
    ) as exc:
        await session.rollback()
        raise _delivery_unavailable() from exc
    except BaseException:
        await session.rollback()
        raise
    finally:
        if session.in_transaction():
            await session.rollback()
