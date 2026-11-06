"""Garden image keeps intake and immutable task association in project code."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from app.modules.checkers.api.external import ExternalCheckerRegistrySpec
from tests.checkers.external.test_harnessy_proof_checker import FACTS

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
        state="open",
        merged=False,
        landed_commit_sha=None,
    )
    run = checker.ORIGIN + "/" + checker.REPOSITORY + "/actions/runs/345"
    facts["required_checks"][0]["run_url"] = run
    proof = {
        "schema": checker.PROOF_SCHEMA,
        "pr_url": facts["change_url"],
        "commit_sha": facts["head_sha"],
        "ci_run_url": run,
        "ci_conclusion": "success",
    }
    return json.dumps(proof).encode(), {"forge_facts": facts, "task_id": task}


def test_matching_open_pr_head_passes_pre_and_post():
    raw, value = control()
    assert checker.evaluate_intake(raw, checker.PRE_CONFIGURATION) == []
    assert checker.evaluate_post(raw, CONFIG, value) == []
    assert (
        checker.evaluate_post(raw, CONFIG, {**value, "task_id": OTHER_TASK})[0]["code"]
        == "garden.proof.task_mismatch"
    )


def test_merged_or_closed_pr_head_still_passes_with_current_evidence():
    raw, value = control()
    facts = value["forge_facts"]
    facts.update(state="closed", merged=True, landed_commit_sha="d" * 40)
    assert checker.evaluate_post(raw, CONFIG, value) == []
    facts.update(merged=False, landed_commit_sha=None)
    assert checker.evaluate_post(raw, CONFIG, value) == []


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"merged": True}, ["garden.proof.fields"]),
        ({"ci_conclusion": None}, ["garden.proof.ci_conclusion"]),
        ({"schema": "harnessy.work.proof.v1"}, ["garden.proof.schema"]),
    ],
)
def test_garden_proof_claims_reject_merge_field_and_wrong_schema(change, expected):
    raw, value = control()
    proof = {**json.loads(raw), **change}
    codes = [item["code"] for item in checker.evaluate_intake(json.dumps(proof).encode(), checker.PRE_CONFIGURATION)]
    assert codes == expected
    assert codes == [item["code"] for item in checker.evaluate_post(json.dumps(proof).encode(), CONFIG, value)]


def test_garden_proof_requires_each_exact_field():
    raw, _ = control()
    proof = json.loads(raw)
    for field in checker.PROOF_KEYS:
        incomplete = {key: value for key, value in proof.items() if key != field}
        codes = [
            item["code"]
            for item in checker.evaluate_intake(
                json.dumps(incomplete).encode(), checker.PRE_CONFIGURATION
            )
        ]
        assert "garden.proof.fields" in codes, field


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
        ("merged", True),
        ("schema", "harnessy.work.proof.v1"),
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
        publisher.registry_spec("sha256:" + "f" * 64, "v3", phase)
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


def test_zero_approvals_is_explicit_and_omission_still_requires_one():
    raw, value = control()
    value["forge_facts"]["reviews"] = []
    assert checker.evaluate_post(raw, {**CONFIG, "required_independent_approvals": 0}, value) == []
    assert [item["code"] for item in checker.evaluate_post(raw, CONFIG, value)] == [
        "harnessy.proof.forge.independent_approval_missing"
    ]
    assert [
        item["code"]
        for item in checker.evaluate_post(
            raw, {**CONFIG, "required_independent_approvals": 1}, value
        )
    ] == ["harnessy.proof.forge.independent_approval_missing"]


@pytest.mark.parametrize(
    "count,valid",
    [
        (0, True),
        (1, True),
        (10, True),
        (True, False),
        (False, False),
        (-1, False),
        (11, False),
        (1.5, False),
        ("0", False),
    ],
)
def test_approval_configuration_matches_published_garden_schema(count, valid):
    from app.modules.checkers.api.external import ExternalCheckerContractError

    configuration = {**CONFIG, "required_independent_approvals": count}
    spec = ExternalCheckerRegistrySpec.model_validate(
        publisher.registry_spec("sha256:" + "f" * 64, "v3", "post_submit")
    )
    raw, value = control()
    findings = checker.evaluate_post(raw, configuration, value)
    assert (not any(item["code"].endswith(".configuration") for item in findings)) is valid
    if valid:
        spec.configuration_schema.validate_instance(configuration)
    else:
        with pytest.raises(ExternalCheckerContractError):
            spec.configuration_schema.validate_instance(configuration)


@pytest.mark.parametrize(
    "guard,code",
    [
        ("ci", "harnessy.proof.forge.required_check"),
        ("producer", "harnessy.proof.forge.producer_mismatch"),
        ("unbound", "harnessy.proof.forge.unbound_required_check"),
        ("protected", "harnessy.proof.forge.protected_path_changed"),
        ("head", "harnessy.proof.forge.facts_binding"),
        ("repository", "harnessy.proof.forge.repository"),
        ("commit", "harnessy.proof.forge.head_sha"),
        ("task", "garden.proof.task_mismatch"),
    ],
)
def test_zero_approvals_retains_other_integrity_guards(guard, code):
    raw, value = control()
    value["forge_facts"]["reviews"] = []
    configuration = {**CONFIG, "required_independent_approvals": 0}
    assert checker.evaluate_post(raw, configuration, value) == []
    facts = value["forge_facts"]
    if guard == "ci":
        facts["required_checks"][0]["conclusion"] = "failure"
    elif guard == "producer":
        facts["required_checks"][0]["judged"][0]["producer"] = "github_app:999"
    elif guard == "unbound":
        facts["required_checks"][0]["required_producer"] = None
    elif guard == "protected":
        facts["changed_files"][0]["path"] = ".github/workflows/ci.yml"
    elif guard == "head":
        facts["required_checks"][0]["judged"][0]["sha"] = "a" * 40
    elif guard == "repository":
        facts["repository"] = "other/repository"
    elif guard == "commit":
        proof = json.loads(raw)
        proof["commit_sha"] = "a" * 40
        raw = json.dumps(proof).encode()
    else:
        value["task_id"] = OTHER_TASK
    findings = checker.evaluate_post(raw, configuration, value)
    assert code in [item["code"] for item in findings]
