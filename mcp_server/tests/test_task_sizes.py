"""Client consumers retain complete old receipts and reject new size substitutions."""

import gzip
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from conftest import mcp_call
from jsonschema import Draft202012Validator

from workstream_mcp.schemas import task_operation_output_schema


def _history() -> dict[str, Any]:
    path = (Path(__file__).resolve().parents[2]
            / "backend/tests/fixtures/finance_reward_v1_task_replay.json.gz")
    with gzip.open(path, "rt") as source:
        return json.load(source)


@pytest.mark.parametrize("name", ["task_import_batch_create", "task_import_batch_get"])
def test_import_original_size_format_is_complete_and_homogeneous(adapter, name):
    client, received, upstream = adapter
    original = _history()["tables"]["task_import_batches"][0]["response"]
    assert len(original["tasks"]) == 2
    assert all("task_size" not in row for row in original["tasks"])
    arguments = {"project_id": original["project_id"]}
    if name.endswith("create"):
        arguments.update(body={"source_id": original["source_id"]},
                         idempotency_key="019a2a00-0000-7000-8000-000000002007")
    else:
        arguments["batch_id"] = original["batch_id"]
    for change in ("old", "new", "null", "mixed", "unknown", "partial"):
        value = deepcopy(original)
        if change != "old":
            for index, row in enumerate(value["tasks"]):
                row["task_size"] = ("small", "large")[index]
        if change == "null":
            value["tasks"][0]["task_size"] = None
        elif change == "mixed":
            value["tasks"][0].pop("task_size")
        elif change == "unknown":
            value["tasks"][0]["task_size"] = "Small"
        elif change == "partial":
            value["tasks"][0].pop("difficulty")
        if name.endswith("get"):
            value = {"creation": value, "current_tasks": [
                {"task_id": row["id"], "row_index": index, "status": "draft"}
                for index, row in enumerate(value["tasks"])
            ]}
        valid = change in {"old", "new"}
        errors = list(Draft202012Validator(task_operation_output_schema(name)).iter_errors(value))
        assert (not errors) == valid, errors
        upstream.update(status=201 if name.endswith("create") else 200, json=value)
        result = mcp_call(client, name="workstream_" + name, arguments=arguments).json()["result"]
        assert result["isError"] is not valid, result
        if not valid:
            assert result["structuredContent"]["error"] == (
                "workstream_execution_uncertain" if name.endswith("create")
                else "invalid_api_response"
            )
    assert len(received) == 6


def test_task_create_returned_size_binds_explicit_input_and_omitted_history(adapter):
    client, received, upstream = adapter
    history = _history()["seed"]
    arguments = {
        "project_id": history["project_id"],
        "body": history["create_request"],
        "idempotency_key": "019a2a00-0000-7000-8000-000000002007",
    }
    for explicit, returned, valid in (
        (True, "large", True), (True, "small", False), (True, None, False),
        (True, "absent", False), (False, "small", True), (False, "absent", True),
        (False, None, False), (False, "medium", False), (False, "large", False),
    ):
        body = deepcopy(arguments["body"])
        if explicit:
            body["task_size"] = "large"
        value = deepcopy(history["create_response"])
        if returned != "absent":
            value["task_size"] = returned
        upstream.update(status=201, json=value)
        result = mcp_call(client, name="workstream_management_task_create",
                          arguments=arguments | {"body": body}).json()["result"]
        assert result["isError"] is not valid, result
        if not valid:
            assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert len(received) == 9
