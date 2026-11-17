"""Typed authority and cursor seam for the caller's own grant and work reads."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

ContributorReadAction = Literal[
    "actor.project.list", "actor.assignment.list", "actor.submission.list",
    "actor.work_summary.read", "task.submission_bundle_preparation.list",
    "task.submission_bundle_preparation.read", "task.submission_operation.read",
]
_ACTIONS = frozenset(ContributorReadAction.__args__)
JsonQueryValue = str | int | None


@dataclass(frozen=True, slots=True)
class ContributorReadRequest:
    """The caller, its exact resource and normalized query, before any cursor parse.

    Actor-wide reads use the caller as ``resource_id`` and an optional
    ``scope_project_id`` filter. Task-scoped reads use the task or preparation
    and the project TASK resolved for the caller.
    """

    action: ContributorReadAction
    actor_profile_id: UUID
    resource_id: UUID
    scope_project_id: UUID | None
    query: tuple[tuple[str, JsonQueryValue], ...]
    presented_cursor: str | None = None

    def __post_init__(self):
        """Reject a request whose action, scope or query is not canonical."""
        if (
            self.action not in _ACTIONS or not isinstance(self.actor_profile_id, UUID)
            or not isinstance(self.resource_id, UUID)
            or (self.scope_project_id is not None and not isinstance(self.scope_project_id, UUID))
            or not isinstance(self.query, tuple)
            or any(not isinstance(key, str) or not isinstance(value, (str, int, type(None)))
                   for key, value in self.query)
            or len({key for key, _ in self.query}) != len(self.query)
            or (self.presented_cursor is not None and (
                not isinstance(self.presented_cursor, str) or len(self.presented_cursor) > 512))
        ):
            raise ValueError("invalid contributor read request")


@dataclass(frozen=True, slots=True)
class ContributorReadPosition:
    """A verified keyset boundary; not authority."""

    timestamp: datetime
    record_id: UUID

    def __post_init__(self):
        """Reject a position without both a timestamp and a record ID."""
        if (not isinstance(self.record_id, UUID) or not isinstance(self.timestamp, datetime)
                or self.timestamp.utcoffset() is None):
            raise ValueError("invalid contributor read position")


@dataclass(frozen=True, slots=True)
class ContributorReadGrant:
    """Projects whose own rows the caller may read now, and the decoded position."""

    project_ids: frozenset[UUID]
    position: ContributorReadPosition | None


@dataclass(frozen=True, slots=True)
class ActorProjectRoles:
    """The caller's effective admin and contributor role names on one project."""

    admin_roles: tuple[str, ...]
    project_roles: tuple[str, ...]


class ContributorReadCursorInvalid(ValueError):
    """Malformed, forged or substituted continuation."""


class ContributorReadUnavailable(RuntimeError):
    """Required cursor configuration is unavailable."""


class ContributorReadAuthorizationPort(Protocol):
    """Live authority precedes cursor verification on every page."""

    async def authorize(self, request: ContributorReadRequest) -> ContributorReadGrant:
        """Decide the read and validate any presented cursor against it."""
        ...

    def encode(self, request: ContributorReadRequest, position: ContributorReadPosition) -> str:
        """Sign the next position for exactly this request."""
        ...

    async def project_roles(
        self, actor_profile_id: UUID, project_ids: tuple[UUID, ...],
    ) -> dict[UUID, ActorProjectRoles]: ...
