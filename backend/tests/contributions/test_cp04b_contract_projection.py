"""Ensure every named CP04B proof node remains executable."""

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = (
    ROOT
    / ".ci/behavior-contracts/contribution-policy-publication-behavior.md"
)


def test_every_cp04b_acceptance_atom_projects_to_an_exact_test_name() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    missing: list[str] = []
    references = re.findall(r"`tests/contributions/([^`:]+\.py)(?:::([^`]+))?`", text)
    for filename, selectors in references:
        path = ROOT / "backend/tests/contributions" / filename
        if not path.exists():
            missing.append(filename)
            continue
        names = {
            node.name
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for expected in re.findall(r"test_[A-Za-z0-9_]+", selectors):
            if expected not in names:
                missing.append(f"{filename}::{expected}")
    all_names = {
        node.name
        for path in (ROOT / "backend/tests").rglob("test_*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    standalone_text = re.sub(r"`[^`]*\.py[^`]*`", "", text)
    for expected in set(re.findall(r"test_[A-Za-z0-9_]+", standalone_text)):
        if expected not in all_names:
            missing.append(expected)
    assert missing == []
