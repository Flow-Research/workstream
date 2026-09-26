"""Scope locking preserves exact authorization without issuing mutation power."""

from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.modules.authorization.api import AuthorizationDenied, PreparedAuthorizationInvalid, action_id
from app.modules.authorization.catalogue import ActionId, ServiceIdentity
from app.modules.authorization.runtime import (
    PreparedAuthorityScope, PreparedAuthorityScopeKind, PreparedAuthorizationUnsupported,
    ActorKind, ServiceAuthorizationContext,
)
from tests.authorization.test_adapter_binding_authorization import _adapter, _facts_for_action
from .fixtures import adapter, mutation

ACTIONS = tuple("contribution.policy." + name for name in (
    "create_draft", "update_draft", "publish", "retire",
)) + tuple("compensation.adapter_binding." + name for name in ("create", "suspend", "resume"))


def subject(action, project, **kwargs):
    """Use actual AUTH/PREP owners with the bounded Finance repository."""
    return (adapter if action.startswith("contribution") else _adapter)(project, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ACTIONS)
async def test_scope_locks_all_authority_without_handle_or_evidence(action, monkeypatch):
    project = uuid4()
    auth, context, _, evidence = subject(action, project)
    order = []
    repository = auth._authorization._admin
    for method, label in (("lock_control", "control"), ("lock_request_actor", "actor"),
                          ("find_effective_grant", "grant")):
        original = getattr(repository, method)

        async def recorded(*args, original=original, label=label, **kwargs):
            order.append(label)
            return await original(*args, **kwargs)

        monkeypatch.setattr(repository, method, recorded)
    assert await auth.lock_mutation_scope(
        action_id=action_id(action), actor_profile_id=context.actor_profile_id, project_id=project,
    ) is None
    assert order == ["control", "actor", "grant"]
    assert not auth._prepared._issued and not auth._authorization._sealed_prelocked
    assert evidence.events == []
    facts = (mutation(context.actor_profile_id, project, action.rsplit(".", 1)[1])
             if action.startswith("contribution") else
             _facts_for_action(context.actor_profile_id, project, action))
    with pytest.raises(PreparedAuthorizationInvalid):
        await auth.consume_mutation(object(), facts)
    assert evidence.events == []
    handle = await auth.prepare_mutation(facts)
    assert await auth.consume_mutation(handle, facts) == context.actor_profile_id
    auth.close_mutation(handle)
    assert not auth._prepared._issued and not auth._authorization._sealed_prelocked
    assert evidence.events


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("failure", ("actor", "project", "missing_grant", "invalid_project", "invalid_actor", "service"))
async def test_scope_substitution_denies_without_capability(action, failure):
    project = uuid4()
    auth, context, _, evidence = subject(action, project, grant_available=failure != "missing_grant")
    auth._authorization._admin.project_exists = AsyncMock(return_value=True)
    if failure == "service":
        auth._authorization._context = auth._prepared._context = ServiceAuthorizationContext(
            actor_profile_id=context.actor_profile_id, actor_kind=ActorKind.SERVICE,
            actor_status=context.actor_status, identity_link_id=context.identity_link_id,
            identity_link_status=context.identity_link_status,
            service_identity=ServiceIdentity.ARTIFACT_MATERIALIZER,
            request_id=context.request_id, correlation_id=context.correlation_id,
        )
    with pytest.raises(AuthorizationDenied):
        await auth.lock_mutation_scope(
            action_id=action_id(action), actor_profile_id="invalid" if failure == "invalid_actor"
            else uuid4() if failure == "actor" else context.actor_profile_id,
            project_id="invalid" if failure == "invalid_project" else
            uuid4() if failure == "project" else project,
        )
    assert not auth._prepared._issued and not auth._authorization._sealed_prelocked
    scoped_denial = action.startswith("contribution") and failure in {"project", "missing_grant"}
    if scoped_denial:
        assert len(evidence.events) == 1
        assert evidence.events[0].after_facts["allowed"] is False
        assert evidence.events[0].action_id == action
        assert evidence.events[0].resource_type == "project"
        auth._authorization._admin.project_exists.assert_awaited_once()
    else:
        assert evidence.events == []
        auth._authorization._admin.project_exists.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ("contribution.policy.publish", "compensation.adapter_binding.suspend"))
@pytest.mark.parametrize("failure", ("no_root", "inactive", "nested", "wrong_action", "repository"))
async def test_scope_failure_leaves_no_partial_authority(family, failure, monkeypatch):
    project = uuid4()
    auth, context, session, evidence = subject(family, project)
    if failure == "no_root":
        session.root = None
    elif failure == "inactive":
        session.root.is_active = False
    elif failure == "nested":
        monkeypatch.setattr(session, "in_nested_transaction", lambda: True)
    elif failure == "repository":
        async def broken(*args, **kwargs):
            raise RuntimeError("authority source failed")
        monkeypatch.setattr(auth._authorization._admin, "find_effective_grant", broken)
    expected = RuntimeError if failure == "repository" else (
        AuthorizationDenied if failure == "wrong_action" else PreparedAuthorizationInvalid
    )
    with pytest.raises(expected):
        await auth.lock_mutation_scope(
            action_id=action_id("project.read" if failure == "wrong_action" else family),
            actor_profile_id=context.actor_profile_id, project_id=project,
        )
    assert not auth._prepared._issued and not auth._authorization._sealed_prelocked
    assert evidence.events == []


@pytest.mark.asyncio
async def test_prep_scope_cannot_lock_other_actions_or_system_scope():
    auth, _, _, _ = adapter(uuid4())
    for action, scope in (
        (ActionId.PROJECT_ROLE_GRANT_ISSUE, PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT, project_id=uuid4())),
        (ActionId.CONTRIBUTION_POLICY_PUBLISH, PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.SYSTEM)),
    ):
        with pytest.raises(PreparedAuthorizationUnsupported):
            await auth._prepared.lock_mutation_scope(action, scope)
    assert not auth._prepared._issued and not auth._authorization._sealed_prelocked
