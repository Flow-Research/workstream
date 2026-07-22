#!/usr/bin/env python3
"""Plan, execute, and validate isolated backend CI test shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

SCHEMA_VERSION = 2
SHARD_COUNT = 4
EXCLUDED_MODULE = "backend/tests/test_isolated_database_runner.py"
MODULE_RE = re.compile(r"backend/tests/test_[a-z0-9_]+\.py")
TREE_RE = re.compile(r"[0-9a-f]{40}")
BUNDLE_FILES = {"coverage.data", "result.json"}
COLLECTED_NODES_ENV = "WORKSTREAM_CI_COLLECTED_NODES"
COMPLETED_NODES_ENV = "WORKSTREAM_CI_COMPLETED_NODES"
PYTEST_PLUGINS = (
    "-p",
    "pytest_asyncio.plugin",
    "-p",
    "pytest_cov.plugin",
    "-p",
    "scripts.ci_test_shards",
)


class ShardError(RuntimeError):
    """A stable CI shard planning or evidence failure."""


def _append_node(destination: str, node_id: str) -> None:
    data = (json.dumps(node_id) + "\n").encode()
    flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(destination, flags)
    try:
        os.write(descriptor, data)
    finally:
        os.close(descriptor)


def pytest_collection_finish(session: Any) -> None:
    """Record the final selected inventory from the executing pytest process."""
    destination = os.environ.get(COLLECTED_NODES_ENV)
    if not destination:
        return
    for item in session.items:
        _append_node(destination, item.nodeid)


def pytest_runtest_logfinish(nodeid: str, location: tuple[str, int | None, str]) -> None:
    """Record a node only after its actual pytest lifecycle has finished."""
    del location
    destination = os.environ.get(COMPLETED_NODES_ENV)
    if not destination:
        return
    _append_node(destination, nodeid)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _regular_file(path: Path) -> bool:
    return not path.is_symlink() and path.is_file()


def _tree_sha(repository_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()
    if TREE_RE.fullmatch(result) is None:
        raise ShardError("invalid_tree_sha")
    return result


def _validate_tree_sha(value: str) -> str:
    if TREE_RE.fullmatch(value) is None:
        raise ShardError("invalid_tree_sha")
    return value


def discover_modules(repository_root: Path) -> list[str]:
    """Return the canonical symlink-free backend test module inventory."""
    tests_root = repository_root / "backend/tests"
    if tests_root.is_symlink() or not tests_root.is_dir():
        raise ShardError("invalid_tests_root")
    modules: list[str] = []
    for path in sorted(tests_root.glob("test_*.py")):
        relative = path.relative_to(repository_root).as_posix()
        if MODULE_RE.fullmatch(relative) is None or not _regular_file(path):
            raise ShardError("invalid_test_module")
        if relative != EXCLUDED_MODULE:
            modules.append(relative)
    if not modules or len(modules) != len(set(modules)):
        raise ShardError("invalid_module_inventory")
    return modules


def _module_from_node(node_id: str) -> str:
    if "::" not in node_id:
        raise ShardError("invalid_node_id")
    module_part = node_id.split("::", 1)[0]
    candidate = f"backend/{module_part}"
    if MODULE_RE.fullmatch(candidate) is None:
        raise ShardError("invalid_node_module")
    return candidate


def _node_base(node_id: str) -> str:
    """Remove only pytest's final parameter display value from a node ID."""
    _module_from_node(node_id)
    if node_id.endswith("]") and "[" in node_id:
        return node_id.split("[", 1)[0]
    return node_id


