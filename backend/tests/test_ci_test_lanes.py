from __future__ import annotations

from dataclasses import replace
from collections import Counter
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


def test_committed_lanes_cover_recursive_inventory_exactly_once() -> None:
    discovered = runner.discover_test_modules()
    runner.validate_lane_inventory(discovered)

    assigned = [module for lane in LANES for module in lane.modules]
    assert len(LANES) == 7
    assert all(lane.requires_postgres for lane in LANES)
    assert Counter(assigned)[runner.PARTITIONED_SCHEMA_MODULE] == 3
    assert all(
        count
        == (
            len(runner.PARTITIONED_SCHEMA_LANES)
            if module == runner.PARTITIONED_SCHEMA_MODULE
            else 2
            if module in runner.SHARED_FOUNDATION_MODULES
            else 1
        )
        for module, count in Counter(assigned).items()
    )
    assert set(assigned) == set(discovered)
    assert runner.ADMIN_RUNNER_MODULE in next(
        lane.modules for lane in LANES if lane.name == "schema_contracts_a"
    )


def test_measured_hotspots_have_explicit_semantic_owners() -> None:
    """Keep lane balance tied to subsystem ownership and measured schema cost."""
    modules_by_lane = {lane.name: set(lane.modules) for lane in LANES}

    assert modules_by_lane["project_lifecycle"] == {
        "tests/projects/guide_compilation/test_contracts.py",
        "tests/projects/guide_compilation/test_database_guards.py",
        "tests/projects/guide_compilation/test_migration_contract.py",
        "tests/projects/guide_compilation/test_public_authorization.py",
        "tests/projects/guide_compilation/test_repository_attempts.py",
        "tests/projects/guide_compilation/test_repository_persistence.py",
        "tests/test_projects.py",
    }
    assert modules_by_lane["task_lifecycle"] == {
        "tests/test_checker_catalogue.py",
        "tests/test_checkers.py",
        "tests/test_default_pre_submit_execution.py",
        "tests/test_effective_pre_submit_execution.py",
        "tests/test_project_guide_compilation_contracts.py",
        "tests/test_review_lease_persistence.py",
        "tests/test_review_queue_persistence.py",
        "tests/test_tasks.py",
    }
    shared_a = modules_by_lane[runner.PARTITIONED_SHARED_LANES[0]]
    shared_b = modules_by_lane[runner.PARTITIONED_SHARED_LANES[1]]
    assert shared_a == shared_b == set(runner.SHARED_FOUNDATION_MODULES)
    assert {
        "tests/test_alembic.py",
        "tests/test_database_reset.py",
        runner.ADMIN_RUNNER_MODULE,
    } == modules_by_lane["schema_contracts_a"]
    assert {"tests/test_alembic.py"} == modules_by_lane["schema_contracts_b"]
    assert {"tests/test_alembic.py"} == modules_by_lane["schema_contracts_c"]
    assert {
        "tests/test_actors.py",
        "tests/test_artifact_admission.py",
        "tests/test_submission_bundle_admission.py",
        "tests/test_authorization.py",
        "tests/test_guide_artifacts.py",
        "tests/test_mutation_policy.py",
    } <= shared_a


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
    (
        ("missing", "missing_lane_modules"),
        ("duplicate", "duplicate_lane_modules"),
        ("foreign", "foreign_lane_modules"),
        ("unsafe", "invalid_lane_module"),
        ("name", "invalid_lane_names"),
    ),
)
def test_inventory_fails_closed(mutation: str, error: str) -> None:
    discovered = runner.discover_test_modules()
    lanes = list(LANES)
    first = lanes[0]
    if mutation == "missing":
        lanes[0] = replace(first, modules=first.modules[1:])
        lanes[1] = replace(lanes[1], modules=lanes[1].modules[1:])
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
    ordinary = f"{runner.PARTITIONED_SCHEMA_MODULE}::test_migration"
    admin = f"{runner.ADMIN_RUNNER_MODULE}::test_admin_owner"
    rows = runner.build_manifest("a" * 40, sorted((ordinary, admin)))["nodes"]

    assert {row["nodeid"]: row["execution_kind"] for row in rows} == {
        admin: runner.ADMIN_KIND,
        ordinary: runner.ORDINARY_KIND,
    }
    assert next(row for row in rows if row["nodeid"] == admin)["lane"] == "schema_contracts_a"


