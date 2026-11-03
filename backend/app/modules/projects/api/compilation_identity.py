"""Shared immutable component identity for compilation and proposal review."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompilationComponentHashes(BaseModel):
    """Named canonical hashes for every independently projected component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["project_guide_check_specification_hashes.v1"] = (
        "project_guide_check_specification_hashes.v1"
    )

    sufficiency_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    requirement_inventory_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    pre_submit_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    post_submit_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
