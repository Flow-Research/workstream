"""Focused behavior proof for the unified compilation AUTH adapter."""

from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind as PublicActorKind,
    AuthorizationDenied as BoundaryAuthorizationDenied,
    PreparedAuthorizationInvalid,
    ProjectGuideCompilationExecutePersistFacts,
    ProjectGuideCompilationExecutePreflightFacts,
    ProjectGuideCompilationRequestFacts,
    project_guide_compilation_execute_resource_digest,
    project_guide_compilation_facts_digest,
)
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.guide_compilation import (
    ProjectGuideCompilationAuthorizationAdapter,
)
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    ServiceAuthorizationContext,
)
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.audit.schemas import AuthorityAuditEventInput


def _request() -> ProjectGuideCompilationRequestFacts:
    digest = "sha256:" + "a" * 64
    return ProjectGuideCompilationRequestFacts(
        project_id=uuid4(),
        guide_id=uuid4(),
        guide_version="v1",
        source_snapshot_id=uuid4(),
        source_snapshot_hash=digest,
        canonical_input_hash=digest,
        guide_material_hash=digest,
        setup_run_id=uuid4(),
        setup_generation=1,
        operation_id=uuid4(),
        request_id=uuid4(),
        idempotency_key=uuid4(),
        pre_catalogue_id="pre",
        pre_catalogue_version="v1",
        pre_catalogue_schema_version="v1",
        pre_catalogue_manifest_hash=digest,
        post_catalogue_id="post",
        post_catalogue_version="v1",
        post_catalogue_schema_version="v1",
        post_catalogue_manifest_hash=digest,
        agent_identity="agent",
        agent_version="v1",
        instruction_version="v1",
    )


def _actor() -> ActorIdentityFacts:
    return ActorIdentityFacts(uuid4(), uuid4(), PublicActorKind.HUMAN)


class _Prepared:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.handle = object()
        self.event_id = uuid4()

    async def prepare(self, *args):
        self.calls.append(("prepare", *args))
        return self.handle

    async def preflight(self, *args):
        self.calls.append(("preflight", *args))

    async def consume(self, *args):
        self.calls.append(("consume", *args))
        return SimpleNamespace(decision_id=self.event_id)


class _Session:
    def __init__(self) -> None:
        self.root = SimpleNamespace(is_active=True)
        self.sync_session = self

    def get_transaction(self):
        return self.root

    def in_nested_transaction(self) -> bool:
        return False


class _Repository:
    def __init__(self, *, link_status: str = "active") -> None:
        self.link_status = link_status

    async def lock_request_actor(self, identity_link_id, actor_profile_id):
        return (
            SimpleNamespace(
                id=str(identity_link_id),
                actor_profile_id=str(actor_profile_id),
                status=self.link_status,
            ),
            SimpleNamespace(
                id=str(actor_profile_id),
                actor_kind="service",
                status="active",
                service_identity=ServiceIdentity.PROJECT_SETUP.value,
            ),
        )


class _Evidence:
    def __init__(self) -> None:
        self.events: list[AuthorityAuditEventInput] = []

    async def add_authority_event(self, event: AuthorityAuditEventInput) -> None:
        self.events.append(event)


