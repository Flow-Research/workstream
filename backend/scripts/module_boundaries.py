#!/usr/bin/env python3
"""Fail-closed modular-monolith dependency validation."""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from scripts import authorization_boundary

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPOSITORY_ROOT / ".ci/module-boundaries/registry.v1.json"
DEFAULT_LEDGER = REPOSITORY_ROOT / ".ci/module-boundaries/private-edge-debt.v1.json"
DEFAULT_AUTH_LEDGER = (
    REPOSITORY_ROOT
    / ".agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md"
)
MODULE_PREFIX = "app.modules."
BUSINESS_MODULES = 9
SUPPORTING_MODULES = 3


class ModuleBoundaryError(RuntimeError):
    """The source tree or protected boundary configuration is invalid."""


@dataclass(frozen=True, order=True, slots=True)
class PrivateEdge:
    """One exact non-AUTH private cross-module dependency."""

    source_file: str
    target_module: str
    imported_private_path: str
    repair_owner: str


@dataclass(frozen=True, slots=True)
class Registry:
    """Canonical modular-monolith module classification."""

    business: tuple[str, ...]
    supporting: tuple[str, ...]
    application_surfaces: tuple[tuple[str, str], ...]

    @property
    def names(self) -> frozenset[str]:
        """Return every registered module name."""
        return frozenset((*self.business, *self.supporting))


