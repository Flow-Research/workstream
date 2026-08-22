"""Reachability proofs for the hidden compilation projection boundary."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.adapters.project_agents.openai_agent_sdk import (
    OpenAIAgentSdkProjectGuideRuntime,
)

from .helpers import seed_database
from .test_projection_postgresql import _project_both


_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_PROJECTION_MODULE = (
    _BACKEND_ROOT / "app/modules/projects/guide_compilation/projections.py"
)
_LIVE_SURFACES = (
    _BACKEND_ROOT / "app/modules/projects/router.py",
    _BACKEND_ROOT / "app/workers/project_setup.py",
)
_LEGACY_METHODS = {
    "analyze_guide_sufficiency",
    "derive_submission_artifact_policy",
    "derive_post_submit_checker_policy",
}


def test_projection_module_cannot_call_legacy_inference_methods() -> None:
    """Keep the new projector deterministic and model-free by construction."""
    tree = ast.parse(_PROJECTION_MODULE.read_text(encoding="utf-8"))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called.isdisjoint(_LEGACY_METHODS)


def test_hidden_projection_methods_are_unreachable_from_routes_and_workers() -> None:
    """Prevent route or queue activation before the separately governed cutover."""
    forbidden = {
        "project_guide_sufficiency",
        "project_submission_artifact_policy",
        "GuideCompilationProjectionService",
    }
    for path in _LIVE_SURFACES:
        source = path.read_text(encoding="utf-8")
        assert all(name not in source for name in forbidden)


@pytest.mark.asyncio
async def test_poisoned_legacy_inference_does_not_affect_projection(
    clean_postgres_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove the complete hidden path never reaches any legacy agent method."""

    async def poison(*_args, **_kwargs):
        raise AssertionError("legacy inference must remain unreachable")

    for method in _LEGACY_METHODS:
        monkeypatch.setattr(OpenAIAgentSdkProjectGuideRuntime, method, poison)
    values = await seed_database(clean_postgres_database)
    receipts = await _project_both(clean_postgres_database, values)
    assert receipts[2].disposition == "projected"
    assert receipts[4].disposition == "projected"
