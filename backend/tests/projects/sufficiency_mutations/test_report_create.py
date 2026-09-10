"""Human report composition and pre-effect guards through controlled ports."""

from dataclasses import replace

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.projects import sufficiency_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.sufficiency_mutations import rows
from projects.sufficiency_mutations.commands import invoke
from projects.sufficiency_mutations.fixtures import case as case


@pytest.mark.parametrize("scope,scope_type", [(rows.PROJECT, "project"), (None, "system")])
async def test_create_stages_human_report(case, scope, scope_type):
    case.decision.matched_scope_project_id = scope
    outcome = await invoke(case, "create")
    report = case.projects.add_guide_sufficiency_report.await_args.args[0]
    assert (outcome.created, outcome.replayed) == (True, False)
    assert (report.project_id, report.guide_id, report.guide_version) == (
        str(rows.PROJECT),
        str(rows.GUIDE),
        "v1",
    )
    assert (report.source_snapshot_id, report.source_snapshot_hash) == (
        str(rows.SNAPSHOT),
        rows.SNAPSHOT_HASH,
    )
    assert (report.status, report.findings, report.summary) == ("passed", [], "Assessment")
    assert (
        report.created_by,
        report.created_by_actor_profile_id,
        report.created_via_identity_link_id,
    ) == (
        str(rows.ACTOR),
        str(rows.ACTOR),
        str(rows.LINK),
    )
    assert report.created_by_admin_role_grant_id == rows.GRANT
    assert (report.creation_scope_type, report.creation_scope_project_id) == (
        scope_type,
        str(rows.PROJECT),
    )
    assert report.creation_action_id == "project.guide_sufficiency_report.create"
    assert report.authorization_decision_event_id == str(case.decision.decision_id)
    case.replay.complete.assert_awaited_once_with(
        case.reservation,
        response_json=outcome.response.model_dump(mode="json"),
        report_id=report.id,
    )
    case.session.commit.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "ack"])
async def test_mutation_rejects_changed_locked_lineage(case, command):
    case.service._lineage.side_effect = [case.lineage, replace(case.lineage, setup_generation=2)]
    with pytest.raises(module.GuideSufficiencyMutationConflict, match="sufficiency_lineage_stale"):
        await invoke(case, command)
    case.prepared.consume.assert_not_awaited()
    case.projects.add_guide_sufficiency_report.assert_not_awaited()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    assert case.report.warnings_acknowledged_at is None
    assert case.setup.status == "enqueue_failed"


@pytest.mark.parametrize("command", ["create", "ack"])
async def test_mutation_consume_failure_has_no_product_effect(case, command):
    failure = RuntimeError("consume denied")

    async def deny(*_):
        case.projects.add_guide_sufficiency_report.assert_not_awaited()
        case.replay.reserve.assert_not_awaited()
        assert case.report.warnings_acknowledged_at is None
        assert case.setup.status == "enqueue_failed"
        raise failure

    case.prepared.consume.side_effect = deny
    with pytest.raises(RuntimeError) as observed:
        await invoke(case, command)
    assert observed.value is failure
    case.prepared.consume.assert_awaited_once()
    case.projects.add_guide_sufficiency_report.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    assert case.report.warnings_acknowledged_at is None
    assert case.setup.status == "enqueue_failed"


async def test_create_rejects_existing_report(case):
    case.projects.get_sufficiency_report_for_snapshot.return_value = case.report
    with pytest.raises(
        module.GuideSufficiencyMutationConflict, match="sufficiency_report_already_exists"
    ):
        await invoke(case, "create")
    case.prepared.consume.assert_awaited_once()
    case.replay.reserve.assert_not_awaited()
    case.projects.add_guide_sufficiency_report.assert_not_awaited()


async def test_create_conceals_insert_conflict(case):
    case.projects.add_guide_sufficiency_report.side_effect = IntegrityError(
        "insert", {}, Exception("race")
    )
    with pytest.raises(
        module.GuideSufficiencyMutationConflict, match="sufficiency_report_already_exists"
    ):
        await invoke(case, "create")
    case.prepared.consume.assert_awaited_once()
    case.projects.add_guide_sufficiency_report.assert_awaited_once()
    case.replay.complete.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "ack"])
@pytest.mark.parametrize("disposition", ["pending", "mismatch", "replayed"])
async def test_mutation_requires_claimed_reservation(case, command, disposition):
    case.replay.reserve.return_value = disposition, case.reservation
    with pytest.raises(module.GuideSufficiencyMutationConflict, match=f"idempotency_{disposition}"):
        await invoke(case, command)
    case.replay.reserve.assert_awaited_once()
    case.projects.add_guide_sufficiency_report.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    assert case.report.warnings_acknowledged_at is None
    assert case.setup.status == "enqueue_failed"
