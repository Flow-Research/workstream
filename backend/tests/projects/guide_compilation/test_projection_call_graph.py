"""The live compiler has one provider path and deterministic projection owners."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "app"
REMOVED_METHODS = {
    "analyze_guide_sufficiency",
    "derive_submission_artifact_policy",
    "derive_post_submit_checker_policy",
    "run_pre_submit_setup_pipeline",
    "run_post_submit_setup_pipeline",
    "project_setup_pipeline_actor",
}


def test_superseded_inference_implementations_and_callers_are_absent():
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not ((names | calls) & REMOVED_METHODS), str(path)
    router = (ROOT / "modules/projects/router.py").read_text()
    assert "run-sufficiency-agent" not in router


def test_projection_owner_cannot_invoke_provider():
    tree = ast.parse((ROOT / "modules/projects/guide_compilation/projections.py").read_text())
    imports = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not any(
        name.startswith(("app.adapters.project_agents", "openai", "agents")) for name in imports
    )
    assert "compile_project_guide" not in calls


def test_only_projects_coordinator_calls_projection_ports_from_live_worker():
    worker = (ROOT / "workers/project_setup.py").read_text()
    coordinator = (ROOT / "modules/projects/guide_compilation/live.py").read_text()
    owner = (ROOT / "adapters/projects/__init__.py").read_text()
    assert "LiveGuideCompilationCoordinator(" in owner
    assert "LiveGuideCompilationCoordinator(" not in worker
    assert "project_guide_compilation_delivery_port(" in worker
    imports = {
        node.module or ""
        for node in ast.walk(ast.parse(worker))
        if isinstance(node, ast.ImportFrom)
    }
    assert all(
        not name.startswith("app.modules.projects.") or name.startswith("app.modules.projects.api.")
        for name in imports
    )
    for method in ["project_guide_sufficiency", "project_submission_artifact_policy"]:
        assert method + "(" in coordinator
        assert method + "(" not in worker
    assert "GuideCompilationFinalizationService(" in coordinator
    assert "compile_project_guide(" not in coordinator
