from __future__ import annotations

from dataclasses import replace
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
from coverage import CoverageData

import scripts.run_test_lanes as runner
from scripts.run_test_lanes import LANES, LaneError, TestLane as LaneDefinition


def test_committed_lanes_cover_recursive_inventory_exactly_once() -> None:
    discovered = runner.discover_test_modules()
    runner.validate_lane_inventory(discovered)

    assigned = [module for lane in LANES for module in lane.modules]
    assert len(LANES) == 4
    assert all(lane.requires_postgres for lane in LANES)
    assert len(assigned) == len(set(assigned))
    assert set(assigned) == set(discovered)
    assert runner.ADMIN_RUNNER_MODULE in next(
        lane.modules for lane in LANES if lane.name == "schema_contracts"
    )


def test_discovery_is_recursive_and_lexically_canonical(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    nested = tests / "nested"
    nested.mkdir(parents=True)
    (nested / "test_z.py").write_text("def test_z(): pass\n", encoding="utf-8")
    (tests / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")

    assert runner.discover_test_modules(tests, tmp_path) == (
        "tests/nested/test_z.py",
        "tests/test_a.py",
    )


@pytest.mark.parametrize("kind", ("file", "directory"))
def test_discovery_rejects_symlinks(tmp_path: Path, kind: str) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    if kind == "file":
        target = tmp_path / "target.py"
        target.write_text("def test_x(): pass\n", encoding="utf-8")
        (tests / "test_link.py").symlink_to(target)
    else:
        target = tmp_path / "target"
        target.mkdir()
        (tests / "nested").symlink_to(target, target_is_directory=True)

    with pytest.raises(LaneError, match="symlink"):
        runner.discover_test_modules(tests, tmp_path)


@pytest.mark.parametrize(
    ("mutation", "error"),
    (("missing", "missing_lane_modules"), ("duplicate", "duplicate_lane_modules"),
     ("foreign", "foreign_lane_modules"), ("unsafe", "invalid_lane_module"),
     ("name", "invalid_lane_names")),
)
def test_inventory_fails_closed(mutation: str, error: str) -> None:
    discovered = runner.discover_test_modules()
    lanes = list(LANES)
    first = lanes[0]
    if mutation == "missing":
        lanes[0] = replace(first, modules=first.modules[1:])
    elif mutation == "duplicate":
        lanes[0] = replace(first, modules=(*first.modules, lanes[1].modules[0]))
    elif mutation == "foreign":
        lanes[0] = replace(first, modules=(*first.modules, "tests/test_foreign.py"))
    elif mutation == "unsafe":
        lanes[0] = replace(first, modules=(*first.modules, "../test_escape.py"))
    else:
        lanes[0] = replace(first, name="Invalid Lane")
    with pytest.raises(LaneError, match=error):
        runner.validate_lane_inventory(discovered, lanes=tuple(lanes))


def test_manifest_contains_sorted_exact_node_ids() -> None:
    nodes = [
        f"{LANES[0].modules[0]}::test_b[value::x]",
        f"{LANES[0].modules[0]}::test_a",
    ]
    manifest = runner.build_manifest("a" * 40, sorted(nodes))

    assert set(manifest) == {"schema_version", "head_sha", "nodes"}
    assert manifest["head_sha"] == "a" * 40
    assert [row["nodeid"] for row in manifest["nodes"]] == sorted(nodes)
    assert set(manifest["nodes"][0]) == {"execution_kind", "nodeid", "module", "lane"}
    assert all(row["execution_kind"] == runner.ORDINARY_KIND for row in manifest["nodes"])


def test_manifest_classifies_only_runner_self_tests_as_admin_kind() -> None:
    ordinary = f"{LANES[1].modules[0]}::test_migration"
    admin = f"{runner.ADMIN_RUNNER_MODULE}::test_admin_owner"
    rows = runner.build_manifest("a" * 40, sorted((ordinary, admin)))["nodes"]

    assert {row["nodeid"]: row["execution_kind"] for row in rows} == {
        admin: runner.ADMIN_KIND,
        ordinary: runner.ORDINARY_KIND,
    }
    assert next(row for row in rows if row["nodeid"] == admin)["lane"] == "schema_contracts"


def test_manifest_has_no_exclusion_escape_hatch() -> None:
    admin = f"{runner.ADMIN_RUNNER_MODULE}::test_admin_owner"
    manifest = runner.build_manifest("a" * 40, [admin])

    assert "excluded_modules" not in manifest
    assert manifest["nodes"] == [{
        "execution_kind": runner.ADMIN_KIND,
        "lane": "schema_contracts",
        "module": runner.ADMIN_RUNNER_MODULE,
        "nodeid": admin,
    }]


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
    command = runner.lane_command(
        lane, lane.name, nodes, tmp_path, 1200, "b" * 40
    )

    assert command[1].endswith("scripts/run_isolated_tests.py")
    assert command[command.index("--lane") + 1] == lane.name
    assert command[command.index("--tree-sha") + 1] == "b" * 40
    assert command[-1] == nodes[0]
    assert "--cov=app" in command
    assert "--cov-report=" in command


def test_lane_environment_uses_private_evidence_and_coverage(tmp_path: Path) -> None:
    coverage = tmp_path / ".coverage.no_postgres"
    env = runner.lane_environment(LANES[0], tmp_path, coverage)

    assert env["COVERAGE_FILE"] == str(coverage.resolve())
    paths = [Path(env[name]) for name in (
        runner.COLLECTED_ENV, runner.COMPLETED_ENV, runner.SKIPPED_ENV, runner.DESELECTED_ENV,
    )]
    assert len(set(paths)) == 4
    assert all(path.parent == tmp_path for path in paths)


def test_admin_runner_environment_retains_only_admin_database_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(runner.ADMIN_ENV, "postgresql+asyncpg://admin:secret@localhost/postgres")
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", "postgresql+asyncpg://app:secret@localhost/app")
    monkeypatch.setenv("WORKSTREAM_TEST_DATABASE_URL", "postgresql+asyncpg://test:secret@localhost/test")
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
            "isolation_path": isolation,
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
            "isolation_path": tmp_path / "unused-admin.database.json",
            "skipped_nodes": [],
        },
    ]

    row = runner._finalize_lane(lane, units, tmp_path)

    combined = tmp_path / row["coverage_file"]
    assert combined.read_bytes() == b"ordinary coverage"
    assert row["coverage_sha256"] == hashlib.sha256(b"ordinary coverage").hexdigest()


