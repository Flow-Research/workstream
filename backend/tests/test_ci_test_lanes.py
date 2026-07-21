from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import time

import pytest  # type: ignore[import-not-found]

import scripts.run_test_lanes as lane_runner
from scripts.run_test_lanes import (
    ADMIN_ENV,
    EXCLUDED_MODULES,
    LANES,
    LaneError,
    TestLane as LaneDefinition,
    discover_test_modules,
    lane_command,
    lane_environment,
    validate_lane_inventory,
)


def test_committed_semantic_lanes_cover_every_test_module_exactly_once() -> None:
    discovered = discover_test_modules()

    validate_lane_inventory(discovered)

    assigned = [module for lane in LANES for module in lane.modules]
    assert len(assigned) == len(set(assigned))
    assert set(assigned).isdisjoint(EXCLUDED_MODULES)
    assert set(assigned) | set(EXCLUDED_MODULES) == set(discovered)
    assert {lane.name for lane in LANES} == {
        "no_postgres",
        "schema_contracts",
        "control_plane",
        "execution_plane",
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("missing", "missing_lane_modules"),
        ("duplicate", "duplicate_lane_modules"),
        ("foreign", "foreign_lane_modules"),
        ("unsafe", "invalid_lane_module"),
        ("name", "invalid_lane_names"),
    ),
)
def test_lane_inventory_rejects_incomplete_or_ambiguous_assignments(
    mutation: str,
    message: str,
) -> None:
    discovered = discover_test_modules()
    lanes = list(LANES)
    first = lanes[0]
    if mutation == "missing":
        lanes[0] = replace(first, modules=first.modules[1:])
    elif mutation == "duplicate":
        lanes[0] = replace(first, modules=(*first.modules, LANES[1].modules[0]))
    elif mutation == "foreign":
        lanes[0] = replace(first, modules=(*first.modules, "tests/test_foreign.py"))
    elif mutation == "unsafe":
        lanes[0] = replace(first, modules=(*first.modules, "../test_escape.py"))
    else:
        lanes[0] = replace(first, name="Invalid Lane")

    with pytest.raises(LaneError, match=message):
        validate_lane_inventory(discovered, lanes=tuple(lanes))


def test_discovery_rejects_symlinked_test_module(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    target = tmp_path / "target.py"
    target.write_text("def test_target(): pass\n", encoding="utf-8")
    (tests / "test_link.py").symlink_to(target)

    with pytest.raises(LaneError, match="invalid_test_module"):
        discover_test_modules(tests, tmp_path)


def test_lane_commands_use_python_argv_and_private_coverage_files(tmp_path: Path) -> None:
    no_postgres = next(lane for lane in LANES if not lane.requires_postgres)
    postgres = next(lane for lane in LANES if lane.requires_postgres)

    direct = lane_command(no_postgres, tmp_path, 1200)
    isolated = lane_command(postgres, tmp_path, 1200)

    assert direct[:3] == [direct[0], "-m", "pytest"]
    assert "scripts/run_isolated_tests.py" not in " ".join(direct)
    assert isolated[1].endswith("scripts/run_isolated_tests.py")
    assert isolated[isolated.index("--timeout-seconds") + 1] == "1200"
    assert isolated[-len(postgres.modules) :] == list(postgres.modules)
    assert "--cov=app" in direct and "--cov=app" in isolated
    assert "--cov-report=" in direct and "--cov-report=" in isolated
    assert "--durations=25" in direct and "--durations=25" in isolated


def test_no_postgres_environment_drops_database_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ADMIN_ENV, "postgresql+asyncpg://admin:secret@localhost/postgres")
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", "postgresql+asyncpg://app:secret@host/db")
    monkeypatch.setenv("WORKSTREAM_TEST_DATABASE_URL", "postgresql+asyncpg://test:secret@host/db")
    no_postgres = next(lane for lane in LANES if not lane.requires_postgres)
    postgres = next(lane for lane in LANES if lane.requires_postgres)

    direct_env = lane_environment(no_postgres)
    postgres_env = lane_environment(postgres)

    assert ADMIN_ENV not in direct_env
    assert "WORKSTREAM_DATABASE_URL" not in direct_env
    assert "WORKSTREAM_TEST_DATABASE_URL" not in direct_env
    assert direct_env["COVERAGE_FILE"] == ".coverage.no_postgres"
    assert postgres_env[ADMIN_ENV].endswith("/postgres")
    assert postgres_env["COVERAGE_FILE"].startswith(".coverage.")


def test_lane_runner_fails_fast_and_records_every_started_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lanes = (
        LaneDefinition(
            name="failing_lane",
            modules=("tests/test_fake_failure.py",),
            requires_postgres=False,
        ),
        LaneDefinition(
            name="interrupted_lane",
            modules=("tests/test_fake_slow.py",),
            requires_postgres=False,
        ),
    )

    def fake_command(
        lane: LaneDefinition,
        _metadata_dir: Path,
        _timeout_seconds: float,
    ) -> list[str]:
        if lane.name == "failing_lane":
            return [sys.executable, "-c", "raise SystemExit(1)"]
        return [sys.executable, "-c", "import time; time.sleep(30)"]

    monkeypatch.setattr(lane_runner, "LANES", lanes)
    monkeypatch.setattr(lane_runner, "lane_command", fake_command)
    monkeypatch.setattr(
        lane_runner,
        "discover_test_modules",
        lambda: (
            *(module for lane in lanes for module in lane.modules),
            *EXCLUDED_MODULES,
        ),
    )
    lane_runner.INTERRUPTED = False
    metadata_dir = tmp_path / "metadata"
    summary_json = tmp_path / "summary.json"

    started = time.monotonic()
    result = lane_runner.run_lanes(metadata_dir, summary_json, 10)
    elapsed = time.monotonic() - started
    try:
        summary = json.loads(summary_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"lane summary was not readable: {exc}") from exc

    assert result == 1
    assert elapsed < 5
    assert set(summary["lanes"]) == {"failing_lane", "interrupted_lane"}
    assert summary["lanes"]["failing_lane"]["exit_code"] == 1
    assert summary["lanes"]["interrupted_lane"]["exit_code"] != 0


def test_lane_contract_rejects_duplicate_exclusion() -> None:
    discovered = discover_test_modules()
    lane = LaneDefinition(
        name="duplicate_exclusion",
        modules=(EXCLUDED_MODULES[0],),
        requires_postgres=False,
    )

    with pytest.raises(LaneError, match="duplicate_lane_modules"):
        validate_lane_inventory(
            discovered,
            lanes=(*LANES, lane),
            excluded=EXCLUDED_MODULES,
        )
