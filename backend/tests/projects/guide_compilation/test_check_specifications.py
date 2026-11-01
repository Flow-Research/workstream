"""Typed implementation handoff and generation-admission boundaries."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CapabilityParameter,
    CapabilitySuggestion,
    CheckInput,
    CheckRuntimeDependency,
    CheckSpecification,
    GuideEvidenceRef,
    PostSubmissionBindingProposal,
    PreSubmissionBindingProposal,
    ProjectGuideCompilationResult,
    require_complete_generated_specifications,
    validate_project_guide_compilation_result,
)
from app.modules.checkers.api.external import (
    EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
)
from app.modules.checkers.api.external_policy import (
    FORGE_FACTS_VERSION_KEY,
    MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS,
    SELECTED_POST_FORGE_FACTS_BUDGET_MS,
    SELECTED_POST_MATERIALIZATION_BUDGET_MS,
)
from app.modules.projects.guide_compilation.contracts import accepted_compilation_result
from tests.checkers.external.support import capability_projection, registry_entry
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
        "requirement_id": "required_item",
        "statement": "The submitted work must include the required item.",
        "disposition": "supported_pre_submit",
        "classification_rationale": "Static inspection can enforce this at intake.",
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


def _with_requirement(
    requirement: AtomicGuideRequirement,
) -> ProjectGuideCompilationResult:
    return generated_result().model_copy(update={"requirements": (requirement,)})


def _entry_with_deadline(
    deadline_ms: int, phase: str = "pre_submit"
) -> ExternalCheckerRegistryEntry:
    original = registry_entry(phase)
    body = original.model_dump()
    body["resources"]["deadline_ms"] = deadline_ms
    spec_fields = ExternalCheckerRegistrySpec.model_fields
    spec = ExternalCheckerRegistrySpec.model_validate({name: body[name] for name in spec_fields})
    body["entry_digest"] = spec.spec_digest
    return ExternalCheckerRegistryEntry.model_validate(body)


def test_valid_generated_result_and_static_specification_are_admitted() -> None:
    compilation_context = context(ids())

    require_complete_generated_specifications(compilation_context, generated_result())
    require_complete_generated_specifications(
        compilation_context, _with_requirement(_requirement())
    )


def test_generation_admission_does_not_change_retained_result_hashes() -> None:
    legacy_requirement = AtomicGuideRequirement(
        requirement_id="review_scope",
        statement="The guide provides background for claim review.",
        disposition="informational",
        evidence_refs=(
            GuideEvidenceRef(
                source_item_id=SOURCE_ITEM_ID,
                document_version_id=DOCUMENT_VERSION_ID,
                sha256=SOURCE_SHA256,
            ),
        ),
    )
    legacy = result().model_copy(update={"requirements": (legacy_requirement,)})
    accepted = accepted_compilation_result(legacy)
    reparsed = ProjectGuideCompilationResult.model_validate(accepted.canonical_result)

    assert "classification_rationale" not in accepted.canonical_result["requirements"][0]
    assert "check_specification" not in accepted.canonical_result["requirements"][0]
    assert accepted_compilation_result(reparsed) == accepted
    validate_project_guide_compilation_result(context(ids()), legacy)
    with pytest.raises(ValueError, match="outside checker specification scope"):
        require_complete_generated_specifications(context(ids()), legacy)


def test_checkless_guide_does_not_require_invented_management_requirements() -> None:
    checkless = ProjectGuideCompilationResult.model_validate(
        result().model_dump(mode="json", exclude={"setup_notes"})
    )
    validate_project_guide_compilation_result(context(ids()), checkless)
    require_complete_generated_specifications(context(ids()), checkless)


def test_every_generated_requirement_requires_source_evidence() -> None:
    requirement = _requirement(evidence_refs=[])

    with pytest.raises(ValueError, match="source evidence"):
        require_complete_generated_specifications(context(ids()), _with_requirement(requirement))


@pytest.mark.parametrize(
    ("disposition", "specification", "message"),
    [
        ("supported_pre_submit", None, "lacks a check specification"),
        ("pre_submit_capability_gap", None, "lacks a check specification"),
        (
            "human_review",
            valid_specification(),
            "outside PRE and POST checker scope",
        ),
        (
            "project_lifecycle_policy",
            valid_specification(),
            "outside PRE and POST checker scope",
        ),
    ],
)
def test_generation_admission_requires_specifications_only_for_check_dispositions(
    disposition: str,
    specification: CheckSpecification | None,
    message: str,
) -> None:
    requirement = _requirement(
        disposition=disposition,
        check_specification=(
            specification.model_dump(mode="json") if specification is not None else None
        ),
    )

    with pytest.raises(ValueError, match=message):
        require_complete_generated_specifications(context(ids()), _with_requirement(requirement))


@pytest.mark.parametrize(
    ("disposition", "execution_mode", "duration", "message"),
    [
        ("supported_pre_submit", "bounded_pre_submit", 61, "not bounded"),
        ("pre_submit_capability_gap", "background", 60, "not bounded"),
        ("supported_post_submit", "bounded_pre_submit", 60, "not background"),
        ("post_submit_capability_gap", "bounded_pre_submit", 60, "not background"),
    ],
)
def test_generation_admission_enforces_stage_from_bounded_work(
    disposition: str,
    execution_mode: str,
    duration: int,
    message: str,
) -> None:
    specification = _specification(
        execution_mode=execution_mode,
        maximum_duration_seconds=duration,
    )

    with pytest.raises(ValueError, match=message):
        require_complete_generated_specifications(
            context(ids()),
            _with_requirement(
                _requirement(
                    disposition=disposition,
                    check_specification=specification.model_dump(mode="json"),
                )
            ),
        )


@pytest.mark.parametrize("material_kind", ["task_context", "guide_context", "prepared_material"])
def test_supported_check_cannot_claim_runtime_support_the_runner_lacks(material_kind: str) -> None:
    dependency = CheckRuntimeDependency(
        dependency_id="task_material",
        kind=material_kind,
        provisioning="runtime_gap",
        purpose="Task instructions needed for evaluation.",
        unavailable_code="material_unavailable",
    )
    specification = _specification(
        inputs=[
            {
                "input_id": "task_material",
                "kind": material_kind,
                "purpose": "Task instructions needed for evaluation.",
            }
        ],
        runtime_dependencies=[dependency.model_dump(mode="json")],
        infrastructure_failures=[
            {
                "code": "material_unavailable",
                "condition": "Task instructions are unavailable.",
            }
        ],
    )

    with pytest.raises(ValueError, match="unavailable runtime support"):
        require_complete_generated_specifications(
            context(ids()),
            _with_requirement(
                _requirement(check_specification=specification.model_dump(mode="json"))
            ),
        )


@pytest.mark.parametrize("stage", ["pre_submit", "post_submit"])
def test_model_evaluation_requires_post_even_with_a_short_duration(stage: str) -> None:
    specification = _specification(
        evaluation_method="model_evaluation",
        execution_mode="bounded_pre_submit" if stage == "pre_submit" else "background",
        maximum_duration_seconds=30,
        runtime_dependencies=[
            {
                "dependency_id": "model_judge",
                "kind": "model_service",
                "provisioning": "model_proxy",
                "purpose": "Evaluate the report against the rubric.",
                "unavailable_code": "implementation_unavailable",
            }
        ],
        infrastructure_failures=[
            {
                "code": "implementation_unavailable",
                "condition": "The model service is unavailable.",
            }
        ],
    )
    requirement = _requirement(
        disposition=f"{stage}_capability_gap",
        check_specification=specification.model_dump(mode="json"),
    )
    proposal = _with_requirement(requirement).model_copy(
        update={
            "status": "draft_ready_with_warnings",
            "capability_suggestions": (
                CapabilitySuggestion(
                    requirement_id=requirement.requirement_id,
                    stage=stage,
                    title="Report evaluation",
                    rationale="The registered implementations do not evaluate this rubric.",
                    evidence_refs=requirement.evidence_refs,
                ),
            ),
        }
    )
    compilation_context = context(ids())
    validate_project_guide_compilation_result(compilation_context, proposal)
    if stage == "pre_submit":
        with pytest.raises(ValueError, match="model service requires post-submit"):
            require_complete_generated_specifications(compilation_context, proposal)
    else:
        require_complete_generated_specifications(compilation_context, proposal)


def test_model_assisted_isolated_execution_requires_post_submit() -> None:
    specification = _specification(
        evaluation_method="isolated_execution",
        execution_mode="bounded_pre_submit",
        maximum_duration_seconds=30,
        runtime_dependencies=[
            {
                "dependency_id": "execution_runner",
                "kind": "isolated_execution",
                "provisioning": "current_runner",
                "purpose": "Execute the bounded trial.",
                "unavailable_code": "implementation_unavailable",
            },
            {
                "dependency_id": "model_judge",
                "kind": "model_service",
                "provisioning": "model_proxy",
                "purpose": "Assess the authenticated trial observations.",
                "unavailable_code": "implementation_unavailable",
            },
        ],
        infrastructure_failures=[
            {
                "code": "implementation_unavailable",
                "condition": "The execution or model service is unavailable.",
            }
        ],
    )
    requirement = _requirement(
        disposition="pre_submit_capability_gap",
        check_specification=specification.model_dump(mode="json"),
    )
    proposal = _with_requirement(requirement).model_copy(
        update={
            "status": "draft_ready_with_warnings",
            "capability_suggestions": (
                CapabilitySuggestion(
                    requirement_id=requirement.requirement_id,
                    stage="pre_submit",
                    title="Trial assessment",
                    rationale="The trial requires model-assisted assessment.",
                    evidence_refs=requirement.evidence_refs,
                ),
            ),
        }
    )

    with pytest.raises(ValueError, match="model service requires post-submit"):
        require_complete_generated_specifications(context(ids()), proposal)


def test_new_generation_rejects_legacy_model_runtime_gap() -> None:
    specification = _specification(
        evaluation_method="model_evaluation",
        execution_mode="background",
        runtime_dependencies=[
            {
                "dependency_id": "model_judge",
                "kind": "model_service",
                "provisioning": "runtime_gap",
                "purpose": "Evaluate the report against the rubric.",
                "unavailable_code": "implementation_unavailable",
            }
        ],
        infrastructure_failures=[
            {
                "code": "implementation_unavailable",
                "condition": "The model service is unavailable.",
            }
        ],
    )
    requirement = _requirement(
        disposition="post_submit_capability_gap",
        check_specification=specification.model_dump(mode="json"),
    )
    proposal = _with_requirement(requirement).model_copy(
        update={
            "status": "draft_ready_with_warnings",
            "capability_suggestions": (
                CapabilitySuggestion(
                    requirement_id=requirement.requirement_id,
                    stage="post_submit",
                    title="Report evaluation",
                    rationale="The project image or exact model profile is unavailable.",
                    evidence_refs=requirement.evidence_refs,
                ),
            ),
        }
    )

    # Immutable older results remain decodable, but cannot pass new generation admission.
    ProjectGuideCompilationResult.model_validate(proposal.model_dump(mode="json"))
    with pytest.raises(ValueError, match="model service requires model proxy"):
        require_complete_generated_specifications(context(ids()), proposal)


def test_pre_submit_binding_must_fit_the_stage_budget() -> None:
    entry = _entry_with_deadline(60_001)
    compilation_context = context(ids(), checker_capabilities=capability_projection(entry))
    proposal = _with_requirement(_requirement()).model_copy(
        update={
            "pre_submit_bindings": (
                PreSubmissionBindingProposal(
                    requirement_id="required_item",
                    capability_id=entry.capability_id,
                    capability_version=entry.capability_version,
                    stage="pre_submit",
                ),
            )
        }
    )

    with pytest.raises(ValueError, match="deadline exceeds"):
        require_complete_generated_specifications(compilation_context, proposal)


@pytest.mark.parametrize(
    ("stage", "durations", "declare_gap", "admitted"),
    [
        ("post_submit", (3280,), False, True),
        ("post_submit", (3281,), False, False),
        ("post_submit", (3281,), True, True),
        ("post_submit", (1600, 1600), False, True),
        ("post_submit", (1800, 1600), False, False),
        ("post_submit", (1800, 1600), True, True),
        ("post_submit", (1,), True, False),
        ("pre_submit", (1,), True, False),
        ("pre_submit", (60,) * 59, False, True),
        ("pre_submit", (60,) * 60, False, False),
        ("pre_submit", (60,) * 60, True, True),
    ],
)
def test_proposed_capacity_includes_stage_fixed_budget_and_each_cleanup(
    stage: str, durations: tuple[int, ...], declare_gap: bool, admitted: bool
) -> None:
    requirements = []
    suggestions = []
    for index, duration in enumerate(durations):
        specification = valid_specification().model_dump(mode="json")
        specification.update(
            execution_mode="background" if stage == "post_submit" else "bounded_pre_submit",
            maximum_duration_seconds=duration,
        )
        if index == 0 and declare_gap:
            specification["runtime_dependencies"].append(
                {
                    "dependency_id": "policy_capacity",
                    "kind": "execution_capacity",
                    "provisioning": "runtime_gap",
                    "purpose": "The proposed policy exceeds the current aggregate worker budget.",
                    "unavailable_code": "capacity_exceeded",
                }
            )
            specification["infrastructure_failures"].append(
                {
                    "code": "capacity_exceeded",
                    "condition": "The runtime cannot supply the required aggregate capacity.",
                }
            )
        requirement = _requirement(
            requirement_id=f"required_item_{index}",
            disposition=f"{stage}_capability_gap",
            check_specification=specification,
        )
        requirements.append(requirement)
        suggestions.append(
            CapabilitySuggestion(
                requirement_id=requirement.requirement_id,
                stage=stage,
                title="Background package inspection",
                rationale="The required implementation is not registered.",
                evidence_refs=requirement.evidence_refs,
            )
        )
    proposal = generated_result().model_copy(
        update={
            "status": "draft_ready_with_warnings",
            "requirements": tuple(requirements),
            "capability_suggestions": tuple(suggestions),
        }
    )
    compilation_context = context(ids())
    validate_project_guide_compilation_result(compilation_context, proposal)
    if admitted:
        require_complete_generated_specifications(compilation_context, proposal)
    else:
        with pytest.raises(ValueError, match="execution capacity gap"):
            require_complete_generated_specifications(compilation_context, proposal)


@pytest.mark.parametrize(
    ("stage", "deadline_ms", "count"),
    [
        ("post_submit", 1_700_000, 2),
        ("pre_submit", 60_000, 60),
    ],
)
def test_supported_capacity_uses_registered_deadlines_not_small_estimates(
    stage: str, deadline_ms: int, count: int
) -> None:
    entry = _entry_with_deadline(deadline_ms, stage)
    compilation_context = context(ids(), checker_capabilities=capability_projection(entry))
    requirements = tuple(
        _requirement(
            requirement_id=f"required_item_{index}",
            disposition=f"supported_{stage}",
            check_specification=_specification(
                execution_mode="background" if stage == "post_submit" else "bounded_pre_submit",
                maximum_duration_seconds=1,
            ).model_dump(mode="json"),
        )
        for index in range(count)
    )
    proposal = generated_result().model_copy(
        update={
            "requirements": requirements,
            f"{stage}_bindings": tuple(
                (
                    PostSubmissionBindingProposal
                    if stage == "post_submit"
                    else PreSubmissionBindingProposal
                )(
                    requirement_id=item.requirement_id,
                    capability_id=entry.capability_id,
                    capability_version=entry.capability_version,
                    stage=stage,
                )
                for item in requirements
            ),
        }
    )
    validate_project_guide_compilation_result(compilation_context, proposal)
    with pytest.raises(ValueError, match="supported .* checks exceed"):
        require_complete_generated_specifications(compilation_context, proposal)


@pytest.mark.parametrize("reads_forge_facts", [False, True])
def test_supported_post_capacity_reserves_a_selected_forge_facts_read(
    reads_forge_facts: bool,
) -> None:
    # The registered deadline fits the stage alone, but not with the facts read.
    deadline_ms = (
        MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS
        - SELECTED_POST_MATERIALIZATION_BUDGET_MS
        - EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
        - SELECTED_POST_FORGE_FACTS_BUDGET_MS // 2
    )
    entry = _entry_with_deadline(deadline_ms, "post_submit")
    compilation_context = context(ids(), checker_capabilities=capability_projection(entry))
    requirement = _requirement(
        requirement_id="required_item_0",
        disposition="supported_post_submit",
        check_specification=_specification(
            execution_mode="background", maximum_duration_seconds=1
        ).model_dump(mode="json"),
    )
    parameters = (
        (CapabilityParameter(name=FORGE_FACTS_VERSION_KEY, value="v1"),)
        if reads_forge_facts
        else ()
    )
    proposal = generated_result().model_copy(
        update={
            "requirements": (requirement,),
            "post_submit_bindings": (
                PostSubmissionBindingProposal(
                    requirement_id=requirement.requirement_id,
                    capability_id=entry.capability_id,
                    capability_version=entry.capability_version,
                    stage="post_submit",
                    parameters=parameters,
                ),
            ),
        }
    )
    if reads_forge_facts:
        with pytest.raises(ValueError, match="supported post-submit checks exceed"):
            require_complete_generated_specifications(compilation_context, proposal)
    else:
        require_complete_generated_specifications(compilation_context, proposal)


@pytest.mark.parametrize("phase", ["pre_submit", "post_submit"])
def test_supported_specification_must_fit_the_selected_checker_deadline(
    phase: str,
) -> None:
    entry = _entry_with_deadline(30_000, phase)
    compilation_context = context(ids(), checker_capabilities=capability_projection(entry))
    specification = _specification(
        execution_mode=("bounded_pre_submit" if phase == "pre_submit" else "background"),
        maximum_duration_seconds=31,
    )
    requirement = _requirement(
        disposition=("supported_pre_submit" if phase == "pre_submit" else "supported_post_submit"),
        check_specification=specification.model_dump(mode="json"),
    )
    binding_type = (
        PreSubmissionBindingProposal if phase == "pre_submit" else PostSubmissionBindingProposal
    )
    binding = binding_type(
        requirement_id="required_item",
        capability_id=entry.capability_id,
        capability_version=entry.capability_version,
        stage=phase,
    )
    proposal = _with_requirement(requirement).model_copy(
        update={
            ("pre_submit_bindings" if phase == "pre_submit" else "post_submit_bindings"): (binding,)
        }
    )

    with pytest.raises(ValueError, match="exceeds the checker deadline"):
        require_complete_generated_specifications(compilation_context, proposal)


@pytest.mark.parametrize(
    "input_body",
    [
        {
            "input_id": "report",
            "kind": "relative_file",
            "purpose": "Report to inspect.",
        },
        {
            "input_id": "report",
            "kind": "package",
            "relative_path": "report.txt",
            "purpose": "Report to inspect.",
        },
        {
            "input_id": "report",
            "kind": "relative_file",
            "relative_path": "../report.txt",
            "purpose": "Report to inspect.",
        },
    ],
)
def test_check_input_requires_a_canonical_path_only_for_relative_material(
    input_body: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="relative path"):
        CheckInput.model_validate(input_body)


def test_negative_test_verdict_must_match_referenced_finding_levels() -> None:
    negative = valid_specification().negative_tests[0].model_dump(mode="json")
    negative["expected_verdict"] = "passed"

    with pytest.raises(ValidationError, match="verdict disagrees"):
        _specification(negative_tests=[negative])


def test_work_findings_cannot_use_reserved_infrastructure_codes() -> None:
    finding = valid_specification().failure_findings[0].model_dump(mode="json")
    finding["code"] = "deadline_exceeded"
    negative = valid_specification().negative_tests[0].model_dump(mode="json")
    negative["expected_finding_codes"] = ["deadline_exceeded"]

    with pytest.raises(ValidationError, match="must be distinct"):
        _specification(failure_findings=[finding], negative_tests=[negative])


def test_every_prose_collection_member_is_validated() -> None:
    with pytest.raises(ValidationError, match="model-produced text is unsafe"):
        _specification(check_steps=["Run bash to inspect the package."])


def test_check_specification_is_a_closed_object() -> None:
    body = valid_specification().model_dump(mode="json")
    body["evaluation_method_description"] = "Extra prose is not admitted."

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CheckSpecification.model_validate(body)


@pytest.mark.parametrize("include_dependency", [False, True])
def test_prepared_material_input_requires_explicit_unavailable_material_custody(
    include_dependency: bool,
) -> None:
    body = valid_specification().model_dump(mode="json")
    body["inputs"] = [
        {
            "input_id": "prepared_images",
            "kind": "prepared_material",
            "purpose": "Offline images prepared outside the submitted package.",
        }
    ]
    body["runtime_dependencies"] = (
        [
            {
                "dependency_id": "prepared_images",
                "kind": "prepared_material",
                "provisioning": "runtime_gap",
                "purpose": "Supply the exact prepared image material.",
                "unavailable_code": "material_unavailable",
            }
        ]
        if include_dependency
        else []
    )
    body["infrastructure_failures"] = [
        {
            "code": "material_unavailable",
            "condition": "Required prepared images are unavailable.",
        }
    ]
    if include_dependency:
        specification = CheckSpecification.model_validate(body)
        assert specification.runtime_dependencies[0].provisioning == "runtime_gap"
    else:
        with pytest.raises(ValidationError, match="context input requires a runtime dependency"):
            CheckSpecification.model_validate(body)


@pytest.mark.parametrize("material_kind", ["task_context", "guide_context", "prepared_material"])
def test_external_material_dependency_requires_its_declared_input(material_kind: str) -> None:
    with pytest.raises(ValidationError, match="material dependency requires a declared input"):
        _specification(
            runtime_dependencies=[
                {
                    "dependency_id": "external_material",
                    "kind": material_kind,
                    "provisioning": "runtime_gap",
                    "purpose": "Provide the external evaluation material.",
                    "unavailable_code": "material_unavailable",
                }
            ],
            infrastructure_failures=[
                {
                    "code": "material_unavailable",
                    "condition": "The external evaluation material is unavailable.",
                }
            ],
        )
