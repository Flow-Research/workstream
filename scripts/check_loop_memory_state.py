"""Validate merged loop memory is not left in a pre-merge state."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKED_FILES = (
    ".agent-loop/LOOP_STATE.md",
    ".agent-loop/WORK_QUEUE.md",
    ".agent-loop/REVIEW_LOG.md",
)
INITIATIVE_STATUS_FILES = tuple(
    str(path.relative_to(ROOT))
    for path in (ROOT / ".agent-loop/initiatives").glob("*/STATUS.md")
)
FORBIDDEN_PATTERNS = (
    (re.compile(r"PR #\d+ open", re.IGNORECASE), "merged main cannot list an open PR"),
    (
        re.compile(r"awaiting human merge decision", re.IGNORECASE),
        "merged main cannot await a merge decision",
    ),
    (
        re.compile(r"human merge checkpoint", re.IGNORECASE),
        "merged main cannot remain at the human merge checkpoint",
    ),
    (
        re.compile(r"CI ready for final rerun", re.IGNORECASE),
        "merged main cannot wait for final CI rerun",
    ),
    (
        re.compile(r"Push the reviewed revision", re.IGNORECASE),
        "merged main cannot instruct pushing reviewed revision",
    ),
    (
        re.compile(r"CodeRabbit, then stop for the user-owned merge decision", re.IGNORECASE),
        "merged main cannot wait for external review before merge",
    ),
    (
        re.compile(r"\|\s*`[^`]+`\s*\|[^|]+\|[^|]+\|\s*In progress\s*\|", re.IGNORECASE),
        "merged main cannot keep a completed chunk in active In progress state",
    ),
)


def checked_paths() -> list[Path]:
    """Return loop memory paths that must not contain pre-merge state."""
    paths = [ROOT / path for path in CHECKED_FILES]
    paths.extend(ROOT / path for path in INITIATIVE_STATUS_FILES)
    return paths


def main() -> int:
    """Fail when loop memory on main still describes a pre-merge checkpoint."""
    failures: list[str] = []
    for path in checked_paths():
        if not path.exists():
            failures.append(f"{path.relative_to(ROOT)}: missing loop memory file")
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, message in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(ROOT)}: {message}")

    if failures:
        print("Loop memory state is stale:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Loop memory state check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
