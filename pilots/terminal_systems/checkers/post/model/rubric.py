"""Closed, source-linked Terminal Systems model rubrics."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


RUBRIC_PATH = Path(__file__).with_name("rubrics.json")
SUPPORTED_CHECKS = frozenset(
    {
        "solver_brief_and_extension_disclosure",
        "materials_reproducibility_and_notes",
        "verification_independence",
        "difficulty_claim_evidence",
    }
)
AGENT_CHECKS = frozenset(
    {"author_evidence_accuracy", "revision_objective_and_explanation"}
)
BLOCKED_CHECKS = {}

# Each model failure code is valid only for the numbered pass conditions it can
# disprove. This is deliberately data, rather than a prompt-only convention.
CONDITION_FINDINGS = {
    "solver_brief_and_extension_disclosure": (
        frozenset({"brief_incomplete"}),
        frozenset({"brief_hidden_constraint"}),
        frozenset({"visible_example_undisclosed"}),
        frozenset({"brief_hidden_constraint"}),
        frozenset(
            {
                "extension_explanation_missing",
                "extension_adds_undocumented_grading",
            }
        ),
    ),
    "materials_reproducibility_and_notes": (
        frozenset(
            {
                "notes_rationale_missing",
                "notes_reference_decisions_missing",
                "notes_requirement_map_missing",
                "notes_reproduction_missing",
                "notes_trial_outcomes_missing",
                "notes_resource_use_missing",
                "notes_limitations_missing",
            }
        ),
        frozenset(
            {
                "notes_incomplete_repair_method_missing",
                "notes_incomplete_repair_rejection_explanation_missing",
            }
        ),
        frozenset({"materials_provenance_incomplete"}),
        frozenset({"prohibited_material_observed"}),
        frozenset({"additional_directory_unexplained"}),
        frozenset({"author_only_material_relabelled"}),
        frozenset(
            {"dependency_inventory_incomplete", "unpinned_reproducibility_input"}
        ),
        frozenset({"reproducibility_condition_incomplete"}),
    ),
    "verification_independence": (
        frozenset({"expected_result_derivation_not_independent"}),
        frozenset({"expected_result_derivation_not_independent"}),
        frozenset({"permitted_implementation_rejected"}),
        frozenset({"undocumented_verification_constraint"}),
        frozenset({"assertion_weakened_for_reference"}),
        frozenset({"verification_coverage_unexplained"}),
    ),
    "author_evidence_accuracy": (
        frozenset({"notes_observation_misrepresented"}),
        frozenset(
            {
                "reproduction_procedure_discrepant",
                "reproduction_procedure_unavailable",
            }
        ),
        frozenset({"trial_outcome_discrepant"}),
        frozenset({"resource_measurement_discrepant"}),
        frozenset({"notes_observation_misrepresented"}),
    ),
    "revision_objective_and_explanation": (
        frozenset({"revision_change_unexplained"}),
        frozenset({"revision_feedback_unaddressed"}),
        frozenset({"revision_objective_not_preserved"}),
    ),
    "difficulty_claim_evidence": (
        frozenset({"difficulty_claim_unsupported", "difficulty_evidence_inconsistent"}),
    ),
}


class RubricError(ValueError):
    """A bundled rubric violates the closed projection contract."""


@dataclass(frozen=True, slots=True)
class FindingRule:
    code: str
    level: str
    condition: str
    message: str


@dataclass(frozen=True, slots=True)
class Rubric:
    requirement_id: str
    statement: str
    inputs: tuple[dict, ...]
    check_steps: tuple[str, ...]
    pass_conditions: tuple[str, ...]
    findings: dict[str, FindingRule]
    condition_findings: tuple[frozenset[str], ...]


def load_rubrics(path: Path = RUBRIC_PATH) -> tuple[dict[str, str], dict[str, Rubric]]:
    """Load the exact retained-handoff projection used inside the image."""
    try:
        root = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RubricError("rubric_unavailable") from exc
    if type(root) is not dict or set(root) != {"source", "requirements"}:
        raise RubricError("rubric_invalid")
    source = root["source"]
    if type(source) is not dict or set(source) != {
        "guide_sha256",
        "compilation_id",
        "result_hash",
    }:
        raise RubricError("rubric_invalid")
    requirements = root["requirements"]
    if type(requirements) is not list:
        raise RubricError("rubric_invalid")
    loaded: dict[str, Rubric] = {}
    for value in requirements:
        if type(value) is not dict or set(value) != {
            "requirement_id",
            "statement",
            "evidence_refs",
            "check_specification",
        }:
            raise RubricError("rubric_invalid")
        requirement_id = value["requirement_id"]
        specification = value["check_specification"]
        if (
            type(requirement_id) is not str
            or not requirement_id
            or requirement_id in loaded
            or type(value["statement"]) is not str
            or type(specification) is not dict
            or set(specification)
            != {"inputs", "check_steps", "pass_conditions", "failure_findings"}
        ):
            raise RubricError("rubric_invalid")
        rules: dict[str, FindingRule] = {}
        for item in specification["failure_findings"]:
            if type(item) is not dict or set(item) != {
                "code",
                "level",
                "condition",
                "message",
            }:
                raise RubricError("rubric_invalid")
            rule = FindingRule(**item)
            if rule.code in rules or rule.level != "error":
                raise RubricError("rubric_invalid")
            rules[rule.code] = rule
        inputs = specification["inputs"]
        steps = specification["check_steps"]
        conditions = specification["pass_conditions"]
        if (
            type(inputs) is not list
            or not inputs
            or type(steps) is not list
            or not steps
            or type(conditions) is not list
            or not conditions
            or any(type(item) is not dict for item in inputs)
            or any(type(item) is not str or not item for item in (*steps, *conditions))
            or not rules
        ):
            raise RubricError("rubric_invalid")
        loaded[requirement_id] = Rubric(
            requirement_id=requirement_id,
            statement=value["statement"],
            inputs=tuple(inputs),
            check_steps=tuple(steps),
            pass_conditions=tuple(conditions),
            findings=rules,
            condition_findings=CONDITION_FINDINGS.get(requirement_id, ()),
        )
        condition_findings = loaded[requirement_id].condition_findings
        if (
            len(condition_findings) != len(conditions)
            or any(
                not codes or not codes <= rules.keys() for codes in condition_findings
            )
            or set().union(*condition_findings) != rules.keys()
        ):
            raise RubricError("rubric_invalid")
    if set(loaded) != SUPPORTED_CHECKS | AGENT_CHECKS | set(BLOCKED_CHECKS):
        raise RubricError("rubric_invalid")
    return source, loaded


__all__ = (
    "BLOCKED_CHECKS",
    "AGENT_CHECKS",
    "FindingRule",
    "Rubric",
    "RubricError",
    "SUPPORTED_CHECKS",
    "load_rubrics",
)
