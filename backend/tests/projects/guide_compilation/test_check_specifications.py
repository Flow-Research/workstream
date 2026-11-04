"""Pure setup specification and source-lineage contract behavior."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CheckInput,
    CheckSpecification,
    GuideEvidenceRef,
    ProjectGuideCompilationResult,
    validate_project_guide_compilation_result,
)
from app.modules.projects.guide_compilation.contracts import accepted_compilation_result
from tests.projects.guide_compilation.helpers import (
    DOCUMENT_VERSION_ID,
    SOURCE_ITEM_ID,
    SOURCE_SHA256,
    context,
    generated_result,
    ids,
    result,
    valid_specification,
)


def _specification(**updates: object) -> CheckSpecification:
    body = valid_specification().model_dump(mode="json")
    body.update(updates)
    return CheckSpecification.model_validate(body)


def _requirement(**updates: object) -> AtomicGuideRequirement:
    body: dict[str, object] = {
        "suggestion_id": "required_item",
        "statement": "The submitted work must include the required item.",
        "stage": "pre_submit",
        "classification_rationale": "The guide asks for this item before submission.",
        "check_specification": valid_specification().model_dump(mode="json"),
        "evidence_refs": [
            GuideEvidenceRef(
                source_item_id=SOURCE_ITEM_ID,
                document_version_id=DOCUMENT_VERSION_ID,
                sha256=SOURCE_SHA256,
            ).model_dump(mode="json")
        ],
    }
    body.update(updates)
    return AtomicGuideRequirement.model_validate(body)


def _with_requirement(requirement: AtomicGuideRequirement) -> ProjectGuideCompilationResult:
    return generated_result().model_copy(update={"requirements": (requirement,)})


@pytest.mark.parametrize("stage", ["pre_submit", "post_submit"])
def test_source_linked_specification_is_admitted_at_either_stage(stage: str) -> None:
    proposal = _with_requirement(_requirement(stage=stage))
    validate_project_guide_compilation_result(context(ids()), proposal)
    assert proposal.requirements[0].check_specification == valid_specification()
    assert accepted_compilation_result(proposal).canonical_result["requirements"][0]["stage"] == stage


def test_checkless_guide_does_not_require_invented_checks() -> None:
    proposal = result()
    validate_project_guide_compilation_result(context(ids()), proposal)
    assert proposal.requirements == ()


def test_suggestion_requires_exact_source_citation_and_complete_specification() -> None:
    body = _requirement().model_dump(mode="json")
    body["evidence_refs"] = []
    with pytest.raises(ValidationError, match="evidence_refs"):
        AtomicGuideRequirement.model_validate(body)

    body = _requirement().model_dump(mode="json")
    body["check_specification"]["pass_conditions"] = []
    with pytest.raises(ValidationError, match="pass_conditions"):
        AtomicGuideRequirement.model_validate(body)

    wrong_source = _requirement(evidence_refs=[
        GuideEvidenceRef(
            source_item_id=new_record_id(),
            document_version_id=DOCUMENT_VERSION_ID,
            sha256=SOURCE_SHA256,
        ).model_dump(mode="json")
    ])
    with pytest.raises(ValueError, match="source lineage"):
        validate_project_guide_compilation_result(context(ids()), _with_requirement(wrong_source))


def test_suggestion_id_is_unique_and_distinct_from_external_requirement_id() -> None:
    first = _requirement()
    duplicate = _requirement(statement="A second proposed check for the same item.")
    proposal = generated_result().model_copy(update={"requirements": (first, duplicate)})
    with pytest.raises(ValueError, match="must be unique"):
        validate_project_guide_compilation_result(context(ids()), proposal)

    body = first.model_dump(mode="json")
    body["requirement_id"] = body.pop("suggestion_id")
    with pytest.raises(ValidationError, match="suggestion_id"):
        AtomicGuideRequirement.model_validate(body)


def test_retained_hash_changes_when_a_source_derived_specification_changes() -> None:
    original = _with_requirement(_requirement())
    revised = _with_requirement(_requirement(
        check_specification=_specification(
            pass_conditions=["The required item is present and readable."]
        ).model_dump(mode="json")
    ))
    assert accepted_compilation_result(original).result_hash != accepted_compilation_result(revised).result_hash
    assert accepted_compilation_result(original).component_hashes.requirement_inventory_hash != (
        accepted_compilation_result(revised).component_hashes.requirement_inventory_hash
    )


@pytest.mark.parametrize("kind", ["package", "relative_file", "guide_context", "prepared_material"])
def test_check_input_kind_is_a_source_defined_identifier(kind: str) -> None:
    input_value = CheckInput(input_id="material", kind=kind, purpose="Material needed for evaluation.")
    assert input_value.kind == kind


@pytest.mark.parametrize("path", ["../report.txt", "/report.txt", "a//report.txt"])
def test_check_input_rejects_noncanonical_relative_path(path: str) -> None:
    with pytest.raises(ValidationError, match="relative path"):
        CheckInput(input_id="report", kind="relative_file", relative_path=path, purpose="Report to inspect.")


def test_negative_test_verdict_must_match_referenced_work_findings() -> None:
    negative = valid_specification().negative_tests[0].model_dump(mode="json")
    negative["expected_verdict"] = "passed"
    with pytest.raises(ValidationError, match="verdict disagrees"):
        _specification(negative_tests=[negative])


def test_work_findings_and_inability_codes_are_disjoint() -> None:
    finding = valid_specification().failure_findings[0].model_dump(mode="json")
    finding["code"] = "invalid_output"
    with pytest.raises(ValidationError, match="must be distinct"):
        _specification(failure_findings=[finding])


def test_every_prose_collection_member_is_validated() -> None:
    with pytest.raises(ValidationError, match="model-produced text is unsafe"):
        _specification(check_steps=["Run bash to inspect the package."])


def test_specification_is_closed_to_runtime_selection_and_provisioning() -> None:
    for name, value in (
        ("execution_mode", "background"),
        ("runtime_dependencies", []),
        ("capability_id", "workstream.default"),
    ):
        body = valid_specification().model_dump(mode="json")
        body[name] = value
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            CheckSpecification.model_validate(body)
