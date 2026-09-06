from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import types
import uuid

import pytest  # type: ignore[import-not-found]

import scripts.run_test_lanes as runner
from scripts.run_test_lanes import LANES, LaneError, TestLane as LaneDefinition


def test_deterministic_uuid_nodeids_match_across_full_subset_and_repeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(runner.HEAD_ENV, "e" * 40)

    def collect(module_names: tuple[str, ...]) -> dict[str, list[str]]:
        runner.pytest_sessionstart(object())
        try:
            result: dict[str, list[str]] = {}
            for module_name in module_names:
                namespace: dict[str, object] = {}
                source = "import uuid\nvalues = [uuid.uuid4(), uuid.uuid4()]\n"
                filename = runner.ROOT / "tests" / f"test_{module_name}.py"
                exec(compile(source, str(filename), "exec"), namespace)
                values = namespace["values"]
                assert isinstance(values, list)
                result[module_name] = [
                    f"tests/test_{module_name}.py::test_value[{value}]" for value in values
                ]
            return result
        finally:
            runner.pytest_sessionfinish(object(), 0)

    first_full = collect(("alpha", "beta"))
    second_full = collect(("alpha", "beta"))
    subset = collect(("beta",))

    assert first_full == second_full
    assert subset["beta"] == first_full["beta"]
    assert len(set(first_full["alpha"] + first_full["beta"])) == 4
    for nodeid in first_full["alpha"] + first_full["beta"]:
        value = nodeid.rsplit("[", 1)[1][:-1]
        generated = __import__("uuid").UUID(value)
        assert generated.version == 4
        assert generated.variant == __import__("uuid").RFC_4122


def test_uuid4_and_repository_import_alias_are_restored_before_test_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(runner.HEAD_ENV, "f" * 40)
    monkeypatch.delenv(runner.COLLECTED_ENV, raising=False)
    original = uuid.uuid4
    module_name = "tests.test_collection_uuid_alias"
    module = types.ModuleType(module_name)
    module.__file__ = str(runner.ROOT / "tests" / "test_collection_uuid_alias.py")
    sys.modules[module_name] = module
    runner.pytest_sessionstart(object())
    try:
        exec(
            compile(
                "from uuid import uuid4\nCOLLECTED_VALUE = uuid4()\n",
                module.__file__,
                "exec",
            ),
            module.__dict__,
        )
        collected_value = module.COLLECTED_VALUE
        assert module.uuid4 is runner._deterministic_uuid4
        runner.pytest_collection_finish(type("Session", (), {"items": []})())

        assert uuid.uuid4 is original
        assert module.uuid4 is original
        assert module.COLLECTED_VALUE is collected_value
        assert module.uuid4() != module.uuid4()
    finally:
        runner.pytest_sessionfinish(object(), 0)
        sys.modules.pop(module_name, None)
    assert uuid.uuid4 is original


def test_lane_command_uses_exact_nodes_and_isolation_contract(tmp_path: Path) -> None:
    lane = LANES[0]
    nodes = [f"{lane.modules[0]}::test_exact[param]"]
    command = runner.lane_command(lane, nodes, tmp_path, 1200, "b" * 40)

    assert command[1].endswith("scripts/run_isolated_tests.py")
    assert command[command.index("--lane") + 1] == lane.name
    assert command[command.index("--tree-sha") + 1] == "b" * 40
    assert command[-1] == nodes[0]
    assert "--cov=app" in command
    assert "--cov-report=" in command


def test_lane_environment_uses_private_evidence_and_coverage(tmp_path: Path) -> None:
    coverage = tmp_path / ".coverage.shared_foundations"
    env = runner.lane_environment(LANES[0], tmp_path, coverage)

    assert env["COVERAGE_FILE"] == str(coverage.resolve())
    paths = [
        Path(env[name])
        for name in (
            runner.COLLECTED_ENV,
            runner.COMPLETED_ENV,
            runner.SKIPPED_ENV,
            runner.DESELECTED_ENV,
        )
    ]
    assert len(set(paths)) == 4
    assert all(path.parent == tmp_path for path in paths)


def test_admin_runner_environment_retains_only_admin_database_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(runner.ADMIN_ENV, "postgresql+asyncpg://admin:secret@localhost/postgres")
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", "postgresql+asyncpg://app:secret@localhost/app")
    monkeypatch.setenv(
        "WORKSTREAM_TEST_DATABASE_URL", "postgresql+asyncpg://test:secret@localhost/test"
    )
    lane = next(lane for lane in LANES if lane.name == "schema_contracts")

    env = runner.admin_runner_environment(lane, tmp_path, tmp_path / ".coverage", "admin")

    assert runner.ADMIN_ENV in env
    assert "WORKSTREAM_DATABASE_URL" not in env
    assert "WORKSTREAM_TEST_DATABASE_URL" not in env
    command = runner.admin_runner_command([f"{runner.ADMIN_RUNNER_MODULE}::test_one"])
    assert "run_isolated_tests.py" not in " ".join(command)


