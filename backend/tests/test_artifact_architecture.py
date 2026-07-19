"""Static enforcement for the closed artifact capability boundary."""

from __future__ import annotations

import ast
from pathlib import Path

from app.interfaces import artifact_operations


BACKEND_ROOT = Path(__file__).parents[1]
APP_ROOT = BACKEND_ROOT / "app"
ARTIFACT_OPERATIONS = APP_ROOT / "interfaces" / "artifact_operations.py"
COMPOSITION_ROOT = APP_ROOT / "adapters" / "artifacts" / "__init__.py"
S3_ADAPTER_MODULE = APP_ROOT / "adapters" / "artifacts" / "s3_compatible.py"
CLOSED_PORTS = {
    "GuideArtifactIngestPort",
    "ContributorArtifactUploadPort",
    "ArtifactBindingPort",
    "ArtifactMaterializationPort",
    "CheckerArtifactOutputPort",
    "ArtifactOperatorReadPort",
    "ArtifactOperatorRecoveryPort",
}
CANONICAL_REQUESTS = {
    "GuideArtifactIngestRequest",
    "ArtifactBindingCreateRequest",
    "ReadyUploadSetRequest",
    "BindingMaterializationRequest",
    "CheckerOutputArtifactRequest",
    "ArtifactRecoveryRequest",
}
CANONICAL_TYPE_ALIASES = {
    "ArtifactAuditResourceType",
    "ArtifactBindingResourceType",
}
RAW_TYPES = {"ArtifactStore", "ArtifactStorageOrchestrator"}
INTERNAL_ADMISSION_TYPES = {
    "ArtifactAdmissionService",
    "ArtifactAdmissionResult",
    "CheckerOutputArtifactAdmissionRequest",
    "ContributorArtifactAdmissionRequest",
    "GuideArtifactAdmissionRequest",
}
PROVIDER_METHODS = {"put", "observe_put_result", "open", "head"}
CONCRETE_ADAPTER_MODULES = {
    "app.adapters.artifacts.local",
    "app.adapters.artifacts.s3_compatible",
}


def _python_files(*roots: Path) -> tuple[Path, ...]:
    return tuple(sorted(path for root in roots for path in root.rglob("*.py")))


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _annotation_names(annotation: ast.expr | None) -> set[str]:
    if annotation is None:
        return set()
    return {
        node.id
        for node in ast.walk(annotation)
        if isinstance(node, ast.Name)
    } | {
        node.attr
        for node in ast.walk(annotation)
        if isinstance(node, ast.Attribute)
    }


def test_product_api_and_workers_cannot_import_or_inject_raw_artifact_types() -> None:
    product_modules = [
        path
        for path in _python_files(APP_ROOT / "modules", APP_ROOT / "api", APP_ROOT / "workers")
        if APP_ROOT / "modules" / "artifacts" not in path.parents
    ]
    violations: list[str] = []
    for path in product_modules:
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported = {alias.name for alias in node.names}
                forbidden = imported & (RAW_TYPES | INTERNAL_ADMISSION_TYPES)
                if forbidden:
                    violations.append(f"{path.relative_to(BACKEND_ROOT)} imports {sorted(forbidden)}")
                if (
                    node.module == "app.modules.artifacts.service"
                    and any(alias.name == "*" for alias in node.names)
                ):
                    violations.append(
                        f"{path.relative_to(BACKEND_ROOT)} imports broad artifact services"
                    )
            if isinstance(node, ast.Import):
                if any(alias.name == "app.interfaces.artifacts" for alias in node.names):
                    violations.append(
                        f"{path.relative_to(BACKEND_ROOT)} imports the raw artifact module"
                    )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                annotations = [node.returns]
                annotations.extend(argument.annotation for argument in node.args.args)
                annotations.extend(argument.annotation for argument in node.args.kwonlyargs)
                for annotation in annotations:
                    forbidden = _annotation_names(annotation) & RAW_TYPES
                    if forbidden:
                        violations.append(
                            f"{path.relative_to(BACKEND_ROOT)} injects {sorted(forbidden)}"
                        )
    assert violations == []


def test_artifact_domain_has_no_provider_execution_during_admission_foundation() -> None:
    """Keep 02C1 free of all provider write and acknowledgement execution."""
    violations: list[str] = []
    for path in _python_files(APP_ROOT / "modules" / "artifacts"):
        for node in ast.walk(_tree(path)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"put", "observe_put_result"}
            ):
                violations.append(
                    f"{path.relative_to(BACKEND_ROOT)} calls {node.func.attr}"
                )
    assert violations == []


def test_artifact_domain_does_not_import_adapter_modules() -> None:
    """Keep provider-neutral artifact rules independent from adapters."""
    violations: list[str] = []
    for path in _python_files(APP_ROOT / "modules" / "artifacts"):
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.ImportFrom) and (
                node.module or ""
            ).startswith("app.adapters.artifacts"):
                violations.append(
                    f"{path.relative_to(BACKEND_ROOT)} imports {node.module}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app.adapters.artifacts"):
                        violations.append(
                            f"{path.relative_to(BACKEND_ROOT)} imports {alias.name}"
                        )
    assert violations == []


