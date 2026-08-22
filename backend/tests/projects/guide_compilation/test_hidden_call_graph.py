"""Syntax-aware reachability guard for the hidden unified candidate path."""

from __future__ import annotations

import ast
from pathlib import Path

from app.modules.projects.api import ProjectGuideCompilationExecutionCommand


BACKEND = Path(__file__).resolve().parents[3]
CANDIDATE_FILES = (
    BACKEND / "app/modules/projects/guide_compilation/orchestrator.py",
    BACKEND / "app/modules/projects/guide_compilation/context.py",
)
LEGACY_RUNTIME_METHODS = {
    "analyze_guide_sufficiency",
    "derive_submission_artifact_policy",
    "derive_post_submit_checker_policy",
}
HUMAN_REQUEST_METHODS = {
    "authorize_request",
    "prepare_request",
    "consume_request",
}


def _called_attributes(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    return [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]


def test_candidate_call_graph_uses_only_the_unified_runtime_method() -> None:
    called = [name for path in CANDIDATE_FILES for name in _called_attributes(path)]
    assert called.count("compile_project_guide") == 1
    assert LEGACY_RUNTIME_METHODS.isdisjoint(called)


def test_candidate_call_graph_cannot_create_human_request_authority() -> None:
    called = [name for path in CANDIDATE_FILES for name in _called_attributes(path)]
    assert HUMAN_REQUEST_METHODS.isdisjoint(called)
    imported_names = {
        alias.name
        for path in CANDIDATE_FILES
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "HumanAuthorizationContext" not in imported_names


def test_public_selector_is_attempt_id_only() -> None:
    assert tuple(ProjectGuideCompilationExecutionCommand.model_fields) == ("attempt_id",)
