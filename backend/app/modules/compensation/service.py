"""Hidden compensation adapter-binding lifecycle orchestration."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.actors.api import CompensationAdapterActorUnavailable
from app.modules.compensation.api import (
    AdapterBindingActorEligibilityPort,
    AdapterBindingConflict,
    AdapterBindingCreateRequest,
    AdapterBindingAction,
    AdapterBindingEventType,
    AdapterBindingMutationAuthorizationFacts,
    AdapterBindingMutationAuthorizationPort,
    AdapterBindingMutationResult,
    AdapterBindingProjectEligibilityPort,
    AdapterBindingReadAuthorizationPort,
    AdapterBindingReadRequest,
    AdapterBindingResumeRequest,
    AdapterBindingStatus,
    AdapterBindingSuspendRequest,
    AdapterBindingUnavailable,
    AdapterBindingView,
    DenyAdapterBindingAuthorization,
)
from app.modules.compensation.models import (
    CompensationAdapterBindingLifecycleEvent,
    ProjectCompensationAdapterBinding,
)
from app.modules.compensation.repository import AdapterBindingRepository
from app.modules.projects.api import ProjectCompensationBindingUnavailable

_EVENT_BY_ACTION = {
    "compensation.adapter_binding.create": "created",
    "compensation.adapter_binding.suspend": "suspended",
    "compensation.adapter_binding.resume": "resumed",
}


def _request_digest(action: AdapterBindingAction, request: object) -> str:
    fields = {
        key: str(value) if isinstance(value, UUID) else value
        for key, value in asdict(request).items()  # type: ignore[arg-type]
    }
    return canonical_json_hash(
        {
            "domain": "workstream.compensation.adapter_binding.operation.v1",
            "action": action,
            "request": fields,
        }
    )


class AdapterBindingService:
    """Run hidden binding commands without transaction or route ownership."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        read_authorization: AdapterBindingReadAuthorizationPort | None = None,
        mutation_authorization: AdapterBindingMutationAuthorizationPort | None = None,
        projects: AdapterBindingProjectEligibilityPort | None = None,
        actors: AdapterBindingActorEligibilityPort | None = None,
    ) -> None:
        deny = DenyAdapterBindingAuthorization()
        self._session = session
        self._repository = AdapterBindingRepository(session)
        self._read_authorization = read_authorization or deny
        self._mutation_authorization = mutation_authorization or deny
        self._projects = projects
        self._actors = actors

    async def read(self, request: AdapterBindingReadRequest) -> AdapterBindingView:
        if type(request) is not AdapterBindingReadRequest:
            raise AdapterBindingConflict("compensation_adapter_binding_not_found")
        request.__post_init__()
        try:
            await self._read_authorization.authorize_adapter_binding_read(request)
        except (AdapterBindingUnavailable, AdapterBindingConflict) as exc:
            raise AdapterBindingConflict("compensation_adapter_binding_not_found") from exc
        binding = await self._repository.get_binding(
            request.project_id, request.adapter_binding_id
        )
        if binding is None:
            raise AdapterBindingConflict("compensation_adapter_binding_not_found")
        return self._view(binding)

    async def create(
        self, request: AdapterBindingCreateRequest
    ) -> AdapterBindingMutationResult:
        self._require_root_transaction(request, AdapterBindingCreateRequest)
        action: AdapterBindingAction = "compensation.adapter_binding.create"
        digest = _request_digest(action, request)
        await self._repository.lock_operation(request.operation_id)
        recovered = await self._recover(action, request, digest)
        if recovered is not None:
            return recovered
        if self._projects is None or self._actors is None:
            raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable")
        binding_id = uuid4()
        try:
            project = await self._projects.lock_compensation_binding_project(
                request.project_id
            )
            actor = await self._actors.lock_compensation_adapter_actor(
                request.adapter_actor_id
            )
        except (ProjectCompensationBindingUnavailable, CompensationAdapterActorUnavailable) as exc:
            raise AdapterBindingConflict("compensation_adapter_binding_not_found") from exc
        if project.project_id != request.project_id or actor.adapter_actor_id != request.adapter_actor_id:
            raise AdapterBindingConflict("compensation_adapter_binding_not_found")
        await self._repository.lock_creation_scope(
            request.project_id, request.instrument_type
        )
        if (
            await self._repository.get_active_binding(
                request.project_id, request.instrument_type
            )
            is not None
        ):
            raise AdapterBindingConflict("compensation_adapter_binding_conflict")
        facts = AdapterBindingMutationAuthorizationFacts(
            action=action,
            actor_profile_id=request.actor_profile_id,
            operation_id=request.operation_id,
            request_digest=digest,
            project_id=request.project_id,
            adapter_binding_id=binding_id,
            instrument_type=request.instrument_type,
            adapter_actor_id=request.adapter_actor_id,
            route_key=request.route_key,
            expected_status=None,
            expected_lifecycle_version=None,
        )
        authorized_actor = await self._consume_and_close(facts)
        binding = ProjectCompensationAdapterBinding(
            id=binding_id,
            project_id=str(request.project_id),
            instrument_type=request.instrument_type,
            adapter_actor_id=str(request.adapter_actor_id),
            route_key=request.route_key,
            status="active",
            binding_lifecycle_version=1,
            created_by=str(authorized_actor),
        )
        event = self._event(
            operation_id=request.operation_id,
            request_digest=digest,
            project_id=request.project_id,
            binding_id=binding_id,
            event_type="created",
            actor_profile_id=authorized_actor,
            from_status=None,
            to_status="active",
            from_version=0,
            to_version=1,
        )
        await self._repository.add_binding_and_event(binding, event)
        return self._result(event)

    async def suspend(
        self, request: AdapterBindingSuspendRequest
    ) -> AdapterBindingMutationResult:
        self._require_root_transaction(request, AdapterBindingSuspendRequest)
        action: AdapterBindingAction = "compensation.adapter_binding.suspend"
        digest = _request_digest(action, request)
        await self._repository.lock_operation(request.operation_id)
        recovered = await self._recover(action, request, digest)
        if recovered is not None:
            return recovered
        binding = await self._lock_transition_binding(request)
        if (
            binding.status != "active"
            or binding.binding_lifecycle_version != request.expected_lifecycle_version
        ):
            raise AdapterBindingConflict("compensation_adapter_binding_conflict")
        facts = self._transition_facts(action, request, digest, binding)
        authorized_actor = await self._consume_and_close(facts)
        from_version = binding.binding_lifecycle_version
        suspended_at = await self._session.scalar(select(func.clock_timestamp()))
        binding.status = "suspended"
        binding.binding_lifecycle_version = from_version + 1
        binding.suspended_by = str(authorized_actor)
        binding.suspended_at = suspended_at
        event = self._event(
            operation_id=request.operation_id,
            request_digest=digest,
            project_id=request.project_id,
            binding_id=request.adapter_binding_id,
            event_type="suspended",
            actor_profile_id=authorized_actor,
            from_status="active",
            to_status="suspended",
            from_version=from_version,
            to_version=from_version + 1,
        )
        await self._repository.flush_event(event)
        return self._result(event)

    async def resume(
        self, request: AdapterBindingResumeRequest
    ) -> AdapterBindingMutationResult:
        self._require_root_transaction(request, AdapterBindingResumeRequest)
        action: AdapterBindingAction = "compensation.adapter_binding.resume"
        digest = _request_digest(action, request)
        await self._repository.lock_operation(request.operation_id)
        recovered = await self._recover(action, request, digest)
        if recovered is not None:
            return recovered
        if self._projects is None or self._actors is None:
            raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable")
        try:
            project = await self._projects.lock_compensation_binding_project(
                request.project_id
            )
            identity = await self._repository.get_binding(
                request.project_id, request.adapter_binding_id
            )
            if identity is None:
                raise AdapterBindingConflict("compensation_adapter_binding_not_found")
            actor_id = UUID(identity.adapter_actor_id)
            actor = await self._actors.lock_compensation_adapter_actor(actor_id)
        except (ProjectCompensationBindingUnavailable, CompensationAdapterActorUnavailable) as exc:
            raise AdapterBindingConflict("compensation_adapter_binding_not_found") from exc
        if project.project_id != request.project_id or actor.adapter_actor_id != actor_id:
            raise AdapterBindingConflict("compensation_adapter_binding_not_found")
        binding = await self._lock_transition_binding(request)
        if binding.adapter_actor_id != str(actor_id):
            raise AdapterBindingConflict("compensation_adapter_binding_conflict")
        if (
            binding.status != "suspended"
            or binding.binding_lifecycle_version != request.expected_lifecycle_version
        ):
            raise AdapterBindingConflict("compensation_adapter_binding_conflict")
        prior = await self._repository.get_prior_suspension_event(
            request.adapter_binding_id, request.expected_lifecycle_version
        )
        if prior is None:
            raise AdapterBindingConflict("compensation_adapter_binding_conflict")
        await self._repository.lock_creation_scope(
            request.project_id, binding.instrument_type
        )
        active = await self._repository.get_active_binding(
            request.project_id, binding.instrument_type
        )
        if active is not None:
            raise AdapterBindingConflict("compensation_adapter_binding_conflict")
        facts = self._transition_facts(action, request, digest, binding)
        authorized_actor = await self._consume_and_close(facts)
        from_version = binding.binding_lifecycle_version
        binding.status = "active"
        binding.binding_lifecycle_version = from_version + 1
        binding.suspended_by = None
        binding.suspended_at = None
        event = self._event(
            operation_id=request.operation_id,
            request_digest=digest,
            project_id=request.project_id,
            binding_id=request.adapter_binding_id,
            event_type="resumed",
            actor_profile_id=authorized_actor,
            from_status="suspended",
            to_status="active",
            from_version=from_version,
            to_version=from_version + 1,
            prior_suspension_event_id=prior.id,
        )
        await self._repository.flush_event(event)
        return self._result(event)

    def _require_root_transaction(self, request: object, expected_type: type[object]) -> None:
        if (
            type(request) is not expected_type
            or not self._session.in_transaction()
            or self._session.in_nested_transaction()
        ):
            raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable")
        request.__post_init__()  # type: ignore[attr-defined]

    async def _recover(
        self, action: AdapterBindingAction, request: object, digest: str
    ) -> AdapterBindingMutationResult | None:
        operation_id = cast(UUID, getattr(request, "operation_id"))
        event = await self._repository.get_event_by_operation(operation_id)
        if event is None:
            return None
        expected_event = _EVENT_BY_ACTION[action]
        actor_id = cast(UUID, getattr(request, "actor_profile_id"))
        project_id = cast(UUID, getattr(request, "project_id"))
        if (
            event.event_type != expected_event
            or event.actor_profile_id != str(actor_id)
            or event.project_id != str(project_id)
            or event.request_digest != digest
        ):
            raise AdapterBindingConflict("compensation_adapter_binding_conflict")
        binding = await self._repository.get_binding(project_id, event.adapter_binding_id)
        if binding is None or not self._recovery_binding_matches(request, binding):
            raise AdapterBindingConflict("compensation_adapter_binding_conflict")
        try:
            await self._read_authorization.authorize_adapter_binding_read(
                AdapterBindingReadRequest(
                    actor_profile_id=actor_id,
                    project_id=project_id,
                    adapter_binding_id=event.adapter_binding_id,
                )
            )
        except (AdapterBindingUnavailable, AdapterBindingConflict) as exc:
            raise AdapterBindingConflict("compensation_adapter_binding_conflict") from exc
        return self._result(event)

    @staticmethod
    def _recovery_binding_matches(
        request: object, binding: ProjectCompensationAdapterBinding
    ) -> bool:
        if type(request) is AdapterBindingCreateRequest:
            return bool(
                binding.instrument_type == request.instrument_type
                and binding.adapter_actor_id == str(request.adapter_actor_id)
                and binding.route_key == request.route_key
            )
        return binding.id == getattr(request, "adapter_binding_id", None)

    async def _lock_transition_binding(
        self, request: AdapterBindingSuspendRequest | AdapterBindingResumeRequest
    ) -> ProjectCompensationAdapterBinding:
        binding = await self._repository.get_binding(
            request.project_id, request.adapter_binding_id, for_update=True
        )
        if binding is None:
            raise AdapterBindingConflict("compensation_adapter_binding_not_found")
        return binding

    def _transition_facts(
        self,
        action: AdapterBindingAction,
        request: AdapterBindingSuspendRequest | AdapterBindingResumeRequest,
        digest: str,
        binding: ProjectCompensationAdapterBinding,
    ) -> AdapterBindingMutationAuthorizationFacts:
        return AdapterBindingMutationAuthorizationFacts(
            action=action,
            actor_profile_id=request.actor_profile_id,
            operation_id=request.operation_id,
            request_digest=digest,
            project_id=request.project_id,
            adapter_binding_id=request.adapter_binding_id,
            instrument_type=binding.instrument_type,
            adapter_actor_id=UUID(binding.adapter_actor_id),
            route_key=binding.route_key,
            expected_status=cast(AdapterBindingStatus, binding.status),
            expected_lifecycle_version=request.expected_lifecycle_version,
        )

    async def _consume_and_close(
        self, facts: AdapterBindingMutationAuthorizationFacts
    ) -> UUID:
        prepared = await self._mutation_authorization.prepare_adapter_binding_mutation(facts)
        try:
            actor = await self._mutation_authorization.consume_adapter_binding_mutation(
                prepared, facts
            )
        finally:
            self._mutation_authorization.close_adapter_binding_mutation(prepared)
        if type(actor) is not UUID or actor != facts.actor_profile_id:
            raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable")
        return actor

    @staticmethod
    def _event(
        *,
        operation_id: UUID,
        request_digest: str,
        project_id: UUID,
        binding_id: UUID,
        event_type: AdapterBindingEventType,
        actor_profile_id: UUID,
        from_status: str | None,
        to_status: AdapterBindingStatus,
        from_version: int,
        to_version: int,
        prior_suspension_event_id: UUID | None = None,
    ) -> CompensationAdapterBindingLifecycleEvent:
        return CompensationAdapterBindingLifecycleEvent(
            id=uuid4(),
            operation_id=operation_id,
            request_digest=request_digest,
            project_id=str(project_id),
            adapter_binding_id=binding_id,
            event_type=event_type,
            actor_profile_id=str(actor_profile_id),
            from_status=from_status,
            to_status=to_status,
            from_lifecycle_version=from_version,
            to_lifecycle_version=to_version,
            prior_suspension_event_id=prior_suspension_event_id,
        )

    @staticmethod
    def _result(
        event: CompensationAdapterBindingLifecycleEvent,
    ) -> AdapterBindingMutationResult:
        return AdapterBindingMutationResult(
            event_id=event.id,
            operation_id=event.operation_id,
            request_digest=event.request_digest,
            project_id=UUID(event.project_id),
            adapter_binding_id=event.adapter_binding_id,
            event_type=cast(AdapterBindingEventType, event.event_type),
            actor_profile_id=UUID(event.actor_profile_id),
            from_status=cast(AdapterBindingStatus | None, event.from_status),
            to_status=cast(AdapterBindingStatus, event.to_status),
            from_lifecycle_version=event.from_lifecycle_version,
            to_lifecycle_version=event.to_lifecycle_version,
            prior_suspension_event_id=event.prior_suspension_event_id,
            occurred_at=event.occurred_at,
        )

    @staticmethod
    def _view(binding: ProjectCompensationAdapterBinding) -> AdapterBindingView:
        return AdapterBindingView(
            adapter_binding_id=binding.id,
            project_id=UUID(binding.project_id),
            instrument_type=binding.instrument_type,
            adapter_actor_id=UUID(binding.adapter_actor_id),
            route_key=binding.route_key,
            status=cast(AdapterBindingStatus, binding.status),
            lifecycle_version=binding.binding_lifecycle_version,
            created_by=UUID(binding.created_by),
            created_at=binding.created_at,
            suspended_by=UUID(binding.suspended_by) if binding.suspended_by else None,
            suspended_at=binding.suspended_at,
        )
