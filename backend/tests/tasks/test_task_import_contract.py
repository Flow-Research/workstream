"""Canonical input ambiguity, bounds and exact source-byte commitments."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.tasks.api.task_import import parse_task_import, task_import_json_schema


def document(count=1):
    return {"schema_version": "workstream.task_import.v1", "metadata": {"label": "Quoted UTF-8 source"},
            "tasks": [{"external_task_id": f"source-{index}", "title": 'Review "café", Lagos',
                       "description": "First line\nSecond line", "task_type": "translation",
                       "skill_tags": ["French", "Python"], "estimated_time_minutes": 30}
                      for index in range(count)]}


def test_200_rows_preserve_exact_received_bytes_and_instructions():
    raw = (json.dumps(document(200), ensure_ascii=False, indent=2) + "\n").encode()
    parsed = parse_task_import(raw)
    assert parsed.byte_count == len(raw) and parsed.sha256 == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert len(parsed.document.tasks) == 200
    assert parsed.document.tasks[0].title == 'Review "café", Lagos'
    compact = json.dumps(document(200), ensure_ascii=False, separators=(",", ":")).encode()
    assert parse_task_import(compact).document == parsed.document
    assert parse_task_import(compact).sha256 != parsed.sha256


@pytest.mark.parametrize("raw", [
    b'{"schema_version":"workstream.task_import.v1","schema_version":"different","tasks":[]}',
    b'{"schema_version":"workstream.task_import.v1","tasks":[{"external_task_id":"x","external_task_id":"y","title":"x","description":"x"}]}',
    b'{"schema_version":"workstream.task_import.v1","tasks":[NaN]}',
    b'{"schema_version":"workstream.task_import.v1","tasks":[Infinity]}',
    b'\xff', b'', b'\xef\xbb\xbf{}', b'{}{}',
])
def test_ambiguous_or_malformed_json_is_rejected(raw):
    with pytest.raises((ValueError, UnicodeError)):
        parse_task_import(raw)


@pytest.mark.parametrize("count", [0, 501])
def test_row_count_is_bounded(count):
    with pytest.raises(ValidationError) as failure:
        parse_task_import(json.dumps(document(count)).encode())
    assert failure.value.errors()[0]["loc"] == ("tasks",)


def test_duplicate_ids_report_zero_based_row_index():
    value = document(3)
    value["tasks"][2]["external_task_id"] = value["tasks"][0]["external_task_id"]
    with pytest.raises(ValidationError) as failure:
        parse_task_import(json.dumps(value).encode())
    assert failure.value.errors()[0]["loc"] == ("tasks", 2, "external_task_id")
    assert failure.value.errors()[0]["type"] == "duplicate_external_task_id"


@pytest.mark.parametrize("field,value", [
    ("external_task_id", None), ("external_task_id", " leading"), ("external_task_id", "trailing "),
    ("external_task_id", "x\n"), ("external_task_id", "x\u0085y"), ("title", " "), ("description", "\n"),
    ("estimated_time_minutes", True), ("estimated_time_minutes", "30"), ("estimated_time_minutes", 0),
    ("skill_tags", [" "]), ("skill_tags", [True]), ("source_ref", "s3://bucket/path"),
    ("description", "nul\x00"), ("title", "\ud800"),
    ("import_batch_id", "client-chosen-id"), ("status", "ready"),
])
def test_row_errors_are_indexed_and_server_custody_is_not_caller_input(field, value):
    data = document(3)
    data["tasks"][1][field] = value
    with pytest.raises(ValidationError) as failure:
        parse_task_import(json.dumps(data).encode())
    assert failure.value.errors()[0]["loc"][:2] == ("tasks", 1)


def test_published_schema_matches_the_live_upload_contract():
    path = Path(__file__).resolve().parents[3] / "contracts/task-import.schema.json"
    assert json.loads(path.read_text()) == task_import_json_schema()
