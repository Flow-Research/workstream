"""Authenticated public policy composition and caller-owned transactions."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import Depends, Request
from pydantic import TypeAdapter
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth import contribution_policy_authorization
from app.adapters.contributions import contribution_policy_service
from app.api.deps.authorization import (
    _authorization_context, get_authorization_actor, get_authorization_actor_identity,
)
from app.core.api_controls import StructuredHTTPException, parse_idempotency_key, request_ids
from app.db.session import get_db_session
from app.modules.contributions.api import (
    ContributionPolicyConflict, ContributionPolicyOperationsPort,
    ContributionPolicyUnavailable,
)

IDEMPOTENCY_PARAMETER = {
    "name": "Idempotency-Key", "in": "header", "required": True,
    "schema": {"type": "string", "format": "uuid"},
}


def require_policy_key(request: Request) -> UUID:
    """Reject missing or duplicate keys before resolving actor/product composition."""
    values = request.headers.getlist("Idempotency-Key")
    return parse_idempotency_key(values[0] if len(values) == 1 else "")


@dataclass(frozen=True)
class PolicyRequest:
    """One authenticated actor and the existing transaction-bound CON owner."""

    session: AsyncSession
    service: ContributionPolicyOperationsPort
    actor_profile_id: UUID


def policy_http_error(status: int) -> StructuredHTTPException:
    """Return bounded errors without internal policy, binding or storage diagnostics."""
    code, message = {
        404: ("contribution_policy_not_found", "Contribution policy unavailable"),
        409: ("contribution_policy_conflict", "Contribution policy conflicts with current state"),
        503: ("contribution_policy_storage_unavailable", "Contribution policy storage unavailable"),
    }[status]
    return StructuredHTTPException(
        status_code=status, detail=code, error_code=code, error_message=message,
        retryable=status == 503,
    )


async def get_policy_request(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[PolicyRequest]:
    """Separate identity refresh from the sole CON operation transaction."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    actor = await get_authorization_actor_identity(resolved)
    await session.rollback()
    try:
        async with session.begin():
            authority = contribution_policy_authorization(session, context)
            yield PolicyRequest(session, contribution_policy_service(
                session, read_authorization=authority, mutation_authorization=authority,
            ), actor.actor_profile_id)
    except ContributionPolicyUnavailable as exc:
        raise policy_http_error(404) from exc
    except ContributionPolicyConflict as exc:
        raise policy_http_error(404 if str(exc) == "contribution_policy_not_found" else 409) from exc
    except SQLAlchemyError as exc:
        raise policy_http_error(503) from exc
    finally:
        if session.in_transaction():
            await session.rollback()


PolicyResponse = TypeVar("PolicyResponse")


async def commit_policy_response(
    request: PolicyRequest, response: PolicyResponse, response_type: type[PolicyResponse],
) -> PolicyResponse:
    """Validate detached output before committing lifecycle and authority together."""
    adapter = TypeAdapter(response_type)
    detached = adapter.validate_json(adapter.dump_json(response, warnings="error"))
    await request.session.commit()
    return detached
