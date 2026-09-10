"""Controlled AUTH service fixtures; not PostgreSQL or real transaction proof."""

from __future__ import annotations
from types import SimpleNamespace
from uuid import uuid4
from app.modules.actors.api import ServiceIdentity
from app.modules.audit.schemas import AuthorityAuditEventInput
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.schemas import AdminRole
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    IdentityLinkStatus,
    AuthorizationContext,
    HumanAuthorizationContext,
    ProjectGuideMutationResourceContext,
    ServiceAuthorizationContext,
)


def _runtime_context(
    *,
    actor_status: ActorStatus = ActorStatus.ACTIVE,
    link_status: IdentityLinkStatus = IdentityLinkStatus.ACTIVE,
    actor_kind: ActorKind = ActorKind.HUMAN,
    service_identity: ServiceIdentity = ServiceIdentity.ARTIFACT_VERIFIER,
) -> AuthorizationContext:
    context_type = (
        ServiceAuthorizationContext
        if actor_kind is ActorKind.SERVICE
        else HumanAuthorizationContext
    )
    service_fields = (
        {"service_identity": service_identity} if actor_kind is ActorKind.SERVICE else {}
    )
    return context_type(
        actor_profile_id=uuid4(),
        actor_kind=actor_kind,
        actor_status=actor_status,
        identity_link_id=uuid4(),
        identity_link_status=link_status,
        request_id=uuid4(),
        correlation_id=uuid4(),
        **service_fields,
    )


class _DecisionEvidence:
    def __init__(self) -> None:
        self.events: list[AuthorityAuditEventInput] = []

    async def add_authority_event(self, event: AuthorityAuditEventInput) -> None:
        self.events.append(event)


_DEFAULT_REVALIDATOR = object()


def _runtime_service(
    context: AuthorizationContext,
    *,
    session=None,
    admin_repository=None,
    revalidate=_DEFAULT_REVALIDATOR,
    revalidate_service=None,
) -> tuple[AuthorizationService, _DecisionEvidence]:
    if revalidate is _DEFAULT_REVALIDATOR:

        async def revalidate(current, _resource):
            return current

    service = AuthorizationService(
        session if session is not None else object(),  # type: ignore[arg-type]
        context,
        revalidate_actor_self=revalidate,
        revalidate_service=revalidate_service,
        admin_repository=admin_repository,
    )
    evidence = _DecisionEvidence()
    service._audit = evidence  # type: ignore[assignment]
    return service, evidence


class _PreparedTestSession:
    """Minimal stable-root session contract for capability unit tests."""

    def __init__(self) -> None:
        self.root = SimpleNamespace(is_active=True)
        self.nested = False
        self.sync_session = self

    def get_transaction(self):
        return self.root

    def in_nested_transaction(self) -> bool:
        return self.nested


class _GuideMutationAuthorityFacts:
    def __init__(
        self,
        context: HumanAuthorizationContext,
        *,
        grant=None,
        permission_id: PermissionId = PermissionId.PROJECT_GUIDE_MANAGE,
    ) -> None:
        self.context = context
        self.grant = grant
        self.permission_id = permission_id

    async def lock_request_actor(self, identity_link_id, actor_profile_id):
        assert identity_link_id == self.context.identity_link_id
        assert actor_profile_id == self.context.actor_profile_id
        return (
            SimpleNamespace(
                id=str(identity_link_id),
                actor_profile_id=str(actor_profile_id),
                status="active",
            ),
            SimpleNamespace(id=str(actor_profile_id), actor_kind="human", status="active"),
        )

    async def find_effective_grant(
        self,
        actor_profile_id,
        permission_id,
        *,
        scope_project_id,
        for_update,
        allowed_roles,
        exact_project_scope=False,
    ):
        assert actor_profile_id == self.context.actor_profile_id
        assert permission_id is self.permission_id
        assert scope_project_id is not None
        assert for_update is True
        assert allowed_roles == frozenset({AdminRole.PROJECT_MANAGER})
        if self.grant is None or self.grant.scope_project_id not in {None, scope_project_id}:
            return None
        if exact_project_scope and self.grant.scope_project_id != scope_project_id:
            return None
        return self.grant




def _guide_mutation_resources(project_id, guide_id, operation_id, digest):
    """Complete create/update controls for the closed resource-contract matrix."""
    return {
        ActionId.PROJECT_GUIDE_CREATE: ProjectGuideMutationResourceContext(
            resource_type="project_guide_mutation",
            resource_id=guide_id,
            operation_id=operation_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            target_kind="create",
            guide_exists=False,
            operation_generation=1,
            request_digest=digest, task_examples_hash=digest, task_examples_count=1,
        ),
        ActionId.PROJECT_GUIDE_UPDATE: ProjectGuideMutationResourceContext(
            resource_type="project_guide_mutation",
            resource_id=guide_id,
            operation_id=operation_id,
            scope_project_id=project_id,
            guide_id=guide_id,
            target_kind="update",
            guide_exists=True,
            guide_status="draft",
            guide_version="1",
            operation_generation=1,
        ),
    }
