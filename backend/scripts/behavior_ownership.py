#!/usr/bin/env python3
"""Generate and validate repository behavior-ownership catalogue data."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from scripts.mutation_policy import CALLABLE_RE
from scripts.mutation_policy import OBSERVABLE_OUTCOMES
from scripts.mutation_policy import REAL_BOUNDARIES
from scripts.mutation_policy import TEST_NODE_RE
from scripts.mutation_policy import _callable_spans
from scripts.mutation_policy import _eligible_target
from scripts.mutation_policy import _safe_path
from scripts.mutation_policy import _regular_repository_file
from scripts.mutation_policy import changed_callables


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = "scripts/behavior-ownership.schema.json"
PARTITION_PATH = ".ci/behavior-ownership/partition.v1.json"
PARTITION_SCHEMA = "workstream.behavior-ownership-partition.v1"
CATALOGUE_SCHEMA = "workstream.behavior-ownership.v1"
GROUPS = ("auth", "artifacts", "lifecycle", "shared")


class BehaviorOwnershipError(RuntimeError):
    """Catalogue input is unsafe, stale, incomplete, or ambiguous."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, text=True, capture_output=True, check=False
    )
    if result.returncode:
        raise BehaviorOwnershipError(f"git_command_failed:{arguments[0]}")
    return result.stdout.strip()


