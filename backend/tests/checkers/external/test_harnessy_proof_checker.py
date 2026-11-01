"""Harnessy proof checker: fail-closed comparison with forge-neutral change facts."""

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
OTHER = "1" * 40
MERGE = "0123456789abcdef0123456789abcdef01234567"
PRODUCER = "github_app:15368"
PR_URL = f"https://github.com/{REPOSITORY}/pull/12"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/345"
OTHER_RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/346"
CONFIGURATION = {
    "workstream_forge_facts_version": "v1",
    "forge": "github",
    "forge_origin": "https://github.com",
    "repository": "acme/widgets",
    "base_branch": "main",
}

VALID_PROOF = {
    "schema": "harnessy.work.proof.v1",
    "commit_sha": MERGE,
    "pr_url": PR_URL,
    "ci_run_url": RUN_URL,
    "ci_conclusion": "success",
    "merged": True,
}


def _check(name: str = "backend", *, sha: str | None = HEAD, **changes: object) -> dict:
    check = {
        "name": name,
        "conclusion": "success",
        "required_producer": PRODUCER,
        "judged": [{"producer": PRODUCER, "sha": sha}],
        "run_url": RUN_URL,
    }
    check.update(changes)
    return check


def _review(
    review_id: str,
    state: str,
    *,
    commit: str | None = HEAD,
    write_access: bool | None = True,
    **reviewer: object,
) -> dict:
    return {
        "id": review_id,
        "reviewer": {"login": "reviewer", "id": 7, "kind": "user", **reviewer},
        "reviewer_write_access": write_access,
        "state": state,
        "commit_id": commit,
        "submitted_at": "2026-10-24T11:00:00Z",
    }


def _file(path: str, previous_path: str | None = None, status: str = "modified") -> dict:
    return {"path": path, "previous_path": previous_path, "status": status}


