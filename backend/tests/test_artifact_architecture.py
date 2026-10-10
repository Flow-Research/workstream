"""Static enforcement for the closed artifact capability boundary."""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest
from tests.architecture_ast import imported_symbols_and_calls

from app.interfaces import artifact_operations
from app.db.base import Base
from app.main import create_app


BACKEND_ROOT = Path(__file__).parents[1]
APP_ROOT = BACKEND_ROOT / "app"
ARTIFACT_OPERATIONS = APP_ROOT / "interfaces" / "artifact_operations.py"
SUBMISSION_PREPARATION_API = (
    APP_ROOT / "modules" / "artifacts" / "api" / "submission_preparation.py"
)
SUBMISSION_ADMISSION_API = APP_ROOT / "modules" / "artifacts" / "api" / "submission_admission.py"
CHECKER_OUTPUT_CUSTODY_API = (
    APP_ROOT / "modules" / "checkers" / "api" / "output_custody.py"
)
CHECKER_MATERIALIZATION_API = (
    APP_ROOT / "modules" / "checkers" / "api" / "materialization.py"
)
RETIRED_ARTIFACT_MATERIALIZATION_API = (
    APP_ROOT / "modules" / "artifacts" / "api" / "submission_materialization.py"
)
COMPOSITION_ROOT = APP_ROOT / "adapters" / "artifacts" / "__init__.py"
CHECKER_COMPOSITION_ROOT = APP_ROOT / "adapters" / "checkers" / "__init__.py"
AGENT_COMPOSITION_ROOT = APP_ROOT / "adapters/project_agents/__init__.py"
OBSERVABILITY_COMPOSITION_ROOT = APP_ROOT / "adapters" / "observability.py"
AGENT_ADAPTER_MODULE = "app.adapters.project_agents.openai_agent_sdk"
S3_ADAPTER_MODULE = APP_ROOT / "adapters" / "artifacts" / "s3_compatible.py"
CLOSED_PORTS = {
    "GuideArtifactIngestCommand",
    "GuideArtifactIngestPort",
    "ArtifactOperatorReadPort",
    "ArtifactOperatorRecoveryPort",
}
CANONICAL_REQUESTS = {
    "GuideArtifactIngestRequest",
    "ArtifactRecoveryRequest",
}
CANONICAL_RESULTS = {
    "GuideArtifactIngestResult",
}
CANONICAL_TYPE_ALIASES = {
    "ArtifactAuditResourceType",
    "ArtifactBindingResourceType",
}
CANONICAL_VALUE_TYPES = set()
PREPARED_MUTATION_REQUESTS = {"GuideArtifactIngestRequest"}
PREPARED_HANDLE_FORBIDDEN_ROOTS = (
    APP_ROOT / "adapters",
    APP_ROOT / "api",
    APP_ROOT / "modules" / "outbox",
    APP_ROOT / "schemas",
    APP_ROOT / "workers",
)
RAW_TYPES = {"ArtifactStore", "ArtifactStorageOrchestrator"}
INTERNAL_ADMISSION_TYPES = {
    "ArtifactAdmissionService",
    "ArtifactAdmissionResult",
    "CheckerOutputArtifactAdmissionRequest",
    "GuideArtifactAdmissionRequest",
    "SubmissionBundleArtifactAdmissionRequest",
}

RETIRED_CONTRIBUTOR_INTAKE_NAMES = {
    "ArtifactUploadItem",
    "ArtifactUploadSession",
    "ContributorArtifactAdmissionRequest",
    "ContributorAdmissionFacts",
    "get_contributor_admission_facts",
    "get_receipt_for_item",
    "lock_upload_item",
    "lock_upload_session",
    "_contributor_facts",
}
PROVIDER_METHODS = {"put", "observe_put_result", "open", "head"}
CONCRETE_ADAPTER_MODULES = {
    "app.adapters.artifacts.local",
    "app.adapters.artifacts.s3_compatible",
    "app.adapters.checkers.external_service",
}
CONCRETE_OBSERVABILITY_MODULES = {
    "opentelemetry.exporter.otlp.proto.http.metric_exporter",
    "opentelemetry.exporter.otlp.proto.http.trace_exporter",
}


def _python_files(*roots: Path) -> tuple[Path, ...]:
    return tuple(sorted(path for root in roots for path in root.rglob("*.py")))


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _annotation_names(annotation: ast.expr | None) -> set[str]:
    if annotation is None:
        return set()
    return {node.id for node in ast.walk(annotation) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(annotation) if isinstance(node, ast.Attribute)
    }


