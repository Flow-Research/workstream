"""Focused AUTH proof for Finance Authority adapter-binding activation."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.modules.audit.schemas import AuthorityAuditEventInput
from app.modules.authorization.adapter_binding_authorization import (
    AdapterBindingAuthorizationAdapter,
)
from app.modules.authorization.api import (
    AdapterBindingMutationAuthorityFacts,
    AdapterBindingReadFacts,
    AuthorizationDenied,
    PreparedAuthorizationInvalid,
    action_id,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.adapter_bindings import (
    AdapterBindingMutationResourceContext,
)
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    AuthorizationDenied as KernelAuthorizationDenied,
)


class _Session:
    def __init__(self) -> None:
        self.root = SimpleNamespace(is_active=True)
        self.sync_session = self

    def get_transaction(self):
        return self.root

    def in_transaction(self) -> bool:
        return True

    def in_nested_transaction(self) -> bool:
        return False


class _FinanceRepository:
    def __init__(self, grant_project_id: UUID | None) -> None:
        self.grant_id = uuid4()
        self.grant_project_id = grant_project_id

    async def lock_control(self) -> None:
        return None

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
        assert {role.value for role in kwargs["allowed_roles"]} == {"finance_authority"}
        requested = kwargs["scope_project_id"]
        if self.grant_project_id is not None and requested != self.grant_project_id:
            return None
        return SimpleNamespace(
            id=self.grant_id,
            status="active",
            scope_type="system" if self.grant_project_id is None else "project",
            scope_project_id=(
                None if self.grant_project_id is None else str(self.grant_project_id)
            ),
        )

    async def has_effective_permission_any_scope(self, *_args, **_kwargs) -> bool:
        return True


class _Evidence:
    def __init__(self) -> None:
        self.events: list[AuthorityAuditEventInput] = []

    async def add_authority_event(self, event: AuthorityAuditEventInput) -> None:
        self.events.append(event)


def _adapter(project_id: UUID | None):
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
    repository = _FinanceRepository(project_id)
    kernel = AuthorizationService(
        session,
        context,
        admin_repository=repository,  # type: ignore[arg-type]
    )
    evidence = _Evidence()
    kernel._audit = evidence  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,
        context,
        kernel,
        repository,  # type: ignore[arg-type]
    )
    return AdapterBindingAuthorizationAdapter(kernel, prepared), context, session, evidence


def _create_facts(actor_id: UUID, project_id: UUID) -> AdapterBindingMutationAuthorityFacts:
    return AdapterBindingMutationAuthorityFacts(
        action_id=action_id("compensation.adapter_binding.create"),
        actor_profile_id=actor_id,
        operation_id=uuid4(),
        request_digest="sha256:" + "a" * 64,
        project_id=project_id,
        adapter_binding_id=uuid4(),
        instrument_type="money",
        adapter_actor_id=uuid4(),
        route_key="stripe.primary",
        expected_status=None,
        expected_lifecycle_version=None,
    )


def _transition_facts(
    actor_id: UUID, project_id: UUID, action: str
) -> AdapterBindingMutationAuthorityFacts:
    return AdapterBindingMutationAuthorityFacts(
        action_id=action_id(action),
        actor_profile_id=actor_id,
        operation_id=uuid4(),
        request_digest="sha256:" + "c" * 64,
        project_id=project_id,
        adapter_binding_id=uuid4(),
        instrument_type="project_points",
        adapter_actor_id=uuid4(),
        route_key="points.primary",
        expected_status=("active" if action.endswith("suspend") else "suspended"),
        expected_lifecycle_version=4,
    )


@pytest.mark.asyncio
async def test_project_finance_authority_reads_and_consumes_exact_create_once() -> None:
    project_id = uuid4()
    adapter, context, _session, evidence = _adapter(project_id)
    await adapter.authorize_read(
        actor_profile_id=context.actor_profile_id,
        facts=AdapterBindingReadFacts(project_id=project_id, adapter_binding_id=uuid4()),
    )
    facts = _create_facts(context.actor_profile_id, project_id)
    prepared = await adapter.prepare_mutation(facts)
    assert await adapter.consume_mutation(prepared, facts) == context.actor_profile_id
    adapter.close_mutation(prepared)
    assert len(evidence.events) == 2
    with pytest.raises(PreparedAuthorizationInvalid):
        await adapter.consume_mutation(prepared, facts)


@pytest.mark.asyncio
async def test_wrong_actor_and_cross_project_deny_before_authority_issuance() -> None:
    project_id = uuid4()
    adapter, context, _session, evidence = _adapter(project_id)
    with pytest.raises(AuthorizationDenied):
        await adapter.prepare_mutation(_create_facts(uuid4(), project_id))
    cross_project = _create_facts(context.actor_profile_id, uuid4())
    with pytest.raises(AuthorizationDenied):
        await adapter.prepare_mutation(cross_project)
    assert evidence.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    (
        "compensation.adapter_binding.suspend",
        "compensation.adapter_binding.resume",
    ),
)
async def test_system_finance_authority_consumes_exact_transition(
    action: str,
) -> None:
    project_id = uuid4()
    adapter, context, _session, evidence = _adapter(None)
    facts = _transition_facts(context.actor_profile_id, project_id, action)
    prepared = await adapter.prepare_mutation(facts)
    assert await adapter.consume_mutation(prepared, facts) == context.actor_profile_id
    adapter.close_mutation(prepared)
    assert len(evidence.events) == 1


@pytest.mark.asyncio
async def test_replaced_transaction_invalidates_prepared_authority() -> None:
    project_id = uuid4()
    adapter, context, session, _evidence = _adapter(project_id)
    facts = _create_facts(context.actor_profile_id, project_id)
    prepared = await adapter.prepare_mutation(facts)
    session.root = SimpleNamespace(is_active=True)
    with pytest.raises(PreparedAuthorizationInvalid):
        await adapter.consume_mutation(prepared, facts)
    adapter.close_mutation(prepared)


@pytest.mark.asyncio
async def test_mutation_action_cannot_bypass_prep_through_direct_kernel_require() -> None:
    project_id = uuid4()
    adapter, context, _session, _evidence = _adapter(project_id)
    facts = _create_facts(context.actor_profile_id, project_id)
    _, resource = adapter._mutation_context(facts)
    assert isinstance(resource, AdapterBindingMutationResourceContext)
    with pytest.raises(KernelAuthorizationDenied):
        await adapter._authorization.require(ActionId.COMPENSATION_ADAPTER_BINDING_CREATE, resource)
