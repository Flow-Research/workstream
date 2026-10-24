"""Networkless Harnessy work-proof checker for post-submission evaluation.

The checker reads one ``external_checker_request.v1`` envelope on stdin and the
verified, read-only Submission material under ``/work/input``. It compares the
claims in ``proof.json`` with ``workstream.github_facts.v1`` facts that
WorkStream read from GitHub and placed in the request input under
``github_facts``, and writes one ``external_checker_result.v1`` envelope.

There is one mode and it fails closed (owner decision 20): the binding
configuration must name ``github_repository`` and ``base_branch``, and the facts
must be present and well formed. Otherwise the verdict is ``failed``. A proof is
never passed on its own claims. The checker itself never uses the network or a
credential, and it derives nothing from URLs beyond exact equality with the
canonical URLs built from the facts.

Integrity rules: every required check must be bound to an App; a change to CI
or repository configuration paths needs explicit human acceptance; the head
commit needs an independent approval (latest decisive review, not the author,
not a bot); every fact entry that names a commit must name the head commit; and
approval only by configured operators adds a non-blocking
``harnessy.operator_approved`` warning.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

PROOF_PATH = "proof.json"
PROOF_SCHEMA = "harnessy.work.proof.v1"
MAX_PROOF_BYTES = 65_536
CHECK_ID = "harnessy.proof"
GITHUB_FACTS_INPUT_KEY = "github_facts"
GITHUB_FACTS_SCHEMA = "workstream.github_facts.v1"
DEFAULT_PROTECTED_PATHS = (".github/**", "**/CODEOWNERS", ".gitlab-ci.yml", ".circleci/**")
DEFAULT_REQUIRED_INDEPENDENT_APPROVALS = 1
OPERATOR_APPROVED_CODE = "harnessy.operator_approved"
_COMMIT_SHA = re.compile(r"[0-9a-fA-F]{40}")
_LOWER_SHA = re.compile(r"[0-9a-f]{40}")
_APPROVAL_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED"})
_MAX_CHECK_NAME_CHARACTERS = 200
_MAX_LISTED_PATHS = 5
_CONFIGURATION_KEYS = frozenset(
    {
        "github_repository",
        "base_branch",
        "allow_unbound_required_checks",
        "protected_paths",
        "required_independent_approvals",
        "operator_logins",
    }
)


def _finding(code: str, message: str, *, level: str = "error") -> dict[str, object]:
    return {
        "check_id": CHECK_ID,
        "code": f"{CHECK_ID}.{code}",
        "level": level,
        "message": message,
        "path": PROOF_PATH,
        "line": None,
    }


def evaluate_proof(
    raw: bytes | None,
    *,
    configuration: object,
    input_value: object,
) -> list[dict[str, object]]:
    """Return findings for one proof; it passes only when it matches GitHub facts."""
    if raw is None:
        return [_finding("missing", "The submission must contain proof.json at its root.")]
    if len(raw) > MAX_PROOF_BYTES:
        return [_finding("too_large", "proof.json must be at most 64 KiB.")]
    try:
        proof = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return [_finding("invalid_json", "proof.json must be valid UTF-8 JSON.")]
    if not isinstance(proof, dict):
        return [_finding("invalid_json", "proof.json must contain a JSON object.")]
    return claim_findings(proof) + compare_github_facts(proof, configuration, input_value)


def claim_findings(proof: dict) -> list[dict[str, object]]:
    """Check the claims that need no facts; URLs are checked against the facts."""
    findings = []
    if proof.get("schema") != PROOF_SCHEMA:
        findings.append(_finding("schema", f"schema must be {PROOF_SCHEMA!r}."))
    commit_sha = proof.get("commit_sha")
    if not isinstance(commit_sha, str) or _COMMIT_SHA.fullmatch(commit_sha) is None:
        findings.append(_finding("commit_sha", "commit_sha must be 40 hexadecimal characters."))
    if proof.get("ci_conclusion") != "success":
        findings.append(_finding("ci_conclusion", "ci_conclusion must be 'success'."))
    if proof.get("merged") is not True:
        findings.append(_finding("merged", "merged must be the JSON value true."))
    return findings


def _strings(value: object) -> bool:
    """Return whether a value is a list of non-empty strings."""
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def github_configuration(configuration: object) -> dict | None:
    """Return the normalized configuration, or None when it is absent or invalid.

    Integrity options take safe defaults: unbound required checks are errors,
    the default protected paths apply, and one independent approval is needed.
    """
    if not isinstance(configuration, dict):
        return None
    repository = configuration.get("github_repository")
    base_branch = configuration.get("base_branch")
    allow_unbound = configuration.get("allow_unbound_required_checks", False)
    protected = configuration.get("protected_paths", [])
    approvals = configuration.get(
        "required_independent_approvals", DEFAULT_REQUIRED_INDEPENDENT_APPROVALS
    )
    operators = configuration.get("operator_logins", [])
    if (
        not set(configuration) <= _CONFIGURATION_KEYS
        or not isinstance(repository, str)
        or not isinstance(base_branch, str)
        or not repository
        or not base_branch
        or not isinstance(allow_unbound, bool)
        or not _strings(protected)
        or type(approvals) is not int
        or approvals < 1
        or not _strings(operators)
    ):
        return None
    return {
        "repository": repository,
        "base_branch": base_branch,
        "allow_unbound": allow_unbound,
        "protected_paths": (*DEFAULT_PROTECTED_PATHS, *protected),
        "required_approvals": approvals,
        "operators": frozenset(login.casefold() for login in operators),
    }


def _actor(value: object) -> bool:
    """Return whether a value has the GitHub actor fact shape."""
    return (
        isinstance(value, dict)
        and isinstance(value.get("login"), str)
        and type(value.get("id")) is int
        and isinstance(value.get("type"), str)
    )


def _optional(value: object, kind: type) -> bool:
    """Return whether a value is null or a non-boolean instance of ``kind``."""
    return value is None or (isinstance(value, kind) and type(value) is not bool)


def _sha_or_none(value: object) -> bool:
    """Return whether a value is null or a lowercase 40-character commit SHA."""
    return value is None or (isinstance(value, str) and _LOWER_SHA.fullmatch(value) is not None)


_CHECK_KEYS = frozenset(
    {
        "name",
        "app_id",
        "app_bound",
        "conclusion",
        "check_run_app_id",
        "check_run_head_sha",
        "check_run_html_url",
        "check_run_details_url",
        "workflow_run_id",
        "commit_status_judged",
        "commit_status_sha",
    }
)


def valid_facts(facts: object) -> bool:
    """Accept only the exact ``workstream.github_facts.v1`` field shape."""
    if not isinstance(facts, dict) or facts.get("schema_version") != GITHUB_FACTS_SCHEMA:
        return False
    checks = facts.get("required_checks")
    reviews = facts.get("reviews")
    files = facts.get("changed_files")
    return (
        isinstance(facts.get("repository"), str)
        and type(facts.get("pull_request_number")) is int
        and isinstance(facts.get("html_url"), str)
        and isinstance(facts.get("merged"), bool)
        and _sha_or_none(facts.get("merge_commit_sha"))
        and isinstance(facts.get("base_ref"), str)
        and isinstance(facts.get("head_sha"), str)
        and _LOWER_SHA.fullmatch(facts["head_sha"]) is not None
        and _actor(facts.get("author"))
        and isinstance(reviews, list)
        and all(
            isinstance(review, dict)
            and type(review.get("id")) is int
            and (review.get("reviewer") is None or _actor(review.get("reviewer")))
            and isinstance(review.get("state"), str)
            and _sha_or_none(review.get("commit_id"))
            for review in reviews
        )
        and isinstance(files, list)
        and type(facts.get("changed_files_count")) is int
        and facts["changed_files_count"] == len(files)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("filename"), str)
            and _optional(item.get("previous_filename"), str)
            for item in files
        )
        and isinstance(checks, list)
        and len(checks) > 0
        and all(
            isinstance(check, dict)
            and set(check) == _CHECK_KEYS
            and isinstance(check["name"], str)
            and isinstance(check["conclusion"], str)
            and isinstance(check["app_bound"], bool)
            and isinstance(check["commit_status_judged"], bool)
            and _sha_or_none(check["check_run_head_sha"])
            and _sha_or_none(check["commit_status_sha"])
            and _optional(check["workflow_run_id"], int)
            for check in checks
        )
    )


def _display(value: str) -> str:
    """Bound a GitHub-provided name for a contributor-visible message."""
    printable = "".join(character if character.isprintable() else "?" for character in value)
    if len(printable) > _MAX_CHECK_NAME_CHARACTERS:
        return printable[:_MAX_CHECK_NAME_CHARACTERS] + "..."
    return printable


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a path glob: ``**`` spans directories, ``*`` and ``?`` do not.

    A leading ``**/`` also matches at the repository root.
    """
    parts = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(parts))


