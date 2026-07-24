#!/usr/bin/env python3
"""Collect and run four exact-custody backend test lanes."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
ISOLATED_RUNNER = ROOT / "scripts" / "run_isolated_tests.py"
ADMIN_ENV = "WORKSTREAM_TEST_ADMIN_DATABASE_URL"
COLLECTED_ENV = "WORKSTREAM_LANE_COLLECTED_NODES"
COMPLETED_ENV = "WORKSTREAM_LANE_COMPLETED_NODES"
SKIPPED_ENV = "WORKSTREAM_LANE_SKIPPED_NODES"
DESELECTED_ENV = "WORKSTREAM_LANE_DESELECTED_NODES"
SCHEMA_VERSION = 1
ADMIN_RUNNER_MODULE = "tests/test_isolated_database_runner.py"
ORDINARY_KIND = "ordinary_isolated"
ADMIN_KIND = "admin_runner_self_test"
HEARTBEAT_SECONDS = 60.0
CLEANUP_GRACE_SECONDS = 10.0
POLL_SECONDS = 0.05
SHA_RE = re.compile(r"[0-9a-f]{40}")
LANE_RE = re.compile(r"[a-z][a-z0-9_]*")
INTERRUPTED = False


class LaneError(RuntimeError):
    """A stable semantic-lane contract failure."""


@dataclass(frozen=True)
class TestLane:
    """One dependency-oriented test process."""

    name: str
    modules: tuple[str, ...]
    requires_postgres: bool = True


LANES = (
    TestLane(
        "no_postgres",
        (
            "tests/test_actor_legacy_classification.py",
            "tests/test_actor_migration_tools.py",
            "tests/test_agent_runtime.py",
            "tests/test_api_contract_e2e.py",
            "tests/test_api_controls.py",
            "tests/test_app.py",
            "tests/test_artifact_architecture.py",
            "tests/test_artifact_authorization.py",
            "tests/test_artifact_cleanup_wiring.py",
            "tests/test_artifact_preparation.py",
            "tests/test_artifact_store_conformance.py",
            "tests/test_artifact_verification.py",
            "tests/test_artifacts.py",
            "tests/test_assertion_helpers.py",
            "tests/test_aws_credential_isolation.py",
            "tests/test_ci_test_lanes.py",
            "tests/test_config.py",
            "tests/test_coverage_contract.py",
            "tests/test_external_service_adapters.py",
            "tests/test_local_artifact_store.py",
            "tests/test_s3_artifact_store.py",
            "tests/test_test_lane_evidence.py",
        ),
    ),
    TestLane(
        "schema_contracts",
        (
            "tests/test_alembic.py",
            "tests/test_database_reset.py",
            ADMIN_RUNNER_MODULE,
        ),
    ),
    TestLane(
        "control_plane",
        (
            "tests/test_actors.py",
            "tests/test_api_rate_controls.py",
            "tests/test_audit.py",
            "tests/test_auth.py",
            "tests/test_authorization.py",
            "tests/test_projects.py",
        ),
    ),
    TestLane(
        "execution_plane",
        (
            "tests/test_artifact_admission.py",
            "tests/test_artifact_operator_api.py",
            "tests/test_artifact_recovery.py",
            "tests/test_checkers.py",
            "tests/test_db_session.py",
            "tests/test_outbox.py",
            "tests/test_tasks.py",
        ),
    ),
)
@dataclass
class ActiveLane:
    key: str
    lane: TestLane
    execution_kind: str
    expected_nodes: tuple[str, ...]
    process: subprocess.Popen[bytes]
    log: TextIO
    log_path: Path
    evidence_path: Path
    coverage_path: Path
    started_at: float
    interrupted_at: float | None = None
    timed_out: bool = False


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exclusive_file(path: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    os.close(descriptor)


def _append_node(destination: str, node_id: str) -> None:
    flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(destination, flags)
    try:
        os.write(descriptor, (json.dumps(node_id) + "\n").encode())
    finally:
        os.close(descriptor)


def pytest_collection_finish(session: Any) -> None:
    """Record exact selected node IDs in the collecting pytest process."""
    destination = os.environ.get(COLLECTED_ENV)
    if destination:
        for item in session.items:
            _append_node(destination, item.nodeid)


def pytest_runtest_logfinish(nodeid: str, location: tuple[str, int | None, str]) -> None:
    """Record completion only after the node's full pytest lifecycle."""
    del location
    destination = os.environ.get(COMPLETED_ENV)
    if destination:
        _append_node(destination, nodeid)