FACTS = {
    "schema_version": "workstream.forge_change_facts.v1",
    "forge": "github",
    "forge_origin": "https://github.com",
    "repository": REPOSITORY,
    "change_number": 12,
    "change_url": PR_URL,
    "state": "closed",
    "merged": True,
    "landed_commit_sha": MERGE,
    "base_ref": "main",
    "head_sha": HEAD,
    "author": {"login": "agent-bot", "id": 501, "kind": "bot"},
    "reviews": [_review("61", "approved")],
    "changed_files_count": 1,
    "changed_files": [_file("src/app.py")],
    "required_checks": [_check("backend"), _check("lint", run_url=OTHER_RUN_URL)],
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
        "forge_facts": {key: value for key, value in facts.items() if value is not ...},
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


def _forge(*codes: str) -> list[str]:
    return [f"harnessy.proof.forge.{code}" for code in codes]


def _request(phase: str = "post_submit") -> dict:
    return {
        "request_digest": "sha256:" + "b" * 64,
        "registry": {"registry_entry_id": str(uuid4()), "entry_digest": "sha256:" + "c" * 64},
        "identity": {"phase": phase},
    }


# Matching proof and result contract --------------------------------------------


def test_proof_matching_forge_facts_passes_with_backend_valid_result() -> None:
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


def test_sha256_repository_commit_ids_pass() -> None:
    head, merge = "a" * 64, "b" * 64
    assert (
        _codes(
            _encoded(commit_sha=merge.upper()),
            head_sha=head,
            landed_commit_sha=merge,
            reviews=[_review("61", "approved", commit=head)],
            required_checks=[_check(sha=head)],
        )
        == []
    )


def test_pr_url_is_compared_with_the_reported_change_url_without_building_one() -> None:
    change_url = "https://forge.example/acme/widgets/-/merge_requests/12"
    run_url = "https://forge.example/acme/widgets/-/pipelines/9"
    proof = _encoded(pr_url=change_url, ci_run_url=run_url)
    assert _codes(proof, change_url=change_url, required_checks=[_check(run_url=run_url)]) == []


def test_failed_verdict_exactly_when_an_error_finding_exists() -> None:
    findings = _findings(merged=False, landed_commit_sha=None)
    parsed = ExternalCheckerExecutionResult.model_validate_json(
        json.dumps(checker.build_result(_request(), findings))
    )
    assert parsed.verdict == "failed"
    info = [{**findings[0], "level": "info"}]
    assert checker.build_result(_request(), info)["verdict"] == "passed"


def test_main_passes_request_configuration_and_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request = {**_request(), "configuration": CONFIGURATION, "input": _input(base_ref="dev")}
    monkeypatch.setattr(checker, "read_proof", lambda _root: _encoded())
    monkeypatch.setattr(checker.sys, "stdin", io.StringIO(json.dumps(request)))
    assert checker.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "failed"
    assert [item["code"] for item in result["findings"]] == _forge("base_branch")


# One fail-closed mode ------------------------------------------------------------


def _without(key: str) -> dict:
    return {name: value for name, value in CONFIGURATION.items() if name != key}


@pytest.mark.parametrize(
    "configuration",
    [
        None,
        {},
        _without("workstream_forge_facts_version"),
        _without("forge"),
        _without("forge_origin"),
        _without("repository"),
        _without("base_branch"),
        {**CONFIGURATION, "workstream_forge_facts_version": "v2"},
        {**CONFIGURATION, "workstream_forge_facts_version": 1},
        {**CONFIGURATION, "forge_origin": "https://github.com/"},
        {**CONFIGURATION, "forge_origin": "https://github.com/acme"},
        {**CONFIGURATION, "forge_origin": "http://github.com"},
        {**CONFIGURATION, "forge_origin": "github.com"},
        {**CONFIGURATION, "forge_origin": "https://user@github.com"},
        {**CONFIGURATION, "repository": "acme"},
        {**CONFIGURATION, "repository": "acme/../widgets"},
        {**CONFIGURATION, "repository": "acme/./widgets"},
        {**CONFIGURATION, "repository": "/acme/widgets"},
        {**CONFIGURATION, "repository": "acme/widgets/"},
        {**CONFIGURATION, "repository": "acme//widgets"},
        {**CONFIGURATION, "repository": "acme/wid gets"},
        {**CONFIGURATION, "repository": "a/" + "b" * 254},
        {**CONFIGURATION, "forge": "gitlab"},
        {**CONFIGURATION, "forge": "GitHub"},
        {**CONFIGURATION, "extra": True},
        {**_without("repository"), "github_repository": "acme/widgets"},
        {**CONFIGURATION, "repository": ""},
        {**CONFIGURATION, "base_branch": ""},
        {**CONFIGURATION, "allow_unbound_required_checks": "yes"},
        {**CONFIGURATION, "protected_paths": ".github/**"},
        {**CONFIGURATION, "protected_paths": [""]},
        {**CONFIGURATION, "required_independent_approvals": 0},
        {**CONFIGURATION, "required_independent_approvals": True},
        {**CONFIGURATION, "operator_logins": [1]},
    ],
)
def test_missing_or_invalid_configuration_never_passes(configuration: object) -> None:
    assert _codes(configuration=configuration) == _forge("configuration")


@pytest.mark.parametrize(
    "input_value",
    [
        {},
        {"schema_version": "workstream.external_checker_post_submit_input.v1"},
        {"github_facts": FACTS},
        "x",
    ],
)
def test_missing_facts_never_pass(input_value: object) -> None:
    findings = _findings(input_value=input_value)
    assert [item["code"] for item in findings] == _forge("facts_missing")
    assert findings[0]["message"] == (
        "proof.json pr_url must name a change in acme/widgets on https://github.com; "
        "WorkStream could not read facts for this proof."
    )


@pytest.mark.parametrize(
    "facts_changes",
    [
        {"schema_version": "workstream.github_facts.v1"},
        {"schema_version": "workstream.forge_change_facts.v2"},
        {"extra": 1},
        {"forge": ...},
        {"forge": None},
        {"forge_origin": ...},
        {"forge_origin": None},
        {"forge_origin": "https://github.com/"},
        {"forge_origin": "https://github.com/Acme"},
        {"repository": "Acme"},
        {"repository": "Acme/../widgets"},
        {"repository": "Acme/widgets/"},
        {"repository": None},
        {"change_url": ...},
        {"change_url": None},
        {"change_number": "12"},
        {"change_number": 0},
        {"change_number": True},
        {"state": "merged"},
        {"merged": "true"},
        {"merged": False},
        {"landed_commit_sha": None},
        {"merge_commit_sha": MERGE, "landed_commit_sha": ...},
        {"state": "open"},
        {"merged": False, "state": "open"},
        {"landed_commit_sha": "ABC"},
        {"landed_commit_sha": MERGE.upper()},
        {"head_sha": ...},
        {"head_sha": HEAD.upper()},
        {"head_sha": "e" * 41},
        {"author": ...},
        {"author": {"login": "agent-bot", "id": 501, "type": "Bot"}},
        {"author": {"login": "agent-bot", "id": 501, "kind": "Bot"}},
        {"author": {"login": "agent-bot", "id": 0, "kind": "bot"}},
        {"author": {"login": "agent-bot", "id": 501, "kind": "bot", "extra": 1}},
        {"reviews": ...},
        {"reviews": [_review("61", "APPROVED")]},
        {"reviews": [_review("61", "approved", commit="not-a-sha")]},
        {"reviews": [{**_review("61", "approved"), "extra": 1}]},
        {"reviews": [{**_review("61", "approved"), "submitted_at": "yesterday"}]},
        {"reviews": [_review("61", "approved", kind="User")]},
        {"reviews": [_review(61, "approved")]},
        {"reviews": [_review("", "approved")]},
        {"reviews": [_review("x" * 101, "approved")]},
        {"reviews": [_review("61", "approved", write_access=1)]},
        {"reviews": [_review("61", "approved", write_access="true")]},
        {
            "reviews": [
                {k: v for k, v in _review("61", "approved").items() if k != "reviewer_write_access"}
            ]
        },
        {"changed_files": ...},
        {"changed_files": [{"filename": "src/app.py", "previous_filename": None, "status": "x"}]},
        {"changed_files": [{"path": "src/app.py", "previous_path": None}]},
        {"changed_files_count": ...},
        {"changed_files_count": 2},
        {"required_checks": []},
        {"required_checks": [{"name": "backend"}]},
        {"required_checks": [{**_check(), "extra": 1}]},
        {"required_checks": [_check(conclusion="passed")]},
        {"required_checks": [_check(required_producer=15368)]},
        {"required_checks": [_check(judged=[{"producer": PRODUCER}])]},
        {"required_checks": [_check(sha=HEAD.upper())]},
        {"required_checks": [_check(run_url=345)]},
        {"required_checks": [_check(judged=[])]},
        {"fetched_at": ...},
        {"fetched_at": "2026-10-24 12:00"},
        {"fetched_at": "2026-13-40T12:00:00Z"},
        {"responses": []},
        {"responses": [{"request": "pull_request", "sha256": "f" * 64}]},
        {"responses": [{"request": "pull_request", "sha256": "sha256:" + "F" * 64}]},
    ],
)
def test_malformed_facts_are_an_error(facts_changes: dict) -> None:
    assert _codes(**facts_changes) == _forge("facts_invalid")


@pytest.mark.parametrize(
    "judged",
    [
        [{"producer": PRODUCER, "sha": OTHER}],
        [{"producer": PRODUCER, "sha": HEAD}, {"producer": PRODUCER, "sha": OTHER}],
        [{"producer": None, "sha": OTHER}],
    ],
    ids=("other-commit", "mixed-commits", "status-other-commit"),
)
def test_judged_result_naming_another_commit_fails_the_binding(judged: list) -> None:
    checks = [_check(judged=judged)]
    assert _codes(required_checks=checks) == _forge("facts_binding")


def test_judged_result_without_a_commit_is_not_a_binding_failure() -> None:
    assert _codes(required_checks=[_check(sha=None)]) == []


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
    [
        "0123456789abcdef0123456789abcdef0123456",
        "0123456789abcdef0123456789abcdef012345678",
        "a" * 63,
        "a" * 65,
        "g" * 40,
        1234,
    ],
)
def test_malformed_commit_sha_fails_shape_and_landed_commit_comparison(commit_sha: object) -> None:
    assert _codes(_encoded(commit_sha=commit_sha)) == [
        "harnessy.proof.commit_sha",
        "harnessy.proof.forge.landed_commit_sha",
    ]


