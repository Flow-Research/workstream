"""Setup proposals retain source-linked PRE and POST checks without image selection."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CompilationFinding,
    ProjectGuideCompilationResult,
    validate_project_guide_compilation_result,
)
from .helpers import context, ids, result, valid_specification


def _context():
    return context(ids())


def growth_report(*, extra_checks: bool = True) -> ProjectGuideCompilationResult:
    """Return checks at both stages with optional extra source-derived suggestions."""
    base = result()
    refs = base.findings[0].evidence_refs
    suggestions = []
    for stage in ("pre_submit", "post_submit"):
        suggestions.append(
            AtomicGuideRequirement(
                suggestion_id=f"required_{stage}",
                statement="The submitted work must include the required item.",
                stage=stage,
                classification_rationale="The project guide identifies this required item.",
                check_specification=valid_specification(),
                evidence_refs=refs,
            )
        )
        if extra_checks:
            suggestions.append(
                AtomicGuideRequirement(
                    suggestion_id=f"additional_{stage}",
                    statement="The submitted work must address the additional condition.",
                    stage=stage,
                    classification_rationale="The project guide identifies this additional condition.",
                    check_specification=valid_specification(),
                    evidence_refs=refs,
                )
            )
    return base.model_copy(update={"requirements": tuple(suggestions)})


@pytest.mark.parametrize("extra_checks", [True, False])
def test_pre_and_post_suggestions_need_no_image_inventory_or_bindings(extra_checks):
    report = growth_report(extra_checks=extra_checks)
    parsed = ProjectGuideCompilationResult.model_validate_json(report.model_dump_json())
    validate_project_guide_compilation_result(_context(), parsed)
    assert {item.stage for item in parsed.requirements} == {"pre_submit", "post_submit"}
    assert len(parsed.requirements) == (4 if extra_checks else 2)
    assert all(item.evidence_refs and item.check_specification.pass_conditions for item in parsed.requirements)
    assert set(parsed.model_dump(mode="json")).isdisjoint(
        {"capability_suggestions", "pre_submit_bindings", "post_submit_bindings"}
    )
    assert "checker_capabilities" not in _context().model_dump(mode="json")


@pytest.mark.parametrize("fault", ["duplicate", "foreign_evidence"])
def test_suggestion_identity_and_source_lineage_reject_ambiguity(fault):
    report = growth_report()
    suggestions = list(report.requirements)
    if fault == "duplicate":
        suggestions[1] = suggestions[1].model_copy(update={"suggestion_id": suggestions[0].suggestion_id})
    else:
        foreign = suggestions[1].evidence_refs[0].model_copy(update={"document_version_id": uuid4()})
        suggestions[1] = suggestions[1].model_copy(update={"evidence_refs": (foreign,)})
    with pytest.raises(ValueError, match="unique" if fault == "duplicate" else "source lineage"):
        validate_project_guide_compilation_result(
            _context(), report.model_copy(update={"requirements": tuple(suggestions)})
        )


@pytest.mark.parametrize("field", ["suggestion_id", "stage", "check_specification", "evidence_refs"])
def test_each_suggestion_requires_explicit_source_linked_handoff(field):
    payload = growth_report().requirements[0].model_dump(mode="json")
    payload.pop(field)
    with pytest.raises(ValidationError, match=field):
        AtomicGuideRequirement.model_validate(payload)


def test_suggestion_rejects_empty_evidence():
    payload = growth_report().requirements[0].model_dump(mode="json")
    payload["evidence_refs"] = []
    with pytest.raises(ValidationError, match="evidence_refs"):
        AtomicGuideRequirement.model_validate(payload)


@pytest.mark.parametrize("count", [50, 100, 200, 201])
def test_source_linked_suggestion_collection_limit(count):
    template = growth_report(extra_checks=False).requirements[0].model_dump(mode="json")
    payload = growth_report(extra_checks=False).model_dump(mode="json")
    payload["requirements"] = [template | {"suggestion_id": f"r{i}"} for i in range(count)]
    if count > 200:
        with pytest.raises(ValidationError, match="at most 200"):
            ProjectGuideCompilationResult.model_validate(payload)
    else:
        validate_project_guide_compilation_result(
            _context(), ProjectGuideCompilationResult.model_validate(payload)
        )


def test_blocked_report_cannot_publish_specifications_or_artifact_policy():
    base = result()
    blocked = base.model_copy(update={
        "status": "guide_blocked",
        "submission_artifact_policy": None,
        "findings": (CompilationFinding(
            severity="blocking_gap", code="guide.invalid",
            message="The guide cannot define a valid task policy.",
            evidence_refs=base.findings[0].evidence_refs,
        ),),
        "requirements": (),
    })
    validate_project_guide_compilation_result(_context(), blocked)
    for update in (
        {"submission_artifact_policy": base.submission_artifact_policy},
        {"requirements": growth_report().requirements},
    ):
        with pytest.raises(ValueError, match="blocked guide"):
            validate_project_guide_compilation_result(_context(), blocked.model_copy(update=update))
