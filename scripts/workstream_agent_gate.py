#!/usr/bin/env python3
"""Static Workstream gates for agent-generated PRs.

This script is intentionally conservative. It does not replace tests, internal
reviewer agents, CodeRabbit, or human judgment. It catches common reviewability
and CI-integrity risks early.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


RISKY_PATTERNS = re.compile(
    r"(auth|permission|policy|payment|payout|billing|invoice|ledger|audit|"
    r"secret|token|session|tenant|pii|migration|schema|deploy|workflow|ci|"
    r"security|review|revision|checker|submission|reputation|contribution|"
    r"alembic|database)",
    re.IGNORECASE,
)

CI_PATTERNS = re.compile(
    r"(^|/)(\.github/workflows/|circleci|gitlab-ci|jenkins|buildkite|"
    r"package\.json|pnpm-lock\.yaml|package-lock\.json|yarn\.lock|Makefile|"
    r"coverage|eslint|tsconfig|pytest|vitest|jest|pyproject\.toml|uv\.lock|"
    r"poetry\.lock|requirements.*|alembic\.ini|backend/alembic/|"
    r"docker-compose\.ya?ml|Dockerfile)",
    re.IGNORECASE,
)
TEST_PATTERNS = re.compile(r"(test|spec|__tests__|\.test\.|\.spec\.)", re.IGNORECASE)
WEAKENING_PATTERNS = re.compile(
    r"(skip\(|\.only\(|continue-on-error\s*:\s*true|\|\|\s*true|"
    r"--passWithNoTests|no-verify|coverageThreshold|threshold|eslint-disable|"
    r"type:\s*ignore|@ts-ignore|@ts-nocheck)",
    re.IGNORECASE,
)


@dataclass
class Finding:
    severity: str
    code: str
    message: str


def run(cmd: list[str]) -> str:
    """Run a command and return trimmed stdout."""
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()


def maybe_run(cmd: list[str]) -> str:
    """Run a command and return stdout, or an empty string on failure."""
    result = subprocess.run(
        cmd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def add_unique(paths: list[str], output: str) -> None:
    """Append unique paths from command output."""
    for path in output.splitlines():
        if path and path not in paths:
            paths.append(path)


def ref_exists(ref: str) -> bool:
    """Return whether a git ref exists."""
    return bool(maybe_run(["git", "rev-parse", "--verify", ref]))


def first_existing_ref(*refs: str) -> str | None:
    """Return the first git ref that exists."""
    for ref in refs:
        if ref_exists(ref):
            return ref
    return None


def changed_files(base: str, head: str) -> list[str]:
    """Return changed file paths, including local dirty-tree paths."""
    paths: list[str] = []
    add_unique(paths, maybe_run(["git", "diff", "--name-only", f"{base}...{head}"]))
    add_unique(paths, maybe_run(["git", "diff", "--name-only", "--cached"]))
    add_unique(paths, maybe_run(["git", "diff", "--name-only"]))
    add_unique(paths, maybe_run(["git", "ls-files", "--others", "--exclude-standard"]))
    return paths


def numstat(base: str, head: str) -> tuple[int, int, list[tuple[str, int, int]]]:
    """Return added/deleted line totals and per-file rows, including dirty files."""
    outputs = [
        maybe_run(["git", "diff", "--numstat", f"{base}...{head}"]),
        maybe_run(["git", "diff", "--numstat", "--cached"]),
        maybe_run(["git", "diff", "--numstat"]),
    ]
    rows_by_path: dict[str, tuple[int, int]] = {}
    for output in outputs:
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            add, delete, path = parts
            try:
                a = int(add)
            except ValueError:
                a = 0
            try:
                d = int(delete)
            except ValueError:
                d = 0
            previous_add, previous_del = rows_by_path.get(path, (0, 0))
            rows_by_path[path] = (previous_add + a, previous_del + d)

    for path in maybe_run(["git", "ls-files", "--others", "--exclude-standard"]).splitlines():
        if not path or path in rows_by_path:
            continue
        added = count_text_lines(path)
        rows_by_path[path] = (added, 0)
    rows = [(path, added, deleted) for path, (added, deleted) in rows_by_path.items()]
    total_add = sum(added for _, added, _ in rows)
    total_del = sum(deleted for _, _, deleted in rows)
    return total_add, total_del, rows


def count_text_lines(path: str) -> int:
    """Return a line count for text files and zero for binary/unreadable files."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return 0
    if b"\x00" in data:
        return 0
    return len(data.splitlines())


