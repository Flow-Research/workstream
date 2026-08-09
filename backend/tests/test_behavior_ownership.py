from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

from scripts import behavior_ownership as ownership


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _partition(targets: list[str]) -> dict[str, object]:
    authority = {
        "schema": ownership.PARTITION_SCHEMA,
        "protected_base_commit": "a" * 40,
        "assignments": [
            {"group": ownership.group_for_target(target), "target": target}
            for target in targets
        ],
    }
    return {**authority, "authority_digest": ownership._digest(authority)}


def _mock_partition_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ownership,
        "_git",
        lambda root, *arguments: "a" * 40 if arguments[0] == "rev-parse" else "",
    )
    monkeypatch.setattr(ownership, "_git_show_optional", lambda root, revision, path: None)


def test_repository_partition_is_exact_deterministic_and_digest_bound() -> None:
    value = json.loads((ownership.ROOT / ownership.PARTITION_PATH).read_text())
    mapping = ownership.validate_partition()
    assert len(mapping) == len(ownership.eligible_targets())
    assert list(mapping) == ownership.eligible_targets()
    authority = {key: value[key] for key in value if key != "authority_digest"}
    assert value["authority_digest"] == hashlib.sha256(ownership._json_bytes(authority)).hexdigest()
    assert ownership.build_partition(base_commit=value["protected_base_commit"]) == value


def test_inventory_reuses_mutation_policy_eligibility() -> None:
    targets = ownership.eligible_targets()
    assert targets == sorted(set(targets))
    assert "backend/scripts/mutation_policy.py" in targets
    assert all(target.endswith(".py") and not target.endswith("/__init__.py") for target in targets)


@pytest.mark.parametrize(
    ("target", "group"),
    [
        ("backend/app/modules/authorization/kernel.py", "auth"),
        ("backend/app/modules/artifacts/service.py", "artifacts"),
        ("backend/app/modules/projects/service.py", "lifecycle"),
        ("backend/app/core/config.py", "shared"),
    ],
)
def test_partition_group_assignment_is_single_and_deterministic(target: str, group: str) -> None:
    assert ownership.group_for_target(target) == group


def test_module_and_callable_inventory_delegate_to_policy(tmp_path: Path) -> None:
    target = "backend/scripts/example.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("def outer():\n    def inner():\n        return 1\n    return inner()\n")
    assert ownership.module_name(target) == "scripts.example"
    assert ownership.callable_names(tmp_path, target) == [
        "scripts.example.outer",
        "scripts.example.outer.inner",
    ]
    with pytest.raises(ownership.BehaviorOwnershipError, match="ineligible_target"):
        ownership.module_name("README.md")
    with pytest.raises(ownership.BehaviorOwnershipError, match="unsafe_or_missing_target"):
        ownership.callable_names(tmp_path, "backend/scripts/missing.py")


@pytest.mark.parametrize(
    ("mutator", "error"),
    [
        (lambda value: value.update(schema="wrong"), "unsupported_partition_schema"),
        (lambda value: value.update(authority_digest="0" * 64), "partition_digest_mismatch"),
        (lambda value: value.update(assignments="wrong"), "partition_digest_mismatch"),
        (lambda value: value["assignments"].append(value["assignments"][0]), "partition_digest_mismatch"),
    ],
)
def test_partition_tampering_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, error: str
) -> None:
    target = "backend/scripts/example.py"
    value = _partition([target])
    mutator(value)
    _write_json(tmp_path / ownership.PARTITION_PATH, value)
    monkeypatch.setattr(ownership, "eligible_targets", lambda root=ownership.ROOT: [target])
    _mock_partition_git(monkeypatch)
    with pytest.raises(ownership.BehaviorOwnershipError, match=error):
        ownership.validate_partition(tmp_path, trusted_revision=None)


def test_partition_rejects_duplicate_missing_wrong_group_and_relocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = "backend/scripts/example.py"
    monkeypatch.setattr(ownership, "eligible_targets", lambda root=ownership.ROOT: [target])
    _mock_partition_git(monkeypatch)
    value = _partition([target])
    value["assignments"].append(value["assignments"][0])
    authority = {key: value[key] for key in value if key != "authority_digest"}
    value["authority_digest"] = ownership._digest(authority)
    _write_json(tmp_path / ownership.PARTITION_PATH, value)
    with pytest.raises(ownership.BehaviorOwnershipError, match="duplicate_partition_target"):
        ownership.validate_partition(tmp_path, trusted_revision=None)
    value = _partition([])
    _write_json(tmp_path / ownership.PARTITION_PATH, value)
    with pytest.raises(ownership.BehaviorOwnershipError, match="partition_target_mismatch"):
        ownership.validate_partition(tmp_path, trusted_revision=None)
    with pytest.raises(ownership.BehaviorOwnershipError, match="relocated_partition"):
        ownership.validate_partition(
            tmp_path, partition_path=tmp_path / "copy.json", trusted_revision=None
        )


def test_partition_rejects_untrusted_branch_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = "backend/scripts/example.py"
    value = _partition([target])
    _write_json(tmp_path / ownership.PARTITION_PATH, value)
    monkeypatch.setattr(ownership, "eligible_targets", lambda root=ownership.ROOT: [target])
    monkeypatch.setattr(
        ownership,
        "_git",
        lambda root, *arguments: "a" * 40 if arguments[0] == "rev-parse" else "",
    )
    monkeypatch.setattr(
        ownership,
        "_git_show_optional",
        lambda root, revision, path: json.dumps({**value, "authority_digest": "0" * 64}),
    )
    with pytest.raises(ownership.BehaviorOwnershipError, match="untrusted_partition_change"):
        ownership.validate_partition(tmp_path, trusted_revision="main")