def test_admin_wrapper_redacts_admin_url_before_persisted_output() -> None:
    secret = "postgresql+asyncpg://admin:secret@localhost/postgres"
    env = os.environ.copy()
    env[runner.ADMIN_ENV] = secret
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            runner.ADMIN_REDACTING_WRAPPER,
            sys.executable,
            "-c",
            f"import os; print(os.environ[{runner.ADMIN_ENV!r}])",
        ],
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )

    assert secret not in result.stdout
    assert result.stdout.strip() == "[REDACTED_ADMIN_DATABASE_URL]"


def test_finalize_lane_requires_ordinary_coverage_but_allows_empty_admin_coverage(
    tmp_path: Path,
) -> None:
    lane = next(lane for lane in LANES if lane.name == "schema_contracts")
    isolation = tmp_path / f"{lane.name}.database.json"
    isolation.write_text("{}\n", encoding="utf-8")
    ordinary_coverage = tmp_path / ".coverage.unit.schema_contracts"
    ordinary_coverage.write_bytes(b"ordinary coverage")
    units = [
        {
            "collection_exit_code": 0,
            "collected_nodes": ["tests/test_alembic.py::test_one"],
            "completed_nodes": ["tests/test_alembic.py::test_one"],
            "coverage_path": ordinary_coverage,
            "deselected_nodes": [],
            "elapsed_seconds": 1.0,
            "execution_kind": runner.ORDINARY_KIND,
            "execution_exit_code": 0,
            "interrupted": False,
            "skipped_nodes": [],
        },
        {
            "collection_exit_code": 0,
            "collected_nodes": [f"{runner.ADMIN_RUNNER_MODULE}::test_one"],
            "completed_nodes": [f"{runner.ADMIN_RUNNER_MODULE}::test_one"],
            "coverage_path": tmp_path / ".coverage.unit.schema_contracts.admin",
            "deselected_nodes": [],
            "elapsed_seconds": 2.0,
            "execution_kind": runner.ADMIN_KIND,
            "execution_exit_code": 0,
            "interrupted": False,
            "skipped_nodes": [],
        },
    ]

    row = runner._finalize_lane(lane, units, tmp_path)

    combined = tmp_path / row["coverage_file"]
    assert combined.read_bytes() == b"ordinary coverage"
    assert row["coverage_sha256"] == hashlib.sha256(b"ordinary coverage").hexdigest()


def test_finalize_lane_rejects_missing_ordinary_coverage(tmp_path: Path) -> None:
    lane = LANES[0]
    tmp_path.joinpath(f"{lane.name}.database.json").write_text("{}\n", encoding="utf-8")
    units = [
        {
            "collection_exit_code": 0,
            "collected_nodes": [f"{lane.modules[0]}::test_one"],
            "completed_nodes": [f"{lane.modules[0]}::test_one"],
            "coverage_path": tmp_path / ".coverage.unit.missing",
            "deselected_nodes": [],
            "elapsed_seconds": 1.0,
            "execution_kind": runner.ORDINARY_KIND,
            "execution_exit_code": 0,
            "interrupted": False,
            "skipped_nodes": [],
        }
    ]

    with pytest.raises(LaneError, match="missing_lane_coverage"):
        runner._finalize_lane(lane, units, tmp_path)


def test_failed_lane_preserves_evidence_without_isolation_metadata(
    tmp_path: Path,
) -> None:
    """A provisioning failure remains observable before metadata exists."""
    lane = LANES[0]
    units = [
        {
            "collection_exit_code": 1,
            "collected_nodes": [],
            "completed_nodes": [],
            "coverage_path": tmp_path / ".coverage.unit.missing",
            "deselected_nodes": [],
            "elapsed_seconds": 1.0,
            "execution_kind": runner.ORDINARY_KIND,
            "execution_exit_code": 2,
            "interrupted": False,
            "skipped_nodes": [],
        }
    ]

    row = runner._finalize_lane(lane, units, tmp_path)
    evidence = json.loads((tmp_path / row["evidence_file"]).read_text())

    assert row["execution_exit_code"] == 1
    assert evidence["isolation_metadata_file"] is None
    assert evidence["isolation_metadata_sha256"] is None


