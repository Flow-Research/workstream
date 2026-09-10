"""The accepted result envelope fits the actual PostgreSQL JSON serializer."""
import json

import pytest
from agents import AgentOutputSchema

from app.interfaces.project_agents import (
    MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES, ProjectGuideCompilationResult,
    project_guide_compilation_result_storage_bytes, validate_project_guide_compilation_result,
)
from .helpers import context, ids
from .test_capability_growth import growth_report


def large_report(length):
    """Build valid multibyte prose within every individual field and array bound."""
    report = growth_report()
    requirement = report.requirements[1]
    suggestion = report.capability_suggestions[0]
    ref = suggestion.evidence_refs[0].model_copy(update={"section": "文" * 200})
    refs = (ref, ref)
    return report.model_copy(update={
        "requirements": tuple(requirement.model_copy(update={
            "requirement_id": f"r{i}", "statement": "文" * length, "evidence_refs": refs,
        }) for i in range(200)),
        "capability_suggestions": tuple(suggestion.model_copy(update={
            "requirement_id": f"r{i}", "title": "文" * length,
            "rationale": "文" * length, "evidence_refs": refs,
        }) for i in range(200)),
        "pre_submit_bindings": (), "post_submit_bindings": (),
    })


def boundary_reports():
    """Find adjacent field lengths straddling the real four MiB envelope ceiling."""
    low, high = 1, 1000
    while low + 1 < high:
        middle = (low + high) // 2
        if project_guide_compilation_result_storage_bytes(large_report(middle)) <= MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES:
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


@pytest.mark.parametrize("gaps", [False, True])
def test_actual_sdk_parser_accepts_current_handoff(gaps):
    schema = AgentOutputSchema(ProjectGuideCompilationResult)
    # Strict SDK parsing sees every field, including explicit linkage and evidence.
    parsed = schema.validate_json(growth_report(gaps=gaps).model_dump_json())
    validate_project_guide_compilation_result(context(ids()), parsed)
    assert len(parsed.capability_suggestions) == (2 if gaps else 0)


def test_stored_revalidation_enforces_storage_limit_even_with_valid_hashes():
    from app.modules.projects.guide_compilation.contracts import (
        CompilationAttemptIdentity, accepted_compilation_result, validate_accepted_compilation_result,
    )
    source = context(ids())
    below, above = boundary_reports()
    identity = CompilationAttemptIdentity.from_context(source)
    assert validate_accepted_compilation_result(identity=identity, context=source,
        accepted=accepted_compilation_result(below)) == below
    with pytest.raises(ValueError, match="compilation result exceeds storage byte limit"):
        validate_accepted_compilation_result(identity=identity, context=source,
            accepted=accepted_compilation_result(above))
