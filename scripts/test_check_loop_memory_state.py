"""Independent checker coverage for explicit authority projections."""

from __future__ import annotations

from pathlib import Path
import json

import pytest
import yaml

from scripts import check_loop_memory_state as checker
from scripts import test_update_post_merge_memory as fixtures
from scripts import update_post_merge_memory as loop


@pytest.fixture(autouse=True)
def _fixed_state_tip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loop, "_state_branch_tip", lambda _root: "e" * 40)


def test_checker_accepts_signed_start_projection(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    fixtures._contract(repository_root)
    loop.apply_merge_record(state_root, fixtures._record())
    loop.apply_authority_event(
        state_root, fixtures._event("start"), repository_root=repository_root
    )
    assert checker.generated_state_failures(state_root) == []


def test_checker_rejects_authority_projection_drift(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    fixtures._contract(repository_root)
    loop.apply_merge_record(state_root, fixtures._record())
    loop.apply_authority_event(
        state_root, fixtures._event("start"), repository_root=repository_root
    )
    state_path = state_root / loop.STATE_PATH
    state_path.write_text(state_path.read_text().replace('"active"', '"broken"', 1))
    assert checker.generated_state_failures(state_root)


def _authority_record(tmp_path: Path) -> dict:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    fixtures._contract(repository_root)
    loop.apply_merge_record(state_root, fixtures._record())
    loop.apply_authority_event(
        state_root, fixtures._event("start"), repository_root=repository_root
    )
    return json.loads((state_root / loop.STATE_PATH).read_text())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda record: record["event"].update(event_id="wrong"),
        lambda record: record["event"].update(dispatcher=""),
        lambda record: record["event"].update(approvers=[]),
        lambda record: record["event"].update(main_sha="bad"),
        lambda record: record.update(updated_at="wrong"),
        lambda record: record.update(active={"planning_chunk": None, "implementation_chunk": None}),
        lambda record: record["gate"].update(status="stopped_after_merge"),
    ],
)
def test_checker_rejects_malformed_authority_records(
    tmp_path: Path, mutation
) -> None:
    record = _authority_record(tmp_path)
    mutation(record)
    assert checker._record_failures(record, "fixture")


def test_checker_rejects_invalid_legacy_exemption(tmp_path: Path) -> None:
    record = fixtures._record()
    record["legacy_exemptions"] = [
        {"initiative_id": "WS-AUTH-001", "chunk_id": "bad", "pr_number": 0}
    ]
    assert checker._record_failures(record, "fixture")


def test_explicit_event_workflow_has_closed_write_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / ".github/workflows/loop-memory-start.yml"
    text = path.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {
        "action", "initiative_id", "chunk_id", "reason", "expected_main_sha"
    }
    assert workflow["permissions"] == {"actions": "read", "contents": "write"}
    assert workflow["concurrency"] == {
        "group": "workstream-loop-memory",
        "cancel-in-progress": "false",
    }
    assert set(workflow["jobs"]) == {"explicit-event"}
    job = workflow["jobs"]["explicit-event"]
    assert job["if"] == "github.ref == 'refs/heads/main' && github.run_attempt == 1"
    assert job["environment"] == "loop-memory-start"
    checkout = job["steps"][0]
    assert checkout["with"] == {
        "persist-credentials": "false",
        "fetch-depth": "0",
        "ref": "main",
    }
    assert "pull_request" not in text
    assert "repository_dispatch" not in text
    assert "automation/loop-memory" in text
    assert "LOOP_MEMORY_START_SIGNING_KEY" in text
    assert "inputs.expected_main_sha" in text
    assert "inputs.destination" not in text and "inputs.ref" not in text
    assert job["env"] == {"STATE_BRANCH": "automation/loop-memory"}
    assert [step.get("name", "checkout") for step in job["steps"]] == [
        "checkout",
        "Resolve trusted protected-main target",
        "Prepare authenticated state and reconcile main",
        "Apply protected authority event",
        "Sign, validate, and publish exact generated tree",
    ]
    assert all("${{ inputs." not in step.get("run", "") for step in job["steps"])
    assert "git push" not in text and "commit-tree" not in text
    assert text.count("update_post_merge_memory.py publish") == 1


def test_checker_accepts_typed_cutover_and_rejects_mismatch(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    record = fixtures._record()
    record["legacy_exemptions"] = [
        {"initiative_id": "WS-AUTH-001", "chunk_id": "WS-AUTH-001-PREP", "pr_number": 162}
    ]
    record["event"] = {
        "type": "cutover",
        "main_sha": "a" * 40,
        "legacy_exemptions": json.loads(json.dumps(record["legacy_exemptions"])),
    }
    loop.apply_merge_record(state_root, record)
    assert checker.generated_state_failures(state_root) == []
    broken = json.loads(json.dumps(record))
    broken["event"]["main_sha"] = "f" * 40
    assert checker._record_failures(broken, "cutover")