def test_collection_rejects_duplicate_or_foreign_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = "tests/test_alpha.py"

    class Result:
        returncode = 0

    def fake_run(*_args, **kwargs):
        collected = Path(kwargs["env"][runner.COLLECTED_ENV])
        collected.write_text('"tests/test_foreign.py::test_x"\n', encoding="utf-8")
        return Result()

    tmp_path.joinpath("metadata").mkdir()
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    with pytest.raises(LaneError, match="invalid_collected_nodes"):
        runner.collect_nodes((module,), tmp_path / "metadata", "a" * 40)


def test_collection_accepts_a_minimal_base_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = "tests/test_alpha.py"
    metadata = tmp_path / "metadata"
    metadata.mkdir()

    class Result:
        returncode = 0

    def fake_run(*_args, **kwargs):
        environment = kwargs["env"]
        assert kwargs["timeout"] == 12.5
        assert environment["PYTHONPATH"] == str(runner.ROOT)
        assert "UNRELATED_SECRET" not in environment
        Path(environment[runner.COLLECTED_ENV]).write_text(
            json.dumps(f"{module}::test_alpha") + "\n", encoding="utf-8"
        )
        return Result()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.collect_nodes(
        (module,),
        metadata,
        "a" * 40,
        base_environment={"PYTHONPATH": str(runner.ROOT)},
        timeout_seconds=12.5,
    )

    assert result == (0, [f"{module}::test_alpha"], [])


def test_timing_summary_is_derived_from_exact_declared_lanes() -> None:
    elapsed = (1.125, 2.25, 0.5, 3.75, 1.0, 0.75, 0.625)
    lanes = [{"elapsed_seconds": value} for value in elapsed]

    assert runner._timing_summary(lanes) == {
        "aggregate_runner_seconds": 10.0,
        "slowest_lane_seconds": 3.75,
    }
    with pytest.raises(LaneError, match="invalid_lane_timing_inventory"):
        runner._timing_summary(lanes[:-1])
    with pytest.raises(LaneError, match="invalid_lane_timing"):
        runner._timing_summary([*lanes[:-1], {"elapsed_seconds": -1.0}])


def test_exit_aggregation_cannot_hide_signal_failure() -> None:
    assert runner._aggregate_exit_codes([0, 0]) == 0
    assert runner._aggregate_exit_codes([0, 3]) == 1
    assert runner._aggregate_exit_codes([0, -15]) == 1
    with pytest.raises(LaneError, match="invalid_lane_exit_codes"):
        runner._aggregate_exit_codes([])


def test_finalized_lanes_leave_one_public_coverage_file_per_lane(tmp_path: Path) -> None:
    rows = []
    for index, lane in enumerate(LANES):
        source = tmp_path / f".coverage.unit.{lane.name}"
        source.write_bytes(f"coverage-{lane.name}".encode())
        (tmp_path / f"{lane.name}.database.json").write_text("{}\n", encoding="utf-8")
        unit = {
            "collected_nodes": [f"{lane.modules[0]}::test_one"],
            "collection_exit_code": 0,
            "completed_nodes": [f"{lane.modules[0]}::test_one"],
            "coverage_path": source,
            "deselected_nodes": [],
            "elapsed_seconds": float(index + 1),
            "execution_kind": runner.ORDINARY_KIND,
            "execution_exit_code": 0,
            "interrupted": False,
            "skipped_nodes": [],
        }
        rows.append(runner._finalize_lane(lane, [unit], tmp_path))

    assert [row["name"] for row in rows] == [lane.name for lane in LANES]
    assert sorted(path.name for path in tmp_path.glob(".coverage.*")) == sorted(
        f".coverage.{lane.name}" for lane in LANES
    )
    assert not list(tmp_path.glob(".coverage.unit.*"))


