"""Authorized creation of project-scoped compensation units.

A ContributionPolicy award definition may reference only an active
``ProjectCompensationUnit``. This owner creates such a unit for the
``project_points`` instrument under exact Finance Authority, records one
immutable creation event, and replays an identical request from that event.
Money units, unit retirement and any public route remain out of scope.
"""

from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.contributions.api import (
    CompensationUnitAction,
    CompensationUnitCreateAuthorizationFacts,
    CompensationUnitInstrument,
    ContributionPolicyConflict,
    ContributionPolicyMutationAuthorizationPort,
    ContributionPolicyUnavailable,
    DenyContributionPolicyAuthorization,
    ProjectCompensationUnitCreateRequest,
    ProjectCompensationUnitCreateResult,
)
from app.modules.contributions.units.models import ProjectCompensationUnit, ProjectCompensationUnitCreationEvent
from app.modules.contributions.policy_mutation_support import consume_and_close_policy_authority
from app.modules.contributions.policy_validation import policy_request_digest
from app.modules.contributions.repository import ContributionPolicyRepository
from app.modules.contributions.schemas import ProjectCompensationUnitInput
from app.modules.projects.api import (
    ProjectContributionPolicyEligibilityPort,
    ProjectContributionPolicyUnavailable,
)

_ACTION: CompensationUnitAction = "contribution.compensation_unit.create"


class ProjectCompensationUnitService:
    """Run unit creation without route or commit ownership."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        mutation_authorization: ContributionPolicyMutationAuthorizationPort | None = None,
        projects: ProjectContributionPolicyEligibilityPort | None = None,
    ) -> None:
        """Compose unit creation inside a caller-owned session; deny by default."""
        self._session = session
        self._repository = ContributionPolicyRepository(session)
        self._authorization = mutation_authorization or DenyContributionPolicyAuthorization()
        self._projects = projects

    async def create(
        self, request: ProjectCompensationUnitCreateRequest
    ) -> ProjectCompensationUnitCreateResult:
        """Create one active points unit, or replay the identical earlier creation."""
        self._require_request(request)
        digest = policy_request_digest(_ACTION, request)
        await self._repository.lock_operation(request.operation_id)
        event = await self._repository.get_unit_creation_event(request.operation_id)
        # After the operation fence, AUTH scope locks precede every product row lock;
        # an identical replay also needs current authority.
        await self._authorization.lock_contribution_policy_mutation_scope(
            action=_ACTION, actor_profile_id=request.actor_profile_id,
            project_id=request.project_id,
        )
        if event is not None:
            if (
                event.request_digest != digest
                or event.actor_profile_id != str(request.actor_profile_id)
                or event.project_id != str(request.project_id)
            ):
                raise ContributionPolicyConflict("compensation_unit_conflict")
            return self._result(event)
        if self._projects is None:
            raise ContributionPolicyUnavailable("compensation_unit_unavailable")
        try:
            project = await self._projects.lock_contribution_policy_project(request.project_id)
        except ProjectContributionPolicyUnavailable as exc:
            raise ContributionPolicyConflict("compensation_unit_not_found") from exc
        if project.project_id != request.project_id:
            raise ContributionPolicyConflict("compensation_unit_not_found")
        await self._repository.lock_unit_scope(
            request.project_id, request.instrument_type, request.unit_code
        )
        if await self._repository.lock_unit(
            request.project_id, request.instrument_type, request.unit_code
        ) is not None:
            raise ContributionPolicyConflict("compensation_unit_conflict")
        actor = await consume_and_close_policy_authority(
            self._authorization,
            CompensationUnitCreateAuthorizationFacts(
                action=_ACTION,
                actor_profile_id=request.actor_profile_id,
                operation_id=request.operation_id,
                request_digest=digest,
                project_id=request.project_id,
                instrument_type=request.instrument_type,
                unit_code=request.unit_code,
            ),
        )
        event = ProjectCompensationUnitCreationEvent(
            id=new_record_id(),
            operation_id=request.operation_id,
            request_digest=digest,
            actor_profile_id=str(actor),
            project_id=str(request.project_id),
            instrument_type=request.instrument_type,
            unit_code=request.unit_code,
        )
        await self._repository.add_unit_and_creation_event(
            ProjectCompensationUnit(
                project_id=str(request.project_id),
                instrument_type=request.instrument_type,
                unit_code=request.unit_code,
                iso_currency_code=None,
                status="active",
                created_by=str(actor),
            ),
            event,
        )
        return self._result(event)

    def _require_request(self, request: object) -> None:
        """Reject wrong types, transaction shape, selectors, instruments and codes."""
        if (
            type(request) is not ProjectCompensationUnitCreateRequest
            or not self._session.in_transaction()
            or self._session.in_nested_transaction()
            or not all(
                isinstance(getattr(request, name), UUID)
                for name in ("operation_id", "actor_profile_id", "project_id")
            )
        ):
            raise ContributionPolicyUnavailable("compensation_unit_unavailable")
        if request.instrument_type != "project_points":
            raise ContributionPolicyConflict("compensation_unit_invalid")
        try:
            ProjectCompensationUnitInput(
                project_id=str(request.project_id),
                instrument_type=request.instrument_type,
                unit_code=request.unit_code,
                created_by=str(request.actor_profile_id),
            )
        except ValueError as exc:
            raise ContributionPolicyConflict("compensation_unit_invalid") from exc

    @staticmethod
    def _result(event: ProjectCompensationUnitCreationEvent) -> ProjectCompensationUnitCreateResult:
        """Project immutable creation evidence into the command result."""
        return ProjectCompensationUnitCreateResult(
            event_id=event.id,
            operation_id=event.operation_id,
            request_digest=event.request_digest,
            actor_profile_id=UUID(event.actor_profile_id),
            project_id=UUID(event.project_id),
            instrument_type=cast(CompensationUnitInstrument, event.instrument_type),
            unit_code=event.unit_code,
            occurred_at=event.occurred_at,
        )