def test_schema_separates_reviewed_candidate_and_structural_records() -> None:
    validator = Draft202012Validator(ownership.load_schema())
    reviewed = json.loads(
        (ownership.ROOT / ".ci/behavior-ownership/examples/reviewed.example.json").read_text()
    )
    assert not list(validator.iter_errors(reviewed))
    candidate = {
        "schema": ownership.CATALOGUE_SCHEMA,
        "behavior_id": "candidate:example",
        "status": "candidate",
        "group": "shared",
        "target": "backend/scripts/example.py",
        "callables": ["scripts.example.run"],
        "unresolved_reason": "review required",
    }
    assert not list(validator.iter_errors(candidate))
    structural = {
        "schema": ownership.CATALOGUE_SCHEMA,
        "behavior_id": "structural:example",
        "status": "structural_only",
        "group": "shared",
        "target": "backend/scripts/example.py",
        "reason": "constants only",
        "reviewed_by": ["reviewer"],
    }
    assert not list(validator.iter_errors(structural))
    structural["tests"] = ["backend/tests/test_example.py::test_value"]
    assert list(validator.iter_errors(structural))


def test_generator_is_deterministic_candidate_only(monkeypatch: pytest.MonkeyPatch) -> None:
    mapping = {
        "backend/scripts/a.py": "shared",
        "backend/scripts/b.py": "auth",
    }
    monkeypatch.setattr(ownership, "validate_partition", lambda root=ownership.ROOT, **kwargs: mapping)
    monkeypatch.setattr(ownership, "callable_names", lambda root, target: [target + ":run"])
    first = ownership.generate_candidates(group="shared")
    assert first == ownership.generate_candidates(group="shared")
    assert first["authoritative"] is False
    assert [item["target"] for item in first["candidates"]] == ["backend/scripts/a.py"]
    assert all(item["status"] == "candidate" for item in first["candidates"])
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_group"):
        ownership.generate_candidates(group="unknown")


def test_record_semantics_reject_missing_callable_and_executable_structural(
    tmp_path: Path,
) -> None:
    target = "backend/scripts/example.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("def run():\n    return 1\n")
    reviewed = {
        "status": "reviewed",
        "target": target,
        "callables": ["scripts.example.missing"],
        "tests": ["backend/tests/test_example.py::test_run"],
        "outcomes": ["return"],
        "boundaries": [],
    }
    with pytest.raises(ownership.BehaviorOwnershipError, match="missing_catalogue_callable"):
        ownership._validate_record_semantics(tmp_path, reviewed)
    with pytest.raises(ownership.BehaviorOwnershipError, match="executable_structural_only"):
        ownership._validate_record_semantics(tmp_path, {"status": "structural_only", "target": target})


def test_structural_target_has_no_owned_tests(tmp_path: Path) -> None:
    assert ownership.run_owned_tests(
        tmp_path,
        [{"status": "candidate"}, {"status": "structural_only"}],
    ) == 0


def test_catalogue_empty_state_is_explicitly_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    target = "backend/scripts/example.py"
    monkeypatch.setattr(
        ownership, "validate_partition", lambda root=ownership.ROOT, **kwargs: {target: "shared"}
    )
    monkeypatch.setattr(ownership, "_catalogue_files", lambda root: [])
    result = ownership.validate_catalogue()
    assert result["complete"] is False
    assert result["unresolved"] == [target]


def test_changed_callable_parity_delegates_to_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []

    def fake_changed(root: Path, base: str, head: str, target: str) -> list[str]:
        captured.extend([root, base, head, target])
        return ["scripts.example.run"]

    monkeypatch.setattr(ownership, "changed_callables", fake_changed)
    assert ownership.changed_callable_names(Path("/repo"), "base", "head", "target") == [
        "scripts.example.run"
    ]
    assert captured == [Path("/repo"), "base", "head", "target"]
    assert ownership.OBSERVABLE_OUTCOMES
    assert ownership.REAL_BOUNDARIES


def _catalogue_record(status: str, target: str, behavior_id: str) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": ownership.CATALOGUE_SCHEMA,
        "behavior_id": behavior_id,
        "status": status,
        "group": "shared",
        "target": target,
    }
    if status == "reviewed":
        base.update(
            callables=[ownership.module_name(target) + ".run"],
            tests=["backend/tests/test_example.py::test_run"],
            outcomes=["return"],
            boundaries=[],
            reviewed_by=["reviewer"],
        )
    elif status == "candidate":
        base.update(
            callables=[ownership.module_name(target) + ".run"],
            unresolved_reason="review required",
        )
    else:
        base.update(reason="constants only", reviewed_by=["reviewer"])
    return base


