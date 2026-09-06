"""Exact ownership, partition and collection contracts for hosted CI."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

import scripts.run_test_lanes as runner
from scripts import test_lane_catalogue as catalogue
from scripts.run_test_lanes import LANES, LaneError


def test_committed_lanes_cover_recursive_inventory_exactly_once() -> None:
    discovered = runner.discover_test_modules()
    runner.validate_lane_inventory(discovered)

    assigned = [module for lane in LANES for module in lane.modules]
    assert len(LANES) == 7
    assert all(lane.requires_postgres for lane in LANES)
    assert Counter(assigned)[catalogue.SCHEMA_MODULE] == 1
    assert all(
        count
        == (
            len(("schema_contracts",))
            if module == catalogue.SCHEMA_MODULE
            else 2
            if module in catalogue.PARTITION_LANES_BY_MODULE
            else 1
        )
        for module, count in Counter(assigned).items()
    )
    assert set(assigned) == set(discovered)
    assert runner.ADMIN_RUNNER_MODULE in next(
        lane.modules for lane in LANES if lane.name == "schema_contracts"
    )


def test_measured_hotspots_have_explicit_semantic_owners() -> None:
    """Keep lane balance tied to subsystem ownership and measured schema cost."""
    modules_by_lane = {lane.name: set(lane.modules) for lane in LANES}

    assert (
        modules_by_lane["project_lifecycle_a"]
        == modules_by_lane["project_lifecycle_b"]
        == {
            "tests/projects/guide_compilation/test_authorized_concurrency_postgresql.py",
            "tests/projects/guide_compilation/test_authorized_execution_service.py",
            "tests/projects/guide_compilation/test_authorized_recovery_postgresql.py",
            "tests/projects/guide_compilation/test_authorized_request_service.py",
            "tests/projects/guide_compilation/test_contracts.py",
            "tests/projects/guide_compilation/test_context_builder.py",
            "tests/projects/guide_compilation/test_database_guards.py",
            "tests/projects/guide_compilation/test_durable_dispatch_handoff.py",
            "tests/projects/guide_compilation/test_hidden_call_graph.py",
            "tests/projects/guide_compilation/test_hidden_orchestrator.py",
            "tests/projects/guide_compilation/test_hidden_orchestrator_postgresql.py",
            "tests/projects/guide_compilation/test_migration_authorized_persistence.py",
            "tests/projects/guide_compilation/test_migration_contract.py",
            "tests/projects/guide_compilation/test_public_authorization.py",
            "tests/projects/guide_compilation/test_projection_call_graph.py",
            "tests/projects/guide_compilation/test_projection_contracts.py",
            "tests/projects/guide_compilation/test_projection_migration.py",
            "tests/projects/guide_compilation/test_projection_policy.py",
            "tests/projects/guide_compilation/test_projection_postgresql.py",
            "tests/projects/guide_compilation/test_projection_authorization_postgresql.py",
            "tests/projects/guide_compilation/test_projection_service.py",
            "tests/projects/guide_compilation/test_request_operation_postgresql.py",
            "tests/projects/guide_compilation/test_repository_attempts.py",
            "tests/projects/guide_compilation/test_repository_persistence.py",
            "tests/projects/test_locked_policy_context.py",
            "tests/projects/test_locked_policy_contract.py",
            "tests/projects/test_activation_readiness.py",
            "tests/projects/test_policy_read_composition.py",
            "tests/projects/test_active_guide_read_composition.py",
            "tests/projects/test_retired_submission_derivation_route.py",
            "tests/test_projects.py",
        }
    )
    assert (
        modules_by_lane["task_lifecycle_a"]
        == modules_by_lane["task_lifecycle_b"]
        == {
            "tests/test_checker_catalogue.py",
            "tests/test_checkers.py",
            "tests/test_default_pre_submit_execution.py",
            "tests/test_effective_pre_submit_execution.py",
            "tests/test_project_guide_compilation_contracts.py",
            "tests/test_review_lease_persistence.py",
            "tests/test_review_queue_persistence.py",
            "tests/test_tasks.py",
        }
    )
    shared_a = modules_by_lane[catalogue.PARTITIONED_SHARED_LANES[0]]
    shared_b = modules_by_lane[catalogue.PARTITIONED_SHARED_LANES[1]]
    assert shared_a == shared_b == set(catalogue.SHARED_FOUNDATION_MODULES)
    assert {
        "tests/test_alembic.py",
        "tests/test_database_reset.py",
        runner.ADMIN_RUNNER_MODULE,
    } == modules_by_lane["schema_contracts"]
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
    ordinary = f"{catalogue.SCHEMA_MODULE}::test_migration"
    admin = f"{runner.ADMIN_RUNNER_MODULE}::test_admin_owner"
    rows = runner.build_manifest("a" * 40, sorted((ordinary, admin)))["nodes"]

    assert {row["nodeid"]: row["execution_kind"] for row in rows} == {
        admin: runner.ADMIN_KIND,
        ordinary: runner.ORDINARY_KIND,
    }
    assert next(row for row in rows if row["nodeid"] == admin)["lane"] == "schema_contracts"


def test_schema_nodes_share_one_lane() -> None:
    nodes = [f"{catalogue.SCHEMA_MODULE}::test_migration_{index}" for index in range(100)]
    rows = runner.build_manifest("a" * 40, nodes)["nodes"]
    assert {row["lane"] for row in rows} == {"schema_contracts"}
    assert [row["nodeid"] for row in rows] == sorted(nodes)


@pytest.mark.parametrize(
    ("names", "modules"), catalogue.PARTITION_GROUPS, ids=("shared", "project", "task")
)
def test_owner_nodes_partition_deterministically(names, modules) -> None:
    module = modules[0]
    nodes = [f"{module}::test_shared_{index}" for index in range(100)]

    first = runner.build_manifest("a" * 40, nodes)
    second = runner.build_manifest("a" * 40, list(reversed(nodes)))
    first_by_node = {row["nodeid"]: row["lane"] for row in first["nodes"]}
    second_by_node = {row["nodeid"]: row["lane"] for row in second["nodes"]}

    assert first_by_node == second_by_node
    assert set(first_by_node.values()) == set(names)
    assert set(first_by_node) == set(nodes)
    assert len(first["nodes"]) == len(nodes)


def test_manifest_has_no_exclusion_escape_hatch() -> None:
    admin = f"{runner.ADMIN_RUNNER_MODULE}::test_admin_owner"
    manifest = runner.build_manifest("a" * 40, [admin])

    assert "excluded_modules" not in manifest
    assert manifest["nodes"] == [
        {
            "execution_kind": runner.ADMIN_KIND,
            "lane": "schema_contracts",
            "module": runner.ADMIN_RUNNER_MODULE,
            "nodeid": admin,
        }
    ]


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


def test_partition_rejects_wrong_owner_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    lanes = list(LANES)
    project_index = next(i for i, lane in enumerate(lanes) if lane.name == "project_lifecycle_b")
    task_index = next(i for i, lane in enumerate(lanes) if lane.name == "task_lifecycle_b")
    project, task = lanes[project_index], lanes[task_index]
    lanes[project_index] = replace(project, modules=(task.modules[0], *project.modules[1:]))
    lanes[task_index] = replace(task, modules=(project.modules[0], *task.modules[1:]))
    # Counts alone still pass: the counterexample changes ownership, not inventory.
    runner.validate_lane_inventory(runner.discover_test_modules(), lanes=tuple(lanes))
    monkeypatch.setattr(runner, "LANES", tuple(lanes))
    with pytest.raises(LaneError, match="invalid_partition_lanes"):
        runner.build_manifest("a" * 40, [f"{project.modules[0]}::test_one"])


def test_direct_runner_cli_remains_runnable(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, str(runner.ROOT / "scripts/run_test_lanes.py"), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "--collect-only" in result.stdout
    assert ",".join(lane.name for lane in LANES) in result.stdout


def test_workflow_lane_inventory_matches_catalogue() -> None:
    source = (runner.ROOT.parent / ".github/workflows/backend.yml").read_text()
    expected = Counter(lane.name for lane in LANES)
    matrix = re.search(r"        lane:\n((?:          - [a-z_]+\n)+)", source)
    assert matrix is not None
    assert Counter(re.findall(r"- ([a-z_]+)", matrix[1])) == expected
    assert (
        Counter(re.findall(r"name: backend-lane-\$\{\{ github.sha \}\}-([a-z_]+)", source))
        == expected
    )
    assert Counter(re.findall(r"path: backend/\.ci/download/([a-z_]+)", source)) == expected
    timing = re.search(r"for lane_name in (\([\s\S]*?\)):", source)
    assert timing is not None
    assert Counter(ast.literal_eval(timing[1])) == expected


@pytest.mark.parametrize(
    ("addition", "allowed"),
    (
        ("backend/scripts/test_lane_catalogue.py", True),
        ("backend/scripts/test_lane_catalogue_unapproved.py", False),
    ),
    ids=("exact-catalogue", "arbitrary-sibling"),
)
def test_catalogue_partition_addition_is_bounded(addition: str, allowed: bool) -> None:
    from scripts import behavior_ownership as ownership

    authority = {
        "schema": ownership.PARTITION_SCHEMA,
        "protected_base_commit": "a" * 40,
        "assignments": [{"group": "shared", "target": "backend/scripts/run_test_lanes.py"}],
    }
    trusted = {**authority, "authority_digest": ownership._digest(authority)}
    current = {
        **trusted,
        "assignments": [*authority["assignments"], {"group": "shared", "target": addition}],
    }
    if allowed:
        ownership._validate_additive_partition_transition(current, trusted)
    else:
        with pytest.raises(ownership.BehaviorOwnershipError, match="untrusted_partition_change"):
            ownership._validate_additive_partition_transition(current, trusted)
