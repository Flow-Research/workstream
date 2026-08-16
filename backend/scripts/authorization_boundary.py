#!/usr/bin/env python3
"""Fail-closed static validation for the public authorization boundary."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import html
from pathlib import Path, PurePosixPath
import sys
from typing import Iterable

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUTH_PACKAGE = "app.modules.authorization"
PUBLIC_PACKAGE = f"{AUTH_PACKAGE}.api"
DYNAMIC_LOADING_MODULES = {
    "builtins",
    "imp",
    "importlib",
    "pkgutil",
    "pydoc",
    "runpy",
    "zipimport",
}
INBOUND_HEADING = "## Inbound private-import debt"
OUTBOUND_HEADING = "## AUTH outbound private-import debt"
AUTH_ADAPTER_ROOT = "backend/app/adapters/auth/__init__.py"


class AuthorizationBoundaryError(RuntimeError):
    """The source tree or its frozen import ledger is unsafe or inconsistent."""


@dataclass(frozen=True, order=True, slots=True)
class ImportEdge:
    """One exact source-to-imported-module edge."""

    source: str
    target: str


def _repository_path(path: Path, root: Path) -> str:
    """Return a canonical repository-relative POSIX path."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise AuthorizationBoundaryError("unsafe_path") from exc
    value = relative.as_posix()
    if ".." in PurePosixPath(value).parts:
        raise AuthorizationBoundaryError("unsafe_path")
    return value


def _module_name(path: Path, root: Path) -> str:
    """Return the import-qualified module for one backend Python source."""
    relative = _repository_path(path, root)
    prefix = "backend/"
    if not relative.startswith(prefix) or not relative.endswith(".py"):
        raise AuthorizationBoundaryError("invalid_python_path")
    value = relative.removeprefix(prefix).removesuffix(".py").replace("/", ".")
    return value.removesuffix(".__init__")


def _resolve_from(node: ast.ImportFrom, current_module: str, *, is_package: bool) -> str:
    """Canonicalize an absolute or relative ImportFrom module."""
    if node.level == 0:
        if not node.module:
            raise AuthorizationBoundaryError("unresolved_import")
        return node.module
    package = current_module if is_package else current_module.rpartition(".")[0]
    package_parts = package.split(".") if package else []
    keep = len(package_parts) - (node.level - 1)
    if keep <= 0:
        raise AuthorizationBoundaryError("unresolved_relative_import")
    parts = package_parts[:keep]
    if node.module:
        parts.extend(node.module.split("."))
    if not parts:
        raise AuthorizationBoundaryError("unresolved_relative_import")
    return ".".join(parts)


def _import_from_targets(
    node: ast.ImportFrom, current_module: str, *, is_package: bool
) -> Iterable[str]:
    """Yield canonical module targets represented by an ImportFrom node."""
    base = _resolve_from(node, current_module, is_package=is_package)
    for alias in node.names:
        if alias.name == "*":
            raise AuthorizationBoundaryError("wildcard_import")
        if base in {"app.modules", AUTH_PACKAGE}:
            yield f"{base}.{alias.name}"
        else:
            yield base


class _DynamicImportVisitor(ast.NodeVisitor):
    """Reject direct, aliased, copied, or computed Python import calls."""

    def __init__(self) -> None:
        self.importlib_names = {"importlib"}
        self.builtins_names = {"builtins"}
        self.sys_names = {"sys"}
        self.import_call_names = {
            "__import__",
            "compile",
            "eval",
            "exec",
            "globals",
            "locals",
            "vars",
        }

    def visit_Import(self, node: ast.Import) -> None:
        """Reject reflection modules that can conceal computed imports."""
        for alias in node.names:
            root_module = alias.name.partition(".")[0]
            if root_module in DYNAMIC_LOADING_MODULES:
                raise AuthorizationBoundaryError("dynamic_import_surface")
            if alias.name == "sys":
                self.sys_names.add(alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record aliases for importlib.import_module and builtins.__import__."""
        if node.level == 0 and node.module and node.module.startswith("importlib"):
            raise AuthorizationBoundaryError("dynamic_import_surface")
        if (
            node.level == 0
            and node.module
            and node.module.partition(".")[0] in DYNAMIC_LOADING_MODULES
        ):
            raise AuthorizationBoundaryError("dynamic_import_surface")
        if node.level == 0 and node.module == "builtins":
            for alias in node.names:
                if alias.name == "__builtins__" or alias.name in self.import_call_names:
                    raise AuthorizationBoundaryError("dynamic_import_surface")
        if node.level == 0 and node.module == "sys" and any(
            alias.name == "modules" for alias in node.names
        ):
            raise AuthorizationBoundaryError("dynamic_import_surface")

    def visit_Name(self, node: ast.Name) -> None:
        """Reject loading or forwarding any dynamic execution capability."""
        if isinstance(node.ctx, ast.Load) and (
            node.id == "__builtins__" or node.id in self.import_call_names
        ):
            raise AuthorizationBoundaryError("dynamic_import_surface")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Reject loading the module registry through any recognized sys alias."""
        if (
            isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and node.value.id in self.sys_names
            and node.attr == "modules"
        ):
            raise AuthorizationBoundaryError("dynamic_import_surface")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Track simple aliases of recognized import callables."""
        if self._is_import_callable(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.import_call_names.add(target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Fail for every recognized dynamic import call regardless of argument."""
        if self._is_import_callable(node.func) or self._is_computed_import_callable(node.func):
            raise AuthorizationBoundaryError("dynamic_import")
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and bool(node.args)
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in self.sys_names
        ):
            raise AuthorizationBoundaryError("dynamic_import_surface")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Reject module-registry access that can recover import capabilities."""
        if (
            isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id in self.sys_names
            and node.value.attr == "modules"
        ):
            raise AuthorizationBoundaryError("dynamic_import_surface")
        self.generic_visit(node)

    def _is_import_callable(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.import_call_names
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
            return False
        return (
            node.value.id in self.importlib_names and node.attr == "import_module"
        ) or (node.value.id in self.builtins_names and node.attr == "__import__")

    def _is_computed_import_callable(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and bool(node.args)
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in self.importlib_names
        )


def source_imports(path: Path, root: Path) -> set[str]:
    """Parse one source without importing it and return canonical imports."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=_repository_path(path, root))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise AuthorizationBoundaryError("invalid_python_source") from exc
    visitor = _DynamicImportVisitor()
    visitor.visit(tree)
    current_module = _module_name(path, root)
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            targets.update(
                _import_from_targets(node, current_module, is_package=path.name == "__init__.py")
            )
    return targets


