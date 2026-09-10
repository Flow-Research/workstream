"""Syntax-aware negative reachability proofs for the hidden finalization owner."""

import ast
import subprocess
import sys
from pathlib import Path

from tests.architecture_ast import imported_symbols_and_calls

ROOT = Path(__file__).resolve().parents[4]
OWNER = ROOT / "app/modules/projects/guide_compilation"
SOURCES = (
    OWNER / "finalization.py",
    OWNER / "finalization_payloads.py",
    OWNER / "custody_payloads.py",
    OWNER / "repository.py",
    OWNER.parent / "api/setup_identity.py",
)


def imports_and_calls(paths):
    imports = set()
    calls = set()
    for path in paths:
        path_imports, path_calls = imported_symbols_and_calls(ast.parse(path.read_text()))
        imports.update(path_imports)
        calls.update(path_calls)
    return imports, calls


def test_finalization_has_no_route():
    imports, calls = imports_and_calls((ROOT / "app/modules/projects/router.py",))
    assert not any("finalization" in name.lower() for name in imports | calls)


def test_worker_composes_finalization_authority_without_calling_finalizer():
    imports, calls = imports_and_calls((ROOT / "app/workers/project_setup.py",))
    assert "setup_finalization_authorization" in imports
    assert "finalize" not in calls
    assert "GuideCompilationFinalizationService" not in calls


def test_finalization_cannot_call_projection_ports():
    imports, calls = imports_and_calls(SOURCES)
    assert imports.isdisjoint(
        {
            "projections",
            "projection_payloads",
            "GuideCompilationProjectionService",
            "ArtifactPolicyProjectionPort",
            "GuideSufficiencyProjectionPort",
        }
    )
    assert calls.isdisjoint({"project_guide_sufficiency", "project_submission_artifact_policy"})


def test_finalization_cannot_import_or_call_provider():
    imports, calls = imports_and_calls(SOURCES)
    assert not any(
        name.startswith(("app.adapters.project_agents", "openai", "agents")) for name in imports
    )
    assert calls.isdisjoint({"compile_project_guide", "run", "run_sync", "create_response"})


def test_finalization_cannot_reach_superseded_inference():
    imports, calls = imports_and_calls(SOURCES)
    assert "app.modules.projects.service" not in imports
    assert calls.isdisjoint(
        {
            "analyze_guide_sufficiency",
            "derive_submission_artifact_policy",
            "derive_post_submit_checker_policy",
        }
    )


def test_finalization_cannot_reach_approval_or_activation():
    _, calls = imports_and_calls(SOURCES)
    assert calls.isdisjoint(
        {
            "approve_submission_artifact_policy",
            "activate_project_guide",
            "approve_post_submit_checker_policy",
        }
    )


def test_finalization_has_no_downstream_product_imports():
    imports, _ = imports_and_calls(SOURCES)
    assert not any(
        name.startswith(
            tuple(
                "app.modules." + owner
                for owner in ("tasks", "reviews", "contributions", "compensation", "checkers")
            )
        )
        for name in imports
    )


def test_negative_structure_probe_detects_forbidden_calls(tmp_path):
    path = tmp_path / "mutation.py"
    path.write_text(
        "from app.modules.projects.service import ProjectService\nservice.project_guide_sufficiency()\n"
    )
    imports, calls = imports_and_calls((path,))
    assert "app.modules.projects.service" in imports
    assert "project_guide_sufficiency" in calls


def assert_no_queue_dependency(paths):
    """Reject broker infrastructure and dispatch calls in the finalization owners."""
    imports, calls = imports_and_calls(paths)
    assert not any(
        name.startswith(("celery", "kombu", "app.workers", "app.modules.projects.setup_queue"))
        or name == "setup_queue"
        for name in imports
    )
    assert calls.isdisjoint(
        {
            "enqueue_project_guide_compilation",
            "dispatch_project_guide_compilation_after_commit",
            "apply_async",
            "send_task",
            "delay",
        }
    )


def test_finalization_sources_cannot_import_or_dispatch_queue():
    assert_no_queue_dependency(SOURCES)


def test_finalization_import_graph_excludes_queue_runtime():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import app.modules.projects.guide_compilation.finalization; "
            "assert not any(n.startswith(('celery', 'kombu', 'app.workers', "
            "'app.modules.projects.setup_queue')) for n in sys.modules)",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_queue_structure_proof_rejects_injected_enqueue(tmp_path):
    import pytest

    source = tmp_path / "queue_mutant.py"
    source.write_text("enqueue_project_guide_compilation(project_id='forged')\n")
    with pytest.raises(AssertionError):
        assert_no_queue_dependency((*SOURCES, source))
