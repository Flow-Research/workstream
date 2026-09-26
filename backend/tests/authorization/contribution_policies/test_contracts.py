"""Public fact validation, boundary translation and deny-default composition."""

from dataclasses import replace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.auth.contribution_policies import ContributionPolicyAuthorization
from app.modules.authorization.api import (
    AuthorizationDenied, AuthorizationUnavailable,
    ContributionPolicyReadFacts,
    PreparedAuthorizationInvalid,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.prepared_contribution_policies import (
    parse_prepared_contribution_policy,
)
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
from app.modules.contributions.api import (
    ContributionPolicyMutationAuthorizationFacts,
    ContributionPolicyPublishAuthorizationFacts,
    ContributionPolicyRetireAuthorizationFacts,
    ContributionPolicyReadRequest,
    ContributionPolicyAuthorizationDenied, ContributionPolicyAuthorizationUnavailable,
)
from .fixtures import ACTIONS, adapter, mutation


def con_facts(facts, operation):
    """Construct CON's existing public facts independently of AUTH translation."""
    common = dict(
        action="contribution.policy." + operation,
        actor_profile_id=facts.actor_profile_id,
        operation_id=facts.operation_id,
        request_digest=facts.request_digest,
        project_id=facts.project_id,
        contribution_policy_id=facts.contribution_policy_id,
        contribution_policy_version_id=facts.contribution_policy_version_id,
        expected_policy_status=facts.expected_policy_status,
        expected_version_status=facts.expected_version_status,
    )
    if operation == "publish":
        return ContributionPolicyPublishAuthorizationFacts(
            **common,
            rules_and_definitions_digest=facts.resource_facts.rules_and_definitions_digest,
            adapter_binding_ids=facts.resource_facts.adapter_binding_ids,
        )
    if operation == "retire":
        return ContributionPolicyRetireAuthorizationFacts(**common)
    return ContributionPolicyMutationAuthorizationFacts(**common)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ACTIONS)
async def test_public_adapter_translates_exact_con_facts_through_real_auth(operation):
    project = uuid4()
    auth, context, _, _ = adapter(project)
    bridge = ContributionPolicyAuthorization(auth)
    facts = mutation(context.actor_profile_id, project, operation)
    value = con_facts(facts, operation)
    assert bridge._facts(value) == facts
    handle = await bridge.prepare_contribution_policy_mutation(value)
    assert (
        await bridge.consume_contribution_policy_mutation(handle, value) == context.actor_profile_id
    )
    bridge.close_contribution_policy_mutation(handle)
    await bridge.authorize_contribution_policy_read(
        ContributionPolicyReadRequest(
            actor_profile_id=context.actor_profile_id,
            project_id=project,
            contribution_policy_id=facts.contribution_policy_id,
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("read", "scope", "prepare", "consume", "close"))
@pytest.mark.parametrize("failure", (AuthorizationDenied, AuthorizationUnavailable, PreparedAuthorizationInvalid, ValueError))
async def test_public_adapter_preserves_authority_failure_classification(method, failure):
    facts = mutation(uuid4(), uuid4())
    port = Mock(
        authorize_read=AsyncMock(side_effect=failure("private")),
        lock_mutation_scope=AsyncMock(side_effect=failure("private")),
        prepare_mutation=AsyncMock(side_effect=failure("private")),
        consume_mutation=AsyncMock(side_effect=failure("private")),
        close_mutation=Mock(side_effect=failure("private")),
    )
    bridge = ContributionPolicyAuthorization(port)
    with pytest.raises(
        ContributionPolicyAuthorizationDenied if failure is AuthorizationDenied else ContributionPolicyAuthorizationUnavailable,
        match="^contribution_policy_unavailable$",
    ):
        if method == "read":
            await bridge.authorize_contribution_policy_read(
                ContributionPolicyReadRequest(
                    actor_profile_id=facts.actor_profile_id,
                    project_id=facts.project_id,
                    contribution_policy_id=facts.contribution_policy_id,
                )
            )
        elif method == "scope":
            await bridge.lock_contribution_policy_mutation_scope(
                action="contribution.policy.create_draft", actor_profile_id=facts.actor_profile_id,
                project_id=facts.project_id,
            )
        elif method == "prepare":
            await bridge.prepare_contribution_policy_mutation(con_facts(facts, "create_draft"))
        elif method == "consume":
            await bridge.consume_contribution_policy_mutation(
                object(), con_facts(facts, "create_draft")
            )
        else:
            bridge.close_contribution_policy_mutation(object())


@pytest.mark.parametrize(
    "field,value",
    (
        ("action_id", "contribution.policy.read"),
        ("actor_profile_id", "invalid"),
        ("request_digest", "invalid"),
        ("expected_policy_status", "retired"),
        ("expected_version_status", "draft"),
    ),
)
def test_public_mutation_facts_reject_invalid_creation_fields(field, value):
    with pytest.raises(ValueError):
        replace(mutation(uuid4(), uuid4()), **{field: value})


@pytest.mark.parametrize("operation", ("update_draft", "publish", "retire"))
@pytest.mark.parametrize(
    "field",
    (
        "contribution_policy_id",
        "contribution_policy_version_id",
        "expected_version_status",
        "expected_policy_status",
    ),
)
def test_public_mutation_facts_reject_mismatched_existing_lineage(operation, field):
    facts = mutation(uuid4(), uuid4(), operation)
    with pytest.raises(ValueError):
        replace(facts, **{field: uuid4() if field.endswith("_id") else None})


def test_prepared_parser_rejects_malformed_values_and_ignores_other_actions():
    assert parse_prepared_contribution_policy(ActionId.REVIEW_QUEUE_READ, {}) == {}
    for value in ({}, {"resource_id": "invalid"}):
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            parse_prepared_contribution_policy(ActionId.CONTRIBUTION_POLICY_CREATE_DRAFT, value)


@pytest.mark.asyncio
async def test_read_actor_substitution_and_invalid_handles_deny():
    project = uuid4()
    auth, context, _, _ = adapter(project)
    with pytest.raises(AuthorizationDenied):
        await auth.authorize_read(
            actor_profile_id=uuid4(),
            facts=ContributionPolicyReadFacts(project_id=project, contribution_policy_id=uuid4()),
        )
    with pytest.raises(PreparedAuthorizationInvalid):
        await auth.consume_mutation(object(), mutation(context.actor_profile_id, project))
    with pytest.raises(PreparedAuthorizationInvalid):
        auth.close_mutation(object())


@pytest.mark.parametrize("raw", ("unknown.action", "contribution.policy.read"))
def test_policy_adapter_rejects_unregistered_mutation_actions(raw):
    auth, _, _, _ = adapter(uuid4())
    with pytest.raises(AuthorizationDenied):
        auth._action(raw)
    with pytest.raises(AuthorizationDenied):
        auth._mutation_context(object())


def test_policy_adapter_rejects_foreign_prepared_composition():
    from app.modules.authorization.contribution_policy_authorization import (
        ContributionPolicyAuthorizationAdapter,
    )

    first, _, _, _ = adapter(uuid4())
    second, _, _, _ = adapter(uuid4())
    with pytest.raises(TypeError, match="requires one composition"):
        ContributionPolicyAuthorizationAdapter(first._authorization, second._prepared)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("read", "create_draft"))
