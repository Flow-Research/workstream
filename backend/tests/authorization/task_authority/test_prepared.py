"""Real kernel/PREP decisions with bounded repository and evidence doubles."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.authorization.catalogue import ActionId
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.api import TaskAuthorityDenied, TaskAuthorityFacts, TaskAuthorityOperation
from app.modules.authorization.domain.task_authority import TaskAuthorityResourceContext
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    ServiceAuthorizationContext,
    IdentityLinkStatus,
    AuthorizationDenied,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)


class Session:
    def __init__(self):
        self.root = SimpleNamespace(is_active=True)
        self.sync_session = self

    def get_transaction(self):
        return self.root

    def in_nested_transaction(self):
        return False


class Repository:
    def __init__(self, context, project, *, granted=True, status="active", link_status="active"):
        self.context, self.project = context, project
        self.granted, self.status, self.link_status = granted, status, link_status
        self.calls = []
        self.grant = SimpleNamespace(id=str(uuid4()), status="active")

    async def lock_request_actor(self, link, actor):
        self.calls.append("actor_link")
        assert link == self.context.identity_link_id and actor == self.context.actor_profile_id
        return (
            SimpleNamespace(id=str(link), actor_profile_id=str(actor), status=self.link_status),
            SimpleNamespace(id=str(actor), actor_kind="human", status=self.status),
        )

    async def find_active_project_role(self, *, project_id, actor_profile_id, role, for_update):
        self.calls.append("grant")
        assert (
            for_update and role == "submitter" and actor_profile_id == self.context.actor_profile_id
        )
        return self.grant if self.granted and project_id == self.project else None


class Evidence:
    def __init__(self):
        self.events = []

    async def add_authority_event(self, event):
        self.events.append(event)


def setup(*, granted=True, status="active", link_status="active"):
    context = HumanAuthorizationContext(
        actor_profile_id=uuid4(),
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    project = uuid4()
    session = Session()
    repository = Repository(
        context, project, granted=granted, status=status, link_status=link_status
    )
    kernel = AuthorizationService(session, context, admin_repository=repository)
    evidence = Evidence()
    kernel._audit = evidence
    prepared = PreparedAuthorizationService(session, context, kernel, repository)
    resource = TaskAuthorityResourceContext(
        resource_id=uuid4(),
        scope_project_id=project,
        actor_profile_id=context.actor_profile_id,
        identity_link_id=context.identity_link_id,
        task_status="ready",
        assigned_to=None,
        assignment_id=None,
        assignment_contributor_id=None,
        locked_context_hash="sha256:" + "a" * 64,
        reason=None,
    )
    return session, repository, prepared, resource, evidence


async def prepare(prepared, resource, action=ActionId.TASK_CLAIM):
    value = PreparedAuthorizationInput(
        idempotency_key=uuid4(), request_value=resource.model_dump(mode="json")
    )
    handle = await prepared.prepare(
        action,
        value,
        PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT,
            project_id=resource.scope_project_id,
        ),
    )
    return handle, value


@pytest.mark.asyncio
async def test_claim_consumes_exact_current_project_grant_and_records_evidence():
    _, repository, prepared, resource, evidence = setup()
    try:
        handle, value = await prepare(prepared, resource)
        decision = await prepared.consume(handle, ActionId.TASK_CLAIM, value, resource)
        assert decision.allowed and str(decision.matched_grant_id) == repository.grant.id
        assert decision.matched_scope_project_id == resource.scope_project_id
        assert repository.calls == ["actor_link", "grant"]
        assert len(evidence.events) == 1
        assert evidence.events[0].project_id == str(resource.scope_project_id)
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await prepared.consume(handle, ActionId.TASK_CLAIM, value, resource)
    finally:
        prepared.close()


@pytest.mark.parametrize("case", ["valid", "missing_profile", "missing_link", "foreign_link"])
async def test_canonical_identity_selectors_and_missing_row_denials(case):
    """Actual AUTH query construction and kernel decisions; SQL execution is doubled."""
    _, repository, prepared, resource, evidence = setup()
    context = repository.context
    profile = SimpleNamespace(
        id=str(context.actor_profile_id), actor_kind="human", status="active",
    )
    link = SimpleNamespace(
        id=str(context.identity_link_id), actor_profile_id=str(context.actor_profile_id),
        status="active", subject_kind="human",
    )
    if case == "foreign_link":
        link.actor_profile_id = str(uuid4())
    rows = [None] if case == "missing_profile" else [
        profile, None if case == "missing_link" else link,
    ]
    sql_session = SimpleNamespace(scalar=AsyncMock(side_effect=rows))
    repository.lock_request_actor = AdminAuthorizationRepository(sql_session).lock_request_actor
    try:
        if case == "valid":
            handle, request = await prepare(prepared, resource)
            decision = await prepared.consume(handle, ActionId.TASK_CLAIM, request, resource)
            assert decision.allowed
            assert str(decision.matched_grant_id) == repository.grant.id
            assert repository.calls == ["grant"]
            assert len(evidence.events) == 1
        else:
            with pytest.raises(PreparedAuthorizationUnsupported):
                await prepare(prepared, resource)
            assert repository.calls == []
            assert evidence.events == []
        expected = [("actor_profiles", context.actor_profile_id)]
        if case != "missing_profile":
            expected.append(("actor_identity_links", context.identity_link_id))
        assert len(sql_session.scalar.await_args_list) == len(expected)
        for call, (table, identity) in zip(sql_session.scalar.await_args_list, expected, strict=True):
            statement = call.args[0]
            assert statement.column_descriptions[0]["entity"].__tablename__ == table
            assert list(statement.compile().params.values()) == [str(identity)]
            assert statement._for_update_arg is not None
            assert statement.get_execution_options()["populate_existing"] is True
    finally:
        prepared.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "settings",
    [
        {"granted": False},
        {"status": "suspended"},
        {"status": "deactivated"},
        {"link_status": "revoked"},
    ],
)
async def test_fresh_authority_denies_despite_active_request_snapshot(settings):
    _, _, prepared, resource, evidence = setup(**settings)
    try:
        with pytest.raises(PreparedAuthorizationUnsupported):
            await prepare(prepared, resource)
        assert evidence.events == []  # PREP failure is not an allow decision.
    finally:
        prepared.close()


@pytest.mark.asyncio
async def test_foreign_project_grant_does_not_prepare():
    _, repository, prepared, resource, _ = setup()
    repository.project = uuid4()
    try:
        with pytest.raises(PreparedAuthorizationUnsupported):
            await prepare(prepared, resource)
    finally:
        prepared.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("resource_id", uuid4()),
        ("scope_project_id", uuid4()),
        ("actor_profile_id", uuid4()),
        ("identity_link_id", uuid4()),
        ("locked_context_hash", "sha256:" + "b" * 64),
        ("task_status", "claimed"),
    ],
)
async def test_substituted_final_facts_cannot_consume(field, value):
    _, _, prepared, resource, evidence = setup()
    try:
        handle, request = await prepare(prepared, resource)
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await prepared.consume(
                handle, ActionId.TASK_CLAIM, request, resource.model_copy(update={field: value})
            )
        assert evidence.events == []
    finally:
        prepared.close()


@pytest.mark.asyncio
async def test_start_requires_exact_assignment_not_only_submitter_grant():
    _, _, prepared, resource, evidence = setup()
    resource = resource.model_copy(
        update={
            "task_status": "claimed",
            "assigned_to": resource.actor_profile_id,
            "assignment_id": uuid4(),
            "assignment_contributor_id": uuid4(),
        }
    )
    try:
        handle, request = await prepare(prepared, resource, ActionId.TASK_START)
        with pytest.raises(AuthorizationDenied):
            await prepared.consume(handle, ActionId.TASK_START, request, resource)
        assert len(evidence.events) == 1
        assert evidence.events[0].after_facts["allowed"] is False
    finally:
        prepared.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["assigned_to", "assignment_id", "assignment_contributor_id"])
@pytest.mark.parametrize("action", [ActionId.TASK_CLAIM, ActionId.TASK_WORK_CONTEXT_READ])
async def test_ready_task_rejects_partial_assignment_facts(action, field):
    """A project grant cannot authorize an inconsistent ready-task resource."""
    _, _, prepared, resource, evidence = setup()
    resource = resource.model_copy(update={field: uuid4()})
    try:
        handle, request = await prepare(prepared, resource, action)
        with pytest.raises(AuthorizationDenied):
            await prepared.consume(handle, action, request, resource)
        assert len(evidence.events) == 1
        assert evidence.events[0].after_facts["allowed"] is False
        assert evidence.events[0].denial_code == "resource_guard_denied"
    finally:
        prepared.close()


@pytest.mark.asyncio
async def test_commit_invalidates_prepared_task_authority():
    session, _, prepared, resource, evidence = setup()
    try:
        handle, request = await prepare(prepared, resource)
        session.root = SimpleNamespace(is_active=True)
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await prepared.consume(handle, ActionId.TASK_CLAIM, request, resource)
        assert evidence.events == []
    finally:
        prepared.close()


@pytest.mark.parametrize("identity", list(ServiceIdentity))
@pytest.mark.parametrize("operation", list(TaskAuthorityOperation))
async def test_service_task_denials_have_canonical_restageable_evidence(identity, operation):
    """Every fixed service remains denied with exact AUTH evidence, not a silent guard."""
    context = ServiceAuthorizationContext(
        actor_profile_id=uuid4(), actor_kind=ActorKind.SERVICE,
        actor_status=ActorStatus.ACTIVE, identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE, service_identity=identity,
        request_id=uuid4(), correlation_id=uuid4(),
    )
    authority = PreparedTaskAuthorization(Session(), context)
    evidence = Evidence()
    authority._kernel._audit = evidence
    facts = TaskAuthorityFacts(
        operation=operation, task_id=uuid4(), project_id=uuid4(),
        actor_profile_id=context.actor_profile_id, task_status="ready",
        assigned_to=None, assignment_id=None, assignment_contributor_id=None,
        locked_context_hash="sha256:" + "a" * 64,
    )
    with pytest.raises(TaskAuthorityDenied) as caught:
        await authority.prepare(facts)
    assert isinstance(caught.value.__cause__, AuthorizationDenied)
    decision = caught.value.__cause__.decision
    assert decision.allowed is False
    assert decision.action_id.value == operation.value
    assert decision.denial_code.value == "permission_not_granted"
    assert len(evidence.events) == 1
    first = evidence.events[0]
    assert first.project_id == str(facts.project_id)
    assert first.after_facts["resource_context_digest"].startswith("sha256:")
    evidence.events.clear()  # Simulate discarding the command transaction's stage.
    assert await authority.restage_denial(caught.value) is True
    assert len(evidence.events) == 1
    assert evidence.events[0].after_facts == first.after_facts
    assert evidence.events[0].project_id == first.project_id
