"""Executable core for source-bound Terminal Systems model checks."""

from __future__ import annotations

from collections.abc import Callable

from assessment import AssessmentError, build_prompt, validate_assessment
from material import MaterialError, MaterialLimits, collect_material
from result import completed_result, infrastructure_result
from rubric import BLOCKED_CHECKS, SUPPORTED_CHECKS, RubricError, load_rubrics


DEFAULT_LIMITS = MaterialLimits(
    maximum_entries=20_000,
    maximum_file_bytes=2 * 1024 * 1024,
    maximum_total_bytes=32 * 1024 * 1024,
)


class ModelCallUnavailable(RuntimeError):
    """The trusted model session could not produce an assessed response."""


def _selected_check(request: dict) -> str:
    try:
        configuration = request["configuration"]
        input_value = request["input"]
        check = configuration["check"]
        requirement = input_value["requirement_id"]
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid_request") from exc
    if (
        type(configuration) is not dict
        or type(input_value) is not dict
        or type(check) is not str
        or check != requirement
    ):
        raise ValueError("invalid_request")
    return check


def execute(
    request: dict,
    material_root,
    model_assess: Callable[[str], str],
    *,
    limits: MaterialLimits = DEFAULT_LIMITS,
) -> dict:
    """Assess one exact requirement; no exception becomes a passing verdict."""
    try:
        check = _selected_check(request)
        if check in BLOCKED_CHECKS:
            return infrastructure_result(request, "implementation_unavailable")
        if check not in SUPPORTED_CHECKS:
            return infrastructure_result(request, "invalid_output")
        source, rubrics = load_rubrics()
        rubric = rubrics[check]
        snapshot = collect_material(material_root, rubric, limits)
        prompt = build_prompt(source, rubric, snapshot)
        raw = model_assess(prompt)
        if type(raw) is not str or not raw:
            raise ModelCallUnavailable("model_call_unavailable")
        findings = validate_assessment(raw, rubric, snapshot)
        return completed_result(request, check, findings)
    except MaterialError as exc:
        code = str(exc)
        return infrastructure_result(
            request,
            code
            if code in {"material_unavailable", "capacity_exceeded"}
            else "material_unavailable",
        )
    except AssessmentError as exc:
        return infrastructure_result(
            request,
            "material_unavailable"
            if str(exc) == "material_unavailable"
            else "invalid_output",
        )
    except (ModelCallUnavailable, RubricError):
        return infrastructure_result(request, "implementation_unavailable")
    except (KeyError, TypeError, ValueError):
        return infrastructure_result(request, "invalid_output")


__all__ = ("DEFAULT_LIMITS", "ModelCallUnavailable", "execute")