def pytest_runtest_logreport(report: Any) -> None:
    """Record every skip observed during setup, call, or teardown."""
    destination = os.environ.get(SKIPPED_ENV)
    if destination and report.skipped:
        _append_node(destination, report.nodeid)


def pytest_deselected(items: list[Any]) -> None:
    """Record nodes removed after initial collection."""
    destination = os.environ.get(DESELECTED_ENV)
    if destination:
        for item in items:
            _append_node(destination, item.nodeid)


def discover_test_modules(tests_dir: Path = TESTS_DIR, root: Path = ROOT) -> tuple[str, ...]:
    """Recursively discover regular test modules without following symlinks."""
    if tests_dir.is_symlink() or not tests_dir.is_dir():
        raise LaneError("invalid_tests_root")
    modules: list[str] = []
    for directory, names, files in os.walk(tests_dir, followlinks=False):
        current = Path(directory)
        if current.is_symlink():
            raise LaneError("symlinked_test_directory")
        for name in names:
            if (current / name).is_symlink():
                raise LaneError("symlinked_test_directory")
        for name in files:
            if not (name.startswith("test_") and name.endswith(".py")):
                continue
            path = current / name
            if path.is_symlink() or not path.is_file():
                    raise LaneError("symlinked_test_module")
            try:
                modules.append(path.relative_to(root).as_posix())
            except ValueError as exc:
                raise LaneError("invalid_test_module") from exc
    if not modules or len(modules) != len(set(modules)):
        raise LaneError("invalid_test_inventory")
    return tuple(sorted(modules))


def _safe_module_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and len(path.parts) >= 2
        and path.parts[0] == "tests"
        and path.name.startswith("test_")
        and path.suffix == ".py"
        and ".." not in path.parts
    )


def validate_lane_inventory(
    discovered: tuple[str, ...],
    *,
    lanes: tuple[TestLane, ...] | None = None,
) -> None:
    lanes = LANES if lanes is None else lanes
    names = [lane.name for lane in lanes]
    if len(lanes) != 4 or len(set(names)) != 4 or any(LANE_RE.fullmatch(x) is None for x in names):
        raise LaneError("invalid_lane_names")
    declared = [module for lane in lanes for module in lane.modules]
    if any(not _safe_module_path(module) for module in declared):
        raise LaneError("invalid_lane_module")
    duplicates = sorted(module for module, count in Counter(declared).items() if count != 1)
    if duplicates:
        raise LaneError(f"duplicate_lane_modules:{','.join(duplicates)}")
    missing = sorted(set(discovered) - set(declared))
    foreign = sorted(set(declared) - set(discovered))
    if missing:
        raise LaneError(f"missing_lane_modules:{','.join(missing)}")
    if foreign:
        raise LaneError(f"foreign_lane_modules:{','.join(foreign)}")


def _tree_sha() -> str:
    value = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()
    if SHA_RE.fullmatch(value) is None:
        raise LaneError("invalid_tree_sha")
    return value


def _read_nodes(path: Path, *, allow_empty: bool = False) -> list[str]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LaneError("invalid_node_evidence") from exc
    if (not allow_empty and not values) or any(not isinstance(value, str) or "::" not in value for value in values):
        raise LaneError("invalid_node_evidence")
    return values


def _module_from_node(node_id: str) -> str:
    module = node_id.split("::", 1)[0]
    if "::" not in node_id or not _safe_module_path(module):
        raise LaneError("invalid_node_id")
    return module


def _plugin_args() -> list[str]:
    return ["-p", "pytest_asyncio.plugin", "-p", "pytest_cov.plugin", "-p", "scripts.run_test_lanes"]


def _collection_environment(collected: Path, deselected: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(ROOT), env.get("PYTHONPATH", "")) if value
    )
    env[COLLECTED_ENV] = str(collected.resolve())
    env[DESELECTED_ENV] = str(deselected.resolve())
    return env


def collect_nodes(modules: tuple[str, ...], metadata_dir: Path) -> tuple[int, list[str], list[str]]:
    collected = metadata_dir / "collection.nodes.jsonl"
    deselected = metadata_dir / "collection.deselected.jsonl"
    _exclusive_file(collected)
    _exclusive_file(deselected)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *_plugin_args(), *modules],
        cwd=ROOT, env=_collection_environment(collected, deselected), check=False,
    )
    nodes = _read_nodes(collected) if result.returncode == 0 else []
    deselected_nodes = _read_nodes(deselected, allow_empty=True)
    if result.returncode == 0:
        expected = set(modules)
        if len(nodes) != len(set(nodes)) or any(_module_from_node(node) not in expected for node in nodes):
            raise LaneError("invalid_collected_nodes")
        if set(_module_from_node(node) for node in nodes) != expected:
            raise LaneError("zero_collected_module")
    return result.returncode, sorted(nodes), sorted(deselected_nodes)


