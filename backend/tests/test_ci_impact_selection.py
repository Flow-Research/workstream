"""Fail-closed tests for the reviewed backend impact classifier."""

from __future__ import annotations

import json
import importlib.util
import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts.test_impact_selection import (
    MAP_RELATIVE_PATH,
    SelectionError,
    build_manifest,
    classify_paths,
)


ROOT = Path(__file__).resolve().parents[2]
RUN_SELECTED_PATH = ROOT / ".ci/test-impact/run_selected_tests.py"
IMPACT_MAP = json.loads((ROOT / MAP_RELATIVE_PATH).read_text(encoding="utf-8"))
S3_TEST_PATHS = [
    "backend/tests/test_config.py",
    "backend/tests/test_artifact_store_conformance.py",
    "backend/tests/test_s3_artifact_store.py",
]
S3_TEST_MODULES = [path.removeprefix("backend/") for path in S3_TEST_PATHS]
POLICY_PATHS = [
    ".commitrail/initiatives/WS-ARCH-001/planning/chunks/WS-ARCH-001-CP07-project-guide-policy-binding.md",
    ".commitrail/initiatives/WS-AUTH-001/planning/chunks/WS-AUTH-001-12H-guide-activation.md",
]
POLICY_MODULE = "tests/projects/review_policy/test_semantics.py"


_RUN_SELECTED_SPEC = importlib.util.spec_from_file_location(
    "ci_run_selected_tests", RUN_SELECTED_PATH
)
assert _RUN_SELECTED_SPEC is not None and _RUN_SELECTED_SPEC.loader is not None
_RUN_SELECTED = importlib.util.module_from_spec(_RUN_SELECTED_SPEC)
_RUN_SELECTED_SPEC.loader.exec_module(_RUN_SELECTED)


@pytest.mark.parametrize("path", POLICY_PATHS)
def test_committrail_policy_inputs_select_the_exact_backend_consumer(path: str) -> None:
    mode, modules, jobs, profile = classify_paths([path], IMPACT_MAP)

    assert mode == "pure"
    assert modules == [POLICY_MODULE]
    assert jobs == ["impact-selection", "auth-boundary-preflight", "impact-pure"]
    assert profile == "none"


def test_unrelated_committrail_metadata_is_still_nonempty() -> None:
    mode, modules, jobs, profile = classify_paths(
        [".commitrail/changes/some-new-record.md"], IMPACT_MAP
    )

    assert (mode, modules, jobs, profile) == (
        "pure",
        [POLICY_MODULE],
        ["impact-selection", "auth-boundary-preflight", "impact-pure"],
        "none",
    )


def test_committrail_policy_test_is_unioned_with_mapped_s3_closure() -> None:
    mode, modules, jobs, profile = classify_paths(
        ["backend/app/core/s3_validation.py", ".commitrail/changes/change.md"],
        IMPACT_MAP,
    )

    assert mode == "impact"
    assert modules == sorted([*S3_TEST_MODULES, POLICY_MODULE])
    assert jobs == ["impact-selection", "auth-boundary-preflight", "minio-image", "impact-s3"]
    assert profile == "minio"


def test_s3_owner_or_mapped_test_edits_select_the_whole_owner_closure() -> None:
    for path in ["backend/app/core/s3_validation.py", *S3_TEST_PATHS]:
        mode, modules, jobs, profile = classify_paths([path], IMPACT_MAP)
        assert mode == "impact"
        assert modules == sorted(S3_TEST_MODULES)
        assert jobs == ["impact-selection", "auth-boundary-preflight", "minio-image", "impact-s3"]
        assert profile == "minio"


def test_incomplete_owner_test_closure_falls_back_to_full() -> None:
    incomplete_map = json.loads(json.dumps(IMPACT_MAP))
    incomplete_map["owners"][0]["test_modules"] = incomplete_map["owners"][0][
        "test_modules"
    ][:-1]

    assert classify_paths(["backend/app/core/s3_validation.py"], incomplete_map) == (
        "full",
        [],
        ["impact-selection", "auth-boundary-preflight", "minio-image", "lanes", "full-api-e2e"],
        "full",
    )


@pytest.mark.parametrize(
    "path",
    [
        "backend/app/core/config.py",
        "backend/tests/conftest.py",
        "backend/tests/test_unmapped.py",
        "backend/scripts/test_lane_catalogue.py",
        "backend/scripts/test_impact_selection.py",
        ".ci/test-impact/impact_map.json",
        ".ci/test-impact/run_selected_tests.py",
        ".github/workflows/backend.yml",
        "docs/roadmap_status.md",
        "AGENTS.md",
    ],
)
def test_unmapped_or_shared_changes_fail_closed_to_full_suite(path: str) -> None:
    assert classify_paths(["backend/app/core/s3_validation.py", path], IMPACT_MAP) == (
        "full",
        [],
        ["impact-selection", "auth-boundary-preflight", "minio-image", "lanes", "full-api-e2e"],
        "full",
    )


@pytest.mark.parametrize("paths", [[], ["../escape"], ["/absolute"], ["a\\b"]])
def test_empty_or_malformed_changes_never_produce_empty_green_selection(
    paths: list[str],
) -> None:
    mode, modules, jobs, profile = classify_paths(paths, IMPACT_MAP)
    assert (mode, modules, jobs, profile) == (
        "full",
        [],
        ["impact-selection", "auth-boundary-preflight", "minio-image", "lanes", "full-api-e2e"],
        "full",
    )


