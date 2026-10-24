"""Exact ownership, partition and collection contracts for hosted CI."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import scripts.run_test_lanes as runner
from scripts import test_lane_catalogue as catalogue
from scripts.run_test_lanes import LANES, LaneError
from scripts.select_ci_scope import ALL_LANES


def test_committed_lanes_cover_recursive_inventory_exactly_once() -> None:
    discovered = runner.discover_test_modules()
    runner.validate_lane_inventory(discovered)

    assigned = [module for lane in LANES for module in lane.modules]
    assert len(LANES) == 17
    assert all(lane.requires_postgres for lane in LANES)
    assert Counter(assigned)[catalogue.SCHEMA_MODULE] == 1
    assert all(
        count
        == (
            len(catalogue.PARTITION_LANES_BY_MODULE[module])
            if module in catalogue.PARTITION_LANES_BY_MODULE
            else 1
        )
        for module, count in Counter(assigned).items()
    )
    assert set(assigned) == set(discovered)
    assert runner.ADMIN_RUNNER_MODULE in next(
        lane.modules for lane in LANES if lane.name == "schema_contracts"
    )


def test_architecture_inspections_share_capacity_without_losing_nodes() -> None:
    modules = {
        "tests/test_artifact_architecture.py",
        "tests/architecture/test_module_boundaries.py",
        "tests/architecture/test_test_structure_boundary.py",
    }
    schema = next(lane for lane in LANES if lane.name == "schema_contracts")
    assert modules.isdisjoint(schema.modules)
    for module in modules:
        assert catalogue.PARTITION_LANES_BY_MODULE[module] == catalogue.PARTITIONED_SHARED_LANES
        assert (
            tuple(lane.name for lane in LANES if module in lane.modules)
            == catalogue.PARTITIONED_SHARED_LANES
        )
    nodes = [f"{module}::test_inspection[{index}]" for module in modules for index in range(256)]
    manifest = runner.build_manifest("a" * 40, list(reversed(nodes)))
    assert Counter(row["nodeid"] for row in manifest["nodes"]) == Counter(nodes)
    assert {row["lane"] for row in manifest["nodes"]} == set(catalogue.PARTITIONED_SHARED_LANES)
    assert runner.build_manifest("a" * 40, nodes) == manifest


def test_checker_delivery_and_routing_preparation_partition_every_node_once() -> None:
    delivery = {
        "tests/checkers/default/test_contract.py",
        "tests/checkers/default/test_execution.py",
        "tests/checkers/external/test_contracts.py",
        "tests/checkers/external/test_migration.py",
        "tests/checkers/external/test_postgresql.py",
        "tests/checkers/external/test_public_api.py",
        "tests/checkers/external/test_registry.py",
        "tests/checkers/external/test_runtime.py",
        "tests/checkers/external/test_policy.py",
        "tests/checkers/external/test_selected_post_submit.py",
        "tests/checkers/external/test_selected_pre_submit.py",
        "tests/checkers/external/test_selected_pre_submit_coordination.py",
        "tests/checkers/external/test_selected_pre_submit_service.py",
        "tests/checkers/external/test_selected_preparation_command.py",
        "tests/checkers/execution/test_execution.py",
        "tests/checkers/execution/test_completion_evidence.py",
        "tests/checkers/execution/test_coordination.py",
        "tests/checkers/execution/test_concurrency.py",
        "tests/checkers/execution/test_storage.py",
        "tests/checkers/execution/test_migration.py",
        "tests/checkers/execution/test_material_lineage.py",
        "tests/checkers/execution/test_material_migration.py",
        "tests/checkers/execution/test_checker_retry.py",
        "tests/checkers/execution/test_checker_retry_authority.py",
        "tests/checkers/execution/test_checker_retry_history_replay.py",
        "tests/checkers/execution/test_checker_retry_http.py",
        "tests/checkers/execution/test_checker_retry_migration.py",
        "tests/checkers/execution/test_delivery_reconciliation_concurrency.py",
        "tests/checkers/execution/test_delivery_reconciliation_contract.py",
        "tests/checkers/execution/test_delivery_reconciliation_custody.py",
        "tests/checkers/execution/test_delivery_reconciliation_public.py",
        "tests/test_post_submit_materialization.py",
        "tests/test_post_submit_selection.py",
        "tests/test_checker_output_custody.py",
        "tests/test_checker_output_storage.py",
    }
    assert set(catalogue.CHECKER_DELIVERY_MODULES) == delivery
    groups = (
        delivery,
        set(catalogue.ROUTING_AUTH_PREPARATION_MODULES),
    )
    for modules in groups:
        assert not modules & set(catalogue.TASK_MODULES)
        assert all(
            catalogue.PARTITION_LANES_BY_MODULE[module] == catalogue.PARTITIONED_PROJECT_LANES
            for module in modules
        )
        for module in modules:
            assert (
                tuple(lane.name for lane in LANES if module in lane.modules)
                == catalogue.PARTITIONED_PROJECT_LANES
            )
        nodes = [f"{module}::test_custody[{index}]" for module in modules for index in range(256)]
        manifest = runner.build_manifest("a" * 40, list(reversed(nodes)))
        assert len(manifest["nodes"]) == len(nodes)
        assert {row["nodeid"] for row in manifest["nodes"]} == set(nodes)
        assert {row["lane"] for row in manifest["nodes"]} == set(
            catalogue.PARTITIONED_PROJECT_LANES
        )


def test_project_intake_partitions_across_the_project_family() -> None:
    expected = {
        "tests/test_guide_document_intake.py",
        "tests/test_projects.py",
    }
    assert set(catalogue.PROJECT_INTAKE_MODULES) == expected
    assert not expected & set(catalogue.PROJECT_MODULES)
    assert catalogue.PARTITION_LANES_BY_MODULE["tests/test_guide_document_intake.py"] == (
        catalogue.PARTITIONED_PROJECT_LANES
    )
    assert catalogue.PARTITION_LANES_BY_MODULE["tests/test_projects.py"] == (
        "project_lifecycle_c",
        "project_lifecycle_b",
        "project_lifecycle_g",
        "project_lifecycle_f",
    )

    for module in expected:
        assert {lane.name for lane in LANES if module in lane.modules} == set(
            catalogue.PARTITION_LANES_BY_MODULE[module]
        )

    nodes = [f"{module}::test_owned[{index}]" for module in expected for index in range(256)]
    manifest = runner.build_manifest("a" * 40, list(reversed(nodes)))
    assert {row["nodeid"] for row in manifest["nodes"]} == set(nodes)
    assert {row["lane"] for row in manifest["nodes"]} == set(catalogue.PARTITIONED_PROJECT_LANES)


def test_expanded_lane_families_keep_exact_semantic_owners() -> None:
    """Every capacity lane retains its exact semantic-family ownership."""
    modules_by_lane = {lane.name: set(lane.modules) for lane in LANES}

    expected_families = (
        (
            (
                "shared_foundations_a",
                "shared_foundations_b",
                "shared_foundations_c",
            ),
            catalogue.SHARED_FOUNDATION_MODULES,
        ),
        (
            (
                "project_lifecycle_a",
                "project_lifecycle_b",
                "project_lifecycle_c",
                "project_lifecycle_d",
                "project_lifecycle_e",
                "project_lifecycle_f",
                "project_lifecycle_g",
            ),
            catalogue.PROJECT_PARTITIONED_MODULES,
        ),
        (
            (
                "task_lifecycle_a",
                "task_lifecycle_b",
                "task_lifecycle_c",
                "task_lifecycle_d",
                "task_lifecycle_e",
            ),
            catalogue.TASK_MODULES,
        ),
    )
    assert catalogue.PARTITION_GROUPS == tuple(
        (lane_names, modules) for lane_names, modules in expected_families
    )
    for lane_names, modules in expected_families:
        for name in lane_names:
            assert modules_by_lane[name] == {
                module for module in modules if name in catalogue.PARTITION_LANES_BY_MODULE[module]
            }
        assert all(catalogue.PARTITION_LANES_BY_MODULE[module] for module in modules)
        assert all(
            set(catalogue.PARTITION_LANES_BY_MODULE[module]) <= set(lane_names)
            for module in modules
        )

    schema_static_contracts = {
        "tests/test_ci_lane_catalogue.py",
        "tests/test_ci_scope_selection.py",
        "tests/test_ci_test_lanes.py",
        "tests/test_test_lane_evidence.py",
        "tests/test_merge_test_lane_evidence.py",
    }
    partitioned_modules = set().union(*(set(modules) for _, modules in expected_families))
    assert set(catalogue.STATIC_FOUNDATION_MODULES) <= set(catalogue.SHARED_FOUNDATION_MODULES)
    assert schema_static_contracts.isdisjoint(partitioned_modules)
    assert {
        "tests/test_alembic.py",
        "tests/migrations/test_project_catalogue_read.py",
        "tests/migrations/test_contribution_export_snapshots.py",
        "tests/migrations/test_contribution_read_audit.py",
        "tests/test_database_reset.py",
        "tests/authorization/post_submit/test_receipt_custody.py",
        "tests/authorization/post_submit/test_migration.py",
        "tests/reviews/packet/test_storage.py",
        "tests/reviews/lifecycle/test_contracts.py",
        "tests/reviews/lifecycle/test_storage.py",
        "tests/reviews/lifecycle/test_transition_storage.py",
        "tests/reviews/lifecycle/test_fence.py",
        "tests/reviews/lifecycle/test_migration.py",
        "tests/reviews/acceptance/test_contracts.py",
        "tests/reviews/acceptance/test_storage.py",
        "tests/reviews/acceptance/test_migration.py",
        runner.ADMIN_RUNNER_MODULE,
    } | schema_static_contracts | set(catalogue.OBSERVABILITY_MODULES) | set(
        catalogue.TASK_ROUTING_REQUEST_MODULES
    ) == modules_by_lane["schema_contracts"]


def test_static_architecture_inventory_partitions_only_in_shared_foundations() -> None:
    expected = {
        "tests/test_artifact_architecture.py",
        "tests/architecture/test_module_boundaries.py",
        "tests/architecture/test_authorization_boundary.py",
        "tests/architecture/test_test_structure_boundary.py",
        "tests/test_identifier_inventory.py",
        "tests/test_record_id_collection.py",
    }
    assert set(catalogue.STATIC_FOUNDATION_MODULES) == expected
    assert all(
        catalogue.PARTITION_LANES_BY_MODULE[module] == catalogue.PARTITIONED_SHARED_LANES
        for module in expected
    )
    assert all(
        tuple(lane.name for lane in LANES if module in lane.modules)
        == catalogue.PARTITIONED_SHARED_LANES
        for module in expected
    )

    nodes = [f"{module}::test_owned[{index}]" for module in expected for index in range(256)]
    rows = runner.build_manifest("a" * 40, list(reversed(nodes)))["nodes"]

    assert Counter(row["nodeid"] for row in rows) == Counter(nodes)
    assert {row["lane"] for row in rows} == set(catalogue.PARTITIONED_SHARED_LANES)


def test_semantic_family_membership_has_an_independent_fingerprint() -> None:
    """A catalogue-internal move across semantic families must fail this contract."""
    expected = {
        "shared": (
            261,
            "d903ceb93c8f54c401100a58226909458c4d41d10fd618421d8d0d1ec78f0c07",
        ),
        "project": (
            213,
            "3c2477009349137e7aefd268294a811c16ee8b2ffff23d5aa513f4b479b1889d",
        ),
        "task": (
            95,
            "76d96db74da2aecac74466fe118af5ed92ce7d8d9620b68e5790e87c3978aad1",
        ),
    }
    actual = {
        "shared": catalogue.SHARED_FOUNDATION_MODULES,
        "project": catalogue.PROJECT_PARTITIONED_MODULES,
        "task": catalogue.TASK_MODULES,
    }
    for family, modules in actual.items():
        count, digest = expected[family]
        canonical = "\n".join(sorted(modules)) + "\n"
        assert len(modules) == len(set(modules)) == count
        assert hashlib.sha256(canonical.encode()).hexdigest() == digest


def test_project_module_lane_overrides_are_exact_and_bounded() -> None:
    expected = {
        "tests/test_projects.py": (
            "project_lifecycle_c",
            "project_lifecycle_b",
            "project_lifecycle_g",
            "project_lifecycle_f",
        ),
        "tests/tasks/test_task_batch_transitions.py": (
            "project_lifecycle_e",
            "project_lifecycle_d",
            "project_lifecycle_a",
            "project_lifecycle_b",
            "project_lifecycle_c",
        ),
        "tests/tasks/submission_dispatch/test_revision_clock_sql.py": ("project_lifecycle_f",),
        "tests/tasks/submission_dispatch/test_revision_retained_pause.py": (
            "project_lifecycle_a",
            "project_lifecycle_c",
            "project_lifecycle_g",
        ),
        "tests/tasks/submission_dispatch/test_revision_pause_races.py": (
            "project_lifecycle_a",
            "project_lifecycle_c",
            "project_lifecycle_e",
            "project_lifecycle_f",
        ),
        "tests/tasks/submission_dispatch/test_revision_exhaustion.py": ("project_lifecycle_g",),
        "tests/tasks/submission_dispatch/test_revision_expiry.py": (
            "project_lifecycle_a",
            "project_lifecycle_e",
            "project_lifecycle_c",
            "project_lifecycle_b",
            "project_lifecycle_d",
        ),
    }
    assert catalogue.PROJECT_MODULE_LANE_OVERRIDES == expected
    assert set(expected) <= set(catalogue.PROJECT_PARTITIONED_MODULES)
    assert all(
        catalogue.PARTITION_LANES_BY_MODULE[module]
        == expected.get(module, catalogue.PARTITIONED_PROJECT_LANES)
        for module in catalogue.PROJECT_PARTITIONED_MODULES
    )


def test_project_lane_ownership_has_an_independent_fingerprint() -> None:
    canonical = (
        "\n".join(
            f"{module}:{','.join(catalogue.PARTITION_LANES_BY_MODULE[module])}"
            for module in sorted(catalogue.PROJECT_PARTITIONED_MODULES)
        )
        + "\n"
    )
    assert len(catalogue.PROJECT_PARTITIONED_MODULES) == 213
    assert hashlib.sha256(canonical.encode()).hexdigest() == (
        "41e0285a424449b5d639407cfd4ca5a4ac1065baa8057198417274d310adc3a8"
    )


def test_project_lane_override_nodes_execute_exactly_once_in_owned_lanes() -> None:
    nodes = [
        f"{module}::test_owned_{index}"
        for module in catalogue.PROJECT_MODULE_LANE_OVERRIDES
        for index in range(256)
    ]
    rows = runner.build_manifest("a" * 40, list(reversed(nodes)))["nodes"]

    assert Counter(row["nodeid"] for row in rows) == Counter(nodes)
    assert len(rows) == len(nodes)
    for module, lane_names in catalogue.PROJECT_MODULE_LANE_OVERRIDES.items():
        assert {row["lane"] for row in rows if row["module"] == module} == set(lane_names)
    pause_module = "tests/tasks/submission_dispatch/test_revision_pause_races.py"
    retained_module = "tests/tasks/submission_dispatch/test_revision_retained_pause.py"
    expected = {
        f"{pause_module}::test_due_old_timer_cannot_expire_paused_or_resumed_head[False]": (
            "project_lifecycle_e"
        ),
        f"{pause_module}::test_due_old_timer_cannot_expire_paused_or_resumed_head[True]": (
            "project_lifecycle_c"
        ),
        f"{pause_module}::test_expiry_beats_real_pm_repair_waiting_for_task_past_deadline": (
            "project_lifecycle_f"
        ),
        f"{retained_module}::test_retained_blocked_clock_pauses_once_or_stays_due[False]": (
            "project_lifecycle_a"
        ),
        f"{retained_module}::test_retained_blocked_clock_pauses_once_or_stays_due[True]": (
            "project_lifecycle_g"
        ),
        "tests/tasks/submission_dispatch/test_revision_expiry.py::test_due_expiry_and_ready_final_submission_wait_for_task_lock": (
            "project_lifecycle_b"
        ),
        "tests/tasks/submission_dispatch/test_revision_expiry.py::test_final_submission_commit_boundary_serializes_expiry[False]": (
            "project_lifecycle_a"
        ),
        "tests/tasks/submission_dispatch/test_revision_expiry.py::test_final_submission_commit_boundary_serializes_expiry[True]": (
            "project_lifecycle_c"
        ),
        "tests/tasks/test_task_batch_transitions.py::test_public_source_import_screen_release_complete_journey[500]": (
            "project_lifecycle_a"
        ),
        "tests/tasks/test_task_batch_transitions.py::test_public_source_import_screen_release_complete_journey[200]": (
            "project_lifecycle_b"
        ),
        "tests/test_projects.py::test_submission_artifact_policy_removed_agent_route_performs_no_runtime_calls": (
            "project_lifecycle_g"
        ),
        "tests/test_projects.py::test_submission_artifact_policy_update_conceals_foreign_policy_id": (
            "project_lifecycle_g"
        ),
        "tests/test_projects.py::test_submission_artifact_policy_update_fault_rolls_back_replacement": (
            "project_lifecycle_c"
        ),
        "tests/test_projects.py::test_sufficiency_report_rejects_unknown_request_fields": (
            "project_lifecycle_f"
        ),
        "tests/test_projects.py::test_unified_warnings_do_not_use_the_manual_report_acknowledgement_path": (
            "project_lifecycle_f"
        ),
        "tests/test_projects.py::test_worker_cannot_create_project_records": (
            "project_lifecycle_b"
        ),
        "tests/tasks/submission_dispatch/test_revision_clock_sql.py::test_direct_sql_cannot_supply_authoritative_clock_values": (
            "project_lifecycle_f"
        ),
        "tests/tasks/submission_dispatch/test_revision_clock_sql.py::test_large_revision_allowance_preserves_every_microsecond": (
            "project_lifecycle_f"
        ),
        "tests/tasks/submission_dispatch/test_revision_clock_sql.py::test_pause_cannot_commit_after_running_parent_deadline": (
            "project_lifecycle_f"
        ),
    }
    rows = runner.build_manifest("a" * 40, list(reversed(expected)))["nodes"]

    assert {row["nodeid"]: row["lane"] for row in rows} == expected


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
        for index in range(len(catalogue.PARTITIONED_SHARED_LANES)):
            lanes[index] = replace(lanes[index], modules=lanes[index].modules[1:])
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
    ("names", "modules"),
    catalogue.PARTITION_GROUPS,
    ids=("shared", "project", "task"),
)
def test_owner_nodes_partition_deterministically(names, modules) -> None:
    module = modules[0]
    nodes = [f"{module}::test_shared_{index}" for index in range(100)]

    first = runner.build_manifest("a" * 40, nodes)
    second = runner.build_manifest("b" * 40, list(reversed(nodes)))
    first_by_node = {row["nodeid"]: row["lane"] for row in first["nodes"]}
    second_by_node = {row["nodeid"]: row["lane"] for row in second["nodes"]}

    assert first_by_node == second_by_node
    assert set(first_by_node.values()) == set(names)
    assert set(first_by_node) == set(nodes)
    assert len(first["nodes"]) == len(nodes)


def test_task_nodes_have_one_partition_owner() -> None:
    nodes = [
        f"{module}::test_task_{index}" for module in catalogue.TASK_MODULES for index in range(10)
    ]
    assert all(
        catalogue.PARTITION_LANES_BY_MODULE[module] == catalogue.PARTITIONED_TASK_LANES
        for module in catalogue.TASK_MODULES
    )
    first = runner.build_manifest("a" * 40, nodes)
    assert first == runner.build_manifest("a" * 40, list(reversed(nodes)))
    partitions = {
        name: {row["nodeid"] for row in first["nodes"] if row["lane"] == name}
        for name in catalogue.PARTITIONED_TASK_LANES
    }
    assert all(partitions.values())
    owners = Counter(node for partition in partitions.values() for node in partition)
    assert owners == Counter(nodes)
    assert len(first["nodes"]) == len(nodes)
    assert [row["nodeid"] for row in first["nodes"]] == sorted(nodes)


@pytest.mark.parametrize("missing", catalogue.PARTITIONED_TASK_LANES)
def test_any_missing_task_partition_rejects_inventory(missing) -> None:
    lanes = tuple(lane for lane in LANES if lane.name != missing)
    with pytest.raises(LaneError, match="invalid_lane_names"):
        runner.validate_lane_inventory(runner.discover_test_modules(), lanes=lanes)


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
    task_index = next(i for i, lane in enumerate(lanes) if lane.name == "task_lifecycle_a")
    project, task = lanes[project_index], lanes[task_index]
    lanes[project_index] = replace(project, name=task.name)
    lanes[task_index] = replace(task, name=project.name)
    # Counts alone still pass: the counterexample changes owner names, not inventory.
    runner.validate_lane_inventory(runner.discover_test_modules(), lanes=tuple(lanes))
    monkeypatch.setattr(runner, "LANES", tuple(lanes))
    with pytest.raises(LaneError, match="invalid_partition_lanes"):
        runner.build_manifest("a" * 40, [f"{project.modules[0]}::test_one"])


def test_partition_accepts_exact_noncanonical_owner_order() -> None:
    module = "tests/tasks/test_task_batch_transitions.py"
    declared = catalogue.PARTITION_LANES_BY_MODULE[module]
    attached = tuple(lane.name for lane in LANES if module in lane.modules)

    assert declared == (
        "project_lifecycle_e",
        "project_lifecycle_d",
        "project_lifecycle_a",
        "project_lifecycle_b",
        "project_lifecycle_c",
    )
    assert attached == catalogue.PARTITIONED_PROJECT_LANES[:5]
    node = f"{module}::test_public_source_import_screen_release_complete_journey[500]"
    assert runner.build_manifest("a" * 40, [node])["nodes"][0]["lane"] == declared[2]


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "foreign"))
def test_partition_rejects_inexact_ordered_owners(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    module = catalogue.PROJECT_MODULES[0]
    owners = catalogue.PARTITION_LANES_BY_MODULE[module]
    changed = {
        "missing": owners[:-1],
        "duplicate": (*owners[:-1], owners[0]),
        "foreign": (*owners[:-1], "schema_contracts"),
    }[mutation]
    monkeypatch.setitem(runner.PARTITION_LANES_BY_MODULE, module, changed)

    with pytest.raises(LaneError, match="invalid_partition_lanes"):
        runner.build_manifest("a" * 40, [f"{module}::test_one"])


def test_partition_rejects_coordinated_duplicate_owners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = "tests/tasks/submission_dispatch/test_revision_retained_pause.py"
    duplicate_owners = (
        "project_lifecycle_a",
        "project_lifecycle_a",
        "project_lifecycle_c",
    )
    changed = tuple(
        replace(
            lane,
            modules=tuple(item for item in lane.modules if item != module)
            + (module,) * duplicate_owners.count(lane.name),
        )
        for lane in LANES
    )
    monkeypatch.setitem(runner.PARTITION_LANES_BY_MODULE, module, duplicate_owners)
    monkeypatch.setattr(runner, "LANES", changed)
    runner.validate_lane_inventory(runner.discover_test_modules(), lanes=changed)

    with pytest.raises(LaneError, match="invalid_partition_lanes"):
        runner.build_manifest("a" * 40, [f"{module}::test_one"])


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
    assert ALL_LANES == tuple(lane.name for lane in LANES)
    assert source.count("matrix: ${{ fromJSON(needs.scope.outputs.lane_matrix) }}") == 1
    assert (
        source.count(
            "name: backend-lane-${{ github.sha }}-${{ matrix.lane }}-attempt-${{ github.run_attempt }}"
        )
        == 1
    )
    assert source.count("pattern: backend-lane-${{ github.sha }}-*-attempt-*") == 1
    assert source.count("path: backend/.ci/download\n          merge-multiple: false") == 1
    assert '--expected-head "${GITHUB_SHA}"' in source
    assert '--run-attempt "${GITHUB_RUN_ATTEMPT}"' in source
    assert 'test "${#coverage_files[@]}" -eq 17' in source
    assert "len(lanes) != 17" in source
    assert 'Path(".ci/download"), expected_head, int(os.environ["GITHUB_RUN_ATTEMPT"])' in source
    assert 'timing_path = bundle / "job-start-epoch.txt"' in source
    assert (
        "name: backend-semantic-lane-evidence-${{ steps.identity.outputs.tree_sha }}-attempt-${{ github.run_attempt }}"
        in source
    )


def test_workflow_requires_the_locked_external_checker_workspace() -> None:
    source = (runner.ROOT.parent / ".github/workflows/backend.yml").read_text()
    assert source.count("external-checker-runtime:") == 1
    assert "rustup toolchain install 1.84.0 --profile minimal --component rustfmt" in source
    assert "cargo fmt --all --check" in source
    assert "cargo test --workspace --locked -- --test-threads=1" in source
    assert "EXTERNAL_CHECKER_RESULT: ${{ needs.external-checker-runtime.result }}" in source
    assert 'require_expected "${EXTERNAL_EXPECTED}" "${EXTERNAL_CHECKER_RESULT}"' in source


def test_former_coverage_reruns_remain_in_full_suite_lanes() -> None:
    """Removing duplicate executions must not remove their behavior tests."""
    required = {
        "tests/projects/guide_compilation/finalization/test_contracts.py",
        "tests/projects/guide_compilation/finalization/test_lineage.py",
        "tests/projects/guide_compilation/finalization/test_replay.py",
        "tests/projects/guide_compilation/finalization/test_service.py",
        "tests/projects/guide_compilation/finalization/test_structure.py",
        "tests/projects/submission_policy_mutations/test_authority.py",
        "tests/projects/submission_policy_mutations/test_commands.py",
        "tests/projects/submission_policy_mutations/test_lineage.py",
        "tests/projects/submission_policy_mutations/test_public_routes.py",
        "tests/projects/submission_policy_mutations/test_replay.py",
        "tests/projects/submission_policy_mutations/test_repository.py",
        "tests/projects/sufficiency_mutations/test_acknowledgement.py",
        "tests/projects/sufficiency_mutations/test_authority.py",
        "tests/projects/sufficiency_mutations/test_lineage.py",
        "tests/projects/sufficiency_mutations/test_public_routes.py",
        "tests/projects/sufficiency_mutations/test_replay.py",
        "tests/projects/sufficiency_mutations/test_replay_repository.py",
        "tests/projects/sufficiency_mutations/test_report_create.py",
        "tests/projects/test_active_guide_read_composition.py",
        "tests/projects/test_diagnostic_read_composition.py",
        "tests/projects/test_diagnostic_read_rejections.py",
        "tests/projects/test_policy_read_composition.py",
    }
    assert required <= set(catalogue.PROJECT_MODULES)


def test_coverage_is_diagnostic_not_a_percentage_gate() -> None:
    root = runner.ROOT.parent
    for name in ("backend", "mcp"):
        workflow = (root / f".github/workflows/{name}.yml").read_text()
        assert "fail-under" not in workflow
    backend = (root / ".github/workflows/backend.yml").read_text()
    # Each selected test executes in its lane, not in a second quota-only run.
    assert "COVERAGE_FILE=.coverage-" not in backend
    assert "coverage run --append -m pytest" not in backend
    assert "coverage report --precision=2" in backend
    assert "or percent < 0" in backend


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


@pytest.mark.parametrize(
    "addition",
    (
        "backend/app/adapters/observability.py",
        "backend/app/core/celery_observability.py",
        "backend/app/core/diagnostic_logging.py",
        "backend/app/core/observability.py",
        "backend/app/interfaces/observability.py",
    ),
)
def test_observability_partition_additions_are_exact(addition: str) -> None:
    from scripts import behavior_ownership as ownership

    authority = {
        "schema": ownership.PARTITION_SCHEMA,
        "protected_base_commit": "a" * 40,
        "assignments": [{"group": "shared", "target": "backend/app/core/config.py"}],
    }
    trusted = {**authority, "authority_digest": ownership._digest(authority)}
    current = {
        **trusted,
        "assignments": [*authority["assignments"], {"group": "shared", "target": addition}],
    }
    ownership._validate_additive_partition_transition(current, trusted)


def test_finalization_tests_are_all_in_project_lanes():
    from scripts.test_lane_catalogue import PROJECT_MODULES

    root = Path(__file__).resolve().parent
    expected = {
        str(path.relative_to(root.parent))
        for path in (root / "projects/guide_compilation/finalization").glob("test_*.py")
    }
    assert expected
    assert expected <= set(PROJECT_MODULES)


def test_routing_request_proofs_use_schema_lane_with_measured_headroom():
    expected = {
        "tests/tasks/post_submit_routing/test_request_contracts.py",
        "tests/tasks/post_submit_routing/test_requests.py",
        "tests/tasks/post_submit_routing/test_request_storage.py",
    }
    assert set(catalogue.TASK_ROUTING_REQUEST_MODULES) == expected
    for lane in LANES:
        assert set(lane.modules) & expected == (
            expected if lane.name == "schema_contracts" else set()
        )
    assert not expected & set(catalogue.PARTITION_LANES_BY_MODULE)


def test_observability_proofs_use_schema_lane_with_measured_headroom():
    expected = {
        "tests/test_observability.py",
        "tests/test_observability_otlp.py",
        "tests/test_celery_observability.py",
    }
    assert set(catalogue.OBSERVABILITY_MODULES) == expected
    for lane in LANES:
        assert set(lane.modules) & expected == (
            expected if lane.name == "schema_contracts" else set()
        )
    assert not expected & set(catalogue.PARTITION_LANES_BY_MODULE)


def test_routing_authorization_proofs_use_the_project_partition():
    expected = {
        "tests/authorization/post_submit_routing/test_contracts.py",
        "tests/authorization/post_submit_routing/test_prepared.py",
    }
    assert set(catalogue.ROUTING_AUTH_PREPARATION_MODULES) == expected
    for module in expected:
        assert catalogue.PARTITION_LANES_BY_MODULE[module] == catalogue.PARTITIONED_PROJECT_LANES
        assert tuple(lane.name for lane in LANES if module in lane.modules) == (
            catalogue.PARTITIONED_PROJECT_LANES
        )


def test_shared_acceptance_owner_proofs_are_in_partitioned_project_lanes():
    expected = {
        "tests/reviews/acceptance/test_participant_contracts.py",
        "tests/reviews/acceptance/test_participation.py",
        "tests/reviews/acceptance/test_participation_transactions.py",
        "tests/tasks/accepted_effects/test_contracts.py",
        "tests/tasks/accepted_effects/test_postgresql.py",
    }
    assert expected <= set(catalogue.PROJECT_MODULES)
    assert all(
        catalogue.PARTITION_LANES_BY_MODULE[path] == catalogue.PARTITIONED_PROJECT_LANES
        for path in expected
    )


def test_evaluation_custody_proofs_use_project_lane_headroom():
    expected = {
        "tests/tasks/post_submit_routing/test_evaluation_guard.py",
        "tests/tasks/post_submit_routing/test_evaluation_currentness.py",
        "tests/tasks/post_submit_routing/test_review_admission_currentness.py",
        "tests/tasks/post_submit_routing/test_source_preparation.py",
    }
    assert expected <= set(catalogue.PROJECT_MODULES)
    assert all(
        catalogue.PARTITION_LANES_BY_MODULE[path] == catalogue.PARTITIONED_PROJECT_LANES
        for path in expected
    )
