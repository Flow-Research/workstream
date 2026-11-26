"""Source eligibility and callable deltas for the behavior-ownership gate."""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
import re
import subprocess


class SourceAnalysisError(RuntimeError):
    """Source ownership cannot be established safely."""


CALLABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]+$")


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


ELIGIBLE_PREFIXES = ("backend/app/", "backend/scripts/")


OBSERVABLE_OUTCOMES = {
    "return",
    "persisted_state",
    "emitted_fact",
    "denial",
    "mapped_error",
    "idempotent_replay",
    "recovery_outcome",
}


REAL_BOUNDARIES = {"postgresql", "minio", "http", "lock", "trigger", "concurrency"}


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise SourceAnalysisError(f"git_command_failed:{arguments[0]}")
    return result.stdout


def _safe_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise SourceAnalysisError("unsafe_path")
    return path


def _eligible_target(path: str) -> bool:
    candidate = _safe_path(path)
    return (
        candidate.suffix == ".py"
        and candidate.name != "__init__.py"
        and any(path.startswith(prefix) for prefix in ELIGIBLE_PREFIXES)
        and "/tests/" not in f"/{path}"
    )


def _regular_repository_file(root: Path, value: str) -> bool:
    """Return whether every component is non-symlink and the leaf is regular."""
    candidate = root
    try:
        for part in _safe_path(value).parts:
            candidate = candidate / part
            if candidate.is_symlink():
                return False
        return candidate.is_file()
    except OSError:
        return False


def _diff_lines(root: Path, base_sha: str, head_sha: str, path: str) -> tuple[set[int], set[int]]:
    """Return exact old/new line numbers touched by a zero-context diff."""
    output = _git(root, "diff", "--unified=0", "--no-ext-diff", base_sha, head_sha, "--", path)
    old_lines: set[int] = set()
    new_lines: set[int] = set()
    for line in output.splitlines():
        match = HUNK_RE.match(line)
        if match is None:
            continue
        old_start, old_count, new_start, new_count = match.groups()
        old_size = int(old_count or "1")
        new_size = int(new_count or "1")
        old_lines.update(range(int(old_start), int(old_start) + old_size))
        new_lines.update(range(int(new_start), int(new_start) + new_size))
    return old_lines, new_lines


def _source_at(root: Path, revision: str, path: str) -> str:
    return _git(root, "show", f"{revision}:{path}")


def _callable_spans(
    source: str, module: str
) -> tuple[list[tuple[int, int, str]], list[tuple[int, int]]]:
    """Return qualified callable spans and module/class executable spans."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SourceAnalysisError("invalid_target_syntax") from exc
    callables: list[tuple[int, int, str]] = []
    executable: list[tuple[int, int]] = []

    def visit(nodes: list[ast.stmt], parents: tuple[str, ...] = ()) -> None:
        for node in nodes:
            end = getattr(node, "end_lineno", node.lineno)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = min([node.lineno, *[item.lineno for item in node.decorator_list]])
                qualified = ".".join((module, *parents, node.name))
                callables.append((start, end, qualified))
                visit(node.body, (*parents, node.name))
            elif isinstance(node, ast.ClassDef):
                start = min([node.lineno, *[item.lineno for item in node.decorator_list]])
                first = node.body[0]
                body_start = min(
                    [first.lineno, *[item.lineno for item in getattr(first, "decorator_list", [])]]
                )
                # Include bases/keywords on later lines, but not a method's decorators.
                executable.append((start, max(node.lineno, body_start - 1)))
                visit(node.body, (*parents, node.name))
            else:
                executable.append((node.lineno, end))

    visit(tree.body)
    return callables, executable


def _map_changed_lines(source: str, module: str, lines: set[int]) -> tuple[set[str], bool]:
    callables, executable = _callable_spans(source, module)
    owners: set[str] = set()
    unmapped = False
    for line in lines:
        matches = [item for item in callables if item[0] <= line <= item[1]]
        if matches:
            owners.add(min(matches, key=lambda item: item[1] - item[0])[2])
        elif any(start <= line <= end for start, end in executable):
            unmapped = True
    return owners, unmapped


def changed_callables(
    root: Path, base_sha: str, head_sha: str, target: str, *, allow_unmapped: bool = False
) -> list[str]:
    """Derive complete current callable ownership for executable target hunks."""
    module = target.removeprefix("backend/").removesuffix(".py").replace("/", ".")
    delta_base = _git(root, "merge-base", base_sha, head_sha).strip()
    old_lines, new_lines = _diff_lines(root, delta_base, head_sha, target)
    current_source = _source_at(root, head_sha, target)
    current, current_unmapped = _map_changed_lines(current_source, module, new_lines)
    try:
        base_source = _source_at(root, delta_base, target)
    except SourceAnalysisError:
        base_source = ""
    previous: set[str] = set()
    previous_unmapped = False
    if base_source:
        previous, previous_unmapped = _map_changed_lines(base_source, module, old_lines)
    removed = previous - {item[2] for item in _callable_spans(current_source, module)[0]}
    if (current_unmapped or previous_unmapped or removed) and not allow_unmapped:
        raise SourceAnalysisError("unmappable_changed_logic")
    derived = sorted(current | (previous - removed if allow_unmapped else previous))
    if not derived:
        raise SourceAnalysisError("zero_changed_callables")
    return derived
