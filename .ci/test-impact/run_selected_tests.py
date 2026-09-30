#!/usr/bin/env python3
"""Execute and attest one exact impact selection without database services."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

BACKEND = Path(__file__).resolve().parents[2] / "backend"
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from scripts.test_impact_selection import (  # noqa: E402
    MAP_RELATIVE_PATH,
    SelectionError,
    _inventory,
    classify_paths,
)


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SelectionError("missing_selection_manifest")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SelectionError("invalid_selection_manifest") from exc
    if not isinstance(value, dict):
        raise SelectionError("invalid_selection_manifest")
    return value


def _digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise SelectionError("missing_bound_input")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_selection(manifest: dict[str, Any], *, expected_job: str) -> list[str]:
    """Recompute every candidate-side binding before collecting tests."""
    current_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    current_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    )
    if (
        current_sha != manifest.get("execution_sha")
        or current_tree != manifest.get("execution_tree")
        or status
        or os.environ.get("GITHUB_SHA") != current_sha
        or os.environ.get("GITHUB_EVENT_PULL_REQUEST_BASE_SHA") != manifest.get("base_sha")
        or os.environ.get("GITHUB_EVENT_PULL_REQUEST_HEAD_SHA") != manifest.get("head_sha")
    ):
        raise SelectionError("candidate_target_mismatch")
    base_sha = str(manifest.get("base_sha", ""))
    head_sha = str(manifest.get("head_sha", ""))
    execution_parents = subprocess.check_output(
        ["git", "show", "-s", "--format=%P", current_sha], cwd=ROOT, text=True
    ).strip().split()
    if execution_parents != [base_sha, head_sha]:
        raise SelectionError("execution_parent_mismatch")
    merge_base = subprocess.check_output(
        ["git", "merge-base", base_sha, head_sha], cwd=ROOT, text=True
    ).strip()
    if merge_base != manifest.get("merge_base_sha"):
        raise SelectionError("merge_base_mismatch")
    raw_paths = subprocess.check_output(
        ["git", "diff", "--name-only", "-z", "--no-renames", merge_base, head_sha, "--"],
        cwd=ROOT,
    )
    try:
        actual_changed_paths = sorted(
            path.decode("utf-8", errors="strict") for path in raw_paths.split(b"\0") if path
        )
    except UnicodeDecodeError as exc:
        raise SelectionError("invalid_changed_path_encoding") from exc
    if actual_changed_paths != manifest.get("changed_paths"):
        raise SelectionError("changed_path_set_mismatch")
    if manifest.get("mode") not in {"impact", "pure"}:
        raise SelectionError("nonselective_manifest")
    expected_jobs = manifest.get("expected_jobs")
    if not isinstance(expected_jobs, list) or expected_job not in expected_jobs:
        raise SelectionError("unexpected_impact_job")

    map_path = ROOT / MAP_RELATIVE_PATH
    selector_path = BACKEND / "scripts/test_impact_selection.py"
    runner_path = Path(__file__).resolve()
    if _digest(map_path) != manifest.get("impact_map_sha256"):
        raise SelectionError("impact_map_drift")
    if _digest(selector_path) != manifest.get("selector_sha256"):
        raise SelectionError("selector_drift")
    if _digest(runner_path) != manifest.get("impact_runner_sha256"):
        raise SelectionError("runner_drift")

    changed_paths = manifest.get("changed_paths")
    if (
        not isinstance(changed_paths, list)
        or any(not isinstance(path, str) for path in changed_paths)
        or hashlib.sha256(_canonical_json(changed_paths)).hexdigest()
        != manifest.get("changed_paths_sha256")
    ):
        raise SelectionError("changed_path_digest_mismatch")
    impact_map = json.loads(map_path.read_text(encoding="utf-8"))
    mode, modules, jobs, profile = classify_paths(changed_paths, impact_map)
    if (
        mode != manifest.get("mode")
        or modules != manifest.get("selected_modules")
        or jobs != manifest.get("expected_jobs")
        or profile != manifest.get("infrastructure_profile")
    ):
        raise SelectionError("classification_drift")

    inventory, inventory_digest = _inventory(ROOT, current_sha)
    if (
        inventory != manifest.get("test_inventory")
        or inventory_digest != manifest.get("test_inventory_sha256")
    ):
        raise SelectionError("test_inventory_drift")
    if _digest(Path(__file__)) != manifest.get("impact_runner_sha256"):
        raise SelectionError("runner_drift")
    return modules


def validate_evidence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    expected_job: str,
    expected_manifest_sha256: str,
) -> None:
    """Verify the selected test artifact against the selection job output."""
    manifest = _read_manifest(manifest_path)
    if _digest(manifest_path) != expected_manifest_sha256:
        raise SelectionError("selection_artifact_digest_mismatch")
    evidence = _read_manifest(evidence_path)
    expected_path = evidence_path.parent / "expected.json"
    expected = _read_manifest(expected_path)
    nodes = evidence.get("selected_nodes")
    completed = evidence.get("completed_nodes")
    observed = evidence.get("observed_collected_nodes")
    elapsed = evidence.get("elapsed_seconds")
    if (
        evidence.get("job") != expected_job
        or evidence.get("execution_sha") != manifest.get("execution_sha")
        or evidence.get("execution_tree") != manifest.get("execution_tree")
        or evidence.get("test_inventory_sha256") != manifest.get("test_inventory_sha256")
        or evidence.get("selection_manifest_sha256") != _hash_bytes(
            _canonical_json(manifest)
        )
        or evidence.get("exit_code") != 0
        or not isinstance(nodes, list)
        or not nodes
        or any(not isinstance(node, str) for node in nodes)
        or nodes != sorted(set(nodes))
        or completed != nodes
        or observed != nodes
        or evidence.get("skipped_nodes") != []
        or evidence.get("deselected_nodes") != []
        or evidence.get("selected_modules") != manifest.get("selected_modules")
        or evidence.get("expected_payload_sha256") != _digest(expected_path)
        or expected.get("execution_sha") != manifest.get("execution_sha")
        or expected.get("execution_tree") != manifest.get("execution_tree")
        or expected.get("selected_modules") != manifest.get("selected_modules")
        or expected.get("selected_nodes") != nodes
        or expected.get("selected_nodes_sha256") != _hash_bytes(_canonical_json(nodes))
        or expected.get("selection_manifest_sha256")
        != _hash_bytes(_canonical_json(manifest))
        or evidence.get("expected_nodes_sha256") != _hash_bytes(_canonical_json(nodes))
        or evidence.get("completed_nodes_sha256") != _hash_bytes(_canonical_json(completed))
        or isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or elapsed < 0
    ):
        raise SelectionError("impact_evidence_incomplete")


def run_selected(manifest: dict[str, Any], output: Path, *, expected_job: str) -> int:
    """Collect exact target nodes, execute them, and require complete custody."""
    from scripts.run_test_lanes import (
        COLLECTED_ENV,
        COMPLETED_ENV,
        DESELECTED_ENV,
        HEAD_ENV,
        SKIPPED_ENV,
        _read_nodes,
        collect_nodes,
    )

    modules = verify_selection(manifest, expected_job=expected_job)
    if output.exists() or output.is_symlink():
        raise SelectionError("impact_output_exists")
    output.mkdir(parents=True, mode=0o700)
    collection_dir = output / "collection"
    collection_dir.mkdir(mode=0o700)
    started = time.monotonic()
    tree_sha = str(manifest["execution_sha"])
    collection_code, nodes, deselected = collect_nodes(
        tuple(modules), collection_dir, tree_sha
    )
    if collection_code != 0 or deselected or not nodes:
        raise SelectionError("impact_collection_failed")

    expected_bytes = _canonical_json(
        {
            "execution_sha": tree_sha,
            "execution_tree": manifest["execution_tree"],
            "selected_modules": modules,
            "selected_nodes": nodes,
            "selected_nodes_sha256": hashlib.sha256(_canonical_json(nodes)).hexdigest(),
            "selection_manifest_sha256": hashlib.sha256(
                _canonical_json(manifest)
            ).hexdigest(),
        }
    )
    expected_path = output / "expected.json"
    expected_path.write_bytes(expected_bytes)

    collected_path = output / "collected.jsonl"
    completed_path = output / "completed.jsonl"
    skipped_path = output / "skipped.jsonl"
    deselected_path = output / "deselected.jsonl"
    for path in (collected_path, completed_path, skipped_path, deselected_path):
        path.touch(mode=0o600, exist_ok=False)
    coverage_path = output / ".coverage"
    env = os.environ.copy()
    env.update(
        {
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONPATH": os.pathsep.join(
                value for value in (str(BACKEND), env.get("PYTHONPATH", "")) if value
            ),
            "COVERAGE_FILE": str(coverage_path),
            COLLECTED_ENV: str(collected_path),
            COMPLETED_ENV: str(completed_path),
            SKIPPED_ENV: str(skipped_path),
            DESELECTED_ENV: str(deselected_path),
            HEAD_ENV: tree_sha,
        }
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "pytest_asyncio.plugin",
        "-p",
        "pytest_cov.plugin",
        "-p",
        "scripts.run_test_lanes",
        "--cov=app",
        "--cov-report=",
        *nodes,
    ]
    result = subprocess.run(command, cwd=BACKEND, env=env, check=False)
    completed = _read_nodes(completed_path, allow_empty=True)
    observed_collected = _read_nodes(collected_path, allow_empty=True)
    skipped = _read_nodes(skipped_path, allow_empty=True)
    run_deselected = _read_nodes(deselected_path, allow_empty=True)
    elapsed = round(time.monotonic() - started, 3)
    evidence = {
        "completed_nodes": sorted(completed),
        "completed_nodes_sha256": hashlib.sha256(
            _canonical_json(sorted(completed))
        ).hexdigest(),
        "expected_nodes_sha256": hashlib.sha256(_canonical_json(nodes)).hexdigest(),
        "expected_payload_sha256": hashlib.sha256(expected_bytes).hexdigest(),
        "execution_sha": tree_sha,
        "execution_tree": manifest["execution_tree"],
        "exit_code": result.returncode,
        "job": expected_job,
        "observed_collected_nodes": sorted(observed_collected),
        "selected_modules": modules,
        "selected_nodes": nodes,
        "skipped_nodes": skipped,
        "deselected_nodes": sorted(set(deselected + run_deselected)),
        "elapsed_seconds": elapsed,
        "selection_manifest_sha256": hashlib.sha256(
            _canonical_json(manifest)
        ).hexdigest(),
        "test_inventory_sha256": manifest["test_inventory_sha256"],
    }
    evidence_path = output / "evidence.json"
    evidence_path.write_bytes(_canonical_json(evidence))
    if (
        result.returncode != 0
        or sorted(observed_collected) != nodes
        or sorted(completed) != nodes
        or skipped
        or run_deselected
    ):
        print("impact test custody incomplete", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-job", required=True, choices=("impact-s3", "impact-pure"))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    try:
        if args.validate_only:
            if args.evidence is None or args.expected_manifest_sha256 is None:
                raise SelectionError("missing_validation_input")
            validate_evidence(
                args.manifest,
                args.evidence,
                expected_job=args.expected_job,
                expected_manifest_sha256=args.expected_manifest_sha256,
            )
            return 0
        return run_selected(
            _read_manifest(args.manifest), args.output, expected_job=args.expected_job
        )
    except (OSError, subprocess.SubprocessError, RuntimeError, SelectionError) as exc:
        print(f"impact test execution failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
