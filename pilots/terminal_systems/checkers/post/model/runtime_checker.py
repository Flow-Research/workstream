"""Terminal Systems trial-planning, execution, and assessed-result orchestration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from assessment import AssessmentError, ValidatedFinding
from material import MaterialEvidence
from model_transport import (
    CompletedModelCall,
    ModelCallUnavailable,
    ModelSessionError,
)
from result import completed_result, infrastructure_result
from rubric import RubricError
from trial_assessment import (
    TrialAssessmentError,
    load_runtime_rubric,
    prepare_runtime_assessment,
    validate_runtime_assessment,
)
from trial_plan import (
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


RUNTIME_REQUIREMENT = "runtime_environment_and_verification_trials"
DEFAULT_TRIAL_LIMITS = TrialPlanLimits(
    maximum_entries=20_000,
    pids=64,
    maximum_steps=35,
)


class ModelSessionPort(Protocol):
    def call(
        self, prompt: str, *, required_receipt_handles: tuple[str, ...] = ()
    ) -> CompletedModelCall: ...


def execute_runtime_check(
    request: dict[str, object],
    material_root: Path,
    model_session: ModelSessionPort,
    trial_execute: Callable[[dict[str, object]], CompletedTrial],
    *,
    limits: TrialPlanLimits = DEFAULT_TRIAL_LIMITS,
) -> dict[str, object]:
    """Run the two-call plan→trial→assessment flow without fabricating evidence."""
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
            return _coverage_incomplete_result(request, sources, proposal.coverage_gaps)
        if planning.session_exhausted:
            return infrastructure_result(request, "implementation_unavailable")
        plan = build_runtime_trial_plan(metadata, proposal, limits)
        if plan is None:
            raise TrialPlanError("invalid_output")
        trial = trial_execute(plan)
        prepared = prepare_runtime_assessment(
            metadata,
            material_digest,
            sources,
            plan,
            trial,
        )
        assessed = model_session.call(
            prepared.prompt,
            required_receipt_handles=prepared.required_receipt_handles,
        )
        findings = validate_runtime_assessment(assessed.output, prepared, trial)
        return completed_result(request, RUNTIME_REQUIREMENT, findings)
    except TrialPlanError as exc:
        return infrastructure_result(request, _plan_failure(str(exc)))
    except TrialUnavailable as exc:
        return infrastructure_result(request, _trial_failure(exc.failure_code))
    except TrialTransportError:
        return infrastructure_result(request, "implementation_unavailable")
    except ModelCallUnavailable:
        return infrastructure_result(request, "implementation_unavailable")
    except ModelSessionError:
        return infrastructure_result(request, "implementation_unavailable")
    except TrialAssessmentError as exc:
        return infrastructure_result(
            request,
            "capacity_exceeded"
            if str(exc) == "capacity_exceeded"
            else "invalid_output",
        )
    except AssessmentError:
        return infrastructure_result(request, "invalid_output")
    except RubricError:
        return infrastructure_result(request, "implementation_unavailable")
    except (KeyError, TypeError, ValueError):
        return infrastructure_result(request, "invalid_output")
    except (MemoryError, RecursionError):
        return infrastructure_result(request, "capacity_exceeded")


def _validate_request(request: dict[str, object]) -> None:
    try:
        configuration = request["configuration"]
        input_value = request["input"]
        if (
            type(configuration) is not dict
            or type(input_value) is not dict
            or configuration.get("check") != RUNTIME_REQUIREMENT
            or input_value.get("requirement_id") != RUNTIME_REQUIREMENT
        ):
            raise ValueError("invalid_request")
        validate_trial_configuration(configuration)
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid_request") from exc


def _coverage_incomplete_result(
    request: dict[str, object],
    sources: tuple,
    gaps: tuple[dict[str, object], ...],
) -> dict[str, object]:
    _, rubric = load_runtime_rubric()
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
    rule = rubric.findings["behavioral_coverage_incomplete"]
    finding = ValidatedFinding(
        code=rule.code,
        message=rule.message,
        evidence=evidence,
        line=gap["start_line"],
    )
    return completed_result(request, RUNTIME_REQUIREMENT, (finding,))


def _plan_failure(code: str) -> str:
    if code == "capacity_exceeded":
        return "capacity_exceeded"
    if code == "material_unavailable":
        return "material_unavailable"
    return "invalid_output"


def _trial_failure(code: str) -> str:
    if code == "capacity_exceeded":
        return "capacity_exceeded"
    if code == "material_unavailable":
        return "material_unavailable"
    if code == "deadline_exceeded":
        return "deadline_exceeded"
    if code == "invalid_request":
        return "invalid_output"
    return "implementation_unavailable"


__all__ = ("DEFAULT_TRIAL_LIMITS", "execute_runtime_check")
