#!/usr/bin/env python3
"""Freeze AUTH structural debt while allowing capability-by-capability repair."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Iterable

SCRIPTS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_ROOT))
from coverage_policy import analyze_python, weak_python  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "workstream.auth-test-structure-debt.v1"
MAP_SCHEMA = "workstream.auth-assertion-map.v1"
PRODUCTION_ROOT = "backend/app/modules/authorization"
RECOVERY_PATHS = (
    "backend/scripts/authorization_boundary.py",
    "backend/scripts/test_structure_boundary.py",
    "backend/tests/architecture/test_authorization_boundary.py",
    "backend/tests/architecture/test_test_structure_boundary.py",
)
HARD_LIMITS = {
    "production_file": 1200,
    "production_function": 100,
    "test_file": 1200,
    "test_function": 120,
    "test_helper": 100,
}
SECURITY_DIMENSIONS = (
    "concurrency",
    "lock_order",
    "denial_side_effects",
    "replay",
    "revocation",
    "evidence",
    "transaction_ownership",
    "concealment",
)
TEST_LAYERS = frozenset({"domain", "service", "persistence", "integration", "end_to_end"})


class TestStructureError(RuntimeError):
    """The structural ledger, assertion maps, or scoped source is unsafe."""


@dataclass(frozen=True, order=True, slots=True)
class DebtItem:
    """One exact hard-limit violation frozen for incremental removal."""

    kind: str
    path: str
    qualified_symbol: str | None
    start_line: int
    end_line: int
    content_sha256: str
    observed_lines: int
    hard_limit: int
    capability: str
    removal_chunk: str

    def as_dict(self) -> dict[str, Any]:
        """Return the canonical JSON representation."""
        return {
            "capability": self.capability,
            "content_sha256": self.content_sha256,
            "end_line": self.end_line,
            "hard_limit": self.hard_limit,
            "kind": self.kind,
            "observed_lines": self.observed_lines,
            "path": self.path,
            "qualified_symbol": self.qualified_symbol,
            "removal_chunk": self.removal_chunk,
            "start_line": self.start_line,
        }


def _safe_relative(path: Path, root: Path) -> str:
    """Return a safe repository-relative POSIX path."""
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError) as exc:
        raise TestStructureError("unsafe_path") from exc
    if ".." in PurePosixPath(relative).parts:
        raise TestStructureError("unsafe_path")
    return relative


def _read_source(path: Path) -> tuple[str, list[str], ast.Module]:
    """Read and parse one UTF-8 Python source file."""
    try:
        source = path.read_text(encoding="utf-8")
        return source, source.splitlines(keepends=True), ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise TestStructureError("invalid_python_source") from exc


def _digest_lines(lines: list[str], start: int, end: int) -> str:
    """Hash an exact inclusive source span."""
    payload = "".join(lines[start - 1 : end]).encode()
    return hashlib.sha256(payload).hexdigest()


def _imports_authorization(tree: ast.Module) -> bool:
    """Return whether a test statically imports the AUTH package or public API."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.startswith("app.modules.authorization") for alias in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("app.modules.authorization")
        ):
            return True
    return False


def scoped_test_paths(root: Path) -> list[Path]:
    """Return exact AUTH-related tests plus recovery architecture tests."""
    tests_root = root / "backend" / "tests"
    result: set[Path] = set()
    for path in tests_root.rglob("*.py"):
        if "auth" in path.name:
            result.add(path)
            continue
        _, _, tree = _read_source(path)
        if _imports_authorization(tree):
            result.add(path)
    for value in RECOVERY_PATHS:
        path = root / value
        if value.startswith("backend/tests/") and path.is_file():
            result.add(path)
    return sorted(result)


def _decorator_name(node: ast.expr) -> str:
    """Return a dotted decorator name when it is statically knowable."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _decorator_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _is_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return whether a function is declared as a pytest fixture."""
    return any(_decorator_name(item).endswith("fixture") for item in node.decorator_list)


def _function_kind(node: ast.FunctionDef | ast.AsyncFunctionDef, *, test_file: bool) -> str:
    """Classify one callable against its applicable hard limit."""
    if not test_file:
        return "production_function"
    if node.name.startswith("test_") and not _is_fixture(node):
        return "test_function"
    return "test_helper"