def _declared_annotation_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            names.update(_annotation_names(node.annotation))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
            for argument in arguments:
                names.update(_annotation_names(argument.annotation))
            if node.args.vararg is not None:
                names.update(_annotation_names(node.args.vararg.annotation))
            if node.args.kwarg is not None:
                names.update(_annotation_names(node.args.kwarg.annotation))
            names.update(_annotation_names(node.returns))
    return names


def test_retired_contributor_intake_has_no_runtime_declaration_or_reference() -> None:
    runtime_files = _python_files(APP_ROOT)
    for path in runtime_files:
        tree = _tree(path)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        declared = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert not ((names | declared) & RETIRED_CONTRIBUTOR_INTAKE_NAMES), path

    assert "artifact_upload_sessions" not in Base.metadata.tables
    assert "artifact_upload_items" not in Base.metadata.tables


def test_no_retired_or_replacement_contributor_intake_route_is_composed() -> None:
    paths = set(create_app().openapi()["paths"])
    forbidden_fragments = (
        "artifact-upload",
        "artifact_upload",
        "upload-session",
        "upload_session",
        "submission-bundle",
        "submission_bundle",
    )
    assert not {path for path in paths if any(fragment in path for fragment in forbidden_fragments)}


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
                    violations.append(
                        f"{path.relative_to(BACKEND_ROOT)} imports {sorted(forbidden)}"
                    )
                if node.module == "app.modules.artifacts.service" and any(
                    alias.name == "*" for alias in node.names
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


def test_only_artifact_custody_services_own_provider_execution() -> None:
    """Fence store calls to the orchestrator and exact guide/Submission readers."""
    violations: list[str] = []
    for path in _python_files(APP_ROOT / "modules" / "artifacts"):
        tree = _tree(path)
        owners = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name in {"ArtifactStorageOrchestrator", "ScopedGuideDocumentGrant", "PostSubmissionMaterializer"}
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in PROVIDER_METHODS
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "_store"
            ):
                owner = next(
                    (
                        candidate
                        for candidate in owners.values()
                        if candidate.lineno
                        <= node.lineno
                        <= (candidate.end_lineno or candidate.lineno)
                    ),
                    None,
                )
                if owner is None or (
                    owner.name in {"ScopedGuideDocumentGrant", "PostSubmissionMaterializer"} and node.func.attr != "open"
                ):
                    violations.append(f"{path.relative_to(BACKEND_ROOT)} calls {node.func.attr}")
    assert violations == []


def test_artifact_domain_does_not_import_adapter_modules() -> None:
    """Keep provider-neutral artifact rules independent from adapters."""
    violations: list[str] = []
    for path in _python_files(APP_ROOT / "modules" / "artifacts"):
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "app.adapters.artifacts"
            ):
                violations.append(f"{path.relative_to(BACKEND_ROOT)} imports {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app.adapters.artifacts"):
                        violations.append(f"{path.relative_to(BACKEND_ROOT)} imports {alias.name}")
    assert violations == []


def test_project_domain_does_not_query_artifact_persistence_models() -> None:
    """Require project orchestration to consume the narrow material port."""
    forbidden_prefixes = (
        "app.modules.artifacts.models",
        "app.modules.artifacts.repository",
    )
    violations: list[str] = []
    for path in _python_files(APP_ROOT / "modules" / "projects"):
        for node in ast.walk(_tree(path)):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom):
                if node.level >= 2 and node.module is not None:
                    modules.append(f"app.modules.{node.module}")
                elif node.level == 0 and node.module is not None:
                    modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            if any(
                module == prefix or module.startswith(f"{prefix}.")
                for module in modules
                for prefix in forbidden_prefixes
            ):
                violations.append(str(path.relative_to(BACKEND_ROOT)))
    assert violations == []