def _node_signature(nodes: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for node in nodes:
        base = _node_base(node)
        counts[base] = counts.get(base, 0) + 1
    return [{"base": base, "count": counts[base]} for base in sorted(counts)]


def _read_node_log(path: Path) -> list[str]:
    try:
        nodes = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShardError("invalid_runtime_nodes") from exc
    if not nodes or not all(isinstance(node, str) for node in nodes):
        raise ShardError("invalid_runtime_nodes")
    return sorted(nodes)


def collect_nodes(repository_root: Path, modules: list[str]) -> dict[str, list[str]]:
    """Collect canonical pytest node IDs for exactly the supplied modules."""
    backend_root = repository_root / "backend"
    relative_modules = [str(PurePosixPath(path).relative_to("backend")) for path in modules]
    collection_env = os.environ.copy()
    collection_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            *PYTEST_PLUGINS,
            *relative_modules,
        ],
        cwd=backend_root,
        env=collection_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ShardError("pytest_collection_failed")
    expected = set(modules)
    collected: dict[str, list[str]] = {module: [] for module in modules}
    seen: set[str] = set()
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or "::" not in line:
            continue
        module = _module_from_node(line)
        if module not in expected or line in seen:
            raise ShardError("foreign_or_duplicate_node")
        collected[module].append(line)
        seen.add(line)
    if not seen or any(not nodes for nodes in collected.values()):
        raise ShardError("zero_test_module")
    return {module: sorted(nodes) for module, nodes in sorted(collected.items())}


def _manifest_body(
    tree_sha: str, module_rows: list[dict[str, Any]], shard_count: int
) -> dict[str, Any]:
    _validate_tree_sha(tree_sha)
    if shard_count != SHARD_COUNT:
        raise ShardError("invalid_shard_count")
    ordered_modules = sorted(row["path"] for row in module_rows)
    if not ordered_modules or len(ordered_modules) != len(set(ordered_modules)):
        raise ShardError("invalid_module_inventory")
    rows_by_module = {row["path"]: row for row in module_rows}
    if len(rows_by_module) != len(module_rows):
        raise ShardError("invalid_module_inventory")
    for module, row in rows_by_module.items():
        if MODULE_RE.fullmatch(module) is None or module == EXCLUDED_MODULE:
            raise ShardError("invalid_test_module")
        signature, weight = row.get("node_signature"), row.get("weight")
        if not isinstance(signature, list) or not signature or not isinstance(weight, int):
            raise ShardError("invalid_node_inventory")
        if any(
            not isinstance(item, dict)
            or set(item) != {"base", "count"}
            or not isinstance(item["base"], str)
            or not isinstance(item["count"], int)
            or isinstance(item["count"], bool)
            or item["count"] < 1
            or _module_from_node(item["base"]) != module
            for item in signature
        ):
            raise ShardError("node_module_mismatch")
        if signature != sorted(signature, key=lambda item: item["base"]):
            raise ShardError("invalid_node_inventory")
        if len({item["base"] for item in signature}) != len(signature) or weight != sum(
            item["count"] for item in signature
        ):
            raise ShardError("invalid_node_inventory")

    bins: list[dict[str, Any]] = [
        {"id": shard_id, "modules": [], "weight": 0} for shard_id in range(1, shard_count + 1)
    ]
    weighted = sorted(
        ((rows_by_module[module]["weight"], module) for module in ordered_modules),
        key=lambda item: (-item[0], item[1]),
    )
    for weight, module in weighted:
        target = min(bins, key=lambda item: (item["weight"], item["id"]))
        target["modules"].append(module)
        target["weight"] += weight
    for shard in bins:
        shard["modules"].sort()
        if not shard["modules"]:
            raise ShardError("empty_shard")

    canonical_rows = [rows_by_module[module] for module in ordered_modules]
    return {
        "excluded_modules": [EXCLUDED_MODULE],
        "modules": canonical_rows,
        "schema_version": SCHEMA_VERSION,
        "shard_count": shard_count,
        "shards": bins,
        "tree_sha": tree_sha,
    }