def test_alembic_nodes_partition_deterministically_across_schema_lanes() -> None:
    nodes = [f"{runner.PARTITIONED_SCHEMA_MODULE}::test_migration_{index}" for index in range(100)]

    first = runner.build_manifest("a" * 40, nodes)
    second = runner.build_manifest("a" * 40, list(reversed(nodes)))
    first_by_node = {row["nodeid"]: row["lane"] for row in first["nodes"]}
    second_by_node = {row["nodeid"]: row["lane"] for row in second["nodes"]}

    assert first_by_node == second_by_node
    assert set(first_by_node.values()) == set(runner.PARTITIONED_SCHEMA_LANES)
    assert all(lane in runner.PARTITIONED_SCHEMA_LANES for lane in first_by_node.values())


def test_shared_nodes_partition_deterministically_across_shared_lanes() -> None:
    module = runner.SHARED_FOUNDATION_MODULES[0]
    nodes = [f"{module}::test_shared_{index}" for index in range(100)]

    first = runner.build_manifest("a" * 40, nodes)
    second = runner.build_manifest("a" * 40, list(reversed(nodes)))
    first_by_node = {row["nodeid"]: row["lane"] for row in first["nodes"]}
    second_by_node = {row["nodeid"]: row["lane"] for row in second["nodes"]}

    assert first_by_node == second_by_node
    assert set(first_by_node.values()) == set(runner.PARTITIONED_SHARED_LANES)


def test_manifest_has_no_exclusion_escape_hatch() -> None:
    admin = f"{runner.ADMIN_RUNNER_MODULE}::test_admin_owner"
    manifest = runner.build_manifest("a" * 40, [admin])

    assert "excluded_modules" not in manifest
    assert manifest["nodes"] == [
        {
            "execution_kind": runner.ADMIN_KIND,
            "lane": "schema_contracts_a",
            "module": runner.ADMIN_RUNNER_MODULE,
            "nodeid": admin,
        }
    ]


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
    lane = next(lane for lane in LANES if lane.name == "schema_contracts_a")

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
    lane = next(lane for lane in LANES if lane.name == "schema_contracts_a")
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


def test_run_lanes_reports_collection_failure_before_manifest_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed pytest collection keeps its stable top-level error."""
    modules = tuple(sorted({module for lane in LANES for module in lane.modules}))
    monkeypatch.setattr(runner, "discover_test_modules", lambda: modules)
    monkeypatch.setattr(runner, "_tree_sha", lambda: "c" * 40)
    monkeypatch.setattr(runner, "collect_nodes", lambda *_args: (2, [], []))

    with pytest.raises(LaneError, match="pytest_collection_failed"):
        runner.run_lanes(tmp_path / "metadata", tmp_path / "summary.json", 10)


def test_collect_only_writes_raw_digest_bound_validator_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modules = tuple(sorted({module for lane in LANES for module in lane.modules}))
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
        "aggregate_runner_seconds",
        "canonical_node_count",
        "elapsed_seconds",
        "head_sha",
        "lanes",
        "manifest_file",
        "manifest_sha256",
        "mode",
        "schema_version",
        "slowest_lane_seconds",
    }
    assert summary["mode"] == "collect"
    assert summary["canonical_node_count"] == len(nodes)
    assert summary["manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    assert len(summary["lanes"]) == len(LANES)
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


def test_collect_only_rejects_selected_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modules = tuple(sorted({module for lane in LANES for module in lane.modules}))
    nodes = sorted(f"{module}::test_one" for module in modules)
    monkeypatch.setattr(runner, "discover_test_modules", lambda: tuple(sorted(modules)))
    monkeypatch.setattr(runner, "_tree_sha", lambda: "c" * 40)
    monkeypatch.setattr(runner, "collect_nodes", lambda *_args: (0, nodes, []))

    with pytest.raises(LaneError, match="collect_with_selected_lane"):
        runner.run_lanes(
            tmp_path / "metadata",
            tmp_path / "summary.json",
            10,
            collect_only=True,
            selected_lane=LANES[0].name,
        )


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
