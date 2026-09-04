"""Architecture proof for incremental AUTH test-structure recovery."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import test_structure_boundary as structure

ROOT = Path(__file__).resolve().parents[3]
INITIATIVE = ROOT / ".ci/auth-boundaries"
POLICY = INITIATIVE / "TEST_STRUCTURE_POLICY.md"
LEDGER = INITIATIVE / "TEST_STRUCTURE_DEBT.json"


def _write(path: Path, content: str) -> None:
    """Create one UTF-8 fixture file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _canonical(path: Path, value: object) -> None:
    """Write canonical JSON expected by the validator."""
    _write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def test_repository_structural_debt_equals_the_frozen_ledger() -> None:
    """Current AUTH debt and policy hashes exactly match committed evidence."""
    structure.validate(ROOT, POLICY, LEDGER)


def test_pol03a_production_package_is_inside_zero_growth_scope() -> None:
    """The modular compilation package cannot escape production size enforcement."""
    scoped = ROOT / structure.POL_03A_PRODUCTION_ROOT
    assert scoped == ROOT / "backend/app/modules/projects/guide_compilation"
    assert scoped.is_dir()


def test_every_pol03a_test_is_inside_zero_growth_scope() -> None:
    """No focused compilation test can escape size or weakening detection."""
    expected = set((ROOT / structure.POL_03A_TEST_ROOT).rglob("*.py"))
    observed = set(structure.scoped_test_paths(ROOT))
    assert expected
    assert expected <= observed


def test_pol03a_skip_or_xfail_is_detected(tmp_path: Path) -> None:
    """A focused compilation test cannot disable its proof."""
    path = tmp_path / structure.POL_03A_TEST_ROOT / "test_disabled.py"
    _write(path, "import pytest\npytestmark = pytest.mark.skip\n")
    assert path in structure.scoped_test_paths(tmp_path)
    assert structure.weak_python(path)


def test_inventory_records_one_oversized_production_function(tmp_path: Path) -> None:
    """A production callable beyond its hard limit enters the debt inventory."""
    body = "\n".join(f"    value_{index} = {index}" for index in range(101))
    _write(
        tmp_path / "backend/app/modules/authorization/service.py",
        f"def oversized():\n{body}\n",
    )
    items = structure.observed_debt(tmp_path)
    functions = [item for item in items if item.kind == "production_function"]
    assert len(functions) == 1
    assert functions[0].qualified_symbol == "oversized"
    assert functions[0].observed_lines == 102


def test_inventory_records_one_mixed_test_beyond_the_hard_limit(tmp_path: Path) -> None:
    """An AUTH test beyond 120 lines is recorded independently of file size."""
    body = "\n".join(f"    assert {index} == {index}" for index in range(120))
    _write(
        tmp_path / "backend/tests/test_auth_boundary.py",
        f"def test_too_many_assertions():\n{body}\n",
    )
    items = structure.observed_debt(tmp_path)
    functions = [item for item in items if item.kind == "test_function"]
    assert len(functions) == 1
    assert functions[0].qualified_symbol == "test_too_many_assertions"
    assert functions[0].observed_lines == 121


def test_changed_debt_hash_is_rejected_as_stale(tmp_path: Path) -> None:
    """A ledger cannot silently bless changed oversized source."""
    value = structure.load_ledger(LEDGER)
    value["entries"][0]["content_sha256"] = "0" * 64
    path = tmp_path / "ledger.json"
    _canonical(path, value)
    with pytest.raises(structure.TestStructureError, match="structural_debt_mismatch"):
        structure.validate(ROOT, POLICY, path)


@pytest.mark.parametrize("change", ("new", "growth", "same_size_rewrite"))
def test_trusted_ledger_rejects_new_grown_or_unshrunk_debt(change: str) -> None:
    """Editing the JSON cannot bless a new or non-shrinking debt item."""
    trusted = structure.load_ledger(LEDGER)
    current = json.loads(json.dumps(trusted))
    if change == "new":
        item = dict(current["entries"][0])
        item["path"] = "backend/tests/test_auth_new.py"
        current["entries"].append(item)
        current["entries"].sort(
            key=lambda value: (
                value["kind"],
                value["path"],
                value["qualified_symbol"] or "",
                value["start_line"],
            )
        )
    elif change == "growth":
        current["entries"][0]["end_line"] += 1
        current["entries"][0]["observed_lines"] += 1
    else:
        current["entries"][0]["content_sha256"] = "0" * 64
    with pytest.raises(
        structure.TestStructureError,
        match="new_structural_debt|structural_debt_growth|structural_debt_changed_without_shrink",
    ):
        structure._validate_trusted_transition(current, trusted)


