"""Immutable, credential-free execution configuration for a guide attempt."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from app.core.hashing import canonical_json_hash
from app.interfaces.external_services import ExternalServiceAdapterIdentity


class ProjectGuideRuntimeConfiguration(BaseModel):
    """Exact trusted configuration captured before authorizing an attempt.

    Instructions are operator-authored evidence, never interpolated secrets or
    project material. Credentials remain with the selected provider adapter.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_key: Literal["project_guide_compilation"] = "project_guide_compilation"
    runtime_key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    model_provider: Literal["openai"]
    model: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")
    model_api: Literal["responses"]
    instruction_id: Literal["project_guide_compilation"] = "project_guide_compilation"
    instruction_version: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=16_000)
    instructions_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    timeout_seconds: StrictInt = Field(ge=1, le=7200)
    request_timeout_seconds: StrictInt = Field(default=300, ge=1, le=1800)
    maximum_retries: StrictInt = Field(default=2, ge=0, le=5)
    retry_backoff_multiplier: StrictInt = Field(default=2, ge=1, le=4)
    retry_jitter: StrictBool = True
    retry_initial_delay_seconds: StrictInt = Field(default=1, ge=1, le=30)
    retry_max_delay_seconds: StrictInt = Field(default=30, ge=1, le=120)
    circuit_failure_threshold: StrictInt = Field(default=3, ge=1, le=20)
    circuit_cooldown_seconds: StrictInt = Field(default=60, ge=1, le=600)
    maximum_manifest_bytes: StrictInt = Field(default=256_000, ge=1024, le=1_000_000)
    maximum_documents: StrictInt = Field(default=100, ge=1, le=100)
    maximum_document_bytes: StrictInt = Field(default=64 * 1024 * 1024, ge=1, le=512 * 1024 * 1024)
    maximum_total_document_bytes: StrictInt = Field(default=512 * 1024 * 1024, ge=1)
    maximum_turns: StrictInt = Field(default=40, ge=3, le=100)
    maximum_hosted_tool_calls: StrictInt = Field(default=80, ge=3, le=200)
    compaction_threshold_tokens: StrictInt = Field(default=32_000, ge=1000, le=100_000)
    container_expiry_minutes: StrictInt = Field(default=20, ge=10, le=60)
    file_expiry_seconds: StrictInt = Field(default=3600, ge=3600, le=7200)
    cleanup_timeout_seconds: StrictInt = Field(default=30, ge=5, le=120)

    @model_validator(mode="after")
    def validate_snapshot(self) -> ProjectGuideRuntimeConfiguration:
        """Bind exact instructions and coherent document limits."""
        if (
            self.instructions_sha256
            != "sha256:" + hashlib.sha256(self.instructions.encode("utf-8")).hexdigest()
        ):
            raise ValueError("project guide instruction hash mismatch")
        if self.maximum_document_bytes > self.maximum_total_document_bytes:
            raise ValueError("document byte limit exceeds the run total")
        if self.retry_initial_delay_seconds > self.retry_max_delay_seconds:
            raise ValueError("initial retry delay exceeds maximum")
        return self

    @property
    def adapter_identity(self) -> ExternalServiceAdapterIdentity:
        """Return the exact shared-factory identity selected by this attempt."""
        return ExternalServiceAdapterIdentity(self.capability_key, self.runtime_key)

    @property
    def sha256(self) -> str:
        """Hash the complete closed configuration, including exact instructions."""
        return canonical_json_hash(self.model_dump(mode="json"))