def test_concrete_adapter_construction_has_one_composition_path() -> None:
    factory_calls: list[Path] = []
    adapter_calls: list[Path] = []
    concrete_imports: list[Path] = []
    agent_imports: list[Path] = []
    agent_calls: list[Path] = []
    observability_imports: list[Path] = []
    observability_calls: list[Path] = []
    for path in _python_files(APP_ROOT):
        imports, calls = imported_symbols_and_calls(_tree(path))
        if imports & CONCRETE_ADAPTER_MODULES:
            concrete_imports.append(path)
        if AGENT_ADAPTER_MODULE in imports:
            agent_imports.append(path)
        if imports & CONCRETE_OBSERVABILITY_MODULES:
            observability_imports.append(path)
        factory_calls.extend(path for name in calls if name == "ExternalServiceAdapterFactory")
        adapter_calls.extend(
            path
            for name in calls
            if name
            in {
                "LocalStorageAdapter",
                "S3CompatibleArtifactStore",
                "UnixSocketExternalCheckerAdapter",
            }
        )
        agent_calls.extend(path for name in calls if name == "OpenAIAgentSdkProjectGuideRuntime")
        observability_calls.extend(
            path
            for name in calls
            if name in {"OTLPMetricExporter", "OTLPSpanExporter", "PeriodicExportingMetricReader"}
        )
    assert set(factory_calls) == {
        COMPOSITION_ROOT,
        CHECKER_COMPOSITION_ROOT,
        AGENT_COMPOSITION_ROOT,
        OBSERVABILITY_COMPOSITION_ROOT,
    }
    assert len(factory_calls) == 4
    assert adapter_calls == [COMPOSITION_ROOT, S3_ADAPTER_MODULE, CHECKER_COMPOSITION_ROOT]
    assert set(concrete_imports) == {COMPOSITION_ROOT, CHECKER_COMPOSITION_ROOT}
    assert agent_imports == [AGENT_COMPOSITION_ROOT]
    assert agent_calls == [AGENT_COMPOSITION_ROOT]
    assert observability_imports == [OBSERVABILITY_COMPOSITION_ROOT]
    assert observability_calls == [OBSERVABILITY_COMPOSITION_ROOT] * 3


@pytest.mark.parametrize("source", [
    "from app.interfaces.external_services import ExternalServiceAdapterFactory as factory\nfactory[object]('extra')\n",
    "from app.interfaces.external_services import ExternalServiceAdapterFactory\nfactory: object = ExternalServiceAdapterFactory\nfactory[object]('extra')\n",
    "import app.interfaces.external_services as external\nexternal.ExternalServiceAdapterFactory[object]('extra')\n",
    "from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime as runtime\nruntime(configuration)\n",
    "import app.adapters.project_agents.openai_agent_sdk as sdk\nsdk.OpenAIAgentSdkProjectGuideRuntime(configuration)\n",
])
def test_composition_proof_rejects_aliased_factories_and_concrete_runtimes(tmp_path, monkeypatch, source):
    import sys

    paths = _python_files(APP_ROOT)
    injected = tmp_path / "extra.py"
    injected.write_text(source)
    monkeypatch.setattr(sys.modules[__name__], "_python_files", lambda *_: (*paths, injected))
    with pytest.raises(AssertionError):
        test_concrete_adapter_construction_has_one_composition_path()


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
        CLOSED_PORTS
        | CANONICAL_REQUESTS
        | CANONICAL_RESULTS
        | CANONICAL_TYPE_ALIASES
        | CANONICAL_VALUE_TYPES
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
    result_names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name.endswith("Result")
    }
    assert protocol_names == CLOSED_PORTS
    assert request_names == CANONICAL_REQUESTS
    assert result_names == CANONICAL_RESULTS

    exported_names = {
        element.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
        and isinstance(node.value, (ast.Tuple, ast.List))
        for element in node.value.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }
    assert exported_names == (
        CLOSED_PORTS
        | CANONICAL_REQUESTS
        | CANONICAL_RESULTS
        | CANONICAL_TYPE_ALIASES
        | CANONICAL_VALUE_TYPES
    )

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
        if isinstance(class_node, ast.ClassDef)
        and class_node.name in (CANONICAL_REQUESTS | CANONICAL_RESULTS)
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


