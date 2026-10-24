"""Receipt-bound assessment for the guide's isolated runtime requirement."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from assessment import (
    AssessmentError,
    ValidatedFinding,
    build_prompt,
    validate_assessment,
)
from material import MaterialEvidence, MaterialSnapshot
from rubric import FindingRule, Rubric, RubricError
from trial_plan import MAXIMUM_MODEL_PROMPT_BYTES, SourceEvidence
from trial_transport import CompletedTrial


RUNTIME_REQUIREMENT = "runtime_environment_and_verification_trials"
REVISION_RERUN_REQUIREMENT = "revision_rerun_evidence"
_LOCAL_HANDOFF_PATH = Path(__file__).with_name("execution-rubrics.json")
_SOURCE_HANDOFF_PATH = Path(__file__).parents[2] / "setup-handoff.json"
HANDOFF_PATH = (
    _LOCAL_HANDOFF_PATH if _LOCAL_HANDOFF_PATH.is_file() else _SOURCE_HANDOFF_PATH
)
_CONDITION_FINDINGS = (
    frozenset({"offline_build_or_runtime_failure"}),
    frozenset({"author_only_material_exposed"}),
    frozenset({"author_only_material_exposed"}),
    frozenset({"runtime_isolation_failure"}),
    frozenset({"reference_not_from_starting_state"}),
    frozenset({"reference_trial_failure"}),
    frozenset({"starter_not_substantively_rejected"}),
    frozenset({"incomplete_repair_not_rejected"}),
    frozenset({"verification_accepts_invalid_output"}),
    frozenset({"verification_role_dependent"}),
    frozenset({"behavioral_coverage_incomplete", "execution_contract_failure"}),
)
_REVISION_CONDITION_FINDINGS = (
    frozenset({"revision_rerun_missing"}),
    frozenset({"revision_rerun_missing"}),
    frozenset({"revision_rerun_missing", "revision_rerun_failure"}),
    frozenset({"revision_rerun_missing"}),
)
_RESOURCE_FAILURES = frozenset(
    {
        "deadline_exceeded",
        "cpu_exceeded",
        "memory_exceeded",
        "pid_exceeded",
        "disk_exceeded",
        "output_exceeded",
        "dependency_skipped",
        "export_invalid",
    }
)


class TrialAssessmentError(AssessmentError):
    """Trial rubric, evidence, or assessed output is not trustworthy."""


@dataclass(frozen=True, slots=True)
class RuntimeAssessmentInput:
    rubric: Rubric
    snapshot: MaterialSnapshot
    prompt: str
    required_receipt_handles: tuple[str, ...]
    slot_kinds: tuple[tuple[str, str], ...]


def load_runtime_rubric(path: Path = HANDOFF_PATH) -> tuple[dict[str, str], Rubric]:
    """Load the exact retained source rule without treating it as policy authority."""
    return _load_execution_rubric(RUNTIME_REQUIREMENT, _CONDITION_FINDINGS, path=path)


def load_revision_rerun_rubric(
    path: Path = HANDOFF_PATH,
) -> tuple[dict[str, str], Rubric]:
    """Load the exact conditional revision rerun rule."""
    return _load_execution_rubric(
        REVISION_RERUN_REQUIREMENT,
        _REVISION_CONDITION_FINDINGS,
        path=path,
    )


def _load_execution_rubric(
    requirement_id: str,
    condition_findings: tuple[frozenset[str], ...],
    *,
    path: Path,
) -> tuple[dict[str, str], Rubric]:
    try:
        root = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RubricError("rubric_unavailable") from exc
    if type(root) is not dict or set(root) not in (
        {"source", "requirements"},
        {"source", "requirements", "capability_suggestions"},
    ):
        raise RubricError("rubric_invalid")
    source = root["source"]
    if type(source) is not dict or set(source) != {
        "guide_sha256",
        "compilation_id",
        "result_hash",
    }:
        raise RubricError("rubric_invalid")
    matches = [
        item
        for item in root["requirements"]
        if type(item) is dict and item.get("requirement_id") == requirement_id
    ]
    if len(matches) != 1:
        raise RubricError("rubric_invalid")
    value = matches[0]
    specification = value.get("check_specification")
    if (
        value.get("disposition") != "post_submit_capability_gap"
        or type(specification) is not dict
        or specification.get("evaluation_method") != "isolated_execution"
    ):
        raise RubricError("rubric_invalid")
    try:
        rules = {
            item["code"]: FindingRule(
                code=item["code"],
                level=item["level"],
                condition=item["condition"],
                message=item["message"],
            )
            for item in specification["failure_findings"]
        }
        inputs = tuple(specification["inputs"])
        steps = tuple(specification["check_steps"])
        conditions = tuple(specification["pass_conditions"])
    except (KeyError, TypeError) as exc:
        raise RubricError("rubric_invalid") from exc
    if (
        len(rules) != len(specification["failure_findings"])
        or any(rule.level != "error" for rule in rules.values())
        or not inputs
        or not steps
        or len(conditions) != len(condition_findings)
        or set().union(*condition_findings) != rules.keys()
    ):
        raise RubricError("rubric_invalid")
    return source, Rubric(
        requirement_id=requirement_id,
        statement=value["statement"],
        inputs=inputs,
        check_steps=steps,
        pass_conditions=conditions,
        findings=rules,
        condition_findings=condition_findings,
    )


def prepare_runtime_assessment(
    metadata: dict[str, object],
    material_digest: str,
    sources: tuple[SourceEvidence, ...],
    plan: dict[str, object],
    trial: CompletedTrial,
) -> RuntimeAssessmentInput:
    source, rubric = load_runtime_rubric()
    evidence = [
        MaterialEvidence(
            evidence_id=item.evidence_id,
            path=item.path,
            kind="submitted_source",
            byte_count=len(item.content.encode("utf-8")),
            sha256=item.sha256,
            content_utf8=item.content,
            line_count=item.line_count,
        )
        for item in sources
    ]
    metadata_bytes = _canonical(metadata)
    evidence.append(
        MaterialEvidence(
            evidence_id="task_metadata",
            path="task.toml",
            kind="parsed_task_metadata",
            byte_count=len(metadata_bytes),
            sha256=_bytes_digest(metadata_bytes),
            content_utf8=metadata_bytes.decode("utf-8"),
            line_count=None,
        )
    )
    aggregate = {
        "receipt_digest": trial.receipt_digest,
        "observations": trial.observations,
    }
    aggregate_bytes = _canonical(aggregate)
    evidence.append(
        MaterialEvidence(
            evidence_id="trial_receipt",
            path=None,
            kind="runner_observation_projection",
            byte_count=len(aggregate_bytes),
            sha256=_bytes_digest(aggregate_bytes),
            content_utf8=aggregate_bytes.decode("utf-8"),
            line_count=None,
        )
    )
    for step in trial.observations["steps"]:
        step_bytes = _canonical(step)
        evidence.append(
            MaterialEvidence(
                evidence_id=f"trial_step.{step['slot_id']}",
                path=None,
                kind="runner_step_projection",
                byte_count=len(step_bytes),
                sha256=_bytes_digest(step_bytes),
                content_utf8=step_bytes.decode("utf-8"),
                line_count=None,
            )
        )
    snapshot_value = {
        "material_digest": material_digest,
        "receipt_digest": trial.receipt_digest,
        "evidence": [item.prompt_value() for item in evidence],
    }
    snapshot = MaterialSnapshot(
        digest=_bytes_digest(_canonical(snapshot_value)), evidence=tuple(evidence)
    )
    prompt = json.loads(build_prompt(source, rubric, snapshot))
    prompt["security"].extend(
        (
            "Runner projections in this prompt are for citation only, not receipt authority.",
            "Use only the trusted service-injected canonical receipt facts for trial claims.",
            "A digest or exit status alone cannot establish a semantic behavior not present in those facts.",
        )
    )
    prompt["authenticated_trial_binding"] = {
        "receipt_digest": trial.receipt_digest,
        "observation_digest": trial.observations["observation_digest"],
        "required_receipt_count": 1,
    }
    encoded_prompt = _canonical(prompt)
    if len(encoded_prompt) > MAXIMUM_MODEL_PROMPT_BYTES:
        raise TrialAssessmentError("capacity_exceeded")
    return RuntimeAssessmentInput(
        rubric=rubric,
        snapshot=snapshot,
        prompt=encoded_prompt.decode("utf-8"),
        required_receipt_handles=(trial.receipt_handle,),
        slot_kinds=tuple(
            (step["slot_id"], step["slot_kind"]) for step in plan["steps"]
        ),
    )


def validate_runtime_assessment(
    raw: str,
    prepared: RuntimeAssessmentInput,
    trial: CompletedTrial,
) -> tuple[ValidatedFinding, ...]:
    """Reject model passes contradicted by closed runner outcomes."""
    try:
        value = json.loads(raw)
        conditions = value["conditions"]
        statuses = {
            item["condition_number"]: item["status"]
            for item in conditions
            if type(item) is dict
            and type(item.get("condition_number")) is int
            and type(item.get("status")) is str
        }
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise TrialAssessmentError("invalid_output") from exc
    contradicted = _contradicted_conditions(
        trial.observations, dict(prepared.slot_kinds)
    )
    if any(statuses.get(number) != "not_satisfied" for number in contradicted):
        raise TrialAssessmentError("invalid_output")
    return validate_assessment(raw, prepared.rubric, prepared.snapshot)


def _contradicted_conditions(
    observations: dict[str, object], slot_kinds: dict[str, str]
) -> frozenset[int]:
    steps = {item["slot_id"]: item for item in observations["steps"]}
    by_kind: dict[str, list[dict[str, object]]] = {}
    for identifier, kind in slot_kinds.items():
        by_kind.setdefault(kind, []).append(steps[identifier])
    contradicted = set()
    if observations["build"]["outcome"] != "succeeded":
        contradicted.add(1)
    if any(
        steps[f"reference_{action}_{number}"]["outcome"] != "succeeded"
        for number in range(1, 4)
        for action in ("apply", "verify")
    ):
        contradicted.add(6)
    if steps["starter_verification"]["outcome"] != "exit_nonzero":
        contradicted.add(7)
    if not _kind_rejected(steps, by_kind, "incomplete_repair"):
        contradicted.add(8)
    if any(
        not _kind_rejected(steps, by_kind, kind, require_unchanged=True)
        for kind in ("missing_output_mutation", "fabricated_output_mutation")
    ):
        contradicted.add(9)
    if any(
        item["outcome"] in _RESOURCE_FAILURES
        for item in observations["steps"]
        if slot_kinds[item["slot_id"]]
        in {"documented_command", "controlled_interruption", "restart"}
    ):
        contradicted.add(11)
    return frozenset(contradicted)


def _mutation_rejected(
    steps: dict[str, dict[str, object]],
    identifier: str,
    *,
    require_unchanged: bool = False,
) -> bool:
    operation = steps.get(identifier)
    verification = steps.get(f"{identifier}_verification")
    if (
        operation is None
        or verification is None
        or operation["outcome"] != "succeeded"
        or verification["outcome"] != "exit_nonzero"
    ):
        return False
    return not require_unchanged or (
        verification["workspace_before_sha256"]
        == verification["workspace_after_sha256"]
    )


def _kind_rejected(
    steps: dict[str, dict[str, object]],
    by_kind: dict[str, list[dict[str, object]]],
    kind: str,
    *,
    require_unchanged: bool = False,
) -> bool:
    operations = by_kind.get(kind, [])
    if len(operations) != 1:
        return False
    return _mutation_rejected(
        steps,
        operations[0]["slot_id"],
        require_unchanged=require_unchanged,
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


__all__ = (
    "RuntimeAssessmentInput",
    "TrialAssessmentError",
    "load_revision_rerun_rubric",
    "load_runtime_rubric",
    "prepare_runtime_assessment",
    "validate_runtime_assessment",
)