def protected_changes(files: list[dict], patterns: tuple[str, ...]) -> list[str]:
    """Return changed paths, including rename sources, that match a protected glob."""
    compiled = [_glob_regex(pattern) for pattern in patterns]
    matched = []
    for item in files:
        for path in (item.get("previous_filename"), item["filename"]):
            if path and any(regex.fullmatch(path) for regex in compiled):
                matched.append(path)
    return sorted(set(matched))


def qualifying_approvals(facts: dict) -> list[str]:
    """Return logins whose latest decisive review approves the head commit.

    Each reviewer's latest ``APPROVED``, ``CHANGES_REQUESTED`` or ``DISMISSED``
    review (by review id) decides; comments do not. The approval must name the
    head SHA and come from a ``User`` who is not the pull request author.
    """
    author = facts["author"]
    latest: dict[int, dict] = {}
    for review in facts["reviews"]:
        reviewer = review["reviewer"]
        if reviewer is None or review["state"] not in _APPROVAL_STATES:
            continue
        current = latest.get(reviewer["id"])
        if current is None or review["id"] > current["id"]:
            latest[reviewer["id"]] = review
    logins = []
    for review in latest.values():
        reviewer = review["reviewer"]
        if (
            review["state"] == "APPROVED"
            and review["commit_id"] == facts["head_sha"]
            and reviewer["type"] == "User"
            and reviewer["id"] != author["id"]
            and reviewer["login"].casefold() != author["login"].casefold()
        ):
            logins.append(reviewer["login"])
    return sorted(logins)