@pytest.mark.parametrize(
    ("proof_changes", "fact_changes", "codes"),
    [
        ({}, {"repository": "acme/other"}, ["repository"]),
        ({}, {"forge": "gitlab"}, ["repository"]),
        ({}, {"forge_origin": "https://github.example.com"}, ["repository"]),
        ({}, {"forge_origin": "https://github.com:8443"}, ["repository"]),
        ({}, {"base_ref": "release"}, ["base_branch"]),
        ({}, {"merged": False, "landed_commit_sha": None}, ["merged", "landed_commit_sha"]),
        (
            {},
            {"merged": False, "state": "open", "landed_commit_sha": None},
            ["merged", "landed_commit_sha"],
        ),
        ({"commit_sha": OTHER}, {}, ["landed_commit_sha"]),
    ],
)
def test_each_forge_mismatch_reports_its_finding(
    proof_changes: dict, fact_changes: dict, codes: list[str]
) -> None:
    assert _codes(_encoded(**proof_changes), **fact_changes) == _forge(*codes)


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
def test_pr_url_must_equal_the_reported_change_url_exactly(pr_url: object) -> None:
    assert _codes(_encoded(pr_url=pr_url)) == _forge("change_url")


def test_change_url_is_not_rebuilt_from_the_change_number() -> None:
    assert _codes(change_number=13) == []
    assert _codes(change_url=f"{PR_URL}/") == _forge("change_url")


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
        PR_URL,
        None,
    ],
)
def test_ci_run_url_must_equal_a_required_check_run_url(ci_run_url: object) -> None:
    assert _codes(_encoded(ci_run_url=ci_run_url)) == _forge("ci_run")


