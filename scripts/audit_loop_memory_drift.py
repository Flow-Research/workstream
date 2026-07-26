"""Read-only audit of the signed loop-memory branch against trusted main."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from check_loop_memory_state import generated_state_failures
from update_post_merge_memory import (
    LoopMemoryError,
    validate_generated_git_tree,
    verify_generated_state_signature,
)


class AuditError(RuntimeError):
    """One bounded audit failure with a stable diagnostic category."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise AuditError("environment", "required Git history is unavailable")
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise AuditError("environment", "Git returned a non-ASCII object ID") from exc


def _remote_tip(repository: str, branch: str) -> str:
    result = subprocess.run(
        [
            "gh", "api", f"repos/{repository}/git/ref/heads/{branch}",
            "--jq", ".object.sha",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise AuditError("environment", f"required branch {branch!r} is unavailable")
    try:
        fields = result.stdout.decode("ascii").split()
    except UnicodeDecodeError as exc:
        raise AuditError("environment", "remote branch identity is not ASCII") from exc
    if len(fields) != 1 or len(fields[0]) != 40 or any(c not in "0123456789abcdef" for c in fields[0]):
        raise AuditError("environment", f"required branch {branch!r} has an invalid tip")
    return fields[0]


def _state_main_sha(state_root: Path) -> str:
    try:
        state = json.loads((state_root / ".agent-loop/STATE.json").read_text("utf-8"))
        event = state.get("event")
        value = event.get("main_sha") if isinstance(event, dict) else state["source"]["main_sha"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AuditError("corruption", "canonical state has no readable main identity") from exc
    if not isinstance(value, str) or len(value) != 40:
        raise AuditError("corruption", "canonical state has an invalid main identity")
    return value


def audit(
    repository_root: Path,
    state_root: Path,
    public_key: Path,
    repository: str,
    expected_main_sha: str,
    expected_state_sha: str,
) -> dict[str, str]:
    """Validate one immutable snapshot, then prove neither remote tip advanced."""
    if _git(repository_root, "rev-parse", "HEAD") != expected_main_sha:
        raise AuditError("environment", "checkout does not match captured main tip")
    if _git(state_root, "rev-parse", "HEAD") != expected_state_sha:
        raise AuditError("environment", "state checkout does not match captured branch tip")
    if _remote_tip(repository, "main") != expected_main_sha:
        raise AuditError("advanced", "main advanced before validation began")
    if _remote_tip(repository, "automation/loop-memory") != expected_state_sha:
        raise AuditError("advanced", "loop-memory branch advanced before validation began")

    try:
        verify_generated_state_signature(state_root, public_key)
        validate_generated_git_tree(state_root, expected_state_sha, state_root)
    except (LoopMemoryError, OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise AuditError("corruption", f"signed-state custody failed: {exc}") from exc
    failures = generated_state_failures(state_root, repository_root)
    if failures:
        raise AuditError("corruption", "; ".join(failures))

    state_main_sha = _state_main_sha(state_root)
    ancestry = subprocess.run(
        ["git", "-C", str(repository_root), "merge-base", "--is-ancestor", state_main_sha, expected_main_sha],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if ancestry.returncode != 0:
        category = "corruption" if ancestry.returncode == 1 else "environment"
        raise AuditError(category, "signed state main identity is not an ancestor of current main")

    end_main = _remote_tip(repository, "main")
    end_state = _remote_tip(repository, "automation/loop-memory")
    if end_main != expected_main_sha or end_state != expected_state_sha:
        raise AuditError("advanced", "main or loop-memory advanced during the audit")
    return {
        "status": "passed",
        "main_sha": expected_main_sha,
        "state_sha": expected_state_sha,
        "signed_state_main_sha": state_main_sha,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-main-sha", required=True)
    parser.add_argument("--expected-state-sha", required=True)
    parser.add_argument("--diagnostic-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = audit(
            args.repository_root.resolve(), args.state_root.resolve(),
            args.public_key.resolve(), args.repository,
            args.expected_main_sha, args.expected_state_sha,
        )
    except AuditError as exc:
        result = {"status": "failed", "category": exc.category, "message": str(exc)}
        exit_code = 2 if exc.category == "advanced" else 1
    else:
        exit_code = 0
    rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.diagnostic_output:
        args.diagnostic_output.write_text(rendered, encoding="utf-8")
    print(rendered, end="", file=sys.stdout if exit_code == 0 else sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