def build_manifest(tree_sha: str, nodes: list[str]) -> dict[str, Any]:
    """Build the validator-owned, raw-byte-digested canonical manifest."""
    if not nodes or len(nodes) != len(set(nodes)):
        raise LaneError("invalid_collected_nodes")
    nodes = sorted(nodes)
    lane_by_module = {module: lane.name for lane in LANES for module in lane.modules}
    return {
        "head_sha": tree_sha,
        "nodes": [
            {
                "execution_kind": ADMIN_KIND
                if _module_from_node(node) == ADMIN_RUNNER_MODULE
                else ORDINARY_KIND,
                "lane": lane_by_module[_module_from_node(node)],
                "module": _module_from_node(node),
                "nodeid": node,
            }
            for node in nodes
        ],
        "schema_version": SCHEMA_VERSION,
    }


def lane_environment(
    lane: TestLane,
    metadata_dir: Path,
    coverage_path: Path,
    evidence_stem: str | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(ROOT), env.get("PYTHONPATH", "")) if value
    )
    env["COVERAGE_FILE"] = str(coverage_path.resolve())
    stem = evidence_stem or lane.name
    env[COLLECTED_ENV] = str((metadata_dir / f"{stem}.collected.jsonl").resolve())
    env[COMPLETED_ENV] = str((metadata_dir / f"{stem}.completed.jsonl").resolve())
    env[SKIPPED_ENV] = str((metadata_dir / f"{stem}.skipped.jsonl").resolve())
    env[DESELECTED_ENV] = str((metadata_dir / f"{stem}.deselected.jsonl").resolve())
    return env


def admin_runner_environment(
    lane: TestLane, metadata_dir: Path, coverage_path: Path, evidence_stem: str
) -> dict[str, str]:
    """Retain only the admin URL needed to test the isolation owner itself."""
    env = lane_environment(lane, metadata_dir, coverage_path, evidence_stem)
    env.pop("WORKSTREAM_DATABASE_URL", None)
    env.pop("WORKSTREAM_TEST_DATABASE_URL", None)
    return env


def lane_command(
    lane: TestLane,
    nodes: list[str],
    metadata_dir: Path,
    timeout_seconds: float,
    tree_sha: str,
) -> list[str]:
    pytest_command = [
        sys.executable, "-m", "pytest", "-q", *_plugin_args(), "--cov=app", "--cov-report=",
        "--durations=25", *nodes,
    ]
    return [
        sys.executable, str(ISOLATED_RUNNER), "--metadata-json",
        str(metadata_dir / f"{lane.name}.database.json"), "--lane", lane.name,
        "--tree-sha", tree_sha, "--timeout-seconds", f"{timeout_seconds:g}",
        "--", *pytest_command,
    ]


def admin_runner_command(nodes: list[str]) -> list[str]:
    """Run isolation-runner self-tests directly, never inside an owned database."""
    return [
        sys.executable, "-m", "pytest", "-q", *_plugin_args(), "--cov=app",
        "--cov-report=", "--durations=25", *nodes,
    ]


def _prepare_outputs(metadata_dir: Path, summary_json: Path) -> None:
    if metadata_dir.exists() or metadata_dir.is_symlink() or summary_json.exists() or summary_json.is_symlink():
        raise LaneError("invalid_lane_outputs")
    if not metadata_dir.parent.is_dir() or not summary_json.parent.is_dir():
        raise LaneError("invalid_lane_outputs")
    metadata_dir.mkdir(mode=0o700)


def _signal_lane(active: ActiveLane, value: int) -> None:
    if active.process.poll() is None:
        try:
            os.killpg(active.process.pid, value)
        except ProcessLookupError:
            pass


def _handle_interrupt(_signum: int, _frame: object) -> None:
    global INTERRUPTED
    INTERRUPTED = True


def _finish_unit(active: ActiveLane, exit_code: int, elapsed: float) -> dict[str, Any]:
    active.log.flush()
    active.log.close()
    collected = _read_nodes(active.evidence_path.with_name(f"{active.key}.collected.jsonl"), allow_empty=True)
    completed = _read_nodes(active.evidence_path.with_name(f"{active.key}.completed.jsonl"), allow_empty=True)
    skipped = _read_nodes(active.evidence_path.with_name(f"{active.key}.skipped.jsonl"), allow_empty=True)
    deselected = _read_nodes(active.evidence_path.with_name(f"{active.key}.deselected.jsonl"), allow_empty=True)
    return {
        "collection_exit_code": 0
        if sorted(collected) == sorted(active.expected_nodes)
        else 1,
        "collected_nodes": collected,
        "completed_nodes": completed,
        "coverage_path": active.coverage_path,
        "deselected_nodes": deselected,
        "elapsed_seconds": round(elapsed, 3),
        "execution_exit_code": exit_code,
        "interrupted": active.interrupted_at is not None or active.timed_out,
        "skipped_nodes": skipped,
    }


