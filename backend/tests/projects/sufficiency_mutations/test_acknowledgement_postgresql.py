"""Real acknowledgement failure custody; executed on hosted PostgreSQL."""

from unittest.mock import AsyncMock
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import func, select

from app.db import session as db_session
from app.modules.projects import setup_queue
from app.modules.projects.models import (
    GuideSufficiencyMutationIdempotencyRecord,
    GuideSufficiencyReport,
    ProjectSetupRun,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.tasks.models import AuditEvent
from projects.client_fixtures import (
    auth_headers,
    project_client as project_client,
    project_database_env as project_database_env,
)
from projects.guide_fixtures import (
    complete_guide_payload,
    create_guide,
    create_project,
    create_source_snapshot,
)
from projects.submission_policy_fixtures import create_sufficiency_report
from committed_guide_fixtures import create_compiled_report_fixture


ACK_ACTION = "project.guide_sufficiency.warnings.acknowledge"


async def transaction_state(session, report_id, project_id, key):
    """Read stored columns, not identity-map values, at the transaction boundary."""
    report = (
        (
            await session.execute(
                select(GuideSufficiencyReport.__table__).where(
                    GuideSufficiencyReport.id == report_id
                )
            )
        )
        .mappings()
        .one()
    )
    setup = (
        (
            await session.execute(
                select(ProjectSetupRun.__table__).where(
                    ProjectSetupRun.id == report["project_setup_run_id"]
                )
            )
        )
        .mappings()
        .one()
    )
    replay = await session.scalar(
        select(func.count())
        .select_from(GuideSufficiencyMutationIdempotencyRecord)
        .where(
            GuideSufficiencyMutationIdempotencyRecord.project_id == project_id,
            GuideSufficiencyMutationIdempotencyRecord.idempotency_key == key,
            GuideSufficiencyMutationIdempotencyRecord.action_id == ACK_ACTION,
        )
    )
    allowed = await session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action_id == ACK_ACTION,
            AuditEvent.event_type == "SensitiveAuthorizationAllowed",
            AuditEvent.target_ref_id == project_id,
        )
    )
    return dict(report), dict(setup), replay, allowed


async def test_acknowledgement_late_conflict_rolls_back(project_client, monkeypatch):
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    diagnostic = await create_sufficiency_report(
        project_client,
        project["id"],
        guide["id"],
        snapshot["id"],
        status="passed_with_warnings",
    )
    report_id = await create_compiled_report_fixture(diagnostic["id"], snapshot["id"])
    headers = auth_headers()
    key = UUID(headers["Idempotency-Key"])
    factory = db_session.get_session_factory()
    async with factory() as session:
        before = await transaction_state(session, report_id, project["id"], key)
    assert before[0]["warnings_acknowledged_at"] is None
    assert before[0]["setup_generation"] == before[1]["setup_generation"]
    original_lock = ProjectRepository.lock_project_setup_run
    observed = []

    async def observe_staged_effects(repository, setup_run_id):
        setup = await original_lock(repository, setup_run_id)
        staged = await transaction_state(repository._session, report_id, project["id"], key)
        assert staged[0]["warnings_acknowledged_at"] is not None
        assert staged[0]["warning_acknowledgement_decision_event_id"] is not None
        assert staged[1] == before[1]
        assert staged[2:] == (before[2] + 1, before[3] + 1)
        observed.append(setup_run_id)
        # The report is immutable. Inject a conflicting locked-setup read at
        # the late boundary instead of corrupting retained report evidence.
        return SimpleNamespace(
            id=setup.id, setup_generation=setup.setup_generation + 1,
            output_sufficiency_report_id=setup.output_sufficiency_report_id,
            output_submission_artifact_policy_id=setup.output_submission_artifact_policy_id,
        )

    dispatch = AsyncMock(side_effect=AssertionError("denied acknowledgement dispatched work"))
    monkeypatch.setattr(ProjectRepository, "lock_project_setup_run", observe_staged_effects)
    monkeypatch.setattr(setup_queue, "dispatch_project_guide_compilation_after_commit", dispatch)
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/sufficiency-reports/"
        f"{report_id}/acknowledge-warnings",
        headers=headers,
        json={"acknowledgement_note": "Understood"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "project_setup_run_context_mismatch"
    assert observed == [before[0]["project_setup_run_id"]]
    dispatch.assert_not_awaited()
    async with factory() as session:
        assert await transaction_state(session, report_id, project["id"], key) == before
