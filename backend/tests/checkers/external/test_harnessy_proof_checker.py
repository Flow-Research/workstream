"""Harnessy proof checker: fail-closed comparison with GitHub facts."""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
import yaml

from app.modules.checkers.api.external import (
    ExternalCheckerContractError,
    ExternalCheckerExecutionResult,
    ExternalCheckerRegistrySpec,
)

CHECKER_ROOT = Path(__file__).parents[4] / "external_checkers" / "harnessy_proof"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"harnessy_proof_{name}", CHECKER_ROOT / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load("checker")
publish_local = _load("publish_local")

REPOSITORY = "Acme/widgets"
HEAD = "e" * 40
MERGE = "0123456789abcdef0123456789abcdef01234567"
PR_URL = f"https://github.com/{REPOSITORY}/pull/12"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/345"
CONFIGURATION = {"github_repository": "acme/widgets", "base_branch": "main"}

VALID_PROOF = {
    "schema": "harnessy.work.proof.v1",
    "commit_sha": MERGE,
    "pr_url": PR_URL,
    "ci_run_url": RUN_URL,
    "ci_conclusion": "success",
    "merged": True,
}


def _check(name: str = "backend", **changes: object) -> dict:
    check = {
        "name": name,
        "app_id": 15368,
        "app_bound": True,
        "conclusion": "success",
        "check_run_app_id": 15368,
        "check_run_head_sha": HEAD,
        "check_run_html_url": f"https://github.com/{REPOSITORY}/runs/10",
        "check_run_details_url": f"{RUN_URL}/job/678",
        "workflow_run_id": 345,
        "commit_status_judged": False,
        "commit_status_sha": None,
    }
    check.update(changes)
    return check


def _review(review_id: int, state: str, *, commit: str = HEAD, **reviewer: object) -> dict:
    return {
        "id": review_id,
        "reviewer": {"login": "reviewer", "id": 7, "type": "User", **reviewer},
        "state": state,
        "commit_id": commit,
        "submitted_at": "2026-10-24T11:00:00Z",
    }


FACTS = {
    "schema_version": "workstream.github_facts.v1",
    "repository": REPOSITORY,
    "pull_request_number": 12,
    "html_url": PR_URL,
    "state": "closed",
    "merged": True,
    "merge_commit_sha": MERGE,
    "base_ref": "main",
    "head_sha": HEAD,
    "author": {"login": "agent-bot", "id": 501, "type": "Bot"},
    "reviews": [_review(61, "APPROVED")],
    "changed_files_count": 1,
    "changed_files": [{"filename": "src/app.py", "previous_filename": None, "status": "modified"}],
    "required_checks": [_check("backend"), _check("lint", workflow_run_id=346)],
    "fetched_at": "2026-10-24T12:00:00Z",
    "responses": [{"request": "pull_request", "sha256": "sha256:" + "f" * 64}],
}


def _encoded(**changes: object) -> bytes:
    proof = {**VALID_PROOF, **changes}
    return json.dumps({key: value for key, value in proof.items() if value is not ...}).encode()


def _input(**changes: object) -> dict:
    facts = {**FACTS, **changes}
    return {
        "schema_version": "workstream.external_checker_post_submit_input.v1",
        "github_facts": {key: value for key, value in facts.items() if value is not ...},
    }


def _findings(
    proof: bytes | None = None,
    *,
    configuration: object = CONFIGURATION,
    input_value: object = None,
    **fact_changes: object,
) -> list[dict]:
    return checker.evaluate_proof(
        _encoded() if proof is None else proof,
        configuration=configuration,
        input_value=_input(**fact_changes) if input_value is None else input_value,
    )


def _codes(proof: bytes | None = None, **kwargs: object) -> list[str]:
    return [item["code"] for item in _findings(proof, **kwargs)]


def _request(phase: str = "post_submit") -> dict:
    return {
        "request_digest": "sha256:" + "b" * 64,
        "registry": {"registry_entry_id": str(uuid4()), "entry_digest": "sha256:" + "c" * 64},
        "identity": {"phase": phase},
    }


# Matching proof and result contract --------------------------------------------


