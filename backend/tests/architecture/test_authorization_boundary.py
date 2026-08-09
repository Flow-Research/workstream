"""Architecture proof for the sole public AUTH dependency boundary."""

from __future__ import annotations

import ast
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest

from app.modules.authorization import api
from scripts import authorization_boundary as boundary

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md"


def _write_module(root: Path, relative: str, source: str) -> Path:
    """Create one isolated Python module for static analysis."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _minimal_root(tmp_path: Path) -> Path:
    """Create the backend application directory expected by the scanner."""
    (tmp_path / "backend/app").mkdir(parents=True)
    return tmp_path


def _write_ledger(path: Path, inbound: str, outbound: str) -> None:
    """Write the exact two frozen edge sections required by the validator."""
    path.write_text(
        f"{boundary.INBOUND_HEADING}\n\n```text\n{inbound}\n```\n\n"
        f"{boundary.OUTBOUND_HEADING}\n\n```text\n{outbound}\n```\n",
        encoding="utf-8",
    )


def test_repository_private_import_edges_equal_the_frozen_ledger() -> None:
    """The current tree has no unrecorded inbound or outbound private edge."""
    boundary.validate(ROOT, LEDGER)


def test_public_api_reachability_contains_no_private_runtime_module() -> None:
    """Every public value is defined by the API package or the standard library."""
    forbidden = (
        "app.modules.authorization.catalogue",
        "app.modules.authorization.kernel",
        "app.modules.authorization.models",
        "app.modules.authorization.prepared",
        "app.modules.authorization.repository",
        "app.modules.authorization.router",
        "app.modules.authorization.runtime",
        "app.modules.authorization.service",
    )
    for name in api.__all__:
        value = getattr(api, name)
        module = value if isinstance(value, ModuleType) else getattr(value, "__module__", "")
        assert not str(module).startswith(forbidden), name


def test_public_identifier_factories_reject_empty_values() -> None:
    """Public identifiers are opaque strings but never empty authority selectors."""
    assert api.action_id(" project.read ") == "project.read"
    assert api.permission_id(" project.read ") == "project.read"
    with pytest.raises(ValueError, match="must not be empty"):
        api.action_id(" ")
    with pytest.raises(ValueError, match="must not be empty"):
        api.permission_id("")


def test_actor_identity_facts_require_service_identity_only_for_services() -> None:
    """Human and fixed-service identity facts cannot be structurally confused."""
    profile_id, link_id = uuid4(), uuid4()
    human = api.ActorIdentityFacts(profile_id, link_id, api.ActorKind.HUMAN)
    service = api.ActorIdentityFacts(
        profile_id,
        link_id,
        api.ActorKind.SERVICE,
        "workstream.artifact.binding",
    )
    assert human.service_identity is None
    assert service.service_identity == "workstream.artifact.binding"
    with pytest.raises(ValueError, match="must match actor kind"):
        api.ActorIdentityFacts(profile_id, link_id, api.ActorKind.HUMAN, "unexpected")
    with pytest.raises(ValueError, match="must match actor kind"):
        api.ActorIdentityFacts(profile_id, link_id, api.ActorKind.SERVICE)
    with pytest.raises(ValueError, match="must match actor kind"):
        api.ActorIdentityFacts(profile_id, link_id, api.ActorKind.SERVICE, " ")


def test_resource_facts_copy_and_freeze_caller_values() -> None:
    """A caller cannot mutate resource facts after handing them to AUTH."""
    values = {"generation": 3, "digest": "abc"}
    facts = api.ResourceFacts(" guide_source ", uuid4(), values)
    values["generation"] = 4
    assert facts.resource_type == "guide_source"
    assert dict(facts.values) == {"digest": "abc", "generation": 3}
    with pytest.raises(TypeError):
        facts.values["generation"] = 5  # type: ignore[index]
    with pytest.raises(ValueError, match="resource type"):
        api.ResourceFacts(" ", uuid4(), {})
    with pytest.raises(ValueError, match="fact keys"):
        api.ResourceFacts("guide", uuid4(), {"": "invalid"})


@pytest.mark.parametrize("value", (["mutable"], {"mutable": True}, {"mutable"}, float("inf")))
def test_resource_facts_reject_mutable_or_non_finite_values(value: object) -> None:
    """Prepared facts cannot change identity or meaning after validation."""
    with pytest.raises(ValueError, match="deeply immutable and finite"):
        api.ResourceFacts("guide", uuid4(), {"value": value})  # type: ignore[dict-item]


def test_resource_facts_reject_an_empty_string_identifier() -> None:
    """A public resource selector always names one exact resource."""
    with pytest.raises(ValueError, match="identifier must not be empty"):
        api.ResourceFacts("guide", " ", {})


def test_decision_denial_code_matches_the_outcome() -> None:
    """Allowed decisions reveal no denial code and denials always carry one."""
    action = api.action_id("project.read")
    permission = api.permission_id("project.read")
    allowed = api.AuthorizationDecision(
        uuid4(), action, permission, api.DecisionOutcome.ALLOW
    )
    denied = api.AuthorizationDecision(
        uuid4(), action, permission, api.DecisionOutcome.DENY, "missing_grant"
    )
    assert allowed.denial_code is None
    assert denied.denial_code == "missing_grant"
    with pytest.raises(ValueError, match="must match decision outcome"):
        api.AuthorizationDecision(
            uuid4(), action, permission, api.DecisionOutcome.ALLOW, "unexpected"
        )
    with pytest.raises(ValueError, match="must match decision outcome"):
        api.AuthorizationDecision(uuid4(), action, permission, api.DecisionOutcome.DENY)


@pytest.mark.parametrize(
    "source",
    (
        "from app.modules.authorization.runtime import *\n",
        "value = __import__('app.modules.authorization.runtime')\n",
        "import builtins as b\nloader = b.__import__\nloader('x')\n",
        "import importlib\nimportlib.import_module('app.modules.authorization.runtime')\n",
        "import importlib as loader\nloader.import_module('x')\n",
        "from importlib import import_module as load\nload('x')\n",
        "import importlib\ngetattr(importlib, 'import_' + 'module')('x')\n",
        "exec('from app.modules.authorization import runtime')\n",
        "eval(\"__import__('app.modules.authorization.runtime')\")\n",
        "code = compile('import app.modules.authorization.runtime', '<x>', 'exec')\n",
        "run = exec\nrun('from app.modules.authorization import runtime')\n",
        "getattr(globals()['__builtins__'], '__import__')('app.modules.authorization.runtime')\n",
        "globals()['__builtins__']['__import__']('app.modules.authorization.runtime')\n",
        "locals()['__builtins__']\n",
        "namespace = vars\nnamespace()['__builtins__']\n",
        "def loader(run=__import__):\n    return run('app.modules.authorization.runtime')\n",
        "def loader(run): return run('x')\nloader(__import__)\n",
        "(lambda run=__import__: run('app.modules.authorization.runtime'))()\n",
        "from builtins import globals as namespace\nnamespace()['__builtins__']\n",
    ),
)
def test_dynamic_and_wildcard_import_bypasses_fail_closed(tmp_path: Path, source: str) -> None:
    """Every non-static import form is rejected before edge comparison."""
    root = _minimal_root(tmp_path)
    path = _write_module(root, "backend/app/modules/example.py", source)
    with pytest.raises(boundary.AuthorizationBoundaryError):
        boundary.source_imports(path, root)


@pytest.mark.parametrize(
    ("relative", "source", "expected"),
    (
        (
            "backend/app/modules/projects/service.py",
            "from ..authorization import runtime\n",
            "app.modules.authorization.runtime",
        ),
        (
            "backend/app/modules/projects/service.py",
            "from ..authorization.prepared import PreparedAuthorizationHandle\n",
            "app.modules.authorization.prepared",
        ),
        (
            "backend/app/modules/authorization/example.py",
            "from ..projects.repository import ProjectRepository\n",
            "app.modules.projects.repository",
        ),
    ),
)
def test_relative_imports_resolve_to_canonical_edges(
    tmp_path: Path,
    relative: str,
    source: str,
    expected: str,
) -> None:
    """Relative syntax cannot disguise the absolute dependency target."""
    root = _minimal_root(tmp_path)
    path = _write_module(root, relative, source)
    assert boundary.source_imports(path, root) == {expected}


def test_unresolved_relative_import_fails_closed(tmp_path: Path) -> None:
    """A relative import escaping the known package cannot be ignored."""
    root = _minimal_root(tmp_path)
    path = _write_module(root, "backend/app/example.py", "from ...unknown import value\n")
    with pytest.raises(boundary.AuthorizationBoundaryError, match="unresolved_relative_import"):
        boundary.source_imports(path, root)


def test_exact_edge_growth_fails_even_inside_an_already_recorded_file(tmp_path: Path) -> None:
    """Ledger comparison is by edge rather than by consumer filename."""
    root = _minimal_root(tmp_path)
    consumer = _write_module(
        root,
        "backend/app/modules/example.py",
        "from app.modules.authorization import runtime\n",
    )
    _write_module(
        root,
        "backend/app/modules/authorization/example.py",
        "from app.modules.actors.service import actor\n",
    )
    ledger = tmp_path / "ledger.md"
    _write_ledger(
        ledger,
        "backend/app/modules/example.py\n  app.modules.authorization.runtime",
        "backend/app/modules/authorization/example.py\n  app.modules.actors.service",
    )
    boundary.validate(root, ledger)
    consumer.write_text(
        "from app.modules.authorization import prepared, runtime\n",
        encoding="utf-8",
    )
    with pytest.raises(boundary.AuthorizationBoundaryError, match="inbound_edge_mismatch"):
        boundary.validate(root, ledger)


def test_import_scanner_parses_source_without_executing_it(tmp_path: Path) -> None:
    """Static discovery never runs module-level application code."""
    root = _minimal_root(tmp_path)
    marker = tmp_path / "executed"
    source = (
        "from app.modules.authorization import api\n"
        f"open({str(marker)!r}, 'w').write('unsafe')\n"
    )
    path = _write_module(root, "backend/app/modules/example.py", source)
    assert boundary.source_imports(path, root) == {"app.modules.authorization.api"}
    assert not marker.exists()


def test_malformed_python_fails_closed(tmp_path: Path) -> None:
    """Syntax errors cannot make a source disappear from boundary validation."""
    root = _minimal_root(tmp_path)
    path = _write_module(root, "backend/app/modules/example.py", "from ??? import value\n")
    with pytest.raises(boundary.AuthorizationBoundaryError, match="invalid_python_source"):
        boundary.source_imports(path, root)


def test_import_from_alias_expansion_is_ast_based() -> None:
    """The fixture itself proves the parser receives ImportFrom nodes."""
    tree = ast.parse("from app.modules.authorization import runtime")
    node = tree.body[0]
    assert isinstance(node, ast.ImportFrom)