def _load_json(path: Path, error: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModuleBoundaryError(error) from exc
    if not isinstance(value, dict):
        raise ModuleBoundaryError(error)
    return value


def load_registry(path: Path) -> Registry:
    """Load and strictly validate the canonical module registry."""
    value = _load_json(path, "invalid_registry")
    if value.get("schema_version") != 1 or set(value) != {
        "schema_version",
        "business_modules",
        "supporting_modules",
        "application_surfaces",
    }:
        raise ModuleBoundaryError("invalid_registry")
    business = value["business_modules"]
    supporting = value["supporting_modules"]
    surfaces = value["application_surfaces"]
    if not isinstance(business, list) or not isinstance(supporting, list):
        raise ModuleBoundaryError("invalid_registry")
    if len(business) != BUSINESS_MODULES or len(supporting) != SUPPORTING_MODULES:
        raise ModuleBoundaryError("invalid_module_count")
    values = business + supporting
    if any(not isinstance(name, str) or not name or not name.isidentifier() for name in values):
        raise ModuleBoundaryError("invalid_module_name")
    if len(set(values)) != len(values):
        raise ModuleBoundaryError("duplicate_module")
    expected_surfaces = {
        ("backend/app/main.py", "application-composition-root-debt-tracked"),
        ("backend/app/api", "delivery-composition-debt-tracked"),
        ("backend/app/adapters", "adapter-debt-tracked"),
        ("backend/app/workers", "durable-delivery-debt-tracked"),
        ("backend/app/interfaces", "legacy-interface-debt-tracked"),
        ("backend/app/db/models.py", "metadata-discovery-model-only"),
    }
    if not isinstance(surfaces, list) or any(
        not isinstance(row, dict)
        or set(row) != {"path", "classification"}
        or not isinstance(row["path"], str)
        or not isinstance(row["classification"], str)
        for row in surfaces
    ):
        raise ModuleBoundaryError("invalid_application_surfaces")
    surface_pairs = {(row["path"], row["classification"]) for row in surfaces}
    if surface_pairs != expected_surfaces or len(surface_pairs) != len(surfaces):
        raise ModuleBoundaryError("invalid_application_surfaces")
    return Registry(tuple(business), tuple(supporting), tuple(sorted(surface_pairs)))


def _module_from_target(target: str) -> str | None:
    if not target.startswith(MODULE_PREFIX):
        return None
    remainder = target.removeprefix(MODULE_PREFIX)
    return remainder.split(".", 1)[0] or None


def _source_module(source: str) -> str | None:
    prefix = "backend/app/modules/"
    if not source.startswith(prefix):
        return None
    return source.removeprefix(prefix).split("/", 1)[0]


def _source_owner_adapter(source: str) -> str | None:
    """Return the module owned by one exact adapter composition root."""
    prefix = "backend/app/adapters/"
    if not source.startswith(prefix):
        return None
    parts = source.removeprefix(prefix).split("/")
    if len(parts) != 2 or parts[1] != "__init__.py":
        return None
    return "authorization" if parts[0] == "auth" else parts[0]


def _is_public_target(target: str, module: str) -> bool:
    public = f"{MODULE_PREFIX}{module}.api"
    return target == public or target.startswith(f"{public}.")


def _repair_owner(target_module: str) -> str:
    if target_module in {"projects", "tasks", "actors"}:
        return "WS-ARCH-001-03"
    if target_module in {"artifacts", "checkers"}:
        return "WS-ARCH-001-04"
    if target_module == "reviews":
        return "WS-ARCH-001-05"
    if target_module in {"contributions", "compensation"}:
        return "WS-ARCH-001-06"
    if target_module in {"audit", "outbox", "api_controls"}:
        return "WS-ARCH-001-07"
    return "owner-unresolved"


def _metadata_discovery_import(source: str, target: str, registry: Registry) -> bool:
    """Recognize the sole model-registration infrastructure exception."""
    metadata_paths = {
        path for path, classification in registry.application_surfaces
        if classification == "metadata-discovery-model-only"
    }
    return source in metadata_paths and target.split(".")[-1] == "models"


def exact_source_imports(path: Path, root: Path, *, source_validated: bool = False) -> set[str]:
    """Return alias-expanded imports after AUTH's fail-closed source validation."""
    if not source_validated:
        authorization_boundary.source_imports(path, root)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise ModuleBoundaryError("invalid_python_source") from exc
    current_module = authorization_boundary._module_name(path, root)
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = authorization_boundary._resolve_from(
                node, current_module, is_package=path.name == "__init__.py"
            )
            parts = base.split(".")
            expand = base == "app.modules" or (
                len(parts) == 3 and parts[:2] == ["app", "modules"]
            )
            for alias in node.names:
                targets.add(f"{base}.{alias.name}" if expand else base)
    return targets


def scan(root: Path, registry: Registry) -> tuple[set[PrivateEdge], dict[str, set[str]], set[authorization_boundary.ImportEdge]]:
    """Scan exact private edges, public dependencies, and AUTH-related edges."""
    app_root = root / "backend/app"
    if not app_root.is_dir():
        raise ModuleBoundaryError("missing_application_root")
    private: set[PrivateEdge] = set()
    public_graph = {name: set() for name in registry.names}
    auth_edges: set[authorization_boundary.ImportEdge] = set()
    for path in sorted(app_root.rglob("*.py")):
        source = path.relative_to(root).as_posix()
        source_module = _source_module(source)
        source_owner_adapter = _source_owner_adapter(source)
        source_is_auth = (
            source_module == "authorization"
            or source == authorization_boundary.AUTH_ADAPTER_ROOT
        )
        canonical_imports = authorization_boundary.source_imports(path, root)
        exact_imports = exact_source_imports(path, root, source_validated=True)
        for target in canonical_imports:
            target_module = _module_from_target(target)
            if target_module is None:
                continue
            if target_module not in registry.names:
                raise ModuleBoundaryError("unknown_module")
            if source_module == target_module:
                continue
            edge = authorization_boundary.ImportEdge(source, target)
            if source_module == target_module or (
                source_is_auth and source_owner_adapter == target_module
            ):
                continue
            if source_is_auth or target_module == "authorization":
                if not _is_public_target(target, target_module):
                    auth_edges.add(edge)
        for target in exact_imports:
            target_module = _module_from_target(target)
            if target_module is None:
                continue
            if target_module not in registry.names:
                raise ModuleBoundaryError("unknown_module")
            if source_module == target_module or source_owner_adapter == target_module:
                continue
            if source_is_auth or target_module == "authorization":
                continue
            if _is_public_target(target, target_module):
                if source_module is not None:
                    public_graph[source_module].add(target_module)
            else:
                if _metadata_discovery_import(source, target, registry):
                    continue
                private.add(
                    PrivateEdge(source, target_module, target, _repair_owner(target_module))
                )
    return private, public_graph, auth_edges


def _validate_public_apis(root: Path, registry: Registry) -> None:
    """Reject public packages that reach into any private module surface."""
    modules_root = root / "backend/app/modules"
    for module in registry.names:
        api_root = modules_root / module / "api"
        if not api_root.exists():
            continue
        for path in sorted(api_root.rglob("*.py")):
            for target in exact_source_imports(path, root):
                target_module = _module_from_target(target)
                if target_module is None:
                    continue
                if target_module not in registry.names:
                    raise ModuleBoundaryError("unknown_module")
                if not _is_public_target(target, target_module):
                    raise ModuleBoundaryError("public_api_private_leak")


def _validate_acyclic(graph: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ModuleBoundaryError("cyclic_public_dependency")
        if node in visited:
            return
        visiting.add(node)
        for target in sorted(graph[node]):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)


def load_ledger(path: Path, registry: Registry) -> set[PrivateEdge]:
    """Load the exact protected-base non-AUTH private-edge ledger."""
    value = _load_json(path, "invalid_ledger")
    return _parse_ledger(value, registry)


def _parse_ledger(value: dict[str, Any], registry: Registry) -> set[PrivateEdge]:
    """Parse one already-loaded protected ledger document."""
    if value.get("schema_version") != 1 or set(value) != {"schema_version", "edges"}:
        raise ModuleBoundaryError("invalid_ledger")
    rows = value["edges"]
    if not isinstance(rows, list):
        raise ModuleBoundaryError("invalid_ledger")
    edges: set[PrivateEdge] = set()
    required = {"source_file", "target_module", "imported_private_path", "repair_owner"}
    for row in rows:
        if not isinstance(row, dict) or set(row) != required:
            raise ModuleBoundaryError("invalid_ledger_edge")
        if any(not isinstance(row[key], str) or not row[key] for key in required):
            raise ModuleBoundaryError("invalid_ledger_edge")
        edge = PrivateEdge(**row)
        if edge.target_module not in registry.names or edge.target_module == "authorization":
            raise ModuleBoundaryError("invalid_ledger_target")
        if edge in edges:
            raise ModuleBoundaryError("duplicate_ledger_edge")
        edges.add(edge)
    return edges


def _git_document(root: Path, ref: str, path: str) -> dict[str, Any] | None:
    """Read one JSON document from an exact Git tree without checkout."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ModuleBoundaryError("invalid_protected_base_ledger") from exc
    if not isinstance(value, dict):
        raise ModuleBoundaryError("invalid_protected_base_ledger")
    return value


def _git_changed_paths(root: Path, ref: str) -> set[str]:
    """Return exact paths changed from the protected base to current HEAD."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{ref}...HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ModuleBoundaryError("invalid_protected_base")
    return {line for line in result.stdout.splitlines() if line}


def validate_protected_base(
    root: Path, ref: str, registry: Registry, current: set[PrivateEdge]
) -> None:
    """Allow debt removal while rejecting additions against an exact base tree."""
    ledger_path = ".ci/module-boundaries/private-edge-debt.v1.json"
    document = _git_document(root, ref, ledger_path)
    if document is None:
        if _git_document(root, ref, ".ci/module-boundaries/registry.v1.json") is not None:
            raise ModuleBoundaryError("missing_protected_base_ledger")
        if any(path.startswith("backend/app/") for path in _git_changed_paths(root, ref)):
            raise ModuleBoundaryError("unsafe_bootstrap_runtime_change")
        return  # Bootstrap is enforcement-only and cannot alter runtime sources.
    protected = _parse_ledger(document, registry)
    if not current.issubset(protected):
        raise ModuleBoundaryError("protected_base_edge_growth")


def validate(
    root: Path,
    registry_path: Path,
    ledger_path: Path,
    auth_ledger: Path,
    protected_base: str | None = None,
) -> None:
    """Validate registry, exact debt, AUTH composition, leaks, and cycles."""
    registry = load_registry(registry_path)
    modules_root = root / "backend/app/modules"
    if not modules_root.is_dir():
        raise ModuleBoundaryError("module_directory_mismatch")
    discovered_modules = {
        path.name for path in modules_root.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    unexpected_module_files = {
        path.name for path in modules_root.glob("*.py")
    } - {"__init__.py"}
    if discovered_modules != registry.names or unexpected_module_files:
        raise ModuleBoundaryError("module_directory_mismatch")
    authorization_boundary.validate(root, auth_ledger)
    expected_auth = set().union(*authorization_boundary.load_ledger(auth_ledger))
    actual_private, public_graph, actual_auth = scan(root, registry)
    if actual_auth != expected_auth:
        raise ModuleBoundaryError("authorization_edge_divergence")
    current_ledger = load_ledger(ledger_path, registry)
    if actual_private != current_ledger:
        raise ModuleBoundaryError("private_edge_mismatch")
    if protected_base:
        validate_protected_base(root, protected_base, registry, current_ledger)
    _validate_public_apis(root, registry)
    _validate_acyclic(public_graph)


def inventory(root: Path, registry_path: Path) -> dict[str, Any]:
    """Return the deterministic current non-AUTH ledger document."""
    registry = load_registry(registry_path)
    edges, _, _ = scan(root, registry)
    return {"schema_version": 1, "edges": [asdict(edge) for edge in sorted(edges)]}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    validate_parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    validate_parser.add_argument("--auth-ledger", type=Path, default=DEFAULT_AUTH_LEDGER)
    validate_parser.add_argument("--protected-base")
    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            print(json.dumps(inventory(REPOSITORY_ROOT, args.registry), indent=2))
        else:
            validate(
                REPOSITORY_ROOT,
                args.registry,
                args.ledger,
                args.auth_ledger,
                args.protected_base,
            )
    except (ModuleBoundaryError, authorization_boundary.AuthorizationBoundaryError) as exc:
        print(f"module-boundaries: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