def test_proof_matching_github_facts_passes_with_backend_valid_result() -> None:
    assert _findings() == []
    assert _codes(_encoded(commit_sha=MERGE.upper())) == []
    request = _request()
    parsed = ExternalCheckerExecutionResult.model_validate_json(
        json.dumps(checker.build_result(request, []))
    )
    assert (parsed.verdict, parsed.findings, parsed.phase) == ("passed", (), "post_submit")
    assert (
        parsed.request_digest,
        str(parsed.registry_entry_id),
        parsed.registry_entry_digest,
    ) == (
        request["request_digest"],
        request["registry"]["registry_entry_id"],
        request["registry"]["entry_digest"],
    )


def test_failed_verdict_exactly_when_an_error_finding_exists() -> None:
    findings = _findings(merged=False)
    parsed = ExternalCheckerExecutionResult.model_validate_json(
        json.dumps(checker.build_result(_request(), findings))
    )
    assert parsed.verdict == "failed"
    info = [{**findings[0], "level": "info"}]
    assert checker.build_result(_request(), info)["verdict"] == "passed"


def test_main_passes_request_configuration_and_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request = {**_request(), "configuration": CONFIGURATION, "input": _input(merged=False)}
    monkeypatch.setattr(checker, "read_proof", lambda _root: _encoded())
    monkeypatch.setattr(checker.sys, "stdin", io.StringIO(json.dumps(request)))
    assert checker.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "failed"
    assert [item["code"] for item in result["findings"]] == ["harnessy.proof.github.merged"]


# One fail-closed mode ------------------------------------------------------------


@pytest.mark.parametrize(
    "configuration",
    [
        None,
        {},
        {"github_repository": "acme/widgets"},
        {"base_branch": "main"},
        {**CONFIGURATION, "extra": True},
        {"github_repository": "", "base_branch": "main"},
        {**CONFIGURATION, "allow_unbound_required_checks": "yes"},
        {**CONFIGURATION, "protected_paths": ".github/**"},
        {**CONFIGURATION, "protected_paths": [""]},
        {**CONFIGURATION, "required_independent_approvals": 0},
        {**CONFIGURATION, "required_independent_approvals": True},
        {**CONFIGURATION, "operator_logins": [1]},
    ],
)
def test_missing_or_invalid_configuration_never_passes(configuration: object) -> None:
    assert _codes(configuration=configuration) == ["harnessy.proof.github.configuration"]


@pytest.mark.parametrize(
    "input_value",
    [{}, {"schema_version": "workstream.external_checker_post_submit_input.v1"}, "x"],
)
def test_missing_facts_never_pass(input_value: object) -> None:
    assert _codes(input_value=input_value) == ["harnessy.proof.github.facts_missing"]


@pytest.mark.parametrize(
    "facts_changes",
    [
        {"schema_version": "workstream.github_facts.v2"},
        {"merged": "true"},
        {"pull_request_number": "12"},
        {"html_url": ...},
        {"required_checks": []},
        {"required_checks": [{"name": "backend"}]},
        {"required_checks": [{**_check(), "extra": 1}]},
        {"required_checks": [_check(workflow_run_id="345")]},
        {"merge_commit_sha": "ABC"},
        {"head_sha": ...},
        {"author": ...},
        {"reviews": ...},
        {"reviews": [_review(61, "APPROVED", commit="not-a-sha")]},
        {"changed_files": ...},
        {"changed_files_count": ...},
        {"changed_files_count": 2},
    ],
)
def test_malformed_facts_are_an_error(facts_changes: dict) -> None:
    assert _codes(**facts_changes) == ["harnessy.proof.github.facts_invalid"]


