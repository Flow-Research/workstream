"""Typed authority and cursor seam for Project Manager and Finance project-wide reads."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

ProjectManagementReadAction = Literal[
    "project.guide.list", "project.guide.read", "project.guide.activation_readiness.read",
    "project.guide.document.read", "project.submission.list", "project.assignment.list",
    "project.summary.read", "project.task.import_batch.list",
    "project.submission_bundle_preparation.list", "contribution.policy.list",
]
_ACTIONS = frozenset(ProjectManagementReadAction.__args__)
# Single-record and summary reads take no continuation.
UNPAGED_MANAGEMENT_READ_ACTIONS = frozenset({
    "project.guide.read", "project.guide.activation_readiness.read", "project.guide.document.read",
    "project.summary.read",
})
JsonQueryValue = str | int | None


@dataclass(frozen=True, slots=True)
class ProjectManagementReadRequest:
    """The caller, the exact project and resource, and the normalized query.

    Collection and summary reads use the project as ``resource_id``. Guide and
    guide-document reads name the selected guide or document; its owner proves
    it belongs to ``project_id`` after the decision and conceals it otherwise.
    """

    action: ProjectManagementReadAction
    actor_profile_id: UUID
    project_id: UUID
    resource_id: UUID
    query: tuple[tuple[str, JsonQueryValue], ...]
    presented_cursor: str | None = None

    def __post_init__(self):
        """Reject a request whose action, scope or query is not canonical."""
        if (
            self.action not in _ACTIONS or not isinstance(self.actor_profile_id, UUID)
            or not isinstance(self.project_id, UUID) or not isinstance(self.resource_id, UUID)
            or not isinstance(self.query, tuple)
            or any(not isinstance(key, str) or not isinstance(value, (str, int, type(None)))
                   for key, value in self.query)
            or len({key for key, _ in self.query}) != len(self.query)
            or (self.presented_cursor is not None and (
                not isinstance(self.presented_cursor, str) or len(self.presented_cursor) > 512
                or self.action in UNPAGED_MANAGEMENT_READ_ACTIONS))
        ):
            raise ValueError("invalid project management read request")


@dataclass(frozen=True, slots=True)
class ProjectManagementReadPosition:
    """A verified keyset boundary; not authority."""

    timestamp: datetime
    record_id: UUID

    def __post_init__(self):
        """Reject a position without both an aware timestamp and a record ID."""
        if (not isinstance(self.record_id, UUID) or not isinstance(self.timestamp, datetime)
                or self.timestamp.utcoffset() is None):
            raise ValueError("invalid project management read position")


@dataclass(frozen=True, slots=True)
class ProjectManagementReadGrant:
    """The authorized project, the decoded position and the award-total disclosure.

    ``award_totals_visible`` is true only for a project summary read whose
    caller also holds a current exact-project Finance Authority grant.
    """

    project_id: UUID
    position: ProjectManagementReadPosition | None
    award_totals_visible: bool = False


class ProjectManagementReadCursorInvalid(ValueError):
    """Malformed, forged or substituted continuation."""


class ProjectManagementReadUnavailable(RuntimeError):
    """Required cursor configuration is unavailable."""


class ProjectManagementReadAuthorizationPort(Protocol):
    """Live authority precedes cursor verification on every page."""

    async def authorize(self, request: ProjectManagementReadRequest) -> ProjectManagementReadGrant:
        """Decide the read and validate any presented cursor against it."""
        ...

    def encode(self, request: ProjectManagementReadRequest, position: ProjectManagementReadPosition) -> str:
        """Sign the next position for exactly this request."""
        ...