def test_concrete_adapter_construction_has_one_composition_path() -> None:
    factory_calls: list[Path] = []
    adapter_calls: list[Path] = []
    concrete_imports: list[Path] = []
    for path in _python_files(APP_ROOT):
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in CONCRETE_ADAPTER_MODULES:
                concrete_imports.append(path)
            if isinstance(node, ast.Import) and any(
                alias.name in CONCRETE_ADAPTER_MODULES for alias in node.names
            ):
                concrete_imports.append(path)
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            if isinstance(called, ast.Subscript):
                called = called.value
            if isinstance(called, ast.Name):
                name = called.id
            elif isinstance(called, ast.Attribute):
                name = called.attr
            else:
                name = None
            if name == "ExternalServiceAdapterFactory":
                factory_calls.append(path)
            if name in {"LocalStorageAdapter", "S3CompatibleArtifactStore"}:
                adapter_calls.append(path)

    assert factory_calls == [COMPOSITION_ROOT]
    assert adapter_calls == [COMPOSITION_ROOT, S3_ADAPTER_MODULE]
    assert set(concrete_imports) == {COMPOSITION_ROOT}


def test_s3_adapter_exposes_only_required_immutable_object_operations() -> None:
    """Keep list, delete, copy, ACL, and multipart behavior out of the provider."""
    allowed = {"get_object", "head_object", "put_object"}
    forbidden = {
        "abort_multipart_upload",
        "complete_multipart_upload",
        "copy_object",
        "create_multipart_upload",
        "delete_object",
        "delete_objects",
        "list_buckets",
        "list_objects",
        "list_objects_v2",
        "put_object_acl",
        "upload_part",
        "upload_part_copy",
    }
    called = {
        node.func.attr
        for node in ast.walk(_tree(S3_ADAPTER_MODULE))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "client"
    }
    assert called & forbidden == set()
    assert called & allowed == allowed


def test_provider_methods_stay_inside_artifact_orchestration_and_adapters() -> None:
    violations: list[str] = []
    allowed_roots = {
        APP_ROOT / "adapters" / "artifacts",
        APP_ROOT / "modules" / "artifacts",
    }
    for path in _python_files(APP_ROOT):
        if any(root in path.parents for root in allowed_roots):
            continue
        tree = _tree(path)
        artifact_store_receivers = {
            argument.arg
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for argument in (*node.args.args, *node.args.kwonlyargs)
            if "ArtifactStore" in _annotation_names(argument.annotation)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in PROVIDER_METHODS:
                continue
            if not isinstance(node.func.value, ast.Name):
                continue
            if node.func.value.id not in artifact_store_receivers:
                continue
            violations.append(
                f"{path.relative_to(BACKEND_ROOT)} calls provider method {node.func.attr}"
            )
    assert violations == []


def test_artifact_operations_exports_only_canonical_closed_contracts() -> None:
    assert set(artifact_operations.__all__) == (
        CLOSED_PORTS | CANONICAL_REQUESTS | CANONICAL_TYPE_ALIASES
    )
    tree = _tree(ARTIFACT_OPERATIONS)
    protocol_names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
    }
    request_names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name.endswith("Request")
    }
    assert protocol_names == CLOSED_PORTS
    assert request_names == CANONICAL_REQUESTS

    exported_names = {
        element.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
        and isinstance(node.value, (ast.Tuple, ast.List))
        for element in node.value.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }
    assert exported_names == CLOSED_PORTS | CANONICAL_REQUESTS | CANONICAL_TYPE_ALIASES

    forbidden_fields = {
        "adapter",
        "provider_object_ref",
        "storage_namespace",
        "scope_map",
        "server_content_id",
    }
    fields = {
        node.target.id
        for class_node in tree.body
        if isinstance(class_node, ast.ClassDef) and class_node.name in CANONICAL_REQUESTS
        for node in class_node.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert fields.isdisjoint(forbidden_fields)

    operator_read = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ArtifactOperatorReadPort"
    )
    operator_methods = {
        node.name
        for node in operator_read.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert operator_methods == {
        "list_bindings",
        "list_replicas",
        "list_receipts",
        "get_verification_job",
        "get_recovery_attempt",
        "list_audit_events",
        "admission_usage",
    }
    resource_type_annotations = {
        annotation.id
        for method in operator_read.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        for argument in method.args.kwonlyargs
        if argument.arg == "resource_type"
        for annotation in [argument.annotation]
        if isinstance(annotation, ast.Name)
    }
    assert resource_type_annotations == {
        "ArtifactAuditResourceType",
        "ArtifactBindingResourceType",
    }


def test_scratch_cleanup_worker_has_no_product_or_database_state() -> None:
    path = APP_ROOT / "workers" / "artifacts.py"
    forbidden_import_prefixes = (
        "app.db",
        "app.modules.actors",
        "app.modules.audit",
        "app.modules.authorization",
    )
    imported_modules: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
    assert not any(
        module.startswith(forbidden_import_prefixes) for module in imported_modules
    )


def test_artifact_repository_does_not_own_actor_persistence() -> None:
    """Keep canonical actor models and queries behind the actors-owned proof API."""
    path = APP_ROOT / "modules" / "artifacts" / "repository.py"
    tree = _tree(path)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
    assert not any(module.startswith("app.modules.actors") for module in imported_modules)
    assert "actor_profiles" not in path.read_text()
    assert "actor_identity_links" not in path.read_text()
