from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import time
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
ISOLATED_RUNNER = ROOT / "scripts" / "run_isolated_tests.py"
ADMIN_ENV = "WORKSTREAM_TEST_ADMIN_DATABASE_URL"
HEARTBEAT_SECONDS = 60.0
CLEANUP_GRACE_SECONDS = 120.0
LANE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class LaneError(RuntimeError):
    """The semantic test-lane contract is invalid."""


@dataclass(frozen=True)
class TestLane:
    """One dependency-based pytest process."""

    name: str
    modules: tuple[str, ...]
    requires_postgres: bool


LANES = (
    TestLane(
        name="no_postgres",
        requires_postgres=False,
        modules=(
            "tests/test_actor_legacy_classification.py",
            "tests/test_actor_migration_tools.py",
            "tests/test_agent_runtime.py",
            "tests/test_api_contract_e2e.py",
            "tests/test_api_controls.py",
            "tests/test_app.py",
            "tests/test_artifact_architecture.py",
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
        ),
    ),
    TestLane(
        name="schema_contracts",
        requires_postgres=True,
        modules=(
            "tests/test_alembic.py",
            "tests/test_database_reset.py",
        ),
    ),
    TestLane(
        name="control_plane",
        requires_postgres=True,
        modules=(
            "tests/test_actors.py",
            "tests/test_api_rate_controls.py",
            "tests/test_audit.py",
            "tests/test_auth.py",
            "tests/test_authorization.py",
            "tests/test_projects.py",
        ),
    ),
    TestLane(
        name="execution_plane",
        requires_postgres=True,
        modules=(
            "tests/test_artifact_admission.py",
            "tests/test_artifact_recovery.py",
            "tests/test_checkers.py",
            "tests/test_db_session.py",
            "tests/test_outbox.py",
            "tests/test_tasks.py",
        ),
    ),
)
EXCLUDED_MODULES = ("tests/test_isolated_database_runner.py",)
INTERRUPTED = False


@dataclass
class ActiveLane:
    """Runtime custody for one lane process and its private log."""

    lane: TestLane
    process: subprocess.Popen[bytes]
    log: TextIO
    log_path: Path
    started_at: float
    interrupted_at: float | None = None
    timed_out: bool = False


def discover_test_modules(tests_dir: Path = TESTS_DIR, root: Path = ROOT) -> tuple[str, ...]:
    """Discover regular top-level backend test modules."""
    modules: list[str] = []
    for path in sorted(tests_dir.glob("test_*.py")):
        if path.is_symlink() or not path.is_file():
            raise LaneError("invalid_test_module")
        try:
            modules.append(path.relative_to(root).as_posix())
        except ValueError as exc:
            raise LaneError("invalid_test_module") from exc
    if not modules:
        raise LaneError("empty_test_inventory")
    return tuple(modules)


def validate_lane_inventory(
    discovered: tuple[str, ...],
    *,
    lanes: tuple[TestLane, ...] = LANES,
    excluded: tuple[str, ...] = EXCLUDED_MODULES,
) -> None:
    """Require every discovered module in exactly one lane or explicit exclusion."""
    lane_names = [lane.name for lane in lanes]
    if len(set(lane_names)) != len(lane_names) or any(
        LANE_NAME_PATTERN.fullmatch(name) is None for name in lane_names
    ):
        raise LaneError("invalid_lane_names")
    assigned = [module for lane in lanes for module in lane.modules]
    declared = [*assigned, *excluded]
    if any(not _safe_module_path(module) for module in declared):
        raise LaneError("invalid_lane_module")
    if duplicates := sorted(name for name, count in Counter(declared).items() if count != 1):
        raise LaneError(f"duplicate_lane_modules:{','.join(duplicates)}")
    discovered_set = set(discovered)
    declared_set = set(declared)
    if missing := sorted(discovered_set - declared_set):
        raise LaneError(f"missing_lane_modules:{','.join(missing)}")
    if foreign := sorted(declared_set - discovered_set):
        raise LaneError(f"foreign_lane_modules:{','.join(foreign)}")


def _safe_module_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and path.parent == PurePosixPath("tests")
        and path.name.startswith("test_")
        and path.suffix == ".py"
        and ".." not in path.parts
    )


def lane_environment(lane: TestLane) -> dict[str, str]:
    """Build one private process environment and coverage filename."""
    env = os.environ.copy()
    env["COVERAGE_FILE"] = f".coverage.{lane.name}"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if not lane.requires_postgres:
        for name in (
            ADMIN_ENV,
            "WORKSTREAM_DATABASE_URL",
            "WORKSTREAM_TEST_DATABASE_URL",
        ):
            env.pop(name, None)
    return env


def lane_command(lane: TestLane, metadata_dir: Path, timeout_seconds: float) -> list[str]:
    """Construct argv without shell interpolation or credentials."""
    pytest_command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "pytest_asyncio.plugin",
        "-p",
        "pytest_cov.plugin",
        "--cov=app",
        "--cov-report=",
        "--durations=25",
        *lane.modules,
    ]
    if not lane.requires_postgres:
        return pytest_command
    return [
        sys.executable,
        str(ISOLATED_RUNNER),
        "--metadata-json",
        str(metadata_dir / f"{lane.name}.json"),
        "--timeout-seconds",
        f"{timeout_seconds:g}",
        "--",
        *pytest_command,
    ]