def _combine_coverage(sources: list[Path], destination: Path) -> None:
    regular = [path for path in sources if path.is_file() and not path.is_symlink()]
    if len(regular) != len(sources):
        return
    if len(regular) == 1:
        shutil.copyfile(regular[0], destination)
        return
    result = subprocess.run(
        [sys.executable, "-m", "coverage", "combine", "--data-file", str(destination),
         *(str(path) for path in regular)],
        cwd=ROOT, check=False,
    )
    if result.returncode != 0:
        raise LaneError("lane_coverage_combine_failed")


def _finalize_lane(
    lane: TestLane, units: list[dict[str, Any]], metadata_dir: Path
) -> dict[str, Any]:
    evidence_path = metadata_dir / f"{lane.name}.json"
    isolation_path = metadata_dir / f"{lane.name}.database.json"
    coverage_path = metadata_dir / f".coverage.{lane.name}"
    _combine_coverage([unit["coverage_path"] for unit in units], coverage_path)
    evidence = {
        "collected_nodes": sorted(node for unit in units for node in unit["collected_nodes"]),
        "completed_nodes": sorted(node for unit in units for node in unit["completed_nodes"]),
        "deselected_nodes": sorted(set(node for unit in units for node in unit["deselected_nodes"])),
        "isolation_metadata_file": isolation_path.name,
        "isolation_metadata_sha256": _sha256(isolation_path.read_bytes()),
        "skipped_nodes": sorted(set(node for unit in units for node in unit["skipped_nodes"])),
    }
    evidence_path.write_bytes(_json_bytes(evidence))
    return {
        "collection_exit_code": max(unit["collection_exit_code"] for unit in units),
        "coverage_file": coverage_path.name,
        "coverage_sha256": _sha256(coverage_path.read_bytes())
        if coverage_path.is_file() and not coverage_path.is_symlink() else None,
        "elapsed_seconds": round(max(unit["elapsed_seconds"] for unit in units), 3),
        "evidence_file": evidence_path.name,
        "evidence_sha256": _sha256(evidence_path.read_bytes()),
        "execution_exit_code": max(unit["execution_exit_code"] for unit in units),
        "interrupted": any(unit["interrupted"] for unit in units),
        "name": lane.name,
    }


