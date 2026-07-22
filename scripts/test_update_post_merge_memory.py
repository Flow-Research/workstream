"""Focused regression tests for signed explicit loop-memory events."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts import check_loop_memory_state as checker
from scripts import update_post_merge_memory as loop


@pytest.fixture(autouse=True)
def _fixed_state_tip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loop, "_state_branch_tip", lambda _root: "e" * 40)


def _record() -> dict:
    metadata = {
        "schema_version": 2,
        "initiative_id": "WS-ENG-001",
        "chunk_id": "WS-ENG-001-04A",
        "chunk_title": "Complete Loop Memory Projections",
        "next_chunk_id": "WS-ENG-001-04B",
        "next_chunk_title": "Signed Explicit Start Events",
        "next_requires_explicit_start": True,
    }
    return {
        "schema_version": 2,
        "repository": "Flow-Research/workstream",
        "state_branch": loop.STATE_BRANCH,
        "updated_at": "2026-07-20T10:00:00Z",
        "source": {
            "main_sha": "a" * 40,
            "first_parent_sha": "0" * 40,
            "pr_number": 161,
            "pr_url": "https://github.com/Flow-Research/workstream/pull/161",
            "pr_title": "Complete loop-memory projections",
            "head_sha": "b" * 40,
            "head_ref": "codex/ws-eng-001-04a",
            "merged_at": "2026-07-20T10:00:00Z",
            "merged_by": "manager",
            "intent_path": ".agent-loop/merge-intents/WS-ENG-001-04A.json",
            "intent_blob_sha": "d" * 40,
        },
        "completed_chunk": metadata,
        "active": {"planning_chunk": None, "implementation_chunk": None},
        "gate": {
            "status": "stopped_after_merge",
            "next_chunk_id": "WS-ENG-001-04B",
            "next_chunk_title": "Signed Explicit Start Events",
            "next_requires_explicit_start": True,
        },
        "checks": {
            "required": {
                name: {"kind": "check_run", "conclusion": "success", "url": None}
                for name in loop.REQUIRED_CHECKS
            },
            "all_required_passed": True,
        },
    }


def _event(kind: str, run_id: int = 41) -> dict:
    return {
        "type": kind,
        "event_id": f"github-actions:{run_id}:{kind}",
        "run_id": run_id,
        "created_at": f"2026-07-20T1{run_id % 10}:00:00Z",
        "dispatcher": "dispatcher",
        "approvers": ["reviewer"],
        "reason": "Human-approved bounded chunk",
        "main_sha": "a" * 40,
        "prior_state_tip": "e" * 40,
        "initiative_id": "WS-ENG-001",
        "chunk_id": "WS-ENG-001-04B",
    }


def _dispatcher_start(run_id: int = 41) -> dict:
    event = _event("start", run_id)
    event.pop("approvers")
    event["authorization"] = {
        "schema_version": 1,
        "type": "github_workflow_dispatch",
        "actor": "dispatcher",
    }
    return event


def _contract(root: Path) -> None:
    path = root / ".agent-loop/initiatives/eng/chunks/WS-ENG-001-04B-events.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Chunk Contract: WS-ENG-001-04B\n", encoding="utf-8")


def _selected_start_fixture(tmp_path: Path) -> tuple[Path, Path, dict, dict]:
    repository_root = tmp_path / "repo"
    contract = repository_root / (
        ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/chunks/"
        "WS-CI-001-02-safe-routing-cache-timing.md"
    )
    contract.parent.mkdir(parents=True)
    contract.write_text(
        "# Chunk Contract: WS-CI-001-02 — Safe Routing, Cache, and Timing Refinement\n"
        "\n## Start phase\n\n`planning`\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(repository_root)], check=True)
    subprocess.run(["git", "-C", str(repository_root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(repository_root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repository_root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repository_root), "commit", "-qm", "fixture"], check=True)
    main_sha = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    record = _record()
    record["source"].update(
        main_sha=main_sha,
        intent_path=".agent-loop/merge-intents/WS-CI-001-01R1.json",
    )
    record["completed_chunk"].update(
        initiative_id="WS-CI-001", chunk_id="WS-CI-001-01R1",
        chunk_title="Timeout Cleanup", next_chunk_id=None, next_chunk_title=None,
    )
    record["gate"].update(next_chunk_id=None, next_chunk_title=None)
    selection = loop.resolve_start_selection(
        repository_root, initiative_id="WS-CI-001", chunk_id="WS-CI-001-02",
        phase="planning", main_sha=main_sha, declared_successor=False,
    )
    event = _dispatcher_start()
    event.update(
        main_sha=main_sha, initiative_id="WS-CI-001", chunk_id="WS-CI-001-02",
        selection=selection,
    )
    event["authorization"] = {
        "schema_version": 2,
        "type": "github_repository_permission",
        "actor": "dispatcher",
        "permission": "write",
    }
    return tmp_path / "state", repository_root, record, event


def test_writer_directed_planning_start_cancel_and_restart(tmp_path: Path) -> None:
    state_root, repository_root, record, event = _selected_start_fixture(tmp_path)
    loop.apply_merge_record(state_root, record)
    assert loop.apply_authority_event(state_root, event, repository_root=repository_root)
    state = json.loads((state_root / loop.STATE_PATH).read_text())
    assert state["authority_state"]["active"] == {
        "planning_chunk": "WS-CI-001-02", "implementation_chunk": None,
    }
    assert state["event"]["selection"]["mode"] == "writer_directed"
    cancel = _event("cancel", 42)
    cancel.update(
        main_sha=event["main_sha"], initiative_id="WS-CI-001",
        chunk_id="WS-CI-001-02", selection=event["selection"],
    )
    assert loop.apply_authority_event(state_root, cancel, repository_root=repository_root)
    restart = json.loads(json.dumps(event))
    restart.update(
        run_id=43, event_id="github-actions:43:start",
        created_at="2026-07-20T13:00:00Z",
    )
    restart["selection"] = loop.resolve_start_selection(
        repository_root, initiative_id="WS-CI-001", chunk_id="WS-CI-001-02",
        phase="planning", main_sha=event["main_sha"], declared_successor=True,
    )
    assert loop.apply_authority_event(state_root, restart, repository_root=repository_root)
    loop.validate_generated_state(state_root)


def test_writer_directed_selection_rejects_symlink_contract(tmp_path: Path) -> None:
    _, repository_root, _record_value, event = _selected_start_fixture(tmp_path)
    selected = repository_root / event["selection"]["contract_path"]
    target = selected.with_name("real.md")
    selected.rename(target)
    selected.symlink_to(target.name)
    subprocess.run(["git", "-C", str(repository_root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repository_root), "commit", "-qm", "symlink"], check=True)
    symlink_sha = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    with pytest.raises(loop.LoopMemoryError, match="regular file"):
        loop.resolve_start_selection(
            repository_root, initiative_id="WS-CI-001", chunk_id="WS-CI-001-02",
            phase="planning", main_sha=symlink_sha, declared_successor=False,
        )


def test_writer_directed_selection_enforces_reviewed_phase(tmp_path: Path) -> None:
    _, repository_root, _record_value, event = _selected_start_fixture(tmp_path)
    with pytest.raises(loop.LoopMemoryError, match="phase does not match"):
        loop.resolve_start_selection(
            repository_root, initiative_id="WS-CI-001", chunk_id="WS-CI-001-02",
            phase="implementation", main_sha=event["main_sha"], declared_successor=False,
        )


def test_writer_directed_selection_rejects_missing_malformed_and_foreign(
    tmp_path: Path,
) -> None:
    _, repository_root, _record_value, event = _selected_start_fixture(tmp_path)
    with pytest.raises(loop.LoopMemoryError, match="regular file"):
        loop.resolve_start_selection(
            repository_root, initiative_id="WS-CI-001", chunk_id="WS-CI-001-99",
            phase="planning", main_sha=event["main_sha"], declared_successor=False,
        )


def test_writer_directed_selection_rejects_same_initiative_ambiguity(
    tmp_path: Path,
) -> None:
    _, repository_root, _record_value, event = _selected_start_fixture(tmp_path)
    duplicate = repository_root / event["selection"]["contract_path"]
    duplicate = duplicate.with_name("WS-CI-001-02-duplicate.md")
    duplicate.write_text(
        "# Chunk Contract: WS-CI-001-02 - Duplicate\n\n## Start phase\n\n`planning`\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repository_root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repository_root), "commit", "-qm", "duplicate"], check=True)
    duplicate_sha = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    with pytest.raises(loop.LoopMemoryError, match="one regular file"):
        loop.resolve_start_selection(
            repository_root, initiative_id="WS-CI-001", chunk_id="WS-CI-001-02",
            phase="planning", main_sha=duplicate_sha, declared_successor=False,
        )
    subprocess.run(
        ["git", "-C", str(repository_root), "rm", "-q", str(duplicate.relative_to(repository_root))],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository_root), "commit", "-qm", "remove duplicate"], check=True)
    foreign = repository_root / (
        ".agent-loop/initiatives/WS-ART-001-foreign/chunks/"
        "WS-CI-001-02-duplicate.md"
    )
    foreign.parent.mkdir(parents=True)
    foreign.write_text(
        "# Chunk Contract: WS-CI-001-02 - Foreign\n\n## Start phase\n\n`planning`\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repository_root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repository_root), "commit", "-qm", "foreign"], check=True)
    foreign_sha = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    with pytest.raises(loop.LoopMemoryError, match="crosses initiative"):
        loop.resolve_start_selection(
            repository_root, initiative_id="WS-CI-001", chunk_id="WS-CI-001-02",
            phase="planning", main_sha=foreign_sha, declared_successor=False,
        )
    subprocess.run(["git", "-C", str(repository_root), "rm", "-q", str(foreign.relative_to(repository_root))], check=True)
    contract = repository_root / event["selection"]["contract_path"]
    contract.write_text("# malformed\n\n## Start phase\n\n`planning`\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository_root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repository_root), "commit", "-qm", "malformed"], check=True)
    malformed_sha = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    with pytest.raises(loop.LoopMemoryError, match="canonical heading"):
        loop.resolve_start_selection(
            repository_root, initiative_id="WS-CI-001", chunk_id="WS-CI-001-02",
            phase="planning", main_sha=malformed_sha, declared_successor=False,
        )


def test_writer_directed_start_rejects_completed_identity(tmp_path: Path) -> None:
    state_root, repository_root, record, event = _selected_start_fixture(tmp_path)
    record["source"]["intent_path"] = ".agent-loop/merge-intents/WS-CI-001-02.json"
    record["completed_chunk"].update(
        chunk_id="WS-CI-001-02",
        chunk_title="Safe Routing, Cache, and Timing Refinement",
    )
    loop.apply_merge_record(state_root, record)
    with pytest.raises(loop.LoopMemoryError, match="already-completed"):
        loop.apply_authority_event(state_root, event, repository_root=repository_root)


def test_writer_directed_start_rejects_blob_and_title_drift(tmp_path: Path) -> None:
    state_root, repository_root, record, event = _selected_start_fixture(tmp_path)
    loop.apply_merge_record(state_root, record)
    wrong_blob = json.loads(json.dumps(event))
    wrong_blob["event_id"] = "github-actions:45:start"
    wrong_blob["run_id"] = 45
    wrong_blob["selection"]["contract_blob_sha"] = "f" * 40
    with pytest.raises(loop.LoopMemoryError, match="does not match current main"):
        loop.apply_authority_event(state_root, wrong_blob, repository_root=repository_root)
    wrong_title = json.loads(json.dumps(event))
    wrong_title["event_id"] = "github-actions:46:start"
    wrong_title["run_id"] = 46
    wrong_title["selection"]["contract_title"] = "Forged title"
    with pytest.raises(loop.LoopMemoryError, match="does not match current main"):
        loop.apply_authority_event(state_root, wrong_title, repository_root=repository_root)


def test_ledger_transition_rejects_second_start_in_same_initiative(tmp_path: Path) -> None:
    state_root, repository_root, record, event = _selected_start_fixture(tmp_path)
    loop.apply_merge_record(state_root, record)
    loop.apply_authority_event(state_root, event, repository_root=repository_root)
    active = json.loads((state_root / loop.STATE_PATH).read_text())
    forged = json.loads(json.dumps(active))
    forged["event"].update(
        run_id=98, event_id="github-actions:98:start",
        created_at="2026-07-20T18:00:00Z",
    )
    with pytest.raises(loop.LoopMemoryError, match="already-active basis"):
        loop._validate_authority_transition(forged, [record, active])


def test_start_cancel_retry_and_replay_are_monotonic(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    start = _event("start")
    assert loop.apply_authority_event(state_root, start, repository_root=repository_root)
    assert not loop.apply_authority_event(state_root, start, repository_root=repository_root)
    assert json.loads((state_root / loop.STATE_PATH).read_text())["authority_state"]["active"][
        "implementation_chunk"
    ] == "WS-ENG-001-04B"
    cancel = _event("cancel", 42)
    assert loop.apply_authority_event(state_root, cancel, repository_root=repository_root)
    retry = _event("start", 43)
    assert loop.apply_authority_event(state_root, retry, repository_root=repository_root)
    loop.validate_generated_state(state_root)


def test_dispatcher_start_and_historical_cancel_share_one_ledger(
    tmp_path: Path,
) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    loop.apply_authority_event(
        state_root, _dispatcher_start(), repository_root=repository_root
    )
    loop.apply_authority_event(
        state_root, _event("cancel", 42), repository_root=repository_root
    )
    loop.apply_authority_event(
        state_root, _dispatcher_start(43), repository_root=repository_root
    )
    loop.validate_generated_state(state_root)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda event: event.update(main_sha="f" * 40), "stale"),
        (lambda event: event.update(chunk_id="WS-ENG-001-99"), "reviewed successor"),
        (lambda event: event.update(initiative_id="WS-ART-001"), "crosses initiative"),
        (lambda event: event.update(approvers=["dispatcher"]), "differ"),
        (lambda event: event.update(reason="bad\nreason"), "reason"),
    ],
)
def test_start_rejects_invalid_authority(
    tmp_path: Path, mutation, message: str
) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    before = (state_root / loop.LEDGER_PATH).read_bytes()
    event = _event("start")
    mutation(event)
    with pytest.raises(loop.LoopMemoryError, match=message):
        loop.apply_authority_event(state_root, event, repository_root=repository_root)
    assert (state_root / loop.LEDGER_PATH).read_bytes() == before


def test_same_run_cannot_authorize_two_events(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    loop.apply_authority_event(state_root, _event("start"), repository_root=repository_root)
    with pytest.raises(loop.LoopMemoryError, match="run ID"):
        loop.apply_authority_event(
            state_root, _event("cancel"), repository_root=repository_root
        )


def test_active_merge_must_match_exact_chunk(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    loop.apply_authority_event(state_root, _event("start"), repository_root=repository_root)
    wrong = _record()
    wrong["source"].update(main_sha="c" * 40, first_parent_sha="a" * 40, pr_number=162)
    wrong["source"]["pr_url"] = "https://github.com/Flow-Research/workstream/pull/162"
    with pytest.raises(loop.LoopMemoryError, match="active signed chunk"):
        loop.apply_merge_record(state_root, wrong)


def test_cutover_exemption_is_exact_and_consumed_once(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    cutover = _record()
    cutover["legacy_exemptions"] = [
        {
            "initiative_id": "WS-AUTH-001",
            "chunk_id": "WS-AUTH-001-PREP",
            "pr_number": 162,
        }
    ]
    cutover["event"] = {
        "type": "cutover",
        "main_sha": "a" * 40,
        "legacy_exemptions": json.loads(json.dumps(cutover["legacy_exemptions"])),
    }
    loop.apply_merge_record(state_root, cutover)
    exempt = _record()
    exempt["source"].update(
        main_sha="c" * 40,
        first_parent_sha="a" * 40,
        pr_number=162,
        pr_url="https://github.com/Flow-Research/workstream/pull/162",
        intent_path=".agent-loop/merge-intents/WS-AUTH-001-PREP.json",
    )
    exempt["completed_chunk"].update(
        initiative_id="WS-AUTH-001",
        chunk_id="WS-AUTH-001-PREP",
        chunk_title="Prepared Mutation Authorization Protocol",
        next_chunk_id="WS-AUTH-001-10",
        next_chunk_title="Project Qualification Grants",
    )
    exempt["gate"].update(
        next_chunk_id="WS-AUTH-001-10",
        next_chunk_title="Project Qualification Grants",
    )
    assert loop.apply_merge_record(state_root, exempt)
    assert json.loads((state_root / loop.STATE_PATH).read_text())["legacy_exemptions"] == []
    later = _record()
    later["source"].update(
        main_sha="f" * 40,
        first_parent_sha="c" * 40,
        pr_number=163,
        pr_url="https://github.com/Flow-Research/workstream/pull/163",
    )
    with pytest.raises(loop.LoopMemoryError, match="no signed start or exemption"):
        loop.apply_merge_record(state_root, later)


def _recovery_policy() -> dict:
    return {
        "schema_version": 1,
        "activation": {
            "initiative_id": "WS-ENG-003",
            "chunk_id": "WS-ENG-003-01",
        },
        "recovered_merge": {
            "initiative_id": "WS-ENG-002",
            "chunk_id": "WS-ENG-002-01",
            "pr_number": 166,
            "merge_sha": "c" * 40,
        },
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda policy: policy.update(extra=True), "invalid schema"),
        (lambda policy: policy.update(schema_version=2), "unsupported"),
        (lambda policy: policy.update(activation={"chunk_id": "bad"}), "activation"),
        (lambda policy: policy.update(recovered_merge=[]), "recovered merge"),
        (
            lambda policy: policy["recovered_merge"].update(pr_number=0),
            "recovered merge",
        ),
        (
            lambda policy: policy["recovered_merge"].update(merge_sha="bad"),
            "SHA",
        ),
    ],
)
def test_recovery_policy_schema_fails_closed(mutation, message: str) -> None:
    policy = _recovery_policy()
    mutation(policy)
    with pytest.raises(loop.LoopMemoryError, match=message):
        loop._validate_recovery_policy(policy)


def test_exact_single_target_recovery_binds_signed_first_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loop, "_validate_protected_actions_checks", lambda *_args: None)
    state_root = tmp_path / "state"
    repository_root = tmp_path / "repo"
    _contract(repository_root)
    art = _merge_record("WS-ART-001", "WS-ART-001-02", 168, "a" * 40, "0" * 40)
    art["completed_chunk"].update(
        next_chunk_id="WS-ART-001-03", next_chunk_title="Artifact Recovery"
    )
    art["gate"].update(
        next_chunk_id="WS-ART-001-03", next_chunk_title="Artifact Recovery"
    )
    auth = _merge_record("WS-AUTH-001", "WS-AUTH-001-10", 169, "c" * 40, "a" * 40)
    auth["completed_chunk"].update(
        next_chunk_id="WS-AUTH-001-10A", next_chunk_title="Project Role Grants"
    )
    auth["gate"].update(
        next_chunk_id="WS-AUTH-001-10A", next_chunk_title="Project Role Grants"
    )
    loop.apply_merge_record(state_root, art)
    loop.apply_merge_record(state_root, auth)
    auth_start = _event("start", 40)
    auth_start.update(
        main_sha="c" * 40, initiative_id="WS-AUTH-001", chunk_id="WS-AUTH-001-10A"
    )
    loop.apply_authority_event(
        state_root, auth_start, repository_root=repository_root
    )
    target = _merge_record("WS-ENG-004", "WS-ENG-004-01", 170, "f" * 40, "c" * 40)
    policy = {
        "schema_version": 2,
        "mode": "exact_single_target",
        "activation": {"initiative_id": "WS-ENG-004", "chunk_id": "WS-ENG-004-01"},
    }
    monkeypatch.setattr(loop, "_load_json_at_commit", lambda *_args: policy)
    monkeypatch.setattr(loop, "collect_merge_record", lambda *_args: target)
    exemptions = loop.prepare_recovery_exemptions(
        object(), "Flow-Research/workstream", repository_root=tmp_path,
        state_root=state_root, target_sha="f" * 40, planned_shas=["f" * 40],
    )
    assert exemptions == [
        {"initiative_id": "WS-ENG-004", "chunk_id": "WS-ENG-004-01", "pr_number": 170}
    ]
    target["source"]["first_parent_sha"] = "b" * 40
    with pytest.raises(loop.LoopMemoryError, match="signed first parent"):
        loop.prepare_recovery_exemptions(
            object(), "Flow-Research/workstream", repository_root=tmp_path,
            state_root=state_root, target_sha="f" * 40, planned_shas=["f" * 40],
        )
    target["source"]["first_parent_sha"] = "c" * 40
    with pytest.raises(loop.LoopMemoryError, match="not exact"):
        loop.prepare_recovery_exemptions(
            object(), "Flow-Research/workstream", repository_root=tmp_path,
            state_root=state_root, target_sha="f" * 40,
            planned_shas=["e" * 40, "f" * 40],
        )
    loop.apply_merge_record(state_root, target, recovery_exemptions=exemptions)
    loop.assert_recovery_consumed(state_root, "f" * 40, exemptions)
    state = json.loads((state_root / loop.STATE_PATH).read_text())
    assert exemptions[0] not in state.get("legacy_exemptions", [])
    latest = loop._latest_by_initiative(
        loop._validate_ledger_entries(loop._load_ledger(state_root / loop.LEDGER_PATH))
    )
    assert latest["WS-AUTH-001"]["active"]["implementation_chunk"] == "WS-AUTH-001-10A"
    auth_projection = (
        state_root / loop.INITIATIVE_STATE_ROOT / "WS-AUTH-001.md"
    ).read_text(encoding="utf-8")
    assert "Active implementation chunk: `WS-AUTH-001-10A`" in auth_projection
    art_start = _event("start", 41)
    art_start.update(
        main_sha="f" * 40, initiative_id="WS-ART-001", chunk_id="WS-ART-001-03"
    )
    assert loop.apply_authority_event(
        state_root, art_start, repository_root=repository_root
    )
    assert loop.prepare_recovery_exemptions(
        object(), "Flow-Research/workstream", repository_root=tmp_path,
        state_root=state_root, target_sha="f" * 40, planned_shas=[],
    ) == []
    for relative in (
        loop.RENDERED_PATH,
        loop.WORK_QUEUE_PATH,
        loop.MANIFEST_PATH,
        Path(".agent-loop/INITIATIVE_STATE/WS-ENG-004.md"),
    ):
        projection = (state_root / relative).read_text(encoding="utf-8")
        assert "legacy_exemptions" not in projection
        assert '"pr_number"' not in projection


def test_load_recovery_policy_from_exact_commit(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "-C", str(repository), "init"], check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
    policy_path = repository / loop.RECOVERY_POLICY_PATH
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(json.dumps(_recovery_policy()), encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repository), "commit", "-m", "policy"], check=True, stdout=subprocess.PIPE)
    sha = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    assert loop._load_json_at_commit(
        repository, sha, loop.RECOVERY_POLICY_PATH, "recovery policy"
    ) == _recovery_policy()
    with pytest.raises(loop.LoopMemoryError, match="no bounded"):
        loop._load_json_at_commit(repository, sha, Path("missing.json"), "recovery policy")


def _merge_record(
    initiative_id: str, chunk_id: str, pr_number: int, sha: str, parent: str
) -> dict:
    record = _record()
    record["source"].update(
        main_sha=sha,
        first_parent_sha=parent,
        pr_number=pr_number,
        pr_url=f"https://github.com/Flow-Research/workstream/pull/{pr_number}",
        intent_path=f".agent-loop/merge-intents/{chunk_id}.json",
    )
    record["completed_chunk"].update(
        initiative_id=initiative_id,
        chunk_id=chunk_id,
        chunk_title=chunk_id,
        next_chunk_id=None,
        next_chunk_title=None,
    )
    record["gate"].update(next_chunk_id=None, next_chunk_title=None)
    return record


def test_prepare_recovery_binds_exact_target_and_two_merge_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loop, "_validate_protected_actions_checks", lambda *_args: None)
    state_root = tmp_path / "state"
    loop.apply_merge_record(state_root, _record())
    recovered = _merge_record("WS-ENG-002", "WS-ENG-002-01", 166, "c" * 40, "a" * 40)
    target = _merge_record("WS-ENG-003", "WS-ENG-003-01", 167, "d" * 40, "c" * 40)
    monkeypatch.setattr(loop, "_load_json_at_commit", lambda *_args: _recovery_policy())
    monkeypatch.setattr(
        loop, "collect_merge_record",
        lambda _client, _repository, sha: target if sha == "d" * 40 else recovered,
    )
    assert loop.prepare_recovery_exemptions(
        object(), "Flow-Research/workstream", repository_root=tmp_path,
        state_root=state_root, target_sha="d" * 40,
        planned_shas=["c" * 40, "d" * 40],
    ) == [
        {"initiative_id": "WS-ENG-002", "chunk_id": "WS-ENG-002-01", "pr_number": 166},
        {"initiative_id": "WS-ENG-003", "chunk_id": "WS-ENG-003-01", "pr_number": 167},
    ]


def test_prepare_recovery_rejects_non_exact_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    loop.apply_merge_record(state_root, _record())
    target = _merge_record("WS-ENG-003", "WS-ENG-003-01", 167, "d" * 40, "c" * 40)
    monkeypatch.setattr(loop, "_load_json_at_commit", lambda *_args: _recovery_policy())
    monkeypatch.setattr(loop, "collect_merge_record", lambda *_args: target)
    with pytest.raises(loop.LoopMemoryError, match="exact two-merge"):
        loop.prepare_recovery_exemptions(
            object(), "Flow-Research/workstream", repository_root=tmp_path,
            state_root=state_root, target_sha="d" * 40,
            planned_shas=["b" * 40, "c" * 40, "d" * 40],
        )


def test_prepare_recovery_ignores_non_activation_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    loop.apply_merge_record(state_root, _record())
    other = _merge_record("WS-ENG-004", "WS-ENG-004-01", 168, "d" * 40, "c" * 40)
    monkeypatch.setattr(loop, "_load_json_at_commit", lambda *_args: _recovery_policy())
    monkeypatch.setattr(loop, "collect_merge_record", lambda *_args: other)
    assert loop.prepare_recovery_exemptions(
        object(), "Flow-Research/workstream", repository_root=tmp_path,
        state_root=state_root, target_sha="d" * 40,
        planned_shas=["c" * 40, "d" * 40],
    ) == []


def test_prepare_recovery_requires_existing_state(tmp_path: Path) -> None:
    with pytest.raises(loop.LoopMemoryError, match="requires canonical state"):
        loop.prepare_recovery_exemptions(
            object(), "Flow-Research/workstream", repository_root=tmp_path,
            state_root=tmp_path / "missing", target_sha="d" * 40,
            planned_shas=["c" * 40, "d" * 40],
        )


def test_prepare_recovery_rejects_wrong_recovered_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    loop.apply_merge_record(state_root, _record())
    target = _merge_record("WS-ENG-003", "WS-ENG-003-01", 167, "d" * 40, "c" * 40)
    wrong = _merge_record("WS-ENG-002", "WS-ENG-002-01", 999, "c" * 40, "a" * 40)
    monkeypatch.setattr(loop, "_load_json_at_commit", lambda *_args: _recovery_policy())
    monkeypatch.setattr(
        loop, "collect_merge_record",
        lambda _client, _repository, sha: target if sha == "d" * 40 else wrong,
    )
    with pytest.raises(loop.LoopMemoryError, match="does not match"):
        loop.prepare_recovery_exemptions(
            object(), "Flow-Research/workstream", repository_root=tmp_path,
            state_root=state_root, target_sha="d" * 40,
            planned_shas=["c" * 40, "d" * 40],
        )


def test_prepare_recovery_rejects_signed_inventory_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loop, "_validate_protected_actions_checks", lambda *_args: None)
    state_root = tmp_path / "state"
    base = _record()
    base["legacy_exemptions"] = [
        {"initiative_id": "WS-ENG-002", "chunk_id": "WS-ENG-002-01", "pr_number": 166}
    ]
    loop.apply_merge_record(state_root, base)
    recovered = _merge_record("WS-ENG-002", "WS-ENG-002-01", 166, "c" * 40, "a" * 40)
    target = _merge_record("WS-ENG-003", "WS-ENG-003-01", 167, "d" * 40, "c" * 40)
    monkeypatch.setattr(loop, "_load_json_at_commit", lambda *_args: _recovery_policy())
    monkeypatch.setattr(
        loop, "collect_merge_record",
        lambda _client, _repository, sha: target if sha == "d" * 40 else recovered,
    )
    with pytest.raises(loop.LoopMemoryError, match="collides"):
        loop.prepare_recovery_exemptions(
            object(), "Flow-Research/workstream", repository_root=tmp_path,
            state_root=state_root, target_sha="d" * 40,
            planned_shas=["c" * 40, "d" * 40],
        )


def test_recovery_exemptions_are_consumed_without_persisting(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    base = _record()
    base["legacy_exemptions"] = [
        {"initiative_id": "WS-MCP-001", "chunk_id": "WS-MCP-001-01", "pr_number": 149}
    ]
    loop.apply_merge_record(state_root, base)
    recovered = _merge_record("WS-ENG-002", "WS-ENG-002-01", 166, "c" * 40, "a" * 40)
    target = _merge_record("WS-ENG-003", "WS-ENG-003-01", 167, "d" * 40, "c" * 40)
    exemptions = [
        {"initiative_id": "WS-ENG-002", "chunk_id": "WS-ENG-002-01", "pr_number": 166},
        {"initiative_id": "WS-ENG-003", "chunk_id": "WS-ENG-003-01", "pr_number": 167},
    ]
    assert loop.apply_merge_record(state_root, recovered, exemptions)
    assert loop.apply_merge_record(state_root, target, exemptions)
    loop.assert_recovery_consumed(state_root, "d" * 40, exemptions)
    state = json.loads((state_root / loop.STATE_PATH).read_text())
    assert state["legacy_exemptions"] == [
        {"chunk_id": "WS-MCP-001-01", "initiative_id": "WS-MCP-001", "pr_number": 149}
    ]
    records = [entry["record"] for entry in loop._load_ledger(state_root / loop.LEDGER_PATH)]
    assert all(
        exemption not in record.get("legacy_exemptions", [])
        for record in records
        for exemption in exemptions
    )
    later = _merge_record("WS-ENG-004", "WS-ENG-004-01", 168, "f" * 40, "d" * 40)
    with pytest.raises(loop.LoopMemoryError, match="no signed start or exemption"):
        loop.apply_merge_record(state_root, later)


def test_successful_recovery_replay_does_not_reinject(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    target = _merge_record("WS-ENG-003", "WS-ENG-003-01", 167, "d" * 40, "c" * 40)
    loop.apply_merge_record(state_root, target)
    assert loop.prepare_recovery_exemptions(
        object(), "Flow-Research/workstream", repository_root=tmp_path,
        state_root=state_root, target_sha="d" * 40, planned_shas=[],
    ) == []


def test_recovery_final_assertion_rejects_partial_consumption(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    target = _merge_record("WS-ENG-003", "WS-ENG-003-01", 167, "d" * 40, "c" * 40)
    target["legacy_exemptions"] = [
        {"initiative_id": "WS-ENG-003", "chunk_id": "WS-ENG-003-01", "pr_number": 167}
    ]
    loop.apply_merge_record(state_root, target)
    with pytest.raises(loop.LoopMemoryError, match="not fully consumed"):
        loop.assert_recovery_consumed(
            state_root, "d" * 40, target["legacy_exemptions"]
        )


def test_recovery_final_assertion_requires_exact_target(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    loop.apply_merge_record(state_root, _record())
    with pytest.raises(loop.LoopMemoryError, match="exact target"):
        loop.assert_recovery_consumed(state_root, "d" * 40, [])


def test_recovery_final_assertion_rejects_historical_leak(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    exemption = {
        "initiative_id": "WS-ENG-003", "chunk_id": "WS-ENG-003-01", "pr_number": 167
    }
    base = _record()
    base["legacy_exemptions"] = [exemption]
    loop.apply_merge_record(state_root, base)
    target = _merge_record("WS-ENG-003", "WS-ENG-003-01", 167, "d" * 40, "a" * 40)
    loop.apply_merge_record(state_root, target)
    with pytest.raises(loop.LoopMemoryError, match="signed history"):
        loop.assert_recovery_consumed(state_root, "d" * 40, [exemption])


def test_recovery_cli_round_trip_consumes_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(loop, "_validate_protected_actions_checks", lambda *_args: None)
    state_root = tmp_path / "state"
    base = _record()
    base["legacy_exemptions"] = []
    loop.apply_merge_record(state_root, base)
    recovered = _merge_record("WS-ENG-002", "WS-ENG-002-01", 166, "c" * 40, "a" * 40)
    target = _merge_record("WS-ENG-003", "WS-ENG-003-01", 167, "d" * 40, "c" * 40)
    records = {"c" * 40: recovered, "d" * 40: target}
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(loop, "_assert_state_branch", lambda _root: None)
    monkeypatch.setattr(loop, "GitHubClient", lambda _token, _url: object())
    monkeypatch.setattr(loop, "_load_json_at_commit", lambda *_args: _recovery_policy())
    monkeypatch.setattr(
        loop, "collect_merge_record", lambda _client, _repository, sha: records[sha]
    )
    plan_file = tmp_path / "plan"
    plan_file.write_text(f"{'c' * 40}\n{'d' * 40}\n", encoding="utf-8")
    assert loop.main([
        "prepare-recovery", "--repository", "Flow-Research/workstream",
        "--repository-root", str(tmp_path), "--state-root", str(state_root),
        "--target-sha", "d" * 40, "--plan-file", str(plan_file),
    ]) == 0
    recovery_file = tmp_path / "recovery.json"
    recovery_file.write_text(capsys.readouterr().out, encoding="utf-8")
    common = [
        "--repository", "Flow-Research/workstream", "--repository-root", str(tmp_path),
        "--state-root", str(state_root), "--branch-root", str(state_root),
    ]
    assert loop.main([
        "update", *common, "--merge-sha", "c" * 40,
        "--recovery-file", str(recovery_file),
    ]) == 0
    assert loop.main([
        "update", *common, "--merge-sha", "d" * 40,
        "--recovery-file", str(recovery_file),
    ]) == 0
    assert loop.main([
        "assert-recovery-consumed", "--state-root", str(state_root),
        "--target-sha", "d" * 40, "--recovery-file", str(recovery_file),
    ]) == 0


@dataclass
class _Client:
    run: object
    approvals: object
    permission: object = None

    def get_json(self, path: str):
        if "/collaborators/" in path and path.endswith("/permission"):
            return self.permission or {"permission": "write"}
        return self.approvals if path.endswith("/approvals") else self.run


def test_collect_start_event_binds_dispatcher_authority_without_approval() -> None:
    client = _Client(
        run={
            "id": 41,
            "run_attempt": 1,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": "a" * 40,
            "actor": {"login": "dispatcher"},
            "created_at": "2026-07-20T11:00:00Z",
        },
        approvals=[
            {
                "state": "approved",
                "user": {"login": "reviewer"},
                "environments": [{"id": 7, "name": "loop-memory-start"}],
            },
            {"state": "rejected", "user": {"login": "ignored"}},
        ],
    )
    event = loop.collect_authority_event(
        client,
        "Flow-Research/workstream",
        action="start",
        initiative_id="WS-ENG-001",
        chunk_id="WS-ENG-001-04B",
        reason="Approved",
        run_id=41,
        dispatcher="dispatcher",
        main_sha="a" * 40,
        prior_state_tip="e" * 40,
        start_permissions=frozenset({"write", "maintain", "admin"}),
    )
    assert event["authorization"] == {
        "schema_version": 2,
        "type": "github_repository_permission",
        "actor": "dispatcher",
        "permission": "write",
    }
    assert "approvers" not in event


def test_collect_cancel_event_retains_protected_approval() -> None:
    client = _Client(
        run={
            "id": 42,
            "run_attempt": 1,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": "a" * 40,
            "actor": {"login": "dispatcher"},
            "created_at": "2026-07-20T12:00:00Z",
        },
        approvals=[{
            "state": "approved",
            "user": {"login": "reviewer"},
            "environments": [{"id": 7, "name": "loop-memory-start"}],
        }],
    )
    event = loop.collect_authority_event(
        client, "Flow-Research/workstream", action="cancel",
        initiative_id="WS-ENG-001", chunk_id="WS-ENG-001-04B",
        reason="Cancel", run_id=42, dispatcher="dispatcher",
        main_sha="a" * 40, prior_state_tip="e" * 40,
        start_permissions=frozenset({"write", "maintain", "admin"}),
    )
    assert event["approvers"] == ["reviewer"]
    assert "authorization" not in event


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", 99, "run_id"),
        ("run_attempt", 2, "first-attempt"),
        ("event", "push", "first-attempt"),
        ("head_branch", "feature", "expected main"),
        ("head_sha", "f" * 40, "expected main"),
        ("actor", {"login": "other"}, "dispatcher"),
    ],
)
def test_collect_authority_event_rejects_untrusted_run(
    field: str, value: object, message: str
) -> None:
    run = {
        "id": 41,
        "run_attempt": 1,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": "a" * 40,
        "actor": {"login": "dispatcher"},
        "created_at": "2026-07-20T11:00:00Z",
    }
    run[field] = value
    with pytest.raises(loop.LoopMemoryError, match=message):
        loop.collect_authority_event(
            _Client(run, [{"state": "approved", "user": {"login": "reviewer"}, "environments": [{"id": 7, "name": "loop-memory-start"}]}]),
            "Flow-Research/workstream",
            action="start",
            initiative_id="WS-ENG-001",
            chunk_id="WS-ENG-001-04B",
            reason="Approved",
            run_id=41,
            dispatcher="dispatcher",
            main_sha="a" * 40,
            prior_state_tip="e" * 40,
            start_permissions=frozenset({"write", "maintain", "admin"}),
        )


def test_load_legacy_exemptions_is_closed_and_sorted(tmp_path: Path) -> None:
    policy = tmp_path / loop.LEGACY_EXEMPTIONS_PATH
    policy.parent.mkdir(parents=True)
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exemptions": [
                    {
                        "initiative_id": "WS-AUTH-001",
                        "chunk_id": "WS-AUTH-001-PREP",
                        "pr_number": 162,
                    }
                ],
            }
        )
    )
    assert loop.load_legacy_exemptions(tmp_path)[0]["pr_number"] == 162
    policy.write_text('{"schema_version":1,"exemptions":"bad"}')
    with pytest.raises(loop.LoopMemoryError, match="unsupported"):
        loop.load_legacy_exemptions(tmp_path)


def test_cutover_inventory_is_loaded_from_exact_historical_commit(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    policy = repository / loop.LEGACY_EXEMPTIONS_PATH
    policy.parent.mkdir(parents=True)
    subprocess.run(["git", "init", str(repository)], check=True, stdout=subprocess.PIPE)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "Loop Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "loop@test.invalid"],
        check=True,
    )
    inventory_a = {
        "schema_version": 1,
        "exemptions": [
            {"initiative_id": "WS-ART-001", "chunk_id": "WS-ART-001-02C2", "pr_number": 159}
        ],
    }
    inventory_b = {
        "schema_version": 1,
        "exemptions": [
            {"initiative_id": "WS-AUTH-001", "chunk_id": "WS-AUTH-001-PREP", "pr_number": 162}
        ],
    }
    policy.write_text(json.dumps(inventory_a), encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-m", "cutover"],
        check=True,
        stdout=subprocess.PIPE,
    )
    cutover_sha = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    policy.write_text(json.dumps(inventory_b), encoding="utf-8")

    assert loop.load_legacy_exemptions_at_commit(repository, cutover_sha) == inventory_a[
        "exemptions"
    ]
    with pytest.raises(loop.LoopMemoryError, match="no bounded"):
        loop.load_legacy_exemptions_at_commit(repository, "f" * 40)


def test_apply_event_cli_routes_authenticated_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _event("start")
    captured = {}
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(loop, "_assert_state_branch", lambda _root: None)
    monkeypatch.setattr(loop, "GitHubClient", lambda _token, _url: object())
    basis = _record()
    monkeypatch.setattr(loop, "_load_json", lambda _path: basis)
    monkeypatch.setattr(loop, "_load_ledger", lambda _path: [])
    monkeypatch.setattr(loop, "_validate_ledger_entries", lambda _rows: [basis])
    monkeypatch.setattr(
        loop, "resolve_start_selection", lambda *_args, **_kwargs: {"selection": True}
    )
    monkeypatch.setattr(
        loop, "load_start_permissions", lambda _root: frozenset({"write", "maintain", "admin"})
    )

    def collect(_client, _repository, **kwargs):
        captured.update(kwargs)
        return event

    monkeypatch.setattr(loop, "collect_authority_event", collect)
    monkeypatch.setattr(
        loop,
        "apply_authority_event",
        lambda _root, supplied, repository_root, branch_root: supplied is event,
    )
    monkeypatch.setattr(loop, "validate_generated_state", lambda _root: None)
    result = loop.main(
        [
            "apply-event",
            "--repository", "Flow-Research/workstream",
            "--repository-root", str(tmp_path),
            "--state-root", str(tmp_path / "state"),
            "--branch-root", str(tmp_path / "branch"),
            "--action", "start",
            "--initiative-id", "WS-ENG-001",
            "--chunk-id", "WS-ENG-001-04B",
            "--reason", "Approved",
            "--run-id", "41",
            "--dispatcher", "dispatcher",
            "--main-sha", "a" * 40,
            "--prior-state-tip", "e" * 40,
        ]
    )
    assert result == 0
    assert captured["run_id"] == 41
    assert "event applied" in capsys.readouterr().out


def test_cancel_cli_does_not_load_start_authority_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = _event("cancel")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(loop, "_assert_state_branch", lambda _root: None)
    monkeypatch.setattr(loop, "GitHubClient", lambda _token, _url: object())
    active = _record()
    active["active"]["implementation_chunk"] = "WS-ENG-001-04B"
    active["event"] = _event("start")
    monkeypatch.setattr(loop, "_load_json", lambda _path: active)
    monkeypatch.setattr(loop, "_load_ledger", lambda _path: [])
    monkeypatch.setattr(loop, "_validate_ledger_entries", lambda _rows: [active])
    monkeypatch.setattr(
        loop, "_latest_by_initiative", lambda _rows: {"WS-ENG-001": active}
    )
    monkeypatch.setattr(
        loop,
        "load_start_permissions",
        lambda _root: (_ for _ in ()).throw(AssertionError("must not load")),
    )
    monkeypatch.setattr(
        loop, "collect_authority_event", lambda _client, _repository, **_kwargs: event
    )
    monkeypatch.setattr(
        loop,
        "apply_authority_event",
        lambda _root, supplied, repository_root, branch_root: supplied is event,
    )
    monkeypatch.setattr(loop, "validate_generated_state", lambda _root: None)
    assert loop.main(
        [
            "apply-event", "--repository", "Flow-Research/workstream",
            "--repository-root", str(tmp_path), "--state-root", str(tmp_path / "state"),
            "--branch-root", str(tmp_path / "branch"), "--action", "cancel",
            "--initiative-id", "WS-ENG-001", "--chunk-id", "WS-ENG-001-04B",
            "--reason", "Cancel", "--run-id", "41", "--dispatcher", "dispatcher",
            "--main-sha", "a" * 40, "--prior-state-tip", "e" * 40,
        ]
    ) == 0


def test_update_cli_applies_cutover_only_from_explicit_repository_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record()
    record["completed_chunk"] = {
        **record["completed_chunk"],
        "chunk_id": "WS-ENG-001-04B",
    }
    captured: list[dict] = []
    repository_root = tmp_path / "repository"
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(loop, "_assert_state_branch", lambda _root: None)
    monkeypatch.setattr(loop, "GitHubClient", lambda _token, _url: object())
    monkeypatch.setattr(loop, "collect_merge_record", lambda *_args: record.copy())
    monkeypatch.setattr(loop, "validate_generated_state", lambda _root: None)
    monkeypatch.setattr(
        loop, "apply_merge_record", lambda _root, supplied: captured.append(supplied) or True
    )
    monkeypatch.setattr(
        loop,
        "load_legacy_exemptions_at_commit",
        lambda root, sha: [{"repository_root": str(root), "commit_sha": sha}],
    )

    common = [
        "update",
        "--repository", "Flow-Research/workstream",
        "--repository-root", str(repository_root),
        "--merge-sha", "a" * 40,
        "--state-root", str(tmp_path / "state"),
    ]
    assert loop.main(common) == 0
    assert "event" not in captured[-1]

    assert loop.main(common + ["--cutover-chunk-id", "WS-ENG-001-04B"]) == 0
    assert captured[-1]["event"]["type"] == "cutover"
    assert captured[-1]["legacy_exemptions"] == [
        {"repository_root": str(repository_root), "commit_sha": "a" * 40}
    ]


def test_publish_cli_routes_repository_owned_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured = {}

    def publish(branch, output, **kwargs):
        captured.update(branch=branch, output=output, **kwargs)
        return "f" * 40

    monkeypatch.setattr(loop, "publish_generated_state", publish)
    assert loop.main(
        [
            "publish", "--branch-root", str(tmp_path / "branch"),
            "--output-root", str(tmp_path / "output"),
            "--expected-prior-tip", "e" * 40,
            "--message", "bounded message",
        ]
    ) == 0
    assert captured["expected_prior_tip"] == "e" * 40
    assert "published as" in capsys.readouterr().out


@pytest.mark.parametrize(
    "event",
    [
        {"type": "cutover"},
        {"type": "cutover", "main_sha": "f" * 40, "legacy_exemptions": []},
        {"type": "cutover", "main_sha": "a" * 40, "legacy_exemptions": [{"bad": True}]},
    ],
)
def test_cutover_event_must_match_merge_and_inventory(event: dict) -> None:
    with pytest.raises(loop.LoopMemoryError):
        loop._validate_cutover_event(event, [], "a" * 40)


def test_state_tip_resolution_fails_closed_outside_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()
    with pytest.raises(loop.LoopMemoryError, match="cannot resolve"):
        loop._state_branch_tip(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda record: record["authority_state"]["completed_chunk"].update(
            initiative_id="WS-ART-001"
        ),
        lambda record: record["authority_state"]["source"].update(pr_number=999),
        lambda record: record["authority_state"]["completed_chunk"].update(
            chunk_title="Tampered basis"
        ),
        lambda record: record["event"].update(chunk_id="WS-ENG-001-99"),
    ],
)
def test_authority_transition_is_bound_to_preceding_basis(
    tmp_path: Path, mutation
) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    loop.apply_authority_event(
        state_root, _event("start"), repository_root=repository_root
    )
    records = [entry["record"] for entry in loop._load_ledger(state_root / loop.LEDGER_PATH)]
    authority = json.loads(json.dumps(records[-1]))
    mutation(authority)
    with pytest.raises(loop.LoopMemoryError):
        loop._validate_authority_transition(authority, records[:-1])


def test_authority_transition_requires_prior_basis(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    loop.apply_authority_event(
        state_root, _event("start"), repository_root=repository_root
    )
    authority = loop._load_ledger(state_root / loop.LEDGER_PATH)[-1]["record"]
    with pytest.raises(loop.LoopMemoryError, match="no preceding"):
        loop._validate_authority_transition(authority, [])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event.update(event_id="wrong"),
        lambda event: event.update(run_id=0),
        lambda event: event.update(approvers=[]),
        lambda event: event.update(approvers=["reviewer", "reviewer"]),
        lambda event: event.update(prior_state_tip="bad"),
        lambda event: event.update(chunk_id="bad"),
    ],
)
def test_authority_event_schema_rejects_malformed_evidence(mutation) -> None:
    event = _event("start")
    mutation(event)
    with pytest.raises(loop.LoopMemoryError):
        loop._validate_event(event)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event["authorization"].update(actor="forged"),
        lambda event: event["authorization"].update(schema_version=2),
        lambda event: event["authorization"].update(type="environment"),
        lambda event: event.update(type="cancel", event_id="github-actions:41:cancel"),
    ],
)
def test_dispatcher_authority_schema_rejects_malformed_attribution(mutation) -> None:
    event = _dispatcher_start()
    mutation(event)
    with pytest.raises(loop.LoopMemoryError, match="dispatcher authorization"):
        loop._validate_event(event)


def test_collect_authority_event_rejects_invalid_approval_shape() -> None:
    run = {
        "id": 41,
        "run_attempt": 1,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": "a" * 40,
        "actor": {"login": "dispatcher"},
        "created_at": "2026-07-20T11:00:00Z",
    }
    with pytest.raises(loop.LoopMemoryError, match="approval history"):
        loop.collect_authority_event(
            _Client(run, {}),
            "Flow-Research/workstream",
            action="cancel", initiative_id="WS-ENG-001",
            chunk_id="WS-ENG-001-04B", reason="Approved", run_id=41,
            dispatcher="dispatcher", main_sha="a" * 40,
            prior_state_tip="e" * 40,
            start_permissions=frozenset({"write", "maintain", "admin"}),
        )


def test_collect_start_rejects_dispatcher_without_current_write_access() -> None:
    run = {
        "id": 41,
        "run_attempt": 1,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": "a" * 40,
        "actor": {"login": "dispatcher"},
        "created_at": "2026-07-20T11:00:00Z",
    }
    with pytest.raises(loop.LoopMemoryError, match="no permitted repository write access"):
        loop.collect_authority_event(
            _Client(run, [], {"permission": "read"}), "Flow-Research/workstream", action="start",
            initiative_id="WS-ENG-001", chunk_id="WS-ENG-001-04B",
            reason="Approved", run_id=41, dispatcher="dispatcher",
            main_sha="a" * 40, prior_state_tip="e" * 40,
            start_permissions=frozenset({"write", "maintain", "admin"}),
        )


def test_load_start_permissions_is_closed(tmp_path: Path) -> None:
    policy = tmp_path / loop.START_AUTHORITIES_PATH
    policy.parent.mkdir(parents=True)
    policy.write_text(
        json.dumps({"schema_version": 2, "permissions": ["admin", "maintain", "push", "write"]}),
        encoding="utf-8",
    )
    assert loop.load_start_permissions(tmp_path) == frozenset({"admin", "maintain", "push", "write"})


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"schema_version": 2, "permissions": ["write"], "extra": True}, "schema"),
        ({"schema_version": 1, "permissions": ["admin", "maintain", "push", "write"]}, "permissions"),
        ({"schema_version": 2, "permissions": ["write"]}, "permissions"),
    ],
)
def test_load_start_permissions_rejects_malformed_policy(
    tmp_path: Path, payload: dict, message: str
) -> None:
    policy = tmp_path / loop.START_AUTHORITIES_PATH
    policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(loop.LoopMemoryError, match=message):
        loop.load_start_permissions(tmp_path)


def test_well_formed_stale_state_tip_is_rejected(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    event = _event("start")
    event["prior_state_tip"] = "f" * 40
    before = {path: path.read_bytes() for path in state_root.rglob("*") if path.is_file()}
    with pytest.raises(loop.LoopMemoryError, match="prior state tip is stale"):
        loop.apply_authority_event(state_root, event, repository_root=repository_root)
    assert before == {path: path.read_bytes() for path in state_root.rglob("*") if path.is_file()}


def test_same_event_id_with_different_bytes_is_collision(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    event = _event("start")
    loop.apply_authority_event(state_root, event, repository_root=repository_root)
    conflict = json.loads(json.dumps(event))
    conflict["reason"] = "Different signed bytes"
    with pytest.raises(loop.LoopMemoryError, match="different bytes"):
        loop.apply_authority_event(state_root, conflict, repository_root=repository_root)


def test_cancel_rejects_inactive_chunk(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    with pytest.raises(loop.LoopMemoryError, match="not the active chunk"):
        loop.apply_authority_event(
            state_root, _event("cancel"), repository_root=repository_root
        )


def test_cross_initiative_start_preserves_parallel_active_work(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    later = _record()
    later["source"].update(
        main_sha="c" * 40, first_parent_sha="a" * 40, pr_number=170,
        pr_url="https://github.com/Flow-Research/workstream/pull/170",
        intent_path=".agent-loop/merge-intents/WS-ART-001-02.json",
    )
    later["completed_chunk"].update(
        initiative_id="WS-ART-001", chunk_id="WS-ART-001-02",
        chunk_title="Artifact Custody", next_chunk_id="WS-ART-001-03",
        next_chunk_title="Artifact Recovery",
    )
    later["gate"].update(
        next_chunk_id="WS-ART-001-03", next_chunk_title="Artifact Recovery"
    )
    loop.apply_merge_record(state_root, later)
    event = _event("start")
    event["main_sha"] = "c" * 40
    loop.apply_authority_event(state_root, event, repository_root=repository_root)
    art_contract = repository_root / ".agent-loop/initiatives/art/chunks/WS-ART-001-03-recovery.md"
    art_contract.parent.mkdir(parents=True)
    art_contract.write_text("# Chunk Contract: WS-ART-001-03\n")
    art_event = _event("start", 44)
    art_event.update(
        main_sha="c" * 40,
        initiative_id="WS-ART-001",
        chunk_id="WS-ART-001-03",
    )
    assert loop.apply_authority_event(
        state_root, art_event, repository_root=repository_root
    )
    latest = loop._latest_by_initiative(
        loop._validate_ledger_entries(loop._load_ledger(state_root / loop.LEDGER_PATH))
    )
    assert latest["WS-ENG-001"]["active"]["implementation_chunk"] == "WS-ENG-001-04B"
    assert latest["WS-ART-001"]["active"]["implementation_chunk"] == "WS-ART-001-03"
    loop.validate_generated_state(state_root)


@pytest.mark.parametrize("close_order", ["merge_then_cancel", "cancel_then_merge"])
def test_three_initiatives_mix_phases_and_isolate_close_operations(
    tmp_path: Path, close_order: str,
) -> None:
    state_root, repository_root, ci_record, ci_event = _selected_start_fixture(tmp_path)
    _contract(repository_root)
    main_sha = ci_record["source"]["main_sha"]

    eng_record = _record()
    art_record = json.loads(json.dumps(_record()))
    art_record["source"].update(
        main_sha="c" * 40, first_parent_sha="a" * 40, pr_number=170,
        pr_url="https://github.com/Flow-Research/workstream/pull/170",
        intent_path=".agent-loop/merge-intents/WS-ART-001-02.json",
    )
    art_record["completed_chunk"].update(
        initiative_id="WS-ART-001", chunk_id="WS-ART-001-02",
        chunk_title="Artifact Custody", next_chunk_id="WS-ART-001-03",
        next_chunk_title="Artifact Recovery",
    )
    art_record["gate"].update(
        next_chunk_id="WS-ART-001-03", next_chunk_title="Artifact Recovery"
    )
    ci_record["source"]["first_parent_sha"] = "c" * 40
    loop.apply_merge_record(state_root, eng_record)
    loop.apply_merge_record(state_root, art_record)
    loop.apply_merge_record(state_root, ci_record)

    eng_event = _event("start", 41)
    eng_event["main_sha"] = main_sha
    assert loop.apply_authority_event(
        state_root, eng_event, repository_root=repository_root
    )
    duplicate_eng = _event("start", 46)
    duplicate_eng["main_sha"] = main_sha
    with pytest.raises(loop.LoopMemoryError, match="initiative already has an active chunk"):
        loop.apply_authority_event(
            state_root, duplicate_eng, repository_root=repository_root
        )
    art_event = _event("start", 42)
    art_event.update(
        main_sha=main_sha, initiative_id="WS-ART-001", chunk_id="WS-ART-001-03"
    )
    assert loop.apply_authority_event(
        state_root, art_event, repository_root=repository_root
    )
    ci_event.update(
        run_id=43, event_id="github-actions:43:start",
        created_at="2026-07-20T13:00:00Z",
    )
    assert loop.apply_authority_event(
        state_root, ci_event, repository_root=repository_root
    )

    records = loop._validate_ledger_entries(loop._load_ledger(state_root / loop.LEDGER_PATH))
    latest = loop._latest_by_initiative(records)
    assert latest["WS-ENG-001"]["active"]["implementation_chunk"] == "WS-ENG-001-04B"
    assert latest["WS-ART-001"]["active"]["implementation_chunk"] == "WS-ART-001-03"
    assert latest["WS-CI-001"]["active"]["planning_chunk"] == "WS-CI-001-02"
    rendered = (state_root / loop.RENDERED_PATH).read_text(encoding="utf-8")
    assert "Active implementation chunks: `WS-ART-001-03`, `WS-ENG-001-04B`" in rendered
    assert "Active planning chunks: `WS-CI-001-02`" in rendered
    queue = (state_root / loop.WORK_QUEUE_PATH).read_text(encoding="utf-8")
    assert "Signed merge/start/cancel projection" in queue
    assert "Unsigned chat or worktree starts are not represented" in queue
    for initiative_id, chunk_id in (
        ("WS-ENG-001", "WS-ENG-001-04B"),
        ("WS-ART-001", "WS-ART-001-03"),
        ("WS-CI-001", "WS-CI-001-02"),
    ):
        assert f"| `{initiative_id}`" in queue
        assert f"| `active` | `{chunk_id}`" in queue

    wrong_cancel = _event("cancel", 44)
    wrong_cancel.update(
        main_sha=main_sha, initiative_id="WS-ART-001", chunk_id="WS-ENG-001-04B"
    )
    with pytest.raises(loop.LoopMemoryError, match="crosses initiative scope"):
        loop.apply_authority_event(
            state_root, wrong_cancel, repository_root=repository_root
        )
    wrong_merge = json.loads(json.dumps(eng_record))
    wrong_merge["source"].update(
        main_sha="f" * 40, first_parent_sha=main_sha, pr_number=180,
        pr_url="https://github.com/Flow-Research/workstream/pull/180",
        intent_path=".agent-loop/merge-intents/WS-ART-001-03.json",
    )
    wrong_merge["completed_chunk"].update(
        chunk_id="WS-ART-001-03", chunk_title="Artifact Recovery",
        next_chunk_id=None, next_chunk_title=None,
    )
    wrong_merge["gate"].update(next_chunk_id=None, next_chunk_title=None)
    with pytest.raises(loop.LoopMemoryError):
        loop.apply_merge_record(state_root, wrong_merge)

    eng_merge = json.loads(json.dumps(eng_record))
    eng_merge["source"].update(
        main_sha="f" * 40, first_parent_sha=main_sha, pr_number=181,
        pr_url="https://github.com/Flow-Research/workstream/pull/181",
        intent_path=".agent-loop/merge-intents/WS-ENG-001-04B.json",
    )
    eng_merge["completed_chunk"].update(
        chunk_id="WS-ENG-001-04B", chunk_title="Signed Explicit Start Events",
        next_chunk_id=None, next_chunk_title=None,
    )
    eng_merge["gate"].update(next_chunk_id=None, next_chunk_title=None)

    def merge_eng(*, expect_art_active: bool) -> None:
        assert loop.apply_merge_record(state_root, eng_merge)
        current = loop._latest_by_initiative(
            loop._validate_ledger_entries(loop._load_ledger(state_root / loop.LEDGER_PATH))
        )
        assert current["WS-ENG-001"]["active"] == {
            "planning_chunk": None, "implementation_chunk": None,
        }
        assert current["WS-ART-001"]["active"]["implementation_chunk"] == (
            "WS-ART-001-03" if expect_art_active else None
        )
        assert current["WS-CI-001"]["active"]["planning_chunk"] == "WS-CI-001-02"

    def cancel_art(current_main: str) -> None:
        art_cancel = _event("cancel", 45)
        art_cancel.update(
            main_sha=current_main, initiative_id="WS-ART-001",
            chunk_id="WS-ART-001-03",
        )
        assert loop.apply_authority_event(
            state_root, art_cancel, repository_root=repository_root
        )
        current = loop._latest_by_initiative(
            loop._validate_ledger_entries(loop._load_ledger(state_root / loop.LEDGER_PATH))
        )
        assert current["WS-ART-001"]["active"] == {
            "planning_chunk": None, "implementation_chunk": None,
        }
        assert current["WS-CI-001"]["active"]["planning_chunk"] == "WS-CI-001-02"

    if close_order == "merge_then_cancel":
        merge_eng(expect_art_active=True)
        cancel_art("f" * 40)
    else:
        cancel_art(main_sha)
        merge_eng(expect_art_active=False)

    latest = loop._latest_by_initiative(
        loop._validate_ledger_entries(loop._load_ledger(state_root / loop.LEDGER_PATH))
    )
    assert latest["WS-ART-001"]["active"] == {
        "planning_chunk": None, "implementation_chunk": None,
    }
    assert latest["WS-ENG-001"]["active"] == {
        "planning_chunk": None, "implementation_chunk": None,
    }
    assert latest["WS-CI-001"]["active"]["planning_chunk"] == "WS-CI-001-02"
    ci_projection = (
        state_root / loop.INITIATIVE_STATE_ROOT / "WS-CI-001.md"
    ).read_text(encoding="utf-8")
    assert "Signed merge/start/cancel state" in ci_projection
    loop.validate_generated_state(state_root)
    assert checker.generated_state_failures(state_root, repository_root) == []


def test_exact_active_merge_closes_and_consumes_exemption(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    base = _record()
    base["legacy_exemptions"] = [
        {"initiative_id": "WS-ENG-001", "chunk_id": "WS-ENG-001-04B", "pr_number": 171}
    ]
    loop.apply_merge_record(state_root, base)
    loop.apply_authority_event(state_root, _event("start"), repository_root=repository_root)
    merged = _record()
    merged["source"].update(
        main_sha="c" * 40, first_parent_sha="a" * 40, pr_number=171,
        pr_url="https://github.com/Flow-Research/workstream/pull/171",
        intent_path=".agent-loop/merge-intents/WS-ENG-001-04B.json",
    )
    merged["completed_chunk"].update(
        chunk_id="WS-ENG-001-04B", chunk_title="Signed Explicit Start Events",
        next_chunk_id=None, next_chunk_title=None,
    )
    merged["gate"].update(next_chunk_id=None, next_chunk_title=None)
    assert loop.apply_merge_record(state_root, merged)
    state = json.loads((state_root / loop.STATE_PATH).read_text())
    assert state["active"]["implementation_chunk"] is None
    assert state["legacy_exemptions"] == []


def test_publication_push_failure_leaves_remote_tip_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    branch, remote, output, repository_root = (
        tmp_path / "branch", tmp_path / "remote.git", tmp_path / "output", tmp_path / "repo"
    )
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "init", "--initial-branch", loop.STATE_BRANCH, str(branch)], check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "-C", str(branch), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(branch), "config", "user.email", "test@example.com"], check=True)
    loop.apply_merge_record(branch, _record())
    subprocess.run(["git", "-C", str(branch), "add", ".agent-loop"], check=True)
    subprocess.run(["git", "-C", str(branch), "commit", "-m", "base"], check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "-C", str(branch), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(branch), "push", "origin", loop.STATE_BRANCH], check=True, stdout=subprocess.PIPE)
    prior = subprocess.run(["git", "-C", str(branch), "rev-parse", "HEAD"], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
    shutil.copytree(branch / ".agent-loop", output / ".agent-loop")
    _contract(repository_root)
    event = _event("start")
    event["prior_state_tip"] = prior
    def real_tip(root: Path) -> str:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
    monkeypatch.setattr(loop, "_state_branch_tip", real_tip)
    loop.apply_authority_event(output, event, repository_root=repository_root, branch_root=branch)
    real_run = subprocess.run

    def fail_push(args, **kwargs):
        if isinstance(args, list) and "push" in args:
            raise subprocess.CalledProcessError(1, args)
        return real_run(args, **kwargs)

    monkeypatch.setattr(loop.subprocess, "run", fail_push)
    with pytest.raises(loop.LoopMemoryError, match="fast-forward"):
        loop.publish_generated_state(
            branch, output, expected_prior_tip=prior, message="test publication"
        )
    monkeypatch.setattr(loop.subprocess, "run", real_run)
    remote_tip = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", loop.STATE_BRANCH], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
    assert remote_tip == prior
    published = loop.publish_generated_state(
        branch, output, expected_prior_tip=prior, message="test publication"
    )
    assert published and published != prior
    remote_tip = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", loop.STATE_BRANCH],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    assert remote_tip == published
