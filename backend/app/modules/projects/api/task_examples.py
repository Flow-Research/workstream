"""Required illustrative task text owned by one immutable guide version."""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from app.core.hashing import canonical_json_hash

MAXIMUM_TASK_EXAMPLE_BYTES = 128 * 1024
TASK_EXAMPLES_HASH_DOMAIN = "workstream.project_guide.task_examples"


class GuideTaskExampleInputError(ValueError):
    """An unavailable setup input, never a model sufficiency judgment."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ProjectGuideTaskExample(BaseModel):
    """A starting idea or fuller description; project rules belong in the guide."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(min_length=1, max_length=65_536)
    title: str | None = Field(default=None, max_length=500)
    labels: tuple[Annotated[str, Field(min_length=1, max_length=100)], ...] = Field(
        default=(), max_length=20,
    )

    @field_validator("content")
    @classmethod
    def require_meaningful_content(cls, value: str) -> str:
        """Reject whitespace-only examples without rewriting meaningful text."""
        if not value.strip():
            raise ValueError("task example content must not be blank")
        return value

    @model_validator(mode="after")
    def require_storable_text(self) -> ProjectGuideTaskExample:
        """Reject text PostgreSQL cannot represent before any creation effects."""
        for value in (self.content, self.title, *self.labels):
            if value is not None:
                if "\x00" in value:
                    raise ValueError("task example text cannot contain a null character")
                value.encode("utf-8")
        return self


def _bounded_examples(
    examples: tuple[ProjectGuideTaskExample, ...],
) -> tuple[ProjectGuideTaskExample, ...]:
    """Bound aggregate prompt input independently of individual field limits."""
    encoded = json.dumps(
        [item.model_dump(mode="json") for item in examples],
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAXIMUM_TASK_EXAMPLE_BYTES:
        raise ValueError("task examples exceed the aggregate byte limit")
    return examples


ProjectGuideTaskExamples = Annotated[
    tuple[ProjectGuideTaskExample, ...],
    Field(min_length=1, max_length=100),
    AfterValidator(_bounded_examples),
]

_EXAMPLES = TypeAdapter(ProjectGuideTaskExamples)


def validate_task_examples(value: object) -> tuple[ProjectGuideTaskExample, ...]:
    """Use the same required shape for requests and persisted source reconstruction."""
    return _EXAMPLES.validate_python(value)


def task_examples_hash(examples: tuple[ProjectGuideTaskExample, ...]) -> str:
    """Commit to every example's exact text, optional metadata and list order."""
    return canonical_json_hash({
        "domain": TASK_EXAMPLES_HASH_DOMAIN,
        "task_examples": [item.model_dump(mode="json") for item in examples],
    })


def require_task_example_commitment(
    value: object, expected_hash: str | None, *, manifest: dict | None = None,
) -> tuple[ProjectGuideTaskExample, ...]:
    """Reconstruct immutable guide input and optionally bind its exact snapshot."""
    try:
        examples = validate_task_examples(value)
    except ValueError:
        raise GuideTaskExampleInputError(
            "task_examples_missing" if value is None else "task_examples_invalid",
        ) from None
    digest = task_examples_hash(examples)
    if digest != expected_hash:
        raise GuideTaskExampleInputError("task_examples_invalid")
    if manifest is not None and (
        manifest.get("task_examples_hash") != digest
        or type(manifest.get("task_examples_count")) is not int
        or manifest["task_examples_count"] != len(examples)
    ):
        raise GuideTaskExampleInputError("task_examples_invalid")
    return examples
