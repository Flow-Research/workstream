#!/usr/bin/env python3
"""Reject temporal merge wording from active engineering-state projections."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPORAL_OUTCOME = re.compile(r"\bon\s+merge\b", re.IGNORECASE)


def projection_paths(root: Path = ROOT) -> list[Path]:
    """Return current state plus every initiative status and chunk map."""
    paths = [root / ".agent-loop" / "CURRENT_STATE.md"]
    initiative_root = root / ".agent-loop" / "initiatives"
    for filename in ("STATUS.md", "CHUNK_MAP.md"):
        paths.extend(sorted(initiative_root.glob(f"*/{filename}")))
    return paths


def temporal_projection_failures(root: Path = ROOT) -> list[str]:
    """Return deterministic failures for temporal wording in active ledgers."""
    failures: list[str] = []
    for path in projection_paths(root):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if TEMPORAL_OUTCOME.search(line):
                failures.append(
                    f"ACTIVE_STATE_TEMPORAL_PROJECTION: {relative}:{line_number}"
                )
    return failures


def main() -> int:
    failures = temporal_projection_failures()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Active state projection check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
