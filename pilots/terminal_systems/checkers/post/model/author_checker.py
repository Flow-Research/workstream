"""Receipt-bound checker for the accuracy of author trial claims."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path

from assessment import (
    AssessmentError,
    ValidatedFinding,
    build_prompt,
    validate_assessment,
)
from checker import DEFAULT_LIMITS
from material import MaterialEvidence, MaterialError, MaterialSnapshot, collect_material
from model_transport import ModelCallUnavailable, ModelSessionError
from result import completed_result, infrastructure_result
from rubric import Rubric, RubricError, load_rubrics
from runtime_checker import DEFAULT_TRIAL_LIMITS, ModelSessionPort
from trial_plan import (
    MAXIMUM_MODEL_PROMPT_BYTES,
    TrialPlanError,
    TrialPlanLimits,
    build_plan_prompt,
    build_runtime_trial_plan,
    collect_plan_sources,
    parse_task_metadata,
    validate_trial_configuration,
    validate_plan_proposal,
)
from trial_transport import CompletedTrial, TrialTransportError, TrialUnavailable


AUTHOR_REQUIREMENT = "author_evidence_accuracy"


def execute_author_accuracy_check(
    request: dict[str, object],
    material_root: Path,
    model_session: ModelSessionPort,
    trial_execute: Callable[[dict[str, object]], CompletedTrial],
    *,
    limits: TrialPlanLimits = DEFAULT_TRIAL_LIMITS,
) -> dict[str, object]:
    """Execute exact cited procedures before assessing author observation claims."""
    try:
        _validate_request(request)
        metadata = parse_task_metadata(material_root)
        material_digest, sources = collect_plan_sources(material_root)
        planning = model_session.call(
            build_plan_prompt(metadata, material_digest, sources),
            required_receipt_handles=(),
        )
        proposal = validate_plan_proposal(planning.output, material_digest, sources)
        if not proposal.coverage_complete:
            return _procedure_unavailable(request, sources, proposal.coverage_gaps)
        if planning.session_exhausted:
            return infrastructure_result(request, "implementation_unavailable")
        plan = build_runtime_trial_plan(metadata, proposal, limits)
        if plan is None:
            raise TrialPlanError("invalid_output")
        trial = trial_execute(plan)
        source, rubrics = load_rubrics()
        rubric = rubrics[AUTHOR_REQUIREMENT]
        prepared = _prepare_assessment(source, rubric, material_root, trial)
        assessed = model_session.call(
            prepared[0], required_receipt_handles=(trial.receipt_handle,)
        )
        findings = validate_assessment(assessed.output, rubric, prepared[1])
        return completed_result(request, AUTHOR_REQUIREMENT, findings)
    except TrialPlanError as exc:
        return infrastructure_result(request, _plan_failure(str(exc)))
    except MaterialError as exc:
        return infrastructure_result(
            request,
            "capacity_exceeded"
            if str(exc) == "capacity_exceeded"
            else "material_unavailable",
        )
    except TrialUnavailable as exc:
        return infrastructure_result(request, _trial_failure(exc.failure_code))
    except (TrialTransportError, ModelCallUnavailable, ModelSessionError, RubricError):
        return infrastructure_result(request, "implementation_unavailable")
    except AssessmentError:
        return infrastructure_result(request, "invalid_output")
    except (KeyError, TypeError, ValueError):
        return infrastructure_result(request, "invalid_output")
    except (MemoryError, RecursionError):
        return infrastructure_result(request, "capacity_exceeded")


def _validate_request(request: dict[str, object]) -> None:
    configuration = request["configuration"]
    input_value = request["input"]
    if (
        type(configuration) is not dict
        or type(input_value) is not dict
        or configuration.get("check") != AUTHOR_REQUIREMENT
        or input_value.get("requirement_id") != AUTHOR_REQUIREMENT
    ):
        raise ValueError("invalid_request")
    validate_trial_configuration(configuration)


def _prepare_assessment(
    source: dict[str, str],
    rubric: Rubric,
    material_root: Path,
    trial: CompletedTrial,
) -> tuple[str, MaterialSnapshot]:
    material_rubric = Rubric(
        requirement_id=rubric.requirement_id,
        statement=rubric.statement,
        inputs=tuple(
            item
            for item in rubric.inputs
            if item.get("kind") in {"relative_file", "relative_directory"}
        ),
        check_steps=rubric.check_steps,
        pass_conditions=rubric.pass_conditions,
        findings=rubric.findings,
        condition_findings=rubric.condition_findings,
    )
    base = collect_material(material_root, material_rubric, DEFAULT_LIMITS)
    receipt_value = {
        "receipt_digest": trial.receipt_digest,
        "observations": trial.observations,
    }
    receipt_bytes = _canonical(receipt_value)
    receipt = MaterialEvidence(
        evidence_id="trial_receipt",
        path=None,
        kind="runner_observation_projection",
        byte_count=len(receipt_bytes),
        sha256=_digest(receipt_bytes),
        content_utf8=receipt_bytes.decode("utf-8"),
        line_count=None,
    )
    evidence = (*base.evidence, receipt)
    snapshot = MaterialSnapshot(
        digest=_digest(_canonical([item.prompt_value() for item in evidence])),
        evidence=evidence,
    )
    prompt = json.loads(build_prompt(source, rubric, snapshot))
    prompt["security"].extend(
        (
            "Runner projections are citation aids, not receipt authority.",
            "Compare claims only with the trusted service-injected canonical receipt facts.",
        )
    )
    prompt["authenticated_trial_binding"] = {
        "receipt_digest": trial.receipt_digest,
        "observation_digest": trial.observations["observation_digest"],
        "required_receipt_count": 1,
    }
    encoded = _canonical(prompt)
    if len(encoded) > MAXIMUM_MODEL_PROMPT_BYTES:
        raise MaterialError("capacity_exceeded")
    return encoded.decode("utf-8"), snapshot


def _procedure_unavailable(
    request: dict[str, object],
    sources: tuple,
    gaps: tuple[dict[str, object], ...],
) -> dict[str, object]:
    _, rubrics = load_rubrics()
    rule = rubrics[AUTHOR_REQUIREMENT].findings["reproduction_procedure_unavailable"]
    gap = gaps[0]
    source = next(item for item in sources if item.evidence_id == gap["evidence_id"])
    evidence = MaterialEvidence(
        evidence_id=source.evidence_id,
        path=source.path,
        kind="submitted_source",
        byte_count=len(source.content.encode("utf-8")),
        sha256=source.sha256,
        content_utf8=source.content,
        line_count=source.line_count,
    )
    finding = ValidatedFinding(
        code=rule.code,
        message=rule.message,
        evidence=evidence,
        line=gap["start_line"],
    )
    return completed_result(request, AUTHOR_REQUIREMENT, (finding,))


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _plan_failure(code: str) -> str:
    if code == "capacity_exceeded":
        return "capacity_exceeded"
    if code == "material_unavailable":
        return "material_unavailable"
    return "invalid_output"


def _trial_failure(code: str) -> str:
    if code in {"capacity_exceeded", "material_unavailable", "deadline_exceeded"}:
        return code
    if code == "invalid_request":
        return "invalid_output"
    return "implementation_unavailable"


__all__ = ("AUTHOR_REQUIREMENT", "execute_author_accuracy_check")
