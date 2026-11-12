"""Architecture proof for the repository-wide public module boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import module_boundaries as boundary
from scripts.authorization_boundary import AuthorizationBoundaryError

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / ".ci/module-boundaries/registry.v1.json"
LEDGER = ROOT / ".ci/module-boundaries/private-edge-debt.v1.json"
AUTH_LEDGER = ROOT / ".ci/auth-boundaries/IMPORT_LEDGER.md"


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _registry(path: Path) -> None:
    path.write_text(REGISTRY.read_text(encoding="utf-8"), encoding="utf-8")


def test_repository_matches_the_protected_module_boundary() -> None:
    """Current exact debt, AUTH composition, APIs, and graph are valid."""
    boundary.validate(ROOT, REGISTRY, LEDGER, AUTH_LEDGER)


def test_registry_names_exactly_eleven_business_and_three_supporting_modules() -> None:
    """The canonical ownership map cannot silently grow or collapse."""
    registry = boundary.load_registry(REGISTRY)
    assert len(registry.business) == 11
    assert len(registry.supporting) == 3
    assert registry.names == {
        "actors",
        "authorization",
        "projects",
        "tasks",
        "artifacts",
        "checkers",
        "model_usage",
        "reviews",
        "contributions",
        "compensation",
        "finance",
        "audit",
        "outbox",
        "api_controls",
    }
    assert dict(registry.application_surfaces)["backend/app/interfaces"] == (
        "legacy-interface-debt-tracked"
    )


def test_new_private_edge_fails_exact_ledger_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second import in an already indebted source is still new debt."""
    edge = boundary.PrivateEdge(
        "backend/app/modules/tasks/service.py",
        "projects",
        "app.modules.projects.repository",
        "WS-ARCH-001-03",
    )
    graph = {name: set() for name in boundary.load_registry(REGISTRY).names}
    monkeypatch.setattr(boundary.authorization_boundary, "validate", lambda *_: None)
    monkeypatch.setattr(boundary.authorization_boundary, "load_ledger", lambda *_: (set(), set()))
    monkeypatch.setattr(boundary, "scan", lambda *_: ({edge}, graph, set()))
    monkeypatch.setattr(boundary, "load_ledger", lambda *_: set())
    monkeypatch.setattr(boundary, "_validate_public_apis", lambda *_: None)
    with pytest.raises(boundary.ModuleBoundaryError, match="private_edge_mismatch"):
        boundary.validate(ROOT, REGISTRY, LEDGER, AUTH_LEDGER)


def test_owner_adapter_may_bind_only_its_own_private_implementation(
    tmp_path: Path,
) -> None:
    """Owner adapters are composition; cross-owner private imports remain debt."""
    _registry(tmp_path / "registry.json")
    _write(
        tmp_path / "backend/app/adapters/tasks/__init__.py",
        "from app.modules.tasks.repository import TaskRepository\n"
        "from app.modules.projects.repository import ProjectRepository\n",
    )
    private, _, _ = boundary.scan(tmp_path, boundary.load_registry(tmp_path / "registry.json"))
    assert private == {
        boundary.PrivateEdge(
            "backend/app/adapters/tasks/__init__.py",
            "projects",
            "app.modules.projects.repository",
            "WS-ARCH-001-03",
        )
    }


def test_non_root_adapter_keeps_same_owner_private_debt_visible(
    tmp_path: Path,
) -> None:
    """Only the exact owner composition root receives the wiring exemption."""
    _registry(tmp_path / "registry.json")
    _write(
        tmp_path / "backend/app/adapters/tasks/worker.py",
        "from app.modules.tasks.repository import TaskRepository\n",
    )
    private, _, _ = boundary.scan(tmp_path, boundary.load_registry(tmp_path / "registry.json"))
    assert private == {
        boundary.PrivateEdge(
            "backend/app/adapters/tasks/worker.py",
            "tasks",
            "app.modules.tasks.repository",
            "WS-ARCH-001-03",
        )
    }


def test_import_from_modules_package_resolves_registered_alias(tmp_path: Path) -> None:
    """Package-level module aliases cannot disappear from dependency scanning."""
    _registry(tmp_path / "registry.json")
    path = tmp_path / "backend/app/modules/tasks/service.py"
    _write(path, "from app.modules import projects\n")
    assert boundary.exact_source_imports(path, tmp_path) == {"app.modules.projects"}