def _adapter(
    actor: ActorIdentityFacts,
) -> tuple[ProjectGuideCompilationAuthorizationAdapter, _Prepared]:
    context = HumanAuthorizationContext(
        actor_profile_id=actor.actor_profile_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=actor.identity_link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    prepared = _Prepared()
    authorization = SimpleNamespace(_context=context)
    prepared._authorization = authorization
    return ProjectGuideCompilationAuthorizationAdapter(authorization, prepared), prepared


def _runtime_context_for(actor_kind: ActorKind, service_identity: ServiceIdentity | None):
    common = dict(
        actor_profile_id=uuid4(), actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(), identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(), correlation_id=uuid4(),
    )
    if actor_kind is ActorKind.SERVICE:
        return ServiceAuthorizationContext(
            actor_kind=actor_kind, service_identity=service_identity, **common
        )
    return HumanAuthorizationContext(actor_kind=actor_kind, **common)


@pytest.mark.asyncio
async def test_request_prepare_and_consume_bind_the_exact_project_context() -> None:
    actor, facts = _actor(), _request()
    adapter, prepared = _adapter(actor)
    handle = await adapter.prepare_request(actor=actor, facts=facts)
    event_id = await adapter.consume_request(handle=handle, actor=actor, facts=facts)
    assert handle is prepared.handle
    assert event_id == prepared.event_id
    assert [call[1] for call in prepared.calls] == [
        ActionId.PROJECT_GUIDE_COMPILATION_REQUEST,
        prepared.handle,
    ]
    resource = prepared.calls[0][2].request_value
    assert resource["resource_id"] == str(facts.operation_id)
    assert resource["scope_project_id"] == str(facts.project_id)


@pytest.mark.asyncio
async def test_preflight_is_non_durable_and_final_digest_is_exact() -> None:
    actor, base = _actor(), _request()
    adapter, prepared = _adapter(actor)
    preflight = ProjectGuideCompilationExecutePreflightFacts(
        **asdict(base), attempt_id=uuid4(), provider_idempotency_key=uuid4()
    )
    await adapter.authorize_execute_preflight(actor=actor, facts=preflight)
    assert [call[0] for call in prepared.calls] == ["preflight"]
    preflight_input, preflight_resource = prepared.calls[0][2], prepared.calls[0][4]
    assert preflight_input.request_value == preflight_resource.model_dump(mode="json")
    assert preflight_resource.attempt_id == preflight.attempt_id
    assert preflight_resource.provider_idempotency_key == preflight.provider_idempotency_key
    assert preflight_resource.request_facts_digest == project_guide_compilation_facts_digest(
        preflight
    )
    digest = "sha256:" + "b" * 64
    values = {
        **asdict(preflight),
        **{
            "result_hash": digest,
            "sufficiency_component_hash": digest,
            "artifact_policy_component_hash": digest,
            "requirement_inventory_component_hash": digest,
            "pre_submit_policy_component_hash": digest,
            "post_submit_policy_component_hash": digest,
            "capability_suggestions_component_hash": digest,
            "setup_notes_component_hash": digest,
        },
    }
    provisional = ProjectGuideCompilationExecutePersistFacts(
        **values, resource_context_digest=digest
    )
    exact = project_guide_compilation_execute_resource_digest(actor, provisional)
    persist = ProjectGuideCompilationExecutePersistFacts(**values, resource_context_digest=exact)
    prepared.calls.clear()
    await adapter.prepare_execute_persist(actor=actor, facts=persist)
    assert prepared.calls[0][2].request_value["result_resource_digest"] == exact

    wrong = ProjectGuideCompilationExecutePersistFacts(
        **values, resource_context_digest="sha256:" + "c" * 64
    )
    prepared.calls.clear()
    with pytest.raises(BoundaryAuthorizationDenied):
        await adapter.prepare_execute_persist(actor=actor, facts=wrong)
    assert prepared.calls == []


@pytest.mark.asyncio
async def test_actor_mismatch_denies_before_prepared_service_access() -> None:
    actor, facts = _actor(), _request()
    adapter, prepared = _adapter(actor)
    wrong = ActorIdentityFacts(uuid4(), actor.identity_link_id, PublicActorKind.HUMAN)
    with pytest.raises(BoundaryAuthorizationDenied):
        await adapter.prepare_request(actor=wrong, facts=facts)
    assert prepared.calls == []


@pytest.mark.asyncio
async def test_real_kernel_system_project_manager_grant_cannot_request_compilation() -> None:
    context = HumanAuthorizationContext(
        actor_profile_id=uuid4(),
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    session = _Session()

    class SystemGrantRepository:
        async def lock_request_actor(self, identity_link_id, actor_profile_id):
            return (
                SimpleNamespace(
                    id=str(identity_link_id),
                    actor_profile_id=str(actor_profile_id),
                    status="active",
                ),
                SimpleNamespace(id=str(actor_profile_id), actor_kind="human", status="active"),
            )

        async def find_effective_grant(self, *_args, **kwargs):
            assert kwargs["exact_project_scope"] is True
            return SimpleNamespace(
                id=uuid4(), status="active", scope_type="system", scope_project_id=None
            )

    repository = SystemGrantRepository()
    authorization = AuthorizationService(
        session,
        context,
        admin_repository=repository,  # type: ignore[arg-type]
    )
    prepared = PreparedAuthorizationService(
        session,
        context,
        authorization,
        repository,  # type: ignore[arg-type]
    )
    adapter = ProjectGuideCompilationAuthorizationAdapter(authorization, prepared)
    actor = ActorIdentityFacts(
        context.actor_profile_id, context.identity_link_id, PublicActorKind.HUMAN
    )
    with pytest.raises(BoundaryAuthorizationDenied):
        await adapter.prepare_request(actor=actor, facts=_request())


@pytest.mark.asyncio
async def test_real_kernel_exact_project_manager_request_succeeds_and_replay_denies() -> None:
    context = HumanAuthorizationContext(
        actor_profile_id=uuid4(), actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE, identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(), correlation_id=uuid4(),
    )
    session, grant_id = _Session(), uuid4()

    class ExactGrantRepository:
        async def lock_request_actor(self, identity_link_id, actor_profile_id):
            return (
                SimpleNamespace(id=str(identity_link_id), actor_profile_id=str(actor_profile_id), status="active"),
                SimpleNamespace(id=str(actor_profile_id), actor_kind="human", status="active"),
            )

        async def find_effective_grant(self, *_args, **kwargs):
            project_id = kwargs["scope_project_id"]
            assert kwargs["exact_project_scope"] is True
            return SimpleNamespace(
                id=grant_id, status="active", scope_type="project",
                scope_project_id=str(project_id),
            )

    repository = ExactGrantRepository()
    authorization = AuthorizationService(
        session, context, admin_repository=repository  # type: ignore[arg-type]
    )
    evidence = _Evidence()
    authorization._audit = evidence  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session, context, authorization, repository  # type: ignore[arg-type]
    )
    adapter = ProjectGuideCompilationAuthorizationAdapter(authorization, prepared)
    actor = ActorIdentityFacts(
        context.actor_profile_id, context.identity_link_id, PublicActorKind.HUMAN
    )
    facts = _request()
    handle = await adapter.prepare_request(actor=actor, facts=facts)
    event_id = await adapter.consume_request(handle=handle, actor=actor, facts=facts)
    assert [event.event_id for event in evidence.events] == [event_id]
    with pytest.raises(PreparedAuthorizationInvalid):
        await adapter.consume_request(handle=handle, actor=actor, facts=facts)


@pytest.mark.parametrize(
    ("actor_kind", "service_identity", "method"),
    [
        (ActorKind.HUMAN, None, "execute"),
        (ActorKind.SERVICE, ServiceIdentity.PROJECT_SETUP, "request"),
        (ActorKind.SERVICE, ServiceIdentity.ARTIFACT_BINDING, "execute"),
    ],
)
@pytest.mark.asyncio
async def test_real_kernel_actor_matrix_denies_without_evidence(
    actor_kind, service_identity, method
) -> None:
    context = _runtime_context_for(actor_kind, service_identity)
    session, repository = _Session(), _Repository()
    authorization = AuthorizationService(
        session, context, admin_repository=repository  # type: ignore[arg-type]
    )
    evidence = _Evidence()
    authorization._audit = evidence  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session, context, authorization, repository  # type: ignore[arg-type]
    )
    adapter = ProjectGuideCompilationAuthorizationAdapter(authorization, prepared)
    public_kind = PublicActorKind(actor_kind.value)
    actor = ActorIdentityFacts(
        context.actor_profile_id, context.identity_link_id, public_kind,
        service_identity.value if service_identity else None,
    )
    with pytest.raises(BoundaryAuthorizationDenied):
        if method == "request":
            await adapter.prepare_request(actor=actor, facts=_request())
        else:
            await adapter.authorize_execute_preflight(
                actor=actor,
                facts=ProjectGuideCompilationExecutePreflightFacts(
                    **asdict(_request()), attempt_id=uuid4(), provider_idempotency_key=uuid4()
                ),
            )
    assert evidence.events == []


