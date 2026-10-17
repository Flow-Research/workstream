"""The one read runner every Project Manager and Finance project read composes.

Each response reads one REPEATABLE READ snapshot: the AUTH decision first,
then only the authorized project's owner rows, then response validation, then
the commit that keeps the decision evidence. AUTH denials are not caught here:
the decision owner restages and conceals them.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.authorization import get_authorization_actor_identity, get_authorization_service
from app.api.deps.snapshot_reads import run_snapshot_read, start_read_snapshot
from app.core.api_controls import StructuredHTTPException
from app.db.session import get_db_session
from app.modules.authorization.api import ActorIdentityFacts
from app.modules.authorization.api.management_reads import (
    ProjectManagementReadAction, ProjectManagementReadAuthorizationPort, ProjectManagementReadCursorInvalid,
    ProjectManagementReadGrant, ProjectManagementReadPosition, ProjectManagementReadRequest,
    ProjectManagementReadUnavailable,
)

READ_FAULTS = (ProjectManagementReadUnavailable, SQLAlchemyError, ValueError)


def project_read_unavailable() -> StructuredHTTPException:
    """The retryable failure for any infrastructure or integrity fault."""
    return StructuredHTTPException(
        status_code=503, detail="Project read unavailable", error_code="project_read_unavailable",
        error_message="Project read unavailable", retryable=True,
    )


def _cursor_invalid() -> StructuredHTTPException:
    """A malformed, forged or substituted continuation."""
    return StructuredHTTPException(
        status_code=422, detail="Invalid project read cursor", error_code="project_read_cursor_invalid",
        error_message="Invalid project read cursor",
    )


def _missing() -> StructuredHTTPException:
    """The concealed not-found response shared with the AUTH denial."""
    return StructuredHTTPException(
        status_code=404, detail="Project authorization resource not found",
        error_code="project_authorization_resource_not_found",
        error_message="Project authorization resource not found",
    )


class ProjectManagementReadRunner:
    """Authorize once, read the owner rows in the same snapshot, validate, then commit evidence."""

    def __init__(
        self, session: AsyncSession, actor_id: UUID, authority: ProjectManagementReadAuthorizationPort,
    ) -> None:
        """Bind the request session, the caller and the AUTH decision port."""
        self._session, self._actor_id, self._authority = session, actor_id, authority

    def request(
        self, action: ProjectManagementReadAction, project_id: UUID, query: dict, *,
        resource_id: UUID | None = None, cursor: str | None = None,
    ) -> ProjectManagementReadRequest:
        """Bind the action, caller, project, selected record and canonical filters into one AUTH request."""
        return ProjectManagementReadRequest(
            action=action, actor_profile_id=self._actor_id, project_id=project_id,
            resource_id=resource_id or project_id, query=tuple(sorted(query.items())), presented_cursor=cursor,
        )

    def next_cursor(self, request: ProjectManagementReadRequest, more: bool, timestamp, record_id) -> str | None:
        """Sign the last row's position only when another page exists."""
        if not more:
            return None
        return self._authority.encode(request, ProjectManagementReadPosition(timestamp, record_id))

    @staticmethod
    def position(grant: ProjectManagementReadGrant):
        """The verified keyset boundary, if a cursor was presented."""
        return None if grant.position is None else (grant.position.timestamp, grant.position.record_id)

    async def snapshot(self) -> None:
        """Start the one REPEATABLE READ snapshot every statement of this response reads."""
        await start_read_snapshot(self._session)

    async def authorize(self, request: ProjectManagementReadRequest) -> ProjectManagementReadGrant:
        """Record the decision inside the open snapshot; a denial propagates for concealment."""
        try:
            return await self._authority.authorize(request)
        except ProjectManagementReadCursorInvalid as exc:
            await self._session.rollback()
            raise _cursor_invalid() from exc

    async def commit(self) -> None:
        """Keep the decision evidence and end the snapshot."""
        await self._session.commit()

    async def rollback(self) -> None:
        """Discard the snapshot after a fault."""
        await self._session.rollback()

    async def conceal(self) -> StructuredHTTPException:
        """Commit the allowed decision, then answer as if the record did not exist."""
        await self._session.commit()
        return _missing()

    async def run(self, request: ProjectManagementReadRequest, read, *, faults: tuple[type[Exception], ...] = ()):
        """One bounded read; owner faults named by the caller map to the retryable 503."""
        return await run_snapshot_read(
            self._session, lambda: self._authority.authorize(request), read,
            cursor_invalid=ProjectManagementReadCursorInvalid, invalid_cursor=_cursor_invalid,
            faults=(*READ_FAULTS, *faults), unavailable=project_read_unavailable,
        )


async def get_project_management_read_runner(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: Annotated[ActorIdentityFacts, Depends(get_authorization_actor_identity)],
    authority: Annotated[object, Depends(get_authorization_service)],
) -> ProjectManagementReadRunner:
    """Build the runner from the request-scoped kernel and the configured cursor secret."""
    from app.adapters.auth import project_management_read_authorization

    return ProjectManagementReadRunner(session, actor.actor_profile_id, project_management_read_authorization(
        authority, request.app.state.settings.pagination_cursor_hmac_secret,
    ))


ProjectManagementReads = Annotated[ProjectManagementReadRunner, Depends(get_project_management_read_runner)]
