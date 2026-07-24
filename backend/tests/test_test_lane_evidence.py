"""Tests for independent semantic test-lane evidence validation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import uuid

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/validate_test_lane_evidence.py"
SPEC = importlib.util.spec_from_file_location("validate_test_lane_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)
REAL_COLLECT_CURRENT_NODES = validator._collect_current_nodes
HEAD = "a" * 40
LANES = (
    "shared_foundations",
    "schema_contracts",
    "project_lifecycle",
    "task_lifecycle",
)


def _write(path: Path, value: object) -> str:
    data = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _bundle(tmp_path: Path, mode: str = "run") -> tuple[Path, Path, dict]:
    metadata = tmp_path / "metadata"
    metadata.mkdir(parents=True)
    nodes = [
        {
            "execution_kind": "ordinary_isolated",
            "lane": lane,
            "module": f"tests/test_{index}.py",
            "nodeid": f"tests/test_{index}.py::test_ok",
        }
        for index, lane in enumerate(LANES)
    ]
    nodes.append(
        {
            "execution_kind": "admin_runner_self_test",
            "lane": "schema_contracts",
            "module": "tests/test_isolated_database_runner.py",
            "nodeid": "tests/test_isolated_database_runner.py::test_admin_custody",
        }
    )
    nodes.sort(key=lambda row: row["nodeid"])
    manifest_name = "manifest.json"
    manifest_digest = _write(
        metadata / manifest_name,
        {"head_sha": HEAD, "nodes": nodes, "schema_version": 1},
    )
    lane_rows = []
    for lane in LANES:
        nodeids = [row["nodeid"] for row in nodes if row["lane"] == lane]
        isolation_file = None
        isolation_digest = None
        coverage_file = None
        coverage_digest = None
        if mode == "run":
            isolation_file = f"{lane}.isolation.json"
            isolation_digest = _write(
                metadata / isolation_file,
                {
                    "alembic_head": "head",
                    "cleanup_complete": True,
                    "database_cleanup_complete": True,
                    "database_name": f"database_{lane}",
                    "database_provisioned": True,
                    "database_role": f"role_{lane}",
                    "lane": lane,
                    "minio_bucket": f"bucket-{lane.replace('_', '-')}",
                    "minio_cleanup_complete": True,
                    "minio_prefix": f"prefix/{lane}",
                    "minio_probe_complete": True,
                    "minio_provisioned": True,
                    "schema_version": 2,
                    "tree_sha": HEAD,
                },
            )
            coverage_file = f"coverage.{lane}"
            (metadata / coverage_file).write_bytes(f"coverage:{lane}".encode())
            coverage_digest = hashlib.sha256((metadata / coverage_file).read_bytes()).hexdigest()
        evidence_file = f"{lane}.evidence.json"
        evidence_digest = _write(
            metadata / evidence_file,
            {
                "collected_nodes": nodeids,
                "completed_nodes": nodeids if mode == "run" else [],
                "deselected_nodes": [],
                "isolation_metadata_file": isolation_file,
                "isolation_metadata_sha256": isolation_digest,
                "skipped_nodes": [],
            },
        )
        lane_rows.append(
            {
                "collection_exit_code": 0,
                "coverage_file": coverage_file,
                "coverage_sha256": coverage_digest,
                "elapsed_seconds": 1.0,
                "evidence_file": evidence_file,
                "evidence_sha256": evidence_digest,
                "execution_exit_code": 0 if mode == "run" else None,
                "interrupted": False,
                "name": lane,
            }
        )
    summary = {
        "aggregate_runner_seconds": 4.0,
        "canonical_node_count": 5,
        "elapsed_seconds": 2.0,
        "head_sha": HEAD,
        "lanes": lane_rows,
        "manifest_file": manifest_name,
        "manifest_sha256": manifest_digest,
        "mode": mode,
        "schema_version": 1,
        "slowest_lane_seconds": 1.0,
    }
    summary_path = tmp_path / "summary.json"
    _write(summary_path, summary)
    return metadata, summary_path, summary


@pytest.fixture(autouse=True)
def exact_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validator, "_current_head", lambda _root: HEAD)
    monkeypatch.setattr(
        validator,
        "_collect_current_nodes",
        lambda _root, _head: sorted(
            [
                *(f"tests/test_{index}.py::test_ok" for index in range(4)),
                "tests/test_isolated_database_runner.py::test_admin_custody",
            ]
        ),
    )


@pytest.mark.parametrize("mode", ["collect", "run"])
def test_validates_complete_exact_custody(tmp_path: Path, mode: str) -> None:
    metadata, summary_path, summary = _bundle(tmp_path, mode)
    assert validator.validate_evidence(metadata, summary_path, tmp_path) == summary


def test_rejects_wrong_head_and_noncanonical_manifest(tmp_path: Path) -> None:
    metadata, summary_path, summary = _bundle(tmp_path)
    summary["head_sha"] = "b" * 40
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match="head_sha_mismatch"):
        validator.validate_evidence(metadata, summary_path, tmp_path)

    metadata, summary_path, summary = _bundle(tmp_path / "second")
    manifest = json.loads((metadata / "manifest.json").read_text())
    manifest["nodes"].reverse()
    summary["manifest_sha256"] = _write(metadata / "manifest.json", manifest)
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match="noncanonical"):
        validator.validate_evidence(metadata, summary_path, tmp_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda evidence: evidence["collected_nodes"].clear(), "collected_node_reconciliation"),
        (
            lambda evidence: evidence["collected_nodes"].append("tests/test_0.py::test_ok"),
            "collected_node_reconciliation",
        ),
        (
            lambda evidence: evidence["collected_nodes"].append("tests/test_foreign.py::test_bad"),
            "collected_node_reconciliation",
        ),
        (lambda evidence: evidence["completed_nodes"].clear(), "partial_or_duplicate_completion"),
        (
            lambda evidence: evidence["skipped_nodes"].append(evidence["collected_nodes"][0]),
            "unexpected_skipped",
        ),
        (
            lambda evidence: evidence["deselected_nodes"].append(evidence["collected_nodes"][0]),
            "unexpected_deselected",
        ),
    ],
)
def test_rejects_node_custody_failures(tmp_path: Path, mutation, message: str) -> None:
    metadata, summary_path, summary = _bundle(tmp_path)
    lane = summary["lanes"][0]
    evidence_path = metadata / lane["evidence_file"]
    evidence = json.loads(evidence_path.read_text())
    mutation(evidence)
    lane["evidence_sha256"] = _write(evidence_path, evidence)
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match=message):
        validator.validate_evidence(metadata, summary_path, tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("collection_exit_code", 1, "collection_failed"),
        ("collection_exit_code", -9, "collection_failed"),
        ("collection_exit_code", False, "collection_failed"),
        ("execution_exit_code", None, "execution_incomplete"),
        ("execution_exit_code", -15, "execution_incomplete"),
        ("execution_exit_code", False, "execution_incomplete"),
        ("interrupted", True, "lane_interrupted"),
    ],
)
def test_rejects_failed_or_partial_lane(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    metadata, summary_path, summary = _bundle(tmp_path)
    summary["lanes"][0][field] = value
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match=message):
        validator.validate_evidence(metadata, summary_path, tmp_path)


def test_rejects_digest_tampering_and_unsafe_paths(tmp_path: Path) -> None:
    metadata, summary_path, summary = _bundle(tmp_path)
    (metadata / summary["lanes"][0]["coverage_file"]).write_bytes(b"tampered")
    with pytest.raises(validator.EvidenceError, match="evidence_digest_mismatch"):
        validator.validate_evidence(metadata, summary_path, tmp_path)

    metadata, summary_path, summary = _bundle(tmp_path / "link-case")
    target = metadata / summary["lanes"][0]["evidence_file"]
    real = metadata / "real.json"
    target.rename(real)
    target.symlink_to(real)
    with pytest.raises(validator.EvidenceError, match="unsafe_evidence_path"):
        validator.validate_evidence(metadata, summary_path, tmp_path)


def test_rejects_wrong_lane_count_zero_nodes_and_unknown_keys(tmp_path: Path) -> None:
    metadata, summary_path, summary = _bundle(tmp_path)
    summary["lanes"].pop()
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match="invalid_lane_count"):
        validator.validate_evidence(metadata, summary_path, tmp_path)

    metadata, summary_path, summary = _bundle(tmp_path / "zero")
    manifest = {"head_sha": HEAD, "nodes": [], "schema_version": 1}
    summary["manifest_sha256"] = _write(metadata / "manifest.json", manifest)
    summary["canonical_node_count"] = 0
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match="zero_canonical_nodes"):
        validator.validate_evidence(metadata, summary_path, tmp_path)

    metadata, summary_path, summary = _bundle(tmp_path / "keys")
    summary["unexpected"] = True
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match="invalid_summary"):
        validator.validate_evidence(metadata, summary_path, tmp_path)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda rows: rows.__setitem__(
                slice(None),
                [row for row in rows if row["module"] != validator.ADMIN_RUNNER_MODULE],
            ),
            "missing_admin_runner_self_tests",
        ),
        (
            lambda rows: rows[-1].__setitem__("execution_kind", validator.ORDINARY_KIND),
            "invalid_manifest_node",
        ),
        (
            lambda rows: rows[0].__setitem__("execution_kind", validator.ADMIN_KIND),
            "invalid_manifest_node",
        ),
        (lambda rows: rows.append(dict(rows[-1])), "noncanonical_or_duplicate"),
    ],
)
def test_rejects_missing_duplicate_or_wrong_kind_admin_custody(
    tmp_path: Path, mutate, message: str
) -> None:
    metadata, summary_path, summary = _bundle(tmp_path)
    manifest_path = metadata / summary["manifest_file"]
    manifest = json.loads(manifest_path.read_text())
    mutate(manifest["nodes"])
    manifest["nodes"].sort(key=lambda row: row["nodeid"])
    summary["canonical_node_count"] = len(manifest["nodes"])
    summary["manifest_sha256"] = _write(manifest_path, manifest)
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match=message):
        validator.validate_evidence(metadata, summary_path, tmp_path)


def test_rejects_recorded_database_environment_or_shared_coverage(tmp_path: Path) -> None:
    metadata, summary_path, summary = _bundle(tmp_path)
    lane = summary["lanes"][0]
    evidence = json.loads((metadata / lane["evidence_file"]).read_text())
    isolation_path = metadata / evidence["isolation_metadata_file"]
    isolation = json.loads(isolation_path.read_text())
    isolation["admin_database_url"] = "postgresql://admin:secret@example.invalid/db"
    evidence["isolation_metadata_sha256"] = _write(isolation_path, isolation)
    lane["evidence_sha256"] = _write(metadata / lane["evidence_file"], evidence)
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match="invalid_isolation_metadata"):
        validator.validate_evidence(metadata, summary_path, tmp_path)

    metadata, summary_path, summary = _bundle(tmp_path / "shared")
    summary["lanes"][1]["coverage_file"] = summary["lanes"][0]["coverage_file"]
    summary["lanes"][1]["coverage_sha256"] = summary["lanes"][0]["coverage_sha256"]
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match="shared_lane_artifact"):
        validator.validate_evidence(metadata, summary_path, tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("aggregate_runner_seconds", 4.01, "summary_timing_mismatch"),
        ("slowest_lane_seconds", 0.99, "summary_timing_mismatch"),
        ("aggregate_runner_seconds", float("nan"), "invalid_summary_timing"),
        ("slowest_lane_seconds", float("inf"), "invalid_summary_timing"),
        ("elapsed_seconds", -1.0, "invalid_summary_timing"),
    ],
)
def test_rejects_invalid_or_drifted_summary_timing(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    metadata, summary_path, summary = _bundle(tmp_path)
    summary[field] = value
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match=message):
        validator.validate_evidence(metadata, summary_path, tmp_path)


@pytest.mark.parametrize("value", [-0.001, float("nan"), float("inf"), True])
def test_rejects_invalid_lane_timing(tmp_path: Path, value: object) -> None:
    metadata, summary_path, summary = _bundle(tmp_path)
    summary["lanes"][0]["elapsed_seconds"] = value
    _write(summary_path, summary)
    with pytest.raises(validator.EvidenceError, match="invalid_lane_elapsed_seconds"):
        validator.validate_evidence(metadata, summary_path, tmp_path)


@pytest.mark.parametrize("mutation", ["missing", "foreign"])
def test_real_collection_rejects_missing_or_foreign_manifest_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    tests = tmp_path / "backend/tests"
    tests.mkdir(parents=True)
    for index in range(4):
        (tests / f"test_{index}.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    (tests / "test_isolated_database_runner.py").write_text(
        "def test_admin_custody():\n    pass\n", encoding="utf-8"
    )
    metadata, summary_path, summary = _bundle(tmp_path)
    manifest_path = metadata / summary["manifest_file"]
    manifest = json.loads(manifest_path.read_text())
    if mutation == "missing":
        manifest["nodes"].pop(0)
    else:
        manifest["nodes"][0]["module"] = "tests/test_foreign.py"
        manifest["nodes"][0]["nodeid"] = "tests/test_foreign.py::test_ok"
    manifest["nodes"].sort(key=lambda row: row["nodeid"])
    summary["canonical_node_count"] = len(manifest["nodes"])
    summary["manifest_sha256"] = _write(manifest_path, manifest)
    _write(summary_path, summary)
    monkeypatch.setattr(validator, "_collect_current_nodes", REAL_COLLECT_CURRENT_NODES)
    with pytest.raises(validator.EvidenceError, match="current_node_inventory_mismatch"):
        validator.validate_evidence(metadata, summary_path, tmp_path)


def test_independent_collections_preserve_full_deterministic_uuid_nodeid(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "backend/tests"
    tests.mkdir(parents=True)
    (tests / "test_uuid_nodes.py").write_text(
        "import pytest\n"
        "import uuid\n"
        "\n"
        "VALUE = uuid.uuid4()\n"
        "\n"
        "@pytest.mark.parametrize('value', [VALUE])\n"
        "def test_value(value):\n"
        "    assert value == VALUE\n",
        encoding="utf-8",
    )
    first = REAL_COLLECT_CURRENT_NODES(tmp_path, HEAD)
    second = REAL_COLLECT_CURRENT_NODES(tmp_path, HEAD)
    expected_key = "\0".join((HEAD, "tests/test_uuid_nodes.py", "4", "0")).encode()
    expected_uuid = uuid.UUID(bytes=hashlib.sha256(expected_key).digest()[:16], version=4)

    assert first == second
    assert first == [f"tests/test_uuid_nodes.py::test_value[{expected_uuid}]"]


def test_independent_collection_clears_inherited_pytest_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """External pytest flags and plugins cannot alter canonical recollection."""
    tests = tmp_path / "backend/tests"
    tests.mkdir(parents=True)
    (tests / "test_one.py").write_text("def test_one():\n    pass\n", encoding="utf-8")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--cov=foreign")
    monkeypatch.setenv("PYTEST_PLUGINS", "foreign.plugin")

    class Result:
        returncode = 0

    def fake_run(*_args, **kwargs):
        environment = kwargs["env"]
        assert "PYTEST_ADDOPTS" not in environment
        assert "PYTEST_PLUGINS" not in environment
        Path(environment[validator.VALIDATOR_COLLECTION_ENV]).write_text(
            '"tests/test_one.py::test_one"\n', encoding="utf-8"
        )
        return Result()

    monkeypatch.setattr(validator.subprocess, "run", fake_run)
    assert REAL_COLLECT_CURRENT_NODES(tmp_path, HEAD) == [
        "tests/test_one.py::test_one"
    ]


def test_collection_finish_restores_uuid4_and_repository_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    destination = tmp_path / "nodes.jsonl"
    monkeypatch.setenv(validator.VALIDATOR_ROOT_ENV, str(backend))
    monkeypatch.setenv(validator.VALIDATOR_HEAD_ENV, HEAD)
    monkeypatch.setenv(validator.VALIDATOR_COLLECTION_ENV, str(destination))
    original = uuid.uuid4
    try:
        validator.pytest_sessionstart(object())
        wrapper = uuid.uuid4
        assert wrapper is validator._deterministic_uuid4

        repository_module = types.ModuleType("validator_alias_fixture")
        repository_module.__file__ = str(backend / "tests/test_alias.py")
        repository_module.imported_uuid4 = wrapper
        monkeypatch.setitem(sys.modules, repository_module.__name__, repository_module)
        session = types.SimpleNamespace(
            items=[types.SimpleNamespace(nodeid="tests/test_alias.py::test_value[full-uuid]")]
        )
        validator.pytest_collection_finish(session)
    finally:
        validator._restore_uuid4()

    assert destination.read_text(encoding="utf-8").splitlines() == [
        '"tests/test_alias.py::test_value[full-uuid]"'
    ]
    assert uuid.uuid4 is original
    assert repository_module.imported_uuid4 is original
    assert validator._UUID_ORIGINAL is None
    validator.pytest_sessionfinish(object(), 0)
    assert uuid.uuid4 is original
