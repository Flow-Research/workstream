#!/usr/bin/env python3
"""Build a trusted, exact-target backend test-impact selection manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MAP_RELATIVE_PATH = ".ci/test-impact/impact_map.json"
RUNNER_RELATIVE_PATH = ".ci/test-impact/run_selected_tests.py"
FULL_LANES = [
    "shared_foundations_a",
    "shared_foundations_b",
    "schema_contracts",
    "project_lifecycle_a",
    "project_lifecycle_b",
    "project_lifecycle_c",
    "task_lifecycle_a",
    "task_lifecycle_b",
    "task_lifecycle_c",
]
POLICY_MODULE = "tests/projects/review_policy/test_semantics.py"
FULL_JOBS = ["impact-selection", "auth-boundary-preflight", "minio-image", "lanes", "full-api-e2e"]


def _full() -> tuple[str, list[str], list[str], str]:
    return "full", [], list(FULL_JOBS), "full"


class SelectionError(RuntimeError):
    """The candidate cannot be safely classified for selective test execution."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git(repository: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repository,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SelectionError("git_object_or_command_unavailable") from exc


def classify_paths(
    changed_paths: list[str],
    impact_map: dict[str, Any],
) -> tuple[str, list[str], list[str], str]:
    """Return mode, exact modules, expected jobs, and infrastructure profile."""
    if not changed_paths or len(set(changed_paths)) != len(changed_paths):
        return _full()
    if any(
        not path
        or path.startswith("/")
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
        for path in changed_paths
    ):
        return _full()

    commitrail_paths = [path for path in changed_paths if path.startswith(".commitrail/")]
    source_paths = [path for path in changed_paths if path not in commitrail_paths]
    commitrail_modules = impact_map.get("commitrail_test_modules")
    if (
        not isinstance(commitrail_modules, list)
        or not commitrail_modules
        or any(not isinstance(module, str) for module in commitrail_modules)
    ):
        return _full()

    if not source_paths:
        if not commitrail_paths:
            return _full()
        return (
            "pure",
            sorted(set(commitrail_modules)),
            ["impact-selection", "auth-boundary-preflight", "impact-pure"],
            "none",
        )

    owners = impact_map.get("owners")
    if not isinstance(owners, list):
        return _full()
    for owner in owners:
        if not isinstance(owner, dict):
            continue
        sources = owner.get("source_paths")
        tests = owner.get("test_paths")
        modules = owner.get("test_modules")
        infrastructure = owner.get("infrastructure")
        if (
            not isinstance(sources, list)
            or not isinstance(tests, list)
            or not isinstance(modules, list)
            or not sources
            or not modules
            or any(not isinstance(path, str) for path in (*sources, *tests))
            or any(not isinstance(module, str) for module in modules)
            or infrastructure not in {"minio", "none"}
            or len(set(sources)) != len(sources)
            or len(set(tests)) != len(tests)
            or len(set(modules)) != len(modules)
            or any(not path.startswith("backend/tests/") for path in tests)
            or sorted(modules)
            != sorted(path.removeprefix("backend/") for path in tests)
        ):
            continue
        permitted_paths = set(sources) | set(tests)
        if set(source_paths) <= permitted_paths and set(source_paths) & permitted_paths:
            selected_modules = set(modules)
            if commitrail_paths:
                selected_modules.update(commitrail_modules)
            profile = "minio" if infrastructure == "minio" else "none"
            job = "impact-s3" if profile == "minio" else "impact-pure"
            jobs = ["impact-selection", "auth-boundary-preflight"]
            if profile == "minio":
                jobs.append("minio-image")
            jobs.append(job)
            return "impact", sorted(selected_modules), jobs, profile
    return _full()


def _inventory(repository: Path, execution_sha: str) -> tuple[list[dict[str, str]], str]:
    raw = _git(repository, "ls-tree", "-r", "-z", execution_sha, "--", "backend/tests")
    inventory: list[dict[str, str]] = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, blob = metadata.decode("ascii").split(" ")
            path = raw_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise SelectionError("invalid_test_inventory") from exc
        name = path.rsplit("/", 1)[-1]
        if kind == "blob" and name.startswith("test_") and name.endswith(".py"):
            inventory.append({"blob": blob, "path": path})
    inventory.sort(key=lambda row: row["path"])
    if not inventory:
        raise SelectionError("empty_test_inventory")
    return inventory, _sha256(_canonical(inventory))


