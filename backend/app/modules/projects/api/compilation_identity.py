"""Shared immutable component identity for compilation and proposal review."""

from pydantic import BaseModel, ConfigDict, Field


class CompilationComponentHashes(BaseModel):
    """Named canonical hashes for every independently projected component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sufficiency_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    requirement_inventory_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    pre_submit_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    post_submit_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    capability_suggestions_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    setup_notes_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
