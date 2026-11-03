"""The setup wire describes checks before any external implementation exists."""

from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.adapters.project_agents.compilation_draft import CompilationDraftParser
from app.core.project_guide_instructions import PROJECT_GUIDE_OUTPUT_EXAMPLE
from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    ProjectGuideCompilationContext,
    validate_project_guide_compilation_result,
)


def _proposal() -> dict:
    return deepcopy(PROJECT_GUIDE_OUTPUT_EXAMPLE["result"])


def _context():
    ref = _proposal()["requirements"][0]["evidence_refs"][0]
    document = SimpleNamespace(
        source_item_id=UUID(ref["source_item_id"]),
        ingest_id=UUID(ref["document_version_id"]),
        sha256=ref["sha256"],
    )
    return SimpleNamespace(material=SimpleNamespace(documents=(document,)))


def test_complete_pre_and_post_specifications_need_no_registry_or_bindings():
    proposal = _proposal()
    parser = CompilationDraftParser(ProjectGuideCompilationResult.model_json_schema(), 100_000)
    assert parser.parse(json.dumps(proposal)) == proposal
    assert parser.canonical_candidate(_context(), proposal) == proposal
    result = ProjectGuideCompilationResult.model_validate(proposal)
    validate_project_guide_compilation_result(_context(), result)
    assert {item.stage.value for item in result.requirements} == {"pre_submit", "post_submit"}
    assert "pre_submit_bindings" not in result.model_dump()
    assert "capability_suggestions" not in result.model_dump()
    assert "checker_capabilities" not in ProjectGuideCompilationContext.model_json_schema()["properties"]


@pytest.mark.parametrize("field", ["pre_submit_bindings", "post_submit_bindings", "capability_suggestions"])
def test_implementation_selections_are_not_setup_output(field):
    proposal = _proposal()
    proposal[field] = []
    with pytest.raises(ValidationError):
        ProjectGuideCompilationResult.model_validate(proposal)


def test_pre_specification_cannot_claim_model_or_unbounded_execution():
    proposal = _proposal()
    proposal["requirements"][0]["check_specification"]["maximum_duration_seconds"] = 61
    result = ProjectGuideCompilationResult.model_validate(proposal)
    with pytest.raises(ValueError, match="pre-submit check specification is not bounded"):
        validate_project_guide_compilation_result(_context(), result)


def test_required_file_needs_its_project_pre_specification():
    proposal = _proposal()
    proposal["submission_artifact_policy"]["required_artifacts"] = ["uncovered.md"]
    result = ProjectGuideCompilationResult.model_validate(proposal)
    with pytest.raises(ValueError, match="required artifact lacks"):
        validate_project_guide_compilation_result(_context(), result)


def test_source_lineage_stays_exact_without_registry_input():
    proposal = _proposal()
    proposal["requirements"][0]["evidence_refs"][0]["sha256"] = "sha256:" + "2" * 64
    result = ProjectGuideCompilationResult.model_validate(proposal)
    with pytest.raises(ValueError, match="source lineage"):
        validate_project_guide_compilation_result(_context(), result)
