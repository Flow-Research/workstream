"""Pure AUTH contracts for the Finance-only compensation-unit creation action."""

from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.adapters.auth.contribution_policies import ContributionPolicyAuthorization
from app.modules.authorization.api import (
    AuthorizationDenied,
    CompensationUnitCreateAuthorityFacts,
    action_id,
)
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionId, PermissionId
from app.modules.authorization.domain.action_groups import (
    CONTEXT_DIGEST_ACTIONS,
    PROJECT_SCOPED_ADMIN_MUTATIONS,
)
from app.modules.authorization.domain.audit_targets import project_authority_audit_target
from app.modules.authorization.domain.contribution_policies import (
    CONTRIBUTION_POLICY_MUTATION_ACTIONS,
    ProjectCompensationUnitCreateResourceContext,
    policy_grant_filters,
)
from app.modules.authorization.domain.prepared_contribution_policies import (
    parse_prepared_contribution_policy,
    prepared_contribution_policy_matches,
)
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
from app.modules.authorization.schemas import AdminRole
from app.modules.contributions.api import (
    CompensationUnitCreateAuthorizationFacts,
    ContributionPolicyAuthorizationDenied,
    ContributionPolicyAuthorizationUnavailable,
)

ACTION = ActionId.CONTRIBUTION_COMPENSATION_UNIT_CREATE
DIGEST = "sha256:" + "c" * 64


def _facts(**changes) -> CompensationUnitCreateAuthorityFacts:
    values = dict(
        action_id=action_id(ACTION.value), actor_profile_id=uuid4(), operation_id=uuid4(),
        request_digest=DIGEST, project_id=uuid4(), instrument_type="project_points",
        unit_code="FLOW",
    )
    values.update(changes)
    return CompensationUnitCreateAuthorityFacts(**values)


def _resource(**changes) -> ProjectCompensationUnitCreateResourceContext:
    project = uuid4()
    values = dict(
        resource_type="project", resource_id=project, scope_project_id=project,
        operation_id=uuid4(), request_digest=DIGEST, instrument_type="project_points",
        unit_code="FLOW",
    )
    values.update(changes)
    return ProjectCompensationUnitCreateResourceContext(**values)


def test_action_is_active_finance_policy_management_in_the_policy_mutation_family() -> None:
    definition = ACTION_BY_ID[ACTION]
    assert definition.permission_id is PermissionId.COMPENSATION_POLICY_MANAGE
    assert definition.availability.value == "active" and definition.owner.value == "project-points-unit-creation"
    assert ACTION in CONTRIBUTION_POLICY_MUTATION_ACTIONS
    assert ACTION in PROJECT_SCOPED_ADMIN_MUTATIONS and ACTION in CONTEXT_DIGEST_ACTIONS
    assert policy_grant_filters(ACTION) == {
        "allowed_roles": frozenset({AdminRole.FINANCE_AUTHORITY})
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"action_id": action_id("contribution.policy.create_draft")},
        {"actor_profile_id": "not-a-uuid"},
        {"operation_id": None},
        {"project_id": str(uuid4())},
        {"request_digest": "sha256:short"},
        {"request_digest": None},
        {"instrument_type": "money"},
        {"unit_code": "1FLOW"},
        {"unit_code": "F" * 33},
        {"unit_code": 7},
    ],
)
def test_public_facts_reject_other_actions_identities_digests_instruments_and_codes(
    changes: dict,
) -> None:
    with pytest.raises(ValueError):
        _facts(**changes)


def test_resource_context_binds_one_exact_project_and_points_identity() -> None:
    assert _resource().unit_code == "FLOW"
    for changes in (
        {"resource_id": uuid4()}, {"resource_type": "contribution_policy"},
        {"instrument_type": "money"}, {"unit_code": "has space"},
    ):
        with pytest.raises(ValidationError):
            _resource(**changes)


def test_prepared_custody_parses_and_matches_only_the_exact_unit_resource() -> None:
    resource = _resource()
    parsed = parse_prepared_contribution_policy(ACTION, resource.model_dump(mode="json"))
    context = parsed["contribution_policy_context"]
    digest = parsed["contribution_policy_resource_digest"]
    assert prepared_contribution_policy_matches(ACTION, context, digest, resource)
    assert not prepared_contribution_policy_matches(
        ACTION, context, digest, resource.model_copy(update={"unit_code": "OTHER"})
    )
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        parse_prepared_contribution_policy(
            ACTION, {**resource.model_dump(mode="json"), "unit_code": "bad code"}
        )
    with pytest.raises(PreparedAuthorizationHandleInvalid):
        parse_prepared_contribution_policy(
            ActionId.CONTRIBUTION_POLICY_CREATE_DRAFT, resource.model_dump(mode="json")
        )


def test_audit_target_names_only_the_owning_project() -> None:
    resource = _resource()
    project = str(resource.scope_project_id)
    assert project_authority_audit_target(resource, ACTION) == (
        project, "project", project, "project", project
    )


class _Port:
    def __init__(self, error: Exception | None = None) -> None:
        self.error, self.facts = error, []

    async def prepare_mutation(self, facts):
        self.facts.append(facts)
        if self.error is not None:
            raise self.error
        return "handle"


def _con_facts(**changes) -> CompensationUnitCreateAuthorizationFacts:
    values = dict(
        action="contribution.compensation_unit.create", actor_profile_id=uuid4(),
        operation_id=uuid4(), request_digest=DIGEST, project_id=uuid4(),
        instrument_type="project_points", unit_code="FLOW",
    )
    values.update(changes)
    return CompensationUnitCreateAuthorizationFacts(**values)


@pytest.mark.asyncio
async def test_con_adapter_translates_unit_facts_exactly() -> None:
    port, facts = _Port(), _con_facts()
    assert await ContributionPolicyAuthorization(port).prepare_contribution_policy_mutation(
        facts
    ) == "handle"
    assert port.facts == [
        CompensationUnitCreateAuthorityFacts(
            action_id=action_id(facts.action), actor_profile_id=facts.actor_profile_id,
            operation_id=facts.operation_id, request_digest=DIGEST,
            project_id=facts.project_id, instrument_type="project_points", unit_code="FLOW",
        )
    ]


@pytest.mark.asyncio
async def test_con_adapter_conceals_invalid_facts_and_auth_denial() -> None:
    with pytest.raises(ContributionPolicyAuthorizationUnavailable):
        await ContributionPolicyAuthorization(_Port()).prepare_contribution_policy_mutation(
            replace(_con_facts(), unit_code="bad code")
        )
    with pytest.raises(ContributionPolicyAuthorizationDenied):
        await ContributionPolicyAuthorization(
            _Port(AuthorizationDenied("denied"))
        ).prepare_contribution_policy_mutation(_con_facts())


def test_prepared_scope_for_the_unit_resource_is_its_exact_project() -> None:
    """PREP derives project scope through the admin project-scoped mutation path."""
    from app.modules.authorization.prepared import PreparedAuthorizationService
    from app.modules.authorization.runtime import (
        PreparedAuthorityScope,
        PreparedAuthorityScopeKind,
    )

    resource = _resource()
    assert PreparedAuthorizationService._scope_from_resource(ACTION, resource) == (
        PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT, project_id=resource.scope_project_id
        )
    )
