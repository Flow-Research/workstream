"""Networkless Harnessy work-proof checker for post-submission evaluation.

The checker reads one ``external_checker_request.v1`` envelope on stdin and the
verified, read-only Submission material under ``/work/input``. It compares the
claims in ``proof.json`` with ``workstream.forge_change_facts.v1`` facts that
WorkStream read from the git host ("forge"; GitHub today) and placed in the
request input under ``forge_facts``, and writes one
``external_checker_result.v1`` envelope.

There is one mode and it fails closed (owner decisions 20 and 21): the binding
configuration must select the facts version and name the forge, the forge
instance origin, repository and base branch, and the facts must be present and
well formed. Otherwise the verdict is ``failed``. A proof is never passed on
its own claims. The checker never uses the network or a credential, parses no
URL and builds no forge URL: claimed URLs must equal URLs the facts report.

Integrity rules: every required check must be bound to a producer and every
judged result must come from it; a change to CI or repository configuration
paths needs explicit human acceptance; the head commit needs an independent
approval (each reviewer's latest decisive review by list position, from a
``user`` account with write access that is not the author); every
judged result that names a commit must name the head commit; and approval only
by configured operators adds a non-blocking ``harnessy.operator_approved``
warning.
"""

from __future__ import annotations

from datetime import datetime
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
FORGE_FACTS_INPUT_KEY = "forge_facts"
FORGE_FACTS_SCHEMA = "workstream.forge_change_facts.v1"
FORGE_FACTS_VERSION = "v1"
SUPPORTED_FORGES = frozenset({"github"})
DEFAULT_PROTECTED_PATHS = (
    ".github/**",
    "**/CODEOWNERS",
    ".gitlab-ci.yml",
    ".gitlab/**",
    ".circleci/**",
    ".forgejo/**",
    ".gitea/**",
    ".woodpecker/**",
    ".woodpecker.yml",
    ".woodpecker.yaml",
)
DEFAULT_REQUIRED_INDEPENDENT_APPROVALS = 1
OPERATOR_APPROVED_CODE = "harnessy.operator_approved"
_COMMIT_SHA = re.compile(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")
_LOWER_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_RESPONSE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_FORGE_ORIGIN = re.compile(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?")
_REPOSITORY_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
_MAX_REPOSITORY_CHARACTERS = 255
_MAX_REVIEW_ID_CHARACTERS = 100
_RFC3339 = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?"
    r"(?:[Zz]|[+-][0-9]{2}:[0-9]{2})"
)
_DECISIVE_STATES = frozenset({"approved", "changes_requested", "dismissed"})
_REVIEW_STATES = _DECISIVE_STATES | {"commented", "pending", "other"}
_ACTOR_KINDS = frozenset({"user", "bot", "other"})
_CHECK_CONCLUSIONS = frozenset(
    {
        "success",
        "failure",
        "neutral",
        "cancelled",
        "skipped",
        "timed_out",
        "action_required",
        "stale",
        "error",
        "pending",
        "missing",
    }
)
_MAX_CHECK_NAME_CHARACTERS = 200
_MAX_LISTED_PATHS = 5
_CONFIGURATION_KEYS = frozenset(
    {
        "workstream_forge_facts_version",
        "forge",
        "forge_origin",
        "repository",
        "base_branch",
        "allow_unbound_required_checks",
        "protected_paths",
        "required_independent_approvals",
        "operator_logins",
    }
)
_FACTS_KEYS = frozenset(
    {
        "schema_version",
        "forge",
        "forge_origin",
        "repository",
        "change_number",
        "change_url",
        "state",
        "merged",
        "landed_commit_sha",
        "base_ref",
        "head_sha",
        "author",
        "reviews",
        "changed_files_count",
        "changed_files",
        "required_checks",
        "fetched_at",
        "responses",
    }
)
_ACTOR_KEYS = frozenset({"login", "id", "kind"})
_REVIEW_KEYS = frozenset(
    {"id", "reviewer", "reviewer_write_access", "state", "commit_id", "submitted_at"}
)
_CHANGED_FILE_KEYS = frozenset({"path", "previous_path", "status"})
_CHECK_KEYS = frozenset({"name", "conclusion", "required_producer", "judged", "run_url"})
_JUDGED_KEYS = frozenset({"producer", "sha"})
_RESPONSE_KEYS = frozenset({"request", "sha256"})


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
    """Return findings for one proof; it passes only when it matches the forge facts."""
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
    return claim_findings(proof) + compare_forge_facts(proof, configuration, input_value)


def claim_findings(proof: dict) -> list[dict[str, object]]:
    """Check the claims that need no facts; URLs are checked against the facts."""
    findings = []
    if proof.get("schema") != PROOF_SCHEMA:
        findings.append(_finding("schema", f"schema must be {PROOF_SCHEMA!r}."))
    commit_sha = proof.get("commit_sha")
    if not isinstance(commit_sha, str) or _COMMIT_SHA.fullmatch(commit_sha) is None:
        findings.append(
            _finding("commit_sha", "commit_sha must be 40 or 64 hexadecimal characters.")
        )
    if proof.get("ci_conclusion") != "success":
        findings.append(_finding("ci_conclusion", "ci_conclusion must be 'success'."))
    if proof.get("merged") is not True:
        findings.append(_finding("merged", "merged must be the JSON value true."))
    return findings


def _strings(value: object) -> bool:
    """Return whether a value is a list of non-empty strings."""
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _forge_origin(value: object) -> bool:
    """Return whether a value is an https web origin: scheme, host and optional port."""
    return isinstance(value, str) and _FORGE_ORIGIN.fullmatch(value) is not None


def _repository(value: object) -> bool:
    """Return whether a value is a forge-neutral repository path.

    At least two ``/``-joined segments of ``[A-Za-z0-9._-]``, none ``.`` or
    ``..``, at most 255 characters. GitLab subgroups are allowed; a provider
    enforces its own stricter grammar.
    """
    if not isinstance(value, str) or len(value) > _MAX_REPOSITORY_CHARACTERS:
        return False
    segments = value.split("/")
    return len(segments) >= 2 and all(
        _REPOSITORY_SEGMENT.fullmatch(segment) is not None and segment not in (".", "..")
        for segment in segments
    )


def forge_configuration(configuration: object) -> dict | None:
    """Return the normalized configuration, or None when it is absent or invalid.

    Integrity options take safe defaults: unbound required checks are errors,
    the default protected paths apply, and one independent approval is needed.
    """
    if not isinstance(configuration, dict):
        return None
    forge = configuration.get("forge")
    forge_origin = configuration.get("forge_origin")
    repository = configuration.get("repository")
    base_branch = configuration.get("base_branch")
    allow_unbound = configuration.get("allow_unbound_required_checks", False)
    protected = configuration.get("protected_paths", [])
    approvals = configuration.get(
        "required_independent_approvals", DEFAULT_REQUIRED_INDEPENDENT_APPROVALS
    )
    operators = configuration.get("operator_logins", [])
    if (
        not set(configuration) <= _CONFIGURATION_KEYS
        or configuration.get("workstream_forge_facts_version") != FORGE_FACTS_VERSION
        or forge not in SUPPORTED_FORGES
        or not _forge_origin(forge_origin)
        or not _repository(repository)
        or not isinstance(base_branch, str)
        or not base_branch
        or not isinstance(allow_unbound, bool)
        or not _strings(protected)
        or type(approvals) is not int
        or approvals < 1
        or not _strings(operators)
    ):
        return None
    return {
        "forge": forge,
        "forge_origin": forge_origin,
        "repository": repository,
        "base_branch": base_branch,
        "allow_unbound": allow_unbound,
        "protected_paths": (*DEFAULT_PROTECTED_PATHS, *protected),
        "required_approvals": approvals,
        "operators": frozenset(login.casefold() for login in operators),
    }


def _record(value: object, keys: frozenset[str]) -> bool:
    """Return whether a value is an object with exactly ``keys``."""
    return isinstance(value, dict) and set(value) == keys


def _positive_int(value: object) -> bool:
    return type(value) is int and value >= 1


def _sha(value: object) -> bool:
    """Return whether a value is a lowercase 40- or 64-character commit id."""
    return isinstance(value, str) and _LOWER_SHA.fullmatch(value) is not None


def _datetime(value: object) -> bool:
    """Return whether a value is an RFC 3339 date-time string."""
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _actor(value: object) -> bool:
    return (
        _record(value, _ACTOR_KEYS)
        and isinstance(value["login"], str)
        and _positive_int(value["id"])
        and value["kind"] in _ACTOR_KINDS
    )


def _review(value: object) -> bool:
    return (
        _record(value, _REVIEW_KEYS)
        # Review ids are opaque: compared for equality only, never ordered.
        and isinstance(value["id"], str)
        and 1 <= len(value["id"]) <= _MAX_REVIEW_ID_CHARACTERS
        and (value["reviewer"] is None or _actor(value["reviewer"]))
        and (
            value["reviewer_write_access"] is None
            or isinstance(value["reviewer_write_access"], bool)
        )
        and value["state"] in _REVIEW_STATES
        and (value["commit_id"] is None or _sha(value["commit_id"]))
        and (value["submitted_at"] is None or _datetime(value["submitted_at"]))
    )


def _changed_file(value: object) -> bool:
    return (
        _record(value, _CHANGED_FILE_KEYS)
        and isinstance(value["path"], str)
        and (value["previous_path"] is None or isinstance(value["previous_path"], str))
        and isinstance(value["status"], str)
    )


def _required_check(value: object) -> bool:
    return (
        _record(value, _CHECK_KEYS)
        and isinstance(value["name"], str)
        and value["conclusion"] in _CHECK_CONCLUSIONS
        and (value["required_producer"] is None or isinstance(value["required_producer"], str))
        and isinstance(value["judged"], list)
        and all(
            _record(judged, _JUDGED_KEYS)
            and (judged["producer"] is None or isinstance(judged["producer"], str))
            and (judged["sha"] is None or _sha(judged["sha"]))
            for judged in value["judged"]
        )
        and (value["run_url"] is None or isinstance(value["run_url"], str))
        # A success must rest on at least one judged result; none is malformed.
        and (value["conclusion"] != "success" or len(value["judged"]) > 0)
    )


def _response(value: object) -> bool:
    return (
        _record(value, _RESPONSE_KEYS)
        and isinstance(value["request"], str)
        and isinstance(value["sha256"], str)
        and _RESPONSE_DIGEST.fullmatch(value["sha256"]) is not None
    )


def valid_facts(facts: object) -> bool:
    """Accept only the exact ``workstream.forge_change_facts.v1`` shape."""
    if not _record(facts, _FACTS_KEYS) or facts["schema_version"] != FORGE_FACTS_SCHEMA:
        return False
    merged = facts["merged"]
    landed_commit_sha = facts["landed_commit_sha"]
    files = facts["changed_files"]
    checks = facts["required_checks"]
    responses = facts["responses"]
    return (
        isinstance(facts["forge"], str)
        and _forge_origin(facts["forge_origin"])
        and _repository(facts["repository"])
        and _positive_int(facts["change_number"])
        and isinstance(facts["change_url"], str)
        and facts["state"] in ("open", "closed")
        and isinstance(merged, bool)
        # merged <=> a landed commit is reported; merged => closed.
        and (_sha(landed_commit_sha) if merged else landed_commit_sha is None)
        and (not merged or facts["state"] == "closed")
        and isinstance(facts["base_ref"], str)
        and _sha(facts["head_sha"])
        and _actor(facts["author"])
        and isinstance(facts["reviews"], list)
        and all(_review(review) for review in facts["reviews"])
        and isinstance(files, list)
        and type(facts["changed_files_count"]) is int
        and facts["changed_files_count"] == len(files)
        and all(_changed_file(item) for item in files)
        and isinstance(checks, list)
        and len(checks) > 0
        and all(_required_check(check) for check in checks)
        and _datetime(facts["fetched_at"])
        and isinstance(responses, list)
        and len(responses) > 0
        and all(_response(item) for item in responses)
    )


def _display(value: str) -> str:
    """Bound a forge-provided name for a contributor-visible message."""
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
        for path in (item["previous_path"], item["path"]):
            if path and any(regex.fullmatch(path) for regex in compiled):
                matched.append(path)
    return sorted(set(matched))


def qualifying_approvals(facts: dict) -> list[str]:
    """Return logins whose latest decisive review approves the head commit.

    Reviews are listed oldest first. Each reviewer's last ``approved``,
    ``changes_requested`` or ``dismissed`` review by list position decides;
    other states do not, and review ids are never ordered. The approval must
    name the head SHA and come from a ``user`` account that is not the change
    author and that the forge proves has write access. A review the forge cannot
    bind to a commit (``commit_id`` null) or whose reviewer's write access it
    cannot prove (``reviewer_write_access`` null) never approves.
    """
    author = facts["author"]
    latest: dict[int, dict] = {}
    for review in facts["reviews"]:
        reviewer = review["reviewer"]
        if reviewer is not None and review["state"] in _DECISIVE_STATES:
            latest[reviewer["id"]] = review
    logins = []
    for review in latest.values():
        reviewer = review["reviewer"]
        if (
            review["state"] == "approved"
            and review["commit_id"] == facts["head_sha"]
            and reviewer["kind"] == "user"
            and review["reviewer_write_access"] is True
            and reviewer["id"] != author["id"]
            and reviewer["login"].casefold() != author["login"].casefold()
        ):
            logins.append(reviewer["login"])
    return sorted(logins)


def _binding_findings(facts: dict) -> list[dict[str, object]]:
    """Every judged result that names a commit must name the head commit."""
    head = facts["head_sha"]
    for check in facts["required_checks"]:
        for judged in check["judged"]:
            if judged["sha"] is not None and judged["sha"] != head:
                return [
                    _finding(
                        "forge.facts_binding",
                        "The forge facts mix results from different commits.",
                    )
                ]
    return []


def _url_findings(proof: dict, facts: dict) -> list[dict[str, object]]:
    """Require the claimed URLs to equal URLs the forge facts report, exactly.

    ``pr_url`` must equal ``change_url``; ``ci_run_url`` must equal the
    ``run_url`` of at least one required check. Nothing is parsed or built.
    """
    findings = []
    if proof.get("pr_url") != facts["change_url"]:
        findings.append(
            _finding(
                "forge.change_url",
                f"pr_url must be exactly {_display(facts['change_url'])}, "
                "the change URL the forge reports.",
            )
        )
    run_urls = {
        check["run_url"] for check in facts["required_checks"] if check["run_url"] is not None
    }
    if proof.get("ci_run_url") not in run_urls:
        findings.append(
            _finding(
                "forge.ci_run",
                "ci_run_url must be exactly the forge's URL of a CI run that produced "
                "a required check result on the head commit.",
            )
        )
    return findings


def _producer_findings(facts: dict, settings: dict) -> list[dict[str, object]]:
    """Each required check must be bound to a producer, and every result must come from it."""
    findings = []
    for check in facts["required_checks"]:
        name = _display(check["name"])
        producer = check["required_producer"]
        if producer is None:
            if not settings["allow_unbound"]:
                findings.append(
                    _finding(
                        "forge.unbound_required_check",
                        f"Required check {name} accepts a result from any source; it must "
                        "be bound to the producer that runs it.",
                    )
                )
        elif any(judged["producer"] != producer for judged in check["judged"]):
            findings.append(
                _finding(
                    "forge.producer_mismatch",
                    f"Required check {name} has a result from a producer other than "
                    f"{_display(producer)}, the producer its requirement is bound to.",
                )
            )
    return findings


def _integrity_findings(facts: dict, settings: dict) -> list[dict[str, object]]:
    """Integrity rules of owner decision 20."""
    findings = _producer_findings(facts, settings)
    protected = protected_changes(facts["changed_files"], settings["protected_paths"])
    if protected:
        listed = ", ".join(_display(path) for path in protected[:_MAX_LISTED_PATHS])
        more = len(protected) - _MAX_LISTED_PATHS
        suffix = f" and {more} more" if more > 0 else ""
        findings.append(
            _finding(
                "forge.protected_path_changed",
                f"The change modifies CI or repository configuration ({listed}{suffix}); "
                "it requires explicit human acceptance and cannot be auto-accepted.",
            )
        )
    approvals = qualifying_approvals(facts)
    if len(approvals) < settings["required_approvals"]:
        findings.append(
            _finding(
                "forge.independent_approval_missing",
                f"The head commit needs {settings['required_approvals']} approval(s) from "
                "reviewers with write access who are neither the author nor a bot; "
                f"the forge shows {len(approvals)}.",
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


def compare_forge_facts(
    proof: dict, configuration: object, input_value: object
) -> list[dict[str, object]]:
    """Compare proof claims with WorkStream-read forge facts; one finding per mismatch."""
    settings = forge_configuration(configuration)
    if settings is None:
        return [
            _finding(
                "forge.configuration",
                "The checker configuration must set workstream_forge_facts_version to "
                f"{FORGE_FACTS_VERSION!r} and name a supported forge, its forge_origin, "
                "the repository and base_branch, with only supported integrity options.",
            )
        ]
    facts = input_value.get(FORGE_FACTS_INPUT_KEY) if isinstance(input_value, dict) else None
    if facts is None:
        return [
            _finding(
                "forge.facts_missing",
                f"proof.json pr_url must name a change in {_display(settings['repository'])} "
                f"on {_display(settings['forge_origin'])}; WorkStream could not read facts "
                "for this proof.",
            )
        ]
    if not valid_facts(facts):
        return [_finding("forge.facts_invalid", "The provided forge facts are malformed.")]
    binding = _binding_findings(facts)
    if binding:
        return binding
    findings = []
    repository = facts["repository"]
    if (
        facts["forge"] != settings["forge"]
        or facts["forge_origin"] != settings["forge_origin"]
        or repository.casefold() != settings["repository"].casefold()
    ):
        findings.append(
            _finding(
                "forge.repository",
                f"The change belongs to {_display(repository)} on "
                f"{_display(facts['forge'])} {_display(facts['forge_origin'])}, not "
                f"{_display(settings['repository'])} on {settings['forge']} "
                f"{_display(settings['forge_origin'])}.",
            )
        )
    if facts["base_ref"] != settings["base_branch"]:
        findings.append(
            _finding(
                "forge.base_branch",
                f"The change targets {_display(facts['base_ref'])}, "
                f"not {_display(settings['base_branch'])}.",
            )
        )
    findings.extend(_url_findings(proof, facts))
    if facts["merged"] is not True:
        findings.append(
            _finding("forge.merged", "The forge reports that the change is not merged.")
        )
    commit_sha = proof.get("commit_sha")
    if not isinstance(commit_sha, str) or facts["landed_commit_sha"] != commit_sha.lower():
        findings.append(
            _finding(
                "forge.landed_commit_sha",
                "commit_sha does not equal the commit the change landed as on the base "
                "branch, as the forge reports it.",
            )
        )
    for check in facts["required_checks"]:
        if check["conclusion"] != "success":
            findings.append(
                _finding(
                    "forge.required_check",
                    f"Required check {_display(check['name'])} is "
                    f"{check['conclusion']}, not success, for the change's head commit.",
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
