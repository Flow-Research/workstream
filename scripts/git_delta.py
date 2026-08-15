"""Deterministic Git delta primitives shared by repository policy tools."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitCommandError(RuntimeError):
    """A checked Git command failed or returned invalid output."""

    def __init__(self, code: str, command: list[str], detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.command = tuple(command)
        self.detail = detail


def run_checked(
    command: list[str],
    *,
    repository_root: Path | None = None,
    timeout_seconds: float = 10,
) -> str:
    """Return stdout for Git, raising a stable error on any failure."""
    try:
        result = subprocess.run(
            command,
            cwd=repository_root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        code = "GIT_TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "GIT_EXEC_ERROR"
        raise GitCommandError(code, command, str(exc)) from exc
    if result.returncode != 0:
        raise GitCommandError("GIT_COMMAND_FAILED", command, result.stderr.strip())
    return result.stdout


def resolve_commit(ref: str, *, repository_root: Path | None = None) -> str:
    """Resolve a ref to one full commit SHA or fail closed."""
    command = ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"]
    output = run_checked(command, repository_root=repository_root).strip()
    if len(output) != 40 or any(character not in "0123456789abcdef" for character in output):
        raise GitCommandError("GIT_INVALID_COMMIT", command, output)
    return output


def resolve_merge_base(
    base_sha: str,
    head_sha: str,
    *,
    repository_root: Path | None = None,
) -> str:
    """Resolve the unique merge base for two commits or fail closed."""
    command = ["git", "merge-base", base_sha, head_sha]
    output = run_checked(command, repository_root=repository_root).strip()
    if len(output) != 40 or any(character not in "0123456789abcdef" for character in output):
        raise GitCommandError("GIT_INVALID_MERGE_BASE", command, output)
    return output


def maybe_run(command: list[str], *, repository_root: Path | None = None) -> str:
    """Return stdout for a successful Git command, otherwise an empty string."""
    result = subprocess.run(
        command,
        cwd=repository_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def add_unique(paths: list[str], output: str) -> None:
    """Append unique non-empty paths from newline-delimited output."""
    for path in output.splitlines():
        if path and path not in paths:
            paths.append(path)


def ref_exists(ref: str, *, repository_root: Path | None = None) -> bool:
    """Return whether a Git ref resolves."""
    return bool(maybe_run(["git", "rev-parse", "--verify", ref], repository_root=repository_root))


def first_existing_ref(
    *refs: str, repository_root: Path | None = None
) -> str | None:
    """Return the first resolvable Git ref."""
    for ref in refs:
        if ref_exists(ref, repository_root=repository_root):
            return ref
    return None


def changed_files(
    base: str,
    head: str,
    *,
    repository_root: Path | None = None,
    include_local: bool = True,
) -> list[str]:
    """Return deterministically ordered changed paths for a Git delta."""
    paths: list[str] = []
    add_unique(
        paths,
        maybe_run(
            ["git", "diff", "--name-only", f"{base}...{head}"],
            repository_root=repository_root,
        ),
    )
    if include_local:
        for command in (
            ["git", "diff", "--name-only", "--cached"],
            ["git", "diff", "--name-only"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ):
            add_unique(paths, maybe_run(command, repository_root=repository_root))
    return sorted(paths)


def count_text_lines(path: str, *, repository_root: Path | None = None) -> int:
    """Return a text-file line count and zero for binary or unreadable data."""
    candidate = (repository_root / path) if repository_root else Path(path)
    try:
        data = candidate.read_bytes()
    except OSError:
        return 0
    return 0 if b"\x00" in data else len(data.splitlines())


def numstat(
    base: str,
    head: str,
    *,
    repository_root: Path | None = None,
    include_local: bool = True,
) -> tuple[int, int, list[tuple[str, int, int]]]:
    """Return added/deleted totals and deterministic per-file Git numstat."""
    outputs = [
        maybe_run(
            ["git", "diff", "--numstat", f"{base}...{head}"],
            repository_root=repository_root,
        )
    ]
    if include_local:
        outputs.extend(
            [
                maybe_run(["git", "diff", "--numstat", "--cached"], repository_root=repository_root),
                maybe_run(["git", "diff", "--numstat"], repository_root=repository_root),
            ]
        )
    rows_by_path: dict[str, tuple[int, int]] = {}
    for output in outputs:
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            added, deleted, path = parts
            try:
                add_count = int(added)
            except ValueError:
                add_count = 0
            try:
                delete_count = int(deleted)
            except ValueError:
                delete_count = 0
            prior_added, prior_deleted = rows_by_path.get(path, (0, 0))
            rows_by_path[path] = (prior_added + add_count, prior_deleted + delete_count)
    if include_local:
        untracked = maybe_run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            repository_root=repository_root,
        )
        for path in untracked.splitlines():
            if path and path not in rows_by_path:
                rows_by_path[path] = (
                    count_text_lines(path, repository_root=repository_root),
                    0,
                )
    rows = [
        (path, added, deleted)
        for path, (added, deleted) in sorted(rows_by_path.items())
    ]
    return (
        sum(row[1] for row in rows),
        sum(row[2] for row in rows),
        rows,
    )


def diff_text(
    base: str,
    head: str,
    paths: list[str] | None = None,
    *,
    repository_root: Path | None = None,
    include_local: bool = True,
) -> str:
    """Return zero-context diff text for the selected Git delta."""
    path_args = ["--", *paths] if paths else []
    parts = [
        maybe_run(
            ["git", "diff", "--unified=0", f"{base}...{head}", *path_args],
            repository_root=repository_root,
        )
    ]
    if include_local:
        parts.extend(
            [
                maybe_run(
                    ["git", "diff", "--unified=0", "--cached", *path_args],
                    repository_root=repository_root,
                ),
                maybe_run(
                    ["git", "diff", "--unified=0", *path_args],
                    repository_root=repository_root,
                ),
            ]
        )
        path_filter = set(paths or [])
        untracked = maybe_run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            repository_root=repository_root,
        )
        for path in untracked.splitlines():
            if path_filter and path not in path_filter:
                continue
            candidate = (repository_root / path) if repository_root else Path(path)
            try:
                text = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            parts.append(f"--- /dev/null\n+++ b/{path}\n{text}")
    return "\n".join(part for part in parts if part)