def run_lanes(metadata_dir: Path, summary_json: Path, timeout_seconds: float, *, collect_only: bool = False) -> int:
    """Collect canonical nodes and optionally execute all lanes concurrently."""
    global INTERRUPTED
    INTERRUPTED = False
    if timeout_seconds <= 0:
        raise LaneError("invalid_lane_timeout")
    modules = discover_test_modules()
    validate_lane_inventory(modules)
    _prepare_outputs(metadata_dir, summary_json)
    tree_sha = _tree_sha()
    collection_exit, nodes, deselected = collect_nodes(modules, metadata_dir)
    manifest = build_manifest(tree_sha, nodes)
    manifest_path = metadata_dir / "manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest))
    manifest_digest = _sha256(manifest_path.read_bytes())
    if collection_exit != 0 or deselected:
        raise LaneError("pytest_collection_failed")
    if collect_only:
        lane_rows = []
        for lane in LANES:
            lane_nodes = [row["nodeid"] for row in manifest["nodes"] if row["lane"] == lane.name]
            evidence_path = metadata_dir / f"{lane.name}.json"
            evidence_path.write_bytes(_json_bytes({
                "collected_nodes": lane_nodes, "completed_nodes": [], "deselected_nodes": [],
                "isolation_metadata_file": None, "isolation_metadata_sha256": None,
                "skipped_nodes": [],
            }))
            lane_rows.append({
                "collection_exit_code": 0, "coverage_file": None, "coverage_sha256": None,
                "elapsed_seconds": 0.0, "evidence_file": evidence_path.name,
                "evidence_sha256": _sha256(evidence_path.read_bytes()), "execution_exit_code": None,
                "interrupted": False, "name": lane.name,
            })
        summary = {"canonical_node_count": len(nodes), "elapsed_seconds": 0.0,
                   "head_sha": tree_sha, "lanes": lane_rows, "manifest_file": manifest_path.name,
                   "manifest_sha256": manifest_digest, "mode": "collect", "schema_version": SCHEMA_VERSION}
        summary_json.write_bytes(_json_bytes(summary))
        return 0
    if any(lane.requires_postgres for lane in LANES) and not os.environ.get(ADMIN_ENV):
        raise LaneError("missing_admin_database_url")

    active: dict[str, ActiveLane] = {}
    unit_results: dict[str, list[dict[str, Any]]] = {lane.name: [] for lane in LANES}
    started = time.monotonic()
    stopping = False
    old_int = signal.signal(signal.SIGINT, _handle_interrupt)
    old_term = signal.signal(signal.SIGTERM, _handle_interrupt)
    try:
        for lane in LANES:
            lane_rows = [row for row in manifest["nodes"] if row["lane"] == lane.name]
            kinds = [ORDINARY_KIND]
            if any(row["execution_kind"] == ADMIN_KIND for row in lane_rows):
                kinds.append(ADMIN_KIND)
            for kind in kinds:
                unit_nodes = [row["nodeid"] for row in lane_rows if row["execution_kind"] == kind]
                if not unit_nodes:
                    continue
                key = lane.name if kind == ORDINARY_KIND else f"{lane.name}.admin"
                for suffix in ("collected", "completed", "skipped", "deselected"):
                    _exclusive_file(metadata_dir / f"{key}.{suffix}.jsonl")
                log_path = metadata_dir / f"{key}.log"
                log = log_path.open("x", encoding="utf-8")
                coverage_path = metadata_dir / f".coverage.unit.{key}"
                if kind == ADMIN_KIND:
                    command = admin_runner_command(unit_nodes)
                    env = admin_runner_environment(lane, metadata_dir, coverage_path, key)
                else:
                    command = lane_command(lane, unit_nodes, metadata_dir, timeout_seconds, tree_sha)
                    env = lane_environment(lane, metadata_dir, coverage_path, key)
                process = subprocess.Popen(
                    command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                active[key] = ActiveLane(
                    key, lane, kind, tuple(unit_nodes), process, log, log_path,
                    metadata_dir / f"{key}.json",
                    coverage_path, time.monotonic(),
                )
        while active:
            now = time.monotonic()
            if INTERRUPTED and not stopping:
                stopping = True
                for item in active.values():
                    item.interrupted_at = now
                    _signal_lane(item, signal.SIGINT)
            for key, item in list(active.items()):
                elapsed = now - item.started_at
                if elapsed >= timeout_seconds and item.interrupted_at is None:
                    item.timed_out = True
                    item.interrupted_at = now
                    _signal_lane(item, signal.SIGINT)
                elif item.interrupted_at is not None and now - item.interrupted_at >= CLEANUP_GRACE_SECONDS:
                    _signal_lane(item, signal.SIGKILL)
                code = item.process.poll()
                if code is None:
                    continue
                unit_results[item.lane.name].append(_finish_unit(item, code, elapsed))
                del active[key]
                if code != 0 and not stopping:
                    stopping = True
                    for other in active.values():
                        other.interrupted_at = now
                        _signal_lane(other, signal.SIGINT)
            if active:
                time.sleep(POLL_SECONDS)
    finally:
        for item in active.values():
            _signal_lane(item, signal.SIGKILL)
            item.process.wait()
            item.log.close()
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
    results = {
        lane.name: _finalize_lane(lane, unit_results[lane.name], metadata_dir)
        for lane in LANES
        if unit_results[lane.name]
    }
    summary = {
        "canonical_node_count": len(nodes), "elapsed_seconds": round(time.monotonic() - started, 3),
        "head_sha": tree_sha, "lanes": [results[lane.name] for lane in LANES if lane.name in results],
        "manifest_file": manifest_path.name, "manifest_sha256": manifest_digest,
        "mode": "run", "schema_version": SCHEMA_VERSION,
    }
    summary_json.write_bytes(_json_bytes(summary))
    return 0 if len(results) == 4 and all(row["execution_exit_code"] == 0 for row in results.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-dir", required=True, type=Path)
    parser.add_argument("--summary-json", required=True, type=Path)
    parser.add_argument("--timeout-seconds", default=1200.0, type=float)
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    try:
        return run_lanes(args.metadata_dir, args.summary_json, args.timeout_seconds, collect_only=args.collect_only)
    except (LaneError, OSError, subprocess.SubprocessError) as exc:
        code = exc.args[0] if isinstance(exc, LaneError) else "lane_operation_failed"
        print(f"test lane runner failed: {code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
