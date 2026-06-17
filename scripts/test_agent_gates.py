"""Regression tests for Workstream agent gate helpers.

Run with plain Python so the agent-gates workflow does not need test
dependencies installed before it can protect the repository process.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: str):
    """Load a script module by path."""
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_required_tracks_expand_for_loop_and_ci_paths() -> None:
    """Loop, Codex, script, and workflow paths require focused reviewers."""
    gate = load_module("review_gate", "scripts/check_internal_review_evidence.py")
    tracks = gate.required_tracks_for(
        [
            ".agent-loop/policies/engineering-review-policy.md",
            ".agents/skills/qa-review/SKILL.md",
            ".codex/agents/qa-reviewer.toml",
            ".github/workflows/agent-gates.yml",
            "scripts/workstream_agent_gate.py",
        ]
    )
    assert tracks == (
        "senior engineering",
        "qa/test",
        "security/auth",
        "product/ops",
        "architecture",
        "docs",
        "reuse/dedup",
        "ci integrity",
    )


def test_backend_config_paths_require_review_evidence() -> None:
    """Migration and backend tooling paths cannot bypass review evidence."""
    gate = load_module("review_gate_backend_paths", "scripts/check_internal_review_evidence.py")
    assert gate.is_relevant("backend/alembic/versions/0001_init.py")
    assert gate.is_relevant("backend/alembic.ini")
    assert gate.is_relevant("backend/pyproject.toml")
    assert gate.is_relevant("demos/week1_api_demo_ui/package.json")

    tracks = gate.required_tracks_for(["backend/alembic/versions/0001_init.py", "backend/pyproject.toml"])
    assert "architecture" in tracks
    assert "ci integrity" in tracks


def test_review_evidence_files_are_not_relevant_changes() -> None:
    """Review evidence files satisfy the gate without requiring more evidence."""
    gate = load_module("review_gate_relevance", "scripts/check_internal_review_evidence.py")
    assert not gate.is_relevant(".agent-loop/initiatives/example/reviews/review.md")
    assert not gate.is_relevant("docs/internal_reviews/example.md")


def test_evidence_requires_completed_yes_statements() -> None:
    """Evidence must contain affirmative completion statements."""
    gate = load_module("review_gate_statements", "scripts/check_internal_review_evidence.py")
    original_changed_files = gate.changed_files
    gate.changed_files = lambda: []
    required = ("senior engineering", "qa/test")

    with tempfile.TemporaryDirectory() as tmpdir:
        weak = Path(tmpdir) / "weak.md"
        weak.write_text(
            "| Reviewer | Result | Blocking findings |\n"
            "|---|---:|---|\n"
            "| senior engineering | PASS | None |\n"
            "| qa/test | PASS | None |\n"
            "open sub-agent sessions: none\nvalid findings addressed: no\n",
            encoding="utf-8",
        )
        assert "valid findings addressed: yes" in gate.validate_evidence(weak, required)

        strong = Path(tmpdir) / "strong.md"
        strong.write_text(
            "| Reviewer | Result | Blocking findings |\n"
            "|---|---:|---|\n"
            "| senior engineering | PASS | None |\n"
            "| qa/test | PASS | None |\n"
            "open sub-agent sessions: none\nvalid findings addressed: yes\n",
            encoding="utf-8",
        )
        assert gate.validate_evidence(strong, required) == []

    gate.changed_files = original_changed_files


def test_evidence_must_reference_changed_chunk() -> None:
    """Evidence must mention the changed chunk contract when one exists."""
    gate = load_module("review_gate_chunk", "scripts/check_internal_review_evidence.py")
    original_changed_files = gate.changed_files
    gate.changed_files = lambda: [
        ".agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/"
        "chunks/WS-ENG-001-01-codex-loop-bootstrap.md"
    ]
    required = ("senior engineering",)

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence = Path(tmpdir) / "review.md"
        evidence.write_text(
            "| Reviewer | Result | Blocking findings |\n"
            "|---|---:|---|\n"
            "| senior engineering | PASS | None |\n"
            "open sub-agent sessions: none\nvalid findings addressed: yes\n",
            encoding="utf-8",
        )
        assert "chunk id: one of ws-eng-001-01" in gate.validate_evidence(evidence, required)

        evidence.write_text(
            "WS-ENG-001-01\n"
            "| Reviewer | Result | Blocking findings |\n"
            "|---|---:|---|\n"
            "| senior engineering | PASS | None |\n"
            "open sub-agent sessions: none\nvalid findings addressed: yes\n",
            encoding="utf-8",
        )
        assert gate.validate_evidence(evidence, required) == []

    gate.changed_files = original_changed_files


def test_evidence_rejects_pending_or_blocking_reviewer_rows() -> None:
    """Evidence table rows must show passing reviewers and no blocking findings."""
    gate = load_module("review_gate_rows", "scripts/check_internal_review_evidence.py")
    original_changed_files = gate.changed_files
    gate.changed_files = lambda: []
    required = ("senior engineering", "qa/test")

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence = Path(tmpdir) / "review.md"
        evidence.write_text(
            "| Reviewer | Result | Blocking findings |\n"
            "|---|---:|---|\n"
            "| senior engineering | PASS | None |\n"
            "| qa/test | Pending | High finding |\n"
            "open sub-agent sessions: none\nvalid findings addressed: yes\n",
            encoding="utf-8",
        )
        missing = gate.validate_evidence(evidence, required)
        assert "qa/test reviewer result must be pass" in missing
        assert "qa/test blocking findings must be none" in missing

    gate.changed_files = original_changed_files


def test_evidence_main_fails_closed_on_unresolved_base_ref() -> None:
    """Configured base refs must resolve before the evidence gate can pass."""
    gate = load_module("review_gate_base_ref", "scripts/check_internal_review_evidence.py")
    original_env = os.environ.get("INTERNAL_REVIEW_BASE_REF")
    original_git_ok = gate.git_ok
    os.environ["INTERNAL_REVIEW_BASE_REF"] = "missing-base"
    gate.git_ok = lambda *args: False
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            assert gate.main() == 1
    finally:
        gate.git_ok = original_git_ok
        if original_env is None:
            os.environ.pop("INTERNAL_REVIEW_BASE_REF", None)
        else:
            os.environ["INTERNAL_REVIEW_BASE_REF"] = original_env


def test_evidence_main_reports_missing_evidence_file() -> None:
    """Changed evidence paths that no longer exist produce structured failure."""
    gate = load_module("review_gate_missing_evidence_file", "scripts/check_internal_review_evidence.py")
    original_changed_files = gate.changed_files
    gate.changed_files = lambda: [
        "scripts/workstream_agent_gate.py",
        ".agent-loop/initiatives/example/reviews/deleted.md",
    ]
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            assert gate.main() == 1
    finally:
        gate.changed_files = original_changed_files


def test_static_sensor_counts_untracked_text_lines() -> None:
    """The static sensor includes untracked text files in line totals."""
    sensor = load_module("agent_sensor", "scripts/workstream_agent_gate.py")
    with tempfile.TemporaryDirectory() as tmpdir:
        sample = Path(tmpdir) / "new.md"
        sample.write_text("one\ntwo\n", encoding="utf-8")
        assert sensor.count_text_lines(str(sample)) == 2


def test_static_sensor_requires_resolved_base_ref() -> None:
    """The static sensor must not silently pass when no base ref resolves."""
    sensor = load_module("agent_sensor_base_ref", "scripts/workstream_agent_gate.py")
    original_ref_exists = sensor.ref_exists
    original_first_existing_ref = sensor.first_existing_ref
    sensor.ref_exists = lambda ref: False
    sensor.first_existing_ref = lambda *refs: None

    report = sensor.analyze("missing-base", "HEAD")
    assert report["result"] == "REVIEW_REQUIRED"
    assert report["findings"][0]["code"] == "BASE_REF_UNRESOLVED"

    sensor.ref_exists = original_ref_exists
    sensor.first_existing_ref = original_first_existing_ref


def test_static_sensor_accumulates_numstat_for_duplicate_paths() -> None:
    """Line totals include committed, staged, and dirty changes to one file."""
    sensor = load_module("agent_sensor_numstat", "scripts/workstream_agent_gate.py")
    original_maybe_run = sensor.maybe_run

    def fake_maybe_run(cmd: list[str]) -> str:
        joined = " ".join(cmd)
        if "diff --numstat origin/main...HEAD" in joined:
            return "3\t1\tscripts/workstream_agent_gate.py"
        if cmd == ["git", "diff", "--numstat", "--cached"]:
            return "2\t0\tscripts/workstream_agent_gate.py"
        if cmd == ["git", "diff", "--numstat"]:
            return "1\t4\tscripts/workstream_agent_gate.py"
        if "ls-files --others --exclude-standard" in joined:
            return ""
        return ""

    sensor.maybe_run = fake_maybe_run

    added, deleted, rows = sensor.numstat("origin/main", "HEAD")
    assert added == 6
    assert deleted == 5
    assert rows == [("scripts/workstream_agent_gate.py", 6, 5)]

    sensor.maybe_run = original_maybe_run


def test_static_sensor_flags_backend_config_as_ci_surface() -> None:
    """Backend config and migration-control paths are CI/build sensitive."""
    sensor = load_module("agent_sensor_ci_paths", "scripts/workstream_agent_gate.py")
    assert sensor.CI_PATTERNS.search("backend/pyproject.toml")
    assert sensor.CI_PATTERNS.search("backend/alembic.ini")
    assert sensor.CI_PATTERNS.search("backend/alembic/versions/0001_init.py")


def test_markdown_link_checker_collects_base_cached_dirty_and_untracked() -> None:
    """Markdown link collection uses PR refs plus local dirty-tree paths."""
    checker = load_module("markdown_link_checker", "scripts/check_markdown_links.py")
    original_check_output = checker.subprocess.check_output
    original_run = checker.subprocess.run

    def fake_check_output(cmd: list[str], text: bool) -> str:
        joined = " ".join(cmd)
        if "diff --name-only origin/main...HEAD" in joined:
            return "README.md\nbackend/app/main.py\n"
        if "diff --name-only --cached" in joined:
            return ".agent-loop/README.md\n"
        if cmd == ["git", "diff", "--name-only"]:
            return "docs/glossary.md\n"
        if "ls-files --others --exclude-standard" in joined:
            return "new.md\n"
        return ""

    checker.subprocess.check_output = fake_check_output
    checker.subprocess.run = lambda *args, **kwargs: SimpleNamespace(returncode=0)

    assert [str(path) for path in checker.changed_markdown_files()] == [
        "README.md",
        ".agent-loop/README.md",
        "docs/glossary.md",
        "new.md",
    ]

    checker.subprocess.check_output = original_check_output
    checker.subprocess.run = original_run


def test_stale_wording_patterns_catch_variants() -> None:
    """Stale wording patterns catch case and separator variants."""
    stale = load_module("stale_wording", "scripts/check_stale_workstream_wording.py")
    sample = "\n".join(
        [
            "Garden " + "Roadmap",
            "AUTO-" + "MERGE",
            "claude " + "code",
            "task-" + "production control plane",
        ]
    )
    matches = [pattern.pattern for pattern in stale.FORBIDDEN_PATTERNS if pattern.search(sample)]
    assert matches == [
        "task-" + "production control plane",
        "garden " + "roadmap",
        "claude " + "code",
        "auto[\\s-]?merge",
    ]


def main() -> int:
    """Run all local test functions."""
    tests = [
        test_required_tracks_expand_for_loop_and_ci_paths,
        test_backend_config_paths_require_review_evidence,
        test_review_evidence_files_are_not_relevant_changes,
        test_evidence_requires_completed_yes_statements,
        test_evidence_must_reference_changed_chunk,
        test_evidence_rejects_pending_or_blocking_reviewer_rows,
        test_evidence_main_fails_closed_on_unresolved_base_ref,
        test_evidence_main_reports_missing_evidence_file,
        test_static_sensor_counts_untracked_text_lines,
        test_static_sensor_requires_resolved_base_ref,
        test_static_sensor_accumulates_numstat_for_duplicate_paths,
        test_static_sensor_flags_backend_config_as_ci_surface,
        test_markdown_link_checker_collects_base_cached_dirty_and_untracked,
        test_stale_wording_patterns_catch_variants,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} agent gate tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
