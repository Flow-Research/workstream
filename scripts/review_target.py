#!/usr/bin/env python3
"""Emit a deterministic, read-only Git review-target snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from scripts.git_delta import GitCommandError, resolve_commit, resolve_merge_base, run_checked
except ModuleNotFoundError:  # Direct execution initially exposes scripts/, not the repo root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.git_delta import GitCommandError, resolve_commit, resolve_merge_base, run_checked


def _nul_fields(output: str) -> list[str]:
    return [field for field in output.split("\0") if field]


def _worktree_state(repository_root: Path) -> dict[str, object]:
    fields = _nul_fields(
        run_checked(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            repository_root=repository_root,
        )
    )
    staged: set[str] = set()
    unstaged: set[str] = set()
    untracked: set[str] = set()
    index = 0
    while index < len(fields):
        entry = fields[index]
        if len(entry) < 4:
            raise GitCommandError("GIT_INVALID_STATUS", ["git", "status"], entry)
        x, y, path = entry[0], entry[1], entry[3:]
        if x == "?" and y == "?":
            untracked.add(path)
        else:
            if x not in {" ", "?"}:
                staged.add(path)
            if y not in {" ", "?"}:
                unstaged.add(path)
            if x in {"R", "C"}:
                index += 1
                if index >= len(fields):
                    raise GitCommandError("GIT_INVALID_STATUS", ["git", "status"], entry)
        index += 1
    clean = not (staged or unstaged or untracked)
    return {
        "clean": clean,
        "staged": sorted(staged),
        "unstaged": sorted(unstaged),
        "untracked": sorted(untracked),
    }


def _changed_paths(base_sha: str, head_sha: str, repository_root: Path) -> list[dict[str, str]]:
    fields = _nul_fields(
        run_checked(
            ["git", "diff", "--name-status", "-z", f"{base_sha}...{head_sha}"],
            repository_root=repository_root,
        )
    )
    rows: list[dict[str, str]] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if index >= len(fields):
            raise GitCommandError("GIT_INVALID_DIFF", ["git", "diff"], status)
        first_path = fields[index]
        index += 1
        if status.startswith(("R", "C")):
            if index >= len(fields):
                raise GitCommandError("GIT_INVALID_DIFF", ["git", "diff"], status)
            rows.append({"status": status, "old_path": first_path, "path": fields[index]})
            index += 1
        else:
            rows.append({"status": status, "path": first_path})
    return sorted(rows, key=lambda row: (row["path"], row["status"], row.get("old_path", "")))


def inspect_review_target(base: str, head: str, repository_root: Path) -> dict[str, object]:
    """Return one exact target snapshot without mutating repository state."""
    root_output = run_checked(
        ["git", "rev-parse", "--show-toplevel"], repository_root=repository_root
    ).strip()
    if not root_output:
        raise GitCommandError("GIT_EMPTY_REPOSITORY_ROOT", ["git", "rev-parse"])
    root = Path(root_output).resolve()
    base_sha = resolve_commit(base, repository_root=root)
    head_sha = resolve_commit(head, repository_root=root)
    merge_base_sha = resolve_merge_base(base_sha, head_sha, repository_root=root)
    worktree = _worktree_state(root)
    return {
        "schema_version": 1,
        "base_ref": base,
        "base_sha": base_sha,
        "merge_base_sha": merge_base_sha,
        "head_ref": head,
        "head_sha": head_sha,
        "changed_paths": _changed_paths(base_sha, head_sha, root),
        "worktree": worktree,
        "final_ready": bool(worktree["clean"]),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = inspect_review_target(args.base, args.head, args.repository)
    except GitCommandError as exc:
        print(json.dumps({"error": exc.code}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