def test_unregistered_top_level_module_file_fails_closed(tmp_path: Path) -> None:
    """A file beside module packages cannot create an invisible pseudo-module."""
    registry_path = tmp_path / "registry.json"
    _registry(registry_path)
    registry = boundary.load_registry(registry_path)
    modules_root = tmp_path / "backend/app/modules"
    for name in registry.names:
        (modules_root / name).mkdir(parents=True)
    _write(modules_root / "rogue.py", "value = 1\n")
    with pytest.raises(boundary.ModuleBoundaryError, match="module_directory_mismatch"):
        boundary.validate(
            tmp_path,
            registry_path,
            tmp_path / "ledger.json",
            tmp_path / "auth-ledger.md",
        )


def test_protected_base_rejects_new_or_expanded_debt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing code and its ledger together cannot authorize boundary growth."""
    registry = boundary.load_registry(REGISTRY)
    current = boundary.load_ledger(LEDGER, registry)
    new_edge = boundary.PrivateEdge(
        "backend/app/modules/tasks/new.py",
        "projects",
        "app.modules.projects.repository",
        "WS-ARCH-001-03",
    )
    protected_document = {
        "schema_version": 1,
        "edges": [boundary.asdict(edge) for edge in sorted(current)],
    }
    monkeypatch.setattr(boundary, "_git_document", lambda *_: protected_document)
    with pytest.raises(boundary.ModuleBoundaryError, match="protected_base_edge_growth"):
        boundary.validate_protected_base(ROOT, "base", registry, current | {new_edge})


def test_bootstrap_rejects_runtime_source_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first ledger install cannot hide a product edge added by its own PR."""
    registry = boundary.load_registry(REGISTRY)
    monkeypatch.setattr(boundary, "_git_document", lambda *_: None)
    monkeypatch.setattr(
        boundary,
        "_git_changed_paths",
        lambda *_: {"backend/app/modules/tasks/service.py"},
    )
    with pytest.raises(boundary.ModuleBoundaryError, match="unsafe_bootstrap_runtime_change"):
        boundary.validate_protected_base(ROOT, "base", registry, set())


def test_bootstrap_allows_enforcement_only_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WS-ARCH-001-01 may install the absent gate without runtime changes."""
    registry = boundary.load_registry(REGISTRY)
    monkeypatch.setattr(boundary, "_git_document", lambda *_: None)
    monkeypatch.setattr(
        boundary,
        "_git_changed_paths",
        lambda *_: {"backend/scripts/module_boundaries.py"},
    )
    boundary.validate_protected_base(ROOT, "base", registry, set())


def test_unknown_module_fails_closed(tmp_path: Path) -> None:
    """Unregistered product packages cannot bypass module ownership."""
    _registry(tmp_path / "registry.json")
    _write(
        tmp_path / "backend/app/modules/tasks/service.py",
        "from app.modules.unknown import repository\n",
    )
    with pytest.raises(boundary.ModuleBoundaryError, match="unknown_module"):
        boundary.scan(tmp_path, boundary.load_registry(tmp_path / "registry.json"))


def test_auth_view_contains_only_cross_boundary_private_edges(tmp_path: Path) -> None:
    """AUTH internal topology never pollutes its canonical boundary ledger."""
    _registry(tmp_path / "registry.json")
    _write(
        tmp_path / "backend/app/modules/authorization/service.py",
        "from app.modules.authorization import repository\nfrom app.modules.tasks import models\n",
    )
    _write(
        tmp_path / "backend/app/modules/tasks/service.py",
        "from app.modules.authorization import runtime\n",
    )
    _, _, auth_edges = boundary.scan(tmp_path, boundary.load_registry(tmp_path / "registry.json"))
    assert auth_edges == {
        boundary.authorization_boundary.ImportEdge(
            "backend/app/modules/authorization/service.py", "app.modules.tasks"
        ),
        boundary.authorization_boundary.ImportEdge(
            "backend/app/modules/tasks/service.py", "app.modules.authorization.runtime"
        ),
    }


def test_public_api_private_reexport_fails_closed(tmp_path: Path) -> None:
    """An api package cannot disguise another module's private implementation."""
    _registry(tmp_path / "registry.json")
    _write(
        tmp_path / "backend/app/modules/tasks/api/__init__.py",
        "from app.modules.projects.repository import ProjectRepository\n",
    )
    with pytest.raises(boundary.ModuleBoundaryError, match="public_api_private_leak"):
        boundary._validate_public_apis(  # noqa: SLF001 - architecture proof
            tmp_path, boundary.load_registry(tmp_path / "registry.json")
        )


