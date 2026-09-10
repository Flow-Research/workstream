"""Public immutable pre-submission capability projection owned by CHECKERS."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ResourceBudget(BaseModel):
    """Frozen canonical ART resource budget."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    maximum_results: StrictInt = Field(ge=1)


class PreSubmissionCapabilityDefinition(BaseModel):
    """Exact read-only projection of one ART catalogue definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stable_id: str
    version: str
    public_name: str
    owner: str
    phase: str
    order: int = Field(ge=0)
    dependencies: tuple[str, ...]
    classification: str
    typed_inputs: tuple[str, ...]
    result_schema: str
    failure_code: str
    resource_budget: ResourceBudget
    state: Literal["enabled", "disabled"]
    disabled_behavior: str
    policy_trace_source: str
    dispatch_kind: Literal["platform_capability", "policy_primitive"]
    dispatch_capability: str
    primitive: str | None = None
    policy_fields: tuple[str, ...] = ()
    selectable: bool


class PreSubmissionCapabilityProjection(BaseModel):
    """Complete immutable ART catalogue plus model-facing selectability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalogue_id: Literal["workstream.pre_submission_checkers"]
    version: Literal["v0.1"]
    schema_version: Literal["pre_submission_checker_catalogue.v1"]
    manifest_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    available: bool
    definitions: tuple[PreSubmissionCapabilityDefinition, ...]