def _qualified_functions(tree: ast.Module) -> Iterable[tuple[str, ast.AST]]:
    """Yield qualified function names without losing nested/class ownership."""
    def walk(body: list[ast.stmt], prefix: tuple[str, ...]) -> Iterable[tuple[str, ast.AST]]:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = ".".join((*prefix, node.name))
                yield qualified, node
                yield from walk(node.body, (*prefix, node.name))
            elif isinstance(node, ast.ClassDef):
                yield from walk(node.body, (*prefix, node.name))

    return walk(tree.body, ())


def _debt_for_path(path: Path, root: Path, *, test_file: bool) -> list[DebtItem]:
    """Return every hard-limit violation in one scoped source file."""
    _, lines, tree = _read_source(path)
    relative = _safe_relative(path, root)
    file_kind = "test_file" if test_file else "production_file"
    items: list[DebtItem] = []
    if len(lines) > HARD_LIMITS[file_kind]:
        items.append(
            DebtItem(
                file_kind,
                relative,
                None,
                1,
                len(lines),
                _digest_lines(lines, 1, len(lines)),
                len(lines),
                HARD_LIMITS[file_kind],
                "unassigned_legacy_auth",
                "WS-AUTH-003-CLOSE",
            )
        )
    for symbol, raw_node in _qualified_functions(tree):
        node = raw_node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.end_lineno is None:
            raise TestStructureError("missing_function_span")
        kind = _function_kind(node, test_file=test_file)
        observed = node.end_lineno - node.lineno + 1
        if observed <= HARD_LIMITS[kind]:
            continue
        items.append(
            DebtItem(
                kind,
                relative,
                symbol,
                node.lineno,
                node.end_lineno,
                _digest_lines(lines, node.lineno, node.end_lineno),
                observed,
                HARD_LIMITS[kind],
                "unassigned_legacy_auth",
                "WS-AUTH-003-CLOSE",
            )
        )
    return items


def observed_debt(root: Path) -> list[DebtItem]:
    """Inventory all current hard-limit violations in the AUTH recovery scope."""
    production = sorted((root / PRODUCTION_ROOT).rglob("*.py"))
    recovery_scripts = [
        root / value
        for value in RECOVERY_PATHS
        if value.startswith("backend/scripts/") and (root / value).is_file()
    ]
    items: list[DebtItem] = []
    for path in [*production, *recovery_scripts]:
        items.extend(_debt_for_path(path, root, test_file=False))
    for path in scoped_test_paths(root):
        items.extend(_debt_for_path(path, root, test_file=True))
    return sorted(items)


def _canonical_json(value: Any) -> str:
    """Serialize canonical human-readable JSON."""
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _policy_limits(policy: Path) -> dict[str, int]:
    """Require the normative Markdown policy to retain the coded hard limits."""
    try:
        text = policy.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TestStructureError("invalid_policy") from exc
    patterns = {
        "test_function": r"test function target: 75 lines; hard maximum: (\d+) lines",
        "test_helper": r"test fixture/helper target: 60 lines; hard maximum: (\d+) lines",
        "production_function": r"production function target: 60 lines; hard maximum: (\d+) lines",
        "test_file": r"test file target: 800 lines; hard maximum: ([\d,]+) lines",
        "production_file": r"production file target: 800 lines; hard maximum: ([\d,]+) lines",
    }
    found: dict[str, int] = {}
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if len(matches) != 1:
            raise TestStructureError("invalid_policy_limits")
        found[key] = int(matches[0].replace(",", ""))
    if found != HARD_LIMITS:
        raise TestStructureError("policy_limit_mismatch")
    return found


def build_ledger(root: Path, policy: Path) -> dict[str, Any]:
    """Build the canonical frozen structural-debt ledger."""
    _policy_limits(policy)
    policy_digest = hashlib.sha256(policy.read_bytes()).hexdigest()
    return {
        "entries": [item.as_dict() for item in observed_debt(root)],
        "exceptions": [],
        "policy_sha256": policy_digest,
        "schema": SCHEMA,
    }