@pytest.mark.parametrize(
    "check",
    [_check(check_run_head_sha="1" * 40), _check(commit_status_sha="2" * 40)],
    ids=("check-run-other-commit", "status-other-commit"),
)
def test_check_entry_naming_another_commit_fails_the_binding(check: dict) -> None:
    assert _codes(required_checks=[check]) == ["harnessy.proof.github.facts_binding"]


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (None, "missing"),
        (b"{not json", "invalid_json"),
        (b"\xff\xfe", "invalid_json"),
        (b"[]", "invalid_json"),
        (b" " * (checker.MAX_PROOF_BYTES + 1), "too_large"),
    ],
)
def test_unreadable_proof_reports_one_error(raw: bytes | None, code: str) -> None:
    findings = checker.evaluate_proof(raw, configuration=CONFIGURATION, input_value=_input())
    assert [item["code"] for item in findings] == [f"harnessy.proof.{code}"]


def test_read_proof_rejects_links_and_bounds_bytes(tmp_path: Path) -> None:
    assert checker.read_proof(tmp_path) is None
    target = tmp_path / "elsewhere.json"
    target.write_bytes(_encoded())
    (tmp_path / "proof.json").symlink_to(target)
    assert checker.read_proof(tmp_path) is None
    (tmp_path / "proof.json").unlink()
    (tmp_path / "proof.json").write_bytes(b"x" * (checker.MAX_PROOF_BYTES + 10))
    assert len(checker.read_proof(tmp_path)) == checker.MAX_PROOF_BYTES + 1


# Claims and mismatches -----------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"schema": "harnessy.work.proof.v2"}, "schema"),
        ({"schema": ...}, "schema"),
        ({"ci_conclusion": "failure"}, "ci_conclusion"),
        ({"ci_conclusion": ...}, "ci_conclusion"),
        ({"merged": "true"}, "merged"),
        ({"merged": 1}, "merged"),
        ({"merged": False}, "merged"),
    ],
)
def test_each_invalid_claim_reports_exactly_its_error(changes: dict, code: str) -> None:
    assert _codes(_encoded(**changes)) == [f"harnessy.proof.{code}"]


@pytest.mark.parametrize(
    "commit_sha",
    ["0123456789abcdef0123456789abcdef0123456", "g" * 40, 1234],
)
def test_malformed_commit_sha_fails_shape_and_merge_comparison(commit_sha: object) -> None:
    assert _codes(_encoded(commit_sha=commit_sha)) == [
        "harnessy.proof.commit_sha",
        "harnessy.proof.github.merge_commit_sha",
    ]


@pytest.mark.parametrize(
    ("proof_changes", "fact_changes", "codes"),
    [
        ({}, {"repository": "acme/other"}, ["repository", "pr_url", "ci_run"]),
        ({}, {"base_ref": "release"}, ["base_branch"]),
        ({}, {"merged": False, "state": "open"}, ["merged"]),
        ({"commit_sha": "1" * 40}, {}, ["merge_commit_sha"]),
        ({}, {"merged": False, "merge_commit_sha": None}, ["merged", "merge_commit_sha"]),
    ],
)
def test_each_github_mismatch_reports_its_finding(
    proof_changes: dict, fact_changes: dict, codes: list[str]
) -> None:
    assert _codes(_encoded(**proof_changes), **fact_changes) == [
        f"harnessy.proof.github.{code}" for code in codes
    ]


@pytest.mark.parametrize(
    "pr_url",
    [
        f"{PR_URL}/",
        f"{PR_URL}?x=1",
        f"{PR_URL}#top",
        "https://github.com:443/Acme/widgets/pull/12",
        "https://user@github.com/Acme/widgets/pull/12",
        "https://github.com/Acme/widgets/pull/%31%32",
        "https://github.com/Acme\\widgets/pull/12",
        "https://github.com/acme/widgets/pull/12",
        "https://github.com/Acme/widgets/pull/012",
        "https://github.com/Acme/widgets/pull/13",
        "https://github.com/Acme/widgéts/pull/12",
        "http://github.com/Acme/widgets/pull/12",
        "https://github.com/Acme/widgets/issues/12",
        "https://github.com/Acme/other/pull/12",
        None,
        12,
    ],
)
def test_pr_url_must_equal_the_canonical_github_url_exactly(pr_url: object) -> None:
    assert _codes(_encoded(pr_url=pr_url)) == ["harnessy.proof.github.pr_url"]


def test_pr_url_must_also_equal_githubs_own_html_url() -> None:
    assert _codes(html_url="https://github.com/Acme/widgets/pull/12/") == [
        "harnessy.proof.github.pr_url"
    ]