def test_catalogue_validation_reports_reviewed_candidate_and_structural(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / ownership.SCHEMA_PATH).write_text(
        (ownership.ROOT / ownership.SCHEMA_PATH).read_text(), encoding="utf-8"
    )
    targets = [
        "backend/scripts/reviewed.py",
        "backend/scripts/candidate.py",
        "backend/scripts/structural.py",
    ]
    for target in targets[:2]:
        path = tmp_path / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def run():\n    return 1\n", encoding="utf-8")
    structural = tmp_path / targets[2]
    structural.parent.mkdir(parents=True, exist_ok=True)
    structural.write_text("VALUE = 1\n", encoding="utf-8")
    test_file = tmp_path / "backend/tests/test_example.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_run():\n    pass\n", encoding="utf-8")
    for index, (status, target) in enumerate(zip(("reviewed", "candidate", "structural_only"), targets)):
        _write_json(
            tmp_path / f".ci/behavior-ownership/shared/{index}.json",
            _catalogue_record(status, target, f"behavior:{index}"),
        )
    monkeypatch.setattr(
        ownership,
        "validate_partition",
        lambda root=ownership.ROOT, **kwargs: {target: "shared" for target in targets},
    )
    monkeypatch.setattr(ownership, "_validate_remaps", lambda *args, **kwargs: None)
    monkeypatch.setattr(ownership, "_run_test_nodes", lambda *args, **kwargs: 0)
    _write_json(tmp_path / ownership.PARTITION_PATH, _partition(targets))
    result = ownership.validate_catalogue(tmp_path, group="shared")
    assert result == {
        "schema": ownership.CATALOGUE_SCHEMA,
        "group": "shared",
        "reviewed": 1,
        "candidates": 1,
        "structural_only": 1,
        "unresolved": [],
        "complete": False,
    }
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_group"):
        ownership.validate_catalogue(tmp_path, group="wrong")


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("outcomes", ["unknown"], "invalid_catalogue_outcome"),
        ("boundaries", ["mock"], "invalid_catalogue_boundary"),
        ("tests", ["not-a-node"], "invalid_catalogue_test"),
        ("callables", ["scripts.example.run", "scripts.example.run"], "duplicate_catalogue_callable"),
    ],
)
def test_reviewed_semantics_fail_closed(
    tmp_path: Path, field: str, value: object, error: str
) -> None:
    target = "backend/scripts/example.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    test_file = tmp_path / "backend/tests/test_example.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_run():\n    pass\n", encoding="utf-8")
    record = _catalogue_record("reviewed", target, "behavior:example")
    record[field] = value
    with pytest.raises(ownership.BehaviorOwnershipError, match=error):
        ownership._validate_record_semantics(tmp_path, record)


def test_catalogue_rejects_schema_and_group_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / ownership.SCHEMA_PATH).write_text(
        (ownership.ROOT / ownership.SCHEMA_PATH).read_text(), encoding="utf-8"
    )
    target = "backend/scripts/example.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    record = _catalogue_record("reviewed", target, "behavior:example")
    record["unexpected"] = True
    record_path = tmp_path / ".ci/behavior-ownership/shared/example.json"
    _write_json(record_path, record)
    monkeypatch.setattr(
        ownership, "validate_partition", lambda root=ownership.ROOT, **kwargs: {target: "shared"}
    )
    monkeypatch.setattr(ownership, "_validate_remaps", lambda *args, **kwargs: None)
    _write_json(tmp_path / ownership.PARTITION_PATH, _partition([target]))
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_catalogue_record"):
        ownership.validate_catalogue(tmp_path)
    record.pop("unexpected")
    record["group"] = "auth"
    _write_json(record_path, record)
    with pytest.raises(ownership.BehaviorOwnershipError, match="wrong_catalogue_group"):
        ownership.validate_catalogue(tmp_path)


def test_catalogue_rejects_duplicate_identity_and_supersession(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / ownership.SCHEMA_PATH).write_text(
        (ownership.ROOT / ownership.SCHEMA_PATH).read_text(), encoding="utf-8"
    )
    targets = ["backend/scripts/a.py", "backend/scripts/b.py"]
    for target in targets:
        path = tmp_path / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def run():\n    return 1\n", encoding="utf-8")
    test_file = tmp_path / "backend/tests/test_example.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_run():\n    pass\n", encoding="utf-8")
    records = [_catalogue_record("reviewed", target, "same:id") for target in targets]
    for index, record in enumerate(records):
        _write_json(tmp_path / f".ci/behavior-ownership/shared/{index}.json", record)
    monkeypatch.setattr(
        ownership,
        "validate_partition",
        lambda root=ownership.ROOT, **kwargs: {target: "shared" for target in targets},
    )
    monkeypatch.setattr(ownership, "_validate_remaps", lambda *args, **kwargs: None)
    monkeypatch.setattr(ownership, "_run_test_nodes", lambda *args, **kwargs: 0)
    _write_json(tmp_path / ownership.PARTITION_PATH, _partition(targets))
    with pytest.raises(ownership.BehaviorOwnershipError, match="duplicate_behavior_id"):
        ownership.validate_catalogue(tmp_path)
    for index, record in enumerate(records):
        record["behavior_id"] = f"behavior:{index}"
        record["supersedes_behavior_id"] = "protected:id"
        _write_json(tmp_path / f".ci/behavior-ownership/shared/{index}.json", record)
    with pytest.raises(ownership.BehaviorOwnershipError, match="duplicate_supersession"):
        ownership.validate_catalogue(tmp_path)


def test_catalogue_rejects_multiple_reviewed_owners_for_one_callable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / ownership.SCHEMA_PATH).write_text(
        (ownership.ROOT / ownership.SCHEMA_PATH).read_text(), encoding="utf-8"
    )
    target = "backend/scripts/example.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    test_file = tmp_path / "backend/tests/test_example.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_run():\n    pass\n", encoding="utf-8")
    for index in range(2):
        _write_json(
            tmp_path / f".ci/behavior-ownership/shared/{index}.json",
            _catalogue_record("reviewed", target, f"behavior:{index}"),
        )
    _write_json(tmp_path / ownership.PARTITION_PATH, _partition([target]))
    monkeypatch.setattr(
        ownership,
        "validate_partition",
        lambda root=ownership.ROOT, **kwargs: {target: "shared"},
    )
    monkeypatch.setattr(ownership, "_validate_remaps", lambda *args, **kwargs: None)
    with pytest.raises(
        ownership.BehaviorOwnershipError, match="multiple_effective_callable_owners"
    ):
        ownership.validate_catalogue(tmp_path)


def test_owned_tests_runs_only_reviewed_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(arguments, 7)

    monkeypatch.setattr(ownership.subprocess, "run", fake_run)
    code = ownership.run_owned_tests(
        tmp_path,
        [
            {"status": "reviewed", "tests": ["backend/tests/test_example.py::test_run"]},
            {"status": "candidate", "tests": ["backend/tests/test_example.py::test_ignored"]},
        ],
    )
    assert code == 7
    assert captured["arguments"][-1] == "tests/test_example.py::test_run"