def test_artifact_ports_keep_prepared_authority_at_the_transaction_boundary() -> None:
    tree = _tree(ARTIFACT_OPERATIONS)
    request_classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in PREPARED_MUTATION_REQUESTS
    }
    assert set(request_classes) == PREPARED_MUTATION_REQUESTS
    for name, class_node in request_classes.items():
        assert not any(
            isinstance(base, ast.Name) and base.id == "BaseModel" for base in class_node.bases
        ), name
        fields = {
            node.target.id: _annotation_names(node.annotation)
            for node in class_node.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        assert fields.get("prepared_authorization") == {"PreparedAuthorizationHandle"}, name
        assert all("AuthorizationContext" not in types for types in fields.values()), name
        assert {"action_id", "resource_context", "facts"}.isdisjoint(fields), name

    source = ARTIFACT_OPERATIONS.read_text(encoding="utf-8")
    assert "upload_session" not in source
    assert "ContributorArtifactUploadPort" not in source
    assert "ReadyUploadSetRequest" not in source
    assert "ActionId" not in source

    expected_methods = {
        "GuideArtifactIngestPort": {"ingest"},
    }
    expected_request_by_method = {
        "ingest": "GuideArtifactIngestRequest",
    }
    protocols = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in expected_methods
    }
    for name, methods in expected_methods.items():
        declared_methods = {
            node.name
            for node in protocols[name].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert declared_methods == methods
        for node in protocols[name].body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            assert node.args.posonlyargs == []
            assert [argument.arg for argument in node.args.args] == ["self", "selector" if node.name == "recover" else "request"]
            assert node.args.kwonlyargs == []
            assert node.args.vararg is None
            assert node.args.kwarg is None
            request_argument = node.args.args[-1]
            assert _annotation_names(request_argument.annotation) == {
                expected_request_by_method[node.name]
            }
            assert "AuthorizationContext" not in _declared_annotation_names(node)


def test_checker_output_contract_has_one_canonical_consumer_owner() -> None:
    """CHECKERS owns the ports that ART implements for future durable execution."""
    tree = _tree(CHECKER_OUTPUT_CUSTODY_API)
    classes = {
        node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
    }
    assert {
        "CheckerOutputArtifactRequest",
        "CheckerOutputArtifactResult",
        "CheckerOutputBindingRequest",
        "CheckerOutputBindingResult",
        "CheckerOutputBindingPort",
        "CheckerArtifactOutputPort",
    } <= set(classes)
    assert "ArtifactBindingPort" not in classes
    for name in ("CheckerOutputArtifactRequest", "CheckerOutputBindingRequest"):
        annotations = _declared_annotation_names(classes[name])
        assert {"PreparedAuthorizationHandle", "AuthorizationContext"}.isdisjoint(
            annotations
        )
        assert "CheckerOutputSelector" in annotations

    expected_methods = {
        "CheckerOutputBindingPort": {"bind_checker_output"},
        "CheckerArtifactOutputPort": {"store", "recover"},
    }
    for name, methods in expected_methods.items():
        assert {
            item.name
            for item in classes[name].body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        } == methods

    artifact_source = ARTIFACT_OPERATIONS.read_text(encoding="utf-8")
    assert "app.modules.checkers" not in artifact_source
    assert not RETIRED_ARTIFACT_MATERIALIZATION_API.exists()
    assert "ArtifactBindingPort" not in "\n".join(
        path.read_text(encoding="utf-8") for path in _python_files(APP_ROOT)
    )


def test_checker_materialization_contract_has_one_canonical_consumer_owner() -> None:
    """The complete material callback contract resides in CHECKERS public API."""
    tree = _tree(CHECKER_MATERIALIZATION_API)
    classes = {
        node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
    }
    assert set(classes) == {
        "MaterializationFacts", "PreparedMaterialization", "MaterializationAuthorityPort",
        "PostSubmissionMaterializationUnavailable",
        "PostSubmissionMaterializationFailure",
        "SubmissionMaterialEntry",
        "SubmissionMaterialView",
        "PostSubmissionMaterialConsumer",
        "PostSubmissionMaterializationResult",
        "PostSubmissionMaterializationPort",
    }
    assert {
        node.name
        for node in classes["PostSubmissionMaterializationPort"].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    } == {"materialize"}
    artifact_api = APP_ROOT / "modules" / "artifacts" / "api" / "__init__.py"
    assert "Materialization" not in artifact_api.read_text(encoding="utf-8")


def test_checker_custody_ports_have_exact_owner_and_art_consumers() -> None:
    """Allow only named CHECKERS consumers and ART implementations of custody ports."""
    expected = {
        "app.modules.checkers.api.output_custody": {
            "app/adapters/artifacts/__init__.py",
            "app/modules/artifacts/checker_output_bindings.py",
            "app/modules/artifacts/checker_output_custody.py",
            "app/modules/artifacts/checker_outputs.py",
            "app/modules/artifacts/schemas.py",
            "app/modules/artifacts/service.py",
            "app/modules/checkers/execution_coordination.py",
        },
        "app.modules.checkers.api.materialization": {
            "app/modules/authorization/domain/post_submit.py",
            "app/modules/authorization/post_submit_authorization.py",
            "app/adapters/artifacts/__init__.py",
            "app/modules/artifacts/post_submit_materialization.py",
            "app/modules/artifacts/post_submit_selection.py",
            "app/modules/checkers/execution.py",
        },
    }
    actual = {module: set() for module in expected}
    for path in _python_files(APP_ROOT):
        modules: set[str] = set()
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.ImportFrom):
                package = ".".join(path.parent.relative_to(BACKEND_ROOT).parts)
                module = resolve_name("." * node.level + (node.module or ""), package)
                modules.add(module)
                modules.update(f"{module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        for module in modules & expected.keys():
            actual[module].add(path.relative_to(BACKEND_ROOT).as_posix())
    assert actual == expected

    composition = _tree(COMPOSITION_ROOT)
    returns = {
        node.name: _annotation_names(node.returns)
        for node in composition.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {
            "post_submission_materialization",
            "checker_output_storage",
            "checker_output_binding",
        }
    }
    assert returns == {
        "post_submission_materialization": {"PostSubmissionMaterializationPort"},
        "checker_output_storage": {"CheckerArtifactOutputPort"},
        "checker_output_binding": {"CheckerOutputBindingPort"},
    }


@pytest.mark.parametrize("port", ["output_custody", "materialization"])
@pytest.mark.parametrize("form", ["symbol", "module", "parent", "relative", "relative_parent"])
def test_checker_custody_inventory_rejects_unregistered_import(monkeypatch, port, form):
    """Alternate import spelling must not conceal an additional API consumer."""
    import sys

    statement = {
        "symbol": f"from app.modules.checkers.api.{port} import AnyContract",
        "module": f"import app.modules.checkers.api.{port} as custody",
        "parent": f"from app.modules.checkers.api import {port} as custody",
        "relative": f"from .modules.checkers.api.{port} import AnyContract",
        "relative_parent": f"from .modules.checkers.api import {port} as custody",
    }[form]
    original = _tree

    def injected(path):
        tree = original(path)
        if path == APP_ROOT / "main.py":
            tree.body.extend(ast.parse(statement).body)
        return tree

    monkeypatch.setattr(sys.modules[__name__], "_tree", injected)
    with pytest.raises(AssertionError):
        test_checker_custody_ports_have_exact_owner_and_art_consumers()


def test_submission_preparation_http_request_never_carries_prepared_authority() -> None:
    tree = _tree(SUBMISSION_PREPARATION_API)
    request_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SubmissionBundlePreparationRequest"
    )
    fields = {
        node.target.id: _annotation_names(node.annotation)
        for node in request_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert "prepared_authorization" not in fields
    assert fields["actor"] == {"ActorIdentityFacts"}
    assert fields["request_id"] == {"UUID"}
    assert fields["correlation_id"] == {"UUID"}
    assert fields["idempotency_key"] == {"UUID"}


def test_prepared_handle_never_enters_public_async_or_provider_contracts() -> None:
    violations: list[str] = []
    schema_files = tuple(APP_ROOT.glob("modules/**/schemas.py"))
    route_files = tuple(APP_ROOT.glob("modules/**/router.py"))
    provider_interface_files = tuple(
        path for path in _python_files(APP_ROOT / "interfaces") if path != ARTIFACT_OPERATIONS
    )
    for path in (
        _python_files(*PREPARED_HANDLE_FORBIDDEN_ROOTS)
        + schema_files
        + route_files
        + provider_interface_files
    ):
        names = _declared_annotation_names(_tree(path))
        if "PreparedAuthorizationHandle" in names:
            violations.append(str(path.relative_to(BACKEND_ROOT)))
    assert violations == []


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
    assert not any(module.startswith(forbidden_import_prefixes) for module in imported_modules)


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




def test_guide_original_runtime_keeps_provider_sdk_out_of_product_modules() -> None:
    """Product owners depend on ports; hosted inspection belongs to the SDK adapter."""
    for path in (APP_ROOT / "modules").rglob("*.py"):
        for node in ast.walk(_tree(path)):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) and node.module
                       else [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            assert not any(module.split(".")[0] in {"openai", "agents", "pypdf", "PIL"} for module in modules), str(path)


def test_safe_xml_dependency_has_one_ingress_consumer() -> None:
    importers = set()
    for path in APP_ROOT.rglob("*.py"):
        for node in ast.walk(_tree(path)):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) and node.module
                       else [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            if any(module.split(".")[0] == "defusedxml" for module in modules):
                importers.add(path.relative_to(APP_ROOT).as_posix())
    assert importers == {"modules/artifacts/guide_formats.py"}