@pytest.mark.parametrize(
    "ci_run_url",
    [
        f"{RUN_URL}/job/678",
        f"{RUN_URL}/",
        f"{RUN_URL}?check_suite_focus=true",
        "https://github.com/Acme/widgets/actions/runs/999",
        "https://github.com/acme/widgets/actions/runs/345",
        "https://github.com/Acme/other/actions/runs/345",
        f"https://github.com/{REPOSITORY}/runs/10",
        None,
    ],
)
def test_ci_run_url_must_be_a_judged_required_workflow_run(ci_run_url: object) -> None:
    assert _codes(_encoded(ci_run_url=ci_run_url)) == ["harnessy.proof.github.ci_run"]


def test_ci_run_url_may_name_any_judged_required_workflow_run() -> None:
    other_run = f"https://github.com/{REPOSITORY}/actions/runs/346"
    assert _codes(_encoded(ci_run_url=other_run)) == []
    no_runs = [_check(workflow_run_id=None)]
    assert _codes(required_checks=no_runs) == ["harnessy.proof.github.ci_run"]


def test_each_unsuccessful_required_check_reports_its_own_finding() -> None:
    checks = [
        _check("backend", conclusion="failure"),
        _check("lint", workflow_run_id=None),
        _check("docs", conclusion="missing", workflow_run_id=None),
        _check("e2e\nspoof", conclusion="pending", workflow_run_id=None),
    ]
    findings = _findings(required_checks=checks)
    assert [item["code"] for item in findings] == ["harnessy.proof.github.required_check"] * 3
    messages = [item["message"] for item in findings]
    assert "backend is failure" in messages[0]
    assert "docs is missing" in messages[1]
    assert "e2e?spoof is pending" in messages[2]


# Integrity rules (owner decision 20) ----------------------------------------------


def test_unbound_required_check_is_an_error_unless_explicitly_allowed() -> None:
    checks = [_check("backend"), _check("lint", app_id=None, app_bound=False)]
    findings = _findings(required_checks=checks)
    assert [item["code"] for item in findings] == [
        "harnessy.proof.github.unbound_required_check"
    ]
    assert "lint" in findings[0]["message"]
    allowed = {**CONFIGURATION, "allow_unbound_required_checks": True}
    assert _codes(configuration=allowed, required_checks=checks) == []


@pytest.mark.parametrize(
    "changed",
    [
        {"filename": ".github/workflows/ci.yml", "previous_filename": None, "status": "modified"},
        {"filename": "docs/CODEOWNERS", "previous_filename": None, "status": "added"},
        {"filename": "CODEOWNERS", "previous_filename": None, "status": "modified"},
        {"filename": ".gitlab-ci.yml", "previous_filename": None, "status": "added"},
        {"filename": ".circleci/config.yml", "previous_filename": None, "status": "removed"},
        {"filename": ".github/workflows/x.yml", "previous_filename": "x.yml", "status": "renamed"},
        {
            "filename": "moved.yml",
            "previous_filename": ".github/workflows/x.yml",
            "status": "renamed",
        },
    ],
    ids=(
        "workflow",
        "nested-codeowners",
        "root-codeowners",
        "gitlab",
        "circleci",
        "rename-into-github",
        "rename-out-of-github",
    ),
)
def test_protected_path_change_requires_human_acceptance(changed: dict) -> None:
    files = [FACTS["changed_files"][0], changed]
    findings = _findings(changed_files=files, changed_files_count=2)
    assert [item["code"] for item in findings] == [
        "harnessy.proof.github.protected_path_changed"
    ]
    assert "cannot be auto-accepted" in findings[0]["message"]


def test_configured_protected_paths_extend_the_defaults() -> None:
    files = [{"filename": "deploy/prod.tf", "previous_filename": None, "status": "modified"}]
    assert _codes(changed_files=files) == []
    extended = {**CONFIGURATION, "protected_paths": ["deploy/**"]}
    assert _codes(configuration=extended, changed_files=files) == [
        "harnessy.proof.github.protected_path_changed"
    ]
    nested = [{"filename": "src/.github/x", "previous_filename": None, "status": "added"}]
    assert _codes(changed_files=nested) == []


