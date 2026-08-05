#!/usr/bin/env python3
"""Select and execute bounded changed-scope mutation pilots fail closed."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from fnmatch import fnmatchcase
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
from typing import Any


def _repository_root() -> Path:
    """Locate the archive root from either original or mutmut-copied code."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "scripts/git_delta.py").is_file():
            return candidate
    raise RuntimeError("repository_root_not_found")


ROOT = _repository_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.git_delta import changed_files  # noqa: E402


SCHEMA_VERSION = 1
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
CHUNK_RE = re.compile(r"^WS-[A-Z]+-[0-9]{3}-[A-Z0-9]+$")
TEST_NODE_RE = re.compile(r"^backend/tests/test_[A-Za-z0-9_/]+\.py::[^\s]+$")
CALLABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]+$")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
ELIGIBLE_PREFIXES = ("backend/app/", "backend/scripts/")
OBSERVABLE_OUTCOMES = {
    "return",
    "persisted_state",
    "emitted_fact",
    "denial",
    "mapped_error",
    "idempotent_replay",
    "recovery_outcome",
}
REAL_BOUNDARIES = {"postgresql", "minio", "http", "lock", "trigger", "concurrency"}
CALIBRATION_TARGET = "backend/scripts/mutation_policy.py"
CALIBRATION_CALLABLES = (
    "scripts.mutation_policy._strong_calibration",
    "scripts.mutation_policy._weak_calibration",
)
CALIBRATION_TESTS = (
    "backend/tests/test_mutation_policy.py::TestMutationPolicy::test_strong_calibration_asserts_the_exact_boundary",
    "backend/tests/test_mutation_policy.py::TestMutationPolicy::test_weak_calibration_deliberately_asserts_only_the_result_type",
)
WEAK_CALIBRATION_FILTER = "scripts.mutation_policy.x__weak_calibration__mutmut_*"
STRONG_CALIBRATION_FILTER = "scripts.mutation_policy.x__strong_calibration__mutmut_*"
# workstream-mutation-capability:discover-v1
POLICY_CAPABILITY_MARKER = "workstream-mutation-capability:discover-v1"
RUNTIME_ENV_ALLOWLIST = {
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "SSL_CERT_FILE",
    "TEMP",
    "TMP",
    "TMPDIR",
    "TZ",
    "VIRTUAL_ENV",
}
OUTCOMES = (
    "generated",
    "killed",
    "survived",
    "timeout",
    "suspicious",
    "excluded",
    "error",
)
STATUS_BY_EXIT_CODE: dict[int | None, str] = {
    0: "survived",
    1: "killed",
    3: "killed",
    -24: "timeout",
    24: "timeout",
    152: "timeout",
    255: "timeout",
    35: "suspicious",
    36: "timeout",
    5: "excluded",
    33: "excluded",
    34: "excluded",
    37: "killed",
    2: "error",
    -11: "error",
    -9: "error",
    None: "excluded",
}


class MutationPolicyError(RuntimeError):
    """The mutation pilot contract is unsafe, incomplete, or stale."""


def _strong_calibration(value: int) -> bool:
    """Provide a behavior whose boundary is asserted exactly by the pilot."""
    return value > 0


