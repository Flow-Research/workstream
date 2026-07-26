"""Fail-closed tests for the read-only signed-state drift audit."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")

import pytest
import yaml

SCRIPT_ROOT = Path(__file__).parent
REPOSITORY_ROOT = SCRIPT_ROOT.parent
sys.path.insert(0, str(SCRIPT_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT))
from scripts import audit_loop_memory_drift as audit  # noqa: E402
from scripts import check_loop_memory_state as state_checker  # noqa: E402
from scripts import test_update_post_merge_memory as state_fixtures  # noqa: E402
from scripts import update_post_merge_memory as state_writer  # noqa: E402


MAIN = "a" * 40
STATE = "b" * 40


def _patch_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit, "verify_generated_state_signature", lambda *_: None)
    monkeypatch.setattr(audit, "validate_generated_git_tree", lambda *_: None)
    monkeypatch.setattr(audit, "generated_state_failures", lambda *_: [])
    monkeypatch.setattr(audit, "_state_main_sha", lambda *_: MAIN)


def test_audit_accepts_one_immutable_valid_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_validators(monkeypatch)
    monkeypatch.setattr(
        audit, "_git", lambda repo, *args: MAIN if repo == tmp_path / "repo" else STATE
    )
    tips = iter((MAIN, STATE, MAIN, STATE))
    monkeypatch.setattr(audit, "_remote_tip", lambda *_: next(tips))
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0),
    )
    result = audit.audit(
        tmp_path / "repo", tmp_path / "state", tmp_path / "public.pem",
        "Flow-Research/workstream", MAIN, STATE,
    )
    assert result == {
        "status": "passed",
        "main_sha": MAIN,
        "state_sha": STATE,
        "signed_state_main_sha": MAIN,
    }


@pytest.mark.parametrize("branch", ["main", "automation/loop-memory"])
def test_missing_required_branch_fails_as_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, branch: str
) -> None:
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 2, b"", b"missing"),
    )
    with pytest.raises(audit.AuditError, match="unavailable") as caught:
        audit._remote_tip(tmp_path, branch)
    assert caught.value.category == "environment"


@pytest.mark.parametrize("validator", ["signature", "tree", "semantic"])
def test_custody_or_semantic_corruption_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, validator: str
) -> None:
    _patch_validators(monkeypatch)
    monkeypatch.setattr(
        audit, "_git", lambda repo, *args: MAIN if repo == tmp_path / "repo" else STATE
    )
    monkeypatch.setattr(
        audit, "_remote_tip", lambda _repo, branch: MAIN if branch == "main" else STATE
    )
    if validator == "signature":
        monkeypatch.setattr(
            audit, "verify_generated_state_signature",
            lambda *_: (_ for _ in ()).throw(audit.LoopMemoryError("bad signature")),
        )
    elif validator == "tree":
        monkeypatch.setattr(
            audit, "validate_generated_git_tree",
            lambda *_: (_ for _ in ()).throw(audit.LoopMemoryError("unsafe tree")),
        )
    else:
        monkeypatch.setattr(audit, "generated_state_failures", lambda *_: ["stale projection"])
    with pytest.raises(audit.AuditError) as caught:
        audit.audit(tmp_path / "repo", tmp_path / "state", tmp_path / "key", "Flow-Research/workstream", MAIN, STATE)
    assert caught.value.category == "corruption"


@pytest.mark.parametrize(
    "tips,message",
    [
        (("c" * 40,), "main advanced before"),
        ((MAIN, "c" * 40), "loop-memory branch advanced before"),
        ((MAIN, STATE, "c" * 40, STATE), "advanced during"),
        ((MAIN, STATE, MAIN, "c" * 40), "advanced during"),
    ],
)
def test_branch_advancement_is_distinct_from_corruption(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tips: tuple[str, ...], message: str
) -> None:
    _patch_validators(monkeypatch)
    monkeypatch.setattr(
        audit, "_git", lambda repo, *args: MAIN if repo == tmp_path / "repo" else STATE
    )
    observed = iter(tips)
    monkeypatch.setattr(audit, "_remote_tip", lambda *_: next(observed))
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0),
    )
    with pytest.raises(audit.AuditError, match=message) as caught:
        audit.audit(tmp_path / "repo", tmp_path / "state", tmp_path / "key", "Flow-Research/workstream", MAIN, STATE)
    assert caught.value.category == "advanced"


def test_non_ancestor_signed_main_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_validators(monkeypatch)
    monkeypatch.setattr(
        audit, "_git", lambda repo, *args: MAIN if repo == tmp_path / "repo" else STATE
    )
    monkeypatch.setattr(
        audit, "_remote_tip", lambda _repo, branch: MAIN if branch == "main" else STATE
    )
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1),
    )
    with pytest.raises(audit.AuditError) as caught:
        audit.audit(tmp_path / "repo", tmp_path / "state", tmp_path / "key", "Flow-Research/workstream", MAIN, STATE)
    assert caught.value.category == "corruption"


def test_shallow_or_unavailable_history_fails_as_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_validators(monkeypatch)
    monkeypatch.setattr(
        audit, "_git", lambda repo, *args: MAIN if repo == tmp_path / "repo" else STATE
    )
    monkeypatch.setattr(
        audit, "_remote_tip", lambda _repository, branch: MAIN if branch == "main" else STATE
    )
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 128),
    )
    with pytest.raises(audit.AuditError) as caught:
        audit.audit(
            tmp_path / "repo", tmp_path / "state", tmp_path / "key",
            "Flow-Research/workstream", MAIN, STATE,
        )
    assert caught.value.category == "environment"


def test_audit_uses_repository_backed_contract_binding_and_rejects_broken_blob(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_root, repository_root, record, event = state_fixtures._selected_start_fixture(
        tmp_path
    )
    monkeypatch.setattr(state_writer, "_state_branch_tip", lambda _root: "e" * 40)
    state_writer.apply_merge_record(state_root, record)
    state_writer.apply_authority_event(
        state_root, event, repository_root=repository_root
    )
    assert state_checker.generated_state_failures(state_root, repository_root) == []

    expected_main = event["main_sha"]
    monkeypatch.setattr(audit, "verify_generated_state_signature", lambda *_: None)
    monkeypatch.setattr(audit, "validate_generated_git_tree", lambda *_: None)
    monkeypatch.setattr(
        audit, "_git",
        lambda repo, *args: expected_main if repo == repository_root else STATE,
    )
    monkeypatch.setattr(
        audit, "_remote_tip",
        lambda _repository, branch: expected_main if branch == "main" else STATE,
    )
    calls: list[tuple[Path, Path | None]] = []

    def checked_failures(root: Path, repo: Path | None = None) -> list[str]:
        calls.append((root, repo))
        return state_checker.generated_state_failures(root, repo)

    monkeypatch.setattr(audit, "generated_state_failures", checked_failures)
    result = audit.audit(
        repository_root, state_root, tmp_path / "key",
        "Flow-Research/workstream", expected_main, STATE,
    )
    assert result["status"] == "passed"
    assert calls == [(state_root, repository_root)]

    blob = event["selection"]["contract_blob_sha"]
    object_path = repository_root / ".git/objects" / blob[:2] / blob[2:]
    object_path.unlink()
    with pytest.raises(audit.AuditError) as caught:
        audit.audit(
            repository_root, state_root, tmp_path / "key",
            "Flow-Research/workstream", expected_main, STATE,
        )
    assert caught.value.category == "corruption"
    assert "selected contract" in str(caught.value)


def test_workflow_is_read_only_bounded_and_default_branch_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / ".github/workflows/loop-memory-drift-audit.yml"
    text = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    assert workflow["jobs"]["audit"]["timeout-minutes"] == 10
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["schedule"] == [{"cron": "17 3 * * *"}]
    assert triggers["repository_dispatch"] == {"types": ["loop-memory-drift-audit"]}
    assert "workflow_dispatch" not in triggers
    assert '[[ "${GITHUB_REF}" == "refs/heads/${DEFAULT_BRANCH}" ]]' in text
    assert "persist-credentials: false" in text
    assert text.count("persist-credentials: false") == 2
    assert "ref: ${{ github.event.repository.default_branch }}" in text
    assert "ref: ${{ steps.tips.outputs.state_sha }}" in text
    assert "path: loop-memory-state-audit" in text
    assert "git clone" not in text
    assert "git ls-remote" not in text
    assert text.count("GH_TOKEN: ${{ github.token }}") == 2
    assert "gh api" in text
    assert '"category":"advanced"' in text
    for forbidden in (
        "LOOP_MEMORY_SIGNING_KEY", "apply-event", "sign-state", "publish",
        "workflow_dispatch", "gh workflow run", "git push", "contents: write",
    ):
        assert forbidden not in text
    assert "continue-on-error" not in text


def main() -> int:
    return pytest.main([__file__])


if __name__ == "__main__":
    raise SystemExit(main())
