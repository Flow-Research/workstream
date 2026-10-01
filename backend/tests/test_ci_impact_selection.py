"""Regressions for the observational backend impact recommendation."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import scripts.test_impact_selection as selector
from scripts.test_impact_selection import ALL_LANES, classify
from scripts.test_lane_catalogue import LANES, PARTITIONED_SHARED_LANES

ROOT = Path(__file__).resolve().parents[2]
IMPACT_MAP = json.loads((ROOT / ".ci/test-impact/impact_map.json").read_text())


def test_exact_s3_owner_recommends_both_shared_partitions() -> None:
    selected, _ = classify(["backend/app/core/s3_validation.py"], IMPACT_MAP)

    assert selected == list(PARTITIONED_SHARED_LANES)


def test_committrail_only_recommends_shared_semantics_partitions() -> None:
    selected, _ = classify([".commitrail/changes/ci-example.md"], IMPACT_MAP)

    assert selected == list(PARTITIONED_SHARED_LANES)


def test_mapped_source_and_test_changes_union_their_lane_closures() -> None:
    selected, _ = classify(
        [
            "backend/app/core/s3_validation.py",
            "backend/tests/test_projects.py",
        ],
        IMPACT_MAP,
    )

    assert set(PARTITIONED_SHARED_LANES) <= set(selected)
    assert {"project_lifecycle_a", "project_lifecycle_b", "project_lifecycle_c"} <= set(selected)


def test_changed_test_module_selects_every_partition_that_owns_it() -> None:
    owners = tuple(
        lane.name for lane in LANES if "tests/test_s3_artifact_store.py" in lane.modules
    )

    selected, _ = classify(["backend/tests/test_s3_artifact_store.py"], IMPACT_MAP)

    assert owners == PARTITIONED_SHARED_LANES
    assert selected == list(owners)


def test_unknown_source_fixture_and_unmapped_test_fail_safe_to_all_lanes() -> None:
    for path in (
        "backend/app/modules/tasks/service.py",
        "backend/tests/conftest.py",
        "backend/tests/test_not_in_catalogue.py",
        "docs/operations_backend_testing.md",
        ".ci/test-impact/impact_map.json",
        "backend/scripts/test_impact_selection.py",
        "backend/scripts/test_lane_catalogue.py",
        ".github/workflows/backend.yml",
    ):
        selected, _ = classify([path], IMPACT_MAP)
        assert selected == list(ALL_LANES), path


def test_mixed_known_and_unknown_paths_fail_safe_to_all_lanes() -> None:
    selected, reasons = classify(
        ["backend/app/core/s3_validation.py", "backend/requirements.lock"], IMPACT_MAP
    )

    assert selected == list(ALL_LANES)
    assert all("no reviewed impact mapping" in ";".join(reasons[lane]) for lane in ALL_LANES)


def test_empty_path_list_recommends_every_lane() -> None:
    selected, _ = classify([], IMPACT_MAP)

    assert selected == list(ALL_LANES)


def test_report_binds_execution_tree_and_exact_pr_merge_parents() -> None:
    base = "a" * 40
    head = "b" * 40
    execution = "c" * 40
    tree = "d" * 40

    def resolve_commit(ref: str, *, repository_root: Path) -> str:
        assert repository_root == ROOT
        if ref == "HEAD":
            return execution
        if ref == base:
            return base
        if ref == head:
            return head
        raise AssertionError(ref)

    def run_checked(command: list[str], *, repository_root: Path) -> str:
        assert repository_root == ROOT
        if command == ["git", "rev-parse", f"{execution}^{{tree}}"]:
            return tree
        if command == ["git", "show", "-s", "--format=%P", execution]:
            return f"{base} {head}"
        raise AssertionError(command)

    with (
        patch.object(selector, "resolve_commit", side_effect=resolve_commit),
        patch.object(selector, "run_checked", side_effect=run_checked),
        patch.object(selector, "resolve_merge_base", return_value=base),
        patch.object(selector, "run_checked_bytes", return_value=b".commitrail/change.md\0"),
    ):
        report = selector.build_report(base, head, execution)

    assert report["base_sha"] == base
    assert report["head_sha"] == head
    assert report["execution_sha"] == execution
    assert report["execution_tree_sha"] == tree
    assert report["merge_base"] == base
    assert report["changed_paths"] == [".commitrail/change.md"]
    assert report["changed_paths_sha256"] == selector._sha256(b".commitrail/change.md")
    assert report["selector_sha256"] == selector._sha256(
        selector.SCRIPT_PATH.read_bytes()
    )
    assert report["impact_map_sha256"] == selector._sha256(
        selector.MAP_PATH.read_bytes()
    )
    assert report["lane_catalogue_sha256"] == selector._sha256(
        selector.CATALOGUE_PATH.read_bytes()
    )
    assert report["selected_lanes"] == list(PARTITIONED_SHARED_LANES)
    assert report["lanes"][0]["reasons"] == [
        ".commitrail/change.md: Commitrail policy semantics are tested in the shared-foundation partition."
    ]
    assert report["lanes"][1]["reasons"] == report["lanes"][0]["reasons"]
    assert all(
        lane["omission_reason"]
        for lane in report["lanes"]
        if not lane["selected"]
    )


def test_report_rejects_execution_commit_with_stale_pr_parents() -> None:
    base = "a" * 40
    head = "b" * 40
    execution = "c" * 40

    def resolve_commit(ref: str, *, repository_root: Path) -> str:
        if ref == "HEAD":
            return execution
        raise AssertionError(ref)

    def run_checked(command: list[str], *, repository_root: Path) -> str:
        if command == ["git", "rev-parse", f"{execution}^{{tree}}"]:
            return "d" * 40
        if command == ["git", "show", "-s", "--format=%P", execution]:
            return f"{base} {'e' * 40}"
        raise AssertionError(command)

    with (
        patch.object(selector, "resolve_commit", side_effect=resolve_commit),
        patch.object(selector, "run_checked", side_effect=run_checked),
    ):
        try:
            selector.build_report(base, head, execution)
        except selector.SelectionError as exc:
            assert "not the exact PR base/head merge" in str(exc)
        else:
            raise AssertionError("stale target accepted")


def test_classifier_failure_preserves_exact_target_and_changed_path_evidence() -> None:
    base = "a" * 40
    head = "b" * 40
    execution = "c" * 40
    tree = "d" * 40
    path = "backend/app/core/s3_validation.py"

    def resolve_commit(ref: str, *, repository_root: Path) -> str:
        del repository_root
        return {"HEAD": execution, base: base, head: head}[ref]

    def run_checked(command: list[str], *, repository_root: Path) -> str:
        del repository_root
        if command[1] == "rev-parse":
            return tree
        if command[1] == "show":
            return f"{base} {head}"
        raise AssertionError(command)

    with (
        patch.object(selector, "resolve_commit", side_effect=resolve_commit),
        patch.object(selector, "run_checked", side_effect=run_checked),
        patch.object(selector, "resolve_merge_base", return_value=base),
        patch.object(selector, "run_checked_bytes", return_value=f"{path}\0".encode()),
        patch.object(selector, "classify", side_effect=selector.SelectionError("bad map")),
    ):
        report = selector.build_report(base, head, execution)

    assert report["classification_status"] == "fallback_all_lanes"
    assert report["base_sha"] == base
    assert report["head_sha"] == head
    assert report["execution_sha"] == execution
    assert report["execution_tree_sha"] == tree
    assert report["merge_base"] == base
    assert report["changed_paths"] == [path]
    assert report["changed_paths_sha256"] == selector._sha256(path.encode())
    assert report["selector_sha256"]
    assert report["impact_map_sha256"]
    assert report["lane_catalogue_sha256"]
    assert report["selected_lanes"] == list(ALL_LANES)
    assert report["classification_error"] == "SelectionError: bad map"


def test_markdown_report_escapes_untrusted_paths_and_reasons() -> None:
    injected = "evil`\n\n## Forged status"
    rendered = selector._markdown(
        {
            "base_sha": "base",
            "head_sha": "head",
            "execution_sha": "execution",
            "execution_tree_sha": "tree",
            "merge_base": "merge",
            "selector_version": 1,
            "changed_paths_sha256": "digest",
            "lane_catalogue_sha256": "catalogue",
            "impact_map_sha256": "map",
            "classification_status": "classified",
            "lanes": [
                {"name": "lane", "selected": True, "reasons": [injected]},
            ],
            "changed_paths": [injected],
        }
    )

    assert "\n## Forged status" not in rendered
    assert r"\x60\n\n## Forged status" in rendered


def test_duplicate_or_unsafe_git_paths_fail_classification() -> None:
    with (
        patch.object(selector, "resolve_merge_base", return_value="a" * 40),
        patch.object(selector, "run_checked_bytes", return_value=b"backend/app.py\0backend/app.py\0"),
    ):
        try:
            selector._changed_paths("a" * 40, "b" * 40)
        except selector.SelectionError as exc:
            assert "duplicate paths" in str(exc)
        else:
            raise AssertionError("duplicate Git paths accepted")

    with (
        patch.object(selector, "resolve_merge_base", return_value="a" * 40),
        patch.object(selector, "run_checked_bytes", return_value=b"../outside\0"),
    ):
        try:
            selector._changed_paths("a" * 40, "b" * 40)
        except selector.SelectionError as exc:
            assert "unsafe changed path" in str(exc)
        else:
            raise AssertionError("unsafe Git path accepted")


def test_cli_reports_all_lane_fallback_when_target_evidence_is_unavailable(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "backend/scripts/test_impact_selection.py"),
            "--base",
            "a" * 40,
            "--head",
            "b" * 40,
            "--execution-sha",
            "c" * 40,
            "--json",
            str(report_path),
            "--markdown",
            str(markdown_path),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["classification_status"] == "fallback_all_lanes"
    assert report["selected_lanes"] == list(ALL_LANES)
    assert report["execution_tree_sha"] is None
    assert report["merge_base"] is None
    assert report["changed_paths"] == []
    assert report["changed_paths_sha256"] is None
    assert "selection evidence unavailable" in markdown_path.read_text(encoding="utf-8")


def test_backend_workflow_keeps_report_out_of_lane_execution_control() -> None:
    workflow = (ROOT / ".github/workflows/backend.yml").read_text(encoding="utf-8")
    impact_job = workflow.split("\n  impact-report:\n", 1)[1].split("\n  lanes:\n", 1)[0]
    lane_job = workflow.split("\n  lanes:\n", 1)[1].split("\n  test:\n", 1)[0]
    aggregate_job = workflow.split("\n  test:\n", 1)[1]

    lane_header = lane_job.split("    services:", 1)[0]
    assert "\n    if:" not in lane_header
    assert "impact-report" not in lane_job
    assert "selected_lanes" not in lane_job
    assert "if: ${{ github.event_name == 'pull_request' }}" in impact_job
    assert "backend-test-impact-${{ github.sha }}" in impact_job
    assert "needs: [auth-boundary-preflight, lanes, minio-image]" in aggregate_job
    assert "impact-report" not in aggregate_job
    assert "Require preflight and every semantic lane" in aggregate_job
    assert "API contract real API e2e" in aggregate_job
    api_step = aggregate_job.split("      - name: API contract real API e2e\n", 1)[1].split(
        "\n      - name:", 1
    )[0]
    assert "\n        if:" not in api_step
    assert "scripts/run_isolated_tests.py" in api_step