def test_ci_run_url_may_name_any_required_check_run() -> None:
    assert _codes(_encoded(ci_run_url=OTHER_RUN_URL)) == []
    no_runs = [_check(run_url=None)]
    assert _codes(required_checks=no_runs) == _forge("ci_run")


def test_each_unsuccessful_required_check_reports_its_own_finding() -> None:
    checks = [
        _check("backend", conclusion="failure"),
        _check("lint", run_url=None),
        _check("docs", conclusion="missing", judged=[], run_url=None),
        _check("e2e\nspoof", conclusion="pending", run_url=None),
    ]
    findings = _findings(required_checks=checks)
    assert [item["code"] for item in findings] == _forge(*["required_check"] * 3)
    messages = [item["message"] for item in findings]
    assert "backend is failure" in messages[0]
    assert "docs is missing" in messages[1]
    assert "e2e?spoof is pending" in messages[2]


# Integrity rules (owner decision 20) ----------------------------------------------


def test_unbound_required_check_is_an_error_unless_explicitly_allowed() -> None:
    unbound = _check("lint", required_producer=None, judged=[{"producer": None, "sha": HEAD}])
    checks = [_check("backend"), unbound]
    findings = _findings(required_checks=checks)
    assert [item["code"] for item in findings] == _forge("unbound_required_check")
    assert "lint" in findings[0]["message"]
    allowed = {**CONFIGURATION, "allow_unbound_required_checks": True}
    assert _codes(configuration=allowed, required_checks=checks) == []


@pytest.mark.parametrize(
    "judged",
    [
        [{"producer": "github_app:999", "sha": HEAD}],
        [{"producer": None, "sha": HEAD}],
        [{"producer": PRODUCER, "sha": HEAD}, {"producer": "github_app:999", "sha": HEAD}],
    ],
    ids=("other-producer", "producer-unknown", "one-of-two-differs"),
)
def test_result_from_another_producer_is_a_producer_mismatch(judged: list) -> None:
    findings = _findings(required_checks=[_check("backend", judged=judged)])
    assert [item["code"] for item in findings] == _forge("producer_mismatch")
    assert "backend" in findings[0]["message"]
    allowed = {**CONFIGURATION, "allow_unbound_required_checks": True}
    checks = [_check("backend", judged=judged)]
    assert _codes(configuration=allowed, required_checks=checks) == _forge("producer_mismatch")


