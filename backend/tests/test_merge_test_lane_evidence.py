"""Tests for fail-closed distributed semantic-lane fan-in."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.merge_test_lane_evidence import merge_bundles
from scripts.run_test_lanes import LANES, LaneError


def _write_json(path: Path, value: object) -> str:
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


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
        metadata = root / lane.name / "metadata"
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
            root / lane.name / "summary.json",
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

    merge_bundles(source, tmp_path / "merged", tmp_path / "summary.json")

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "run"
    assert [row["name"] for row in summary["lanes"]] == [lane.name for lane in LANES]
    assert summary["aggregate_runner_seconds"] == sum(
        float(index) for index in range(1, len(LANES) + 1)
    )
    assert summary["slowest_lane_seconds"] == float(len(LANES))
    assert len(list((tmp_path / "merged").glob(".coverage.*"))) == len(LANES)


def test_merge_bundles_rejects_missing_or_foreign_lane(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    (source / LANES[0].name).rename(source / "foreign")

    with pytest.raises(LaneError, match="invalid_lane_bundle_set"):
        merge_bundles(source, tmp_path / "merged", tmp_path / "summary.json")


def test_merge_bundles_rejects_coverage_digest_drift(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    lane = LANES[0]
    (source / lane.name / "metadata" / f".coverage.{lane.name}").write_bytes(b"changed")

    with pytest.raises(LaneError, match="invalid_lane_bundle_file"):
        merge_bundles(source, tmp_path / "merged", tmp_path / "summary.json")


def test_merge_bundles_rejects_manifest_path_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    summary_path = source / LANES[0].name / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["manifest_file"] = "../manifest.json"
    _write_json(summary_path, summary)

    with pytest.raises(LaneError, match="invalid_lane_bundle_manifest"):
        merge_bundles(source, tmp_path / "merged", tmp_path / "summary.json")


def test_merge_bundles_rejects_manifest_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    metadata = source / LANES[0].name / "metadata"
    manifest = json.loads((metadata / "manifest.json").read_text(encoding="utf-8"))
    manifest["head_sha"] = "b" * 40
    digest = _write_json(metadata / "manifest.json", manifest)
    summary_path = source / LANES[0].name / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["manifest_sha256"] = digest
    _write_json(summary_path, summary)

    with pytest.raises(LaneError, match="lane_manifest_mismatch"):
        merge_bundles(source, tmp_path / "merged", tmp_path / "summary.json")


def test_merge_bundles_rejects_symlinked_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    lane_root = source / LANES[0].name
    metadata = lane_root / "metadata"
    moved = lane_root / "moved"
    metadata.rename(moved)
    metadata.symlink_to(moved, target_is_directory=True)

    with pytest.raises(LaneError, match="invalid_lane_bundle_metadata"):
        merge_bundles(source, tmp_path / "merged", tmp_path / "summary.json")


def test_merge_bundles_rejects_failed_lane_row(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _bundles(source)
    summary_path = source / LANES[0].name / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["lanes"][0]["execution_exit_code"] = 1
    _write_json(summary_path, summary)

    with pytest.raises(LaneError, match="lane_bundle_execution_incomplete"):
        merge_bundles(source, tmp_path / "merged", tmp_path / "summary.json")
