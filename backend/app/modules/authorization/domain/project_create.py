"""Internal resource context for prepared project creation authority."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectCreateResourceContext(BaseModel):
    """Server-owned facts for one system-scoped project creation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["project_create"]
    resource_id: UUID
    requested_project_id: UUID
    operation_generation: int = Field(ge=1)

    @model_validator(mode="after")
    def require_operation_identity(self):
        if self.resource_id == self.requested_project_id:
            raise ValueError("project creation operation must not impersonate project identity")
        return self