def _binding_findings(facts: dict) -> list[dict[str, object]]:
    """Every check entry that names a commit must name the head commit."""
    head = facts["head_sha"]
    for check in facts["required_checks"]:
        for sha in (check["check_run_head_sha"], check["commit_status_sha"]):
            if sha is not None and sha != head:
                return [
                    _finding(
                        "github.facts_binding",
                        "The GitHub facts mix results from different commits.",
                    )
                ]
    return []


def _url_findings(proof: dict, facts: dict) -> list[dict[str, object]]:
    """Require the claimed URLs to equal the canonical URLs built from the facts.

    ``pr_url`` must equal ``https://github.com/{repository}/pull/{number}`` and
    GitHub's own ``html_url``. ``ci_run_url`` must equal
    ``https://github.com/{repository}/actions/runs/{id}`` for the workflow run of
    at least one judged required check. Nothing else is derived from either URL.
    """
    findings = []
    repository = facts["repository"]
    canonical_pull = f"https://github.com/{repository}/pull/{facts['pull_request_number']}"
    if proof.get("pr_url") != canonical_pull or facts["html_url"] != canonical_pull:
        findings.append(
            _finding(
                "github.pr_url",
                f"pr_url must be exactly {canonical_pull}, the pull request GitHub reports.",
            )
        )
    run_urls = {
        f"https://github.com/{repository}/actions/runs/{check['workflow_run_id']}"
        for check in facts["required_checks"]
        if check["workflow_run_id"] is not None
    }
    if proof.get("ci_run_url") not in run_urls:
        findings.append(
            _finding(
                "github.ci_run",
                "ci_run_url must be https://github.com/<repository>/actions/runs/<id> for a "
                "workflow run that produced a required check on the head commit.",
            )
        )
    return findings


def _integrity_findings(facts: dict, settings: dict) -> list[dict[str, object]]:
    """Integrity rules of owner decision 20."""
    findings = []
    if not settings["allow_unbound"]:
        for check in facts["required_checks"]:
            if not check["app_bound"]:
                findings.append(
                    _finding(
                        "github.unbound_required_check",
                        f"Required check {_display(check['name'])} accepts a result from "
                        "any source; it must be bound to the App that produces it.",
                    )
                )
    protected = protected_changes(facts["changed_files"], settings["protected_paths"])
    if protected:
        listed = ", ".join(_display(path) for path in protected[:_MAX_LISTED_PATHS])
        more = len(protected) - _MAX_LISTED_PATHS
        suffix = f" and {more} more" if more > 0 else ""
        findings.append(
            _finding(
                "github.protected_path_changed",
                f"The pull request changes CI or repository configuration ({listed}{suffix}); "
                "it requires explicit human acceptance and cannot be auto-accepted.",
            )
        )
    approvals = qualifying_approvals(facts)
    if len(approvals) < settings["required_approvals"]:
        findings.append(
            _finding(
                "github.independent_approval_missing",
                f"The head commit needs {settings['required_approvals']} approval(s) from "
                "reviewers who are neither the author nor a bot; "
                f"GitHub shows {len(approvals)}.",
            )
        )
    if approvals and all(login.casefold() in settings["operators"] for login in approvals):
        findings.append(
            {
                **_finding(
                    "operator_approved",
                    "Only operator accounts approved this work. It may earn points but may "
                    "not be paid in money until an independent reviewer confirms it.",
                    level="warning",
                ),
                "code": OPERATOR_APPROVED_CODE,
            }
        )
    return findings