def test_finalize_lane_rejects_missing_ordinary_coverage(tmp_path: Path) -> None:
    lane = LANES[0]
    isolation = tmp_path / f"{lane.name}.database.json"
    isolation.write_text("{}\n", encoding="utf-8")
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
            "isolation_path": isolation,
            "skipped_nodes": [],
        }
    ]

    with pytest.raises(LaneError, match="missing_lane_coverage"):
        runner._finalize_lane(lane, units, tmp_path)


def test_combine_coverage_merges_multiple_semantic_unit_files(tmp_path: Path) -> None:
    sources = []
    for index in range(2):
        source = tmp_path / f".coverage.unit.{index}"
        data = CoverageData(basename=str(source))
        data.add_lines({str(tmp_path / f"module_{index}.py"): {index + 1}})
        data.write()
        sources.append(source)
    destination = tmp_path / ".coverage.public_lane"

    runner._combine_coverage(sources, destination)

    combined = CoverageData(basename=str(destination))
    combined.read()
    assert set(combined.measured_files()) == {
        str(tmp_path / "module_0.py"),
        str(tmp_path / "module_1.py"),
    }


def test_collect_only_writes_raw_digest_bound_validator_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modules = tuple(module for lane in LANES for module in lane.modules)
    nodes = sorted(f"{module}::test_one" for module in modules)
    monkeypatch.setattr(runner, "discover_test_modules", lambda: tuple(sorted(modules)))
    monkeypatch.setattr(runner, "_tree_sha", lambda: "c" * 40)
    monkeypatch.setattr(runner, "collect_nodes", lambda *_args: (0, nodes, []))
    metadata = tmp_path / "metadata"
    summary_path = tmp_path / "summary.json"

    assert runner.run_lanes(metadata, summary_path, 10, collect_only=True) == 0
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest_bytes = (metadata / summary["manifest_file"]).read_bytes()
    assert set(summary) == {
        "aggregate_runner_seconds", "canonical_node_count", "elapsed_seconds", "head_sha",
        "lanes", "manifest_file", "manifest_sha256", "mode", "schema_version",
        "slowest_lane_seconds",
    }
    assert summary["mode"] == "collect"
    assert summary["canonical_node_count"] == len(nodes)
    assert summary["manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    assert len(summary["lanes"]) == 4
    assert summary["slowest_lane_seconds"] == max(
        lane["elapsed_seconds"] for lane in summary["lanes"]
    )
    assert summary["aggregate_runner_seconds"] == sum(
        lane["elapsed_seconds"] for lane in summary["lanes"]
    )
    for lane in summary["lanes"]:
        assert lane["coverage_file"] is None
        assert lane["execution_exit_code"] is None
        evidence = metadata / lane["evidence_file"]
        assert lane["evidence_sha256"] == hashlib.sha256(evidence.read_bytes()).hexdigest()


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


def test_timing_summary_is_derived_from_exact_four_lanes() -> None:
    lanes = [{"elapsed_seconds": value} for value in (1.125, 2.25, 0.5, 3.75)]

    assert runner._timing_summary(lanes) == {
        "aggregate_runner_seconds": 7.625,
        "slowest_lane_seconds": 3.75,
    }
    with pytest.raises(LaneError, match="invalid_lane_timing_inventory"):
        runner._timing_summary(lanes[:3])
    with pytest.raises(LaneError, match="invalid_lane_timing"):
        runner._timing_summary([*lanes[:3], {"elapsed_seconds": -1.0}])


def test_slow_lanes_use_exact_dependency_owned_execution_units() -> None:
    for lane_name, expected_keys in {
        "control_plane": {"control_plane_authority", "control_plane_projects"},
        "execution_plane": {
            "execution_plane_artifacts",
            "execution_plane_tasks_checkers",
        },
    }.items():
        lane = next(item for item in LANES if item.name == lane_name)
        rows = [
            {"module": module, "nodeid": f"{module}::test_one"}
            for module in lane.modules
        ]
        units = runner._ordinary_units(lane, rows)

        assert {key for key, _rows in units} == expected_keys
        assert sorted(row["nodeid"] for _key, unit_rows in units for row in unit_rows) == sorted(
            row["nodeid"] for row in rows
        )


def test_semantic_execution_units_reject_module_drift() -> None:
    lane = next(item for item in LANES if item.name == "control_plane")
    rows = [
        {"module": module, "nodeid": f"{module}::test_one"}
        for module in lane.modules[:-1]
    ]

    with pytest.raises(LaneError, match="invalid_semantic_unit_inventory"):
        runner._ordinary_units(lane, rows)


def test_exit_aggregation_cannot_hide_signal_failure() -> None:
    assert runner._aggregate_exit_codes([0, 0]) == 0
    assert runner._aggregate_exit_codes([0, 3]) == 1
    assert runner._aggregate_exit_codes([0, -15]) == 1
    with pytest.raises(LaneError, match="invalid_lane_exit_codes"):
        runner._aggregate_exit_codes([])


def test_finalized_lanes_leave_exactly_four_public_coverage_files(tmp_path: Path) -> None:
    rows = []
    for index, lane in enumerate(LANES):
        source = tmp_path / f".coverage.unit.{lane.name}"
        source.write_bytes(f"coverage-{lane.name}".encode())
        isolation = tmp_path / f"{lane.name}.database.json"
        isolation.write_text("{}\n", encoding="utf-8")
        unit = {
            "collected_nodes": [f"{lane.modules[0]}::test_one"],
            "collection_exit_code": 0,
            "completed_nodes": [f"{lane.modules[0]}::test_one"],
            "coverage_path": source,
                "deselected_nodes": [],
                "elapsed_seconds": float(index + 1),
                "execution_kind": runner.ORDINARY_KIND,
                "execution_exit_code": 0,
            "isolation_path": isolation,
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

    def fake_command(lane, resource_lane, _nodes, metadata, _timeout, _sha):
        database = metadata / f"{resource_lane}.database.json"
        database.write_text("{}\n", encoding="utf-8")
        coverage = metadata / f".coverage.unit.{resource_lane}"
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
