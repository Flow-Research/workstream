"""Garden image keeps intake and immutable task association in project code."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from app.modules.checkers.api.external import ExternalCheckerRegistrySpec
from tests.checkers.external.test_harnessy_proof_checker import FACTS, VALID_PROOF

ROOT = Path(__file__).parents[4] / "external_checkers/garden_proof"


def load(name):
    spec = importlib.util.spec_from_file_location("garden_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker, publisher = load("checker"), load("publish_local")
TASK = "019a5300-0000-7000-8000-000000000001"
OTHER_TASK = "019a5300-0000-7000-8000-000000000002"
MESSAGE = "Explain verified contributions\n\nWorkstream-Task: " + TASK + "\n"
CONFIG = {
    "workstream_forge_facts_version": "v1",
    "forge": "github",
    **checker.PRE_CONFIGURATION,
    "base_branch": "main",
}


def control(message=MESSAGE, task=TASK):
    facts = deepcopy(FACTS)
    facts.update(
        repository=checker.REPOSITORY,
        change_url=checker.ORIGIN + "/" + checker.REPOSITORY + "/pull/12",
        head_commit_message=message,
    )
    run = checker.ORIGIN + "/" + checker.REPOSITORY + "/actions/runs/345"
    facts["required_checks"][0]["run_url"] = run
    proof = {**VALID_PROOF, "pr_url": facts["change_url"], "ci_run_url": run}
    return json.dumps(proof).encode(), {"forge_facts": facts, "task_id": task}


def test_matching_reviewed_task_passes_pre_and_post():
    raw, value = control()
    assert checker.evaluate_intake(raw, checker.PRE_CONFIGURATION) == []
    assert checker.evaluate_post(raw, CONFIG, value) == []
    assert (
        checker.evaluate_post(raw, CONFIG, {**value, "task_id": OTHER_TASK})[0]["code"]
        == "garden.proof.task_mismatch"
    )


@pytest.mark.parametrize(
    "message",
    [
        "No marker",
        "Subject\n\nWorkstream-Task: " + TASK + "\nWorkstream-Task: " + TASK,
        "Workstream-Task appears in prose\n\nWorkstream-Task: " + TASK,
        "workstream-task: " + TASK + "\n\nWorkstream-Task: " + TASK,
        "Subject\n\nWorkstream-Task: " + TASK.upper(),
        "Subject\n\nWorkstream-Task: " + TASK + " trailing",
        "Subject\n\n Workstream-Task: " + TASK,
        "Subject\n\nWorkstream-Task: " + TASK + "\n\nMore prose",
        "Subject\n\nWorkstream-Task: " + TASK + "\nnot a trailer",
        "Subject\n\nWorkstream-Task: " + TASK + "\r\n",
    ],
)
def test_marker_negative_controls_after_valid_pr_integrity(message):
    raw, value = control()
    assert checker.evaluate_post(raw, CONFIG, value) == []
    value["forge_facts"]["head_commit_message"] = message
    findings = checker.evaluate_post(raw, CONFIG, value)
    assert [item["code"] for item in findings] == ["garden.proof.task_trailer"]


def test_other_trailers_are_allowed_and_case_is_exact():
    raw, value = control(
        "Subject\n\nWorkstream-Task: " + TASK + "\nSigned-off-by: Reviewer <reviewer@example.org>\n"
    )
    assert checker.evaluate_post(raw, CONFIG, value) == []
    raw, value = control("Workstream-Task: " + TASK)
    assert checker.evaluate_post(raw, CONFIG, value) == []


def test_failed_ci_still_fails_even_with_correct_task():
    raw, value = control()
    assert checker.evaluate_post(raw, CONFIG, value) == []
    value["forge_facts"]["required_checks"][0]["conclusion"] = "failure"
    assert [f["code"] for f in checker.evaluate_post(raw, CONFIG, value)] == [
        "harnessy.proof.forge.required_check"
    ]


@pytest.mark.parametrize(
    "raw,code", [(None, "missing"), (b"{", "invalid_json"), (b"x" * 65_537, "too_large")],
    ids=["missing", "invalid-json", "oversized"],
)
def test_intake_rejects_unusable_proof_without_facts(raw, code):
    assert [f["code"] for f in checker.evaluate_intake(raw, checker.PRE_CONFIGURATION)] == [
        "harnessy.proof." + code
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("merged", False),
        ("commit_sha", "invalid"),
        ("pr_url", "https://github.com/other/repo/pull/1"),
        ("pr_url", "https://github.com/Flow-Research/garden/pull/1?x=1"),
        ("ci_run_url", "https://github.com/other/repo/actions/runs/1"),
    ],
)
def test_intake_rejects_bad_claim_shape_and_foreign_urls(field, value):
    raw, _ = control()
    assert checker.evaluate_intake(raw, checker.PRE_CONFIGURATION) == []
    proof = json.loads(raw)
    proof[field] = value
    assert checker.evaluate_intake(json.dumps(proof).encode(), checker.PRE_CONFIGURATION)


@pytest.mark.parametrize("phase", ["pre_submit", "post_submit"])
def test_registry_specs_select_distinct_authority(phase):
    spec = ExternalCheckerRegistrySpec.model_validate(
        publisher.registry_spec("sha256:" + "f" * 64, "v1", phase)
    )
    assert spec.phase == phase
    assert spec.capability_id == "garden.work_proof"
    spec.configuration_schema.validate_instance(
        checker.PRE_CONFIGURATION if phase == "pre_submit" else CONFIG
    )
    if phase == "pre_submit":
        assert (
            "workstream_forge_facts_version" not in spec.configuration_schema.document["properties"]
        )


@pytest.mark.parametrize(
    "message", [None, 3, "x" * 65_537, "é" * 32_769, "\ud800"],
    ids=["missing", "non-string", "oversized-ascii", "oversized-utf8", "invalid-surrogate"],
)
def test_malformed_message_facts_fail_closed(message):
    raw, value = control()
    assert checker.evaluate_post(raw, CONFIG, value) == []
    value["forge_facts"]["head_commit_message"] = message
    assert [f["code"] for f in checker.evaluate_post(raw, CONFIG, value)] == [
        "harnessy.proof.forge.facts_invalid"
    ]
