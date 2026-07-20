"""Tests for deterministic backend CI shard evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ci_test_shards.py"
SPEC = importlib.util.spec_from_file_location("ci_test_shards", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
shards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shards)

TREE_SHA = "a" * 40


def _nodes() -> dict[str, list[str]]:
    return {
        "backend/tests/test_alpha.py": [
            "tests/test_alpha.py::test_a",
            "tests/test_alpha.py::test_b[value]",
            "tests/test_alpha.py::test_c",
            "tests/test_alpha.py::test_d",
        ],
        "backend/tests/test_beta.py": [
            "tests/test_beta.py::test_a",
            "tests/test_beta.py::test_b",
            "tests/test_beta.py::test_c",
        ],
        "backend/tests/test_delta.py": ["tests/test_delta.py::test_a"],
        "backend/tests/test_epsilon.py": ["tests/test_epsilon.py::test_a"],
        "backend/tests/test_gamma.py": [
            "tests/test_gamma.py::test_a",
            "tests/test_gamma.py::test_b",
        ],
    }


def _write_bundle_set(root: Path, manifest: dict) -> None:
    root.mkdir()
    modules = {
        row["path"]: [
            f"{item['base']}[runtime-{index}]" if item["count"] > 1 else item["base"]
            for item in row["node_signature"]
            for index in range(item["count"])
        ]
        for row in manifest["modules"]
    }
    for shard in manifest["shards"]:
        bundle = root / f"shard-{shard['id']}"
        bundle.mkdir()
        coverage = bundle / "coverage.data"
        coverage.write_bytes(f"coverage-{shard['id']}".encode())
        observed = sorted(node for module in shard["modules"] for node in modules[module])
        result = {
            "coverage_file": "coverage.data",
            "coverage_sha256": shards._sha256(coverage.read_bytes()),
            "duration_seconds": 1.25,
            "manifest_sha256": manifest["manifest_sha256"],
            "modules": shard["modules"],
            "collected_node_ids": observed,
            "completed_node_ids": observed,
            "schema_version": shards.SCHEMA_VERSION,
            "shard_id": shard["id"],
            "tree_sha": manifest["tree_sha"],
        }
        (bundle / "result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def test_manifest_is_deterministic_and_balanced() -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    assert manifest == shards.build_manifest(TREE_SHA, dict(reversed(_nodes().items())), 4)
    assert [row["weight"] for row in manifest["shards"]] == [4, 3, 2, 2]
    assigned = [module for row in manifest["shards"] for module in row["modules"]]
    assert sorted(assigned) == sorted(_nodes())
    assert len(assigned) == len(set(assigned))
    assert shards.validate_manifest(manifest) == manifest


@pytest.mark.parametrize(
    ("tree_sha", "nodes", "count", "message"),
    [
        ("bad", _nodes(), 4, "invalid_tree_sha"),
        (TREE_SHA, {}, 4, "invalid_module_inventory"),
        (TREE_SHA, _nodes(), 3, "invalid_shard_count"),
        (
            TREE_SHA,
            {"backend/tests/test_zero.py": []},
            4,
            "invalid_node_inventory",
        ),
        (
            TREE_SHA,
            {"backend/tests/test_alpha.py": ["tests/test_other.py::test_a"]},
            4,
            "node_module_mismatch",
        ),
        (
            TREE_SHA,
            {"backend/tests/../test_escape.py": ["tests/test_escape.py::test_a"]},
            4,
            "invalid_test_module",
        ),
    ],
)
def test_manifest_rejects_invalid_inventory(
    tree_sha: str, nodes: dict[str, list[str]], count: int, message: str
) -> None:
    with pytest.raises(shards.ShardError, match=message):
        shards.build_manifest(tree_sha, nodes, count)


def test_manifest_rejects_digest_or_assignment_tampering() -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    manifest["shards"][0]["modules"].append("backend/tests/test_foreign.py")
    with pytest.raises(shards.ShardError, match="manifest_digest_mismatch"):
        shards.validate_manifest(manifest)


def test_discovery_rejects_symlinked_module(tmp_path: Path) -> None:
    tests = tmp_path / "backend/tests"
    tests.mkdir(parents=True)
    target = tmp_path / "target.py"
    target.write_text("def test_a(): pass\n", encoding="utf-8")
    (tests / "test_link.py").symlink_to(target)
    with pytest.raises(shards.ShardError, match="invalid_test_module"):
        shards.discover_modules(tmp_path)


def test_collect_nodes_rejects_collection_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Result:
        returncode = 2
        stdout = ""
        stderr = "failure"

    monkeypatch.setattr(shards.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(shards.ShardError, match="pytest_collection_failed"):
        shards.collect_nodes(tmp_path, ["backend/tests/test_alpha.py"])


def test_collect_nodes_rejects_zero_or_foreign_nodes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Result:
        returncode = 0
        stdout = "tests/test_other.py::test_a\n"
        stderr = ""

    monkeypatch.setattr(shards.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(shards.ShardError, match="foreign_or_duplicate_node"):
        shards.collect_nodes(tmp_path, ["backend/tests/test_alpha.py"])


def test_collect_nodes_accepts_parameterized_nodes_and_sets_safe_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: dict = {}

    class Result:
        returncode = 0
        stdout = (
            "tests/test_alpha.py::test_a[value]\ntests/test_alpha.py::test_b\n2 tests collected\n"
        )
        stderr = ""

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["env"] = kwargs["env"]
        return Result()

    monkeypatch.setattr(shards.subprocess, "run", fake_run)
    result = shards.collect_nodes(tmp_path, ["backend/tests/test_alpha.py"])
    assert result == {
        "backend/tests/test_alpha.py": [
            "tests/test_alpha.py::test_a[value]",
            "tests/test_alpha.py::test_b",
        ]
    }
    assert observed["command"][-1] == "tests/test_alpha.py"
    assert observed["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_discovery_accepts_regular_modules_and_explicit_exclusion(tmp_path: Path) -> None:
    tests = tmp_path / "backend/tests"
    tests.mkdir(parents=True)
    (tests / "test_alpha.py").write_text("def test_a(): pass\n", encoding="utf-8")
    (tests / "test_beta.py").write_text("def test_b(): pass\n", encoding="utf-8")
    (tests / "test_isolated_database_runner.py").write_text(
        "def test_runner(): pass\n", encoding="utf-8"
    )
    assert shards.discover_modules(tmp_path) == [
        "backend/tests/test_alpha.py",
        "backend/tests/test_beta.py",
    ]


def test_manifest_file_round_trip_and_invalid_json(tmp_path: Path) -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert shards.load_manifest(path) == manifest
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(shards.ShardError, match="invalid_manifest_file"):
        shards.load_manifest(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 99),
        ("shard_count", True),
        ("manifest_sha256", "bad"),
        ("excluded_modules", []),
        ("shards", "bad"),
    ],
)
def test_manifest_rejects_invalid_top_level_schema(field: str, value: object) -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    manifest[field] = value
    with pytest.raises(shards.ShardError, match="invalid_manifest"):
        shards.validate_manifest(manifest)


def test_run_shard_uses_python_argv_and_writes_authenticated_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    shard = manifest["shards"][0]
    module_nodes = {module: nodes for module, nodes in _nodes().items()}
    monkeypatch.setattr(shards, "_assert_checked_out_tree", lambda *args: None)
    captured: dict = {}

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        Path(kwargs["env"]["COVERAGE_FILE"]).write_bytes(b"real-coverage")
        runtime = sorted(node for module in shard["modules"] for node in module_nodes[module])
        for variable in (shards.COLLECTED_NODES_ENV, shards.COMPLETED_NODES_ENV):
            Path(kwargs["env"][variable]).write_text(
                "".join(json.dumps(node) + "\n" for node in runtime), encoding="utf-8"
            )
        return Result()

    monkeypatch.setattr(shards.subprocess, "run", fake_run)
    bundle = tmp_path / "bundle"
    shards.run_shard(
        tmp_path,
        manifest_path,
        shard["id"],
        bundle,
        tmp_path / "database.json",
    )
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    assert captured["command"][:2] == [shards.sys.executable, "scripts/run_isolated_tests.py"]
    invoked_modules = [
        argument for argument in captured["command"] if argument.startswith("tests/")
    ]
    assert invoked_modules == [
        str(Path(module).relative_to("backend")) for module in shard["modules"]
    ]
    assert "scripts.ci_test_shards" in captured["command"]
    assert captured["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert result["modules"] == shard["modules"]
    assert result["coverage_sha256"] == shards._sha256(b"real-coverage")


def test_run_shard_rejects_failed_test_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    shard = manifest["shards"][0]
    monkeypatch.setattr(shards, "_assert_checked_out_tree", lambda *args: None)

    class Result:
        returncode = 1

    monkeypatch.setattr(shards.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(shards.ShardError, match="shard_tests_failed"):
        shards.run_shard(tmp_path, path, shard["id"], tmp_path / "bundle", tmp_path / "db")


def test_run_shard_rejects_collected_but_not_executed_node(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    shard = manifest["shards"][0]
    module_nodes = _nodes()
    monkeypatch.setattr(shards, "_assert_checked_out_tree", lambda *args: None)

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        Path(kwargs["env"]["COVERAGE_FILE"]).write_bytes(b"coverage")
        expected = sorted(node for module in shard["modules"] for node in module_nodes[module])
        Path(kwargs["env"][shards.COLLECTED_NODES_ENV]).write_text(
            "".join(json.dumps(node) + "\n" for node in expected),
            encoding="utf-8",
        )
        Path(kwargs["env"][shards.COMPLETED_NODES_ENV]).write_text(
            "".join(json.dumps(node) + "\n" for node in expected[1:]),
            encoding="utf-8",
        )
        return Result()

    monkeypatch.setattr(shards.subprocess, "run", fake_run)
    with pytest.raises(shards.ShardError, match="shard_execution_mismatch"):
        shards.run_shard(tmp_path, path, shard["id"], tmp_path / "bundle", tmp_path / "db")


def test_pytest_hooks_record_runtime_collection_and_completion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    collected = tmp_path / "collected.jsonl"
    completed = tmp_path / "completed.jsonl"
    collected.write_text("", encoding="utf-8")
    completed.write_text("", encoding="utf-8")
    monkeypatch.setenv(shards.COLLECTED_NODES_ENV, str(collected))
    monkeypatch.setenv(shards.COMPLETED_NODES_ENV, str(completed))
    session = type(
        "Session", (), {"items": [type("Item", (), {"nodeid": "tests/test_alpha.py::test_a"})()]}
    )()
    shards.pytest_collection_finish(session)
    shards.pytest_runtest_logfinish("tests/test_alpha.py::test_a", ("file", 1, "test_a"))
    assert collected.read_text(encoding="utf-8") == '"tests/test_alpha.py::test_a"\n'
    assert completed.read_text(encoding="utf-8") == '"tests/test_alpha.py::test_a"\n'


def test_runtime_signature_tolerates_changed_parameter_display_values() -> None:
    before = ["tests/test_alpha.py::test_a[550e8400::nested[value]]"]
    after = ["tests/test_alpha.py::test_a[6ba7b810::other[value]]"]
    assert shards._node_signature(before) == shards._node_signature(after)
    first = shards.build_manifest(
        TREE_SHA,
        {
            "backend/tests/test_alpha.py": before,
            **{
                key: value
                for key, value in _nodes().items()
                if key != "backend/tests/test_alpha.py"
            },
        },
        4,
    )
    second = shards.build_manifest(
        TREE_SHA,
        {
            "backend/tests/test_alpha.py": after,
            **{
                key: value
                for key, value in _nodes().items()
                if key != "backend/tests/test_alpha.py"
            },
        },
        4,
    )
    assert first == second


def test_fan_in_accepts_exact_authenticated_bundles(tmp_path: Path) -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    bundles = tmp_path / "bundles"
    _write_bundle_set(bundles, manifest)
    summary_path = tmp_path / "fan-in-summary.json"
    outputs = shards.validate_fan_in(manifest, bundles, tmp_path / "combined", summary_path)
    assert [path.name for path in outputs] == [
        ".coverage.shard-1",
        ".coverage.shard-2",
        ".coverage.shard-3",
        ".coverage.shard-4",
    ]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["tree_sha"] == TREE_SHA
    assert summary["manifest_sha256"] == manifest["manifest_sha256"]
    assert summary["node_count"] == sum(len(nodes) for nodes in _nodes().values())
    assert [row["node_count"] for row in summary["shards"]] == [4, 3, 2, 2]
    assert summary["timing"] == {
        "imbalance_seconds": 0.0,
        "maximum_seconds": 1.25,
        "total_runner_seconds": 5.0,
    }


@pytest.mark.parametrize("mutation", ["missing", "extra", "coverage", "nodes", "tree"])
def test_fan_in_rejects_incomplete_or_tampered_evidence(tmp_path: Path, mutation: str) -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    bundles = tmp_path / "bundles"
    _write_bundle_set(bundles, manifest)
    if mutation == "missing":
        (bundles / "shard-1/result.json").unlink()
    elif mutation == "extra":
        (bundles / "surplus").mkdir()
    elif mutation == "coverage":
        (bundles / "shard-1/coverage.data").write_bytes(b"changed")
    else:
        path = bundles / "shard-1/result.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "nodes":
            result["completed_node_ids"] = result["completed_node_ids"][1:]
        else:
            result["tree_sha"] = "b" * 40
        path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(shards.ShardError):
        shards.validate_fan_in(manifest, bundles, tmp_path / "combined")


def test_fan_in_rejects_symlink_and_unexpected_file(tmp_path: Path) -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    bundles = tmp_path / "bundles"
    _write_bundle_set(bundles, manifest)
    (bundles / "shard-1/unexpected").write_text("no", encoding="utf-8")
    with pytest.raises(shards.ShardError, match="unexpected_bundle_path"):
        shards.validate_fan_in(manifest, bundles, tmp_path / "combined")
    (bundles / "shard-1/unexpected").unlink()
    coverage = bundles / "shard-1/coverage.data"
    coverage.unlink()
    coverage.symlink_to(bundles / "shard-2/coverage.data")
    with pytest.raises(shards.ShardError, match="unexpected_bundle_path"):
        shards.validate_fan_in(manifest, bundles, tmp_path / "combined")


def test_fan_in_rejects_runtime_collection_completion_mismatch(tmp_path: Path) -> None:
    manifest = shards.build_manifest(TREE_SHA, _nodes(), 4)
    bundles = tmp_path / "bundles"
    _write_bundle_set(bundles, manifest)
    second = bundles / "shard-2/result.json"
    two = json.loads(second.read_text(encoding="utf-8"))
    two["completed_node_ids"] = two["completed_node_ids"][1:]
    second.write_text(json.dumps(two), encoding="utf-8")
    with pytest.raises(shards.ShardError, match="shard_node_mismatch"):
        shards.validate_fan_in(manifest, bundles, tmp_path / "combined")