@pytest.mark.parametrize(
    "changed",
    [
        _file(".github/workflows/ci.yml"),
        _file("docs/CODEOWNERS", status="added"),
        _file("CODEOWNERS"),
        _file(".gitlab-ci.yml", status="added"),
        _file(".circleci/config.yml", status="removed"),
        _file(".gitlab/ci/build.yml", status="added"),
        _file(".forgejo/workflows/ci.yml"),
        _file(".gitea/workflows/ci.yml"),
        _file(".woodpecker/build.yml"),
        _file(".woodpecker.yml"),
        _file(".woodpecker.yaml", status="added"),
        _file(".github/workflows/x.yml", "x.yml", "renamed"),
        _file("moved.yml", ".github/workflows/x.yml", "renamed"),
    ],
    ids=(
        "workflow",
        "nested-codeowners",
        "root-codeowners",
        "gitlab",
        "circleci",
        "gitlab-directory",
        "forgejo",
        "gitea",
        "woodpecker-directory",
        "woodpecker-yml",
        "woodpecker-yaml",
        "rename-into-github",
        "rename-out-of-github",
    ),
)
def test_protected_path_change_requires_human_acceptance(changed: dict) -> None:
    files = [FACTS["changed_files"][0], changed]
    findings = _findings(changed_files=files, changed_files_count=2)
    assert [item["code"] for item in findings] == _forge("protected_path_changed")
    assert "cannot be auto-accepted" in findings[0]["message"]


def test_configured_protected_paths_extend_the_defaults() -> None:
    files = [_file("deploy/prod.tf")]
    assert _codes(changed_files=files) == []
    extended = {**CONFIGURATION, "protected_paths": ["deploy/**"]}
    assert _codes(configuration=extended, changed_files=files) == _forge("protected_path_changed")
    nested = [_file("src/.github/x", status="added")]
    assert _codes(changed_files=nested) == []


def test_protected_path_finding_lists_a_bounded_number_of_paths() -> None:
    files = [_file(f".github/workflows/w{index}.yml", status="added") for index in range(20)]
    findings = _findings(changed_files=files, changed_files_count=20)
    assert len(findings) == 1
    assert "and 15 more" in findings[0]["message"]


@pytest.mark.parametrize(
    "reviews",
    [
        [],
        [_review("61", "approved", commit=OTHER)],
        [_review("61", "approved", commit=None)],
        [_review("61", "approved"), _review("62", "changes_requested")],
        [_review("61", "approved"), _review("62", "dismissed")],
        [_review("61", "approved", kind="bot", login="ci-bot[bot]")],
        [_review("61", "approved", kind="other", login="some-app")],
        [_review("61", "approved", login="agent-bot", id=501)],
        [_review("61", "approved", login="Agent-Bot", id=999)],
        [_review("61", "commented")],
        [_review("61", "pending")],
        [_review("61", "other")],
        [{**_review("61", "approved"), "reviewer": None}],
        [_review("61", "approved", write_access=None)],
        [_review("61", "approved", write_access=False)],
    ],
    ids=(
        "no-review",
        "stale-approval-on-old-commit",
        "approval-not-bound-to-a-commit",
        "approval-then-changes-requested",
        "approval-then-dismissed",
        "bot-approval",
        "other-kind-approval",
        "author-self-approval",
        "author-login-different-case",
        "comment-only",
        "pending-only",
        "other-state-only",
        "deleted-reviewer",
        "write-access-unknown",
        "no-write-access",
    ),
)
def test_missing_independent_approval_on_head_commit_is_an_error(reviews: list) -> None:
    assert _codes(reviews=reviews) == _forge("independent_approval_missing")