def compare_github_facts(
    proof: dict, configuration: object, input_value: object
) -> list[dict[str, object]]:
    """Compare proof claims with WorkStream-read GitHub facts; one finding per mismatch."""
    settings = github_configuration(configuration)
    if settings is None:
        return [
            _finding(
                "github.configuration",
                "The checker configuration must name github_repository and base_branch, "
                "with only supported integrity options.",
            )
        ]
    facts = input_value.get(GITHUB_FACTS_INPUT_KEY) if isinstance(input_value, dict) else None
    if facts is None:
        return [
            _finding(
                "github.facts_missing",
                "GitHub facts are required for this check but were not provided.",
            )
        ]
    if not valid_facts(facts):
        return [_finding("github.facts_invalid", "The provided GitHub facts are malformed.")]
    binding = _binding_findings(facts)
    if binding:
        return binding
    findings = []
    repository = facts["repository"]
    if repository.casefold() != settings["repository"].casefold():
        findings.append(
            _finding(
                "github.repository",
                f"The pull request belongs to {_display(repository)}, "
                f"not {_display(settings['repository'])}.",
            )
        )
    if facts["base_ref"] != settings["base_branch"]:
        findings.append(
            _finding(
                "github.base_branch",
                f"The pull request targets {_display(facts['base_ref'])}, "
                f"not {_display(settings['base_branch'])}.",
            )
        )
    findings.extend(_url_findings(proof, facts))
    if facts["merged"] is not True:
        findings.append(
            _finding("github.merged", "GitHub reports that the pull request is not merged.")
        )
    commit_sha = proof.get("commit_sha")
    if not isinstance(commit_sha, str) or facts["merge_commit_sha"] != commit_sha.lower():
        findings.append(
            _finding(
                "github.merge_commit_sha",
                "commit_sha does not equal the pull request's merge commit on GitHub.",
            )
        )
    for check in facts["required_checks"]:
        if check["conclusion"] != "success":
            findings.append(
                _finding(
                    "github.required_check",
                    f"Required check {_display(check['name'])} is "
                    f"{_display(check['conclusion'])}, not success, "
                    "for the pull request head commit.",
                )
            )
    findings.extend(_integrity_findings(facts, settings))
    return findings


def read_proof(input_root: Path) -> bytes | None:
    """Read at most one byte past the limit from a regular, non-linked proof file."""
    try:
        descriptor = os.open(input_root / PROOF_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    # Check the type before wrapping: ``fdopen`` raises for a directory, and a
    # contributor-controlled archive must yield a finding, not a crash.
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        return None
    with os.fdopen(descriptor, "rb") as handle:
        return handle.read(MAX_PROOF_BYTES + 1)


def _canonical(value: object) -> str:
    """Match the backend canonical JSON for the string/int/bool/null result body."""
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def build_result(request: dict, findings: list[dict[str, object]]) -> dict[str, object]:
    """Bind a completed verdict to the exact request; failed iff an error exists."""
    has_error = any(item["level"] == "error" for item in findings)
    body = {
        "schema_version": "external_checker_result.v1",
        "request_digest": request["request_digest"],
        "registry_entry_id": request["registry"]["registry_entry_id"],
        "registry_entry_digest": request["registry"]["entry_digest"],
        "phase": request["identity"]["phase"],
        "outcome": "completed",
        "verdict": "failed" if has_error else "passed",
        "findings": findings,
        "infrastructure_failure_code": None,
    }
    digest = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    return {**body, "result_digest": f"sha256:{digest}"}


def main() -> int:
    request = json.load(sys.stdin)
    findings = evaluate_proof(
        read_proof(Path("/work/input")),
        configuration=request.get("configuration"),
        input_value=request.get("input"),
    )
    result = build_result(request, findings)
    sys.stdout.write(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
