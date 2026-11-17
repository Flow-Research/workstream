"""Current client consumers reject size omissions, substitutions and partial receipts."""

from copy import deepcopy
from typing import Any

import pytest
from conftest import mcp_call
from jsonschema import Draft202012Validator

from workstream_mcp.schemas import _contract_document, task_operation_output_schema

PROJECT = "019a2a00-0000-7000-8000-000000002001"
TASK = "019a2a00-0000-7000-8000-000000002002"
SOURCE = "019a2a00-0000-7000-8000-000000002004"
BATCH = "019a2a00-0000-7000-8000-000000002005"
KEY = "019a2a00-0000-7000-8000-000000002007"


def _task() -> dict[str, Any]:
    schema = _contract_document("task_import_batch_create")["components"]["schemas"]["TaskResponse"]
    value = dict.fromkeys(schema["properties"])
    value.update(id=TASK, project_id=PROJECT, title="T", description="D", task_size="small",
                 skill_tags=[], source_type="manual", status="draft", created_by=PROJECT,
                 created_at="2026-11-12T05:00:00Z", updated_at="2026-11-12T05:00:00Z")
    return value


def _batch() -> dict[str, Any]:
    rows = []
    for index, size in enumerate(("small", "large")):
        row = _task()
        row.update(id=f"019a2a00-0000-7000-8000-00000000300{index}", task_size=size,
                   source_type="json_import", source_ref="task-import-source:" + SOURCE,
                   source_payload_hash="sha256:" + "a" * 64, import_batch_id=BATCH,
                   external_task_id=f"row-{index}")
        rows.append(row)
    return {"batch_id": BATCH, "project_id": PROJECT, "source_id": SOURCE,
            "sha256": "sha256:" + "a" * 64, "byte_count": 1000,
            "schema_version": "workstream.task_import.v1",
            "mapping_version": "workstream.task_import.draft_mapping.v1",
            "row_count": 2, "label": None, "created_at": "2026-11-12T05:00:00Z", "tasks": rows}


@pytest.mark.parametrize("name", ["task_import_batch_create", "task_import_batch_get"])
def test_import_receipts_require_complete_current_size_context(adapter, name):
    client, received, upstream = adapter
    arguments: dict[str, Any] = {"project_id": PROJECT}
    if name.endswith("create"):
        arguments.update(body={"source_id": SOURCE}, idempotency_key=KEY)
    else:
        arguments["batch_id"] = BATCH
    for change in ("valid", "null", "missing_size", "unknown", "partial"):
        value = _batch()
        if change == "null":
            value["tasks"][0]["task_size"] = None
        elif change == "missing_size":
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
        valid = change == "valid"
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
    assert len(received) == 5


def test_task_create_returned_size_binds_normalized_input(adapter):
    client, received, upstream = adapter
    for explicit, returned, valid in (
        (True, "large", True), (True, "small", False), (True, None, False),
        (True, "absent", False), (False, "small", True), (False, "absent", False),
        (False, None, False), (False, "medium", False), (False, "large", False),
    ):
        body: dict[str, Any] = {"title": "T", "description": "D"}
        if explicit:
            body["task_size"] = "large"
        value = deepcopy(_task())
        if returned == "absent":
            value.pop("task_size")
        else:
            value["task_size"] = returned
        upstream.update(status=201, json=value)
        result = mcp_call(client, name="workstream_management_task_create", arguments={
            "project_id": PROJECT, "body": body, "idempotency_key": KEY,
        }).json()["result"]
        assert result["isError"] is not valid, result
        if not valid:
            assert result["structuredContent"]["error"] == "workstream_execution_uncertain"
    assert len(received) == 9