def test_latest_decisive_review_by_list_position_wins_and_comments_do_not_cancel() -> None:
    reviews = [
        _review("61", "changes_requested"),
        _review("62", "approved"),
        _review("63", "commented"),
    ]
    assert _codes(reviews=reviews) == []
    old_then_new = [_review("60", "approved", commit=OTHER), _review("61", "approved")]
    assert _codes(reviews=old_then_new) == []
    # Ids are opaque: a later approval counts although its id sorts lower.
    assert _codes(reviews=[_review("9", "changes_requested"), _review("10", "approved")]) == []


def test_later_changes_requested_supersedes_approval_even_when_its_id_sorts_lower() -> None:
    """Position, not id order, decides: numeric and string orderings both disagree here."""
    reviews = [_review("70", "approved"), _review("100", "changes_requested")]
    assert _codes(reviews=reviews) == _forge("independent_approval_missing")
    reviews = [_review("b", "approved"), _review("a", "changes_requested")]
    assert _codes(reviews=reviews) == _forge("independent_approval_missing")


def test_contributor_second_account_without_write_access_is_not_independent() -> None:
    """A second account the forge does not show with write access never counts."""
    second = {"login": "contributor-alt", "id": 900}
    for write_access in (None, False):
        reviews = [_review("61", "approved", write_access=write_access, **second)]
        findings = _findings(reviews=reviews)
        assert [item["code"] for item in findings] == _forge("independent_approval_missing")
        message = findings[0]["message"]
        assert "reviewers with write access who are neither the author nor a bot" in message
    maintainer = [
        _review("61", "approved", write_access=False, **second),
        _review("62", "approved", login="maintainer", id=8),
    ]
    assert _codes(reviews=maintainer) == []


def test_gitlab_style_subgroup_repository_is_accepted() -> None:
    repository = "acme/platform/widgets"
    configuration = {**CONFIGURATION, "repository": "Acme/Platform/widgets"}
    assert _codes(configuration=configuration, repository=repository) == []


def test_required_independent_approvals_is_configurable() -> None:
    two = {**CONFIGURATION, "required_independent_approvals": 2}
    assert _codes(configuration=two) == _forge("independent_approval_missing")
    reviews = [_review("61", "approved"), _review("62", "approved", login="second", id=8)]
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
    reviews = [_review("61", "approved"), _review("62", "approved", login="independent", id=8)]
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
    for accepted in (
        {**CONFIGURATION, "repository": "acme/platform/widgets"},
        {**CONFIGURATION, "repository": "acme/.github"},
        {**CONFIGURATION, "forge_origin": "https://git.example.org:8443"},
    ):
        spec.configuration_schema.validate_instance(accepted)
    spec.input_schema.validate_instance(_input())
    for schema, value in (
        (spec.configuration_schema, {}),
        (spec.configuration_schema, _without("workstream_forge_facts_version")),
        (spec.configuration_schema, _without("forge")),
        (spec.configuration_schema, _without("forge_origin")),
        (spec.configuration_schema, {**CONFIGURATION, "forge_origin": "https://github.com/"}),
        (spec.configuration_schema, {**CONFIGURATION, "forge_origin": "http://github.com"}),
        (spec.configuration_schema, _without("repository")),
        (spec.configuration_schema, _without("base_branch")),
        (spec.configuration_schema, {**CONFIGURATION, "workstream_forge_facts_version": "v2"}),
        (spec.configuration_schema, {**CONFIGURATION, "forge": "gitlab"}),
        (spec.configuration_schema, {**CONFIGURATION, "repository": "acme"}),
        (spec.configuration_schema, {**CONFIGURATION, "repository": "acme/../widgets"}),
        (spec.configuration_schema, {**CONFIGURATION, "repository": "../acme/widgets"}),
        (spec.configuration_schema, {**CONFIGURATION, "repository": "acme/widgets/"}),
        (spec.configuration_schema, {**CONFIGURATION, "repository": "a/" + "b" * 254}),
        (spec.configuration_schema, {**CONFIGURATION, "github_repository": "acme/widgets"}),
        (spec.configuration_schema, {**CONFIGURATION, "extra": 1}),
        (spec.configuration_schema, {**CONFIGURATION, "required_independent_approvals": 0}),
        (spec.configuration_schema, {**CONFIGURATION, "protected_paths": "deploy/**"}),
        (spec.input_schema, _input(schema_version="workstream.github_facts.v1")),
        (spec.input_schema, _input(schema_version="workstream.forge_change_facts.v2")),
    ):
        with pytest.raises(ExternalCheckerContractError):
            schema.validate_instance(value)
    for registry in ("localhost:5000@registry.example", "localhost", "registry.example:5000"):
        with pytest.raises(SystemExit):
            publish_local.publish(registry, "harnessy-proof")


