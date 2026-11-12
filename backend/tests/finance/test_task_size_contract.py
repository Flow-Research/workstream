"""One current creation format normalizes defaults before canonical hashing."""

import json

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.modules.tasks.api.task_import import TaskImportRow, parse_task_import
from app.modules.tasks.schemas import TaskCreate


@pytest.mark.parametrize("size", ["small", "medium", "large"])
def test_create_and_import_size_are_exact_choices(size):
    assert TaskCreate(title="T", description="D", task_size=size).task_size == size
    assert (
        TaskImportRow(external_task_id="a", title="T", description="D", task_size=size).task_size
        == size
    )


@pytest.mark.parametrize("model", [TaskCreate, TaskImportRow])
@pytest.mark.parametrize("size", [None, "Small", "", 0, True, [], "extra_large"])
def test_explicit_invalid_size_never_becomes_default(model, size):
    values = {"title": "T", "description": "D", "task_size": size}
    if model is TaskImportRow:
        values["external_task_id"] = "a"
    with pytest.raises(ValidationError):
        model.model_validate(values)


@pytest.mark.parametrize(
    "field", ["quantity", "instrument_type", "unit_code", "award_definition_id"]
)
def test_task_author_cannot_override_financial_facts(field):
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({"title": "T", "description": "D", field: "override"})


def test_omitted_size_is_small_without_changing_received_import_bytes():
    value = {
        "schema_version": "workstream.task_import.v1",
        "tasks": [{"external_task_id": "a", "title": "T", "description": "D"}],
    }
    raw = json.dumps(value).encode()
    parsed = parse_task_import(raw)
    assert parsed.document.tasks[0].task_size == "small"
    assert parsed.document.model_dump(mode="json")["tasks"][0]["task_size"] == "small"
    assert parsed.byte_count == len(raw)
    assert "task_size" not in TaskCreate(title="T", description="D").model_fields_set


def test_current_creation_hash_normalizes_omission_and_explicit_small():
    omitted = TaskCreate(title="T", description="D")
    explicit = TaskCreate(title="T", description="D", task_size="small")
    medium = TaskCreate(title="T", description="D", task_size="medium")
    assert omitted.model_dump(mode="json") == explicit.model_dump(mode="json")
    assert canonical_json_hash(omitted.model_dump(mode="json")) == canonical_json_hash(
        explicit.model_dump(mode="json")
    )
    assert canonical_json_hash(omitted.model_dump(mode="json")) != canonical_json_hash(
        medium.model_dump(mode="json")
    )
