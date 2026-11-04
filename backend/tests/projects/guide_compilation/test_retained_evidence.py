"""Retained results stay verifiable without an executable old agent contract."""

from types import SimpleNamespace
import subprocess
import sys

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.projects.guide_compilation.retained_evidence import verified_compilation_result


def _retained_compilation():
    body = {
        "schema_version": "project_guide_compilation_result.v1",
        "status": "draft_ready",
        "findings": [],
        "submission_artifact_policy": {"required_artifacts": ["work.zip"]},
        "requirements": [{"id": "one"}],
        "pre_submit_bindings": [{"requirement_id": "one"}],
        "post_submit_bindings": [],
        "capability_suggestions": [],
        "setup_notes": ["Keep the original evidence."],
        "agent_name": "ProjectGuideCompilationAgent",
        "agent_version": "one",
    }
    hashes = {
        "sufficiency_hash": canonical_json_hash(
            {"status": body["status"], "findings": body["findings"]}
        ),
        "artifact_policy_hash": canonical_json_hash(body["submission_artifact_policy"]),
        "requirement_inventory_hash": canonical_json_hash({"requirements": body["requirements"]}),
        "pre_submit_hash": canonical_json_hash(
            {"pre_submit_bindings": body["pre_submit_bindings"]}
        ),
        "post_submit_hash": canonical_json_hash(
            {"post_submit_bindings": body["post_submit_bindings"]}
        ),
        "capability_suggestions_hash": canonical_json_hash(
            {"capability_suggestions": body["capability_suggestions"]}
        ),
        "setup_notes_hash": canonical_json_hash({"setup_notes": body["setup_notes"]}),
    }
    return SimpleNamespace(
        result_schema_version=None,
        canonical_result=body,
        result_hash=canonical_json_hash(body),
        component_hashes=hashes,
    )


def test_retained_result_verified_as_evidence():
    compilation = _retained_compilation()
    assert verified_compilation_result(compilation) is compilation.canonical_result
    assert "schema_version" not in compilation.component_hashes


def test_project_agent_contract_imports_before_project_api():
    """Catch the actual cold-import order used by setup adapters."""
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.interfaces.project_agents import AtomicGuideRequirement; "
            "from app.modules.projects.api.locked_policy import ProjectLockedPolicyContextFacts",
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize("change", ["result", "component", "schema", "extra_hash"])
def test_retained_result_rejects_drift(change):
    compilation = _retained_compilation()
    if change == "result":
        compilation.canonical_result["setup_notes"] = ["Changed"]
    elif change == "component":
        compilation.component_hashes["setup_notes_hash"] = "sha256:" + "f" * 64
    elif change == "schema":
        compilation.canonical_result["schema_version"] = "project_guide_check_specification.v1"
        compilation.result_hash = canonical_json_hash(compilation.canonical_result)
    else:
        compilation.component_hashes["schema_version"] = (
            "project_guide_check_specification_hashes.v1"
        )
    with pytest.raises(ValueError):
        verified_compilation_result(compilation)
