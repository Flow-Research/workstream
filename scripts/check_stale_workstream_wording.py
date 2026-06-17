"""Check for stale Workstream wording outside explicit allowlisted files."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FORBIDDEN = (
    "task-" "production control plane",
    "Garden " "roadmap",
    "Claude " "Code",
    "claude " "code",
    "auto" "merge",
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
SKIP_FILES = {
    "AGENTS.md",
    "scripts/check_stale_workstream_wording.py",
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
        if raw_path in SKIP_FILES or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            paths.append(path)
    return paths


def read_text(path: Path) -> str | None:
    """Read text files and ignore binary or unreadable files."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def main() -> int:
    """Run the stale wording check."""
    failures: list[str] = []
    for path in tracked_and_new_files():
        text = read_text(path)
        if text is None:
            continue
        for term in FORBIDDEN:
            if term in text:
                failures.append(f"{path}: contains stale wording {term!r}")

    if failures:
        print("Stale wording check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Stale wording check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