def build_manifest(
    trusted_root: Path,
    candidate_root: Path,
    *,
    base_sha: str,
    head_sha: str,
    execution_sha: str,
    force_full: bool = False,
) -> dict[str, Any]:
    """Bind selection to event commits, merge candidate, trusted map and tests."""
    if any(SHA_RE.fullmatch(value) is None for value in (base_sha, head_sha, execution_sha)):
        raise SelectionError("invalid_event_sha")
    candidate_head = _git(candidate_root, "rev-parse", "HEAD").decode().strip()
    candidate_tree = _git(candidate_root, "rev-parse", "HEAD^{tree}").decode().strip()
    candidate_status = _git(candidate_root, "status", "--porcelain").decode()
    if candidate_head != execution_sha or candidate_status:
        raise SelectionError("candidate_checkout_mismatch")
    for value in (base_sha, head_sha, execution_sha):
        _git(candidate_root, "cat-file", "-e", f"{value}^{{commit}}")
    execution_tree = _git(candidate_root, "rev-parse", f"{execution_sha}^{{tree}}").decode().strip()
    if candidate_tree != execution_tree:
        raise SelectionError("candidate_tree_mismatch")
    if force_full:
        if not base_sha == head_sha == execution_sha:
            raise SelectionError("invalid_forced_full_target")
        merge_base = execution_sha
        changed_raw = b""
    else:
        parents = (
            _git(candidate_root, "show", "-s", "--format=%P", execution_sha)
            .decode()
            .strip()
            .split()
        )
        if parents != [base_sha, head_sha]:
            raise SelectionError("execution_parent_mismatch")
        merge_base = _git(candidate_root, "merge-base", base_sha, head_sha).decode().strip()
        if SHA_RE.fullmatch(merge_base) is None:
            raise SelectionError("invalid_merge_base")
        changed_raw = _git(
            candidate_root,
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            merge_base,
            head_sha,
            "--",
        )
    try:
        changed_paths = sorted(
            path.decode("utf-8", errors="strict")
            for path in changed_raw.split(b"\0")
            if path
        )
    except UnicodeDecodeError as exc:
        raise SelectionError("invalid_changed_path_encoding") from exc

    map_path = trusted_root / MAP_RELATIVE_PATH
    if map_path.is_symlink() or not map_path.is_file():
        raise SelectionError("missing_trusted_impact_map")
    map_bytes = map_path.read_bytes()
    try:
        impact_map = json.loads(map_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SelectionError("invalid_trusted_impact_map") from exc
    if not isinstance(impact_map, dict) or impact_map.get("schema_version") != 1:
        raise SelectionError("invalid_trusted_impact_map")

    mode, modules, jobs, profile = (
        _full() if force_full else classify_paths(changed_paths, impact_map)
    )
    inventory, inventory_digest = _inventory(candidate_root, execution_sha)
    known_modules = {f"{Path(row['path']).relative_to('backend')}" for row in inventory}
    expected_paths: set[str] = set()
    for owner in impact_map.get("owners", []):
        if isinstance(owner, dict):
            expected_paths.update(owner.get("test_modules", []))
    expected_paths.update(impact_map.get("commitrail_test_modules", []))
    if any(module not in known_modules for module in modules):
        mode, modules, jobs, profile = _full()
    if mode != "full" and any(module not in expected_paths for module in modules):
        mode, modules, jobs, profile = _full()

    trusted_script = trusted_root / "backend/scripts/test_impact_selection.py"
    if trusted_script.is_symlink() or not trusted_script.is_file():
        raise SelectionError("missing_trusted_selector")
    runner_path = trusted_root / RUNNER_RELATIVE_PATH
    if runner_path.is_symlink() or not runner_path.is_file():
        raise SelectionError("missing_trusted_runner")
    return {
        "base_sha": base_sha,
        "changed_paths": changed_paths,
        "changed_paths_sha256": _sha256(_canonical(changed_paths)),
        "execution_sha": execution_sha,
        "execution_tree": execution_tree,
        "expected_jobs": jobs,
        "head_sha": head_sha,
        "impact_map_sha256": _sha256(map_bytes),
        "infrastructure_profile": profile,
        "merge_base_sha": merge_base,
        "mode": mode,
        "schema_version": 1,
        "selected_modules": modules,
        "selector_sha256": _sha256(trusted_script.read_bytes()),
        "impact_runner_sha256": _sha256(runner_path.read_bytes()),
        "test_inventory": inventory,
        "test_inventory_sha256": inventory_digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trusted-root", required=True, type=Path)
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--execution-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force-full", action="store_true")
    args = parser.parse_args()
    try:
        manifest = build_manifest(
            args.trusted_root.resolve(strict=True),
            args.candidate_root.resolve(strict=True),
            base_sha=args.base_sha,
            head_sha=args.head_sha,
            execution_sha=args.execution_sha,
            force_full=args.force_full,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        manifest_bytes = _canonical(manifest)
        args.output.write_bytes(manifest_bytes)
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            with Path(github_output).open("a", encoding="utf-8") as output:
                output.write(f"mode={manifest['mode']}\n")
                output.write(f"profile={manifest['infrastructure_profile']}\n")
                output.write(f"manifest_sha256={_sha256(manifest_bytes)}\n")
        print(json.dumps({key: manifest[key] for key in ("mode", "expected_jobs", "infrastructure_profile")}))
        return 0
    except (OSError, SelectionError, subprocess.SubprocessError) as exc:
        print(f"impact selection failed closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