def test_cli_inventory_generate_validate_and_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ownership, "eligible_targets", lambda root=ownership.ROOT: ["target"])
    monkeypatch.setattr(sys, "argv", ["behavior_ownership.py", "inventory"])
    assert ownership._main() == 0
    assert json.loads(capsys.readouterr().out) == ["target"]
    monkeypatch.setattr(ownership, "generate_candidates", lambda **kwargs: {"generated": kwargs})
    monkeypatch.setattr(sys, "argv", ["behavior_ownership.py", "generate", "--group", "auth"])
    assert ownership._main() == 0
    assert json.loads(capsys.readouterr().out)["generated"] == {"group": "auth"}
    monkeypatch.setattr(ownership, "validate_catalogue", lambda **kwargs: {"validated": kwargs})
    monkeypatch.setattr(ownership, "validate_partition", lambda **kwargs: {})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "behavior_ownership.py",
            "validate",
            "--group",
            "shared",
            "--trusted-revision",
            "main",
            "--run-owned-tests",
        ],
    )
    assert ownership._main() == 0
    assert json.loads(capsys.readouterr().out)["validated"] == {
        "group": "shared",
        "trusted_revision": "main",
        "head_revision": "HEAD",
        "run_tests": True,
    }
    monkeypatch.setattr(
        ownership,
        "build_partition",
        lambda **kwargs: {"base": kwargs["base_commit"]},
    )
    monkeypatch.setattr(sys, "argv", ["behavior_ownership.py", "partition", "--base-commit", "abc"])
    assert ownership._main() == 0
    assert json.loads(capsys.readouterr().out) == {"base": "abc"}
    monkeypatch.setattr(
        ownership,
        "eligible_targets",
        lambda root=ownership.ROOT: (_ for _ in ()).throw(ownership.BehaviorOwnershipError("bad")),
    )
    monkeypatch.setattr(sys, "argv", ["behavior_ownership.py", "inventory"])
    assert ownership._main() == 2
    assert "behavior_ownership_error:bad" in capsys.readouterr().err


def _context_artifact(**overrides: object) -> dict[str, object]:
    node = "tests/test_example.py::test_run"
    authority: dict[str, object] = {
        "schema": ownership.CONTEXT_EVIDENCE_SCHEMA,
        "authoritative": False,
        "head_sha": "a" * 40,
        "lane": "context_evidence",
        "target": "backend/scripts/example.py",
        "test_module": "tests/test_example.py",
        "collection_complete": True,
        "execution_complete": True,
        "collected_nodes": [node],
        "completed_nodes": [node],
        "skipped_nodes": [],
        "deselected_nodes": [],
        "callables": [
            {
                "callable": "scripts.example.run",
                "start_line": 1,
                "end_line": 2,
                "contexts": [{"nodeid": node, "lines": [1, 2]}],
            }
        ],
        "elapsed_seconds": 1.25,
    }
    authority.update(overrides)
    return {**authority, "artifact_digest": ownership._digest(authority)}


def _prepare_context_identity(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = root / "backend/scripts/example.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    test_module = root / "backend/tests/test_example.py"
    test_module.parent.mkdir(parents=True, exist_ok=True)
    test_module.write_text("def test_run(): pass\n", encoding="utf-8")
    monkeypatch.setattr(ownership, "_tracked_at_revision", lambda *args: True)


def test_context_evidence_is_separate_digest_bound_candidate_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "context.json"
    artifact = _context_artifact()
    _write_json(path, artifact)
    monkeypatch.setattr(ownership, "_git", lambda root, *arguments: "a" * 40)
    _prepare_context_identity(tmp_path, monkeypatch)

    result = ownership.validate_context_evidence(tmp_path, path)

    assert result["authoritative"] is False
    assert result["schema"] == ownership.CONTEXT_EVIDENCE_SCHEMA
    assert result["node_count"] == 1
    assert "status" not in artifact
    assert artifact["schema"] != ownership.CATALOGUE_SCHEMA


@pytest.mark.parametrize(
    ("updates", "error"),
    [
        ({"head_sha": "b" * 40}, "stale_context_evidence"),
        ({"completed_nodes": []}, "incomplete_context_evidence"),
        ({"skipped_nodes": ["tests/test_example.py::test_run"]}, "weakened_context_evidence"),
        (
            {"deselected_nodes": ["tests/test_example.py::test_run"]},
            "weakened_context_evidence",
        ),
    ],
)
def test_context_evidence_rejects_stale_partial_skip_and_deselect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    updates: dict[str, object],
    error: str,
) -> None:
    path = tmp_path / "context.json"
    _write_json(path, _context_artifact(**updates))
    monkeypatch.setattr(ownership, "_git", lambda root, *arguments: "a" * 40)
    _prepare_context_identity(tmp_path, monkeypatch)

    with pytest.raises(ownership.BehaviorOwnershipError, match=error):
        ownership.validate_context_evidence(tmp_path, path)


def test_context_evidence_rejects_missing_callable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "context.json"
    _write_json(path, _context_artifact(callables=[]))
    monkeypatch.setattr(ownership, "_git", lambda root, *arguments: "a" * 40)
    _prepare_context_identity(tmp_path, monkeypatch)

    with pytest.raises(
        ownership.BehaviorOwnershipError, match="incomplete_context_evidence"
    ):
        ownership.validate_context_evidence(tmp_path, path)


def test_context_evidence_rejects_digest_drift_and_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "context.json"
    artifact = _context_artifact()
    artifact["artifact_digest"] = "0" * 64
    _write_json(path, artifact)
    monkeypatch.setattr(ownership, "_git", lambda root, *arguments: "a" * 40)
    _prepare_context_identity(tmp_path, monkeypatch)
    with pytest.raises(ownership.BehaviorOwnershipError, match="digest_mismatch"):
        ownership.validate_context_evidence(tmp_path, path)
    with pytest.raises(ownership.BehaviorOwnershipError, match="output_exists"):
        ownership._write_exclusive(path, b"{}\n")


