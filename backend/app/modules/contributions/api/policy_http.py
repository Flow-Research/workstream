"""Closed delivery inputs using the canonical owner rule graph."""

from pydantic import BaseModel, ConfigDict, Field

from app.modules.contributions.api.policies import PolicyRuleInput


class PolicyCreateInput(BaseModel):
    """Name the first or next draft; actor and operation come from the request."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=200)


class PolicyUpdateInput(BaseModel):
    """Replace the complete graph without client-generated row identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    rules: tuple[PolicyRuleInput, ...] = Field(min_length=2, max_length=2)


class PolicyDecisionInput(BaseModel):
    """An explicit decision on the path-selected version; no replacement graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)