def test_tasks_public_api_has_no_private_or_mutable_dependency() -> None:
    """TASK facts remain dependency-safe immutable public contracts."""
    boundary._validate_public_apis(  # noqa: SLF001 - architecture proof
        ROOT, boundary.load_registry(REGISTRY)
    )
    api_files = list((ROOT / "backend/app/modules/tasks/api").rglob("*.py"))
    assert api_files
    imports: set[str] = set()
    for path in api_files:
        imports.update(boundary.exact_source_imports(path, ROOT))
    assert imports
    assert all(
        not target.startswith("app.modules.") or target.startswith("app.modules.tasks.api")
        for target in imports
    )


def test_projects_public_api_has_no_private_or_mutable_dependency() -> None:
    """PROJECT facts remain dependency-safe immutable public contracts."""
    boundary._validate_public_apis(  # noqa: SLF001 - architecture proof
        ROOT, boundary.load_registry(REGISTRY)
    )
    api_files = list((ROOT / "backend/app/modules/projects/api").rglob("*.py"))
    assert api_files
    imports: set[str] = set()
    for path in api_files:
        imports.update(boundary.exact_source_imports(path, ROOT))
    assert imports
    assert all(
        not target.startswith("app.modules.")
        or target.startswith("app.modules.projects.api")
        or target == "app.modules.checkers.api.external_policy"
        for target in imports
    )


def test_checkers_public_api_has_no_private_or_mutable_dependency() -> None:
    """CHECKER plans and result facts remain dependency-safe contracts."""
    boundary._validate_public_apis(  # noqa: SLF001 - architecture proof
        ROOT, boundary.load_registry(REGISTRY)
    )
    api_files = list((ROOT / "backend/app/modules/checkers/api").rglob("*.py"))
    assert api_files
    imports: set[str] = set()
    for path in api_files:
        imports.update(boundary.exact_source_imports(path, ROOT))
    assert imports
    assert all(
        not target.startswith("app.modules.")
        or target == "app.modules.checkers.api"
        or target.startswith("app.modules.checkers.api.")
        or target == "app.modules.model_usage.api"
        for target in imports
    )


def test_cyclic_public_dependencies_fail_closed() -> None:
    """Typed public facades cannot form an architectural dependency cycle."""
    graph = {name: set() for name in boundary.load_registry(REGISTRY).names}
    graph["tasks"].add("artifacts")
    graph["artifacts"].add("tasks")
    with pytest.raises(boundary.ModuleBoundaryError, match="cyclic_public_dependency"):
        boundary._validate_acyclic(graph)  # noqa: SLF001 - architecture proof


def test_art_implements_checker_consumer_ports_without_a_public_cycle() -> None:
    """Selected checker execution has no private CHECKERS-to-ART dependency."""
    registry = boundary.load_registry(REGISTRY)
    private, graph, _ = boundary.scan(ROOT, registry)
    assert "checkers" in graph["artifacts"]
    assert "artifacts" not in graph["checkers"]
    assert {
        (edge.source_file, edge.imported_private_path)
        for edge in private
        if edge.source_file.startswith("backend/app/modules/checkers/")
        and edge.target_module == "artifacts"
    } == set()
    boundary._validate_acyclic(graph)  # noqa: SLF001 - architecture proof


def test_checker_to_art_public_import_would_close_a_cycle(tmp_path: Path) -> None:
    """A concrete future CHECKERS import of ART public API fails closed."""
    registry_path = tmp_path / "registry.json"
    _registry(registry_path)
    _write(
        tmp_path / "backend/app/modules/artifacts/implementation.py",
        "from app.modules.checkers.api.output_custody import CheckerArtifactOutputPort\n",
    )
    _write(
        tmp_path / "backend/app/modules/checkers/future_execution.py",
        "from app.modules.artifacts.api import SubmissionBundlePreparationCommand\n",
    )
    _, graph, _ = boundary.scan(tmp_path, boundary.load_registry(registry_path))
    assert graph["artifacts"] == {"checkers"}
    assert graph["checkers"] == {"artifacts"}
    with pytest.raises(boundary.ModuleBoundaryError, match="cyclic_public_dependency"):
        boundary._validate_acyclic(graph)  # noqa: SLF001 - architecture proof


def test_general_ledger_rejects_copied_authorization_edges(tmp_path: Path) -> None:
    """AUTH debt remains exclusively owned by the AUTH-003 ledger."""
    document = {
        "schema_version": 1,
        "edges": [
            {
                "source_file": "backend/app/modules/tasks/service.py",
                "target_module": "authorization",
                "imported_private_path": "app.modules.authorization.runtime",
                "repair_owner": "security-triage-required",
            }
        ],
    }
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(boundary.ModuleBoundaryError, match="invalid_ledger_target"):
        boundary.load_ledger(path, boundary.load_registry(REGISTRY))


