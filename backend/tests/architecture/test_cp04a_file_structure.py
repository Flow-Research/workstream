"""Structural limits for the CP04A behavior slice."""

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_cp04a_changed_behavior_files_remain_below_500_lines() -> None:
    paths = (
        ROOT / "app/modules/contributions/service.py",
        ROOT / "app/modules/contributions/repository.py",
        ROOT / "app/modules/contributions/policy_validation.py",
        ROOT / "app/modules/contributions/api/policies.py",
        ROOT / "app/modules/compensation/policy_binding_service.py",
        ROOT / "app/modules/projects/contribution_policy.py",
    )
    assert all(len(path.read_text(encoding="utf-8").splitlines()) < 500 for path in paths)
    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) < 500
        for path in (ROOT / "tests/contributions").glob("*.py")
    )


def test_cp04a_tests_map_one_to_one_to_contract_behavior_atoms() -> None:
    contract = (
        ROOT.parent
        / ".agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks"
        / "WS-ARCH-001-CP04A-con-policy-draft-behavior.md"
    ).read_text(encoding="utf-8")
    required = re.findall(r"`(tests/[^`]+\.py)::([A-Za-z0-9_]+)`", contract)
    assert required
    for relative, name in required:
        if relative == "tests/contributions/test_policy_negative_scope.py":
            if name in {
                "test_cp04a_exposes_no_publish_behavior",
                "test_cp04a_exposes_no_retire_behavior",
            }:
                continue
            name = {
                "test_cp04a_cannot_change_current_version_identity": (
                    "test_cp04b_cannot_bypass_publication_to_change_current_version"
                )
            }.get(name, name.replace("test_cp04a_", "test_cp04b_", 1))
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert len(re.findall(rf"(?:async )?def {re.escape(name)}\(", source)) == 1


def test_cp04a_tests_do_not_invoke_other_test_functions() -> None:
    tests = ROOT / "tests/contributions"
    for path in tests.glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id.startswith("test_")
            for node in ast.walk(tree)
        )