def test_protected_path_finding_lists_a_bounded_number_of_paths() -> None:
    files = [
        {"filename": f".github/workflows/w{index}.yml", "previous_filename": None, "status": "added"}
        for index in range(20)
    ]
    findings = _findings(changed_files=files, changed_files_count=20)
    assert len(findings) == 1
    assert "and 15 more" in findings[0]["message"]


@pytest.mark.parametrize(
    "reviews",
    [
        [],
        [_review(61, "APPROVED", commit="1" * 40)],
        [_review(61, "APPROVED"), _review(62, "CHANGES_REQUESTED")],
        [_review(61, "APPROVED"), _review(62, "DISMISSED")],
        [_review(61, "APPROVED", type="Bot", login="ci-bot[bot]")],
        [_review(61, "APPROVED", login="agent-bot", id=501)],
        [_review(61, "APPROVED", login="Agent-Bot", id=999)],
        [_review(61, "COMMENTED")],
        [{**_review(61, "APPROVED"), "reviewer": None}],
    ],
    ids=(
        "no-review",
        "stale-approval-on-old-commit",
        "approval-then-changes-requested",
        "approval-then-dismissed",
        "bot-approval",
        "author-self-approval",
        "author-login-different-case",
        "comment-only",
        "deleted-reviewer",
    ),
)
def test_missing_independent_approval_on_head_commit_is_an_error(reviews: list) -> None:
    assert _codes(reviews=reviews) == ["harnessy.proof.github.independent_approval_missing"]


def test_latest_decisive_review_wins_and_comments_do_not_cancel() -> None:
    reviews = [
        _review(61, "CHANGES_REQUESTED"),
        _review(62, "APPROVED"),
        _review(63, "COMMENTED"),
    ]
    assert _codes(reviews=reviews) == []
    out_of_order = [_review(70, "APPROVED"), _review(65, "CHANGES_REQUESTED")]
    assert _codes(reviews=out_of_order) == []
    old_then_new = [_review(60, "APPROVED", commit="1" * 40), _review(61, "APPROVED")]
    assert _codes(reviews=old_then_new) == []


def test_required_independent_approvals_is_configurable() -> None:
    two = {**CONFIGURATION, "required_independent_approvals": 2}
    assert _codes(configuration=two) == ["harnessy.proof.github.independent_approval_missing"]
    reviews = [_review(61, "APPROVED"), _review(62, "APPROVED", login="second", id=8)]
    assert _codes(configuration=two, reviews=reviews) == []


def test_operator_only_approval_is_a_non_blocking_warning() -> None:
    operators = {**CONFIGURATION, "operator_logins": ["Reviewer"]}
    findings = _findings(configuration=operators)
    assert [(item["code"], item["level"]) for item in findings] == [
        ("harnessy.operator_approved", "warning")
    ]
    result = ExternalCheckerExecutionResult.model_validate_json(
        json.dumps(checker.build_result(_request(), findings))
    )
    assert result.verdict == "passed"
    reviews = [_review(61, "APPROVED"), _review(62, "APPROVED", login="independent", id=8)]
    assert _codes(configuration=operators, reviews=reviews) == []


# Published registry body -----------------------------------------------------------