async def test_policy_audit_failure_conceals_and_denies_authority(operation):
    from sqlalchemy.exc import OperationalError
    from app.modules.authorization.api import AuthorizationUnavailable

    project = uuid4()
    auth, context, _, evidence = adapter(project)
    evidence.add_authority_event = AsyncMock(
        side_effect=OperationalError("audit", {}, RuntimeError())
    )
    with pytest.raises(
        AuthorizationUnavailable, match="^contribution-policy authority unavailable$"
    ):
        if operation == "read":
            await auth.authorize_read(
                actor_profile_id=context.actor_profile_id,
                facts=ContributionPolicyReadFacts(
                    project_id=project, contribution_policy_id=uuid4()
                ),
            )
        else:
            facts = mutation(context.actor_profile_id, project)
            handle = await auth.prepare_mutation(facts)
            await auth.consume_mutation(handle, facts)


@pytest.mark.asyncio
async def test_scope_existence_failure_is_unavailable_without_denial():
    from sqlalchemy.exc import SQLAlchemyError
    project = uuid4()
    auth, context, _, evidence = adapter(project, grant_available=False)
    auth._authorization._admin.project_exists = AsyncMock(side_effect=SQLAlchemyError("private"))
    with pytest.raises(AuthorizationUnavailable, match="^contribution-policy authority unavailable$"):
        await auth.lock_mutation_scope(action_id=ActionId.CONTRIBUTION_POLICY_CREATE_DRAFT,
            actor_profile_id=context.actor_profile_id, project_id=project)
    assert evidence.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ("action", "input", "project", "policy"))
async def test_scope_denial_rejects_substituted_or_invented_facts(invalid):
    from pydantic import ValidationError
    from app.modules.authorization.domain.contribution_policies import ContributionPolicyMutationScopeDenialResourceContext
    from app.modules.authorization.runtime import (
        AuthorizationDenialCode, PreparedAuthorizationInput, PreparedAuthorizationUnsupported,
    )
    project = uuid4()
    auth, _, _, evidence = adapter(project, grant_available=False)
    values = dict(resource_type="project", resource_id=project, scope_project_id=project,
        project_exists=True, requested_action=ActionId.CONTRIBUTION_POLICY_CREATE_DRAFT)
    if invalid in {"project", "policy"}:
        values.update({"resource_id": uuid4()} if invalid == "project" else {"contribution_policy_id": uuid4()})
        with pytest.raises(ValidationError):
            ContributionPolicyMutationScopeDenialResourceContext(**values)
    else:
        context = ContributionPolicyMutationScopeDenialResourceContext(**values)
        caller_input = PreparedAuthorizationInput(idempotency_key=uuid4(), request_value={}) if invalid == "input" else None
        action = ActionId.CONTRIBUTION_POLICY_RETIRE if invalid == "action" else ActionId.CONTRIBUTION_POLICY_CREATE_DRAFT
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await auth._prepared.deny_unsupported(action, caller_input, context,
                PreparedAuthorizationUnsupported(AuthorizationDenialCode.PERMISSION_NOT_GRANTED))
    assert evidence.events == []
