"""Production AUTH adapter for unified Project Guide compilation custody."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from app.modules.authorization.api import (
    ActorIdentityFacts,
    AuthorizationDenied as BoundaryAuthorizationDenied,
    PreparedAuthorizationInvalid,
    ProjectGuideCompilationExecutePersistFacts,
    ProjectGuideCompilationExecutePreflightFacts,
    ProjectGuideCompilationRequestFacts,
    ProjectGuideCompilationRequestOrigin,
    project_guide_compilation_execute_resource_digest,
    project_guide_compilation_facts_digest,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_compilation import (
    ProjectGuideCompilationExecuteResourceContext,
    ProjectGuideCompilationRequestResourceContext,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import (
    PreparedAuthorizationHandle,
    PreparedAuthorizationService,
)
from app.modules.authorization.runtime import (
    AuthorizationDenied as KernelAuthorizationDenied,
    HumanAuthorizationContext,
    PreparedAuthorizationInput,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationUnsupported,
    ServiceAuthorizationContext,
)


def _request_action(origin: ProjectGuideCompilationRequestOrigin) -> ActionId:
    """Select authority by the explicit trigger, never by ambient actor roles."""
    if origin.trigger != "project_manager":
        raise BoundaryAuthorizationDenied("explicit Project Manager request required")
    return ActionId.PROJECT_GUIDE_COMPILATION_REQUEST


def _request_context(
    facts: ProjectGuideCompilationRequestFacts,
    origin: ProjectGuideCompilationRequestOrigin,
) -> ProjectGuideCompilationRequestResourceContext:
    return ProjectGuideCompilationRequestResourceContext(
        resource_type="project_guide_compilation_request",
        resource_id=facts.operation_id,
        scope_project_id=facts.project_id,
        guide_id=facts.guide_id,
        source_snapshot_id=facts.source_snapshot_id,
        setup_run_id=facts.setup_run_id,
        setup_generation=facts.setup_generation,
        operation_id=facts.operation_id,
        request_id=facts.request_id,
        idempotency_key=facts.idempotency_key,
        request_facts_digest=project_guide_compilation_facts_digest(facts),
        **asdict(origin),
    )


def _execute_context(
    facts: ProjectGuideCompilationExecutePreflightFacts,
    *,
    phase: str,
) -> ProjectGuideCompilationExecuteResourceContext:
    result_digest = (
        facts.resource_context_digest
        if isinstance(facts, ProjectGuideCompilationExecutePersistFacts)
        else None
    )
    return ProjectGuideCompilationExecuteResourceContext(
        resource_type="project_guide_compilation_attempt",
        resource_id=facts.attempt_id,
        scope_project_id=facts.project_id,
        guide_id=facts.guide_id,
        source_snapshot_id=facts.source_snapshot_id,
        setup_run_id=facts.setup_run_id,
        setup_generation=facts.setup_generation,
        attempt_id=facts.attempt_id,
        provider_idempotency_key=facts.provider_idempotency_key,
        phase=phase,
        request_facts_digest=project_guide_compilation_facts_digest(facts),
        result_resource_digest=result_digest,
    )


def _input(resource, idempotency_key: UUID) -> PreparedAuthorizationInput:
    return PreparedAuthorizationInput(
        idempotency_key=idempotency_key,
        request_value=resource.model_dump(mode="json"),
    )


class ProjectGuideCompilationAuthorizationAdapter:
    """Bind the public compilation port to the existing AUTH kernel and PREP."""

    def __init__(
        self,
        authorization: AuthorizationService,
        prepared: PreparedAuthorizationService,
    ) -> None:
        if prepared._authorization is not authorization:
            raise TypeError("compilation adapter requires one authorization composition")
        self._authorization = authorization
        self._prepared = prepared

    @classmethod
    def from_prepared(
        cls, prepared: PreparedAuthorizationService
    ) -> ProjectGuideCompilationAuthorizationAdapter:
        """Compose the adapter without exposing AUTH's private pairing."""
        return cls(prepared._authorization, prepared)

    def _assert_actor(self, actor: ActorIdentityFacts) -> None:
        context = self._authorization._context
        if (
            actor.actor_profile_id != context.actor_profile_id
            or actor.identity_link_id != context.identity_link_id
            or (
                isinstance(context, ServiceAuthorizationContext)
                and actor.service_identity != context.service_identity.value
            )
            or (
                isinstance(context, HumanAuthorizationContext)
                and actor.service_identity is not None
            )
        ):
            raise BoundaryAuthorizationDenied("compilation authority denied")

    @staticmethod
    def _assert_result_digest(
        actor: ActorIdentityFacts, facts: ProjectGuideCompilationExecutePersistFacts
    ) -> None:
        if facts.resource_context_digest != project_guide_compilation_execute_resource_digest(
            actor, facts
        ):
            raise BoundaryAuthorizationDenied("compilation authority denied")

    @staticmethod
    async def _invoke(operation):
        try:
            return await operation
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid("prepared compilation authority is invalid") from exc
        except (PreparedAuthorizationUnsupported, KernelAuthorizationDenied) as exc:
            raise BoundaryAuthorizationDenied("compilation authority denied") from exc

    async def lock_request_scope(self, *, actor: ActorIdentityFacts, project_id: UUID) -> None:
        """Reuse PREP's live scope fence without issuing product mutation authority."""
        self._assert_actor(actor)
        await self._invoke(self._prepared.lock_mutation_scope(
            ActionId.PROJECT_GUIDE_COMPILATION_REQUEST,
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT, project_id=project_id),
        ))

    async def prepare_request(
        self, *, actor: ActorIdentityFacts, facts: ProjectGuideCompilationRequestFacts,
        origin: ProjectGuideCompilationRequestOrigin,
    ) -> PreparedAuthorizationHandle:
        self._assert_actor(actor)
        resource = _request_context(facts, origin)
        return await self._invoke(
            self._prepared.prepare(
                _request_action(origin),
                _input(resource, facts.idempotency_key),
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT, project_id=facts.project_id
                ),
            )
        )

    async def consume_request(
        self,
        *,
        handle: PreparedAuthorizationHandle,
        actor: ActorIdentityFacts,
        prepared_facts: ProjectGuideCompilationRequestFacts,
        facts: ProjectGuideCompilationRequestFacts,
        origin: ProjectGuideCompilationRequestOrigin,
    ) -> UUID:
        self._assert_actor(actor)
        resource = _request_context(facts, origin)
        decision = await self._invoke(
            self._prepared.consume(
                handle,
                _request_action(origin),
                _input(_request_context(prepared_facts, origin), prepared_facts.idempotency_key),
                resource,
            )
        )
        return decision.decision_id

    async def validate_request_replay(
        self, *, actor: ActorIdentityFacts, facts: ProjectGuideCompilationRequestFacts,
        origin: ProjectGuideCompilationRequestOrigin,
    ) -> None:
        """Hold current trigger authority in the caller's receipt transaction."""
        self._assert_actor(actor)
        resource = _request_context(facts, origin)
        await self._invoke(self._prepared.preflight(
            _request_action(origin), _input(resource, facts.idempotency_key),
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT, project_id=facts.project_id),
            resource,
        ))

    async def authorize_execute_preflight(
        self, *, actor: ActorIdentityFacts, facts: ProjectGuideCompilationExecutePreflightFacts
    ) -> None:
        self._assert_actor(actor)
        resource = _execute_context(facts, phase="preflight")
        await self._invoke(
            self._prepared.preflight(
                ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE,
                _input(resource, facts.idempotency_key),
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=facts.project_id,
                ),
                resource,
            )
        )

    async def prepare_execute_persist(
        self, *, actor: ActorIdentityFacts, facts: ProjectGuideCompilationExecutePersistFacts
    ) -> PreparedAuthorizationHandle:
        self._assert_actor(actor)
        self._assert_result_digest(actor, facts)
        resource = _execute_context(facts, phase="persist")
        return await self._invoke(
            self._prepared.prepare(
                ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE,
                _input(resource, facts.idempotency_key),
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT, project_id=facts.project_id
                ),
            )
        )

    async def consume_execute_persist(
        self,
        *,
        handle: PreparedAuthorizationHandle,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePersistFacts,
    ) -> UUID:
        self._assert_actor(actor)
        self._assert_result_digest(actor, facts)
        resource = _execute_context(facts, phase="persist")
        decision = await self._invoke(
            self._prepared.consume(
                handle,
                ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE,
                _input(resource, facts.idempotency_key),
                resource,
            )
        )
        return decision.decision_id