def _weak_calibration(value: int) -> bool:
    """Provide an intentionally under-asserted behavior for pilot calibration."""
    return value > 0


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _minimal_runtime_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Return only non-authority runtime values for untrusted candidate code."""
    values = os.environ if source is None else source
    environment = {key: values[key] for key in RUNTIME_ENV_ALLOWLIST if key in values}
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["PYTHONHASHSEED"] = "0"
    return environment


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        raise MutationPolicyError(f"git_command_failed:{arguments[0]}")
    return output


def _safe_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise MutationPolicyError("unsafe_path")
    return path


def _eligible_target(path: str) -> bool:
    candidate = _safe_path(path)
    return (
        candidate.suffix == ".py"
        and candidate.name != "__init__.py"
        and any(path.startswith(prefix) for prefix in ELIGIBLE_PREFIXES)
        and "/tests/" not in f"/{path}"
    )


def _regular_repository_file(root: Path, value: str) -> bool:
    """Return whether every component is non-symlink and the leaf is regular."""
    candidate = root
    try:
        for part in _safe_path(value).parts:
            candidate = candidate / part
            if candidate.is_symlink():
                return False
        return candidate.is_file()
    except OSError:
        return False


def discover_claim_path(root: Path, base_sha: str, head_sha: str) -> Path | None:
    """Discover one exact changed behavior claim without workflow input."""
    candidates = sorted(
        path
        for path in changed_files(base_sha, head_sha, repository_root=root, include_local=False)
        if path.startswith(".ci/behavior-claims/")
        and path.endswith(".json")
        and path != ".ci/behavior-claims/example.behavior-claim.json"
    )
    if len(candidates) > 1:
        raise MutationPolicyError("multiple_behavior_claims")
    if not candidates:
        return None
    candidate = root / candidates[0]
    if not _regular_repository_file(root, candidates[0]):
        raise MutationPolicyError("invalid_behavior_claim_path")
    return candidate


def _diff_lines(root: Path, base_sha: str, head_sha: str, path: str) -> tuple[set[int], set[int]]:
    """Return exact old/new line numbers touched by a zero-context diff."""
    output = _git(root, "diff", "--unified=0", "--no-ext-diff", base_sha, head_sha, "--", path)
    old_lines: set[int] = set()
    new_lines: set[int] = set()
    for line in output.splitlines():
        match = HUNK_RE.match(line)
        if match is None:
            continue
        old_start, old_count, new_start, new_count = match.groups()
        old_size = int(old_count or "1")
        new_size = int(new_count or "1")
        old_lines.update(range(int(old_start), int(old_start) + old_size))
        new_lines.update(range(int(new_start), int(new_start) + new_size))
    return old_lines, new_lines


def _source_at(root: Path, revision: str, path: str) -> str:
    return _git(root, "show", f"{revision}:{path}")


def _callable_spans(
    source: str, module: str
) -> tuple[
    list[tuple[int, int, str]],
    list[tuple[int, int]],
    list[tuple[int, int]],
]:
    """Return callable, declaration, and unsupported executable spans."""
    module_declaration_factories = frozenset({"frozenset"})
    declaration_factory_imports = {
        "dataclasses": frozenset({"dataclass"}),
        "pydantic": frozenset({"Field"}),
        "sqlalchemy": frozenset(
            {
                "CheckConstraint",
                "DateTime",
                "ForeignKey",
                "ForeignKeyConstraint",
                "Index",
                "String",
                "UniqueConstraint",
                "Uuid",
                "text",
            }
        ),
        "sqlalchemy.orm": frozenset({"mapped_column", "relationship"}),
    }
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise MutationPolicyError("invalid_target_syntax") from exc
    callables: list[tuple[int, int, str]] = []
    declarations: list[tuple[int, int]] = []
    executable: list[tuple[int, int]] = []
    import_bindings: dict[str, set[str]] = {}
    approved_imports: dict[str, str] = {}
    sqlalchemy_func_imports: dict[str, str] = {}
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom) and statement.module is not None:
            approved = declaration_factory_imports.get(statement.module, frozenset())
            for item in statement.names:
                local_name = item.asname or item.name
                source_name = f"{statement.module}.{item.name}"
                import_bindings.setdefault(local_name, set()).add(source_name)
                if item.name in approved:
                    approved_imports[local_name] = source_name
                if statement.module in {"sqlalchemy", "sqlalchemy.sql"} and item.name == "func":
                    sqlalchemy_func_imports[local_name] = source_name
        elif isinstance(statement, ast.Import):
            for item in statement.names:
                local_name = item.asname or item.name.split(".", 1)[0]
                import_bindings.setdefault(local_name, set()).add(item.name)

    def bound_names(target: ast.expr) -> set[str]:
        if isinstance(target, ast.Name):
            return {target.id}
        if isinstance(target, (ast.Tuple, ast.List)):
            return set().union(*(bound_names(item) for item in target.elts))
        if isinstance(target, ast.Starred):
            return bound_names(target.value)
        return set()

    shadowed_names: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            shadowed_names.add(statement.name)
        elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            shadowed_names.update(set().union(*(bound_names(target) for target in targets)))
    approved_factory_names = {
        name
        for name, source in approved_imports.items()
        if import_bindings.get(name) == {source} and name not in shadowed_names
    }
    sqlalchemy_func_names = {
        name
        for name, source in sqlalchemy_func_imports.items()
        if import_bindings.get(name) == {source} and name not in shadowed_names
    }
    safe_builtin_factories = module_declaration_factories - set(import_bindings) - shadowed_names

    def declaration_value(node: ast.expr | None, *, class_scope: bool) -> bool:
        if node is None:
            return True
        if isinstance(node, (ast.Constant, ast.Name, ast.Attribute)):
            return True
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return all(declaration_value(item, class_scope=class_scope) for item in node.elts)
        if isinstance(node, ast.Dict):
            return all(
                declaration_value(item, class_scope=class_scope)
                for item in (*node.keys, *node.values)
                if item is not None
            )
        if isinstance(node, ast.UnaryOp):
            return declaration_value(node.operand, class_scope=class_scope)
        if isinstance(node, ast.Starred):
            return declaration_value(node.value, class_scope=class_scope)
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "split"
                and not class_scope
                and isinstance(node.func.value, ast.Constant)
                and isinstance(node.func.value.value, str)
            ):
                return not node.args and not node.keywords
            approved_call = (
                (isinstance(node.func, ast.Name) and name in approved_factory_names)
                or (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in sqlalchemy_func_names
                    and node.func.attr == "now"
                )
                or (
                    not class_scope
                    and isinstance(node.func, ast.Name)
                    and name in safe_builtin_factories
                )
            )
            return approved_call and all(
                declaration_value(item, class_scope=class_scope)
                for item in (*node.args, *(item.value for item in node.keywords))
            )
        return False

    def visit(nodes: list[ast.stmt], parents: tuple[str, ...] = ()) -> None:
        for node in nodes:
            end = getattr(node, "end_lineno", node.lineno)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = min([node.lineno, *[item.lineno for item in node.decorator_list]])
                qualified = ".".join((module, *parents, node.name))
                callables.append((start, end, qualified))
                visit(node.body, (*parents, node.name))
            elif isinstance(node, ast.ClassDef):
                start = min([node.lineno, *[item.lineno for item in node.decorator_list]])
                decorators_valid = all(
                    (isinstance(item, ast.Name) and item.id in approved_factory_names)
                    or (isinstance(item, ast.Call) and declaration_value(item, class_scope=True))
                    for item in node.decorator_list
                )
                bases_valid = all(
                    declaration_value(item, class_scope=True)
                    for item in (*node.bases, *(item.value for item in node.keywords))
                )
                destination = declarations if decorators_valid and bases_valid else executable
                destination.append((start, node.lineno))
                visit(node.body, (*parents, node.name))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                declarations.append((node.lineno, end))
            elif isinstance(node, ast.Assign) and declaration_value(
                node.value, class_scope=bool(parents)
            ):
                declarations.append((node.lineno, end))
            elif isinstance(node, ast.AnnAssign) and declaration_value(
                node.value, class_scope=bool(parents)
            ):
                declarations.append((node.lineno, end))
            elif (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                declarations.append((node.lineno, end))
            else:
                executable.append((node.lineno, end))

    visit(tree.body)
    return callables, declarations, executable


def _map_changed_lines(source: str, module: str, lines: set[int]) -> tuple[set[str], bool, bool]:
    callables, declarations, executable = _callable_spans(source, module)
    owners: set[str] = set()
    unmapped = False
    declaration_changed = False
    for line in lines:
        matches = [item for item in callables if item[0] <= line <= item[1]]
        if matches:
            owners.add(min(matches, key=lambda item: item[1] - item[0])[2])
        elif any(start <= line <= end for start, end in declarations):
            declaration_changed = True
        elif any(start <= line <= end for start, end in executable):
            unmapped = True
    return owners, declaration_changed, unmapped


def changed_target_ownership(
    root: Path, base_sha: str, head_sha: str, target: str
) -> tuple[list[str], bool]:
    """Return exact callable owners and whether declaration evidence is also required."""
    module = target.removeprefix("backend/").removesuffix(".py").replace("/", ".")
    delta_base = _git(root, "merge-base", base_sha, head_sha)
    old_lines, new_lines = _diff_lines(root, delta_base, head_sha, target)
    current_source = _source_at(root, head_sha, target)
    current, current_declarations, current_unmapped = _map_changed_lines(
        current_source, module, new_lines
    )
    try:
        base_source = _source_at(root, delta_base, target)
    except MutationPolicyError:
        base_source = ""
    previous: set[str] = set()
    previous_declarations = False
    previous_unmapped = False
    if base_source:
        previous, previous_declarations, previous_unmapped = _map_changed_lines(
            base_source, module, old_lines
        )
        base_classes = {
            f"{module}.{node.name}"
            for node in ast.walk(ast.parse(base_source))
            if isinstance(node, ast.ClassDef)
        }
        current_classes = {
            f"{module}.{node.name}"
            for node in ast.walk(ast.parse(current_source))
            if isinstance(node, ast.ClassDef)
        }
        if base_classes - current_classes:
            raise MutationPolicyError("unmappable_changed_logic")
    available = {item[2] for item in _callable_spans(current_source, module)[0]}
    removed = previous - available
    if current_unmapped or previous_unmapped or removed:
        raise MutationPolicyError("unmappable_changed_logic")
    derived = sorted(current | previous)
    declaration_changed = current_declarations or previous_declarations
    if not derived and not declaration_changed:
        raise MutationPolicyError("zero_changed_ownership")
    return derived, declaration_changed


def changed_callables(
    root: Path, base_sha: str, head_sha: str, target: str, *, allow_unmapped: bool = False
) -> list[str]:
    """Derive complete current callable ownership for executable target hunks."""
    if allow_unmapped:
        module = target.removeprefix("backend/").removesuffix(".py").replace("/", ".")
        delta_base = _git(root, "merge-base", base_sha, head_sha)
        old_lines, new_lines = _diff_lines(root, delta_base, head_sha, target)
        current_source = _source_at(root, head_sha, target)
        current, _, _ = _map_changed_lines(current_source, module, new_lines)
        try:
            base_source = _source_at(root, delta_base, target)
        except MutationPolicyError:
            base_source = ""
        previous = _map_changed_lines(base_source, module, old_lines)[0] if base_source else set()
        derived = sorted(current | previous)
        if not derived:
            raise MutationPolicyError("zero_changed_callables")
        return derived
    return changed_target_ownership(root, base_sha, head_sha, target)[0]


def _read_claim(path: Path | None, root: Path, expected_chunk: str) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MutationPolicyError("invalid_behavior_claim_json") from exc
    if not isinstance(value, dict) or set(value) != {"schema_version", "chunk_id", "claims"}:
        raise MutationPolicyError("invalid_behavior_claim_shape")
    if value["schema_version"] != SCHEMA_VERSION:
        raise MutationPolicyError("unsupported_behavior_claim_schema")
    if value["chunk_id"] != expected_chunk or CHUNK_RE.fullmatch(expected_chunk) is None:
        raise MutationPolicyError("stale_behavior_claim_chunk")
    claims = value["claims"]
    if not isinstance(claims, list) or len(claims) > 8:
        raise MutationPolicyError("invalid_behavior_claim_count")
    normalized: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {
            "target",
            "callables",
            "tests",
            "outcomes",
            "boundaries",
        }:
            raise MutationPolicyError("invalid_behavior_claim")
        target = claim["target"]
        tests = claim["tests"]
        if not isinstance(target, str) or not _eligible_target(target):
            raise MutationPolicyError("ineligible_claim_target")
        if target in seen_targets:
            raise MutationPolicyError("duplicate_claim_target")
        seen_targets.add(target)
        if not _regular_repository_file(root, target):
            raise MutationPolicyError("missing_claim_target")
        if not isinstance(tests, list) or not tests or len(tests) > 12:
            raise MutationPolicyError("invalid_claim_tests")
        callables = claim["callables"]
        if (
            not isinstance(callables, list)
            or len(callables) > 24
            or any(
                not isinstance(item, str) or CALLABLE_RE.fullmatch(item) is None
                for item in callables
            )
            or len(set(callables)) != len(callables)
        ):
            raise MutationPolicyError("invalid_claim_callables")
        target_module = target.removeprefix("backend/").removesuffix(".py").replace("/", ".")
        if any(not item.startswith(f"{target_module}.") for item in callables):
            raise MutationPolicyError("claim_callable_target_mismatch")
        normalized_tests: list[str] = []
        for node in tests:
            if not isinstance(node, str) or TEST_NODE_RE.fullmatch(node) is None:
                raise MutationPolicyError("invalid_claim_test_node")
            module = node.split("::", 1)[0]
            _safe_path(module)
            if not _regular_repository_file(root, module):
                raise MutationPolicyError("missing_claim_test_module")
            if node in normalized_tests:
                raise MutationPolicyError("duplicate_claim_test_node")
            normalized_tests.append(node)
        outcomes = claim["outcomes"]
        if (
            not isinstance(outcomes, list)
            or not outcomes
            or any(
                not isinstance(item, str) or item not in OBSERVABLE_OUTCOMES for item in outcomes
            )
            or len(set(outcomes)) != len(outcomes)
        ):
            raise MutationPolicyError("invalid_claim_outcomes")
        boundaries = claim["boundaries"]
        if (
            not isinstance(boundaries, list)
            or any(not isinstance(item, str) or item not in REAL_BOUNDARIES for item in boundaries)
            or len(set(boundaries)) != len(boundaries)
        ):
            raise MutationPolicyError("invalid_claim_boundaries")
        normalized.append(
            {
                "target": target,
                "callables": sorted(callables),
                "tests": sorted(normalized_tests),
                "outcomes": sorted(outcomes),
                "boundaries": sorted(boundaries),
            }
        )
    return sorted(normalized, key=lambda item: item["target"])


def build_selection(
    root: Path,
    base_sha: str,
    head_sha: str,
    chunk_id: str,
    claim_path: Path | None,
) -> dict[str, Any]:
    """Build deterministic mandatory changed targets plus additive claims."""
    if SHA_RE.fullmatch(base_sha) is None or SHA_RE.fullmatch(head_sha) is None:
        raise MutationPolicyError("invalid_revision")
    resolved_head = _git(root, "rev-parse", head_sha)
    resolved_base = _git(root, "rev-parse", base_sha)
    if resolved_head != head_sha or resolved_base != base_sha:
        raise MutationPolicyError("non_exact_revision")
    changed = changed_files(
        base_sha,
        head_sha,
        repository_root=root,
        include_local=False,
    )
    delta_base = _git(root, "merge-base", base_sha, head_sha)
    deleted = set(
        filter(
            None,
            _git(
                root, "diff", "--diff-filter=D", "--name-only", delta_base, head_sha, "--"
            ).splitlines(),
        )
    )
    deleted_targets = sorted(path for path in changed if _eligible_target(path) and path in deleted)
    if deleted_targets:
        raise MutationPolicyError("deleted_eligible_target")
    changed_targets = sorted(
        path for path in changed if _eligible_target(path) and path not in deleted
    )
    if claim_path is not None:
        expected_claim = root / ".ci" / "behavior-claims" / f"{chunk_id}.json"
        try:
            resolved_claim = claim_path.resolve(strict=True)
        except OSError as exc:
            raise MutationPolicyError("invalid_behavior_claim_path") from exc
        if resolved_claim != expected_claim.resolve(strict=False) or claim_path.is_symlink():
            raise MutationPolicyError("invalid_behavior_claim_path")
    claims = _read_claim(claim_path, root, chunk_id)
    claims_by_target = {claim["target"]: claim for claim in claims}
    unowned_targets = sorted(set(changed_targets) - set(claims_by_target))
    if unowned_targets:
        raise MutationPolicyError("changed_target_without_behavior_claim")
    for target, claim in claims_by_target.items():
        module = target.removeprefix("backend/").removesuffix(".py").replace("/", ".")
        available = {
            item[2] for item in _callable_spans(_source_at(root, head_sha, target), module)[0]
        }
        if not set(claim["callables"]).issubset(available):
            raise MutationPolicyError("missing_claim_callable")
    targets = sorted(set(changed_targets) | set(claims_by_target))
    bootstrap = False
    blocking_policy = chunk_id == "WS-QUAL-001-05M"
    try:
        base_policy = _source_at(root, base_sha, "backend/scripts/mutation_policy.py")
    except MutationPolicyError:
        base_policy = ""
    if chunk_id == "WS-QUAL-001-05M":
        bootstrap = POLICY_CAPABILITY_MARKER not in base_policy
    blocking_policy = blocking_policy or POLICY_CAPABILITY_MARKER in base_policy
    ownership = {
        target: (
            (changed_callables(root, base_sha, head_sha, target, allow_unmapped=True), False)
            if bootstrap
            else changed_target_ownership(root, base_sha, head_sha, target)
        )
        for target in changed_targets
    }
    derived_callables = {target: value[0] for target, value in ownership.items()}
    for target, required in derived_callables.items():
        if set(required) != set(claims_by_target[target]["callables"]):
            raise MutationPolicyError("unowned_changed_callable")
    if any(
        not claim["callables"]
        for target, claim in claims_by_target.items()
        if target not in changed_targets
    ):
        raise MutationPolicyError("empty_claim_only_callables")
    if blocking_policy:
        targets = sorted(set(targets) | {CALIBRATION_TARGET})
    declaration_targets = sorted(
        target for target, (_, has_declarations) in ownership.items() if has_declarations
    )
    mutation_targets = sorted(
        target for target, claim in claims_by_target.items() if claim["callables"]
    )
    if blocking_policy:
        mutation_targets = sorted(set(mutation_targets) | {CALIBRATION_TARGET})
    tests = {node for claim in claims for node in claim["tests"]}
    if blocking_policy:
        tests.update(CALIBRATION_TESTS)
    tests = sorted(tests)
    if not targets:
        raise MutationPolicyError("zero_mutation_targets")
    if not tests:
        raise MutationPolicyError("zero_owning_tests")
    return {
        "schema_version": SCHEMA_VERSION,
        "chunk_id": chunk_id,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "head_tree": _git(root, "rev-parse", f"{head_sha}^{{tree}}"),
        "changed_paths": changed,
        "changed_targets": changed_targets,
        "changed_callables": derived_callables,
        "declaration_targets": declaration_targets,
        "mutation_targets": mutation_targets,
        "claims": claims,
        "target_owners": [
            {
                **(
                    {
                        "target": target,
                        "callables": sorted(
                            set(claims_by_target.get(target, {}).get("callables", []))
                            | (
                                set(CALIBRATION_CALLABLES)
                                if blocking_policy and target == CALIBRATION_TARGET
                                else set()
                            )
                        ),
                        "tests": sorted(
                            set(claims_by_target.get(target, {}).get("tests", []))
                            | (
                                set(CALIBRATION_TESTS)
                                if blocking_policy and target == CALIBRATION_TARGET
                                else set()
                            )
                        ),
                        "outcomes": sorted(
                            set(claims_by_target.get(target, {}).get("outcomes", []))
                            | (
                                {"return"}
                                if blocking_policy and target == CALIBRATION_TARGET
                                else set()
                            )
                        ),
                        "boundaries": claims_by_target.get(target, {}).get("boundaries", []),
                    }
                ),
                "selection_reason": (
                    "changed"
                    if target in changed_targets
                    else "claim"
                    if target in claims_by_target
                    else "calibration"
                ),
            }
            for target in targets
        ],
        "targets": targets,
        "tests": tests,
    }


def discover_selection(root: Path, base_sha: str, head_sha: str) -> dict[str, Any]:
    """Discover applicability and the only canonical claim from the git delta."""
    changed = changed_files(base_sha, head_sha, repository_root=root, include_local=False)
    delta_base = _git(root, "merge-base", base_sha, head_sha)
    deleted = set(
        filter(
            None,
            _git(
                root, "diff", "--diff-filter=D", "--name-only", delta_base, head_sha, "--"
            ).splitlines(),
        )
    )
    deleted_targets = sorted(path for path in changed if _eligible_target(path) and path in deleted)
    if deleted_targets:
        raise MutationPolicyError("deleted_eligible_target")
    changed_targets = sorted(
        path for path in changed if _eligible_target(path) and path not in deleted
    )
    claim_path = discover_claim_path(root, base_sha, head_sha)
    if not changed_targets and claim_path is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "applicability": "not_applicable",
            "base_sha": base_sha,
            "head_sha": head_sha,
            "changed_paths": changed,
        }
    if claim_path is None:
        raise MutationPolicyError("missing_behavior_claim")
    try:
        raw = json.loads(claim_path.read_text(encoding="utf-8"))
        chunk_id = raw["chunk_id"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MutationPolicyError("invalid_behavior_claim_json") from exc
    selection = build_selection(root, base_sha, head_sha, chunk_id, claim_path)
    selection["applicability"] = "applicable"
    selection["claim_path"] = claim_path.relative_to(root).as_posix()
    return selection


def _write_mutmut_config(backend: Path, selection: dict[str, Any]) -> str:
    """Replace any static mutmut section with exact policy-derived config."""
    pyproject = backend / "pyproject.toml"
    try:
        original = pyproject.read_text(encoding="utf-8")
        tomllib.loads(original)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise MutationPolicyError("invalid_mutation_config") from exc
    relative_targets = [
        target.removeprefix("backend/")
        for target in selection.get("mutation_targets", selection["targets"])
    ]
    source_paths = sorted({target.split("/", 1)[0] for target in relative_targets})
    test_nodes = [node.removeprefix("backend/") for node in selection["tests"]]
    lines = original.splitlines()
    retained: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == "[tool.mutmut]":
            skipping = True
            continue
        if skipping and line.startswith("["):
            skipping = False
        if not skipping:
            retained.append(line)
    config_lines = [
        "[tool.mutmut]",
        f"source_paths = {json.dumps(source_paths)}",
        f"only_mutate = {json.dumps(relative_targets)}",
        f"pytest_add_cli_args_test_selection = {json.dumps(test_nodes)}",
        'pytest_add_cli_args = ["-q", "--noconftest"]',
        "use_git_change_detection = false",
        "debug = true",
        "timeout_multiplier = 4.0",
        "timeout_constant = 2.0",
    ]
    rendered = "\n".join([*retained, "", *config_lines, ""])
    pyproject.write_text(rendered, encoding="utf-8")
    try:
        config = tomllib.loads(rendered)["tool"]["mutmut"]
    except (tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise MutationPolicyError("invalid_generated_mutation_config") from exc
    digest = _sha256(_json_bytes(config))
    return digest


def _reject_disposable_special_files(disposable: Path) -> None:
    """Reject symlinks and non-regular archive entries before PR code runs."""
    for candidate in disposable.rglob("*"):
        try:
            mode = candidate.lstat().st_mode
        except OSError as exc:
            raise MutationPolicyError("invalid_disposable_entry") from exc
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise MutationPolicyError("invalid_disposable_entry")


def _mutant_filters(selection: dict[str, Any]) -> list[str]:
    """Translate reviewed qualified callables into exact mutmut name globs."""
    filters: list[str] = []
    for owner in selection["target_owners"]:
        target = owner.get("target")
        if not isinstance(target, str) or not target:
            raise MutationPolicyError("missing_owner_target")
        target_module = target.removeprefix("backend/").removesuffix(".py").replace("/", ".")
        for callable_name in owner["callables"]:
            relative = callable_name.removeprefix(f"{target_module}.")
            filters.append(f"{target_module}.x_{relative.replace('.', '__')}__mutmut_*")
    return sorted(set(filters))


def classify_outcomes(
    counts: dict[str, int], mutants: list[dict[str, str]], filters: list[str]
) -> dict[str, Any]:
    """Produce the closed blocking verdict for complete mutation outcomes."""
    if set(counts) != set(OUTCOMES) or counts["generated"] != len(mutants):
        raise MutationPolicyError("incomplete_mutation_outcomes")
    if any(not isinstance(value, int) or value < 0 for value in counts.values()):
        raise MutationPolicyError("invalid_mutation_outcomes")
    controls: list[str] = []
    blockers: list[dict[str, str]] = []
    for mutant in mutants:
        name = mutant.get("name")
        outcome = mutant.get("outcome")
        if not isinstance(name, str) or outcome not in OUTCOMES[1:]:
            raise MutationPolicyError("unknown_mutation_outcome")
        selected = any(fnmatchcase(name, pattern) for pattern in filters)
        weak_control = fnmatchcase(name, WEAK_CALIBRATION_FILTER)
        if outcome == "killed":
            continue
        if outcome == "survived" and weak_control and selected:
            controls.append(name)
            continue
        if outcome == "excluded" and not selected:
            continue
        blockers.append({"name": name, "outcome": outcome})
    return {
        "status": "pass" if not blockers else "block",
        "classification": "calibrated" if controls else "strict",
        "calibration_controls": sorted(controls),
        "blockers": sorted(blockers, key=lambda item: (item["outcome"], item["name"])),
    }


def policy_self_test() -> None:
    """Prove the protected evaluator blocks and permits only closed outcomes."""
    filters = [WEAK_CALIBRATION_FILTER]
    outcomes = {name: 0 for name in OUTCOMES}
    outcomes.update({"generated": 1, "survived": 1})
    control = [
        {"name": "scripts.mutation_policy.x__weak_calibration__mutmut_1", "outcome": "survived"}
    ]
    if classify_outcomes(outcomes, control, filters)["status"] != "pass":
        raise MutationPolicyError("self_test_control_failed")
    blocker = [{"name": "scripts.control.x_changed__mutmut_1", "outcome": "survived"}]
    if classify_outcomes(outcomes, blocker, filters)["status"] != "block":
        raise MutationPolicyError("self_test_blocker_failed")


def _validate_calibration(mutants: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    """Validate only the exact repository-owned strong and weak controls."""
    strong = [
        mutant for mutant in mutants if fnmatchcase(mutant["name"], STRONG_CALIBRATION_FILTER)
    ]
    weak = [mutant for mutant in mutants if fnmatchcase(mutant["name"], WEAK_CALIBRATION_FILTER)]
    if not any(mutant["outcome"] == "killed" for mutant in strong):
        raise MutationPolicyError("strong_calibration_not_killed")
    if not any(mutant["outcome"] == "survived" for mutant in weak):
        raise MutationPolicyError("weak_calibration_not_survived")
    return {
        "strong": dict(Counter(mutant["outcome"] for mutant in strong)),
        "weak": dict(Counter(mutant["outcome"] for mutant in weak)),
    }


def _parse_outcomes(backend: Path) -> tuple[dict[str, int], list[dict[str, str]]]:
    counts = Counter({outcome: 0 for outcome in OUTCOMES})
    mutants: list[dict[str, str]] = []
    for meta_path in sorted((backend / "mutants").rglob("*.meta")):
        try:
            value = json.loads(meta_path.read_text(encoding="utf-8"))
            results = value["exit_code_by_key"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
            raise MutationPolicyError("invalid_mutmut_metadata") from exc
        if not isinstance(results, dict):
            raise MutationPolicyError("invalid_mutmut_results")
        for name, exit_code in sorted(results.items()):
            if not isinstance(name, str) or not (isinstance(exit_code, int) or exit_code is None):
                raise MutationPolicyError("invalid_mutmut_result")
            status = STATUS_BY_EXIT_CODE.get(exit_code, "suspicious")
            counts[status] += 1
            mutants.append({"name": name, "outcome": status})
    counts["generated"] = len(mutants)
    if not mutants:
        raise MutationPolicyError("zero_generated_mutants")
    return dict(counts), mutants


def execute_pilot(
    root: Path,
    selection: dict[str, Any],
    manifest: Path,
    manifest_digest: str,
    mutmut_executable: Path,
    output: Path,
    timeout_seconds: int,
    *,
    enforce: bool = False,
) -> None:
    """Run mutation testing in an archived disposable tree and emit evidence."""
    if timeout_seconds < 1 or timeout_seconds > 720:
        raise MutationPolicyError("invalid_timeout")
    manifest_bytes = manifest.read_bytes()
    if DIGEST_RE.fullmatch(manifest_digest) is None or _sha256(manifest_bytes) != manifest_digest:
        raise MutationPolicyError("untrusted_manifest_digest")
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise MutationPolicyError("dirty_source_tree")
    before_tree = _git(root, "rev-parse", "HEAD^{tree}")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="workstream-mutation-") as temporary:
        disposable = Path(temporary) / "repository"
        disposable.mkdir()
        archive = subprocess.run(
            ["git", "archive", selection["head_sha"]],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if archive.returncode != 0:
            raise MutationPolicyError("archive_failed")
        extract = subprocess.run(
            ["tar", "-x", "-C", str(disposable)],
            input=archive.stdout,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if extract.returncode != 0:
            raise MutationPolicyError("archive_extract_failed")
        _reject_disposable_special_files(disposable)
        backend = disposable / "backend"
        generated_config_sha256 = _write_mutmut_config(backend, selection)
        environment = _minimal_runtime_environment()
        baseline = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--noconftest",
                *[node.removeprefix("backend/") for node in selection["tests"]],
            ],
            cwd=backend,
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=min(timeout_seconds, 180),
        )
        if baseline.returncode != 0:
            raise MutationPolicyError("baseline_test_failure")
        try:
            result = subprocess.run(
                [
                    str(mutmut_executable),
                    "run",
                    "--max-children",
                    "2",
                    *_mutant_filters(selection),
                ],
                cwd=backend,
                env=environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise MutationPolicyError("mutation_timeout") from exc
        if result.returncode != 0:
            raise MutationPolicyError("mutation_engine_error")
        counts, mutants = _parse_outcomes(backend)
        verdict = classify_outcomes(counts, mutants, _mutant_filters(selection))
        calibration = _validate_calibration(mutants)
        elapsed = round(time.monotonic() - started, 3)
    if (
        _git(root, "status", "--porcelain", "--untracked-files=no")
        or _git(root, "rev-parse", "HEAD^{tree}") != before_tree
    ):
        raise MutationPolicyError("source_tree_changed")
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "chunk_id": selection["chunk_id"],
        "base_sha": selection["base_sha"],
        "head_sha": selection["head_sha"],
        "head_tree": selection["head_tree"],
        "tool": {"name": "mutmut", "version": "3.7.0"},
        "manifest": {"sha256": manifest_digest},
        "config": {
            "timeout_seconds": timeout_seconds,
            "targets": selection["targets"],
            "tests": selection["tests"],
            "target_owners": selection["target_owners"],
        },
        "selection_sha256": _sha256(_json_bytes(selection)),
        "generated_config_sha256": generated_config_sha256,
        "elapsed_seconds": elapsed,
        "outcomes": counts,
        "calibration": calibration,
        "mutants": mutants,
        "verdict": verdict,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(_json_bytes(evidence))
    if enforce and verdict["status"] != "pass":
        raise MutationPolicyError("blocking_mutation_outcome")


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--base-sha")
    parser.add_argument("--head-sha")
    parser.add_argument("--chunk-id")
    parser.add_argument("--claim-file", type=Path)
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--selection-output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-digest")
    parser.add_argument("--mutmut-executable", type=Path)
    parser.add_argument("--evidence-output", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=720)
    args = parser.parse_args()
    try:
        if args.self_test:
            policy_self_test()
            return 0
        if not args.base_sha or not args.head_sha:
            raise MutationPolicyError("missing_revision")
        root = args.repository_root.resolve(strict=True)
        if args.discover:
            selection = discover_selection(root, args.base_sha, args.head_sha)
        else:
            if args.chunk_id is None:
                raise MutationPolicyError("missing_chunk_id")
            selection = build_selection(
                root,
                args.base_sha,
                args.head_sha,
                args.chunk_id,
                args.claim_file,
            )
        if args.selection_output:
            args.selection_output.write_bytes(_json_bytes(selection))
        if selection.get("applicability") == "not_applicable":
            if args.execute:
                raise MutationPolicyError("inapplicable_execution")
            return 0
        if args.execute:
            if not all(
                (args.manifest, args.manifest_digest, args.mutmut_executable, args.evidence_output)
            ):
                raise MutationPolicyError("missing_execution_argument")
            execute_pilot(
                root,
                selection,
                args.manifest,
                args.manifest_digest,
                args.mutmut_executable,
                args.evidence_output,
                args.timeout_seconds,
                enforce=args.enforce,
            )
    except (MutationPolicyError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"mutation_policy_error:{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