def _private_auth_target(target: str) -> bool:
    """Return whether a target bypasses the public AUTH namespace."""
    return target == AUTH_PACKAGE or (
        target.startswith(f"{AUTH_PACKAGE}.")
        and target != PUBLIC_PACKAGE
        and not target.startswith(f"{PUBLIC_PACKAGE}.")
    )


def _private_product_target(target: str) -> bool:
    """Return whether AUTH imports another product module outside its API."""
    if not target.startswith("app.modules.") or target.startswith(f"{AUTH_PACKAGE}."):
        return False
    parts = target.split(".")
    return len(parts) < 4 or parts[3] != "api"


def scan_edges(root: Path) -> tuple[set[ImportEdge], set[ImportEdge]]:
    """Collect exact inbound and outbound private dependency edges."""
    app_root = root / "backend" / "app"
    if not app_root.is_dir():
        raise AuthorizationBoundaryError("missing_application_root")
    inbound: set[ImportEdge] = set()
    outbound: set[ImportEdge] = set()
    for path in sorted(app_root.rglob("*.py")):
        source = _repository_path(path, root)
        module = _module_name(path, root)
        imports = source_imports(path, root)
        inside_auth = (
            module == AUTH_PACKAGE
            or module.startswith(f"{AUTH_PACKAGE}.")
            or source == AUTH_ADAPTER_ROOT
        )
        if inside_auth:
            outbound.update(
                ImportEdge(source, target) for target in imports if _private_product_target(target)
            )
        else:
            inbound.update(
                ImportEdge(source, target) for target in imports if _private_auth_target(target)
            )
    return inbound, outbound


def _section_block(text: str, heading: str) -> list[str]:
    """Return the sole fenced text block following a required heading."""
    if text.count(heading) != 1:
        raise AuthorizationBoundaryError("invalid_ledger_heading")
    remainder = text.split(heading, 1)[1]
    before_next = remainder.split("\n## ", 1)[0]
    parts = before_next.split("```text")
    if len(parts) != 2 or "```" not in parts[1]:
        raise AuthorizationBoundaryError("invalid_ledger_block")
    block, tail = parts[1].split("```", 1)
    if "```" in tail:
        raise AuthorizationBoundaryError("invalid_ledger_block")
    return block.strip().splitlines()


def _parse_edges(lines: Iterable[str]) -> set[ImportEdge]:
    """Parse an exact indented source-to-target edge list."""
    result: set[ImportEdge] = set()
    source: str | None = None
    for raw in lines:
        if not raw.strip():
            continue
        if raw.startswith("  "):
            if source is None or raw.startswith("   "):
                raise AuthorizationBoundaryError("invalid_ledger_edge")
            target = raw.strip()
            edge = ImportEdge(source, target)
            if edge in result:
                raise AuthorizationBoundaryError("duplicate_ledger_edge")
            result.add(edge)
            continue
        source = html.unescape(raw.strip())
        if not source.startswith("backend/app/") or not source.endswith(".py"):
            raise AuthorizationBoundaryError("invalid_ledger_source")
    if not result:
        raise AuthorizationBoundaryError("empty_ledger_section")
    return result


def load_ledger(path: Path) -> tuple[set[ImportEdge], set[ImportEdge]]:
    """Load the canonical inbound and outbound frozen edge sets."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AuthorizationBoundaryError("invalid_ledger") from exc
    return (
        _parse_edges(_section_block(text, INBOUND_HEADING)),
        _parse_edges(_section_block(text, OUTBOUND_HEADING)),
    )


def validate(root: Path, ledger: Path) -> None:
    """Require the source edge sets to equal the frozen ledger exactly."""
    expected_inbound, expected_outbound = load_ledger(ledger)
    actual_inbound, actual_outbound = scan_edges(root)
    if actual_inbound != expected_inbound:
        raise AuthorizationBoundaryError("inbound_edge_mismatch")
    if actual_outbound != expected_outbound:
        raise AuthorizationBoundaryError("outbound_edge_mismatch")


def main() -> int:
    """Run the boundary validator from the command line."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--ledger", required=True, type=Path)
    args = parser.parse_args()
    try:
        validate(REPOSITORY_ROOT, args.ledger)
    except AuthorizationBoundaryError as exc:
        print(f"authorization-boundary: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