def _git_show_optional(root: Path, revision: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def eligible_targets(root: Path = ROOT) -> list[str]:
    """Return every tracked eligible module using mutation policy eligibility."""
    paths = _git(root, "ls-files", "backend/app", "backend/scripts").splitlines()
    return sorted(path for path in paths if _eligible_target(path))


def module_name(target: str) -> str:
    """Convert an eligible repository path to its import-qualified module."""
    _safe_path(target)
    if not _eligible_target(target):
        raise BehaviorOwnershipError("ineligible_target")
    return target.removeprefix("backend/").removesuffix(".py").replace("/", ".")


def callable_names(root: Path, target: str) -> list[str]:
    """Read exact callable names through mutation policy's AST implementation."""
    if not _regular_repository_file(root, target):
        raise BehaviorOwnershipError("unsafe_or_missing_target")
    try:
        source = (root / _safe_path(target)).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise BehaviorOwnershipError("unsafe_or_missing_target") from exc
    return sorted(item[2] for item in _callable_spans(source, module_name(target))[0])


def changed_callable_names(root: Path, base_sha: str, head_sha: str, target: str) -> list[str]:
    """Delegate exact changed-callable derivation to the mutation policy."""
    return changed_callables(root, base_sha, head_sha, target)


def group_for_target(target: str) -> str:
    """Assign one exact population group without wildcard authority."""
    if "/authorization/" in target or target.endswith("/auth.py"):
        return "auth"
    if "/artifacts/" in target or any(
        token in target for token in ("storage", "archive", "checker", "external_service")
    ):
        return "artifacts"
    if any(
        token in target
        for token in ("project", "task", "submission", "review", "contribution", "payment")
    ):
        return "lifecycle"
    return "shared"


def build_partition(root: Path = ROOT, *, base_commit: str | None = None) -> dict[str, Any]:
    """Build the canonical deterministic path partition."""
    resolved_base = base_commit or _git(root, "rev-parse", "HEAD")
    assignments = [
        {"group": group_for_target(target), "target": target}
        for target in eligible_targets(root)
    ]
    authority = {
        "schema": PARTITION_SCHEMA,
        "protected_base_commit": resolved_base,
        "assignments": assignments,
    }
    return {**authority, "authority_digest": _digest(authority)}


def _read_json(path: Path, error: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BehaviorOwnershipError(error) from exc


def validate_partition(
    root: Path = ROOT,
    *,
    partition_path: Path | None = None,
    trusted_revision: str | None = "origin/main",
) -> dict[str, str]:
    """Validate exact partition completeness, digest, location, and custody."""
    expected_path = root / PARTITION_PATH
    path = partition_path or expected_path
    if not _regular_repository_file(root, PARTITION_PATH):
        raise BehaviorOwnershipError("unsafe_or_missing_partition")
    try:
        if path.resolve() != expected_path.resolve():
            raise BehaviorOwnershipError("relocated_partition")
    except OSError as exc:
        raise BehaviorOwnershipError("missing_partition") from exc
    value = _read_json(path, "invalid_partition_json")
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "protected_base_commit",
        "assignments",
        "authority_digest",
    }:
        raise BehaviorOwnershipError("invalid_partition_shape")
    if value["schema"] != PARTITION_SCHEMA:
        raise BehaviorOwnershipError("unsupported_partition_schema")
    authority = {key: value[key] for key in value if key != "authority_digest"}
    if value["authority_digest"] != _digest(authority):
        raise BehaviorOwnershipError("partition_digest_mismatch")
    protected_base = value["protected_base_commit"]
    if not isinstance(protected_base, str) or len(protected_base) != 40 or any(
        character not in "0123456789abcdef" for character in protected_base
    ):
        raise BehaviorOwnershipError("invalid_partition_base_commit")
    if _git(root, "rev-parse", "--verify", f"{protected_base}^{{commit}}") != protected_base:
        raise BehaviorOwnershipError("missing_partition_base_commit")
    assignments = value["assignments"]
    if not isinstance(assignments, list):
        raise BehaviorOwnershipError("invalid_partition_assignments")
    targets: list[str] = []
    for item in assignments:
        if (
            not isinstance(item, dict)
            or set(item) != {"group", "target"}
            or item["group"] not in GROUPS
            or not isinstance(item["target"], str)
            or not _eligible_target(item["target"])
        ):
            raise BehaviorOwnershipError("invalid_partition_assignment")
        targets.append(item["target"])
    if len(targets) != len(set(targets)):
        raise BehaviorOwnershipError("duplicate_partition_target")
    expected = eligible_targets(root)
    if sorted(targets) != expected:
        raise BehaviorOwnershipError("partition_target_mismatch")
    expected_assignments = [
        {"group": group_for_target(target), "target": target} for target in expected
    ]
    if assignments != expected_assignments:
        raise BehaviorOwnershipError("partition_assignment_mismatch")
    if trusted_revision is not None:
        trusted = _git_show_optional(root, trusted_revision, PARTITION_PATH)
        if trusted is not None:
            try:
                trusted_value = json.loads(trusted)
            except json.JSONDecodeError as exc:
                raise BehaviorOwnershipError("invalid_trusted_partition") from exc
            if trusted_value != value:
                raise BehaviorOwnershipError("untrusted_partition_change")
        else:
            try:
                _git(root, "merge-base", "--is-ancestor", protected_base, "HEAD")
            except BehaviorOwnershipError as exc:
                raise BehaviorOwnershipError("invalid_partition_ancestry") from exc
    return {item["target"]: item["group"] for item in assignments}


def load_schema(root: Path = ROOT) -> dict[str, Any]:
    """Load and verify the catalogue JSON Schema."""
    if not _regular_repository_file(root, SCHEMA_PATH):
        raise BehaviorOwnershipError("unsafe_or_missing_catalogue_schema")
    value = _read_json(root / SCHEMA_PATH, "invalid_catalogue_schema_json")
    try:
        Draft202012Validator.check_schema(value)
    except Exception as exc:  # jsonschema exposes version-specific subclasses
        raise BehaviorOwnershipError("invalid_catalogue_schema") from exc
    return value


def _catalogue_files(root: Path) -> list[Path]:
    base = root / ".ci/behavior-ownership"
    return sorted(
        path
        for path in base.glob("*/*.json")
        if path.is_file() and "examples" not in path.parts
    )


def _is_strictly_structural(root: Path, target: str) -> bool:
    if not _regular_repository_file(root, target):
        raise BehaviorOwnershipError("unsafe_or_missing_target")
    try:
        tree = ast.parse((root / target).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise BehaviorOwnershipError("invalid_target_syntax") from exc
    forbidden = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.Call,
        ast.Await,
        ast.Yield,
        ast.YieldFrom,
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.Raise,
        ast.Match,
        ast.NamedExpr,
        ast.AugAssign,
        ast.Delete,
    )
    return not any(isinstance(node, forbidden) for node in ast.walk(tree))


def _validate_record_semantics(root: Path, record: dict[str, Any]) -> None:
    target = record["target"]
    actual_callables = set(callable_names(root, target))
    status = record["status"]
    if status != "reviewed" and "supersedes_behavior_id" in record:
        raise BehaviorOwnershipError("invalid_non_reviewed_supersession")
    if status == "structural_only":
        if actual_callables or not _is_strictly_structural(root, target):
            raise BehaviorOwnershipError("executable_structural_only")
        return
    for callable_name in record["callables"]:
        if CALLABLE_RE.fullmatch(callable_name) is None or callable_name not in actual_callables:
            raise BehaviorOwnershipError("missing_catalogue_callable")
    if len(record["callables"]) != len(set(record["callables"])):
        raise BehaviorOwnershipError("duplicate_catalogue_callable")
    if status == "reviewed":
        if not set(record["outcomes"]).issubset(OBSERVABLE_OUTCOMES):
            raise BehaviorOwnershipError("invalid_catalogue_outcome")
        if not set(record["boundaries"]).issubset(REAL_BOUNDARIES):
            raise BehaviorOwnershipError("invalid_catalogue_boundary")
        if any(TEST_NODE_RE.fullmatch(node) is None for node in record["tests"]):
            raise BehaviorOwnershipError("invalid_catalogue_test")
        for node in record["tests"]:
            test_path = node.split("::", 1)[0]
            if not _regular_repository_file(root, test_path):
                raise BehaviorOwnershipError("missing_catalogue_test")


def _catalogue_at_revision(root: Path, revision: str) -> list[dict[str, Any]]:
    output = _git(root, "ls-tree", "-r", "--name-only", revision, "--", ".ci/behavior-ownership")
    records: list[dict[str, Any]] = []
    for path in output.splitlines():
        if not path.endswith(".json") or "/examples/" in path or path == PARTITION_PATH:
            continue
        source = _git_show_optional(root, revision, path)
        if source is None:
            raise BehaviorOwnershipError("missing_protected_record")
        try:
            value = json.loads(source)
        except json.JSONDecodeError as exc:
            raise BehaviorOwnershipError("invalid_protected_record") from exc
        if isinstance(value, dict):
            records.append(value)
    return records


def _validate_remaps(
    root: Path, records: list[dict[str, Any]], *, base_sha: str, head_sha: str
) -> None:
    protected = _catalogue_at_revision(root, base_sha)
    protected_by_id: dict[str, list[dict[str, Any]]] = {}
    for item in protected:
        protected_by_id.setdefault(item.get("behavior_id", ""), []).append(item)
    current_by_id = {item["behavior_id"]: item for item in records}
    for behavior_id, owners in protected_by_id.items():
        if len(owners) != 1:
            raise BehaviorOwnershipError("multiple_protected_owners")
        current = current_by_id.get(behavior_id)
        if current is not None and current != owners[0]:
            raise BehaviorOwnershipError("protected_owner_replacement")
    for record in records:
        superseded_id = record.get("supersedes_behavior_id")
        if superseded_id is None:
            continue
        owners = protected_by_id.get(superseded_id, [])
        if len(owners) != 1 or owners[0].get("status") != "reviewed":
            raise BehaviorOwnershipError("invalid_remap_ancestry")
        old = owners[0]
        if _git_show_optional(root, head_sha, old["target"]) is not None:
            raise BehaviorOwnershipError("protected_location_still_exists")
        if _git_show_optional(root, head_sha, record["target"]) is None:
            raise BehaviorOwnershipError("missing_remap_location")
        for field in ("tests", "outcomes", "boundaries"):
            if not set(old[field]).issubset(record[field]):
                raise BehaviorOwnershipError("narrowed_remap_evidence")
    for behavior_id, owners in protected_by_id.items():
        current = current_by_id.get(behavior_id)
        replacements = [
            item for item in records if item.get("supersedes_behavior_id") == behavior_id
        ]
        effective_count = int(current == owners[0]) + len(replacements)
        if effective_count == 0:
            raise BehaviorOwnershipError("missing_effective_owner")
        if effective_count > 1:
            raise BehaviorOwnershipError("multiple_effective_owners")


def validate_catalogue(
    root: Path = ROOT,
    *,
    group: str | None = None,
    trusted_revision: str = "origin/main",
    head_revision: str = "HEAD",
    run_tests: bool = False,
) -> dict[str, Any]:
    """Validate catalogue shape, exact bindings, identities, and completeness."""
    partition = validate_partition(root, trusted_revision=trusted_revision)
    if group is not None and group not in GROUPS:
        raise BehaviorOwnershipError("invalid_group")
    validator = Draft202012Validator(load_schema(root))
    all_records: list[dict[str, Any]] = []
    for path in _catalogue_files(root):
        relative = path.relative_to(root).as_posix()
        if not _regular_repository_file(root, relative):
            raise BehaviorOwnershipError("unsafe_catalogue_record")
        value = _read_json(path, "invalid_catalogue_json")
        errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
        if errors:
            raise BehaviorOwnershipError(f"invalid_catalogue_record:{errors[0].json_path}")
        if partition.get(value["target"]) != value["group"]:
            raise BehaviorOwnershipError("wrong_catalogue_group")
        if path.parent.name != value["group"]:
            raise BehaviorOwnershipError("misplaced_catalogue_record")
        _validate_record_semantics(root, value)
        all_records.append(value)
    identities = [item["behavior_id"] for item in all_records]
    if len(identities) != len(set(identities)):
        raise BehaviorOwnershipError("duplicate_behavior_id")
    superseded = [
        item["supersedes_behavior_id"]
        for item in all_records
        if "supersedes_behavior_id" in item
    ]
    if len(superseded) != len(set(superseded)):
        raise BehaviorOwnershipError("duplicate_supersession")
    callable_owners = [
        (item["target"], callable_name)
        for item in all_records
        if item["status"] == "reviewed"
        for callable_name in item["callables"]
    ]
    if len(callable_owners) != len(set(callable_owners)):
        raise BehaviorOwnershipError("multiple_effective_callable_owners")
    partition_value = _read_json(root / PARTITION_PATH, "invalid_partition_json")
    _validate_remaps(
        root,
        all_records,
        base_sha=partition_value["protected_base_commit"],
        head_sha=head_revision,
    )
    records = [item for item in all_records if group in (None, item["group"])]
    reviewed_records = [item for item in records if item["status"] == "reviewed"]
    if reviewed_records:
        collection_code = _run_test_nodes(root, reviewed_records, collect_only=True)
        if collection_code:
            raise BehaviorOwnershipError("stale_catalogue_test")
        if run_tests and _run_test_nodes(root, reviewed_records, collect_only=False):
            raise BehaviorOwnershipError("owned_test_failure")
    covered = {item["target"] for item in records}
    expected = {target for target, assigned in partition.items() if group in (None, assigned)}
    return {
        "schema": CATALOGUE_SCHEMA,
        "group": group,
        "reviewed": sum(item["status"] == "reviewed" for item in records),
        "candidates": sum(item["status"] == "candidate" for item in records),
        "structural_only": sum(item["status"] == "structural_only" for item in records),
        "unresolved": sorted(expected - covered),
        "complete": expected == covered and all(item["status"] != "candidate" for item in records),
    }


def generate_candidates(root: Path = ROOT, *, group: str | None = None) -> dict[str, Any]:
    """Generate deterministic non-authoritative candidates and unresolved paths."""
    partition = validate_partition(root)
    if group is not None and group not in GROUPS:
        raise BehaviorOwnershipError("invalid_group")
    candidates = []
    unresolved = []
    for target, assigned in sorted(partition.items()):
        if group not in (None, assigned):
            continue
        names = callable_names(root, target)
        if not names:
            unresolved.append(
                {"group": assigned, "target": target, "reason": "structural review required"}
            )
            continue
        candidates.append(
            {
                "schema": CATALOGUE_SCHEMA,
                "behavior_id": "candidate:" + target.removeprefix("backend/").removesuffix(".py").replace("/", "."),
                "status": "candidate",
                "group": assigned,
                "target": target,
                "callables": names,
                "unresolved_reason": "reviewed tests, outcomes, and boundaries required",
            }
        )
    return {
        "schema": CATALOGUE_SCHEMA,
        "authoritative": False,
        "candidates": candidates,
        "unresolved": unresolved,
    }


def _run_test_nodes(
    root: Path, records: Iterable[dict[str, Any]], *, collect_only: bool
) -> int:
    nodes = sorted(
        {node for item in records if item.get("status") == "reviewed" for node in item["tests"]}
    )
    if not nodes:
        return 0
    arguments = [sys.executable, "-m", "pytest", "-q"]
    if collect_only:
        arguments.append("--collect-only")
    result = subprocess.run(
        [*arguments, *[node.removeprefix("backend/") for node in nodes]],
        cwd=root / "backend",
        check=False,
    )
    return result.returncode


def run_owned_tests(root: Path, records: Iterable[dict[str, Any]]) -> int:
    """Run exact reviewed test nodes; candidates and structural records are excluded."""
    return _run_test_nodes(root, records, collect_only=False)


def _main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inventory")
    candidate_parser = subparsers.add_parser("generate")
    candidate_parser.add_argument("--group", choices=GROUPS)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--group", choices=GROUPS)
    validate_parser.add_argument("--trusted-revision")
    validate_parser.add_argument("--head-revision", default="HEAD")
    validate_parser.add_argument("--run-owned-tests", action="store_true")
    partition_parser = subparsers.add_parser("partition")
    partition_parser.add_argument("--base-commit")
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            result: Any = eligible_targets()
        elif args.command == "generate":
            result = generate_candidates(group=args.group)
        elif args.command == "partition":
            result = build_partition(base_commit=args.base_commit)
        else:
            result = validate_catalogue(
                group=args.group,
                trusted_revision=args.trusted_revision or "origin/main",
                head_revision=args.head_revision,
                run_tests=args.run_owned_tests,
            )
    except BehaviorOwnershipError as exc:
        print(f"behavior_ownership_error:{exc}", file=sys.stderr)
        return 2
    print(_json_bytes(result).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