def test_build_context_evidence_reuses_lane_collection_and_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = "backend/scripts/example.py"
    target_path = tmp_path / target
    target_path.parent.mkdir(parents=True)
    target_path.write_text("def run():\n    return 1\n", encoding="utf-8")
    tests_dir = tmp_path / "backend/tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_example.py").write_text("def test_run(): pass\n", encoding="utf-8")
    node = "tests/test_example.py::test_run"
    monkeypatch.setattr(
        ownership,
        "_git",
        lambda root, *arguments: "a" * 40 if arguments[0] == "rev-parse" else "",
    )
    monkeypatch.setattr(
        ownership.test_lanes,
        "discover_test_modules",
        lambda *args: ("tests/test_example.py",),
    )
    monkeypatch.setattr(ownership, "_tracked_at_revision", lambda *args: True)

    def fake_run(arguments, *, cwd, env, check, timeout):
        assert env["PYTHONPATH"] == str(tmp_path / "backend")
        assert "UNRELATED_SECRET" not in env
        if "--collect-only" in arguments:
            Path(env[ownership.test_lanes.COLLECTED_ENV]).write_text(
                json.dumps(node) + "\n", encoding="utf-8"
            )
            Path(env[ownership.test_lanes.DESELECTED_ENV]).write_text(
                "", encoding="utf-8"
            )
            return subprocess.CompletedProcess(arguments, 0)
        metadata = Path(env[ownership.test_lanes.COLLECTED_ENV]).parent
        for suffix in ("collected", "completed"):
            (metadata / f"context.{suffix}.jsonl").write_text(
                json.dumps(node) + "\n", encoding="utf-8"
            )
        (metadata / "context.skipped.jsonl").write_text("", encoding="utf-8")
        (metadata / "context.deselected.jsonl").write_text("", encoding="utf-8")
        Path(env["COVERAGE_FILE"]).write_bytes(b"coverage")
        assert "--cov-context=test" in arguments
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(ownership.subprocess, "run", fake_run)
    monkeypatch.setattr(
        ownership,
        "_coverage_lines_by_context",
        lambda path, target_path, completed: {node: {1, 2}},
    )
    output = tmp_path / "context.json"

    artifact = ownership.build_context_evidence(
        tmp_path,
        target=target,
        test_module="tests/test_example.py",
        output=output,
    )

    assert output.stat().st_size <= ownership.CONTEXT_ARTIFACT_LIMIT_BYTES
    assert artifact["collected_nodes"] == [node]
    assert artifact["completed_nodes"] == [node]
    assert artifact["callables"][0]["contexts"] == [{"nodeid": node, "lines": [1, 2]}]

    ticks = iter((0.0, ownership.CONTEXT_RUNTIME_LIMIT_SECONDS + 1.0))
    monkeypatch.setattr(ownership.time, "monotonic", lambda: next(ticks))
    with pytest.raises(ownership.BehaviorOwnershipError, match="context_runtime_exceeded"):
        ownership.build_context_evidence(
            tmp_path,
            target=target,
            test_module="tests/test_example.py",
            output=tmp_path / "late-context.json",
        )


def test_context_output_rejects_size_and_missing_parent(tmp_path: Path) -> None:
    with pytest.raises(ownership.BehaviorOwnershipError, match="too_large"):
        ownership._write_exclusive(
            tmp_path / "large.json", b"x" * (ownership.CONTEXT_ARTIFACT_LIMIT_BYTES + 1)
        )
    with pytest.raises(ownership.BehaviorOwnershipError, match="output_parent"):
        ownership._write_exclusive(tmp_path / "missing/out.json", b"{}\n")


def test_context_identity_helpers_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed = subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")
    monkeypatch.setattr(ownership.subprocess, "run", lambda *args, **kwargs: completed)
    assert ownership._tracked_at_revision(tmp_path, "HEAD", "backend/scripts/example.py")
    completed.returncode = 1
    assert not ownership._tracked_at_revision(
        tmp_path, "HEAD", "backend/scripts/example.py"
    )
    assert not ownership._tracked_at_revision(tmp_path, "HEAD", "../unsafe.py")
    assert ownership._context_node_is_valid(
        "tests/test_example.py::test_run", "tests/test_example.py"
    )
    assert not ownership._context_node_is_valid(
        "tests/test_other.py::test_run", "tests/test_example.py"
    )
    assert not ownership._context_target_is_valid(tmp_path, "../unsafe.py")


def test_coverage_context_reader_filters_noncompleted_and_requires_every_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = "tests/test_example.py::test_run"

    class FakeCoverageData:
        def __init__(self, *, basename: str) -> None:
            self.basename = basename
            self.contexts: list[str] | None = []

        def read(self) -> None:
            return None

        def measured_contexts(self) -> set[str]:
            return {f"{node}|run", "tests/test_other.py::test_other|run"}

        def set_query_contexts(self, contexts: list[str] | None) -> None:
            self.contexts = contexts

        def lines(self, filename: str) -> list[int]:
            assert filename.endswith("example.py")
            return [1, 2]

    monkeypatch.setattr(ownership, "CoverageData", FakeCoverageData)
    result = ownership._coverage_lines_by_context(
        tmp_path / "coverage", tmp_path / "example.py", {node}
    )
    assert result == {node: {1, 2}}
    with pytest.raises(ownership.BehaviorOwnershipError, match="missing_test_context"):
        ownership._coverage_lines_by_context(
            tmp_path / "coverage", tmp_path / "example.py", {node, "missing::node"}
        )


