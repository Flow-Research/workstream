"""Offline Garden claim intake and reviewed immutable task association.

The existing Harnessy evaluator owns PR/CI/review integrity comparisons. Only
this project image interprets the Workstream-Task commit trailer.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys

# The image contains precisely this source file; local tests use the same owner.
_SHARED = Path(__file__).parents[1] / "harnessy_proof/checker.py"
_spec = importlib.util.spec_from_file_location("harnessy_proof", _SHARED)
assert _spec is not None and _spec.loader is not None
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)

TASK_MARKER = "Workstream-Task"
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_TASK_LINE = re.compile(r"Workstream-Task: (" + _UUID + r")")
_TRAILER = re.compile(r"[A-Za-z0-9-]+: [^\r\n]+")
REPOSITORY = "Flow-Research/garden"
ORIGIN = "https://github.com"
PRE_CONFIGURATION = {"repository": REPOSITORY, "forge_origin": ORIGIN}


def finding(code: str, message: str) -> dict:
    return {
        "check_id": "garden.proof",
        "code": "garden.proof." + code,
        "level": "error",
        "message": message,
        "path": "proof.json",
        "line": None,
    }


def task_findings(input_value: object) -> list[dict]:
    if not isinstance(input_value, dict):
        return [
            finding("task_identity", "Trusted Workstream task identity is missing.")
        ]
    task = input_value.get("task_id")
    if not isinstance(task, str) or re.fullmatch(_UUID, task) is None:
        return [
            finding(
                "task_identity",
                "Trusted Workstream task identity must be a canonical UUID.",
            )
        ]
    facts = input_value.get("forge_facts")
    # The shared evaluator reports malformed/missing facts; never interpret them.
    if not shared.valid_facts(facts):
        return []
    message = facts["head_commit_message"]
    if len(re.findall(TASK_MARKER, message, flags=re.IGNORECASE)) != 1:
        return [
            finding(
                "task_trailer",
                "The reviewed head commit must contain exactly one Workstream-Task trailer.",
            )
        ]
    block = message.rstrip("\n").split("\n\n")[-1].split("\n")
    matches = [_TASK_LINE.fullmatch(line) for line in block]
    markers = [match.group(1) for match in matches if match is not None]
    if len(markers) != 1 or not all(_TRAILER.fullmatch(line) for line in block):
        return [
            finding(
                "task_trailer",
                "Put Workstream-Task: <canonical lowercase task UUID> in the final trailer block before checks and review.",
            )
        ]
    if markers[0] != task:
        return [
            finding(
                "task_mismatch",
                "The reviewed head commit names another Workstream task.",
            )
        ]
    return []


def evaluate_intake(raw: bytes | None, configuration: object) -> list[dict]:
    proof, findings = shared.parse_proof(raw)
    if proof is None:
        return findings
    findings += shared.claim_findings(proof)
    if configuration != PRE_CONFIGURATION:
        findings.append(
            finding(
                "configuration",
                "Garden intake must select its exact GitHub origin and repository.",
            )
        )
    for field, path in (("pr_url", "pull"), ("ci_run_url", "actions/runs")):
        pattern = (
            re.escape(ORIGIN + "/" + REPOSITORY + "/" + path + "/") + r"[1-9][0-9]*"
        )
        value = proof.get(field)
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            findings.append(
                finding(field, f"{field} must be a canonical {REPOSITORY} GitHub URL.")
            )
    return findings


def evaluate_post(
    raw: bytes | None, configuration: object, input_value: object
) -> list[dict]:
    findings = shared.evaluate_proof(
        raw, configuration=configuration, input_value=input_value
    )
    if not isinstance(configuration, dict) or any(
        configuration.get(key) != value for key, value in PRE_CONFIGURATION.items()
    ):
        findings.append(
            finding(
                "configuration",
                "Garden evaluation must select its exact GitHub origin and repository.",
            )
        )
    return findings + task_findings(input_value)


def main() -> int:
    request = json.load(sys.stdin)
    raw = shared.read_proof(Path("/work/input"))
    phase = request["identity"]["phase"]
    input_value = request.get("input")
    if (
        phase == "post_submit"
        and isinstance(input_value, dict)
        and input_value.get("workstream_forge_facts_stage") == "locate"
    ):
        result = shared.build_locator(request, raw)
    else:
        findings = (
            evaluate_intake(raw, request.get("configuration"))
            if phase == "pre_submit"
            else evaluate_post(raw, request.get("configuration"), input_value)
        )
        result = shared.build_result(request, findings)
    sys.stdout.write(shared._canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
