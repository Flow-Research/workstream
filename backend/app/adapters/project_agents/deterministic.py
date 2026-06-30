"""Deterministic project-agent runtime for local development and tests."""

from __future__ import annotations

import re
from typing import Any

from app.interfaces.project_agents import (
    AgentFinding,
    GuideSourceMaterial,
    GuideSufficiencyAgentResult,
    SubmissionArtifactPolicyDerivationResult,
)

DETERMINISTIC_AGENT_VERSION = "deterministic-v0.1"
PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"reveal\s+(secrets|credentials|tokens)", re.IGNORECASE),
)


class DeterministicProjectGuideAgentRuntime:
    """Local project-agent runtime that never performs network or model calls."""

    async def analyze_guide_sufficiency(
        self,
        material: GuideSourceMaterial,
    ) -> GuideSufficiencyAgentResult:
        """Assess guide material with deterministic local rules."""
        text = _flatten_material_text(material.guide_material)
        findings: list[AgentFinding] = []
        if len(text.strip()) < 80:
            findings.append(
                AgentFinding(
                    severity="blocking_gap",
                    code="project_owner_clarification_required",
                    message="Project guide material is too thin to derive an artifact intake policy.",
                    location="project_guide",
                )
            )
            return GuideSufficiencyAgentResult(
                status="blocked",
                findings=findings,
                summary="Guide material needs clarification before setup can continue.",
                agent_version=DETERMINISTIC_AGENT_VERSION,
            )

        for pattern in PROMPT_INJECTION_PATTERNS:
            if pattern.search(text):
                findings.append(
                    AgentFinding(
                        severity="warning",
                        code="untrusted_instruction_detected",
                        message=(
                            "Guide material contains instruction-like text that is treated as "
                            "source content only."
                        ),
                        location="project_guide",
                    )
                )
                break

        return GuideSufficiencyAgentResult(
            status="passed_with_warnings" if findings else "passed",
            findings=findings,
            summary="Guide material is sufficient for deterministic policy derivation.",
            agent_version=DETERMINISTIC_AGENT_VERSION,
        )

    async def derive_submission_artifact_policy(
        self,
        material: GuideSourceMaterial,
        sufficiency_report: GuideSufficiencyAgentResult,
    ) -> SubmissionArtifactPolicyDerivationResult:
        """Derive a conservative v0.1 artifact intake policy."""
        artifact_key = _first_safe_token(
            material.guide_material.get("required_submission_fields"),
            fallback="primary_output",
        )
        artifact_path = f"outputs/{artifact_key}.md"
        policy_body: dict[str, Any] = {
            "required_artifacts": [
                {
                    "key": artifact_key,
                    "path": artifact_path,
                    "hash_required": True,
                    "required": True,
                    "description": "Primary worker output required by the project guide.",
                }
            ],
            "required_evidence": [
                {
                    "key": "work_evidence",
                    "label": "Work evidence",
                    "hash_required": True,
                    "required": True,
                    "description": "Evidence supporting the submitted work.",
                }
            ],
            "forbidden_artifacts": [],
            "attestation_terms": ["project_specific_originality"],
            "manifest_required": True,
            "artifact_hash_required": True,
            "artifact_hash_algorithm": "sha256",
            "allowed_storage_schemes": ["local", "s3", "r2"],
            "maximum_file_size_bytes": None,
            "maximum_package_size_bytes": None,
            "packaging": {"package_required": False},
        }
        return SubmissionArtifactPolicyDerivationResult(
            policy_version=f"agent-{material.source_snapshot_hash.removeprefix('sha256:')[:12]}",
            policy_body=policy_body,
            change_summary=(
                "Derived from the immutable project guide source snapshot after "
                f"{sufficiency_report.status} sufficiency review."
            ),
            agent_version=DETERMINISTIC_AGENT_VERSION,
        )


def _flatten_material_text(value: Any) -> str:
    """Flatten nested material into text for deterministic inspection."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(_flatten_material_text(value[key]) for key in sorted(value))
    if isinstance(value, list | tuple | set):
        return "\n".join(_flatten_material_text(item) for item in value)
    return str(value)


def _first_safe_token(value: Any, *, fallback: str) -> str:
    """Return the first safe artifact token from guide material."""
    if not isinstance(value, list):
        return fallback
    for item in value:
        token = re.sub(r"[^a-z0-9_]+", "_", str(item).strip().lower()).strip("_")
        if re.fullmatch(r"[a-z][a-z0-9_]{1,63}", token):
            return token
    return fallback