def test_published_registry_body_is_post_only_and_backend_valid() -> None:
    digest = "sha256:" + "d" * 64
    spec = ExternalCheckerRegistrySpec.model_validate(publish_local.registry_spec(digest, "v2"))
    assert (spec.phase, spec.image_digest, spec.capability_id, spec.capability_version) == (
        "post_submit",
        digest,
        "harnessy.work_proof",
        "v2",
    )
    full = {
        **CONFIGURATION,
        "allow_unbound_required_checks": False,
        "protected_paths": ["deploy/**"],
        "required_independent_approvals": 2,
        "operator_logins": ["julian"],
    }
    spec.configuration_schema.validate_instance(CONFIGURATION)
    spec.configuration_schema.validate_instance(full)
    spec.input_schema.validate_instance(_input())
    for schema, value in (
        (spec.configuration_schema, {}),
        (spec.configuration_schema, {"github_repository": "acme/widgets"}),
        (spec.configuration_schema, {"base_branch": "main"}),
        (spec.configuration_schema, {**CONFIGURATION, "github_repository": "acme"}),
        (spec.configuration_schema, {**CONFIGURATION, "extra": 1}),
        (spec.configuration_schema, {**CONFIGURATION, "required_independent_approvals": 0}),
        (spec.configuration_schema, {**CONFIGURATION, "protected_paths": "deploy/**"}),
        (spec.input_schema, _input(schema_version="workstream.github_facts.v2")),
    ):
        with pytest.raises(ExternalCheckerContractError):
            schema.validate_instance(value)
    for registry in ("localhost:5000@registry.example", "localhost", "registry.example:5000"):
        with pytest.raises(SystemExit):
            publish_local.publish(registry, "harnessy-proof")


def test_published_service_paths_match_the_compose_overlay() -> None:
    """The service config and the overlay must name the same daemon and socket paths."""
    overlay = yaml.safe_load(
        (CHECKER_ROOT.parents[1] / "docker-compose.agent-loop.yml").read_text()
    )
    environment = overlay["x-agent-loop-backend"]["environment"]
    config = publish_local.service_config(
        {"operating_system": "linux", "architecture": "arm64"},
        compose_project="${COMPOSE_PROJECT_NAME}",
        sandbox_uid=501,
        sandbox_gid=20,
    )
    assert config["material_root"] == environment["WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT"]
    assert config["material_root"] == environment["WORKSTREAM_ARTIFACT_SCRATCH_ROOT"]
    assert config["socket_path"] == environment["WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET"]
    assert len(config["socket_path"].encode()) <= 107
    for name in ("backend", "worker", "beat", "checker", "checker-volumes-init"):
        socket_mounts = [
            mount
            for mount in overlay["services"][name]["volumes"]
            if (mount.split(":")[1] if isinstance(mount, str) else mount["target"])
            == "/run/ws-checker"
        ]
        mode = ":ro" if name in ("backend", "worker", "beat") else ""
        assert socket_mounts == [f"checker_socket:/run/ws-checker{mode}"], name


def test_long_or_control_check_names_are_bounded_in_messages() -> None:
    name = "x" * 300
    findings = _findings(required_checks=[_check(name, conclusion="failure")])
    assert [item["code"] for item in findings] == ["harnessy.proof.github.required_check"]
    assert "x" * 200 + "..." in findings[0]["message"]
    assert "x" * 201 not in findings[0]["message"]


@pytest.mark.parametrize(
    ("path", "protected"),
    [
        ("deploy/prod.tf", True),
        ("deploy/eu/prod.tf", False),
        ("keys/secret1.pem", True),
        ("keys/secret12.pem", False),
    ],
)
def test_configured_globs_keep_single_segment_wildcards_within_a_directory(
    path: str, protected: bool
) -> None:
    configuration = {**CONFIGURATION, "protected_paths": ["deploy/*.tf", "keys/secret?.pem"]}
    files = [{"filename": path, "previous_filename": None, "status": "modified"}]
    expected = ["harnessy.proof.github.protected_path_changed"] if protected else []
    assert _codes(configuration=configuration, changed_files=files) == expected


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_read_proof_rejects_non_regular_files(tmp_path: Path, kind: str) -> None:
    if kind == "directory":
        (tmp_path / "proof.json").mkdir()
    else:
        os.mkfifo(tmp_path / "proof.json")
    assert checker.read_proof(tmp_path) is None


def test_entrypoint_fails_closed_without_proof_material() -> None:
    """The image entrypoint runs isolated and reports the missing proof."""
    request = {**_request(), "configuration": CONFIGURATION, "input": _input()}
    completed = subprocess.run(
        [sys.executable, "-I", str(CHECKER_ROOT / "checker.py")],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    result = json.loads(completed.stdout)
    assert result["verdict"] == "failed"
    assert [item["code"] for item in result["findings"]] == ["harnessy.proof.missing"]
