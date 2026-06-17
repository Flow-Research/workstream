"""Regression tests for Workstream agent gate helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


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
            ".agent-loop/policies/review-policy.md",
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


def test_review_evidence_files_are_not_relevant_changes() -> None:
    """Review evidence files satisfy the gate without requiring more evidence."""
    gate = load_module("review_gate", "scripts/check_internal_review_evidence.py")
    assert not gate.is_relevant(".agent-loop/initiatives/example/reviews/review.md")
    assert not gate.is_relevant("docs/internal_reviews/example.md")


def test_evidence_requires_completed_yes_statements(tmp_path: Path, monkeypatch) -> None:
    """Evidence must contain affirmative completion statements."""
    gate = load_module("review_gate", "scripts/check_internal_review_evidence.py")
    monkeypatch.setattr(gate, "changed_files", lambda: [])
    required = ("senior engineering", "qa/test")

    weak = tmp_path / "weak.md"
    weak.write_text(
        "senior engineering\nqa/test\nopen sub-agent sessions: none\n"
        "valid findings addressed: no\n",
        encoding="utf-8",
    )
    assert "valid findings addressed: yes" in gate.validate_evidence(weak, required)

    strong = tmp_path / "strong.md"
    strong.write_text(
        "senior engineering\nqa/test\nopen sub-agent sessions: none\n"
        "valid findings addressed: yes\n",
        encoding="utf-8",
    )
    assert gate.validate_evidence(strong, required) == []


def test_evidence_must_reference_changed_chunk(tmp_path: Path, monkeypatch) -> None:
    """Evidence must mention the changed chunk contract when one exists."""
    gate = load_module("review_gate_chunk", "scripts/check_internal_review_evidence.py")
    monkeypatch.setattr(
        gate,
        "changed_files",
        lambda: [
            ".agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/"
            "chunks/WS-ENG-001-01-codex-loop-bootstrap.md"
        ],
    )
    required = ("senior engineering",)

    evidence = tmp_path / "review.md"
    evidence.write_text(
        "senior engineering\nopen sub-agent sessions: none\nvalid findings addressed: yes\n",
        encoding="utf-8",
    )
    assert "chunk id: one of ws-eng-001-01" in gate.validate_evidence(evidence, required)

    evidence.write_text(
        "WS-ENG-001-01\nsenior engineering\nopen sub-agent sessions: none\n"
        "valid findings addressed: yes\n",
        encoding="utf-8",
    )
    assert gate.validate_evidence(evidence, required) == []


def test_static_sensor_counts_untracked_text_lines(tmp_path: Path, monkeypatch) -> None:
    """The static sensor includes untracked text files in line totals."""
    sensor = load_module("agent_sensor", "scripts/workstream_agent_gate.py")
    sample = tmp_path / "new.md"
    sample.write_text("one\ntwo\n", encoding="utf-8")
    assert sensor.count_text_lines(str(sample)) == 2


def test_markdown_link_checker_collects_base_cached_dirty_and_untracked(monkeypatch) -> None:
    """Markdown link collection uses PR refs plus local dirty-tree paths."""
    checker = load_module("markdown_link_checker", "scripts/check_markdown_links.py")

    def fake_check_output(cmd: list[str], text: bool) -> str:
        joined = " ".join(cmd)
        if "rev-parse --verify origin/main" in joined:
            return "abc\n"
        if "diff --name-only origin/main...HEAD" in joined:
            return "README.md\nbackend/app/main.py\n"
        if "diff --name-only --cached" in joined:
            return ".agent-loop/README.md\n"
        if cmd == ["git", "diff", "--name-only"]:
            return "docs/glossary.md\n"
        if "ls-files --others --exclude-standard" in joined:
            return "new.md\n"
        return ""

    monkeypatch.setattr(checker.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0})(),
    )
    assert [str(path) for path in checker.changed_markdown_files()] == [
        "README.md",
        ".agent-loop/README.md",
        "docs/glossary.md",
        "new.md",
    ]
