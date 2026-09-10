"""Warning acknowledgement provenance and setup continuation guards."""

from uuid import UUID

import pytest

from app.modules.projects import sufficiency_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.sufficiency_mutations import rows
from projects.sufficiency_mutations.commands import invoke
from projects.sufficiency_mutations.fixtures import case as case


@pytest.mark.parametrize("scope,scope_type", [(rows.PROJECT, "project"), (None, "system")])
async def test_acknowledgement_stages_exact_provenance(case, scope, scope_type):
    case.decision.matched_scope_project_id = scope
    outcome = await invoke(case, "ack")
    report = case.report
    assert outcome.replayed is False
    assert (report.warnings_acknowledged_by_role, report.warnings_acknowledged_by_actor) == (
        "project_manager",
        str(rows.ACTOR),
    )
    assert (
        report.warnings_acknowledged_by_actor_profile_id,
        report.warnings_acknowledged_via_identity_link_id,
    ) == (
        str(rows.ACTOR),
        str(rows.LINK),
    )
    assert report.warnings_acknowledged_by_admin_role_grant_id == rows.GRANT
    assert (
        report.warning_acknowledgement_scope_type,
        report.warning_acknowledgement_scope_project_id,
    ) == (
        scope_type,
        str(rows.PROJECT),
    )
    assert (
        report.warning_acknowledgement_action_id == "project.guide_sufficiency.warnings.acknowledge"
    )
    assert report.warning_acknowledgement_decision_event_id == str(case.decision.decision_id)
    assert report.acknowledgement_note == "Understood"
    assert report.warnings_acknowledged_at is not None
    assert outcome.response.warnings_acknowledged_at == report.warnings_acknowledged_at
    case.replay.complete.assert_awaited_once_with(
        case.reservation,
        response_json=outcome.response.model_dump(mode="json"),
        report_id=str(rows.REPORT),
    )


@pytest.mark.parametrize(
    "fault,error,match",
    [
        ("missing", module.SufficiencyReportNotFound, "not found"),
        ("project_id", module.SufficiencyReportNotFound, "not found"),
        ("guide_id", module.SufficiencyReportNotFound, "not found"),
        ("missing_locked", module.SufficiencyReportNotFound, "not found"),
        (
            "source_snapshot_hash",
            module.GuideSufficiencyMutationConflict,
            "sufficiency_lineage_stale",
        ),
        ("status", module.PolicySetupBlocked, "only sufficiency warnings"),
    ],
)
async def test_acknowledgement_rejects_invalid_report(case, fault, error, match):
    if fault == "missing":
        case.projects.get_guide_sufficiency_report.return_value = None
    elif fault == "missing_locked":
        case.projects.lock_guide_sufficiency_report.return_value = None
    else:
        setattr(case.report, fault, "passed" if fault == "status" else str(UUID(int=99)))
    with pytest.raises(error, match=match):
        await invoke(case, "ack")
    case.prepared.consume.assert_not_awaited()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    assert case.report.warnings_acknowledged_at is None


async def test_acknowledgement_rejects_repeat(case):
    case.report.warnings_acknowledged_at = rows.NOW
    with pytest.raises(module.GuideSufficiencyMutationConflict, match="already_acknowledged"):
        await invoke(case, "ack")
    assert case.report.warnings_acknowledged_at == rows.NOW
    case.prepared.consume.assert_awaited_once()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()


@pytest.mark.parametrize(
    "fault",
    [
        "id",
        "output_sufficiency_report_id",
        "output_submission_artifact_policy_id",
    ],
)
async def test_acknowledgement_rejects_invalid_continuation(case, fault):
    case.report.project_setup_run_id = str(rows.SETUP)
    case.report.setup_generation = 1
    case.setup.output_sufficiency_report_id = str(rows.REPORT)
    setattr(case.setup, fault, str(UUID(int=99)))
    if fault == "id":
        case.report.project_setup_run_id = case.setup.id
    before = vars(case.setup).copy()
    with pytest.raises(
        module.GuideSufficiencyMutationConflict, match="project_setup_run_context_mismatch"
    ):
        await invoke(case, "ack")
    case.prepared.consume.assert_awaited_once()
    case.projects.lock_project_setup_run.assert_awaited_once_with(case.report.project_setup_run_id)
    assert vars(case.setup) == before
    case.replay.complete.assert_not_awaited()
    # Transaction rollback is proved separately in test_acknowledgement_postgresql.py.


async def test_acknowledgement_rejects_report_generation_mismatch(case):
    case.report.project_setup_run_id = str(rows.SETUP)
    case.report.setup_generation = 2
    case.setup.output_sufficiency_report_id = str(rows.REPORT)
    before = vars(case.setup).copy()
    with pytest.raises(
        module.GuideSufficiencyMutationConflict, match="project_setup_run_context_mismatch"
    ):
        await invoke(case, "ack")
    assert vars(case.setup) == before
    case.replay.complete.assert_not_awaited()


async def test_acknowledgement_preserves_setup_without_restart(case):
    case.report.project_setup_run_id = str(rows.SETUP)
    case.report.setup_generation = 1
    case.setup.output_sufficiency_report_id = str(rows.REPORT)
    before = vars(case.setup).copy()
    outcome = await invoke(case, "ack")
    assert vars(case.setup) == before
    case.projects.lock_project_setup_run.assert_awaited_once_with(str(rows.SETUP))
    case.replay.complete.assert_awaited_once_with(
        case.reservation,
        response_json=outcome.response.model_dump(mode="json"),
        report_id=str(rows.REPORT),
    )
