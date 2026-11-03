"""The setup wire describes checks before any external implementation exists."""

from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.adapters.project_agents.compilation_draft import CompilationDraftParser
from app.core.project_guide_instructions import PROJECT_GUIDE_OUTPUT_EXAMPLE
from app.core.hashing import canonical_json_hash
from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    ProjectGuideCompilationContext,
    ProjectGuideCorrectionFeedback,
    project_guide_compilation_prompt_bytes,
    validate_project_guide_compilation_result,
)
from app.modules.projects.api.task_examples import validate_task_examples


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


def test_specification_is_descriptive_without_runtime_selection():
    proposal = _proposal()
    specification = proposal["requirements"][0]["check_specification"]
    assert set(specification) == {
        "evaluation_method", "inputs", "check_steps", "pass_conditions",
        "failure_findings", "positive_tests", "negative_tests",
        "implementation_needs", "inability_to_evaluate",
    }
    assert "runtime_dependencies" not in specification
    assert "execution_mode" not in specification
    assert "maximum_duration_seconds" not in specification
    specification["evaluation_method"] = "Compare the submitted observations with source rules."
    specification["inputs"][0]["kind"] = "source_defined_material"
    result = ProjectGuideCompilationResult.model_validate(proposal)
    validate_project_guide_compilation_result(_context(), result)


def test_work_failure_and_inability_codes_are_distinct():
    proposal = _proposal()
    specification = proposal["requirements"][0]["check_specification"]
    specification["inability_to_evaluate"][0]["code"] = specification["failure_findings"][0]["code"]
    with pytest.raises(ValidationError, match="work and evaluation inability codes must be distinct"):
        ProjectGuideCompilationResult.model_validate(proposal)


def test_input_paths_remain_canonical_when_present():
    proposal = _proposal()
    proposal["requirements"][0]["check_specification"]["inputs"][0]["relative_path"] = "../private"
    with pytest.raises(ValidationError, match="check input relative path is invalid"):
        ProjectGuideCompilationResult.model_validate(proposal)


def test_artifact_policy_paths_are_valid_without_per_file_pre_specs():
    proposal = _proposal()
    proposal["submission_artifact_policy"]["required_artifacts"] = ["uncovered.md"]
    result = ProjectGuideCompilationResult.model_validate(proposal)
    validate_project_guide_compilation_result(_context(), result)
    proposal["submission_artifact_policy"]["required_artifacts"] = ["../invalid"]
    with pytest.raises(ValidationError):
        ProjectGuideCompilationResult.model_validate(proposal)


@pytest.mark.parametrize("corrected", [False, True])
def test_model_prompt_has_exactly_documents_and_examples_without_private_canaries(corrected):
    material = SimpleNamespace(agent_projection=lambda: {"documents": [{"handle": "assigned-guide"}]})
    examples = validate_task_examples([{"content": "Assigned task example."}])
    context = ProjectGuideCompilationContext.model_construct(
        material=material,
        task_examples=examples,
        setup_run_id="private setup canary",
        setup_generation=9,
        instruction_version="private instruction canary",
        agent_identity="private agent canary",
        agent_version="private version canary",
        runtime_configuration="private registry profile binding canary",
    )
    if corrected:
        predecessor = ProjectGuideCompilationResult.model_validate(_proposal())
        feedback = ProjectGuideCorrectionFeedback(
            operation_id=uuid4(),
            predecessor_compilation_id=uuid4(),
            predecessor_result_hash=canonical_json_hash(predecessor.model_dump(mode="json")),
            target_digest="sha256:" + "1" * 64,
            reason="private previous registry profile binding canary",
        )
        context = context.model_copy(update={
            "correction_feedback": feedback,
            "correction_predecessor": predecessor,
        })
    prompt = project_guide_compilation_prompt_bytes(context)
    body = json.loads(prompt)
    assert body == {
        "material": {"documents": [{"handle": "assigned-guide"}]},
        "task_examples": [item.model_dump(mode="json") for item in examples],
    }
    assert set(body) == {"material", "task_examples"}
    assert b"private" not in prompt


def test_source_lineage_stays_exact_without_registry_input():
    proposal = _proposal()
    proposal["requirements"][0]["evidence_refs"][0]["sha256"] = "sha256:" + "2" * 64
    result = ProjectGuideCompilationResult.model_validate(proposal)
    with pytest.raises(ValueError, match="source lineage"):
        validate_project_guide_compilation_result(_context(), result)