def diff_text(base: str, head: str, paths: list[str] | None = None) -> str:
    """Return zero-context diff text, including local dirty changes."""
    path_args = ["--", *paths] if paths else []
    parts = [
        maybe_run(["git", "diff", "--unified=0", f"{base}...{head}", *path_args]),
        maybe_run(["git", "diff", "--unified=0", "--cached", *path_args]),
        maybe_run(["git", "diff", "--unified=0", *path_args]),
    ]
    path_filter = set(paths or [])
    for path in maybe_run(["git", "ls-files", "--others", "--exclude-standard"]).splitlines():
        if path_filter and path not in path_filter:
            continue
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parts.append(f"--- /dev/null\n+++ b/{path}\n{text}")
    return "\n".join(part for part in parts if part)


def analyze(base: str, head: str, max_l1_lines: int = 500) -> dict:
    """Analyze a diff for Workstream reviewability and gate-integrity risk."""
    resolved_base = base if ref_exists(base) else first_existing_ref("origin/main", "main")
    if resolved_base is None:
        return {
            "result": "REVIEW_REQUIRED",
            "files_changed": 0,
            "lines_added": 0,
            "lines_deleted": 0,
            "total_changed_lines": 0,
            "risky_files": [],
            "ci_files": [],
            "test_files": [],
            "findings": [
                asdict(
                    Finding(
                        "High",
                        "BASE_REF_UNRESOLVED",
                        "Could not resolve a valid git base ref for analysis.",
                    )
                )
            ],
        }

    files = changed_files(resolved_base, head)
    adds, dels, _rows = numstat(resolved_base, head)
    total = adds + dels

    findings: list[Finding] = []

    risky_files = [f for f in files if RISKY_PATTERNS.search(f)]
    ci_files = [f for f in files if CI_PATTERNS.search(f)]
    test_files = [f for f in files if TEST_PATTERNS.search(f)]

    if total > max_l1_lines:
        findings.append(
            Finding(
                "Medium",
                "DIFF_SIZE",
                f"Large diff: {total} changed lines. Confirm this is one coherent chunk.",
            )
        )

    if len(files) > 15:
        findings.append(
            Finding(
                "Medium",
                "FILE_COUNT",
                f"Many files changed: {len(files)} files. Confirm this is one coherent chunk.",
            )
        )

    if risky_files:
        findings.append(
            Finding(
                "High",
                "RISKY_PATH",
                "Risk-sensitive paths changed: " + ", ".join(risky_files[:20]),
            )
        )

    if ci_files:
        findings.append(
            Finding(
                "High",
                "CI_CHANGED",
                "CI/build/test/package configuration changed: " + ", ".join(ci_files[:20]),
            )
        )

    if test_files and len(test_files) >= 5:
        findings.append(
            Finding(
                "Medium",
                "MANY_TESTS_CHANGED",
                f"Many test files changed ({len(test_files)}). Run test-delta review first.",
            )
        )

    weakening_scan_paths = sorted(set(ci_files + test_files))
    weakening_text = diff_text(resolved_base, head, weakening_scan_paths) if weakening_scan_paths else ""
    weakening_matches = sorted(set(m.group(0) for m in WEAKENING_PATTERNS.finditer(weakening_text)))
    if weakening_matches:
        findings.append(
            Finding(
                "High",
                "POSSIBLE_WEAKENING",
                "Possible test/CI weakening tokens found: " + ", ".join(weakening_matches[:20]),
            )
        )

    result = "PASS"
    if any(f.severity in {"Critical", "High"} for f in findings):
        result = "REVIEW_REQUIRED"
    elif findings:
        result = "WARN"

    return {
        "result": result,
        "files_changed": len(files),
        "lines_added": adds,
        "lines_deleted": dels,
        "total_changed_lines": total,
        "risky_files": risky_files,
        "ci_files": ci_files,
        "test_files": test_files,
        "findings": [asdict(f) for f in findings],
    }


def print_markdown(report: dict) -> None:
    """Print a Markdown gate report."""
    print("# Workstream Agent Sensor Report\n")
    print(f"Result: **{report['result']}**\n")
    print("## Summary\n")
    print(f"- Files changed: {report['files_changed']}")
    print(f"- Lines added: {report['lines_added']}")
    print(f"- Lines deleted: {report['lines_deleted']}")
    print(f"- Total changed lines: {report['total_changed_lines']}\n")
    print("## Findings\n")
    if not report["findings"]:
        print("No static gate findings.")
    else:
        for f in report["findings"]:
            print(f"- **{f['severity']}** `{f['code']}`: {f['message']}")
    print("\n## Reminder\n")
    print(
        "This static sensor is not a verdict. Internal reviewers, external review, "
        "CI, and human merge ownership still decide readiness."
    )


def main() -> int:
    """Run the static gate CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--fail-on-high", action="store_true", help="Exit non-zero on High/Critical findings")
    args = parser.parse_args()

    report = analyze(args.base, args.head)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print_markdown(report)

    if args.fail_on_high and any(f["severity"] in {"Critical", "High"} for f in report["findings"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
