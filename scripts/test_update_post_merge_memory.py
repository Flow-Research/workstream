"""Focused regression tests for signed explicit loop-memory events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts import update_post_merge_memory as loop


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


def _contract(root: Path) -> None:
    path = root / ".agent-loop/initiatives/eng/chunks/WS-ENG-001-04B-events.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Chunk Contract: WS-ENG-001-04B\n", encoding="utf-8")


def test_start_cancel_retry_and_replay_are_monotonic(tmp_path: Path) -> None:
    state_root, repository_root = tmp_path / "state", tmp_path / "repo"
    _contract(repository_root)
    loop.apply_merge_record(state_root, _record())
    start = _event("start")
    assert loop.apply_authority_event(state_root, start, repository_root=repository_root)
    assert not loop.apply_authority_event(state_root, start, repository_root=repository_root)
    assert json.loads((state_root / loop.STATE_PATH).read_text())["active"][
        "implementation_chunk"
    ] == "WS-ENG-001-04B"
    cancel = _event("cancel", 42)
    assert loop.apply_authority_event(state_root, cancel, repository_root=repository_root)
    retry = _event("start", 43)
    assert loop.apply_authority_event(state_root, retry, repository_root=repository_root)
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


@dataclass
class _Client:
    run: object
    approvals: object

    def get_json(self, path: str):
        return self.approvals if path.endswith("/approvals") else self.run


def test_collect_authority_event_binds_run_and_approval_evidence() -> None:
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
            {"state": "approved", "user": {"login": "reviewer"}},
            {"state": "rejected", "user": {"login": "ignored"}},
        ],
    )
    assert loop.collect_authority_event(
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
    )["approvers"] == ["reviewer"]


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
            _Client(run, [{"state": "approved", "user": {"login": "reviewer"}}]),
            "Flow-Research/workstream",
            action="start",
            initiative_id="WS-ENG-001",
            chunk_id="WS-ENG-001-04B",
            reason="Approved",
            run_id=41,
            dispatcher="dispatcher",
            main_sha="a" * 40,
            prior_state_tip="e" * 40,
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


def test_apply_event_cli_routes_authenticated_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    event = _event("start")
    captured = {}
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(loop, "_assert_state_branch", lambda _root: None)
    monkeypatch.setattr(loop, "GitHubClient", lambda _token, _url: object())

    def collect(_client, _repository, **kwargs):
        captured.update(kwargs)
        return event

    monkeypatch.setattr(loop, "collect_authority_event", collect)
    monkeypatch.setattr(
        loop,
        "apply_authority_event",
        lambda _root, supplied, repository_root: supplied is event,
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
            action="start", initiative_id="WS-ENG-001",
            chunk_id="WS-ENG-001-04B", reason="Approved", run_id=41,
            dispatcher="dispatcher", main_sha="a" * 40,
            prior_state_tip="e" * 40,
        )
