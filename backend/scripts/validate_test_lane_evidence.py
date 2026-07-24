"""Fail-closed validation for exact-custody semantic test-lane evidence."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = 1
LANE_COUNT = 4
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
LANE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ADMIN_RUNNER_MODULE = "tests/test_isolated_database_runner.py"
ORDINARY_KIND = "ordinary_isolated"
ADMIN_KIND = "admin_runner_self_test"
DATABASE_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$")


class EvidenceError(RuntimeError):
    """Test-lane evidence is incomplete, unsafe, or inconsistent."""


def _object(value: Any, keys: set[str], error: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise EvidenceError(error)
    return value


def _json_bytes(data: bytes, error: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(error) from exc
    if not isinstance(value, dict):
        raise EvidenceError(error)
    return value


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _current_head(repository_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    head = result.stdout.strip()
    if result.returncode != 0 or SHA_RE.fullmatch(head) is None:
        raise EvidenceError("invalid_git_head")
    return head


def _safe_file(metadata_dir: Path, name: Any) -> Path:
    if not isinstance(name, str) or not name:
        raise EvidenceError("unsafe_evidence_path")
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != name:
        raise EvidenceError("unsafe_evidence_path")
    root = metadata_dir.resolve(strict=True)
    candidate = metadata_dir / Path(*pure.parts)
    try:
        relative = candidate.relative_to(metadata_dir)
    except ValueError as exc:
        raise EvidenceError("unsafe_evidence_path") from exc
    current = metadata_dir
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise EvidenceError("missing_evidence_file") from exc
        if stat.S_ISLNK(mode):
            raise EvidenceError("unsafe_evidence_path")
    try:
        if (
            candidate.resolve(strict=True).parent != root
            and root not in candidate.resolve(strict=True).parents
        ):
            raise EvidenceError("unsafe_evidence_path")
        if not stat.S_ISREG(candidate.stat().st_mode):
            raise EvidenceError("unsafe_evidence_path")
    except OSError as exc:
        raise EvidenceError("missing_evidence_file") from exc
    return candidate


def _bound_bytes(metadata_dir: Path, name: Any, digest: Any) -> bytes:
    if not isinstance(digest, str) or DIGEST_RE.fullmatch(digest) is None:
        raise EvidenceError("invalid_evidence_digest")
    try:
        data = _safe_file(metadata_dir, name).read_bytes()
    except OSError as exc:
        raise EvidenceError("unreadable_evidence_file") from exc
    if _digest(data) != digest:
        raise EvidenceError("evidence_digest_mismatch")
    return data


def _nodes(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(node, str) or not node for node in value):
        raise EvidenceError(f"invalid_{field}")
    return value


def validate_evidence(
    metadata_dir: Path, summary_json: Path, repository_root: Path | None = None
) -> dict[str, Any]:
    """Validate one complete collection or execution evidence set."""
    if metadata_dir.is_symlink() or not metadata_dir.is_dir():
        raise EvidenceError("invalid_metadata_dir")
    if summary_json.is_symlink() or not summary_json.is_file():
        raise EvidenceError("invalid_summary_file")
    summary = _object(
        _json_bytes(summary_json.read_bytes(), "invalid_summary"),
        {
            "canonical_node_count",
            "elapsed_seconds",
            "head_sha",
            "lanes",
            "manifest_file",
            "manifest_sha256",
            "mode",
            "schema_version",
        },
        "invalid_summary",
    )
    mode = summary["mode"]
    if summary["schema_version"] != SCHEMA_VERSION or mode not in {"collect", "run"}:
        raise EvidenceError("invalid_summary")
    root = repository_root or Path(__file__).resolve().parents[2]
    head = summary["head_sha"]
    if not isinstance(head, str) or head != _current_head(root):
        raise EvidenceError("head_sha_mismatch")

    manifest = _object(
        _json_bytes(
            _bound_bytes(metadata_dir, summary["manifest_file"], summary["manifest_sha256"]),
            "invalid_manifest",
        ),
        {"head_sha", "nodes", "schema_version"},
        "invalid_manifest",
    )
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["head_sha"] != head:
        raise EvidenceError("manifest_head_mismatch")
    raw_manifest_nodes = manifest["nodes"]
    if not isinstance(raw_manifest_nodes, list) or not raw_manifest_nodes:
        raise EvidenceError("zero_canonical_nodes")
    canonical: list[tuple[str, str, str, str]] = []
    for value in raw_manifest_nodes:
        row = _object(
            value,
            {"execution_kind", "lane", "module", "nodeid"},
            "invalid_manifest_node",
        )
        if not all(isinstance(row[key], str) and row[key] for key in row):
            raise EvidenceError("invalid_manifest_node")
        module_path = PurePosixPath(row["module"])
        if (
            module_path.is_absolute()
            or ".." in module_path.parts
            or not module_path.parts
            or module_path.parts[0] != "tests"
            or not module_path.name.startswith("test_")
            or module_path.suffix != ".py"
            or not row["nodeid"].startswith(f"{row['module']}::")
            or LANE_RE.fullmatch(row["lane"]) is None
            or row["execution_kind"] not in {ORDINARY_KIND, ADMIN_KIND}
            or (row["execution_kind"] == ADMIN_KIND and row["module"] != ADMIN_RUNNER_MODULE)
            or (row["execution_kind"] == ORDINARY_KIND and row["module"] == ADMIN_RUNNER_MODULE)
        ):
            raise EvidenceError("invalid_manifest_node")
        canonical.append((row["nodeid"], row["module"], row["lane"], row["execution_kind"]))
    if (
        canonical != sorted(canonical)
        or len(canonical) != len(set(canonical))
        or len({nodeid for nodeid, _module, _lane, _kind in canonical}) != len(canonical)
    ):
        raise EvidenceError("noncanonical_or_duplicate_manifest_nodes")
    if not any(module == ADMIN_RUNNER_MODULE for _node, module, _lane, _kind in canonical):
        raise EvidenceError("missing_admin_runner_self_tests")
    if isinstance(summary["canonical_node_count"], bool) or summary["canonical_node_count"] != len(
        canonical
    ):
        raise EvidenceError("canonical_node_count_mismatch")

    lanes = summary["lanes"]
    if not isinstance(lanes, list) or len(lanes) != LANE_COUNT:
        raise EvidenceError("invalid_lane_count")
    expected_by_lane: dict[str, list[str]] = {}
    for nodeid, _module, lane, _kind in canonical:
        expected_by_lane.setdefault(lane, []).append(nodeid)
    lane_names = [lane.get("name") if isinstance(lane, dict) else None for lane in lanes]
    if len(set(lane_names)) != LANE_COUNT or set(lane_names) != set(expected_by_lane):
        raise EvidenceError("lane_inventory_mismatch")

    all_collected: list[str] = []
    all_completed: list[str] = []
    isolation_namespaces: list[tuple[str, str, str, str]] = []
    coverage_files: list[str] = []
    isolation_files: list[str] = []
    for lane_value in lanes:
        lane = _object(
            lane_value,
            {
                "collection_exit_code",
                "coverage_file",
                "coverage_sha256",
                "elapsed_seconds",
                "evidence_file",
                "evidence_sha256",
                "execution_exit_code",
                "interrupted",
                "name",
            },
            "invalid_lane_summary",
        )
        name = lane["name"]
        if lane["collection_exit_code"] != 0:
            raise EvidenceError("collection_failed")
        if lane["interrupted"] is not False:
            raise EvidenceError("lane_interrupted")
        expected_execution = None if mode == "collect" else 0
        if lane["execution_exit_code"] != expected_execution:
            raise EvidenceError("execution_incomplete")
        evidence = _object(
            _json_bytes(
                _bound_bytes(metadata_dir, lane["evidence_file"], lane["evidence_sha256"]),
                "invalid_lane_evidence",
            ),
            {
                "collected_nodes",
                "completed_nodes",
                "deselected_nodes",
                "isolation_metadata_file",
                "isolation_metadata_sha256",
                "skipped_nodes",
            },
            "invalid_lane_evidence",
        )
        collected = _nodes(evidence["collected_nodes"], "collected_nodes")
        completed = _nodes(evidence["completed_nodes"], "completed_nodes")
        skipped = _nodes(evidence["skipped_nodes"], "skipped_nodes")
        deselected = _nodes(evidence["deselected_nodes"], "deselected_nodes")
        if skipped:
            raise EvidenceError("unexpected_skipped_nodes")
        if deselected:
            raise EvidenceError("unexpected_deselected_nodes")
        if Counter(collected) != Counter(expected_by_lane[name]):
            raise EvidenceError("collected_node_reconciliation_failed")
        if len(collected) != len(set(collected)):
            raise EvidenceError("duplicate_collected_nodes")
        if mode == "collect":
            if (
                completed
                or lane["coverage_file"] is not None
                or lane["coverage_sha256"] is not None
            ):
                raise EvidenceError("invalid_collect_mode_artifacts")
            if (
                evidence["isolation_metadata_file"] is not None
                or evidence["isolation_metadata_sha256"] is not None
            ):
                raise EvidenceError("invalid_collect_mode_artifacts")
        else:
            if Counter(completed) != Counter(collected) or len(completed) != len(set(completed)):
                raise EvidenceError("partial_or_duplicate_completion")
            _bound_bytes(metadata_dir, lane["coverage_file"], lane["coverage_sha256"])
            coverage_files.append(lane["coverage_file"])
            isolation_files.append(evidence["isolation_metadata_file"])
            isolation = _object(
                _json_bytes(
                    _bound_bytes(
                        metadata_dir,
                        evidence["isolation_metadata_file"],
                        evidence["isolation_metadata_sha256"],
                    ),
                    "invalid_isolation_metadata",
                ),
                {
                    "alembic_head",
                    "cleanup_complete",
                    "database_name",
                    "database_cleanup_complete",
                    "database_provisioned",
                    "database_role",
                    "lane",
                    "minio_bucket",
                    "minio_cleanup_complete",
                    "minio_prefix",
                    "minio_probe_complete",
                    "minio_provisioned",
                    "schema_version",
                    "tree_sha",
                },
                "invalid_isolation_metadata",
            )
            namespace_fields = (
                "database_name",
                "database_role",
                "minio_bucket",
                "minio_prefix",
            )
            if (
                isolation["schema_version"] != 2
                or isolation["tree_sha"] != head
                or isolation["lane"] != name
                or isolation["database_provisioned"] is not True
                or isolation["minio_provisioned"] is not True
                or isolation["database_cleanup_complete"] is not True
                or isolation["minio_probe_complete"] is not True
                or isolation["minio_cleanup_complete"] is not True
                or isolation["cleanup_complete"] is not True
                or not isinstance(isolation["alembic_head"], str)
                or not isolation["alembic_head"]
                or any(
                    not isinstance(isolation[field], str) or not isolation[field]
                    for field in namespace_fields
                )
                or DATABASE_IDENTIFIER_RE.fullmatch(isolation["database_name"]) is None
                or DATABASE_IDENTIFIER_RE.fullmatch(isolation["database_role"]) is None
                or BUCKET_RE.fullmatch(isolation["minio_bucket"]) is None
                or PurePosixPath(isolation["minio_prefix"]).is_absolute()
                or ".." in PurePosixPath(isolation["minio_prefix"]).parts
            ):
                raise EvidenceError("invalid_isolation_metadata")
            isolation_namespaces.append(tuple(isolation[field] for field in namespace_fields))
        all_collected.extend(collected)
        all_completed.extend(completed)

    canonical_ids = [nodeid for nodeid, _module, _lane, _kind in canonical]
    if Counter(all_collected) != Counter(canonical_ids):
        raise EvidenceError("global_collection_reconciliation_failed")
    if mode == "run" and Counter(all_completed) != Counter(canonical_ids):
        raise EvidenceError("global_completion_reconciliation_failed")
    if mode == "run" and any(
        len({namespace[index] for namespace in isolation_namespaces}) != LANE_COUNT
        for index in range(4)
    ):
        raise EvidenceError("shared_isolation_namespace")
    if mode == "run" and (
        len(set(coverage_files)) != LANE_COUNT or len(set(isolation_files)) != LANE_COUNT
    ):
        raise EvidenceError("shared_lane_artifact")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-dir", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate_evidence(args.metadata_dir, args.summary_json)
    except (EvidenceError, OSError) as exc:
        print(f"test lane evidence invalid: {exc}", file=sys.stderr)
        return 1
    print("test lane evidence valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