def build_manifest(
    tree_sha: str, modules_to_nodes: dict[str, list[str]], shard_count: int
) -> dict[str, Any]:
    """Build a canonical manifest with a digest over its executable body."""
    for module, nodes in modules_to_nodes.items():
        if MODULE_RE.fullmatch(module) is None or module == EXCLUDED_MODULE:
            raise ShardError("invalid_test_module")
        if not nodes or nodes != sorted(set(nodes)):
            raise ShardError("invalid_node_inventory")
        if any(_module_from_node(node) != module for node in nodes):
            raise ShardError("node_module_mismatch")
    rows = [
        {"node_signature": _node_signature(nodes), "path": module, "weight": len(nodes)}
        for module, nodes in sorted(modules_to_nodes.items())
    ]
    body = _manifest_body(tree_sha, rows, shard_count)
    return {**body, "manifest_sha256": _sha256(_json_bytes(body))}


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate and canonically reproduce one shard manifest."""
    required = {
        "excluded_modules",
        "manifest_sha256",
        "modules",
        "schema_version",
        "shard_count",
        "shards",
        "tree_sha",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise ShardError("invalid_manifest")
    digest = manifest.get("manifest_sha256")
    modules = manifest.get("modules")
    shard_count = manifest.get("shard_count")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("excluded_modules") != [EXCLUDED_MODULE]
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or not isinstance(modules, list)
        or not isinstance(shard_count, int)
        or isinstance(shard_count, bool)
        or not isinstance(manifest.get("shards"), list)
    ):
        raise ShardError("invalid_manifest")
    rows: list[dict[str, Any]] = []
    for row in modules:
        if not isinstance(row, dict) or set(row) != {"node_signature", "path", "weight"}:
            raise ShardError("invalid_manifest")
        if not isinstance(row["path"], str):
            raise ShardError("invalid_manifest")
        rows.append(row)
    body = _manifest_body(str(manifest.get("tree_sha", "")), rows, shard_count)
    reproduced = {**body, "manifest_sha256": _sha256(_json_bytes(body))}
    if manifest != reproduced or digest != reproduced["manifest_sha256"]:
        raise ShardError("manifest_digest_mismatch")
    return reproduced


def load_manifest(path: Path) -> dict[str, Any]:
    if not _regular_file(path):
        raise ShardError("invalid_manifest_file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShardError("invalid_manifest_file") from exc
    return validate_manifest(value)


def _shard(manifest: dict[str, Any], shard_id: int) -> dict[str, Any]:
    matches = [row for row in manifest["shards"] if row["id"] == shard_id]
    if len(matches) != 1:
        raise ShardError("invalid_shard_id")
    return matches[0]


def _assert_checked_out_tree(repository_root: Path, expected: str) -> None:
    if _tree_sha(repository_root) != _validate_tree_sha(expected):
        raise ShardError("checked_out_tree_mismatch")


def _safe_empty_directory(path: Path) -> None:
    if path.is_symlink() or (path.exists() and (not path.is_dir() or any(path.iterdir()))):
        raise ShardError("invalid_output_directory")
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, value: Any) -> None:
    if path.exists() or path.is_symlink():
        raise ShardError("output_exists")
    path.write_bytes(_json_bytes(value))


def run_shard(
    repository_root: Path,
    manifest_path: Path,
    shard_id: int,
    bundle_dir: Path,
    database_metadata: Path,
) -> None:
    """Run one manifest shard and emit a fixed, non-secret evidence bundle."""
    manifest = load_manifest(manifest_path)
    _assert_checked_out_tree(repository_root, manifest["tree_sha"])
    shard = _shard(manifest, shard_id)
    expected_rows = [row for row in manifest["modules"] if row["path"] in shard["modules"]]

    _safe_empty_directory(bundle_dir)
    coverage_path = bundle_dir / "coverage.data"
    collected_path = database_metadata.with_name(f"collected-nodes-{shard_id}.jsonl")
    completed_path = database_metadata.with_name(f"completed-nodes-{shard_id}.jsonl")
    for path in (collected_path, completed_path):
        if path.exists() or path.is_symlink():
            raise ShardError("runtime_nodes_path_exists")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
    env = os.environ.copy()
    env["COVERAGE_FILE"] = str(coverage_path.resolve())
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env[COLLECTED_NODES_ENV] = str(collected_path.resolve())
    env[COMPLETED_NODES_ENV] = str(completed_path.resolve())
    started = time.monotonic()
    command = [
        sys.executable,
        "scripts/run_isolated_tests.py",
        "--metadata-json",
        str(database_metadata),
        "--timeout-seconds",
        "4800",
        "--",
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *PYTEST_PLUGINS,
        *(str(PurePosixPath(module).relative_to("backend")) for module in shard["modules"]),
        "--cov=app",
        "--cov-report=",
    ]
    result = subprocess.run(command, cwd=repository_root / "backend", env=env, check=False)
    if result.returncode != 0:
        raise ShardError("shard_tests_failed")
    try:
        collected_nodes = _read_node_log(collected_path)
        completed_nodes = _read_node_log(completed_path)
    except ShardError:
        raise
    if collected_nodes != completed_nodes or len(collected_nodes) != len(set(collected_nodes)):
        raise ShardError("shard_execution_mismatch")
    runtime_by_module = {module: [] for module in shard["modules"]}
    for node in collected_nodes:
        module = _module_from_node(node)
        if module not in runtime_by_module:
            raise ShardError("shard_execution_mismatch")
        runtime_by_module[module].append(node)
    runtime_signatures = [
        {
            "node_signature": _node_signature(runtime_by_module[row["path"]]),
            "path": row["path"],
            "weight": len(runtime_by_module[row["path"]]),
        }
        for row in expected_rows
    ]
    if runtime_signatures != expected_rows:
        raise ShardError("shard_signature_mismatch")
    if not _regular_file(coverage_path):
        raise ShardError("missing_coverage")
    coverage_digest = _sha256(coverage_path.read_bytes())
    metadata = {
        "coverage_file": "coverage.data",
        "coverage_sha256": coverage_digest,
        "duration_seconds": round(time.monotonic() - started, 3),
        "manifest_sha256": manifest["manifest_sha256"],
        "modules": shard["modules"],
        "collected_node_ids": collected_nodes,
        "completed_node_ids": completed_nodes,
        "schema_version": SCHEMA_VERSION,
        "shard_id": shard_id,
        "tree_sha": manifest["tree_sha"],
    }
    _write_json(bundle_dir / "result.json", metadata)


def _safe_bundle_files(bundle: Path) -> dict[str, Path]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise ShardError("invalid_bundle_directory")
    found: dict[str, Path] = {}
    for path in bundle.iterdir():
        if path.name not in BUNDLE_FILES or not _regular_file(path):
            raise ShardError("unexpected_bundle_path")
        found[path.name] = path
    if set(found) != BUNDLE_FILES:
        raise ShardError("incomplete_bundle")
    return found


def validate_fan_in(
    manifest: dict[str, Any],
    bundles_root: Path,
    output_dir: Path,
    summary_output: Path | None = None,
) -> list[Path]:
    """Validate the exact shard set and copy authenticated coverage for combine."""
    if bundles_root.is_symlink() or not bundles_root.is_dir():
        raise ShardError("invalid_bundles_root")
    expected_dirs = {f"shard-{index}" for index in range(1, SHARD_COUNT + 1)}
    entries = {path.name for path in bundles_root.iterdir()}
    if entries != expected_dirs:
        raise ShardError("unexpected_bundle_set")

    expected_node_count = sum(module["weight"] for module in manifest["modules"])
    observed_modules: list[str] = []
    coverage_sources: list[Path] = []
    durations: list[float] = []
    for shard_id in range(1, SHARD_COUNT + 1):
        files = _safe_bundle_files(bundles_root / f"shard-{shard_id}")
        try:
            result = json.loads(files["result.json"].read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ShardError("invalid_result_metadata") from exc
        required = {
            "coverage_file",
            "coverage_sha256",
            "duration_seconds",
            "manifest_sha256",
            "modules",
            "collected_node_ids",
            "completed_node_ids",
            "schema_version",
            "shard_id",
            "tree_sha",
        }
        if not isinstance(result, dict) or set(result) != required:
            raise ShardError("invalid_result_metadata")
        expected_shard = _shard(manifest, shard_id)
        if (
            result["schema_version"] != SCHEMA_VERSION
            or result["shard_id"] != shard_id
            or result["tree_sha"] != manifest["tree_sha"]
            or result["manifest_sha256"] != manifest["manifest_sha256"]
            or result["modules"] != expected_shard["modules"]
            or result["coverage_file"] != "coverage.data"
            or not isinstance(result["duration_seconds"], (int, float))
            or isinstance(result["duration_seconds"], bool)
            or result["duration_seconds"] < 0
        ):
            raise ShardError("result_provenance_mismatch")
        collected = result["collected_node_ids"]
        completed = result["completed_node_ids"]
        if (
            not isinstance(collected, list)
            or not all(isinstance(node, str) for node in collected)
            or collected != completed
            or collected != sorted(set(collected))
        ):
            raise ShardError("shard_node_mismatch")
        runtime_by_module = {module: [] for module in expected_shard["modules"]}
        for node in collected:
            module = _module_from_node(node)
            if module not in runtime_by_module:
                raise ShardError("shard_node_mismatch")
            runtime_by_module[module].append(node)
        expected_rows = [
            row for row in manifest["modules"] if row["path"] in expected_shard["modules"]
        ]
        runtime_rows = [
            {
                "node_signature": _node_signature(runtime_by_module[row["path"]]),
                "path": row["path"],
                "weight": len(runtime_by_module[row["path"]]),
            }
            for row in expected_rows
        ]
        if runtime_rows != expected_rows:
            raise ShardError("shard_node_mismatch")
        coverage = files["coverage.data"]
        if result["coverage_sha256"] != _sha256(coverage.read_bytes()):
            raise ShardError("coverage_digest_mismatch")
        observed_modules.extend(result["modules"])
        coverage_sources.append(coverage)
        durations.append(float(result["duration_seconds"]))
    expected_modules = sorted(module["path"] for module in manifest["modules"])
    if sorted(observed_modules) != expected_modules or len(observed_modules) != len(
        set(observed_modules)
    ):
        raise ShardError("fan_in_module_mismatch")

    _safe_empty_directory(output_dir)
    outputs: list[Path] = []
    for shard_id, source in enumerate(coverage_sources, 1):
        target = output_dir / f".coverage.shard-{shard_id}"
        shutil.copyfile(source, target, follow_symlinks=False)
        outputs.append(target)
    if summary_output is not None:
        _write_json(
            summary_output,
            {
                "manifest_sha256": manifest["manifest_sha256"],
                "module_count": len(expected_modules),
                "node_count": expected_node_count,
                "schema_version": SCHEMA_VERSION,
                "timing": {
                    "imbalance_seconds": round(max(durations) - min(durations), 3),
                    "maximum_seconds": max(durations),
                    "total_runner_seconds": round(sum(durations), 3),
                },
                "shards": [
                    {
                        "duration_seconds": durations[index - 1],
                        "id": index,
                        "module_count": len(_shard(manifest, index)["modules"]),
                        "node_count": _shard(manifest, index)["weight"],
                    }
                    for index in range(1, SHARD_COUNT + 1)
                ],
                "tree_sha": manifest["tree_sha"],
            },
        )
    return outputs


def _plan(repository_root: Path, tree_sha: str, shard_count: int) -> dict[str, Any]:
    modules = discover_modules(repository_root)
    return build_manifest(tree_sha, collect_nodes(repository_root, modules), shard_count)


def _dry_run(repository_root: Path, shard_count: int) -> None:
    manifest = _plan(repository_root, _tree_sha(repository_root), shard_count)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        bundles = root / "bundles"
        bundles.mkdir()
        for shard in manifest["shards"]:
            bundle = bundles / f"shard-{shard['id']}"
            bundle.mkdir()
            coverage = bundle / "coverage.data"
            coverage.write_bytes(f"dry-run-{shard['id']}".encode())
            nodes = [
                f"{item['base']}[{index}]" if item["count"] > 1 else item["base"]
                for module in manifest["modules"]
                if module["path"] in shard["modules"]
                for item in module["node_signature"]
                for index in range(item["count"])
            ]
            nodes.sort()
            _write_json(
                bundle / "result.json",
                {
                    "coverage_file": "coverage.data",
                    "coverage_sha256": _sha256(coverage.read_bytes()),
                    "duration_seconds": 0,
                    "manifest_sha256": manifest["manifest_sha256"],
                    "modules": shard["modules"],
                    "collected_node_ids": nodes,
                    "completed_node_ids": nodes,
                    "schema_version": SCHEMA_VERSION,
                    "shard_id": shard["id"],
                    "tree_sha": manifest["tree_sha"],
                },
            )
        validate_fan_in(manifest, bundles, root / "combined")
    print(
        json.dumps(
            {
                "manifest_sha256": manifest["manifest_sha256"],
                "modules": len(manifest["modules"]),
                "nodes": sum(row["weight"] for row in manifest["modules"]),
                "shard_weights": [row["weight"] for row in manifest["shards"]],
                "tree_sha": manifest["tree_sha"],
            },
            sort_keys=True,
        )
    )


def main() -> int:
    """Run the requested shard lifecycle command."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--repository-root", type=Path, required=True)
    plan.add_argument("--tree-sha", required=True)
    plan.add_argument("--shards", type=int, default=SHARD_COUNT)
    plan.add_argument("--output", type=Path, required=True)

    run = subparsers.add_parser("run-shard")
    run.add_argument("--repository-root", type=Path, required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--shard", type=int, required=True)
    run.add_argument("--bundle-dir", type=Path, required=True)
    run.add_argument("--database-metadata", type=Path, required=True)

    fan_in = subparsers.add_parser("fan-in")
    fan_in.add_argument("--manifest", type=Path, required=True)
    fan_in.add_argument("--tree-sha", required=True)
    fan_in.add_argument("--bundles-root", type=Path, required=True)
    fan_in.add_argument("--output-dir", type=Path, required=True)
    fan_in.add_argument("--summary-output", type=Path, required=True)

    dry_run = subparsers.add_parser("dry-run")
    dry_run.add_argument("--repository-root", type=Path, required=True)
    dry_run.add_argument("--shards", type=int, default=SHARD_COUNT)

    args = parser.parse_args()
    try:
        if args.command == "plan":
            repository_root = args.repository_root.resolve()
            manifest = _plan(repository_root, args.tree_sha, args.shards)
            if args.output.exists() or args.output.is_symlink():
                raise ShardError("output_exists")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(_json_bytes(manifest))
            print(manifest["manifest_sha256"])
        elif args.command == "run-shard":
            run_shard(
                args.repository_root.resolve(),
                args.manifest,
                args.shard,
                args.bundle_dir,
                args.database_metadata,
            )
        elif args.command == "fan-in":
            manifest = load_manifest(args.manifest)
            if manifest["tree_sha"] != _validate_tree_sha(args.tree_sha):
                raise ShardError("checked_out_tree_mismatch")
            validate_fan_in(
                manifest,
                args.bundles_root,
                args.output_dir,
                args.summary_output,
            )
        else:
            _dry_run(args.repository_root.resolve(), args.shards)
    except (OSError, subprocess.SubprocessError, ShardError) as exc:
        code = exc.args[0] if isinstance(exc, ShardError) else "ci_shard_operation_failed"
        print(f"backend CI shard operation failed: {code}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