def _load_json(path: Path, error: str) -> dict[str, Any]:
    """Load one required JSON object."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TestStructureError(error) from exc
    if not isinstance(value, dict):
        raise TestStructureError(error)
    return value


def _validate_exception(value: Any) -> None:
    """Validate one narrowly reviewed hard-limit exception."""
    required = {
        "capability",
        "path",
        "primary_invariant",
        "qualified_symbol",
        "reviewed_by",
        "removal_chunk",
        "technical_reason",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise TestStructureError("invalid_exception")
    if not all(isinstance(value[key], str) and value[key].strip() for key in required):
        raise TestStructureError("invalid_exception")


def load_ledger(path: Path) -> dict[str, Any]:
    """Load and validate canonical debt-ledger shape."""
    value = _load_json(path, "invalid_debt_ledger")
    if set(value) != {"entries", "exceptions", "policy_sha256", "schema"}:
        raise TestStructureError("invalid_debt_ledger")
    if value["schema"] != SCHEMA or not re.fullmatch(r"[0-9a-f]{64}", value["policy_sha256"]):
        raise TestStructureError("invalid_debt_ledger")
    if not isinstance(value["entries"], list) or not isinstance(value["exceptions"], list):
        raise TestStructureError("invalid_debt_ledger")
    parsed = _parse_debt_entries(value["entries"])
    if value["entries"] != [item.as_dict() for item in parsed]:
        raise TestStructureError("invalid_debt_ledger")
    for item in value["exceptions"]:
        _validate_exception(item)
    if path.read_text(encoding="utf-8") != _canonical_json(value):
        raise TestStructureError("noncanonical_debt_ledger")
    return value


def _parse_debt_entries(values: list[Any]) -> list[DebtItem]:
    """Parse canonical, unique, ordered structural-debt entries."""
    fields = set(DebtItem.__dataclass_fields__)
    items: list[DebtItem] = []
    for value in values:
        if not isinstance(value, dict) or set(value) != fields:
            raise TestStructureError("invalid_debt_entry")
        try:
            item = DebtItem(**value)
        except TypeError as exc:
            raise TestStructureError("invalid_debt_entry") from exc
        if (
            item.kind not in HARD_LIMITS
            or not isinstance(item.path, str)
            or not item.path.startswith("backend/")
            or ".." in PurePosixPath(item.path).parts
            or (item.qualified_symbol is not None and not isinstance(item.qualified_symbol, str))
            or type(item.start_line) is not int
            or type(item.end_line) is not int
            or type(item.observed_lines) is not int
            or type(item.hard_limit) is not int
            or item.start_line < 1
            or item.end_line < item.start_line
            or item.observed_lines != item.end_line - item.start_line + 1
            or item.hard_limit != HARD_LIMITS[item.kind]
            or item.observed_lines <= item.hard_limit
            or not isinstance(item.content_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", item.content_sha256)
            or not isinstance(item.capability, str)
            or not item.capability.strip()
            or not isinstance(item.removal_chunk, str)
            or not item.removal_chunk.strip()
        ):
            raise TestStructureError("invalid_debt_entry")
        items.append(item)
    if items != sorted(items) or len(items) != len(set(items)):
        raise TestStructureError("invalid_debt_entry_order")
    return items


def _trusted_ledger(root: Path, ledger_path: Path) -> dict[str, Any] | None:
    """Load the protected-main ledger, allowing absence only for foundation creation."""
    relative = _safe_relative(ledger_path, root)
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "origin/main^{commit}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode:
        raise TestStructureError("trusted_revision_unavailable")
    result = subprocess.run(
        ["git", "show", f"origin/main:{relative}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TestStructureError("invalid_trusted_debt_ledger") from exc
    if not isinstance(value, dict):
        raise TestStructureError("invalid_trusted_debt_ledger")
    return value


def _validate_trusted_transition(current: dict[str, Any], trusted: dict[str, Any] | None) -> None:
    """Reject new debt, growth, and rewrites that do not shrink frozen debt."""
    if trusted is None:
        return
    if set(trusted) != {"entries", "exceptions", "policy_sha256", "schema"}:
        raise TestStructureError("invalid_trusted_debt_ledger")
    if trusted.get("schema") != SCHEMA:
        raise TestStructureError("invalid_trusted_debt_ledger")
    trusted_items = _parse_debt_entries(trusted.get("entries", []))
    current_items = _parse_debt_entries(current["entries"])
    def key(item: DebtItem) -> tuple[str, str, str | None]:
        return item.kind, item.path, item.qualified_symbol

    trusted_by_key = {key(item): item for item in trusted_items}
    current_by_key = {key(item): item for item in current_items}
    if set(current_by_key) - set(trusted_by_key):
        raise TestStructureError("new_structural_debt")
    for item_key in set(current_by_key) & set(trusted_by_key):
        before = trusted_by_key[item_key]
        after = current_by_key[item_key]
        if after.observed_lines > before.observed_lines:
            raise TestStructureError("structural_debt_growth")
        if after.content_sha256 != before.content_sha256 and after.observed_lines >= before.observed_lines:
            raise TestStructureError("structural_debt_changed_without_shrink")


def _assert_current_matches(root: Path, policy: Path, ledger: dict[str, Any]) -> None:
    """Require exact policy and observed-debt parity."""
    _policy_limits(policy)
    if hashlib.sha256(policy.read_bytes()).hexdigest() != ledger["policy_sha256"]:
        raise TestStructureError("stale_policy_digest")
    actual = [item.as_dict() for item in observed_debt(root)]
    if actual != ledger["entries"]:
        raise TestStructureError("structural_debt_mismatch")
    scoped_tests = scoped_test_paths(root)
    if any(weak_python(path) for path in scoped_tests):
        raise TestStructureError("skip_or_xfail_in_auth_scope")


def _test_nodes(root: Path) -> set[str]:
    """Collect static pytest function node IDs for assertion-map references."""
    result: set[str] = set()
    for path in scoped_test_paths(root):
        _, _, tree = _read_source(path)
        relative = _safe_relative(path, root).removeprefix("backend/")
        for symbol, node in _qualified_functions(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                result.add(f"{relative}::{symbol.replace('.', '::')}")
    return result


def _validate_mapping_entry(value: Any, nodes: set[str]) -> None:
    """Validate one exact old-to-new assertion preservation entry."""
    required = {
        "invariant_category",
        "new_test_node",
        "old_assertion_id",
        "old_content_sha256",
        "old_revision",
        "old_source_span",
        "old_test_node",
        "security_dimensions",
        "target_layer",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise TestStructureError("invalid_assertion_mapping")
    strings = required - {"old_source_span", "security_dimensions"}
    if not all(isinstance(value[key], str) and value[key].strip() for key in strings):
        raise TestStructureError("invalid_assertion_mapping")
    if value["new_test_node"] not in nodes:
        raise TestStructureError("missing_new_test_node")
    if value["target_layer"] not in TEST_LAYERS:
        raise TestStructureError("invalid_target_layer")
    span = value["old_source_span"]
    if (
        not isinstance(span, list)
        or len(span) != 2
        or not all(type(item) is int and item > 0 for item in span)
        or span[0] > span[1]
        or not re.fullmatch(r"[0-9a-f]{64}", value["old_content_sha256"])
        or not re.fullmatch(r"[0-9a-f]{40}", value["old_revision"])
    ):
        raise TestStructureError("invalid_assertion_mapping")
    dimensions = value["security_dimensions"]
    if not isinstance(dimensions, dict) or set(dimensions) != set(SECURITY_DIMENSIONS):
        raise TestStructureError("invalid_assertion_mapping")
    for disposition in dimensions.values():
        if disposition == "preserved":
            continue
        if (
            not isinstance(disposition, dict)
            or set(disposition) != {"not_applicable_reason"}
            or not isinstance(disposition["not_applicable_reason"], str)
            or not disposition["not_applicable_reason"].strip()
        ):
            raise TestStructureError("invalid_assertion_mapping")


def _old_source(root: Path, revision: str, node_id: str) -> str:
    """Load one old test module from an exact ancestor commit."""
    test_path = node_id.split("::", 1)[0]
    if not test_path.startswith("tests/") or not test_path.endswith(".py"):
        raise TestStructureError("invalid_old_test_node")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if ancestry.returncode:
        raise TestStructureError("invalid_old_revision")
    result = subprocess.run(
        ["git", "show", f"{revision}:backend/{test_path}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise TestStructureError("missing_old_test_source")
    return result.stdout


def _assertion_inventory(source: str, node_id: str) -> dict[tuple[int, int], str]:
    """Derive every framework-aware assertion span/hash inside one old test node."""
    try:
        tree, analysis = analyze_python(source)
    except (SyntaxError, ValueError) as exc:
        raise TestStructureError("invalid_old_test_source") from exc
    symbol = node_id.split("::", 1)[1].replace("::", ".") if "::" in node_id else ""
    functions = {
        name: node
        for name, node in _qualified_functions(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    node = functions.get(symbol)
    if node is None or node.end_lineno is None or not node.name.startswith("test_"):
        raise TestStructureError("missing_old_test_node")
    lines = source.splitlines(keepends=True)
    inventory = {
        (start, end): _digest_lines(lines, start, end)
        for start, end in analysis.assertion_ranges
        if node.lineno <= start <= end <= node.end_lineno
    }
    if not inventory:
        raise TestStructureError("old_test_has_no_assertions")
    return inventory


def _require_complete_dispositions(
    inventories: dict[tuple[str, str], dict[tuple[int, int], str]],
    mapped_spans: dict[tuple[str, str], set[tuple[int, int]]],
) -> None:
    """Require exactly one disposition for every trusted old assertion span."""
    for revision_node, inventory in inventories.items():
        if mapped_spans.get(revision_node, set()) != set(inventory):
            raise TestStructureError("incomplete_assertion_disposition")


def _validate_old_assertion(
    mapping: dict[str, Any],
    inventory: dict[tuple[int, int], str],
) -> tuple[int, int]:
    """Bind one mapping to an exact assertion span and digest from old source."""
    span = tuple(mapping["old_source_span"])
    digest = inventory.get(span)
    if digest is None or digest != mapping["old_content_sha256"]:
        raise TestStructureError("old_assertion_mismatch")
    expected_id = f"assertion:{span[0]}:{span[1]}:{digest}"
    if mapping["old_assertion_id"] != expected_id:
        raise TestStructureError("old_assertion_id_mismatch")
    return span


def validate_assertion_maps(root: Path, maps_dir: Path) -> None:
    """Validate every capability assertion map and reject duplicate old proof IDs."""
    if not maps_dir.exists():
        return
    nodes = _test_nodes(root)
    dispositions: set[tuple[str, str, str]] = set()
    mapped_spans: dict[tuple[str, str], set[tuple[int, int]]] = {}
    inventories: dict[tuple[str, str], dict[tuple[int, int], str]] = {}
    for path in sorted(maps_dir.glob("*.json")):
        value = _load_json(path, "invalid_assertion_map")
        if set(value) != {"chunk_id", "mappings", "schema"} or value["schema"] != MAP_SCHEMA:
            raise TestStructureError("invalid_assertion_map")
        if not isinstance(value["chunk_id"], str) or not value["chunk_id"].strip():
            raise TestStructureError("invalid_assertion_map")
        if not isinstance(value["mappings"], list) or not value["mappings"]:
            raise TestStructureError("invalid_assertion_map")
        for mapping in value["mappings"]:
            _validate_mapping_entry(mapping, nodes)
            revision_node = (mapping["old_revision"], mapping["old_test_node"])
            inventory = inventories.setdefault(
                revision_node,
                _assertion_inventory(
                    _old_source(root, mapping["old_revision"], mapping["old_test_node"]),
                    mapping["old_test_node"],
                ),
            )
            span = _validate_old_assertion(mapping, inventory)
            key = (*revision_node, mapping["old_assertion_id"])
            if key in dispositions:
                raise TestStructureError("duplicate_assertion_disposition")
            dispositions.add(key)
            mapped_spans.setdefault(revision_node, set()).add(span)
    _require_complete_dispositions(inventories, mapped_spans)


def validate(root: Path, policy: Path, ledger_path: Path) -> None:
    """Validate current structural debt, proof integrity, and assertion maps."""
    ledger = load_ledger(ledger_path)
    _assert_current_matches(root, policy, ledger)
    _validate_trusted_transition(ledger, _trusted_ledger(root, ledger_path))
    validate_assertion_maps(root, ledger_path.parent / "assertion-maps")


def main() -> int:
    """Generate or validate the AUTH structural debt ledger."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("--policy", required=True, type=Path)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--policy", required=True, type=Path)
    validate_parser.add_argument("--ledger", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            print(_canonical_json(build_ledger(REPOSITORY_ROOT, args.policy)), end="")
        else:
            validate(REPOSITORY_ROOT, args.policy, args.ledger)
    except (TestStructureError, OSError, ValueError) as exc:
        print(f"test-structure-boundary: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
