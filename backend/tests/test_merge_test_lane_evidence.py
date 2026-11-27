"""Tests for fail-closed distributed semantic-lane fan-in."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from scripts.merge_test_lane_evidence import merge_bundles, select_lane_bundles
from scripts.run_test_lanes import LANES, LaneError


def _write_json(path: Path, value: object) -> str:
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


HEAD = "a" * 40


def _bundle(root: Path, lane: str, attempt: int = 1) -> Path:
    return root / f"backend-lane-{HEAD}-{lane}-attempt-{attempt}"


def _merge(source: Path, metadata: Path, summary: Path, attempt: int = 1) -> None:
    merge_bundles(source, metadata, summary, expected_head=HEAD, run_attempt=attempt)


def _bundles(root: Path) -> None:
    manifest = {
        "head_sha": "a" * 40,
        "nodes": [
            {
                "execution_kind": "ordinary_isolated",
                "lane": lane.name,
                "module": lane.modules[0],
                "nodeid": f"{lane.modules[0]}::test_one",
            }
            for lane in LANES
        ],
        "schema_version": 1,
    }
    for index, lane in enumerate(LANES, 1):
        metadata = _bundle(root, lane.name) / "metadata"
        metadata.mkdir(parents=True)
        manifest_digest = _write_json(metadata / "manifest.json", manifest)
        isolation_name = f"{lane.name}.database.json"
        isolation_digest = _write_json(metadata / isolation_name, {"lane": lane.name})
        evidence_name = f"{lane.name}.json"
        evidence_digest = _write_json(
            metadata / evidence_name,
            {
                "collected_nodes": [f"{lane.modules[0]}::test_one"],
                "completed_nodes": [f"{lane.modules[0]}::test_one"],
                "deselected_nodes": [],
                "isolation_metadata_file": isolation_name,
                "isolation_metadata_sha256": isolation_digest,
                "skipped_nodes": [],
            },
        )
        coverage_name = f".coverage.{lane.name}"
        coverage = f"coverage-{lane.name}".encode()
        (metadata / coverage_name).write_bytes(coverage)
        row = {
            "collection_exit_code": 0,
            "coverage_file": coverage_name,
            "coverage_sha256": hashlib.sha256(coverage).hexdigest(),
            "elapsed_seconds": float(index),
            "evidence_file": evidence_name,
            "evidence_sha256": evidence_digest,
            "execution_exit_code": 0,
            "interrupted": False,
            "name": lane.name,
        }
        _write_json(
            _bundle(root, lane.name) / "summary.json",
            {
                "aggregate_runner_seconds": float(index),
                "canonical_node_count": len(LANES),
                "elapsed_seconds": float(index),
                "head_sha": "a" * 40,
                "lanes": [row],
                "manifest_file": "manifest.json",
                "manifest_sha256": manifest_digest,
                "mode": "lane",
                "schema_version": 1,
                "slowest_lane_seconds": float(index),
            },
        )


def test_merge_bundles_emits_complete_run_summary(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)

    _merge(source, tmp_path / "merged", tmp_path / "summary.json")

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "run"
    assert [row["name"] for row in summary["lanes"]] == [lane.name for lane in LANES]
    assert summary["aggregate_runner_seconds"] == sum(
        float(index) for index in range(1, len(LANES) + 1)
    )
    assert summary["slowest_lane_seconds"] == float(len(LANES))
    assert len(list((tmp_path / "merged").glob(".coverage.*"))) == len(LANES)


@pytest.mark.parametrize("lane_name", ["shared_foundations_a", "shared_foundations_i", "schema_contracts_a", "schema_contracts_b", "schema_contracts_c", "project_lifecycle_d", "project_lifecycle_e", "task_lifecycle_d"])
@pytest.mark.parametrize("damage", ["missing", "foreign"])
def test_merge_bundles_rejects_missing_or_foreign_lane(tmp_path: Path, lane_name: str, damage: str) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    path = _bundle(source, lane_name)
    if damage == "missing":
        shutil.rmtree(path)
    else:
        path.rename(source / "foreign")

    with pytest.raises(LaneError, match="invalid_lane_bundle_set"):
        _merge(source, tmp_path / "merged", tmp_path / "summary.json")


def test_merge_bundles_rejects_coverage_digest_drift(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    lane = LANES[0]
    (_bundle(source, lane.name) / "metadata" / f".coverage.{lane.name}").write_bytes(b"changed")

    with pytest.raises(LaneError, match="invalid_lane_bundle_file"):
        _merge(source, tmp_path / "merged", tmp_path / "summary.json")


def test_merge_bundles_rejects_manifest_path_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    summary_path = _bundle(source, LANES[0].name) / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["manifest_file"] = "../manifest.json"
    _write_json(summary_path, summary)

    with pytest.raises(LaneError, match="invalid_lane_bundle_manifest"):
        _merge(source, tmp_path / "merged", tmp_path / "summary.json")


def test_merge_bundles_rejects_manifest_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    metadata = _bundle(source, LANES[0].name) / "metadata"
    manifest = json.loads((metadata / "manifest.json").read_text(encoding="utf-8"))
    manifest["head_sha"] = "b" * 40
    digest = _write_json(metadata / "manifest.json", manifest)
    summary_path = _bundle(source, LANES[0].name) / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["manifest_sha256"] = digest
    _write_json(summary_path, summary)

    with pytest.raises(LaneError, match="lane_manifest_mismatch"):
        _merge(source, tmp_path / "merged", tmp_path / "summary.json")


def test_merge_bundles_rejects_symlinked_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    lane_root = _bundle(source, LANES[0].name)
    metadata = lane_root / "metadata"
    moved = lane_root / "moved"
    metadata.rename(moved)
    metadata.symlink_to(moved, target_is_directory=True)

    with pytest.raises(LaneError, match="invalid_lane_bundle_metadata"):
        _merge(source, tmp_path / "merged", tmp_path / "summary.json")


def test_merge_bundles_rejects_failed_lane_row(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    summary_path = _bundle(source, LANES[0].name) / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["lanes"][0]["execution_exit_code"] = 1
    _write_json(summary_path, summary)

    with pytest.raises(LaneError, match="lane_bundle_execution_incomplete"):
        _merge(source, tmp_path / "merged", tmp_path / "summary.json")


def test_partial_retry_selects_numeric_latest_before_validation(tmp_path: Path) -> None:
    """Attempt 10 supersedes 9; untouched lanes survive an aggregate-only retry."""
    source = tmp_path / "source"
    _bundles(source)
    lane = LANES[0].name
    latest = _bundle(source, lane, 10)
    shutil.copytree(_bundle(source, lane), latest)
    # Old registry-failure artifacts contain only timing, not a bundle.
    _bundle(source, lane, 9).mkdir()
    (_bundle(source, lane) / "summary.json").unlink()
    selection = select_lane_bundles(source, HEAD, 11)
    assert selection[lane] == latest
    assert all(selection[item.name] == _bundle(source, item.name) for item in LANES[1:])
    _merge(source, tmp_path / "merged", tmp_path / "summary.json", 11)
    assert len(json.loads((tmp_path / "summary.json").read_text())["lanes"]) == len(LANES)


@pytest.mark.parametrize("damage,error", [
    ("missing", "missing_lane_bundle_file"),
    ("failed", "lane_bundle_execution_incomplete"),
    ("coverage", "invalid_lane_bundle_file"),
    ("head", "invalid_lane_bundle_summary"),
])
@pytest.mark.parametrize("lane_name", ["shared_foundations_a", "shared_foundations_i", "schema_contracts_a", "schema_contracts_b", "schema_contracts_c", "project_lifecycle_d", "project_lifecycle_e", "task_lifecycle_d"])
def test_latest_invalid_attempt_never_falls_back(tmp_path: Path, damage: str, error: str, lane_name: str) -> None:
    source = tmp_path / "source"
    _bundles(source)
    lane = lane_name
    latest = _bundle(source, lane, 2)
    shutil.copytree(_bundle(source, lane), latest)
    summary_file = latest / "summary.json"
    if damage == "missing":
        summary_file.unlink()
    elif damage == "coverage":
        (latest / "metadata" / f".coverage.{lane}").write_bytes(b"corrupt")
    else:
        summary = json.loads(summary_file.read_text())
        if damage == "failed":
            summary["lanes"][0]["execution_exit_code"] = 1
        else:
            summary["head_sha"] = "b" * 40
        _write_json(summary_file, summary)
    with pytest.raises(LaneError, match=error):
        _merge(source, tmp_path / "merged", tmp_path / "summary.json", 2)


@pytest.mark.parametrize("suffix", ["0", "01", "-1", "future", "3"])
def test_attempt_names_are_canonical_and_not_future(tmp_path: Path, suffix: str) -> None:
    _bundles(tmp_path)
    (tmp_path / f"backend-lane-{HEAD}-{LANES[0].name}-attempt-{suffix}").mkdir()
    with pytest.raises(LaneError, match="invalid_lane_bundle_set"):
        select_lane_bundles(tmp_path, HEAD, 2)


@pytest.mark.parametrize("damage", ["wrong_head", "foreign_lane", "file", "symlink", "missing"])
def test_selection_rejects_untrusted_bundle_set(tmp_path: Path, damage: str) -> None:
    _bundles(tmp_path)
    path = _bundle(tmp_path, LANES[0].name)
    if damage == "wrong_head":
        path.rename(tmp_path / path.name.replace(HEAD, "b" * 40))
    elif damage == "foreign_lane":
        path.rename(_bundle(tmp_path, "foreign"))
    elif damage == "file":
        (tmp_path / "extra").write_text("unexpected")
    else:
        moved = tmp_path.parent / f"retained-{damage}"
        path.rename(moved)
        if damage == "symlink":
            path.symlink_to(moved, target_is_directory=True)
    with pytest.raises(LaneError, match="invalid_lane_bundle_set"):
        select_lane_bundles(tmp_path, HEAD, 2)


@pytest.mark.parametrize("head,attempt", [("wrong", 1), (HEAD, 0), (HEAD, True)])
def test_selection_rejects_invalid_run_identity(tmp_path: Path, head: str, attempt: int) -> None:
    with pytest.raises(LaneError, match="invalid_lane_bundle_root"):
        select_lane_bundles(tmp_path, head, attempt)
