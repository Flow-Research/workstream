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


def test_checker_accepts_dispatcher_authorized_start_projection(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    fixtures._contract(repository_root)
    loop.apply_merge_record(state_root, fixtures._record())
    loop.apply_authority_event(
        state_root, fixtures._dispatcher_start(), repository_root=repository_root
    )
    assert checker.generated_state_failures(state_root) == []


def test_checker_accepts_writer_directed_planning_projection(tmp_path: Path) -> None:
    state_root, repository_root, record, event = fixtures._selected_start_fixture(tmp_path)
    loop.apply_merge_record(state_root, record)
    loop.apply_authority_event(state_root, event, repository_root=repository_root)
    assert checker.generated_state_failures(state_root, repository_root) == []


def test_checker_rejects_forged_writer_selection_mode(tmp_path: Path) -> None:
    state_root, repository_root, record, event = fixtures._selected_start_fixture(tmp_path)
    loop.apply_merge_record(state_root, record)
    loop.apply_authority_event(state_root, event, repository_root=repository_root)
    state = json.loads((state_root / loop.STATE_PATH).read_text())
    state["event"]["selection"]["mode"] = "declared_successor"
    assert checker._authority_transition_failures(state, [record], "fixture")


def test_checker_binds_selection_to_exact_main_blob(tmp_path: Path) -> None:
    _state_root, repository_root, _record, event = fixtures._selected_start_fixture(tmp_path)
    assert checker._selection_tree_failures(event, repository_root, "fixture") == []
    event["selection"]["contract_blob_sha"] = "f" * 40
    assert checker._selection_tree_failures(event, repository_root, "fixture")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda selection: selection.update(extra="field"), "schema"),
        (lambda selection: selection.update(schema_version=2), "unsupported"),
        (lambda selection: selection.update(mode="untrusted"), "unsupported"),
        (lambda selection: selection.update(phase="delivery"), "unsupported"),
        (lambda selection: selection.update(contract_path="README.md"), "path"),
        (lambda selection: selection.update(contract_title=""), "title"),
        (lambda selection: selection.update(contract_blob_sha="bad"), "blob"),
    ],
)
def test_checker_rejects_malformed_start_selection(
    tmp_path: Path, mutation, message: str
) -> None:
    _state_root, _repository_root, _record, event = fixtures._selected_start_fixture(
        tmp_path
    )
    mutation(event["selection"])
    failures = checker._selection_failures(event["selection"], event, "fixture")
    assert any(message in failure for failure in failures)


def test_checker_ignores_tree_binding_without_selection(tmp_path: Path) -> None:
    assert checker._selection_tree_failures({}, tmp_path, "fixture") == []


@pytest.mark.parametrize("field", ["main_sha", "contract_path"])
def test_checker_requires_exact_selection_git_identity(
    tmp_path: Path, field: str
) -> None:
    _state_root, repository_root, _record, event = fixtures._selected_start_fixture(
        tmp_path
    )
    if field == "main_sha":
        event[field] = None
    else:
        event["selection"][field] = None
    assert "no exact Git identity" in checker._selection_tree_failures(
        event, repository_root, "fixture"
    )[0]


def test_checker_rejects_second_start_in_same_initiative(tmp_path: Path) -> None:
    state_root, repository_root, record, event = fixtures._selected_start_fixture(tmp_path)
    loop.apply_merge_record(state_root, record)
    loop.apply_authority_event(state_root, event, repository_root=repository_root)
    active = json.loads((state_root / loop.STATE_PATH).read_text())
    forged = json.loads(json.dumps(active))
    forged["event"].update(
        run_id=99, event_id="github-actions:99:start",
        created_at="2026-07-20T19:00:00Z",
    )
    failures = checker._authority_transition_failures(
        forged, [record, active], "fixture"
    )
    assert any("basis is already active" in failure for failure in failures)


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
        lambda record: record["event"].update(main_sha="f" * 40),
        lambda record: record["event"].update(initiative_id="WS-ART-001"),
        lambda record: record["event"].update(chunk_id="WS-ENG-001-99"),
        lambda record: record["authority_state"].update(source={}),
        lambda record: record["authority_state"]["source"].update(head_sha="bad"),
        lambda record: record["authority_state"]["source"].update(pr_number=0),
        lambda record: record["authority_state"]["source"].update(pr_number=True),
        lambda record: record["authority_state"]["source"].update(pr_url="wrong"),
        lambda record: record["authority_state"]["source"].update(pr_title=""),
        lambda record: record["authority_state"]["source"].update(merged_at="wrong"),
        lambda record: record["authority_state"]["source"].update(
            merged_at="2026-07-20T10:00:00"
        ),
        lambda record: record["authority_state"]["source"].update(
            intent_path=".agent-loop/merge-intents/WS-BAD-001.json"
        ),
        lambda record: record["authority_state"].update(completed_chunk=[]),
        lambda record: record["authority_state"].pop("gate"),
        lambda record: record["authority_state"]["completed_chunk"].update(
            initiative_id="WS-ART-001"
        ),
        lambda record: record.update(updated_at="wrong"),
        lambda record: record.update(active={"planning_chunk": None, "implementation_chunk": "WS-BAD-001"}),
        lambda record: record["authority_state"]["gate"].update(status="stopped_after_merge"),
    ],
)
def test_checker_rejects_malformed_authority_records(
    tmp_path: Path, mutation
) -> None:
    record = _authority_record(tmp_path)
    mutation(record)
    assert checker._record_failures(record, "fixture")


def test_checker_accepts_cross_initiative_start_without_borrowed_evidence(
    tmp_path: Path,
) -> None:
    state_root, repository_root = fixtures._cross_initiative_merge_bound_state(
        tmp_path
    )
    assert checker.generated_state_failures(state_root, repository_root) == []


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
        "action", "initiative_id", "chunk_id", "phase", "reason", "expected_main_sha"
    }
    assert workflow["permissions"] == {"actions": "read", "contents": "write"}
    assert workflow["concurrency"] == {
        "group": "workstream-loop-memory",
        "cancel-in-progress": "false",
    }
    assert set(workflow["jobs"]) == {"cancel-approval", "explicit-event"}
    cancel_job = workflow["jobs"]["cancel-approval"]
    assert cancel_job["if"] == "inputs.action == 'cancel'"
    assert cancel_job["environment"] == "loop-memory-start"
    job = workflow["jobs"]["explicit-event"]
    assert job["needs"] == "cancel-approval"
    assert "inputs.action == 'start'" in job["if"]
    assert "needs.cancel-approval.result == 'success'" in job["if"]
    assert "environment" not in job
    checkout = job["steps"][0]
    assert checkout["with"] == {
        "persist-credentials": "false",
        "fetch-depth": "0",
        "ref": "main",
    }
    assert "pull_request" not in text
    assert "repository_dispatch" not in text
    assert "automation/loop-memory" in text
    assert "LOOP_MEMORY_SIGNING_KEY" in text
    assert "LOOP_MEMORY_START_SIGNING_KEY" not in text
    assert "inputs.expected_main_sha" in text
    assert "inputs.destination" not in text and "inputs.ref" not in text
    assert job["env"] == {"STATE_BRANCH": "automation/loop-memory"}
    assert [step.get("name", "checkout") for step in job["steps"]] == [
        "checkout",
        "Resolve trusted protected-main target",
        "Prepare authenticated state and reconcile main",
        "Apply authenticated authority event",
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