def _signal_lane(active: ActiveLane, value: int = signal.SIGINT) -> None:
    if active.process.poll() is not None:
        return
    try:
        os.killpg(active.process.pid, value)
    except ProcessLookupError:
        pass


def _handle_interrupt(_signum: int, _frame: object) -> None:
    global INTERRUPTED
    INTERRUPTED = True


def _emit_lane_log(active: ActiveLane, exit_code: int, elapsed: float) -> None:
    active.log.flush()
    active.log.close()
    print(
        f"=== test lane {active.lane.name}: exit_code={exit_code} "
        f"elapsed_seconds={elapsed:.2f} ===",
        flush=True,
    )
    data = active.log_path.read_bytes()
    if data:
        sys.stdout.buffer.write(data)
        if not data.endswith(b"\n"):
            sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.flush()


def _prepare_outputs(metadata_dir: Path, summary_json: Path) -> None:
    if (
        metadata_dir.exists()
        or metadata_dir.is_symlink()
        or summary_json.exists()
        or summary_json.is_symlink()
        or not summary_json.parent.is_dir()
    ):
        raise LaneError("invalid_lane_outputs")
    for lane in LANES:
        coverage_path = ROOT / f".coverage.{lane.name}"
        if coverage_path.exists() or coverage_path.is_symlink():
            raise LaneError("stale_lane_coverage")
    metadata_dir.mkdir(mode=0o700)


def run_lanes(metadata_dir: Path, summary_json: Path, timeout_seconds: float) -> int:
    """Run all semantic lanes concurrently and retain exact local evidence."""
    if timeout_seconds <= 0:
        raise LaneError("invalid_lane_timeout")
    validate_lane_inventory(discover_test_modules(), lanes=LANES)
    if any(lane.requires_postgres for lane in LANES) and not os.environ.get(ADMIN_ENV):
        raise LaneError("missing_admin_database_url")
    _prepare_outputs(metadata_dir, summary_json)

    previous_sigint = signal.signal(signal.SIGINT, _handle_interrupt)
    previous_sigterm = signal.signal(signal.SIGTERM, _handle_interrupt)
    active: dict[str, ActiveLane] = {}
    results: dict[str, dict[str, object]] = {}
    started = time.monotonic()
    next_heartbeat = started + HEARTBEAT_SECONDS
    stopping = False
    try:
        for lane in LANES:
            log_path = metadata_dir / f"{lane.name}.log"
            log = log_path.open("w", encoding="utf-8")
            process = subprocess.Popen(
                lane_command(lane, metadata_dir, timeout_seconds),
                cwd=ROOT,
                env=lane_environment(lane),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            active[lane.name] = ActiveLane(
                lane=lane,
                process=process,
                log=log,
                log_path=log_path,
                started_at=time.monotonic(),
            )

        while active:
            now = time.monotonic()
            if INTERRUPTED and not stopping:
                stopping = True
                for item in active.values():
                    item.interrupted_at = now
                    _signal_lane(item)
            for name, item in list(active.items()):
                elapsed = now - item.started_at
                if elapsed >= timeout_seconds and item.interrupted_at is None:
                    item.timed_out = True
                    item.interrupted_at = now
                    _signal_lane(item)
                elif (
                    item.interrupted_at is not None
                    and now - item.interrupted_at >= CLEANUP_GRACE_SECONDS
                ):
                    _signal_lane(item, signal.SIGKILL)
                exit_code = item.process.poll()
                if exit_code is None:
                    continue
                _emit_lane_log(item, exit_code, elapsed)
                results[name] = {
                    "elapsed_seconds": round(elapsed, 3),
                    "exit_code": exit_code,
                    "modules": list(item.lane.modules),
                    "requires_postgres": item.lane.requires_postgres,
                    "timed_out": item.timed_out,
                }
                del active[name]
                if exit_code != 0 and not stopping:
                    stopping = True
                    for other in active.values():
                        other.interrupted_at = now
                        _signal_lane(other)
            if active and now >= next_heartbeat:
                names = ",".join(sorted(active))
                print(
                    f"test lanes active: elapsed_seconds={int(now - started)} lanes={names}",
                    flush=True,
                )
                next_heartbeat = now + HEARTBEAT_SECONDS
            if active:
                time.sleep(0.1)
    finally:
        for item in active.values():
            _signal_lane(item, signal.SIGKILL)
            item.log.close()
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)

    summary = {
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "lanes": results,
        "schema_version": 1,
    }
    summary_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return (
        0
        if len(results) == len(LANES)
        and all(result["exit_code"] == 0 for result in results.values())
        else 1
    )


def main() -> int:
    """Validate arguments and run the dependency lanes."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-dir", required=True, type=Path)
    parser.add_argument("--summary-json", required=True, type=Path)
    parser.add_argument("--timeout-seconds", default=1200.0, type=float)
    args = parser.parse_args()
    try:
        return run_lanes(args.metadata_dir, args.summary_json, args.timeout_seconds)
    except (LaneError, OSError) as exc:
        code = exc.args[0] if isinstance(exc, LaneError) else "lane_operation_failed"
        print(f"test lane runner failed: {code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