def test_general_ledger_allows_non_auth_security_triage_owner(tmp_path: Path) -> None:
    """Unresolved authorization-affecting non-AUTH debt can block its capability."""
    document = {
        "schema_version": 1,
        "edges": [
            {
                "source_file": "backend/app/modules/tasks/service.py",
                "target_module": "actors",
                "imported_private_path": "app.modules.actors.models",
                "repair_owner": "security-triage-required",
            }
        ],
    }
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert boundary.load_ledger(path, boundary.load_registry(REGISTRY)) == {
        boundary.PrivateEdge(
            "backend/app/modules/tasks/service.py",
            "actors",
            "app.modules.actors.models",
            "security-triage-required",
        )
    }


def test_initial_ledgers_capture_high_risk_application_edges() -> None:
    """The protected base includes known ART/TASK/wiring boundary debt."""
    general = boundary.load_ledger(LEDGER, boundary.load_registry(REGISTRY))
    actual = {(edge.source_file, edge.imported_private_path) for edge in general}
    assert ("backend/app/api/router.py", "app.modules.tasks.router") in actual
    assert (
        "backend/app/interfaces/artifact_operations.py",
        "app.modules.checkers.pre_submit_execution",
    ) not in actual
    assert not any(
        source == "backend/app/adapters/artifacts/__init__.py"
        and target.startswith("app.modules.artifacts.")
        for source, target in actual
    )
    assert any(
        source.startswith("backend/app/adapters/artifacts/")
        and source != "backend/app/adapters/artifacts/__init__.py"
        and target.startswith("app.modules.artifacts.")
        for source, target in actual
    )
    assert (
        "backend/app/adapters/artifacts/__init__.py",
        "app.modules.actors.models",
    ) not in actual
    assert not any(
        source == "backend/app/workers/project_setup.py"
        and target.startswith("app.modules.projects.")
        for source, target in actual
    )
    auth_inbound, _ = boundary.authorization_boundary.load_ledger(AUTH_LEDGER)
    assert (
        boundary.authorization_boundary.ImportEdge(
            "backend/app/interfaces/artifact_operations.py",
            "app.modules.authorization.prepared",
        )
        in auth_inbound
    )


def test_metadata_discovery_exception_is_exact_and_model_only(tmp_path: Path) -> None:
    """Metadata registration cannot become a generic private capability path."""
    _registry(tmp_path / "registry.json")
    path = tmp_path / "backend/app/db/models.py"
    _write(path, "from app.modules.tasks import models\n")
    registry = boundary.load_registry(tmp_path / "registry.json")
    edges, _, _ = boundary.scan(tmp_path, registry)
    assert not edges
    _write(path, "from app.modules.tasks import repository\n")
    edges, _, _ = boundary.scan(tmp_path, registry)
    assert {edge.imported_private_path for edge in edges} == {"app.modules.tasks.repository"}


