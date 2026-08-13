#!/usr/bin/env python3
"""Generate and validate repository behavior-ownership catalogue data."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable

from coverage import CoverageData
from jsonschema import Draft202012Validator

from scripts import run_test_lanes as test_lanes
from scripts.mutation_policy import CALLABLE_RE
from scripts.mutation_policy import MutationPolicyError
from scripts.mutation_policy import OBSERVABLE_OUTCOMES
from scripts.mutation_policy import REAL_BOUNDARIES
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
CONTEXT_EVIDENCE_SCHEMA = "workstream.behavior-ownership-context-evidence.v1"
GROUPS = ("auth", "artifacts", "lifecycle", "shared")
CONTEXT_RUNTIME_LIMIT_SECONDS = 120.0
CONTEXT_ARTIFACT_LIMIT_BYTES = 10 * 1024 * 1024
CONTEXT_EVIDENCE_KEYS = {
    "schema",
    "authoritative",
    "head_sha",
    "lane",
    "target",
    "test_module",
    "collection_complete",
    "execution_complete",
    "collected_nodes",
    "completed_nodes",
    "skipped_nodes",
    "deselected_nodes",
    "callables",
    "elapsed_seconds",
    "artifact_digest",
}
OWNERSHIP_TEST_NODE_RE = re.compile(
    r"^backend/tests/(?:[A-Za-z0-9_]+/)*test_[A-Za-z0-9_]+\.py::[^\s]+$"
)
AUTH_BOUNDARY_FOUNDATION_TARGETS = frozenset(
    {
        "backend/app/modules/authorization/api/action_ids.py",
        "backend/app/modules/authorization/api/decisions.py",
        "backend/app/modules/authorization/api/errors.py",
        "backend/app/modules/authorization/api/facts.py",
        "backend/app/modules/authorization/api/ports.py",
        "backend/scripts/authorization_boundary.py",
        "backend/scripts/test_structure_boundary.py",
    }
)
MODULE_BOUNDARY_FOUNDATION_TARGETS = frozenset(
    {"backend/scripts/module_boundaries.py"}
)
MODULE_PUBLIC_API_FOUNDATION_TARGETS = frozenset(
    {
        "backend/app/api/routes/artifact_submissions.py",
        "backend/app/modules/artifacts/api/submission_admission.py",
        "backend/app/modules/artifacts/api/submission_preparation.py",
        "backend/app/modules/artifacts/submission_bindings.py",
        "backend/app/modules/checkers/api/pre_submit.py",
        "backend/app/modules/projects/api/locked_policy.py",
        "backend/app/modules/projects/locked_policy_repository.py",
        "backend/app/modules/tasks/api/submission_context.py",
    }
)
ARCH_02F_SUBMISSION_COMPOSITION_TARGETS = frozenset(
    {
        "backend/app/modules/tasks/api/submission_command.py",
        "backend/app/modules/tasks/submission_composition.py",
    }
)
ARCH_02G_AUTH_PREPARATION_TARGETS = frozenset(
    {
        "backend/app/modules/authorization/artifact_project_authority.py",
        "backend/app/modules/authorization/pre_submit_materialization.py",
        "backend/app/modules/authorization/submission_preparation.py",
    }
)
ARCH_02H_AUTH_CONSUMPTION_TARGETS = frozenset(
    {
        "backend/app/modules/authorization/submission_consumption.py",
        "backend/app/modules/authorization/submission_creation_authorization.py",
    }
)
POL_03A_CALLABLE_TARGETS = frozenset(
    {
        "backend/app/modules/authorization/api/project_guide_compilation.py",
        "backend/app/modules/projects/guide_compilation/authorization.py",
        "backend/app/modules/projects/guide_compilation/contracts.py",
        "backend/app/modules/projects/guide_compilation/repository.py",
        "backend/app/modules/projects/guide_compilation/validation.py",
    }
)
POL_03A_DECLARATIVE_MODEL_TARGET = (
    "backend/app/modules/projects/guide_compilation/models.py"
)
AUTH_12I_TARGETS = frozenset(
    {
        "backend/app/modules/authorization/domain/audit.py",
        "backend/app/modules/authorization/domain/guide_compilation.py",
        "backend/app/modules/authorization/domain/prepared_compilation.py",
        "backend/app/modules/authorization/domain/prepared_service.py",
        "backend/app/modules/authorization/domain/project_create.py",
        "backend/app/modules/authorization/guide_compilation.py",
    }
)
V01_BASELINE_REMOVED_TARGETS = frozenset(
    {
        "backend/app/modules/actors/service_identity_migration.py",
        "backend/scripts/service_actor_identity_mapping.py",
    }
)
V01_BASELINE_ADDED_TARGETS = frozenset(
    {
        "backend/scripts/schema_baseline_manifest.py",
        "backend/scripts/schema_baseline_sql.py",
    }
)


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


def _validate_additive_partition_transition(
    current: dict[str, Any],
    trusted: Any,
) -> None:
    """Allow only the exact approved module public-API foundation additions."""
    keys = {"schema", "protected_base_commit", "assignments", "authority_digest"}
    if not isinstance(trusted, dict) or set(trusted) != keys:
        raise BehaviorOwnershipError("invalid_trusted_partition")
    trusted_authority = {key: trusted[key] for key in trusted if key != "authority_digest"}
    if trusted.get("authority_digest") != _digest(trusted_authority):
        raise BehaviorOwnershipError("invalid_trusted_partition")
    if (
        trusted.get("schema") != current["schema"]
        or trusted.get("protected_base_commit") != current["protected_base_commit"]
        or not isinstance(trusted.get("assignments"), list)
    ):
        raise BehaviorOwnershipError("untrusted_partition_change")
    trusted_assignments = trusted["assignments"]
    trusted_targets: list[str] = []
    for item in trusted_assignments:
        if (
            not isinstance(item, dict)
            or set(item) != {"group", "target"}
            or item.get("group") not in GROUPS
            or not isinstance(item.get("target"), str)
        ):
            raise BehaviorOwnershipError("invalid_trusted_partition")
        trusted_targets.append(item["target"])
    if len(trusted_targets) != len(set(trusted_targets)):
        raise BehaviorOwnershipError("invalid_trusted_partition")
    current_assignments = current["assignments"]
    current_by_target = {item["target"]: item for item in current_assignments}
    removed = set(trusted_targets) - set(current_by_target)
    retained_trusted = [
        item for item in trusted_assignments if item["target"] not in removed
    ]
    if (
        trusted_targets != sorted(trusted_targets)
        or removed - V01_BASELINE_REMOVED_TARGETS
        or [current_by_target[item["target"]] for item in retained_trusted]
        != retained_trusted
    ):
        raise BehaviorOwnershipError("untrusted_partition_change")
    additions = set(current_by_target) - set(trusted_targets)
    approved_additions = (
        AUTH_BOUNDARY_FOUNDATION_TARGETS
        | MODULE_BOUNDARY_FOUNDATION_TARGETS
        | MODULE_PUBLIC_API_FOUNDATION_TARGETS
        | POL_03A_CALLABLE_TARGETS
        | AUTH_12I_TARGETS
        | ARCH_02F_SUBMISSION_COMPOSITION_TARGETS
        | ARCH_02G_AUTH_PREPARATION_TARGETS
        | ARCH_02H_AUTH_CONSUMPTION_TARGETS
        | V01_BASELINE_ADDED_TARGETS
    )
    expected_additions = (approved_additions & additions) - set(trusted_targets)
    if POL_03A_DECLARATIVE_MODEL_TARGET in additions:
        expected_additions = expected_additions | {POL_03A_DECLARATIVE_MODEL_TARGET}
    if additions != expected_additions:
        raise BehaviorOwnershipError("untrusted_partition_change")
    if any(
        current_by_target[target]["group"] != group_for_target(target)
        for target in additions
    ):
        raise BehaviorOwnershipError("untrusted_partition_change")


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
                _validate_additive_partition_transition(value, trusted_value)
        else:
            raise BehaviorOwnershipError("trusted_partition_unavailable")
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
        if any(OWNERSHIP_TEST_NODE_RE.fullmatch(node) is None for node in record["tests"]):
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
    unresolved = expected - covered
    if unresolved.intersection(AUTH_BOUNDARY_FOUNDATION_TARGETS | POL_03A_CALLABLE_TARGETS):
        raise BehaviorOwnershipError("unresolved_auth_boundary_foundation")
    return {
        "schema": CATALOGUE_SCHEMA,
        "group": group,
        "reviewed": sum(item["status"] == "reviewed" for item in records),
        "candidates": sum(item["status"] == "candidate" for item in records),
        "structural_only": sum(item["status"] == "structural_only" for item in records),
        "unresolved": sorted(unresolved),
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


def _write_exclusive(path: Path, data: bytes) -> None:
    """Write one private regular artifact without overwrite or symlink following."""
    if len(data) > CONTEXT_ARTIFACT_LIMIT_BYTES:
        raise BehaviorOwnershipError("context_evidence_too_large")
    if not path.parent.is_dir():
        raise BehaviorOwnershipError("invalid_context_output_parent")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise BehaviorOwnershipError("context_output_exists_or_unsafe") from exc
    try:
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(data)
    except OSError:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _tracked_at_revision(root: Path, revision: str, path: str) -> bool:
    """Return whether one safe repository path is tracked at the revision."""
    try:
        _safe_path(path)
    except MutationPolicyError:
        return False
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}:{path}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _context_node_is_valid(node: object, test_module: str) -> bool:
    """Validate one backend-relative pytest node against the selected module."""
    if not isinstance(node, str) or any(character in node for character in "\x00\r\n"):
        return False
    try:
        return test_lanes._module_from_node(node) == test_module
    except test_lanes.LaneError:
        return False


def _context_target_is_valid(root: Path, target: object) -> bool:
    """Validate an eligible regular target without leaking policy exceptions."""
    if not isinstance(target, str):
        return False
    try:
        return _eligible_target(target) and _regular_repository_file(root, target)
    except MutationPolicyError:
        return False


def _coverage_lines_by_context(
    coverage_path: Path, target_path: Path, completed_nodes: set[str]
) -> dict[str, set[int]]:
    """Read exact pytest contexts without exposing unrelated coverage metadata."""
    data = CoverageData(basename=str(coverage_path))
    try:
        data.read()
    except Exception as exc:
        raise BehaviorOwnershipError("invalid_context_coverage") from exc
    result: dict[str, set[int]] = {}
    for context in sorted(data.measured_contexts()):
        # Fixture setup/teardown contexts are deliberately excluded: they do
        # not prove that the test body executed the callable behavior.
        node = context.removesuffix("|run")
        if node not in completed_nodes:
            continue
        data.set_query_contexts([f"^{re.escape(context)}$"])
        lines = data.lines(str(target_path.resolve())) or []
        result.setdefault(node, set()).update(lines)
    data.set_query_contexts(None)
    if set(result) != completed_nodes:
        raise BehaviorOwnershipError("missing_test_context")
    return result


def _sanitize_context_environment(
    environment: dict[str, str], backend_root: Path
) -> dict[str, str]:
    """Retain only non-secret runtime and lane-custody environment values."""
    allowed = {
        "PATH",
        "VIRTUAL_ENV",
        "LANG",
        "LC_ALL",
        "TZ",
        "TMPDIR",
        test_lanes.COLLECTED_ENV,
        test_lanes.COMPLETED_ENV,
        test_lanes.SKIPPED_ENV,
        test_lanes.DESELECTED_ENV,
        test_lanes.HEAD_ENV,
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "COVERAGE_FILE",
    }
    sanitized = {key: value for key, value in environment.items() if key in allowed}
    sanitized["PYTHONPATH"] = str(backend_root)
    return sanitized


def build_context_evidence(
    root: Path,
    *,
    target: str,
    test_module: str,
    output: Path,
    runtime_limit_seconds: float = CONTEXT_RUNTIME_LIMIT_SECONDS,
) -> dict[str, Any]:
    """Run one local context probe and emit non-authoritative evidence."""
    started = time.monotonic()
    if runtime_limit_seconds <= 0 or runtime_limit_seconds > CONTEXT_RUNTIME_LIMIT_SECONDS:
        raise BehaviorOwnershipError("invalid_context_runtime_limit")
    if not _regular_repository_file(root, target) or not _eligible_target(target):
        raise BehaviorOwnershipError("unsafe_or_missing_target")
    backend_root = root / "backend"
    if not test_lanes._safe_module_path(test_module):
        raise BehaviorOwnershipError("invalid_context_test_module")
    if test_module not in test_lanes.discover_test_modules(backend_root / "tests", backend_root):
        raise BehaviorOwnershipError("missing_context_test_module")
    head_sha = _git(root, "rev-parse", "HEAD")
    if not _tracked_at_revision(root, head_sha, target) or not _tracked_at_revision(
        root, head_sha, f"backend/{test_module}"
    ):
        raise BehaviorOwnershipError("untracked_context_input")
    if _git(root, "status", "--porcelain", "--untracked-files=all"):
        raise BehaviorOwnershipError("dirty_context_tree")
    if output.is_symlink() or any(
        parent.is_symlink() for parent in output.parents if parent.exists()
    ):
        raise BehaviorOwnershipError("context_output_exists_or_unsafe")
    try:
        output = output.resolve(strict=False)
    except OSError as exc:
        raise BehaviorOwnershipError("invalid_context_output") from exc
    if output.exists() or output.is_symlink():
        raise BehaviorOwnershipError("context_output_exists_or_unsafe")

    with tempfile.TemporaryDirectory(prefix="workstream-context-evidence-") as directory:
        metadata = Path(directory)
        remaining = runtime_limit_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise BehaviorOwnershipError("context_runtime_exceeded")
        try:
            collection_code, nodes, collection_deselected = test_lanes.collect_nodes(
                (test_module,),
                metadata,
                head_sha,
                base_environment=_sanitize_context_environment(os.environ, backend_root),
                timeout_seconds=remaining,
            )
        except subprocess.TimeoutExpired as exc:
            raise BehaviorOwnershipError("context_runtime_exceeded") from exc
        if collection_code != 0 or collection_deselected or not nodes:
            raise BehaviorOwnershipError("invalid_context_collection")
        coverage_path = metadata / ".coverage.context"
        lane = test_lanes.TestLane("context_evidence", (test_module,), requires_postgres=False)
        for suffix in ("collected", "completed", "skipped", "deselected"):
            test_lanes._exclusive_file(metadata / f"context.{suffix}.jsonl")
        environment = test_lanes.lane_environment(
            lane, metadata, coverage_path, "context", head_sha
        )
        environment = _sanitize_context_environment(environment, backend_root)
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *test_lanes._plugin_args(),
            f"--cov={module_name(target)}",
            "--cov-report=",
            "--cov-context=test",
            *nodes,
        ]
        remaining = runtime_limit_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise BehaviorOwnershipError("context_runtime_exceeded")
        try:
            run = subprocess.run(
                command,
                cwd=backend_root,
                env=environment,
                check=False,
                timeout=remaining,
            )
        except subprocess.TimeoutExpired as exc:
            raise BehaviorOwnershipError("context_runtime_exceeded") from exc
        if run.returncode:
            raise BehaviorOwnershipError("context_test_failure")
        collected = test_lanes._read_nodes(metadata / "context.collected.jsonl")
        completed = test_lanes._read_nodes(metadata / "context.completed.jsonl")
        skipped = test_lanes._read_nodes(
            metadata / "context.skipped.jsonl", allow_empty=True
        )
        deselected = test_lanes._read_nodes(
            metadata / "context.deselected.jsonl", allow_empty=True
        )
        if collected != nodes or completed != nodes:
            raise BehaviorOwnershipError("incomplete_context_execution")
        if skipped or deselected:
            raise BehaviorOwnershipError("weakened_context_execution")
        if not coverage_path.is_file() or coverage_path.is_symlink():
            raise BehaviorOwnershipError("missing_context_coverage")
        lines_by_node = _coverage_lines_by_context(
            coverage_path, root / target, set(completed)
        )

    elapsed = time.monotonic() - started
    if elapsed > runtime_limit_seconds:
        raise BehaviorOwnershipError("context_runtime_exceeded")
    source = (root / target).read_text(encoding="utf-8")
    spans = _callable_spans(source, module_name(target))[0]
    callables = []
    for start_line, end_line, name in sorted(spans, key=lambda item: item[2]):
        node_lines = {
            node: sorted(line for line in lines if start_line <= line <= end_line)
            for node, lines in lines_by_node.items()
        }
        callables.append(
            {
                "callable": name,
                "start_line": start_line,
                "end_line": end_line,
                "contexts": [
                    {"nodeid": node, "lines": lines}
                    for node, lines in sorted(node_lines.items())
                    if lines
                ],
            }
        )
    authority = {
        "schema": CONTEXT_EVIDENCE_SCHEMA,
        "authoritative": False,
        "head_sha": head_sha,
        "lane": "context_evidence",
        "target": target,
        "test_module": test_module,
        "collection_complete": True,
        "execution_complete": True,
        "collected_nodes": nodes,
        "completed_nodes": completed,
        "skipped_nodes": skipped,
        "deselected_nodes": deselected,
        "callables": callables,
        "elapsed_seconds": round(elapsed, 3),
    }
    artifact = {**authority, "artifact_digest": _digest(authority)}
    _write_exclusive(output, _json_bytes(artifact))
    return artifact


def validate_context_evidence(
    root: Path, path: Path, *, head_revision: str = "HEAD"
) -> dict[str, Any]:
    """Validate one local context artifact as non-authoritative candidate input."""
    try:
        if not path.is_file() or path.is_symlink():
            raise BehaviorOwnershipError("unsafe_context_evidence")
        if path.stat().st_size > CONTEXT_ARTIFACT_LIMIT_BYTES:
            raise BehaviorOwnershipError("context_evidence_too_large")
    except OSError as exc:
        raise BehaviorOwnershipError("unsafe_context_evidence") from exc
    value = _read_json(path, "invalid_context_evidence_json")
    if not isinstance(value, dict) or set(value) != CONTEXT_EVIDENCE_KEYS:
        raise BehaviorOwnershipError("invalid_context_evidence_shape")
    if value["schema"] != CONTEXT_EVIDENCE_SCHEMA or value["authoritative"] is not False:
        raise BehaviorOwnershipError("invalid_context_evidence_schema")
    authority = {key: value[key] for key in value if key != "artifact_digest"}
    if value["artifact_digest"] != _digest(authority):
        raise BehaviorOwnershipError("context_evidence_digest_mismatch")
    if value["head_sha"] != _git(root, "rev-parse", head_revision):
        raise BehaviorOwnershipError("stale_context_evidence")
    head_sha = value["head_sha"]
    target = value["target"]
    test_module = value["test_module"]
    if (
        not isinstance(head_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None
        or not _context_target_is_valid(root, target)
        or not _tracked_at_revision(root, head_revision, target)
        or not isinstance(test_module, str)
        or not test_lanes._safe_module_path(test_module)
        or test_module
        not in test_lanes.discover_test_modules(root / "backend/tests", root / "backend")
        or not _tracked_at_revision(root, head_revision, f"backend/{test_module}")
    ):
        raise BehaviorOwnershipError("invalid_context_identity")
    collected = value["collected_nodes"]
    completed = value["completed_nodes"]
    if (
        value["lane"] != "context_evidence"
        or value["collection_complete"] is not True
        or value["execution_complete"] is not True
        or not isinstance(collected, list)
        or not collected
        or any(not _context_node_is_valid(node, test_module) for node in collected)
        or not isinstance(completed, list)
        or any(not _context_node_is_valid(node, test_module) for node in completed)
        or collected != completed
        or len(collected) != len(set(collected))
    ):
        raise BehaviorOwnershipError("incomplete_context_evidence")
    skipped = value["skipped_nodes"]
    deselected = value["deselected_nodes"]
    if (
        not isinstance(skipped, list)
        or not isinstance(deselected, list)
        or any(not _context_node_is_valid(node, test_module) for node in skipped)
        or any(not _context_node_is_valid(node, test_module) for node in deselected)
        or skipped
        or deselected
    ):
        raise BehaviorOwnershipError("weakened_context_evidence")
    if (
        not isinstance(value["elapsed_seconds"], (int, float))
        or isinstance(value["elapsed_seconds"], bool)
        or value["elapsed_seconds"] < 0
        or value["elapsed_seconds"] > CONTEXT_RUNTIME_LIMIT_SECONDS
    ):
        raise BehaviorOwnershipError("invalid_context_elapsed")
    if not isinstance(value["callables"], list):
        raise BehaviorOwnershipError("invalid_context_callables")
    source = _git_show_optional(root, head_revision, target)
    if source is None:
        raise BehaviorOwnershipError("invalid_context_identity")
    actual_spans = {
        name: (start_line, end_line)
        for start_line, end_line, name in _callable_spans(
            source, module_name(target)
        )[0]
    }
    actual_callables = set(actual_spans)
    seen_callables: set[str] = set()
    for item in value["callables"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"callable", "start_line", "end_line", "contexts"}
            or not isinstance(item["callable"], str)
            or CALLABLE_RE.fullmatch(item["callable"]) is None
            or item["callable"] not in actual_callables
            or item["callable"] in seen_callables
            or not isinstance(item["start_line"], int)
            or isinstance(item["start_line"], bool)
            or not isinstance(item["end_line"], int)
            or isinstance(item["end_line"], bool)
            or item["start_line"] > item["end_line"]
            or (item["start_line"], item["end_line"])
            != actual_spans[item["callable"]]
            or not isinstance(item["contexts"], list)
        ):
            raise BehaviorOwnershipError("invalid_context_callables")
        seen_callables.add(item["callable"])
        for context in item["contexts"]:
            if (
                not isinstance(context, dict)
                or set(context) != {"nodeid", "lines"}
                or context["nodeid"] not in completed
                or not isinstance(context["lines"], list)
                or not context["lines"]
                or any(
                    not isinstance(line, int)
                    or isinstance(line, bool)
                    or line < item["start_line"]
                    or line > item["end_line"]
                    for line in context["lines"]
                )
            ):
                raise BehaviorOwnershipError("invalid_context_callables")
    if seen_callables != actual_callables:
        raise BehaviorOwnershipError("incomplete_context_evidence")
    return {
        "schema": CONTEXT_EVIDENCE_SCHEMA,
        "authoritative": False,
        "head_sha": value["head_sha"],
        "target": value["target"],
        "test_module": value["test_module"],
        "callable_count": len(value["callables"]),
        "node_count": len(collected),
        "artifact_digest": value["artifact_digest"],
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
    context_parser = subparsers.add_parser("context-evidence")
    context_parser.add_argument("--target", required=True)
    context_parser.add_argument("--test-module", required=True)
    context_parser.add_argument("--output", required=True, type=Path)
    context_validate_parser = subparsers.add_parser("validate-context-evidence")
    context_validate_parser.add_argument("--input", required=True, type=Path)
    context_validate_parser.add_argument("--head-revision", default="HEAD")
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            result: Any = eligible_targets()
        elif args.command == "generate":
            result = generate_candidates(group=args.group)
        elif args.command == "partition":
            result = build_partition(base_commit=args.base_commit)
        elif args.command == "context-evidence":
            result = build_context_evidence(
                ROOT,
                target=args.target,
                test_module=args.test_module,
                output=args.output,
            )
        elif args.command == "validate-context-evidence":
            result = validate_context_evidence(
                ROOT, args.input, head_revision=args.head_revision
            )
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
