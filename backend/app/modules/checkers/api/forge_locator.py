"""Untrusted, request-bound forge selectors returned by an offline project image."""

from __future__ import annotations

import json
import unicodedata
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictStr, ValidationError, model_validator

from app.modules.checkers.api.external import (
    ExternalCheckerContractError,
    ExternalCheckerExecutionRequest,
    ExternalCheckerValue,
    MAX_RESULT_BYTES,
    Sha256,
    external_checker_json_hash,
)

FORGE_LOCATOR_STAGE_KEY = "workstream_forge_facts_stage"
FORGE_LOCATOR_SCHEMA = "external_checker_forge_locator.v1"


def require_forge_locator_request(request: ExternalCheckerExecutionRequest) -> None:
    """Require an explicitly declared, locked POST capability, never URL authority."""
    properties = request.registry.input_schema.document.get("properties", {})
    if (
        request.identity.phase != "post_submit"
        or request.input.get(FORGE_LOCATOR_STAGE_KEY) != "locate"
        or request.configuration.get("workstream_forge_facts_version") != "v1"
        or not isinstance(properties, dict)
        or not isinstance(properties.get(FORGE_LOCATOR_STAGE_KEY), dict)
        or properties[FORGE_LOCATOR_STAGE_KEY].get("const") != "locate"
    ):
        raise ExternalCheckerContractError("forge locator request is not selected")


class ExternalCheckerForgeLocator(ExternalCheckerValue):
    """One image-selected URL, with no verdict or permission to fetch it."""

    schema_version: Literal["external_checker_forge_locator.v1"] = FORGE_LOCATOR_SCHEMA
    request_digest: Sha256
    registry_entry_id: UUID = Field(strict=True)
    registry_entry_digest: Sha256
    phase: Literal["post_submit"]
    change_url: Annotated[StrictStr, Field(min_length=1, max_length=2048)] | None
    locator_digest: Sha256

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        if self.change_url is not None and any(
            unicodedata.category(char) in {"Cc", "Cs"} for char in self.change_url
        ):
            raise ExternalCheckerContractError("forge locator contains invalid characters")
        if (
            external_checker_json_hash(self.model_dump(mode="json", exclude={"locator_digest"}))
            != self.locator_digest
        ):
            raise ExternalCheckerContractError("forge locator digest differs")
        return self

    def validate_request(self, request: ExternalCheckerExecutionRequest) -> None:
        try:
            ExternalCheckerForgeLocator.model_validate(self)
        except ValidationError as exc:
            raise ExternalCheckerContractError("forge locator contract is invalid") from exc
        require_forge_locator_request(request)
        if (
            self.request_digest != request.request_digest
            or self.registry_entry_id != request.registry.registry_entry_id
            or self.registry_entry_digest != request.registry.entry_digest
        ):
            raise ExternalCheckerContractError("forge locator request identity differs")
        value = self.model_dump(mode="json")
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        if len(encoded) > min(MAX_RESULT_BYTES, request.registry.resources.maximum_output_bytes):
            raise ExternalCheckerContractError("forge locator exceeds output bound")
        request.registry.output_schema.validate_instance(value)