@pytest.mark.asyncio
async def test_real_kernel_preflight_is_non_evidencing_and_final_is_single_use() -> None:
    context = ServiceAuthorizationContext(
        actor_profile_id=uuid4(),
        actor_kind=ActorKind.SERVICE,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        service_identity=ServiceIdentity.PROJECT_SETUP,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    session, repository = _Session(), _Repository()
    authorization = AuthorizationService(
        session,
        context,
        admin_repository=repository,  # type: ignore[arg-type]
    )
    evidence = _Evidence()
    authorization._audit = evidence  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,
        context,
        authorization,
        repository,  # type: ignore[arg-type]
    )
    adapter = ProjectGuideCompilationAuthorizationAdapter(authorization, prepared)
    actor = ActorIdentityFacts(
        context.actor_profile_id,
        context.identity_link_id,
        PublicActorKind.SERVICE,
        ServiceIdentity.PROJECT_SETUP.value,
    )
    base = _request()
    preflight = ProjectGuideCompilationExecutePreflightFacts(
        **asdict(base), attempt_id=uuid4(), provider_idempotency_key=uuid4()
    )
    await adapter.authorize_execute_preflight(actor=actor, facts=preflight)
    await adapter.authorize_execute_preflight(actor=actor, facts=preflight)
    assert evidence.events == []
    assert prepared._issued == {}

    digest = "sha256:" + "b" * 64
    result = dict(
        result_hash=digest,
        sufficiency_component_hash=digest,
        artifact_policy_component_hash=digest,
        requirement_inventory_component_hash=digest,
        pre_submit_policy_component_hash=digest,
        post_submit_policy_component_hash=digest,
        capability_suggestions_component_hash=digest,
        setup_notes_component_hash=digest,
    )
    provisional = ProjectGuideCompilationExecutePersistFacts(
        **asdict(preflight), **result, resource_context_digest=digest
    )
    facts = ProjectGuideCompilationExecutePersistFacts(
        **asdict(preflight),
        **result,
        resource_context_digest=project_guide_compilation_execute_resource_digest(
            actor, provisional
        ),
    )
    handle = await adapter.prepare_execute_persist(actor=actor, facts=facts)
    event_id = await adapter.consume_execute_persist(handle=handle, actor=actor, facts=facts)
    assert [event.event_id for event in evidence.events] == [event_id]
    with pytest.raises(PreparedAuthorizationInvalid):
        await adapter.consume_execute_persist(handle=handle, actor=actor, facts=facts)
    assert [event.event_id for event in evidence.events] == [event_id]