def test_failure_interrupts_sibling_process_groups_and_records_all_lanes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lanes = tuple(
        LaneDefinition(f"lane_{index}", (f"tests/test_{index}.py",)) for index in range(4)
    )
    modules = tuple(lane.modules[0] for lane in lanes)
    nodes = [f"{lane.modules[0]}::test_one" for lane in lanes]
    monkeypatch.setattr(runner, "LANES", lanes)
    monkeypatch.setattr(runner, "discover_test_modules", lambda: modules)
    monkeypatch.setattr(runner, "_tree_sha", lambda: "d" * 40)
    monkeypatch.setattr(runner, "collect_nodes", lambda *_args: (0, nodes, []))
    monkeypatch.setenv(runner.ADMIN_ENV, "postgresql+asyncpg://admin@localhost/postgres")
    monkeypatch.setattr(runner, "CLEANUP_GRACE_SECONDS", 0.2)

    def fake_command(lane, _nodes, metadata, _timeout, _sha):
        database = metadata / f"{lane.name}.database.json"
        database.write_text("{}\n", encoding="utf-8")
        coverage = metadata / f".coverage.{lane.name}"
        coverage.write_bytes(b"coverage")
        if lane.name == "lane_0":
            return [sys.executable, "-c", "raise SystemExit(1)"]
        return [sys.executable, "-c", "import time; time.sleep(30)"]

    monkeypatch.setattr(runner, "lane_command", fake_command)
    metadata = tmp_path / "metadata"
    summary_path = tmp_path / "summary.json"
    started = time.monotonic()
    result = runner.run_lanes(metadata, summary_path, 5)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert result == 1
    assert time.monotonic() - started < 3
    assert len(summary["lanes"]) == 4
    assert summary["lanes"][0]["execution_exit_code"] == 1
    assert all(row["interrupted"] for row in summary["lanes"][1:])
    assert summary["slowest_lane_seconds"] == max(
        row["elapsed_seconds"] for row in summary["lanes"]
    )
    assert summary["aggregate_runner_seconds"] == round(
        sum(row["elapsed_seconds"] for row in summary["lanes"]), 3
    )


def test_unexpected_runner_failure_force_kills_and_records_every_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cleanup preserves four-lane evidence and the orchestration traceback."""
    lanes = tuple(
        LaneDefinition(f"lane_{index}", (f"tests/test_{index}.py",)) for index in range(4)
    )
    modules = tuple(lane.modules[0] for lane in lanes)
    nodes = [f"{module}::test_one" for module in modules]
    monkeypatch.setattr(runner, "LANES", lanes)
    monkeypatch.setattr(runner, "discover_test_modules", lambda: modules)
    monkeypatch.setattr(runner, "_tree_sha", lambda: "e" * 40)
    monkeypatch.setattr(runner, "collect_nodes", lambda *_args: (0, nodes, []))
    monkeypatch.setenv(runner.ADMIN_ENV, "postgresql+asyncpg://admin@localhost/postgres")

    def fake_command(lane, _nodes, metadata, _timeout, _sha):
        return [sys.executable, "-c", "import time; time.sleep(30)"]

    monkeypatch.setattr(runner, "lane_command", fake_command)
    admin_url = os.environ[runner.ADMIN_ENV]
    monkeypatch.setattr(
        runner.time,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(RuntimeError(f"boom {admin_url}")),
    )
    metadata = tmp_path / "metadata"
    summary_path = tmp_path / "summary.json"

    assert runner.run_lanes(metadata, summary_path, 5) == 1
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert len(summary["lanes"]) == 4
    assert all(row["interrupted"] for row in summary["lanes"])
    assert all(row["execution_exit_code"] != 0 for row in summary["lanes"])
    stderr = capsys.readouterr().err
    assert "Traceback (most recent call last)" in stderr
    assert "RuntimeError: boom [REDACTED_WORKSTREAM_TEST_ADMIN_DATABASE_URL]" in stderr
    assert admin_url not in stderr


def test_partial_startup_failure_records_exactly_four_failed_lanes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process-launch failure cannot erase lanes that never started."""
    lanes = tuple(
        LaneDefinition(f"lane_{index}", (f"tests/test_{index}.py",)) for index in range(4)
    )
    modules = tuple(lane.modules[0] for lane in lanes)
    nodes = [f"{module}::test_one" for module in modules]
    monkeypatch.setattr(runner, "LANES", lanes)
    monkeypatch.setattr(runner, "discover_test_modules", lambda: modules)
    monkeypatch.setattr(runner, "_tree_sha", lambda: "f" * 40)
    monkeypatch.setattr(runner, "collect_nodes", lambda *_args: (0, nodes, []))
    monkeypatch.setenv(runner.ADMIN_ENV, "postgresql+asyncpg://admin@localhost/postgres")
    monkeypatch.setattr(
        runner,
        "lane_command",
        lambda *_args: [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    real_popen = subprocess.Popen
    launches = 0

    def fail_second_launch(*args, **kwargs):
        nonlocal launches
        launches += 1
        if launches == 2:
            raise OSError("launch failed")
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(runner.subprocess, "Popen", fail_second_launch)
    metadata = tmp_path / "metadata"
    summary_path = tmp_path / "summary.json"

    assert runner.run_lanes(metadata, summary_path, 5) == 1
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert len(summary["lanes"]) == 4
    assert all(row["execution_exit_code"] != 0 for row in summary["lanes"])
