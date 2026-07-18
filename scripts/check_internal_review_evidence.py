"""Require internal reviewer evidence for engineering-loop and code changes."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_POST_REVIEW_PREFIXES = (
    ".agent-loop/initiatives/",
    "docs/internal_reviews/",
)
ALLOWED_POST_REVIEW_EXACT_PATHS = {
    ".agent-loop/LOOP_STATE.md",
}
RELEVANT_PREFIXES = (
    ".agent-loop/",
    ".agents/",
    ".codex/",
    ".github/",
    ".github/workflows/",
    "AGENTS.md",
    "README.md",
    "backend/alembic/",
    "backend/app/",
    "backend/tests/",
    "docs/",
    "scripts/",
)
RELEVANT_EXACT_PATHS = {
    "backend/alembic.ini",
    "backend/pyproject.toml",
}
IGNORED_PREFIXES = (
    "docs/internal_reviews/",
    "docs/diagrams/rendered/",
)
BASE_REQUIRED_TRACKS = (
    "senior engineering",
    "qa/test",
    "security/auth",
    "product/ops",
)
KNOWN_REVIEWER_TRACKS = BASE_REQUIRED_TRACKS + (
    "architecture",
    "ci integrity",
    "docs",
    "reuse/dedup",
    "test delta",
)
REQUIRED_STATEMENTS = {
    "open sub-agent sessions": "none",
    "valid findings addressed": "yes",
}
ACTIVE_CHUNK_ENV = "INTERNAL_REVIEW_CHUNK_ID"
CHUNK_ID_PATTERN = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){3,}"
CHUNK_HEADING_PATTERNS = (
    re.compile(
        rf"^# (?:Chunk Contract|Parent Chunk):\s+(?P<chunk>{CHUNK_ID_PATTERN})(?=\s|$)"
    ),
    re.compile(rf"^# (?P<chunk>{CHUNK_ID_PATTERN}):(?=\s|$)"),
)
CHUNK_REFERENCE_PATTERN = re.compile(
    rf"(?<![A-Z0-9-])(?P<chunk>{CHUNK_ID_PATTERN})(?![A-Z0-9-])",
    re.IGNORECASE,
)
REVIEWED_SHA_PATTERN = re.compile(
    r"^reviewed code sha:\s*`?([0-9a-f]{40})`?$", re.IGNORECASE | re.MULTILINE
)
PROVENANCE_VALUE_PATTERN = re.compile(
    r"^(reviewed at|reviewer run ids):[ \t]*(.+)$", re.IGNORECASE | re.MULTILINE
)
UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}(?:\.\d+)?z$")
ACCEPTED_BLOCKING_VALUES = {"none", "none remaining", "n/a", "no"}
ACCEPTED_PASS_RESULTS = {"pass", "pass after fixes", "pass with low risks"}
ACCEPTED_NA_RESULT = "n/a - with approved reason"
REQUIRED_PROVENANCE_LABELS = ("reviewed code sha:", "reviewed at:", "reviewer run ids:")
PROVENANCE_PLACEHOLDER_FRAGMENTS = (
    "<",
    ">",
    "utc timestamp",
    "agent ids",
    "ci run ids",
    "local reviewer run references",
)


def git(*args: str) -> str:
    """Run git and return stdout."""
    result = subprocess.run(
        ["git", *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def git_ok(*args: str) -> bool:
    """Return whether a git command succeeds."""
    result = subprocess.run(
        ["git", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode == 0


def resolve_base_ref() -> str:
    """Resolve the base ref used to compare review-relevant changes."""
    base_ref = os.environ.get("INTERNAL_REVIEW_BASE_REF") or os.environ.get(
        "GITHUB_BASE_REF"
    )
    if base_ref:
        candidates = (f"origin/{base_ref}", base_ref)
        for candidate in candidates:
            if git_ok("rev-parse", "--verify", candidate):
                return candidate
        raise RuntimeError(f"could not resolve configured base ref {base_ref!r}")

    for candidate in ("origin/main", "main"):
        if git_ok("rev-parse", "--verify", candidate):
            return candidate
    raise RuntimeError("could not resolve default base ref origin/main or main")


def changed_files() -> list[str]:
    """Return files changed by this PR or local branch."""
    paths: list[str] = []

    def add(output: str) -> None:
        for line in output.splitlines():
            if line and line not in paths:
                paths.append(line)

    base_ref = resolve_base_ref()
    add(git("diff", "--name-only", f"{base_ref}...HEAD"))

    add(git("diff", "--name-only", "--cached"))
    add(git("diff", "--name-only"))
    add(git("ls-files", "--others", "--exclude-standard"))
    return paths


def is_relevant(path: str) -> bool:
    """Return whether a changed path requires internal review evidence."""
    if path.startswith(".agent-loop/initiatives/") and "/reviews/" in path:
        return False
    if path.startswith(IGNORED_PREFIXES):
        return False
    return path.startswith(RELEVANT_PREFIXES) or path in RELEVANT_EXACT_PATHS


def required_tracks_for(paths: list[str]) -> tuple[str, ...]:
    """Return reviewer tracks required for the changed path set."""
    required = list(BASE_REQUIRED_TRACKS)

    def add(track: str) -> None:
        if track not in required:
            required.append(track)

    for path in paths:
        if path.startswith(
            (".agent-loop/", ".agents/", ".codex/", "backend/app/", "backend/alembic/")
        ):
            add("architecture")
        if path.startswith((".github/", "scripts/")) or path in {
            "backend/pyproject.toml",
        }:
            add("ci integrity")
        if (
            path.endswith(".md")
            or path.startswith(("docs/", ".agent-loop/", ".agents/"))
            or path
            in {
                "AGENTS.md",
                "README.md",
            }
        ):
            add("docs")
        if path.startswith(
            (".agents/skills/", ".codex/agents/", "backend/app/", "scripts/")
        ):
            add("reuse/dedup")
        if (
            path.startswith("backend/tests/")
            or "/tests/" in path
            or Path(path).name.startswith("test_")
        ):
            add("test delta")

    return tuple(required)


def is_internal_review_evidence_path(path: str) -> bool:
    """Return whether path is an internal reviewer evidence file."""
    return (
        path.startswith(".agent-loop/initiatives/")
        and "/reviews/" in path
        and path.endswith("-internal-review-evidence.md")
    )


def reviewer_rows(text: str) -> dict[str, tuple[str, str, str]]:
    """Return reviewer table rows keyed by reviewer name."""
    rows: dict[str, tuple[str, str, str]] = {}
    in_reviewer_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            in_reviewer_table = False
            continue
        cells = [cell.strip().lower() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[:3] == ["reviewer", "result", "blocking findings"]:
            in_reviewer_table = True
            continue
        if not in_reviewer_table or "---" in stripped:
            continue
        if cells[0] not in KNOWN_REVIEWER_TRACKS:
            in_reviewer_table = False
            continue
        notes = cells[3] if len(cells) > 3 else ""
        # Evidence addenda are newest-first, matching reviewed_sha() and
        # provenance_value(). Preserve the first authoritative result for each
        # track instead of letting an older table below overwrite it.
        rows.setdefault(cells[0], (cells[1], cells[2], notes))
    return rows


def normalize_result(result: str) -> str:
    """Normalize a reviewer result token for exact comparison."""
    return result.replace("—", "-").replace("–", "-").strip().lower()


def validate_reviewer_rows(text: str, required_tracks: tuple[str, ...]) -> list[str]:
    """Validate reviewer result rows for required tracks."""
    rows = reviewer_rows(text)
    missing: list[str] = []
    allowed_results = ACCEPTED_PASS_RESULTS | {ACCEPTED_NA_RESULT}
    for track, (result, _blocking, notes) in rows.items():
        normalized = normalize_result(result)
        if normalized not in allowed_results:
            missing.append(
                f"{track} reviewer result must be one of: "
                f"{', '.join(sorted(allowed_results))}"
            )
        if normalized == ACCEPTED_NA_RESULT and not provenance_text_value(notes):
            missing.append(f"{track} n/a result requires notes")
    for track in required_tracks:
        row = rows.get(track)
        if row is None:
            missing.append(f"reviewer result row: {track}")
            continue
        result, blocking, notes = row
        normalized = normalize_result(result)
        if normalized in ACCEPTED_PASS_RESULTS:
            pass
        elif normalized == ACCEPTED_NA_RESULT:
            missing.append(f"{track} reviewer result cannot be n/a when required")
        if blocking not in ACCEPTED_BLOCKING_VALUES:
            missing.append(f"{track} blocking findings must be none")
    return missing


def reviewed_sha(text: str) -> str | None:
    """Return the reviewed code SHA recorded in evidence text."""
    match = REVIEWED_SHA_PATTERN.search(text)
    if match:
        return match.group(1).lower()
    return None


def provenance_value(text: str, label: str) -> str:
    """Return a non-empty provenance value by label."""
    for match in PROVENANCE_VALUE_PATTERN.finditer(text):
        if match.group(1).lower() == label:
            value = provenance_text_value(match.group(2))
            if label == "reviewed at" and not is_utc_timestamp(value):
                return ""
            if value:
                return value
    return ""


def provenance_text_value(value: str) -> str:
    """Return a non-placeholder provenance value."""
    cleaned = value.strip().strip("`")
    normalized = cleaned.lower()
    if not cleaned or normalized in {"-", "n/a", "none", "pending"}:
        return ""
    if any(fragment in normalized for fragment in PROVENANCE_PLACEHOLDER_FRAGMENTS):
        return ""
    return cleaned


def is_utc_timestamp(value: str) -> bool:
    """Return whether value is a concrete UTC timestamp."""
    if not UTC_TIMESTAMP_PATTERN.match(value.lower()):
        return False
    try:
        datetime.fromisoformat(value.lower().replace("z", "+00:00"))
    except ValueError:
        return False
    return True


def review_target_sha() -> str:
    """Return the PR head SHA when available, otherwise local HEAD."""
    for key in ("INTERNAL_REVIEW_HEAD_SHA", "PR_HEAD_SHA", "GITHUB_HEAD_SHA"):
        value = os.environ.get(key, "").strip().lower()
        if value:
            return value
    return git("rev-parse", "HEAD").lower()


def dirty_after_review_paths() -> list[str]:
    """Return staged, unstaged, and untracked paths not committed after review."""
    paths: list[str] = []

    def add(output: str) -> None:
        for path in output.splitlines():
            if path and path not in paths:
                paths.append(path)

    add(git("diff", "--name-only", "--cached"))
    add(git("diff", "--name-only"))
    add(git("ls-files", "--others", "--exclude-standard"))
    return paths


def is_allowed_after_review_path(path: str) -> bool:
    """Return whether a path may change after the reviewed SHA."""
    if path in ALLOWED_POST_REVIEW_EXACT_PATHS:
        return True
    if path.startswith("docs/internal_reviews/"):
        return True
    if path.startswith(ALLOWED_POST_REVIEW_PREFIXES) and (
        "/reviews/" in path or path.endswith("/STATUS.md")
    ):
        return True
    return False


def validate_reviewed_revision(text: str) -> list[str]:
    """Validate that evidence is bound to the current reviewed revision."""
    missing: list[str] = []
    if "reviewed code sha:" not in text:
        missing.append("reviewed code sha")
    if not provenance_value(text, "reviewed at"):
        missing.append("reviewed at")
    if not provenance_value(text, "reviewer run ids"):
        missing.append("reviewer run ids")

    sha = reviewed_sha(text)
    if sha is None:
        missing.append("reviewed code sha: <40-character sha>")
        return missing
    if not git_ok("rev-parse", "--verify", f"{sha}^{{commit}}"):
        missing.append(f"reviewed code sha does not resolve: {sha}")
        return missing

    target_sha = review_target_sha()
    if not git_ok("rev-parse", "--verify", f"{target_sha}^{{commit}}"):
        missing.append(f"review target sha does not resolve: {target_sha}")
        return missing

    changed_after_review = git(
        "diff", "--name-only", f"{sha}..{target_sha}"
    ).splitlines()
    changed_after_review.extend(dirty_after_review_paths())
    invalid = [
        path for path in changed_after_review if not is_allowed_after_review_path(path)
    ]
    if invalid:
        missing.append(
            "reviewed code sha is stale; non-evidence files changed after review: "
            + ", ".join(invalid[:20])
        )
    return missing


def validate_evidence(
    path: Path,
    required_tracks: tuple[str, ...],
    chunk_ids: list[str] | None = None,
    enforce_reviewed_revision: bool = True,
) -> list[str]:
    """Validate one internal review evidence file."""
    text = path.read_text(encoding="utf-8").lower()
    missing = [track for track in required_tracks if track not in text]
    chunk_ids = (
        list(chunk_ids)
        if chunk_ids is not None
        else required_chunk_ids(changed_files())
    )
    env_chunk_id = os.environ.get(ACTIVE_CHUNK_ENV, "").strip().lower()
    if env_chunk_id:
        chunk_ids.append(env_chunk_id)
    referenced_chunk_ids = evidence_chunk_ids(text)
    if chunk_ids and referenced_chunk_ids.isdisjoint(chunk_ids):
        missing.append(f"chunk id: one of {', '.join(chunk_ids)}")
    for label, expected_value in REQUIRED_STATEMENTS.items():
        if f"{label}: {expected_value}" not in text:
            missing.append(f"{label}: {expected_value}")
    missing.extend(validate_reviewer_rows(text, required_tracks))
    if enforce_reviewed_revision:
        missing.extend(validate_reviewed_revision(text))
    return missing


def required_chunk_ids(paths: list[str]) -> list[str]:
    """Return chunk IDs from changed chunk-contract paths."""
    chunk_ids: list[str] = []
    for path in paths:
        if "/chunks/" not in path or not path.endswith(".md"):
            continue
        contract_path = ROOT / path
        try:
            if os.path.lexists(contract_path):
                if contract_path.is_symlink() or not contract_path.is_file():
                    raise RuntimeError("changed chunk contract is not a regular file")
                text = contract_path.read_text(encoding="utf-8")
            else:
                text = historical_contract_text(path)
            heading = text.splitlines()[0]
        except (IndexError, OSError, UnicodeDecodeError, RuntimeError) as exc:
            raise RuntimeError(f"cannot read changed chunk contract {path}") from exc
        chunk_id = chunk_id_from_heading(heading)
        if chunk_id is None:
            raise RuntimeError(
                f"changed chunk contract has no canonical heading: {path}"
            )
        if chunk_id not in chunk_ids:
            chunk_ids.append(chunk_id)
    return chunk_ids


def historical_contract_text(path: str) -> str:
    """Recover a deleted contract from index, HEAD, or the review base."""
    base_ref = resolve_base_ref()
    object_names = (f":{path}", f"HEAD:{path}", f"{base_ref}:{path}")
    for object_name in object_names:
        result = subprocess.run(
            ["git", "show", object_name],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            return result.stdout
    raise RuntimeError(f"deleted contract has no recoverable provenance: {path}")


def chunk_id_from_heading(heading: str) -> str | None:
    """Return the exact chunk ID from a canonical contract heading."""
    for pattern in CHUNK_HEADING_PATTERNS:
        match = pattern.match(heading)
        if match:
            return match.group("chunk").lower()
    return None


def evidence_chunk_ids(text: str) -> set[str]:
    """Return exact normalized lifecycle IDs referenced by evidence text."""
    return {
        match.group("chunk").lower() for match in CHUNK_REFERENCE_PATTERN.finditer(text)
    }


def main() -> int:
    """Check that changed engineering files include complete review evidence."""
    try:
        changed = changed_files()
    except RuntimeError as exc:
        print(f"Internal review evidence gate failed closed: {exc}", file=sys.stderr)
        return 1
    relevant = [path for path in changed if is_relevant(path)]
    if not relevant:
        print("No internal review evidence required for this change.")
        return 0
    required_tracks = required_tracks_for(relevant)

    evidence_paths = []
    for path in changed:
        if not path.endswith(".md"):
            continue
        if is_internal_review_evidence_path(path):
            evidence_paths.append(Path(path))

    if not evidence_paths:
        print(
            "Internal review evidence is required for engineering-loop, process, "
            "or implementation changes.\n"
            "Add a changed .agent-loop/initiatives/<initiative>/reviews/"
            "*-internal-review-evidence.md file with these "
            f"reviewer tracks before opening the PR: {', '.join(required_tracks)}.",
            file=sys.stderr,
        )
        return 1

    failures: list[str] = []
    try:
        chunk_ids = required_chunk_ids(changed)
    except RuntimeError as exc:
        print(f"Internal review evidence gate failed closed: {exc}", file=sys.stderr)
        return 1
    for path in evidence_paths:
        if not path.is_file():
            failures.append(
                f"{path}: missing evidence file in HEAD (deleted or renamed)"
            )
            continue
        try:
            missing = validate_evidence(path, required_tracks, chunk_ids)
        except (OSError, UnicodeDecodeError) as exc:
            failures.append(
                f"{path}: unreadable evidence file ({exc.__class__.__name__})"
            )
            continue
        if missing:
            failures.append(f"{path}: missing {', '.join(missing)}")

    if failures:
        print("Internal review evidence is incomplete:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Internal review evidence gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
