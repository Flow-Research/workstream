"""Require internal reviewer evidence when PRs change Workstream contracts."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

RELEVANT_PREFIXES = (
    ".agent-loop/",
    ".agents/",
    ".codex/",
    ".github/",
    ".github/workflows/",
    "AGENTS.md",
    "README.md",
    "backend/app/",
    "backend/tests/",
    "docs/",
    "scripts/",
)
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
REQUIRED_STATEMENTS = {
    "open sub-agent sessions": "none",
    "valid findings addressed": "yes",
}
ACTIVE_CHUNK_ENV = "INTERNAL_REVIEW_CHUNK_ID"
CHUNK_FILE_PATTERN = re.compile(r"(?P<chunk>[A-Z]+-[A-Z]+-\d+-\d+)")


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


def changed_files() -> list[str]:
    """Return files changed by this PR or local branch."""
    paths: list[str] = []

    def add(output: str) -> None:
        for line in output.splitlines():
            if line and line not in paths:
                paths.append(line)

    base_ref = os.environ.get("INTERNAL_REVIEW_BASE_REF") or os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        candidates = [f"origin/{base_ref}", base_ref]
        for candidate in candidates:
            try:
                add(git("diff", "--name-only", f"{candidate}...HEAD"))
                break
            except subprocess.CalledProcessError:
                continue
    else:
        for candidate in ("origin/main", "main"):
            if git_ok("rev-parse", "--verify", candidate):
                add(git("diff", "--name-only", f"{candidate}...HEAD"))
                break

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
    return path.startswith(RELEVANT_PREFIXES)


def required_tracks_for(paths: list[str]) -> tuple[str, ...]:
    """Return reviewer tracks required for the changed path set."""
    required = list(BASE_REQUIRED_TRACKS)

    def add(track: str) -> None:
        if track not in required:
            required.append(track)

    for path in paths:
        if path.startswith((".agent-loop/", ".agents/", ".codex/", "backend/app/", "backend/alembic/")):
            add("architecture")
        if path.startswith((".github/", "scripts/")) or path in {
            "backend/pyproject.toml",
            "demos/week1_api_demo_ui/package-lock.json",
            "demos/week1_api_demo_ui/package.json",
        }:
            add("ci integrity")
        if path.endswith(".md") or path.startswith(("docs/", ".agent-loop/", ".agents/")) or path in {
            "AGENTS.md",
            "README.md",
        }:
            add("docs")
        if path.startswith((".agents/skills/", ".codex/agents/", "backend/app/", "scripts/")):
            add("reuse/dedup")
        if path.startswith("backend/tests/") or "/tests/" in path or Path(path).name.startswith("test_"):
            add("test delta")

    return tuple(required)


def validate_evidence(path: Path, required_tracks: tuple[str, ...]) -> list[str]:
    """Validate one internal review evidence file."""
    text = path.read_text(encoding="utf-8").lower()
    missing = [track for track in required_tracks if track not in text]
    chunk_ids = required_chunk_ids(changed_files())
    env_chunk_id = os.environ.get(ACTIVE_CHUNK_ENV, "").strip().lower()
    if env_chunk_id:
        chunk_ids.append(env_chunk_id)
    if chunk_ids and not any(chunk_id in text for chunk_id in chunk_ids):
        missing.append(f"chunk id: one of {', '.join(chunk_ids)}")
    for label, expected_value in REQUIRED_STATEMENTS.items():
        if f"{label}: {expected_value}" not in text:
            missing.append(f"{label}: {expected_value}")
    return missing


def required_chunk_ids(paths: list[str]) -> list[str]:
    """Return chunk IDs from changed chunk-contract paths."""
    chunk_ids: list[str] = []
    for path in paths:
        if "/chunks/" not in path or not path.endswith(".md"):
            continue
        match = CHUNK_FILE_PATTERN.search(Path(path).name)
        if match:
            chunk_id = match.group("chunk").lower()
            if chunk_id not in chunk_ids:
                chunk_ids.append(chunk_id)
    return chunk_ids


def main() -> int:
    """Check that changed contract files include complete review evidence."""
    changed = changed_files()
    relevant = [path for path in changed if is_relevant(path)]
    if not relevant:
        print("No internal review evidence required for this change.")
        return 0
    required_tracks = required_tracks_for(relevant)

    evidence_paths = []
    for path in changed:
        if not path.endswith(".md"):
            continue
        if path.startswith("docs/internal_reviews/"):
            evidence_paths.append(Path(path))
            continue
        if path.startswith(".agent-loop/initiatives/") and "/reviews/" in path:
            evidence_paths.append(Path(path))

    if not evidence_paths:
        print(
            "Internal review evidence is required for Workstream contract changes.\n"
            "Add a changed docs/internal_reviews/*.md file or "
            ".agent-loop/initiatives/<initiative>/reviews/*.md file with these "
            f"reviewer tracks before opening the PR: {', '.join(required_tracks)}.",
            file=sys.stderr,
        )
        return 1

    failures: list[str] = []
    for path in evidence_paths:
        missing = validate_evidence(path, required_tracks)
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
