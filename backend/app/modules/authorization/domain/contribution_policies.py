"""Exact action-specific ContributionPolicy authorization resources."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.catalogue import ActionId


class ContributionPolicyMutationScopeDenialResourceContext(BaseModel):
    """Refused project scope before any policy/version facts exist."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["project"]
    resource_id: UUID
    scope_project_id: UUID
    project_exists: bool
    requested_action: Literal[
        ActionId.CONTRIBUTION_POLICY_CREATE_DRAFT,
        ActionId.CONTRIBUTION_POLICY_UPDATE_DRAFT,
        ActionId.CONTRIBUTION_POLICY_PUBLISH,
        ActionId.CONTRIBUTION_POLICY_RETIRE,
    ]

    @model_validator(mode="after")
    def exact_project(self):
        """Bind the refused scope to the requested project only."""
        if self.resource_id != self.scope_project_id:
            raise ValueError("scope denial requires one exact project")
        return self


class ContributionPolicyReadResourceContext(BaseModel):
    """One scoped policy and optional immutable version disclosure."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["contribution_policy"]
    resource_id: UUID
    scope_project_id: UUID
    contribution_policy_version_id: UUID | None
    resource_facts_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ContributionPolicyMutationResourceContext(BaseModel):
    """Common exact mutation custody; never registered as an action resource."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["contribution_policy"]
    resource_id: UUID
    scope_project_id: UUID
    contribution_policy_version_id: UUID
    operation_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    resource_facts_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ContributionPolicyCreateResourceContext(ContributionPolicyMutationResourceContext):
    """New draft identity and exact predecessor aggregate state."""

    expected_policy_status: Literal["draft", "active"] | None
    expected_version_status: None


class ContributionPolicyUpdateResourceContext(ContributionPolicyMutationResourceContext):
    """Exact existing draft replacement."""

    expected_policy_status: Literal["draft", "active"]
    expected_version_status: Literal["draft"]


class ContributionPolicyPublishResourceContext(ContributionPolicyMutationResourceContext):
    """Exact publication graph and eligible binding identities."""

    expected_policy_status: Literal["draft", "active"]
    expected_version_status: Literal["draft"]
    rules_and_definitions_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    adapter_binding_ids: tuple[UUID, ...]


class ContributionPolicyRetireResourceContext(ContributionPolicyMutationResourceContext):
    """Exact current published version retirement."""

    expected_policy_status: Literal["active"]
    expected_version_status: Literal["published"]


CONTRIBUTION_POLICY_RESOURCE_BY_ACTION = {
    ActionId.CONTRIBUTION_POLICY_READ: ContributionPolicyReadResourceContext,
    ActionId.CONTRIBUTION_POLICY_CREATE_DRAFT: ContributionPolicyCreateResourceContext,
    ActionId.CONTRIBUTION_POLICY_UPDATE_DRAFT: ContributionPolicyUpdateResourceContext,
    ActionId.CONTRIBUTION_POLICY_PUBLISH: ContributionPolicyPublishResourceContext,
    ActionId.CONTRIBUTION_POLICY_RETIRE: ContributionPolicyRetireResourceContext,
}
CONTRIBUTION_POLICY_READ_ACTIONS = frozenset({ActionId.CONTRIBUTION_POLICY_READ})
CONTRIBUTION_POLICY_ACTIONS = frozenset(CONTRIBUTION_POLICY_RESOURCE_BY_ACTION)
CONTRIBUTION_POLICY_MUTATION_ACTIONS = (
    CONTRIBUTION_POLICY_ACTIONS - CONTRIBUTION_POLICY_READ_ACTIONS
)


def policy_finance_grant_filters(action_id: ActionId) -> dict[str, object]:
    """Confine the five policy actions to Finance Authority grants."""
    if action_id not in CONTRIBUTION_POLICY_ACTIONS:
        return {}
    from app.modules.authorization.schemas import AdminRole

    return {"allowed_roles": frozenset({AdminRole.FINANCE_AUTHORITY})}