def test_published_service_paths_match_the_compose_overlay() -> None:
    """The service config and the overlay must name the same daemon and socket paths."""
    base = yaml.safe_load((CHECKER_ROOT.parents[1] / "docker-compose.yml").read_text())
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
    assert "model_proxy_socket" not in config
    assert "model_relay_root" not in config
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

    model_config = publish_local.service_config(
        {"operating_system": "linux", "architecture": "arm64"},
        compose_project="${COMPOSE_PROJECT_NAME}",
        sandbox_uid=501,
        sandbox_gid=20,
        enable_model_proxy=True,
    )
    relay_root = "/var/lib/docker/volumes/${COMPOSE_PROJECT_NAME}-checker-relay/_data"
    assert model_config["model_proxy_socket"] == "/run/ws-model-proxy/model-proxy.sock"
    assert model_config["model_relay_root"] == relay_root
    assert len(f"{relay_root}/.model-{'0' * 16}/model.sock".encode()) < 108
    base_proxy = base["services"]["model-proxy"]
    overlay_proxy = overlay["services"]["model-proxy"]
    assert base_proxy["profiles"] == ["model-proxy"]
    assert base_proxy["command"] == ["python", "-m", "app.workers.checker_model_proxy"]
    assert base_proxy["stop_grace_period"] == "125m"
    assert "extends" not in overlay_proxy
    assert "profiles" not in overlay_proxy
    assert overlay_proxy["environment"]["WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET"] == (
        "/run/ws-model-proxy/model-proxy.sock"
    )
    assert "checker_model_proxy:/run/ws-model-proxy" in overlay_proxy["volumes"]
    for name in ("backend", "worker", "beat", "model-proxy"):
        assert all(
            "/var/run/docker.sock" not in str(mount)
            for mount in overlay["services"].get(name, {}).get("volumes", ())
        )
    for name in ("backend", "beat"):
        assert all(
            "checker_model_proxy" not in str(mount)
            for mount in overlay["services"][name]["volumes"]
        )
    worker = overlay["services"]["worker"]
    assert worker["environment"]["WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET"] == (
        "/run/ws-model-proxy/model-proxy.sock"
    )
    assert "checker_model_proxy:/run/ws-model-proxy:ro" in worker["volumes"]
    assert "checker_model_proxy:/run/ws-model-proxy:ro" in overlay["services"]["checker"]["volumes"]
    assert (
        "checker_model_relay:"
        "/var/lib/docker/volumes/${COMPOSE_PROJECT_NAME}-checker-relay/_data"
        in overlay["services"]["checker"]["volumes"]
    )
    for volume in ("checker_model_proxy", "checker_model_relay"):
        assert any(
            isinstance(mount, str) and mount.startswith(f"{volume}:")
            for mount in overlay["services"]["checker-volumes-init"]["volumes"]
        )
    with pytest.raises(ValueError, match="relay socket path too long"):
        publish_local.service_config(
            {"operating_system": "linux", "architecture": "arm64"},
            compose_project="x" * 80,
            sandbox_uid=501,
            sandbox_gid=20,
            enable_model_proxy=True,
        )


def test_long_or_control_check_names_are_bounded_in_messages() -> None:
    name = "x" * 300
    findings = _findings(required_checks=[_check(name, conclusion="failure")])
    assert [item["code"] for item in findings] == _forge("required_check")
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
    files = [_file(path)]
    expected = _forge("protected_path_changed") if protected else []
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