def test_coverage_context_reader_rejects_invalid_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenCoverageData:
        def __init__(self, *, basename: str) -> None:
            pass

        def read(self) -> None:
            raise ValueError("broken")

    monkeypatch.setattr(ownership, "CoverageData", BrokenCoverageData)
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_context_coverage"):
        ownership._coverage_lines_by_context(
            tmp_path / "coverage", tmp_path / "example.py", {"tests/test_x.py::test_x"}
        )


@pytest.mark.parametrize(
    ("updates", "error"),
    [
        ({"schema": "wrong"}, "invalid_context_evidence_schema"),
        ({"elapsed_seconds": 121.0}, "invalid_context_elapsed"),
        ({"callables": "wrong"}, "invalid_context_callables"),
        (
            {
                "callables": [
                    {
                        "callable": "scripts.example.run",
                        "start_line": 2,
                        "end_line": 1,
                        "contexts": [],
                    }
                ]
            },
            "invalid_context_callables",
        ),
        (
            {
                "callables": [
                    {
                        "callable": "scripts.example.run",
                        "start_line": 1,
                        "end_line": 3,
                        "contexts": [],
                    }
                ]
            },
            "invalid_context_callables",
        ),
        ({"target": "../unsafe.py"}, "invalid_context_identity"),
        ({"test_module": "../unsafe.py"}, "invalid_context_identity"),
        ({"head_sha": "not-a-sha"}, "stale_context_evidence"),
        ({"collected_nodes": ["invalid node"], "completed_nodes": ["invalid node"]}, "incomplete_context_evidence"),
        ({"skipped_nodes": "wrong"}, "weakened_context_evidence"),
        (
            {
                "callables": [
                    {
                        "callable": "scripts.example.run",
                        "start_line": 1,
                        "end_line": 2,
                        "contexts": [{"nodeid": "missing::node", "lines": [3]}],
                    }
                ]
            },
            "invalid_context_callables",
        ),
    ],
)
def test_context_validator_rejects_invalid_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    updates: dict[str, object],
    error: str,
) -> None:
    path = tmp_path / "context.json"
    _write_json(path, _context_artifact(**updates))
    monkeypatch.setattr(ownership, "_git", lambda root, *arguments: "a" * 40)
    _prepare_context_identity(tmp_path, monkeypatch)
    with pytest.raises(ownership.BehaviorOwnershipError, match=error):
        ownership.validate_context_evidence(tmp_path, path)


def test_context_validator_rejects_unsafe_and_unknown_shape(tmp_path: Path) -> None:
    with pytest.raises(ownership.BehaviorOwnershipError, match="unsafe_context_evidence"):
        ownership.validate_context_evidence(tmp_path, tmp_path / "missing.json")
    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(tmp_path / "missing-target.json")
    with pytest.raises(ownership.BehaviorOwnershipError, match="unsafe_context_evidence"):
        ownership.validate_context_evidence(tmp_path, symlink)
    oversized = tmp_path / "oversized.json"
    with oversized.open("wb") as destination:
        destination.truncate(ownership.CONTEXT_ARTIFACT_LIMIT_BYTES + 1)
    with pytest.raises(ownership.BehaviorOwnershipError, match="too_large"):
        ownership.validate_context_evidence(tmp_path, oversized)
    path = tmp_path / "context.json"
    artifact = _context_artifact()
    artifact["unexpected"] = True
    _write_json(path, artifact)
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_context_evidence_shape"):
        ownership.validate_context_evidence(tmp_path, path)


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("runtime", "invalid_context_runtime_limit"),
        ("target", "unsafe_or_missing_target"),
        ("module", "invalid_context_test_module"),
        ("missing_module", "missing_context_test_module"),
        ("dirty", "dirty_context_tree"),
        ("untracked", "untracked_context_input"),
        ("symlink_output", "context_output_exists_or_unsafe"),
        ("output", "context_output_exists_or_unsafe"),
        ("collection", "invalid_context_collection"),
    ],
)
def test_context_builder_fails_closed_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    error: str,
) -> None:
    target = "backend/scripts/example.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    tests = tmp_path / "backend/tests"
    tests.mkdir(parents=True)
    (tests / "test_example.py").write_text("def test_run(): pass\n", encoding="utf-8")
    output = tmp_path / "context.json"
    test_module = "../unsafe.py" if case == "module" else "tests/test_example.py"
    selected_target = "backend/scripts/missing.py" if case == "target" else target
    runtime = 0.0 if case == "runtime" else ownership.CONTEXT_RUNTIME_LIMIT_SECONDS
    monkeypatch.setattr(
        ownership,
        "_git",
        lambda root, *arguments: (
            "dirty" if arguments[0] == "status" and case == "dirty" else "a" * 40
            if arguments[0] == "rev-parse"
            else ""
        ),
    )
    monkeypatch.setattr(
        ownership.test_lanes,
        "discover_test_modules",
        lambda *args: () if case == "missing_module" else ("tests/test_example.py",),
    )
    monkeypatch.setattr(
        ownership,
        "_tracked_at_revision",
        lambda *args: case != "untracked",
    )
    def fake_collection(arguments, *, cwd, env, check, timeout):
        if case != "collection":
            Path(env[ownership.test_lanes.COLLECTED_ENV]).write_text(
                json.dumps("tests/test_example.py::test_run") + "\n", encoding="utf-8"
            )
        Path(env[ownership.test_lanes.DESELECTED_ENV]).write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(arguments, 1 if case == "collection" else 0)

    monkeypatch.setattr(ownership.subprocess, "run", fake_collection)
    if case == "output":
        output.write_text("existing", encoding="utf-8")
    if case == "symlink_output":
        output.symlink_to(tmp_path / "missing-context.json")

    with pytest.raises(ownership.BehaviorOwnershipError, match=error):
        ownership.build_context_evidence(
            tmp_path,
            target=selected_target,
            test_module=test_module,
            output=output,
            runtime_limit_seconds=runtime,
        )


