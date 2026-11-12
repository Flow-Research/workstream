"""Immutable, credential-free execution configuration for a guide attempt."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.core.hashing import canonical_json_hash
from workstream_external_services import ExternalServiceAdapterIdentity

NO_INFERENCE_IDENTITY = "none"
"""Provider, API and model identity recorded when no inference runs."""

MAXIMUM_ADAPTER_PROFILE_BYTES = 8192
MAXIMUM_ADAPTER_PROFILE_SETTINGS = 32
MAXIMUM_ADAPTER_PROFILE_STRING_BYTES = 512
_PROFILE_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

AdapterProfileValue: TypeAlias = bool | int | str | None


def canonical_adapter_profile(profile: Mapping[str, object]) -> str:
    """Return one bounded immutable canonical JSON profile.

    The selected adapter owns the meaning and exact supported key set. Core only
    guarantees a small, deterministic scalar map whose persisted value cannot be
    mutated after the attempt is frozen.
    """
    if len(profile) > MAXIMUM_ADAPTER_PROFILE_SETTINGS:
        raise ValueError("project guide adapter profile has too many settings")
    validated: dict[str, AdapterProfileValue] = {}
    for key, value in profile.items():
        if not isinstance(key, str) or _PROFILE_KEY.fullmatch(key) is None:
            raise ValueError("project guide adapter profile key is invalid")
        if type(value) not in {bool, int, str, type(None)}:
            raise ValueError("project guide adapter profile value is invalid")
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("project guide adapter profile string contains a null character")
            if len(value.encode("utf-8")) > MAXIMUM_ADAPTER_PROFILE_STRING_BYTES:
                raise ValueError("project guide adapter profile string is too large")
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53 - 1:
            raise ValueError("project guide adapter profile integer is out of range")
        validated[key] = value
    encoded = json.dumps(
        validated,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > MAXIMUM_ADAPTER_PROFILE_BYTES:
        raise ValueError("project guide adapter profile is too large")
    return encoded


def require_project_guide_inference_identity(
    model_provider: str, model_api: str, model: str
) -> bool:
    """Require an all-``none`` or all-concrete inference identity."""
    identities = (model_provider, model_api, model)
    no_inference = all(value == NO_INFERENCE_IDENTITY for value in identities)
    if not no_inference and any(value == NO_INFERENCE_IDENTITY for value in identities):
        raise ValueError("guide runtime inference identity must be entirely none or concrete")
    return not no_inference


class ProjectGuideRuntimeConfiguration(BaseModel):
    """Exact trusted configuration captured before authorizing an attempt.

    Credentials and provider endpoints remain with the selected adapter. Its
    native controls are an immutable canonical JSON scalar map; the selected
    adapter must reject any unsupported or dishonest profile.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_key: str = Field(
        default="project_guide_compilation", pattern=r"^[a-z][a-z0-9_]{0,63}$"
    )
    runtime_key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    model_provider: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    model: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")
    model_api: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    model_profile_id: UUID | None = None
    model_profile_version: StrictInt | None = Field(default=None, ge=1)
    model_profile_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    adapter_profile: str = Field(min_length=2, max_length=MAXIMUM_ADAPTER_PROFILE_BYTES)
    instruction_id: str = Field(
        default="project_guide_compilation", pattern=r"^[a-z][a-z0-9_]{0,63}$"
    )
    instruction_version: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=16_000)
    instructions_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    timeout_seconds: StrictInt = Field(ge=1, le=7200)
    maximum_manifest_bytes: StrictInt = Field(default=512_000, ge=1024, le=1_000_000)
    maximum_documents: StrictInt = Field(default=100, ge=1, le=100)
    maximum_document_bytes: StrictInt = Field(default=64 * 1024 * 1024, ge=1, le=512 * 1024 * 1024)
    maximum_total_document_bytes: StrictInt = Field(default=512 * 1024 * 1024, ge=1)
    maximum_turns: StrictInt = Field(default=40, ge=3, le=100)
    maximum_tool_calls: StrictInt = Field(default=80, ge=3, le=200)
    maximum_tool_output_characters: StrictInt = Field(
        default=4 * 1024 * 1024, ge=65_536, le=16 * 1024 * 1024
    )

    @model_validator(mode="after")
    def validate_snapshot(self) -> ProjectGuideRuntimeConfiguration:
        """Bind exact instructions, profile canonicality and coherent limits."""
        if (
            self.instructions_sha256
            != "sha256:" + hashlib.sha256(self.instructions.encode("utf-8")).hexdigest()
        ):
            raise ValueError("project guide instruction hash mismatch")
        if self.maximum_document_bytes > self.maximum_total_document_bytes:
            raise ValueError("document byte limit exceeds the run total")
        uses_inference = require_project_guide_inference_identity(
            self.model_provider, self.model_api, self.model
        )
        selector = (
            self.model_profile_id,
            self.model_profile_version,
            self.model_profile_digest,
        )
        if any(value is not None for value in selector) and not all(
            value is not None for value in selector
        ):
            raise ValueError("guide runtime model profile selector is incomplete")
        if not uses_inference and any(value is not None for value in selector):
            raise ValueError("provider-free guide runtime cannot select a model profile")
        try:
            profile = json.loads(self.adapter_profile)
        except (TypeError, ValueError):
            raise ValueError("project guide adapter profile is invalid") from None
        if (
            not isinstance(profile, dict)
            or canonical_adapter_profile(profile) != self.adapter_profile
        ):
            raise ValueError("project guide adapter profile is not canonical")
        return self

    @property
    def uses_inference(self) -> bool:
        """Return whether this attempt invokes an inference provider."""
        return require_project_guide_inference_identity(
            self.model_provider, self.model_api, self.model
        )

    def adapter_profile_values(self) -> dict[str, AdapterProfileValue]:
        """Return a fresh parsed copy for validation by the selected adapter."""
        values = json.loads(self.adapter_profile)
        return dict(values)

    @property
    def adapter_identity(self) -> ExternalServiceAdapterIdentity:
        """Return the exact shared-factory identity selected by this attempt."""
        return ExternalServiceAdapterIdentity(self.capability_key, self.runtime_key)

    @property
    def sha256(self) -> str:
        """Hash the complete closed configuration, including exact instructions."""
        return canonical_json_hash(self.model_dump(mode="json"))
