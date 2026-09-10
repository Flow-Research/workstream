"""Explicit unified-worker composition and forbidden direct-finalization proof."""

from pathlib import Path

import pytest

from app.adapters.auth import setup_finalization_authorization
from app.modules.authorization.project_setup_finalization import SetupFinalizationAuthorization
from app.modules.projects.api import ProjectGuideSetupFinalizationError
from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService
from tests.projects.guide_compilation.finalization.support import scenario
from tests.projects.guide_compilation.finalization.test_structure import imports_and_calls

ROOT = Path(__file__).resolve().parents[3]


def assert_no_live_finalization(paths):
    for path in paths:
        imports, calls = imports_and_calls((path,))
        if path == ROOT / "app/workers/project_setup.py":
            assert "setup_finalization_authorization" in imports
            imports.remove("setup_finalization_authorization")
        assert not any("finalization" in name.lower() for name in imports | calls)
        assert "finalize" not in calls


async def test_finalization_authority_is_composed_only_for_unified_delivery():
    paths = tuple((ROOT / "app/modules").rglob("router.py")) + tuple(
        (ROOT / "app/workers").rglob("*.py")
    )
    assert paths
    assert_no_live_finalization(paths)
    case = scenario()
    adapter = setup_finalization_authorization(case.session)
    assert type(adapter) is SetupFinalizationAuthorization
    assert adapter._session is case.session
    service = GuideCompilationFinalizationService(case.session)
    service._repository = case.repo
    with pytest.raises(ProjectGuideSetupFinalizationError, match="service_authority_denied"):
        await service.finalize(case.command)
    assert case.repo.calls == ["lookup"]


@pytest.mark.parametrize(
    "source",
    [
        "from app.adapters.auth import setup_finalization_authorization as ordinary\nordinary(session)\n",
        "authority.prepare_setup_finalization(locator)\n",
    ],
)
def test_reachability_proof_rejects_injected_factory_or_call(tmp_path, source):
    path = tmp_path / "worker.py"
    path.write_text(source)
    with pytest.raises(AssertionError):
        assert_no_live_finalization((path,))


def test_authorization_owner_has_no_product_storage_or_provider_imports():
    paths = (
        ROOT / "app/modules/authorization/project_setup_finalization.py",
        ROOT / "app/modules/authorization/domain/project_setup_finalization.py",
    )
    imports, calls = imports_and_calls(paths)
    assert not any(
        name.startswith(
            (
                "app.modules.projects",
                "app.adapters.project_agents",
                "openai",
                "agents",
                "app.workers",
            )
        )
        for name in imports
    )
    assert calls.isdisjoint(
        {
            "commit",
            "begin",
            "compile_project_guide",
            "project_guide_sufficiency",
            "project_submission_artifact_policy",
        }
    )


def test_finalization_partition_additions_are_exact_and_fail_closed():
    """Register four exact owners without granting arbitrary partition additions."""
    from scripts import behavior_ownership as ownership
    from tests.test_behavior_ownership import _partition

    expected = {
        "backend/app/modules/authorization/domain/audit_targets.py",
        "backend/app/modules/authorization/domain/project_setup_finalization.py",
        "backend/app/modules/authorization/domain/resource_digest.py",
        "backend/app/modules/authorization/project_setup_finalization.py",
    }
    assert ownership.AUTH_12B2_TARGETS == expected
    retained = "backend/app/core/config.py"
    trusted = _partition([retained])
    ownership._validate_additive_partition_transition(
        _partition(sorted({retained, *expected})), trusted
    )
    with pytest.raises(ownership.BehaviorOwnershipError, match="untrusted_partition_change"):
        ownership._validate_additive_partition_transition(
            _partition(sorted({retained, *expected, "backend/app/modules/authorization/extra.py"})),
            trusted,
        )


@pytest.mark.parametrize(
    "source",
    [
        "from app.adapters.auth import setup_finalization_authorization as ordinary\nordinary(session)\n",
        "import app.adapters.auth as auth\nauth.setup_finalization_authorization(session)\n",
        "from app.adapters.auth import setup_finalization_authorization\nordinary = setup_finalization_authorization\nordinary(session)\n",
        "from app.adapters.auth import setup_finalization_authorization\nordinary: object = setup_finalization_authorization\nordinary(session)\n",
    ],
)
def test_exact_worker_cannot_call_aliased_finalization_factory(tmp_path, monkeypatch, source):
    import sys

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    path = tmp_path / "app/workers/project_setup.py"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    with pytest.raises(AssertionError):
        assert_no_live_finalization((path,))
