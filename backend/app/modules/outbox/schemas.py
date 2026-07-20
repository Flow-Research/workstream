"""Strict feature-neutral inputs and results for shared outbox append."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import re
from typing import Any, NoReturn, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    field_validator,
    model_validator,
)
from pydantic_core import SchemaValidator, core_schema

_KEY = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SECRET_KEYS = frozenset(
    {
        "access_token",
        "artifact_bytes",
        "authorization",
        "bearer_token",
        "cookie",
        "credentials",
        "id_token",
        "jwks",
        "password",
        "raw_callback",
        "raw_provider_response",
        "refresh_token",
        "request_body",
        "response_body",
        "secret",
        "signed_url",
    }
)
_SECRET_KEY_PARTS = frozenset(
    {"credential", "credentials", "password", "secret", "token"}
)
_COMPACT_SECRET_LEXEMES = (
    "credential",
    "jwt",
    "passphrase",
    "password",
    "secret",
    "token",
)
_COMPACT_KEY_LEXEMES = (
    "accesskey",
    "apikey",
    "encryptionkey",
    "keymaterial",
    "privatekey",
    "providerkey",
    "secretkey",
    "signingkey",
)
_KEY_QUALIFIERS = frozenset(
    {"access", "api", "encryption", "private", "provider", "secret", "signing"}
)
_KEY_DESCRIPTORS = frozenset({"data", "material", "payload", "value"})
_MAX_DEPTH = 16
_MAX_MEMBERS = 1024
_MAX_NODES = 4096
_MAX_KEY_BYTES = 128
_MAX_STRING_BYTES = 16_384
_MAX_ENCODING_BUDGET = 262_144
_MAX_INTEGER_MAGNITUDE = 10**38 - 1


class OutboxInputError(TypeError):
    """Raised without payload details when append input is invalid."""


class OutboxIdempotencyConflict(RuntimeError):
    """Raised without payload details when either event identity drifts."""


class OutboxPersistenceError(RuntimeError):
    """Raised without statement parameters when database persistence fails."""


class OutboxAppendDisposition(StrEnum):
    """Closed caller-visible outcomes for append or exact replay."""

    CREATED = "created"
    REPLAYED = "replayed"


def _raise_input_error() -> NoReturn:
    """Raise the public input error from a payload-free frame."""
    raise OutboxInputError("outbox_invalid_input")


def _is_sensitive_key(value: str) -> bool:
    """Reject explicit and conventionally secret-bearing JSON field names."""
    normalized = value.casefold().replace("-", "_")
    ordered_parts = tuple(normalized.split("_"))
    parts = frozenset(ordered_parts)
    key_compound = any(
        part == "key"
        and (
            (index > 0 and ordered_parts[index - 1] in _KEY_QUALIFIERS)
            or (
                index + 1 < len(ordered_parts)
                and ordered_parts[index + 1] in _KEY_DESCRIPTORS
            )
        )
        for index, part in enumerate(ordered_parts)
    )
    return (
        normalized in _SECRET_KEYS
        or bool(parts & _SECRET_KEY_PARTS)
        or normalized == "key"
        or normalized.endswith("_key")
        or key_compound
        or any(lexeme in normalized for lexeme in _COMPACT_SECRET_LEXEMES)
        or any(lexeme in normalized for lexeme in _COMPACT_KEY_LEXEMES)
    )


def _encoding_budget(value: object, *, depth: int, nodes: list[int]) -> int:
    """Return a conservative canonical UTF-8 size bound while validating JSON."""
    nodes[0] += 1
    if nodes[0] > _MAX_NODES:
        raise ValueError("payload_nodes")
    if type(value) is dict:
        if depth > _MAX_DEPTH or len(value) > _MAX_MEMBERS:
            raise ValueError("payload_container")
        budget = 2 + max(0, len(value) - 1)
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("payload_key")
            if _is_sensitive_key(key):
                raise ValueError("payload_sensitive")
            key_bytes = key.encode("utf-8")
            if len(key_bytes) > _MAX_KEY_BYTES or _KEY.fullmatch(key) is None:
                raise ValueError("payload_key")
            budget += (6 * len(key_bytes)) + 3
            budget += _encoding_budget(item, depth=depth + 1, nodes=nodes)
        return budget
    if type(value) is list:
        if depth > _MAX_DEPTH or len(value) > _MAX_MEMBERS:
            raise ValueError("payload_container")
        return 2 + max(0, len(value) - 1) + sum(
            _encoding_budget(item, depth=depth + 1, nodes=nodes) for item in value
        )
    if type(value) is str:
        encoded = value.encode("utf-8")
        if len(encoded) > _MAX_STRING_BYTES:
            raise ValueError("payload_string")
        return (6 * len(encoded)) + 2
    if value is None:
        return 4
    if type(value) is bool:
        return 5
    if type(value) is int:
        if abs(value) > _MAX_INTEGER_MAGNITUDE:
            raise ValueError("payload_integer")
        return len(str(value))
    raise ValueError("payload_type")


def validate_outbox_payload(value: object) -> dict[str, Any]:
    """Validate generic structure, privacy, and resource bounds without encoding."""
    if type(value) is not dict:
        raise ValueError("payload_object")
    if _encoding_budget(value, depth=1, nodes=[0]) > _MAX_ENCODING_BUDGET:
        raise ValueError("payload_size")
    return value


class OutboxAppendInput(BaseModel):
    """Immutable logical event facts accepted by the append participant."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )

    event_id: UUID
    event_type: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
    event_version: int = Field(ge=1, le=32767)
    aggregate_type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    aggregate_id: UUID
    project_id: UUID
    correlation_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,200}$")
    causation_event_id: UUID | None = None
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,200}$")
    payload: dict[str, Any]

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload_object(cls, value: object) -> object:
        """Reject mapping subclasses before Pydantic traverses their overrides."""
        if type(value) is not dict:
            raise ValueError("payload_object")
        return value

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        """Apply payload-free failure translation at the Pydantic core boundary."""
        inner_schema = handler(source_type)
        string_validator = SchemaValidator(inner_schema)

        def admit(
            value: object,
            validator: core_schema.ValidatorFunctionWrapHandler,
            info: core_schema.ValidationInfo,
        ) -> object:
            """Preserve validation mode while detaching every rejected input."""
            admitted = None
            try:
                admitted = (
                    string_validator.validate_strings(value)
                    if info.mode == "string"
                    else validator(value)
                )
            except Exception:  # noqa: BLE001 - rejected input must not escape diagnostics
                admitted = None
            if admitted is None:
                value = None
                validator = None
                _raise_input_error()
            return admitted

        return core_schema.with_info_wrap_validator_function(admit, inner_schema)

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        """Reject noncanonical, sensitive, or unbounded generic payloads."""
        validate_outbox_payload(self.payload)
        return self


class OutboxAppendResult(BaseModel):
    """Minimal immutable append result; operational state is not exposed."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event_id: UUID
    disposition: OutboxAppendDisposition
    payload_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    occurred_at: datetime
