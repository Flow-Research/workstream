"""Canonical task-import JSON, validated before ART durable admission."""

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError


TASK_IMPORT_MAXIMUM_BYTES = 8 * 1024 * 1024


class TaskImportRow(BaseModel):
    """Task instructions only; source custody and record IDs are server-owned."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    external_task_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=50000)
    task_type: str | None = Field(default=None, max_length=80)
    difficulty: str | None = Field(default=None, max_length=80)
    skill_tags: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=100)
    estimated_time_minutes: int | None = Field(default=None, ge=1, le=525600)
    acceptance_criteria: str | None = Field(default=None, max_length=50000)
    rejection_criteria: str | None = Field(default=None, max_length=50000)

    @field_validator("*", mode="after")
    @classmethod
    def valid_text(cls, value):
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, str):
                if "\x00" in item:
                    raise ValueError("text must not contain NUL")
                try:
                    item.encode("utf-8")
                except UnicodeError as exc:
                    raise ValueError("text must contain valid Unicode") from exc
        return value

    @field_validator("external_task_id")
    @classmethod
    def exact_external_id(cls, value: str) -> str:
        if value != value.strip() or any(unicodedata.category(char) == "Cc" for char in value):
            raise ValueError("external_task_id must have no surrounding whitespace or control characters")
        return value

    @field_validator("title", "description")
    @classmethod
    def nonblank_instructions(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task instructions must not be blank")
        return value

    @field_validator("skill_tags")
    @classmethod
    def bounded_tags(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 200 for value in values):
            raise ValueError("skill_tags must contain nonblank strings of at most 200 characters")
        return values


class TaskImportMetadata(BaseModel):
    """Optional display label; provenance commitments remain server-owned."""
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    label: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("label")
    @classmethod
    def valid_label(cls, value: str | None) -> str | None:
        """Reject labels that cannot be retained as PostgreSQL UTF-8 text."""
        if value is not None:
            TaskImportRow.valid_text(value)
        return value


class TaskImportDocument(BaseModel):
    """One bounded, canonical input format for future atomic DRAFT import."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["workstream.task_import.v1"]
    metadata: TaskImportMetadata = Field(default_factory=TaskImportMetadata)
    tasks: list[TaskImportRow] = Field(min_length=1, max_length=500)


@dataclass(frozen=True)
class ParsedTaskImport:
    document: TaskImportDocument
    sha256: str
    byte_count: int


def _object_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object member")
        result[key] = value
    return result


def _reject_nonfinite(_: str) -> None:
    raise ValueError("non-finite JSON numbers are invalid")


def parse_task_import(raw: bytes) -> ParsedTaskImport:
    """Preserve exact bytes while rejecting ambiguous JSON and indexed row errors."""
    if type(raw) is not bytes or not 0 < len(raw) <= TASK_IMPORT_MAXIMUM_BYTES:
        raise ValueError("task-import JSON must contain 1..8388608 bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_members, parse_constant=_reject_nonfinite)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the parser limit") from exc
    document = TaskImportDocument.model_validate(value)
    seen = {}
    errors = []
    for index, row in enumerate(document.tasks):
        if row.external_task_id in seen:
            errors.append({
                "type": PydanticCustomError("duplicate_external_task_id", "external_task_id duplicates row {first_row}",
                                            {"first_row": seen[row.external_task_id]}),
                "loc": ("tasks", index, "external_task_id"), "input": row.external_task_id,
            })
        else:
            seen[row.external_task_id] = index
    if errors:
        raise ValidationError.from_exception_data("TaskImportDocument", errors)
    return ParsedTaskImport(document, "sha256:" + hashlib.sha256(raw).hexdigest(), len(raw))


def task_import_json_schema() -> dict:
    schema = TaskImportDocument.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["description"] = (
        "UTF-8 JSON source, maximum 8388608 bytes. Object member names must be unique. "
        "external_task_id is required, case-sensitive, with no surrounding whitespace/control characters; "
        "IDs must be unique across rows. Atomic TASK import additionally rejects existing project IDs. "
        "Client conversions map category to task_type, languages/tools to skill_tags, and source ID to external_task_id. "
        "The received JSON is the retained server source, not the original CSV."
    )
    return schema
