"""Check for stale Workstream wording outside explicit allowlisted files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_PATTERNS = (
    re.compile(r"task-production control plane", re.IGNORECASE),
    re.compile(r"garden roadmap", re.IGNORECASE),
    re.compile(r"ApprovedTaskArtifactBinding", re.IGNORECASE),
    re.compile(r"EffectiveTaskSubmissionArtifactPolicy", re.IGNORECASE),
    re.compile(r"EffectiveSubmissionArtifactPolicy", re.IGNORECASE),
    re.compile(r"ProjectPreSubmitCheckerSpec", re.IGNORECASE),
    re.compile(r"task_artifact_binding", re.IGNORECASE),
    re.compile(r"task artifact binding", re.IGNORECASE),
    re.compile(r"effective_task_submission", re.IGNORECASE),
    re.compile(r"effective task submission artifact policy", re.IGNORECASE),
    re.compile(r"effective task policy", re.IGNORECASE),
    re.compile(r"effective_project_policy_hash", re.IGNORECASE),
    re.compile(r"effective project policy hash(?:es)?", re.IGNORECASE),
    re.compile(r"effective policy hash(?:es)?", re.IGNORECASE),
    re.compile(r"locked_task_artifact_binding_id", re.IGNORECASE),
    re.compile(r"locked_effective_task_submission_artifact_policy_hash", re.IGNORECASE),
    re.compile(r"generated task pre-submit", re.IGNORECASE),
    re.compile(r"task-level PreSubmitCheckerPolicy", re.IGNORECASE),
    re.compile(r"task-level pre-submit", re.IGNORECASE),
    re.compile(r"project/task policy", re.IGNORECASE),
    re.compile(r"profile-scoped", re.IGNORECASE),
    re.compile(r"project/profile", re.IGNORECASE),
    re.compile(r"pre-submit checker policy hash(?:es)?", re.IGNORECASE),
    re.compile(r"pre_submit_checker_policy_hash", re.IGNORECASE),
    re.compile(r"project pre-submit checker policy hash(?:es)?", re.IGNORECASE),
    re.compile(r"project checker hash(?:es)?", re.IGNORECASE),
    re.compile(r"PreSubmitCheckerPolicy hash(?:es)?", re.IGNORECASE),
    re.compile(r"PreSubmitCheckerPolicy snapshot/hash(?:es)?", re.IGNORECASE),
)
FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)\.claude(/|$)", re.IGNORECASE),
    re.compile(r"(^|/)claude\.md$", re.IGNORECASE),
)
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "downloads",
    "sheets",
}
SKIP_PREFIXES = (
    "docs/internal_reviews/",
)
SKIP_FILES = {
    "scripts/check_stale_workstream_wording.py",
}
ALLOWLISTED_LINES = {
    "AGENTS.md": ("Do not use old names such as",),
}


def tracked_and_new_files() -> list[Path]:
    """Return tracked and untracked files that should be scanned."""
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"],
        text=True,
    ).splitlines()
    paths = []
    for raw_path in tracked + untracked:
        path = Path(raw_path)
        if (
            raw_path in SKIP_FILES
            or raw_path.startswith(SKIP_PREFIXES)
            or any(part in SKIP_DIRS for part in path.parts)
        ):
            continue
        if path.is_file():
            paths.append(path)
    return paths


def forbidden_path_failures(paths: list[Path]) -> list[str]:
    """Return failures for forbidden tool-specific files or directories."""
    failures: list[str] = []
    for path in paths:
        raw_path = path.as_posix()
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(raw_path):
                failures.append(f"{raw_path}: forbidden Codex-incompatible path /{pattern.pattern}/i")
    return failures


def read_text(path: Path) -> str | None:
    """Read text files and ignore binary or unreadable files."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    allowed_prefixes = ALLOWLISTED_LINES.get(path.as_posix(), ())
    if allowed_prefixes:
        return "\n".join(
            line
            for line in text.splitlines()
            if not any(allowed_prefix in line for allowed_prefix in allowed_prefixes)
        )
    return text


def main() -> int:
    """Run the stale wording check."""
    paths = tracked_and_new_files()
    failures: list[str] = forbidden_path_failures(paths)
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path}: contains stale wording /{pattern.pattern}/i")

    if failures:
        print("Stale wording check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Stale wording check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