@pytest.mark.parametrize(
    "source",
    [
        "open('value.txt')\n",
        "if FLAG:\n    VALUE = 1\n",
        "VALUES = []\nVALUES.append(1)\n",
        "for item in VALUES:\n    VALUE = item\n",
        "raise RuntimeError('side effect')\n",
    ],
)
def test_structural_only_rejects_runtime_side_effects(tmp_path: Path, source: str) -> None:
    target = "backend/scripts/structural.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ownership.BehaviorOwnershipError, match="executable_structural_only"):
        ownership._validate_record_semantics(
            tmp_path, {"status": "structural_only", "target": target}
        )


def test_candidate_generator_reports_no_callable_target_as_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "backend/scripts/constants.py"
    monkeypatch.setattr(
        ownership,
        "validate_partition",
        lambda root=ownership.ROOT, **kwargs: {target: "shared"},
    )
    monkeypatch.setattr(ownership, "callable_names", lambda root, value: [])
    result = ownership.generate_candidates()
    assert result["candidates"] == []
    assert result["unresolved"] == [
        {"group": "shared", "target": target, "reason": "structural review required"}
    ]


def test_record_rejects_validly_shaped_missing_test_node(tmp_path: Path) -> None:
    target = "backend/scripts/example.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    record = _catalogue_record("reviewed", target, "behavior:example")
    record["tests"] = ["backend/tests/test_missing.py::test_missing"]
    with pytest.raises(ownership.BehaviorOwnershipError, match="missing_catalogue_test"):
        ownership._validate_record_semantics(tmp_path, record)


def test_callable_inventory_rejects_symlink_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("def leaked():\n    return 1\n", encoding="utf-8")
    target = tmp_path / "backend/scripts/example.py"
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    with pytest.raises(ownership.BehaviorOwnershipError, match="unsafe_or_missing_target"):
        ownership.callable_names(tmp_path, "backend/scripts/example.py")


def test_partition_rejects_recomputed_group_reassignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = "backend/scripts/example.py"
    value = _partition([target])
    value["assignments"][0]["group"] = "auth"
    authority = {key: value[key] for key in value if key != "authority_digest"}
    value["authority_digest"] = ownership._digest(authority)
    _write_json(tmp_path / ownership.PARTITION_PATH, value)
    monkeypatch.setattr(ownership, "eligible_targets", lambda root=ownership.ROOT: [target])
    _mock_partition_git(monkeypatch)
    with pytest.raises(ownership.BehaviorOwnershipError, match="partition_assignment_mismatch"):
        ownership.validate_partition(tmp_path, trusted_revision=None)


def test_partition_rejects_missing_invalid_shape_and_invalid_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ownership.BehaviorOwnershipError, match="unsafe_or_missing_partition"):
        ownership.validate_partition(tmp_path, trusted_revision=None)
    _write_json(tmp_path / ownership.PARTITION_PATH, {})
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_partition_shape"):
        ownership.validate_partition(tmp_path, trusted_revision=None)
    target = "backend/scripts/example.py"
    value = _partition([target])
    value["protected_base_commit"] = "invalid"
    authority = {key: value[key] for key in value if key != "authority_digest"}
    value["authority_digest"] = ownership._digest(authority)
    _write_json(tmp_path / ownership.PARTITION_PATH, value)
    monkeypatch.setattr(ownership, "eligible_targets", lambda root=ownership.ROOT: [target])
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_partition_base_commit"):
        ownership.validate_partition(tmp_path, trusted_revision=None)


def _reviewed_remap(target: str, behavior_id: str, supersedes: str | None = None):
    record = {
        "status": "reviewed",
        "behavior_id": behavior_id,
        "target": target,
        "tests": ["backend/tests/test_example.py::test_run"],
        "outcomes": ["return"],
        "boundaries": [],
    }
    if supersedes is not None:
        record["supersedes_behavior_id"] = supersedes
    return record


def test_remap_requires_protected_ancestry_location_and_carried_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _reviewed_remap("backend/scripts/old.py", "protected:id")
    new = _reviewed_remap("backend/scripts/new.py", "new:id", "protected:id")
    monkeypatch.setattr(ownership, "_catalogue_at_revision", lambda root, revision: [old])
    monkeypatch.setattr(
        ownership,
        "_git_show_optional",
        lambda root, revision, path: "source" if path == new["target"] else None,
    )
    ownership._validate_remaps(Path("/repo"), [new], base_sha="base", head_sha="head")
    missing = dict(new, supersedes_behavior_id="missing:id")
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_remap_ancestry"):
        ownership._validate_remaps(Path("/repo"), [missing], base_sha="base", head_sha="head")
    narrowed = dict(new, tests=[])
    with pytest.raises(ownership.BehaviorOwnershipError, match="narrowed_remap_evidence"):
        ownership._validate_remaps(Path("/repo"), [narrowed], base_sha="base", head_sha="head")
    monkeypatch.setattr(ownership, "_git_show_optional", lambda root, revision, path: "source")
    with pytest.raises(ownership.BehaviorOwnershipError, match="protected_location_still_exists"):
        ownership._validate_remaps(Path("/repo"), [new], base_sha="base", head_sha="head")


def test_remap_rejects_protected_replacement_and_multiple_owners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _reviewed_remap("backend/scripts/old.py", "protected:id")
    replacement = dict(old, tests=["backend/tests/test_example.py::test_weaker"])
    monkeypatch.setattr(ownership, "_catalogue_at_revision", lambda root, revision: [old])
    with pytest.raises(ownership.BehaviorOwnershipError, match="protected_owner_replacement"):
        ownership._validate_remaps(
            Path("/repo"), [replacement], base_sha="base", head_sha="head"
        )
    monkeypatch.setattr(ownership, "_catalogue_at_revision", lambda root, revision: [old, old])
    with pytest.raises(ownership.BehaviorOwnershipError, match="multiple_protected_owners"):
        ownership._validate_remaps(Path("/repo"), [], base_sha="base", head_sha="head")


