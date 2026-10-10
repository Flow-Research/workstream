"""Registry registration remains caller-transactional, authorized and replay exact."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.checker_registry_authorization import (
    ExternalCheckerRegistryAuthorizationAdapter,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.checkers.api.external import (
    ExternalCheckerRegistrationAuthorityFacts,
    ExternalCheckerRegistrationAuthorityReceipt,
    ExternalCheckerRegistryConflict,
    ExternalCheckerRegistryUnavailable,
    make_external_checker_registration_request,
)
from app.modules.checkers.external_registry import ExternalCheckerRegistryService
from tests.checkers.external.support import registration_request, schema


class _Session:
    def __init__(self, active: bool = True) -> None:
        self.root = SimpleNamespace(is_active=active) if active else None
        self.sync_session = self

    def get_transaction(self):
        return self.root

    def in_nested_transaction(self) -> bool:
        return False


class _Authority:
    def __init__(self) -> None:
        self.calls: list[ExternalCheckerRegistrationAuthorityFacts] = []

    async def authorize_registration(self, facts):
        self.calls.append(facts)
        return ExternalCheckerRegistrationAuthorityReceipt(
            actor_profile_id=facts.actor_profile_id,
            authorization_decision_event_id=uuid4(),
        )


class _KernelAdminRepository:
    def __init__(self) -> None:
        self.grant_id = uuid4()
        self.filters = None

    async def lock_control(self) -> None:
        return None

    async def lock_request_actor(self, identity_link_id, actor_profile_id):
        return (
            SimpleNamespace(id=str(identity_link_id), status="active"),
            SimpleNamespace(id=str(actor_profile_id), actor_kind="human", status="active"),
        )

    async def find_effective_grant(self, *_args, **kwargs):
        self.filters = kwargs
        return SimpleNamespace(id=self.grant_id)


class _Evidence:
    def __init__(self) -> None:
        self.events = []

    async def add_authority_event(self, event) -> None:
        self.events.append(event)


class _Repository:
    def __init__(self) -> None:
        self.rows = []
        self.locks: list[tuple] = []

    async def lock_registration_scopes(self, operation_id, **identity):
        self.locks.append((operation_id, identity))

    async def by_operation(self, operation_id):
        return next(
            (row for row in self.rows if row.registration_operation_id == operation_id),
            None,
        )

    async def by_identity(self, **identity):
        return next(
            (
                row
                for row in self.rows
                if all(getattr(row, name) == value for name, value in identity.items())
            ),
            None,
        )

    async def add(self, row):
        row.created_at = datetime.now(timezone.utc)
        self.rows.append(row)

    async def by_exact_id(self, entry_id):
        return next((row for row in self.rows if row.id == entry_id), None)


def _service(active: bool = True):
    authority = _Authority()
    service = ExternalCheckerRegistryService(_Session(active), authority)  # type: ignore[arg-type]
    repository = _Repository()
    service._repository = repository  # type: ignore[assignment]
    return service, authority, repository


@pytest.mark.asyncio
async def test_register_flushes_once_and_freshly_authorizes_exact_replay() -> None:
    service, authority, repository = _service()
    request = registration_request()

    first = await service.register(request)
    replay = await service.register(request)

    assert replay == first
    assert len(repository.rows) == 1
    assert authority.calls == [authority.calls[0], authority.calls[0]]
    assert first.entry_digest == request.spec.spec_digest
    assert first.registered_by_actor_profile_id == request.actor_profile_id


@pytest.mark.asyncio
async def test_register_rejects_operation_or_logical_identity_substitution() -> None:
    service, authority, repository = _service()
    request = registration_request()
    await service.register(request)

    changed_operation = registration_request()
    changed_operation = changed_operation.model_copy(
        update={"spec": request.spec}
    )
    with pytest.raises(ExternalCheckerRegistryConflict):
        await service.register(changed_operation)

    assert len(repository.rows) == 1
    assert len(authority.calls) == 2


@pytest.mark.asyncio
async def test_same_operation_rejects_every_mutated_payload_and_preserves_row() -> None:
    service, authority, repository = _service()
    request = registration_request()
    stored = await service.register(request)
    spec = request.spec
    changed_image = type(spec).model_validate(
        spec.model_dump() | {"image_digest": "sha256:" + "b" * 64}
    )
    changed_schema = type(spec).model_validate(
        spec.model_dump()
        | {"configuration_schema": schema("acme.changed.configuration")}
    )
    changed_resources = type(spec).model_validate(
        spec.model_dump()
        | {"resources": spec.resources.model_dump() | {"cpu_millis": 600}}
    )
    mutations = (
        make_external_checker_registration_request(
            actor_profile_id=request.actor_profile_id,
            operation_id=request.operation_id,
            registry_entry_id=registry_entry_id,
            spec=changed,
        )
        for registry_entry_id, changed in (
            (new_record_id(), spec),
            (request.registry_entry_id, changed_image),
            (request.registry_entry_id, changed_schema),
            (request.registry_entry_id, changed_resources),
        )
    )
    for mutation in mutations:
        with pytest.raises(ExternalCheckerRegistryConflict):
            await service.register(mutation)

    assert len(repository.rows) == 1
    assert len(authority.calls) == 5
    assert await service.read_exact(stored.registry_entry_id, stored.entry_digest) == stored


@pytest.mark.asyncio
async def test_register_requires_an_active_caller_owned_root_transaction() -> None:
    service, authority, repository = _service(active=False)
    with pytest.raises(ExternalCheckerRegistryUnavailable):
        await service.register(registration_request())
    assert authority.calls == []
    assert repository.rows == []


@pytest.mark.asyncio
async def test_authority_adapter_binds_actor_correlation_and_exact_resource() -> None:
    operation_id, actor_id, event_id = uuid4(), uuid4(), uuid4()
    context = HumanAuthorizationContext(
        actor_profile_id=actor_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=operation_id,
    )
    calls = []

    async def require(action, resource):
        calls.append((action, resource))
        return SimpleNamespace(decision_id=event_id)

    authorization = SimpleNamespace(_context=context, require=require)
    adapter = ExternalCheckerRegistryAuthorizationAdapter(authorization)  # type: ignore[arg-type]
    facts = ExternalCheckerRegistrationAuthorityFacts(
        actor_profile_id=actor_id,
        operation_id=operation_id,
        registry_entry_id=uuid4(),
        request_digest="sha256:" + "1" * 64,
        entry_digest="sha256:" + "2" * 64,
    )

    receipt = await adapter.authorize_registration(facts)

    assert receipt.authorization_decision_event_id == event_id
    assert calls[0][0] is ActionId.CHECKER_REGISTRY_REGISTER
    assert calls[0][1].model_dump() == {
        "resource_type": "external_checker_registry_entry",
        "resource_id": facts.registry_entry_id,
        "operation_id": operation_id,
        "request_digest": facts.request_digest,
        "entry_digest": facts.entry_digest,
    }

    authorization._context = context.model_copy(update={"correlation_id": uuid4()})
    with pytest.raises(ExternalCheckerRegistryUnavailable):
        await adapter.authorize_registration(facts)


@pytest.mark.asyncio
async def test_real_kernel_classifies_registry_as_system_operator_mutation() -> None:
    operation_id, actor_id = uuid4(), uuid4()
    context = HumanAuthorizationContext(
        actor_profile_id=actor_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=operation_id,
    )
    repository = _KernelAdminRepository()
    authorization = AuthorizationService(
        _Session(),
        context,
        admin_repository=repository,  # type: ignore[arg-type]
    )
    evidence = _Evidence()
    authorization._audit = evidence  # type: ignore[assignment]
    facts = ExternalCheckerRegistrationAuthorityFacts(
        actor_profile_id=actor_id,
        operation_id=operation_id,
        registry_entry_id=uuid4(),
        request_digest="sha256:" + "1" * 64,
        entry_digest="sha256:" + "2" * 64,
    )

    receipt = await ExternalCheckerRegistryAuthorizationAdapter(
        authorization
    ).authorize_registration(facts)

    assert receipt.actor_profile_id == actor_id
    assert len(evidence.events) == 1
    assert repository.filters is not None
    assert repository.filters["scope_project_id"] is None
    assert repository.filters["system_scope_only"] is True
    assert {role.value for role in repository.filters["allowed_roles"]} == {"operator"}