@pytest.mark.parametrize("mutation", ("missing", "additional"))
def test_auth_ledger_and_general_view_divergence_fails_closed(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    """A missing or additional AUTH edge cannot disappear between validators."""
    registry = boundary.load_registry(REGISTRY)
    _, _, actual_auth = boundary.scan(ROOT, registry)
    expected = set(actual_auth)
    if mutation == "missing":
        expected.remove(next(iter(expected)))
    else:
        expected.add(
            boundary.authorization_boundary.ImportEdge(
                "backend/app/example.py", "app.modules.authorization.runtime"
            )
        )
    monkeypatch.setattr(boundary.authorization_boundary, "validate", lambda *_: None)
    monkeypatch.setattr(
        boundary.authorization_boundary,
        "load_ledger",
        lambda *_: (expected, set()),
    )
    with pytest.raises(boundary.ModuleBoundaryError, match="authorization_edge_divergence"):
        boundary.validate(ROOT, REGISTRY, LEDGER, AUTH_LEDGER)


def test_authorization_adapter_root_is_present_in_canonical_auth_view(
    tmp_path: Path,
) -> None:
    """Both scanners retain AUTH-private imports from its exact adapter root."""
    _registry(tmp_path / "registry.json")
    source = tmp_path / "backend/app/adapters/authorization/__init__.py"
    _write(source, "import app.modules.authorization.runtime\n")
    registry = boundary.load_registry(tmp_path / "registry.json")

    _, _, actual_auth = boundary.scan(tmp_path, registry)

    assert actual_auth == {
        boundary.authorization_boundary.ImportEdge(
            "backend/app/adapters/authorization/__init__.py",
            "app.modules.authorization.runtime",
        )
    }


def test_exact_auth_adapter_root_uses_owner_parity_without_nested_exception(
    tmp_path: Path,
) -> None:
    """Root wiring is AUTH-owned while nested/private product edges stay visible."""
    _registry(tmp_path / "registry.json")
    _write(
        tmp_path / "backend/app/adapters/auth/__init__.py",
        "import app.modules.authorization.runtime\nimport app.modules.tasks.repository\n",
    )
    nested = "backend/app/adapters/auth/adapter_bindings.py"
    _write(
        tmp_path / nested,
        "import app.modules.authorization.kernel\n",
    )
    registry = boundary.load_registry(tmp_path / "registry.json")

    private, _, actual_auth = boundary.scan(tmp_path, registry)

    assert private == set()
    assert actual_auth == {
        boundary.authorization_boundary.ImportEdge(
            "backend/app/adapters/auth/__init__.py",
            "app.modules.tasks.repository",
        ),
        boundary.authorization_boundary.ImportEdge(
            nested,
            "app.modules.authorization.kernel",
        ),
    }


@pytest.mark.parametrize(
    "source",
    (
        "value = __import__('app.modules.projects.repository')\n",
        "import importlib\nimportlib.import_module('app.modules.projects.repository')\n",
        "exec('from app.modules.projects import repository')\n",
        "import sys\nsys.modules['app.modules.projects.repository']\n",
        "from app.modules.projects.repository import *\n",
    ),
)
def test_dynamic_and_wildcard_imports_fail_repository_wide(tmp_path: Path, source: str) -> None:
    """The general scanner inherits AUTH's fail-closed AST parser."""
    _registry(tmp_path / "registry.json")
    _write(tmp_path / "backend/app/modules/tasks/service.py", source)
    with pytest.raises(AuthorizationBoundaryError):
        boundary.scan(tmp_path, boundary.load_registry(tmp_path / "registry.json"))


def test_policy_public_api_exports_immutable_contracts() -> None:
    from dataclasses import is_dataclass
    import app.modules.contributions.api as policy_api

    public_dataclasses = {
        name: value
        for name in policy_api.__all__
        if is_dataclass(value := getattr(policy_api, name))
    }
    assert public_dataclasses == {
        name: getattr(policy_api, name)
        for name in (
            "ContributionPolicyCreateDraftRequest",
            "ContributionPolicyMutationAuthorizationFacts",
            "ContributionPolicyMutationResult",
            "ContributionPolicyPublishAuthorizationFacts",
            "ContributionPolicyPublishRequest",
            "ContributionPolicyReadRequest",
            "ContributionPolicyProjectReadRequest",
            "ContributionPolicyProjectSelection",
            "ContributionPolicyRetireAuthorizationFacts",
            "ContributionPolicyRetireRequest",
            "ContributionPolicyUpdateDraftRequest",
            "ContributionPolicyValidationFacts",
            "ContributionPolicyValidationRequest",
            "ContributionPolicyView",
            "PolicyDefinitionInput",
            "PolicyDefinitionView",
            "PolicyRuleInput",
            "PolicyRuleView",
            "LockedCompensationAward",
            "LockedCompensationTerms",
            "CompensationUnitCreateAuthorizationFacts",
            "ProjectCompensationUnitCreateRequest",
            "ProjectCompensationUnitCreateResult",
        )
    }
    assert all(value.__dataclass_params__.frozen for value in public_dataclasses.values())


def test_policy_public_api_exports_no_private_persistence_values() -> None:
    import app.modules.contributions.api as policy_api

    exported = set(policy_api.__all__)
    assert not exported & {"AsyncSession", "ContributionPolicyRepository", "Base"}


def test_cp04a_public_policy_api_has_no_private_cross_module_edge() -> None:
    root = Path(__file__).resolve().parents[2] / "app/modules/contributions"
    forbidden = {
        "app.modules.compensation.schemas",
        "app.modules.projects.models",
        "app.modules.projects.repository",
    }
    imported = set().union(
        *(boundary.exact_source_imports(path, ROOT) for path in root.rglob("*.py"))
    )
    assert imported.isdisjoint(forbidden)


def test_policy_uses_public_compensation_instrument_enum_only() -> None:
    from app.modules.compensation.api import CompensationInstrumentType as public_type
    from app.modules.compensation.schemas import CompensationInstrumentType as schema_type

    assert public_type is schema_type


def test_cp04a_uses_only_public_projects_policy_eligibility_port() -> None:
    # The import-aware repository boundary proof above covers direct and
    # package-level imports of both private PROJECTS modules.
    test_cp04a_public_policy_api_has_no_private_cross_module_edge()
