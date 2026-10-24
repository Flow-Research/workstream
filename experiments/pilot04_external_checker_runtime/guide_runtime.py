"""Explicit recorded inference for the isolated prefork worker, never production."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
from guide_compilation_e2e import E2EProjectGuideRuntime, runtime_factory  # noqa: E402
from app.interfaces.project_agents import (  # noqa: E402
    AtomicGuideRequirement, PreSubmissionBindingProposal, PostSubmissionBindingProposal,
    SubmissionArtifactPolicyProposal, ProjectGuideCompilationResult,
    CheckSpecification,
)
from app.modules.projects.api.task_examples import validate_task_examples  # noqa: E402
from experiments.pilot04_external_checker_runtime.guide_inputs import (  # noqa: E402
    guide_bytes, TASK_EXAMPLES, CORRECTION_REASON,
)


class RecordedGuideRuntime(E2EProjectGuideRuntime):
    """Read real scoped documents and observe exact examples; return recorded rules."""

    async def compile_project_guide(self, context, capabilities):
        expected = validate_task_examples(TASK_EXAMPLES)
        if context.task_examples != expected:
            raise AssertionError("worker did not receive exact normalized task examples")
        if context.correction_feedback is not None:
            if context.correction_feedback.reason != CORRECTION_REASON:
                raise AssertionError("worker did not receive exact manager correction")
        variants = {"sha256:" + hashlib.sha256(guide_bytes(count)).hexdigest(): count
                    for count in (0, 1, 2)}
        if len(context.material.documents) != 1 or context.material.documents[0].sha256 not in variants:
            raise AssertionError("worker did not receive the uploaded original")
        pre_requirements = variants[context.material.documents[0].sha256]
        base = await super().compile_project_guide(context, capabilities)
        refs = base.findings[0].evidence_refs
        requirements, pre, post = [], [], []
        for stage, binding_type, target in (
            ("pre_submit", PreSubmissionBindingProposal, pre),
            ("post_submit", PostSubmissionBindingProposal, post),
        ):
            entries = [d for d in context.checker_capabilities.definitions
                       if d.selectable and d.phase == stage]
            if len(entries) != 1:
                raise AssertionError("recorded guide requires one registered image per stage")
            entry = entries[0]
            count = pre_requirements if stage == "pre_submit" else 1
            for index in range(count):
                key = "project." + stage + (f".{index + 1:02d}" if count == 2 else "")
                requirements.append(AtomicGuideRequirement(
                    requirement_id=key, statement="Apply the registered project image rules.",
                    disposition="supported_" + stage, evidence_refs=refs,
                    classification_rationale="The recorded fixture has a registered image for this stage.",
                    check_specification=_recorded_specification(stage, index=index),
                ))
                target.append(binding_type(
                    requirement_id=key, capability_id=entry.capability_id,
                    capability_version=entry.capability_version, stage=stage,
                ))
        value = base.model_dump(mode="json", exclude={"setup_notes"})
        value.update(
            submission_artifact_policy=SubmissionArtifactPolicyProposal(
                maximum_file_size_bytes=1_000_000, maximum_package_size_bytes=5_000_000,
                required_artifacts=("task.toml",), required_evidence=("results",),
                attestation_terms=("rights_confirmed",),
            ).model_dump(mode="json"),
            requirements=[item.model_dump(mode="json") for item in requirements],
            pre_submit_bindings=[item.model_dump(mode="json") for item in pre],
            post_submit_bindings=[item.model_dump(mode="json") for item in post],
        )
        return ProjectGuideCompilationResult.model_validate(value)



def _recorded_specification(stage, *, index=0):
    """Describe the negative-trial marker, not a general code-quality evaluator."""
    pre = stage == "pre_submit"
    marker = ("project-rejected.txt" if index == 0 else "second-pre-rejected.txt") if pre else "post-rejected.txt"
    code = "probe.project_rule_failed" if pre else "probe.post_rule_failed"
    return CheckSpecification.model_validate({
        "evaluation_method": "static_inspection",
        "execution_mode": "bounded_pre_submit" if pre else "background",
        "maximum_duration_seconds": 1,
        "stage_rationale": (
            "Bounded fixture-file inspection before intake."
            if pre else "Recorded background-delivery trial; not a real project classification."
        ),
        "inputs": [{"input_id": "package", "kind": "package", "purpose": "Verified fixture files."}],
        "check_steps": [f"Check whether {marker} exists at the package root."],
        "pass_conditions": [f"The package does not contain {marker}."],
        "failure_findings": [{"code": code, "level": "error",
                              "condition": f"The file {marker} is present.",
                              "message": "The recorded negative-trial marker is present."}],
        "positive_tests": [f"A fixture without {marker} passes this rule."],
        "negative_tests": [{"name": "negative_marker", "scenario": f"Add {marker} to the fixture.",
                            "expected_verdict": "failed", "expected_finding_codes": [code]}],
        "runtime_dependencies": [],
        "infrastructure_failures": [{"code": "invalid_output",
                                     "condition": "The runner receives malformed checker output."}],
    })


def create_recorded_runtime(configuration):
    """Use the same typed adapter factory at the worker's external runtime seam."""
    return runtime_factory(RecordedGuideRuntime(configuration))(configuration)