def test_remap_requires_exactly_one_effective_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    old = _reviewed_remap("backend/scripts/old.py", "protected:id")
    new = _reviewed_remap("backend/scripts/new.py", "new:id", "protected:id")
    monkeypatch.setattr(ownership, "_catalogue_at_revision", lambda root, revision: [old])
    monkeypatch.setattr(
        ownership,
        "_git_show_optional",
        lambda root, revision, path: "source" if path == new["target"] else None,
    )
    with pytest.raises(ownership.BehaviorOwnershipError, match="missing_effective_owner"):
        ownership._validate_remaps(Path("/repo"), [], base_sha="base", head_sha="head")
    with pytest.raises(ownership.BehaviorOwnershipError, match="multiple_effective_owners"):
        ownership._validate_remaps(Path("/repo"), [old, new], base_sha="base", head_sha="head")


def test_catalogue_fails_when_exact_test_collection_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = "backend/scripts/example.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    test_file = tmp_path / "backend/tests/test_example.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_run():\n    pass\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / ownership.SCHEMA_PATH).write_text(
        (ownership.ROOT / ownership.SCHEMA_PATH).read_text(), encoding="utf-8"
    )
    _write_json(
        tmp_path / ".ci/behavior-ownership/shared/example.json",
        _catalogue_record("reviewed", target, "behavior:example"),
    )
    _write_json(tmp_path / ownership.PARTITION_PATH, _partition([target]))
    monkeypatch.setattr(
        ownership,
        "validate_partition",
        lambda root=ownership.ROOT, **kwargs: {target: "shared"},
    )
    monkeypatch.setattr(ownership, "_validate_remaps", lambda *args, **kwargs: None)
    monkeypatch.setattr(ownership, "_run_test_nodes", lambda *args, **kwargs: 1)
    with pytest.raises(ownership.BehaviorOwnershipError, match="stale_catalogue_test"):
        ownership.validate_catalogue(tmp_path)


def test_low_level_invalid_inputs_fail_closed(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    with pytest.raises(ownership.BehaviorOwnershipError, match="bad_json"):
        ownership._read_json(invalid, "bad_json")
    with pytest.raises(
        ownership.BehaviorOwnershipError, match="unsafe_or_missing_catalogue_schema"
    ):
        ownership.load_schema(tmp_path)
    target = tmp_path / "backend/scripts/broken.py"
    target.parent.mkdir(parents=True)
    target.write_text("if:\n", encoding="utf-8")
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_target_syntax"):
        ownership._is_strictly_structural(tmp_path, "backend/scripts/broken.py")


def test_candidate_supersession_and_invalid_group_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = "backend/scripts/example.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    record = _catalogue_record("candidate", target, "candidate:id")
    record["supersedes_behavior_id"] = "protected:id"
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_non_reviewed_supersession"):
        ownership._validate_record_semantics(tmp_path, record)
    monkeypatch.setattr(ownership, "validate_partition", lambda root=ownership.ROOT: {})
    with pytest.raises(ownership.BehaviorOwnershipError, match="invalid_group"):
        ownership.generate_candidates(group="wrong")


def test_structural_supersession_fails_with_typed_error(tmp_path: Path) -> None:
    target = "backend/scripts/constants.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("VALUE = 1\n", encoding="utf-8")
    record = _catalogue_record("structural_only", target, "structural:id")
    record["supersedes_behavior_id"] = "protected:id"
    with pytest.raises(
        ownership.BehaviorOwnershipError, match="invalid_non_reviewed_supersession"
    ):
        ownership._validate_record_semantics(tmp_path, record)


def test_catalogue_record_must_reside_in_declared_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / ownership.SCHEMA_PATH).write_text(
        (ownership.ROOT / ownership.SCHEMA_PATH).read_text(), encoding="utf-8"
    )
    target = "backend/scripts/example.py"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_text("def run():\n    return 1\n", encoding="utf-8")
    test_file = tmp_path / "backend/tests/test_example.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_run():\n    pass\n", encoding="utf-8")
    _write_json(
        tmp_path / ".ci/behavior-ownership/auth/misplaced.json",
        _catalogue_record("reviewed", target, "behavior:example"),
    )
    _write_json(tmp_path / ownership.PARTITION_PATH, _partition([target]))
    monkeypatch.setattr(
        ownership,
        "validate_partition",
        lambda root=ownership.ROOT, **kwargs: {target: "shared"},
    )
    with pytest.raises(ownership.BehaviorOwnershipError, match="misplaced_catalogue_record"):
        ownership.validate_catalogue(tmp_path)


def test_remap_rejects_missing_new_location(monkeypatch: pytest.MonkeyPatch) -> None:
    old = _reviewed_remap("backend/scripts/old.py", "protected:id")
    new = _reviewed_remap("backend/scripts/new.py", "new:id", "protected:id")
    monkeypatch.setattr(ownership, "_catalogue_at_revision", lambda root, revision: [old])
    monkeypatch.setattr(ownership, "_git_show_optional", lambda root, revision, path: None)
    with pytest.raises(ownership.BehaviorOwnershipError, match="missing_remap_location"):
        ownership._validate_remaps(Path("/repo"), [new], base_sha="base", head_sha="head")


def test_collect_only_runner_adds_collection_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    def fake_run(arguments, **kwargs):
        captured.extend(arguments)
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(ownership.subprocess, "run", fake_run)
    assert ownership._run_test_nodes(
        tmp_path,
        [{"status": "reviewed", "tests": ["backend/tests/test_example.py::test_run"]}],
        collect_only=True,
    ) == 0
    assert "--collect-only" in captured
