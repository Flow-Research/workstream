"""Check local Markdown links in changed Markdown files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def changed_markdown_files() -> list[Path]:
    """Return changed tracked and untracked Markdown files."""
    tracked: list[str] = []
    base_ref = first_existing_ref("origin/main", "main")
    if base_ref:
        tracked.extend(
            subprocess.check_output(
                ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
                text=True,
            ).splitlines()
        )
    tracked.extend(subprocess.check_output(["git", "diff", "--name-only", "--cached"], text=True).splitlines())
    tracked.extend(subprocess.check_output(["git", "diff", "--name-only"], text=True).splitlines())
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"],
        text=True,
    ).splitlines()
    paths: list[str] = []
    for path in tracked + untracked:
        if path.endswith(".md") and path not in paths:
            paths.append(path)
    return [Path(path) for path in paths]


def first_existing_ref(*refs: str) -> str | None:
    """Return the first git ref that exists."""
    for ref in refs:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            return ref
    return None


def local_target(raw_target: str) -> str | None:
    """Return a local link target or None for non-file links."""
    target = raw_target.strip()
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    target = target.split("#", 1)[0]
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return target


def main() -> int:
    """Run the Markdown link check."""
    missing: list[str] = []
    paths = changed_markdown_files()
    for path in paths:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in LINK_PATTERN.finditer(text):
            target = local_target(match.group(1))
            if target is None:
                continue
            if not (path.parent / target).exists():
                missing.append(f"{path}: missing {target}")

    if missing:
        print("Markdown link check failed:", file=sys.stderr)
        for item in missing:
            print(f"- {item}", file=sys.stderr)
        return 1

    print(f"Markdown link check passed for {len(paths)} changed Markdown files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