def test_trusted_transition_reconciles_only_unchanged_base_paths() -> None:
    """A stale measurement is tolerated only when its source path did not change."""
    trusted = structure.load_ledger(LEDGER)
    current = json.loads(json.dumps(trusted))
    target = current["entries"][0]
    target["end_line"] += 1
    target["observed_lines"] += 1
    target["content_sha256"] = "0" * 64

    structure._validate_trusted_transition(current, trusted, changed_paths=set())
    with pytest.raises(structure.TestStructureError, match="structural_debt_growth"):
        structure._validate_trusted_transition(
            current,
            trusted,
            changed_paths={target["path"]},
        )


def test_trusted_ledger_follows_an_exact_git_rename(tmp_path: Path) -> None:
    """Cutover relocation keeps comparing against the protected-base ledger."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    old_path = tmp_path / "legacy/debt.json"
    trusted = structure.load_ledger(LEDGER)
    _canonical(old_path, trusted)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    subprocess.run(["git", "branch", "origin/main"], cwd=tmp_path, check=True)
    new_path = tmp_path / ".ci/auth-boundaries/debt.json"
    new_path.parent.mkdir(parents=True)
    old_path.rename(new_path)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "relocate"], cwd=tmp_path, check=True)

    assert structure._trusted_ledger(tmp_path, new_path) == trusted

    grown = json.loads(json.dumps(trusted))
    item = dict(grown["entries"][0])
    item["path"] = "backend/tests/test_auth_new.py"
    grown["entries"].append(item)
    grown["entries"].sort(
        key=lambda value: (
            value["kind"],
            value["path"],
            value["qualified_symbol"] or "",
            value["start_line"],
        )
    )
    with pytest.raises(structure.TestStructureError, match="new_structural_debt"):
        structure._validate_trusted_transition(
            grown,
            structure._trusted_ledger(tmp_path, new_path),
        )


def test_trusted_ledger_follows_declared_cutover_relocation(tmp_path: Path) -> None:
    """An archived old ledger still protects its new active CI successor."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    old_relative = structure.TRUSTED_LEDGER_RELOCATIONS[
        ".ci/auth-boundaries/TEST_STRUCTURE_DEBT.json"
    ]
    old_path = tmp_path / old_relative
    trusted = structure.load_ledger(LEDGER)
    _canonical(old_path, trusted)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    subprocess.run(["git", "branch", "origin/main"], cwd=tmp_path, check=True)

    archive = tmp_path / ".commitrail/initiatives/WS-AUTH-003/pre-cutover/debt.json"
    _canonical(archive, trusted)
    active = tmp_path / ".ci/auth-boundaries/TEST_STRUCTURE_DEBT.json"
    _canonical(active, trusted)
    old_path.unlink()
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "cutover"], cwd=tmp_path, check=True)

    loaded = structure._trusted_ledger(tmp_path, active)
    assert loaded == trusted
    grown = json.loads(json.dumps(trusted))
    item = dict(grown["entries"][0])
    item["path"] = "backend/tests/test_auth_new.py"
    grown["entries"].append(item)
    grown["entries"].sort(
        key=lambda value: (
            value["kind"],
            value["path"],
            value["qualified_symbol"] or "",
            value["start_line"],
        )
    )
    with pytest.raises(structure.TestStructureError, match="new_structural_debt"):
        structure._validate_trusted_transition(grown, loaded)


@pytest.mark.parametrize(
    "source",
    (
        "import pytest\npytest.skip('disabled')\n",
        "import pytest\npytest.importorskip('optional')\n",
        "import pytest\npytestmark = pytest.mark.skipif(True, reason='disabled')\n",
        "import pytest\n@pytest.mark.xfail\ndef test_auth(): assert False\n",
        "import unittest\n@unittest.skip('disabled')\ndef test_auth(): pass\n",
    ),
)
def test_skip_and_xfail_mechanisms_are_detected(tmp_path: Path, source: str) -> None:
    """Every proof-weakening framework mechanism fails the AUTH scope gate."""
    path = tmp_path / "backend/tests/test_auth.py"
    _write(path, source)
    assert structure.weak_python(path)


def test_malformed_exception_schema_fails_closed(tmp_path: Path) -> None:
    """A vague line-limit exception cannot enter the structural ledger."""
    value = structure.load_ledger(LEDGER)
    value["exceptions"] = [{"reason": "large test"}]
    path = tmp_path / "ledger.json"
    _canonical(path, value)
    with pytest.raises(structure.TestStructureError, match="invalid_exception"):
        structure.load_ledger(path)


def test_non_string_policy_digest_fails_with_the_mapped_ledger_error(tmp_path: Path) -> None:
    """Malformed digest types cannot escape the validator with a raw TypeError."""
    value = structure.load_ledger(LEDGER)
    value["policy_sha256"] = 42
    path = tmp_path / "ledger.json"
    _canonical(path, value)
    with pytest.raises(structure.TestStructureError, match="invalid_debt_ledger"):
        structure.load_ledger(path)


