"""Unified proposals preserve separate human review and unsupported-automation gaps."""

import pytest

from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CapabilitySuggestion,
    PostSubmissionBindingProposal,
    CapabilityParameter,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    validate_project_guide_compilation_result,
)
from app.modules.checkers.api.post_submit_catalogue import (
    PostSubmitCatalogue,
)
from tests.test_project_guide_compilation_contracts import _artifact_policy, _context, _evidence
from tests.checkers.post_submit.support import altered_catalogue, catalogue


def context(snapshot=None):
    base = _context()
    fields = base.model_dump()
    fields["post_submission_capabilities"] = PostSubmitCatalogue.model_validate(
        (snapshot or catalogue()).model_dump()
    )
    return ProjectGuideCompilationContext.model_validate(fields)


def proposal(disposition, *, binding=False):
    gap = disposition == "post_submit_capability_gap"
    return ProjectGuideCompilationResult(
        status="guide_blocked" if gap else "draft_ready",
        agent_version="v1",
        submission_artifact_policy=None if gap else _artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="quality",
                statement="Evaluate the submitted analysis.",
                disposition=disposition,
                evidence_refs=(_evidence(),),
            ),
        ),
        capability_suggestions=(CapabilitySuggestion(
            requirement_id="quality", stage="post_submit", title="Required automated analysis check",
            rationale="Engineering must provide the unavailable automated analysis evaluator.",
            evidence_refs=(_evidence(),),
        ),) if gap else (),
        post_submit_bindings=(
            PostSubmissionBindingProposal(
                requirement_id="quality",
                capability_id="check_acceptance_criteria_present",
                capability_version="v0.1",
                stage="post_submit",
            ),
        )
        if binding
        else (),
    )


def test_requirement_disposition_is_preserved():
    source = context()
    human = proposal("human_review")
    validate_project_guide_compilation_result(source, human)
    assert human.requirements[0].disposition.value == "human_review"
    assert human.post_submit_bindings == ()
    gap = proposal("post_submit_capability_gap")
    validate_project_guide_compilation_result(source, gap)
    assert gap.requirements[0].disposition.value == "post_submit_capability_gap"
    assert gap.post_submit_bindings == ()
    ready_gap = gap.model_copy(
        update={"status": "draft_ready", "submission_artifact_policy": _artifact_policy()}
    )
    with pytest.raises(ValueError, match="ready compilation cannot contain blocking"):
        validate_project_guide_compilation_result(source, ready_gap)


@pytest.mark.parametrize("disposition", ("human_review", "post_submit_capability_gap"))
def test_unbound_dispositions_cannot_acquire_a_binding(disposition):
    source = context()
    validate_project_guide_compilation_result(source, proposal(disposition))
    with pytest.raises(ValueError, match="compilation capability binding is invalid"):
        validate_project_guide_compilation_result(source, proposal(disposition, binding=True))


def test_supported_binding_is_valid_and_roundtrips():
    source = context()
    valid = proposal("supported_post_submit", binding=True)
    validate_project_guide_compilation_result(source, valid)
    assert ProjectGuideCompilationContext.model_validate_json(source.model_dump_json()) == source


@pytest.mark.parametrize(
    "change,message",
    [
        ({"capability_version": "wrong"}, "version is stale"),
        ({"capability_id": "unknown"}, "binding is invalid"),
        ({"capability_id": "check_submission_packet"}, "binding is invalid"),
        ({"stage": "pre_submit"}, "binding is invalid"),
        ({"parameters": (CapabilityParameter(name="arbitrary", value="data"),)}, "Extra inputs"),
        ({"parameters": (CapabilityParameter(name="supported_claim", value="criteria_presence"),)}, "Extra inputs"),
    ],
)
def test_binding_rejects_exact_invalid_property(change, message):
    valid = proposal("supported_post_submit", binding=True)
    binding = valid.post_submit_bindings[0]
    invalid = PostSubmissionBindingProposal(**{**binding.model_dump(), **change})
    with pytest.raises(ValueError, match=message):
        validate_project_guide_compilation_result(
            context(), valid.model_copy(update={"post_submit_bindings": (invalid,)})
        )


def test_disabled_selection_stays_a_gap_and_cannot_bind():
    source = context(altered_catalogue(state="disabled"))
    gap = proposal("post_submit_capability_gap")
    validate_project_guide_compilation_result(source, gap)
    assert gap.requirements[0].disposition.value == "post_submit_capability_gap"
    with pytest.raises(ValueError, match="definition is unavailable"):
        validate_project_guide_compilation_result(
            source, proposal("supported_post_submit", binding=True)
        )


def test_disabled_mandatory_catalogue_cannot_produce_a_ready_guide():
    with pytest.raises(ValueError, match="post-submit capability projection is unavailable"):
        validate_project_guide_compilation_result(
            context(altered_catalogue(index=0, state="disabled")), proposal("human_review")
        )
