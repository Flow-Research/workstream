"""Creation defaults and immutable saved formats have distinct canonical inputs."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID
import json

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.modules.tasks.api.task_import import TaskImportRow, parse_task_import
from app.modules.tasks.command_replay import (
    TaskCommandReplay,
    recorded_task_import_fields,
    retained_task_response,
)
from app.modules.tasks.schemas import TaskCreate, TaskResponse, TaskImportBatchResponse
from tests.finance.reward_history import reward_history


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


def test_saved_omitted_size_creation_selects_original_hash_before_defaults():
    history = reward_history("task_replay")
    seed = history["seed"]
    response = seed["create_response"]
    receipt = next(
        row
        for row in history["tables"]["task_command_receipts"]
        if row["task_id"] == response["id"]
    )
    prior = SimpleNamespace(status="committed", response=response)
    payload = TaskCreate.model_validate(seed["create_request"])
    assert payload.task_size == "small"
    assert retained_task_response(response)
    original = TaskCommandReplay.creation_value(
        UUID(seed["project_id"]), payload, prior, size_explicit=False
    )
    assert "task_size" not in original["payload"]
    assert canonical_json_hash(original) == receipt["request_digest"]
    for prior_value, explicit in (
        (None, False),
        (prior, True),
        (SimpleNamespace(status="pending", response=response), False),
    ):
        current = TaskCommandReplay.creation_value(
            UUID(seed["project_id"]), payload, prior_value, size_explicit=explicit
        )
        assert current["payload"]["task_size"] == "small"
        assert canonical_json_hash(current) != receipt["request_digest"]


def test_saved_responses_and_import_members_preserve_original_fields_and_hashes():
    history = reward_history("task_replay")
    stored = history["seed"]["create_response"]
    old = TaskResponse.model_validate(stored)
    assert old.task_size is None and "task_size" not in old.model_fields_set
    assert old.model_dump(mode="json") == stored
    sized = stored | {"task_size": "large"}
    assert TaskResponse.model_validate(sized).model_dump(mode="json") == sized
    batch = history["tables"]["task_import_batches"][0]["response"]
    decoded = TaskImportBatchResponse.model_validate(batch)
    assert decoded.model_dump(mode="json") == batch
    for member, task in zip(
        sorted(history["tables"]["task_import_batch_members"], key=lambda row: row["row_index"]),
        decoded.tasks,
        strict=True,
    ):
        fields = recorded_task_import_fields(member["response"])
        assert "task_size" not in fields
        assert (
            canonical_json_hash({field: getattr(task, field) for field in fields})
            == member["row_digest"]
        )
        assert "task_size" in recorded_task_import_fields(
            member["response"] | {"task_size": "small"}
        )


def test_unknown_or_partial_saved_formats_do_not_get_a_legacy_hash_fallback():
    original = reward_history("task_replay")["seed"]["create_response"]
    partial = deepcopy(original)
    partial.pop("description")
    for value in (partial, original | {"unexpected": None}, original | {"task_size": None}):
        assert not retained_task_response(value)
        with pytest.raises(ValueError):
            recorded_task_import_fields(value)
