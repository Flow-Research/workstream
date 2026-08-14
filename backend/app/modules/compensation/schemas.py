"""Closed persistence inputs for compensation adapter bindings."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.compensation.api.adapter_bindings import validate_adapter_route_key


class CompensationInstrumentType(StrEnum):
    """Canonical compensation instrument families."""

    MONEY = "money"
    PROJECT_POINTS = "project_points"


class ProjectCompensationAdapterBindingInput(BaseModel):
    """Creation-only binding facts; this input grants no authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    project_id: str = Field(pattern=r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
    instrument_type: CompensationInstrumentType
    adapter_actor_id: str = Field(pattern=r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
    route_key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9._:-]{0,119}$")
    created_by: str = Field(pattern=r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")

    @field_validator("route_key")
    @classmethod
    def reject_path_traversal(cls, value: str) -> str:
        """Apply the canonical CON-owned route-key grammar."""
        return validate_adapter_route_key(value)
