"""Owner-context-bound revision explanation and rerun checks."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
import stat

from assessment import (
    AssessmentError,
    ValidatedFinding,
    build_prompt,
    validate_assessment,
)
from material import MaterialEvidence, MaterialSnapshot
from model_transport import ModelCallUnavailable, ModelSessionError
from result import completed_result, infrastructure_result
from rubric import RubricError, load_rubrics
from runtime_checker import DEFAULT_TRIAL_LIMITS, ModelSessionPort
from trial_assessment import load_revision_rerun_rubric
from trial_plan import (
    MAXIMUM_MODEL_PROMPT_BYTES,
    TrialPlanError,
    TrialPlanLimits,
    build_revision_rerun_plan,
    parse_task_metadata,
    validate_trial_configuration,
)
from trial_transport import CompletedTrial, TrialTransportError, TrialUnavailable


REVISION_OBJECTIVE_REQUIREMENT = "revision_objective_and_explanation"
REVISION_RERUN_REQUIREMENT = "revision_rerun_evidence"
PREDECESSOR_ROOT = Path("/work/context/predecessor")
MAXIMUM_CONTEXT_FILE_BYTES = 2 * 1024 * 1024


def execute_revision_objective_check(
    request: dict[str, object],
    material_root: Path,
    model_session: ModelSessionPort,
    *,
    predecessor_root: Path = PREDECESSOR_ROOT,
) -> dict[str, object]:
    """Pass initial work conditionally or assess exact prior work and feedback."""
    try:
        context = _context(request, REVISION_OBJECTIVE_REQUIREMENT)
        if context["kind"] == "initial":
            return completed_result(request, REVISION_OBJECTIVE_REQUIREMENT, ())
        source, rubrics = load_rubrics()
        rubric = rubrics[REVISION_OBJECTIVE_REQUIREMENT]
        snapshot = _revision_snapshot(
            material_root,
            predecessor_root,
            context,
        )
        prompt = build_prompt(source, rubric, snapshot)
        if len(prompt.encode("utf-8")) > MAXIMUM_MODEL_PROMPT_BYTES:
            return infrastructure_result(request, "capacity_exceeded")
        assessed = model_session.call(prompt, required_receipt_handles=())
        findings = validate_assessment(assessed.output, rubric, snapshot)
        _validate_revision_finding_locations(findings)
        return completed_result(request, REVISION_OBJECTIVE_REQUIREMENT, findings)
    except MaterialContextError as exc:
        return infrastructure_result(request, str(exc))
    except (ModelCallUnavailable, ModelSessionError, RubricError):
        return infrastructure_result(request, "implementation_unavailable")
    except AssessmentError:
        return infrastructure_result(request, "invalid_output")
    except (KeyError, TypeError, ValueError):
        return infrastructure_result(request, "invalid_output")
    except (MemoryError, RecursionError):
        return infrastructure_result(request, "capacity_exceeded")


def execute_revision_rerun_check(
    request: dict[str, object],
    material_root: Path,
    trial_execute: Callable[[dict[str, object]], CompletedTrial],
    *,
    limits: TrialPlanLimits = DEFAULT_TRIAL_LIMITS,
) -> dict[str, object]:
    """Execute exact fresh reference→verification order for a real revision."""
    try:
        context = _context(request, REVISION_RERUN_REQUIREMENT)
        configuration = request["configuration"]
        if type(configuration) is not dict:
            raise ValueError("invalid_request")
        validate_trial_configuration(configuration, revision=True)
        if context["kind"] == "initial":
            return completed_result(request, REVISION_RERUN_REQUIREMENT, ())
        metadata = parse_task_metadata(material_root)
        plan = build_revision_rerun_plan(metadata, limits)
        trial = trial_execute(plan)
        build = trial.observations["build"]
        steps = trial.observations["steps"]
        passed = (
            build["outcome"] == "succeeded"
            and len(steps) == 2
            and steps[0]["slot_id"] == "revision_reference"
            and steps[0]["outcome"] == "succeeded"
            and steps[1]["slot_id"] == "revision_verification"
            and steps[1]["outcome"] == "succeeded"
        )
        if passed:
            return completed_result(request, REVISION_RERUN_REQUIREMENT, ())
        _, rubric = load_revision_rerun_rubric()
        rule = rubric.findings["revision_rerun_failure"]
        metadata_bytes = _read_file(material_root / "task.toml")
        evidence = MaterialEvidence(
            evidence_id="task_metadata",
            path="task.toml",
            kind="task_metadata",
            byte_count=len(metadata_bytes),
            sha256=_digest(metadata_bytes),
            content_utf8=metadata_bytes.decode("utf-8"),
            line_count=len(metadata_bytes.decode("utf-8").splitlines()),
        )
        finding = ValidatedFinding(rule.code, rule.message, evidence, None)
        return completed_result(request, REVISION_RERUN_REQUIREMENT, (finding,))
    except TrialPlanError as exc:
        code = str(exc)
        return infrastructure_result(
            request,
            code
            if code in {"capacity_exceeded", "material_unavailable"}
            else "invalid_output",
        )
    except TrialUnavailable as exc:
        return infrastructure_result(request, _trial_failure(exc.failure_code))
    except TrialTransportError:
        return infrastructure_result(request, "implementation_unavailable")
    except (RubricError, OSError):
        return infrastructure_result(request, "material_unavailable")
    except (KeyError, TypeError, ValueError):
        return infrastructure_result(request, "invalid_output")
    except (MemoryError, RecursionError):
        return infrastructure_result(request, "capacity_exceeded")


class MaterialContextError(RuntimeError):
    """Authenticated revision context material cannot be represented safely."""


def _context(request: dict[str, object], requirement_id: str) -> dict[str, object]:
    configuration = request["configuration"]
    input_value = request["input"]
    context = input_value["evaluation_context"]
    if (
        type(configuration) is not dict
        or configuration.get("check") != requirement_id
        or type(input_value) is not dict
        or input_value.get("requirement_id") != requirement_id
        or type(context) is not dict
        or context.get("schema_version")
        != "workstream.post_submit_evaluation_context.v1"
        or context.get("kind") not in {"initial", "checker_remediation"}
    ):
        raise ValueError("invalid_request")
    if context["kind"] == "initial" and any(
        context.get(name) is not None for name in ("source", "predecessor", "feedback")
    ):
        raise ValueError("invalid_request")
    if context["kind"] == "checker_remediation" and any(
        type(context.get(name)) is not dict
        for name in ("source", "predecessor", "feedback")
    ):
        raise ValueError("invalid_request")
    return context


def _revision_snapshot(
    current_root: Path,
    predecessor_root: Path,
    context: dict[str, object],
) -> MaterialSnapshot:
    selected = (
        ("current_instruction", current_root / "instruction.md", "instruction.md"),
        ("current_author_notes", current_root / "AUTHOR_NOTES.md", "AUTHOR_NOTES.md"),
        ("prior_instruction", predecessor_root / "instruction.md", None),
        ("prior_author_notes", predecessor_root / "AUTHOR_NOTES.md", None),
    )
    evidence = []
    for evidence_id, path, result_path in selected:
        raw = _read_file(path)
        try:
            content = raw.decode("utf-8")
        except UnicodeError as exc:
            raise MaterialContextError("material_unavailable") from exc
        evidence.append(
            MaterialEvidence(
                evidence_id=evidence_id,
                path=result_path,
                kind="current_material" if result_path else "predecessor_material",
                byte_count=len(raw),
                sha256=_digest(raw),
                content_utf8=content,
                line_count=len(content.splitlines()),
            )
        )
    context_bytes = _canonical(
        {
            "source": context["source"],
            "predecessor": context["predecessor"],
            "feedback": context["feedback"],
        }
    )
    evidence.append(
        MaterialEvidence(
            evidence_id="revision_context",
            path=None,
            kind="owner_revision_context",
            byte_count=len(context_bytes),
            sha256=_digest(context_bytes),
            content_utf8=context_bytes.decode("utf-8"),
            line_count=None,
        )
    )
    snapshot_value = [item.prompt_value() for item in evidence]
    return MaterialSnapshot(
        digest=_digest(_canonical(snapshot_value)), evidence=tuple(evidence)
    )


def _read_file(path: Path) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise MaterialContextError("material_unavailable")
            value = handle.read(MAXIMUM_CONTEXT_FILE_BYTES + 1)
    except MaterialContextError:
        raise
    except OSError as exc:
        raise MaterialContextError("material_unavailable") from exc
    if len(value) > MAXIMUM_CONTEXT_FILE_BYTES:
        raise MaterialContextError("capacity_exceeded")
    return value


def _validate_revision_finding_locations(
    findings: tuple[ValidatedFinding, ...],
) -> None:
    expected = {
        "revision_change_unexplained": "AUTHOR_NOTES.md",
        "revision_feedback_unaddressed": "AUTHOR_NOTES.md",
        "revision_objective_not_preserved": "instruction.md",
    }
    if any(item.evidence.path != expected[item.code] for item in findings):
        raise AssessmentError("invalid_output")


def _trial_failure(code: str) -> str:
    if code in {"capacity_exceeded", "material_unavailable", "deadline_exceeded"}:
        return code
    if code == "invalid_request":
        return "invalid_output"
    return "implementation_unavailable"


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


__all__ = (
    "REVISION_OBJECTIVE_REQUIREMENT",
    "REVISION_RERUN_REQUIREMENT",
    "execute_revision_objective_check",
    "execute_revision_rerun_check",
)