def test_assertion_map_rejects_a_missing_new_test_node(tmp_path: Path) -> None:
    """Decomposition evidence must point to a test that exists now."""
    maps = tmp_path / "assertion-maps"
    value = {
        "chunk_id": "WS-AUTH-003-example",
        "mappings": [
            {
                "invariant_category": "replay",
                "new_test_node": "tests/test_auth.py::test_missing",
                "old_assertion_id": "old-replay-denial",
                "old_content_sha256": "0" * 64,
                "old_revision": "0" * 40,
                "old_source_span": [10, 12],
                "old_test_node": "tests/test_auth.py::test_old",
                "security_dimensions": {
                    name: {"not_applicable_reason": "not part of this invariant"}
                    for name in structure.SECURITY_DIMENSIONS
                },
                "target_layer": "service",
            }
        ],
        "schema": structure.MAP_SCHEMA,
    }
    _canonical(maps / "example.json", value)
    with pytest.raises(structure.TestStructureError, match="missing_new_test_node"):
        structure.validate_assertion_maps(tmp_path, maps)


def test_old_assertion_inventory_rejects_a_bogus_test_node() -> None:
    """An assertion map cannot invent an old test that never owned proof."""
    source = "def test_real():\n    assert True\n"
    with pytest.raises(structure.TestStructureError, match="missing_old_test_node"):
        structure._assertion_inventory(source, "tests/test_auth.py::test_fake")


def test_old_assertion_inventory_binds_exact_span_and_hash() -> None:
    """Old assertion identity derives from exact trusted source bytes."""
    source = "def test_real():\n    assert True\n"
    inventory = structure._assertion_inventory(source, "tests/test_auth.py::test_real")
    assert inventory == {(2, 2): structure.hashlib.sha256(b"    assert True\n").hexdigest()}


@pytest.mark.parametrize(
    ("span", "digest"),
    (([3, 3], "0" * 64), ([2, 2], "0" * 64)),
)
def test_old_assertion_mapping_rejects_a_bogus_span_or_hash(
    span: list[int], digest: str
) -> None:
    """A cosmetic map cannot claim proof bytes absent from trusted source."""
    actual = structure.hashlib.sha256(b"    assert True\n").hexdigest()
    mapping = {
        "old_source_span": span,
        "old_content_sha256": digest,
        "old_assertion_id": f"assertion:{span[0]}:{span[1]}:{digest}",
    }
    with pytest.raises(structure.TestStructureError, match="old_assertion_mismatch"):
        structure._validate_old_assertion(mapping, {(2, 2): actual})


def test_assertion_mapping_rejects_an_unknown_test_layer() -> None:
    """Decomposed proof must land in one of the policy's named test layers."""
    value = {
        "invariant_category": "replay",
        "new_test_node": "tests/test_auth.py::test_new",
        "old_assertion_id": "assertion:2:2:" + "0" * 64,
        "old_content_sha256": "0" * 64,
        "old_revision": "0" * 40,
        "old_source_span": [2, 2],
        "old_test_node": "tests/test_auth.py::test_old",
        "security_dimensions": {
            name: {"not_applicable_reason": "not part of this invariant"}
            for name in structure.SECURITY_DIMENSIONS
        },
        "target_layer": "miscellaneous",
    }
    with pytest.raises(structure.TestStructureError, match="invalid_target_layer"):
        structure._validate_mapping_entry(value, {"tests/test_auth.py::test_new"})


def test_assertion_inventory_detects_an_omitted_old_assertion() -> None:
    """Every old assertion span requires exactly one preserved disposition."""
    source = "def test_real():\n    assert True\n    assert 1 == 1\n"
    inventory = structure._assertion_inventory(source, "tests/test_auth.py::test_real")
    key = ("0" * 40, "tests/test_auth.py::test_real")
    with pytest.raises(structure.TestStructureError, match="incomplete_assertion_disposition"):
        structure._require_complete_dispositions({key: inventory}, {key: {(2, 2)}})


def test_policy_limit_drift_fails_closed(tmp_path: Path) -> None:
    """Changing a documented hard limit without code alignment is rejected."""
    changed = POLICY.read_text(encoding="utf-8").replace(
        "test function target: 75 lines; hard maximum: 120 lines",
        "test function target: 75 lines; hard maximum: 121 lines",
    )
    path = tmp_path / "policy.md"
    _write(path, changed)
    with pytest.raises(structure.TestStructureError, match="policy_limit_mismatch"):
        structure.build_ledger(ROOT, path)
