"""The accepted result envelope fits the actual PostgreSQL JSON serializer."""

import json

import pytest

from app.interfaces.project_agents import (
    MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES,
    CheckSpecification,
    ProjectGuideCompilationResult,
    project_guide_compilation_result_storage_bytes,
    validate_project_guide_compilation_result,
)
from .helpers import context, ids
from .test_capability_growth import _context as growth_context, growth_report


def large_report(length):
    """Build valid multibyte specifications within each field and collection bound."""
    report = growth_report()
    template = report.requirements[0]
    prose = "文" * length
    body = template.check_specification.model_dump(mode="json")
    body["evaluation_method"] = prose
    for field in ("check_steps", "pass_conditions", "positive_tests", "implementation_needs"):
        body[field] = [prose]
    body["inputs"][0]["purpose"] = prose
    body["failure_findings"][0]["condition"] = prose
    body["failure_findings"][0]["message"] = prose
    body["negative_tests"][0]["scenario"] = prose
    body["inability_to_evaluate"][0]["condition"] = prose
    specification = CheckSpecification.model_validate(body)
    ref = template.evidence_refs[0].model_copy(update={"section": "文" * 200})
    return report.model_copy(update={
        "requirements": tuple(template.model_copy(update={
            "suggestion_id": f"r{i}",
            "statement": prose,
            "classification_rationale": prose,
            "check_specification": specification,
            "evidence_refs": (ref, ref),
        }) for i in range(200)),
    })

def boundary_reports():
    """Find adjacent field lengths straddling the real four MiB envelope ceiling."""
    low, high = 1, 1000
    while low + 1 < high:
        middle = (low + high) // 2
        if (
            project_guide_compilation_result_storage_bytes(large_report(middle))
            <= MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES
        ):
            low = middle
        else:
            high = middle
    return large_report(low), large_report(high)


def test_multibyte_storage_threshold_uses_driver_encoding():
    below, above = boundary_reports()
    for report in (below, above):
        parsed = ProjectGuideCompilationResult.model_validate_json(report.model_dump_json())
        expected = len(json.dumps(parsed.model_dump(mode="json"), allow_nan=False).encode("utf-8"))
        assert project_guide_compilation_result_storage_bytes(parsed) == expected
        assert expected > len(parsed.model_dump_json().encode("utf-8"))
    assert project_guide_compilation_result_storage_bytes(below) <= 4_194_304
    assert project_guide_compilation_result_storage_bytes(above) > 4_194_304
    validate_project_guide_compilation_result(context(ids()), below)
    with pytest.raises(ValueError, match="compilation result exceeds storage byte limit"):
        validate_project_guide_compilation_result(context(ids()), above)


@pytest.mark.parametrize("extra_checks", [False, True])
def test_actual_sdk_parser_accepts_current_handoff(extra_checks):
    from agents import AgentOutputSchema

    schema = AgentOutputSchema(ProjectGuideCompilationResult)
    # Strict SDK parsing sees every field, including explicit linkage and evidence.
    parsed = schema.validate_json(growth_report(extra_checks=extra_checks).model_dump_json())
    validate_project_guide_compilation_result(growth_context(), parsed)
    assert len(parsed.requirements) == (4 if extra_checks else 2)


def test_stored_revalidation_enforces_storage_limit_even_with_valid_hashes():
    from app.modules.projects.guide_compilation.contracts import (
        CompilationAttemptIdentity,
        accepted_compilation_result,
        validate_accepted_compilation_result,
    )

    source = context(ids())
    below, above = boundary_reports()
    identity = CompilationAttemptIdentity.from_context(source)
    assert (
        validate_accepted_compilation_result(
            identity=identity, context=source, accepted=accepted_compilation_result(below)
        )
        == below
    )
    with pytest.raises(ValueError, match="compilation result exceeds storage byte limit"):
        validate_accepted_compilation_result(
            identity=identity, context=source, accepted=accepted_compilation_result(above)
        )