@pytest.mark.asyncio
async def test_real_kernel_revoked_service_preflight_denies_without_evidence() -> None:
    context = ServiceAuthorizationContext(
        actor_profile_id=uuid4(),
        actor_kind=ActorKind.SERVICE,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        service_identity=ServiceIdentity.PROJECT_SETUP,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    session, repository = _Session(), _Repository(link_status="revoked")
    authorization = AuthorizationService(
        session,
        context,
        admin_repository=repository,  # type: ignore[arg-type]
    )
    evidence = _Evidence()
    authorization._audit = evidence  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,
        context,
        authorization,
        repository,  # type: ignore[arg-type]
    )
    adapter = ProjectGuideCompilationAuthorizationAdapter(authorization, prepared)
    actor = ActorIdentityFacts(
        context.actor_profile_id,
        context.identity_link_id,
        PublicActorKind.SERVICE,
        ServiceIdentity.PROJECT_SETUP.value,
    )
    preflight = ProjectGuideCompilationExecutePreflightFacts(
        **asdict(_request()), attempt_id=uuid4(), provider_idempotency_key=uuid4()
    )
    with pytest.raises(BoundaryAuthorizationDenied):
        await adapter.authorize_execute_preflight(actor=actor, facts=preflight)
    assert evidence.events == []


@pytest.mark.asyncio
async def test_exact_project_repository_scope_requires_a_project_identifier() -> None:
    """Never fall back to a system grant for an incomplete exact-project query."""
    repository = AdminAuthorizationRepository(SimpleNamespace())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact project scope requires"):
        await repository.find_effective_grant(
            uuid4(),
            PermissionId.PROJECT_GUIDE_COMPILATION_REQUEST,
            scope_project_id=None,
            exact_project_scope=True,
        )