def test_impact_fan_in_requires_predeclared_exact_nodes_and_completion(tmp_path: Path) -> None:
    manifest = {
        "execution_sha": "a" * 40,
        "execution_tree": "b" * 40,
        "selected_modules": ["tests/test_config.py"],
        "test_inventory_sha256": "c" * 64,
    }
    nodes = ["tests/test_config.py::test_one"]

    def canonical(value: object) -> bytes:
        return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

    selection_path = tmp_path / "selection.json"
    selection_bytes = canonical(manifest)
    selection_path.write_bytes(selection_bytes)
    payload = {
        "execution_sha": manifest["execution_sha"],
        "execution_tree": manifest["execution_tree"],
        "selected_modules": manifest["selected_modules"],
        "selected_nodes": nodes,
        "selected_nodes_sha256": hashlib.sha256(canonical(nodes)).hexdigest(),
        "selection_manifest_sha256": hashlib.sha256(selection_bytes).hexdigest(),
    }
    evidence = {
        "job": "impact-pure",
        "execution_sha": manifest["execution_sha"],
        "execution_tree": manifest["execution_tree"],
        "test_inventory_sha256": manifest["test_inventory_sha256"],
        "selection_manifest_sha256": hashlib.sha256(selection_bytes).hexdigest(),
        "exit_code": 0,
        "selected_nodes": nodes,
        "completed_nodes": nodes,
        "observed_collected_nodes": nodes,
        "skipped_nodes": [],
        "deselected_nodes": [],
        "selected_modules": manifest["selected_modules"],
        "expected_nodes_sha256": hashlib.sha256(canonical(nodes)).hexdigest(),
        "completed_nodes_sha256": hashlib.sha256(canonical(nodes)).hexdigest(),
        "elapsed_seconds": 1.0,
        "expected_payload_sha256": hashlib.sha256(canonical(payload)).hexdigest(),
    }
    expected_path = tmp_path / "expected.json"
    expected_path.write_bytes(canonical(payload))
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_bytes(canonical(evidence))
    manifest_digest = hashlib.sha256(selection_bytes).hexdigest()

    _RUN_SELECTED.validate_evidence(
        selection_path,
        evidence_path,
        expected_job="impact-pure",
        expected_manifest_sha256=manifest_digest,
    )

    evidence_path.write_bytes(canonical({**evidence, "completed_nodes": []}))
    with pytest.raises(SelectionError, match="impact_evidence_incomplete"):
        _RUN_SELECTED.validate_evidence(
            selection_path,
            evidence_path,
            expected_job="impact-pure",
            expected_manifest_sha256=manifest_digest,
        )


def test_execution_candidate_must_be_the_event_merge_commit(tmp_path: Path) -> None:
    repository = tmp_path / "candidate"
    repository.mkdir()
    _git(repository, "init", "-q", "-b", "main")
    _git(repository, "config", "user.email", "ci@example.invalid")
    _git(repository, "config", "user.name", "CI test")
    paths = [
        "backend/app/core/s3_validation.py",
        *S3_TEST_PATHS,
        "backend/tests/projects/review_policy/test_semantics.py",
    ]
    for path in paths:
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# inventory fixture\n", encoding="utf-8")
    _git(repository, "add", "backend")
    _git(repository, "commit", "-q", "-m", "base")
    base = _git(repository, "rev-parse", "HEAD")
    source = repository / "backend/app/core/s3_validation.py"
    source.write_text("# changed source\n", encoding="utf-8")
    _git(repository, "add", "backend/app/core/s3_validation.py")
    _git(repository, "commit", "-q", "-m", "change")
    head = _git(repository, "rev-parse", "HEAD")
    tree = _git(repository, "rev-parse", "HEAD^{tree}")
    execution = subprocess.run(
        ["git", "commit-tree", tree, "-p", base, "-p", head],
        cwd=repository,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    _git(repository, "reset", "--hard", execution)

    manifest = build_manifest(
        ROOT,
        repository,
        base_sha=base,
        head_sha=head,
        execution_sha=execution,
    )
    assert manifest["merge_base_sha"] == base
    assert manifest["execution_sha"] == execution
    assert manifest["selected_modules"] == sorted(S3_TEST_MODULES)
    assert manifest["expected_jobs"] == [
        "impact-selection",
        "auth-boundary-preflight",
        "minio-image",
        "impact-s3",
    ]
    forced_full = build_manifest(
        ROOT,
        repository,
        base_sha=execution,
        head_sha=execution,
        execution_sha=execution,
        force_full=True,
    )
    assert forced_full["mode"] == "full"
    assert forced_full["selected_modules"] == []
    assert set(forced_full["expected_jobs"]) == {
        "impact-selection",
        "auth-boundary-preflight",
        "minio-image",
        "lanes",
        "full-api-e2e",
    }
    _git(repository, "reset", "--hard", head)
    with pytest.raises(SelectionError, match="candidate_checkout_mismatch"):
        build_manifest(
            ROOT,
            repository,
            base_sha=base,
            head_sha=head,
            execution_sha=execution,
        )
    _git(repository, "reset", "--hard", head)
    with pytest.raises(SelectionError, match="execution_parent_mismatch"):
        build_manifest(
            ROOT,
            repository,
            base_sha=base,
            head_sha=head,
            execution_sha=head,
        )
    _git(repository, "reset", "--hard", execution)


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()
