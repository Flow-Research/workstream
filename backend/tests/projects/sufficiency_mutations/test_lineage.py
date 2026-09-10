"""Fresh lineage and setup custody cases isolate one invalid owner fact each."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.projects import sufficiency_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.sufficiency_mutations import rows
from projects.sufficiency_mutations.fixtures import case as case


def install_rows(case):
    guide = SimpleNamespace(
        id=str(rows.GUIDE), project_id=str(rows.PROJECT), version="v1", status="draft"
    )
    snapshot = SimpleNamespace(
        id=str(rows.SNAPSHOT), bundle_hash=rows.SNAPSHOT_HASH, creation_generation=1
    )
    for name, value in (
        ("get_guide", guide),
        ("lock_project_guide", guide),
        ("get_latest_guide_source_snapshot", snapshot),
        ("lock_latest_guide_source_snapshot", snapshot),
        ("get_latest_project_setup_run", case.setup),
        ("lock_latest_project_setup_run", case.setup),
    ):
        setattr(case.projects, name, AsyncMock(return_value=value))
    case.service._validation = SimpleNamespace(validate_source_snapshot_integrity=AsyncMock())
    return guide, snapshot


@pytest.mark.parametrize(
    "fault,error,match",
    [
        ("missing_guide", module.GuideNotFound, "not found"),
        ("foreign_guide", module.GuideNotFound, "not found"),
        ("active_guide", module.GuideEditBlocked, "only draft"),
        ("missing_snapshot", module.PolicySetupConflict, "snapshot is stale"),
        ("replaced_snapshot", module.PolicySetupConflict, "snapshot is stale"),
        ("ambiguous_snapshot", module.PolicySetupBlocked, "snapshot is ambiguous"),
        ("guide_version", module.PolicySetupConflict, "context mismatch"),
        ("source_snapshot_id", module.PolicySetupConflict, "context mismatch"),
        ("source_snapshot_hash", module.PolicySetupConflict, "context mismatch"),
        ("required_setup", module.PolicySetupConflict, "context mismatch"),
        ("missing_generation", module.PolicySetupConflict, "context mismatch"),
    ],
)
async def test_lineage_rejects_invalid_context(case, fault, error, match):
    guide, snapshot = install_rows(case)
    if fault == "missing_guide":
        case.projects.get_guide.return_value = None
    elif fault == "foreign_guide":
        guide.project_id = str(UUID(int=99))
    elif fault == "active_guide":
        guide.status = "active"
    elif fault == "missing_snapshot":
        case.projects.get_latest_guide_source_snapshot.return_value = None
    elif fault == "replaced_snapshot":
        snapshot.id = str(UUID(int=99))
    elif fault == "ambiguous_snapshot":
        case.projects.get_latest_guide_source_snapshot.side_effect = (
            module.ProjectRepositoryIntegrityError("ambiguous")
        )
    elif fault == "required_setup":
        case.projects.get_latest_project_setup_run.return_value = None
    elif fault == "missing_generation":
        case.projects.get_latest_project_setup_run.return_value = None
        snapshot.creation_generation = None
    else:
        setattr(case.setup, fault, "different")
    with pytest.raises(error, match=match):
        await case.actual_lineage(
            rows.PROJECT,
            rows.GUIDE,
            rows.SNAPSHOT,
            lock=False,
            require_setup_run=fault != "missing_generation",
        )


@pytest.mark.parametrize("lock", [False, True])
async def test_lineage_resolves_exact_context(case, lock):
    _, snapshot = install_rows(case)
    result = await case.actual_lineage(rows.PROJECT, rows.GUIDE, rows.SNAPSHOT, lock=lock)
    assert result == module._Lineage(
        "v1",
        rows.SNAPSHOT,
        rows.SNAPSHOT_HASH,
        1,
        rows.SETUP,
        canonical_json_hash(
            {
                "domain": "workstream.project_setup.sufficiency_stale_output.v1",
                "setup_run_id": str(rows.SETUP),
                "setup_generation": 1,
                "current_step": "guide_sufficiency",
                "output_sufficiency_report_id": None,
            }
        ),
    )
    selectors = (
        ("lock_project_guide", "get_guide", (str(rows.GUIDE),)),
        (
            "lock_latest_guide_source_snapshot",
            "get_latest_guide_source_snapshot",
            (str(rows.PROJECT), str(rows.GUIDE), "v1"),
        ),
        (
            "lock_latest_project_setup_run",
            "get_latest_project_setup_run",
            (str(rows.PROJECT), str(rows.GUIDE), "v1")
            if lock
            else (str(rows.PROJECT), str(rows.GUIDE)),
        ),
    )
    for locked, unlocked, args in selectors:
        getattr(case.projects, locked if lock else unlocked).assert_awaited_once_with(*args)
        getattr(case.projects, unlocked if lock else locked).assert_not_awaited()
    case.service._validation.validate_source_snapshot_integrity.assert_awaited_once_with(
        snapshot, module.PolicySetupBlocked
    )


def custody_arguments(case):
    case.setup.status = "queued"
    return dict(
        project_id=rows.PROJECT,
        guide_id=rows.GUIDE,
        source_snapshot_id=rows.SNAPSHOT,
        setup_run_id=rows.SETUP,
        setup_generation=1,
        task_id=UUID(case.setup.celery_task_id),
        correlation_id=UUID(int=21),
    )
