"""A Submitter reads their own claim, attempt, preparation and totals through public routes."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from sqlalchemy import select

from app.db import session as db_session
from app.modules.artifacts.preparation_reads import SubmissionBundlePreparationReader
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256, WORKSTREAM_DEFAULT_CHECK_IDS, WorkstreamDefaultCheckerResult,
)
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitExecutionFacts, SelectedPreSubmitRunView
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.compensation.api.award_reads import ContributorAwardTotal
from app.modules.compensation.awards.read_repository import ContributionAwardReadRepository
from tests.submission_fixtures import route_retained_checker_remediation, seed_retained_checker_run
from tests.test_tasks import set_dev_actor
from .support import ME, OWNER, as_actor, get_ok, preparations_path, submitted_case


def _present(view):
    return {name: value for name, value in view.items() if value is not None}


async def test_projects_list_exact_grant_roles_and_active_guide(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    await as_actor(task_client, monkeypatch, OWNER)
    page = await get_ok(task_client, f"{ME}/projects")
    assert page["next_cursor"] is None
    [item] = page["items"]
    assert item["project_id"] == project and item["status"] == "active"
    assert item["project_roles"] == ["submitter"] and item["admin_roles"] == []
    assert item["active_guide"]["version"] == "v1"


async def test_assignment_projects_claim_submission_and_next_action(task_client, monkeypatch):
    project, task, submission = await submitted_case(task_client, monkeypatch)
    await as_actor(task_client, monkeypatch, OWNER)
    [item] = (await get_ok(task_client, f"{ME}/assignments"))["items"]
    assert (item["project_id"], item["task_id"], item["state"]) == (project, task, "active")
    assert item["assignment_status"] == "active" and item["task_status"] == "evaluation_pending"
    assert item["started_at"] is not None and item["locked_guide_version"] == "v1"
    assert item["latest_submission"]["submission_id"] == submission
    assert item["latest_submission"]["status"] == "evaluation_pending"
    assert item["next_action"] == "awaiting_evaluation" and item["revision"] is None
    assert item["compensation"]["contribution_policy_version_id"]


async def test_assignment_revision_fields_equal_work_context(task_client, monkeypatch):
    _project, task, submission = await submitted_case(task_client, monkeypatch)
    await route_retained_checker_remediation(submission, generation=2)
    await as_actor(task_client, monkeypatch, OWNER)
    context = (await get_ok(task_client, f"/api/v1/tasks/{task}/work-context"))["revision_context"]
    [item] = (await get_ok(task_client, f"{ME}/assignments"))["items"]
    # The work-context route omits null fields; the values are the same projection.
    assert _present(item["revision"]) == _present(context)
    assert item["task_status"] == "needs_revision"
    assert item["next_action"] == ("revise" if context["disposition"] == "ready" else "none")


async def test_submission_list_carries_stored_outcome_and_finding_counts(task_client, monkeypatch):
    project, task, submission = await submitted_case(task_client, monkeypatch)
    await route_retained_checker_remediation(submission, generation=2)
    await as_actor(task_client, monkeypatch, OWNER)
    [item] = (await get_ok(task_client, f"{ME}/submissions"))["items"]
    assert (item["submission_id"], item["project_id"], item["task_id"]) == (submission, project, task)
    assert item["status"] == "needs_revision" and item["decided_at"] is not None
    assert item["finding_counts"]["blocking"] >= 1
    history = await get_ok(task_client, f"/api/v1/submissions/{submission}")
    assert item["finding_counts"] == history["finding_counts"]


async def test_incremental_submission_read_sees_findings_committed_before_routing(task_client, monkeypatch):
    _project, _task, submission = await submitted_case(task_client, monkeypatch)
    await as_actor(task_client, monkeypatch, OWNER)
    [before] = (await get_ok(task_client, f"{ME}/submissions"))["items"]
    since = (datetime.fromisoformat(before["updated_at"]) + timedelta(microseconds=1)).isoformat()
    assert (await get_ok(task_client, f"{ME}/submissions", updated_since=since))["items"] == []
    # A retry's failed run commits its findings; TASK routing has not restamped the submission.
    await seed_retained_checker_run(submission, verdict="failed", generation=2)
    [after] = (await get_ok(task_client, f"{ME}/submissions", updated_since=since))["items"]
    assert after["submission_id"] == submission and after["status"] == "evaluation_pending"
    assert after["finding_counts"]["blocking"] >= 1 > before["finding_counts"]["blocking"]
    assert after["updated_at"] >= since


async def test_preparation_reads_return_own_submitted_preparation(task_client, monkeypatch):
    _project, task, submission = await submitted_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        run = await session.scalar(select(SelectedPreSubmitRun).where(SelectedPreSubmitRun.task_id == task))
    await as_actor(task_client, monkeypatch, OWNER)
    [summary] = (await get_ok(task_client, preparations_path(task)))["items"]
    assert summary["preparation_id"] == run.id and "findings" not in summary
    assert (summary["outcome"], summary["state"], summary["submission_id"]) == ("passed", "submitted", submission)
    assert summary["archive_sha256"] == run.archive_sha256
    assert summary["archive_byte_count"] == run.archive_byte_count
    detail = await get_ok(task_client, f"{preparations_path(task)}/{run.id}")
    assert detail | {"findings": None} == summary | {"findings": None}
    assert {item["source"] for item in detail["findings"]} >= {"workstream_default"}


async def test_summary_counts_own_work(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    summary = await get_ok(task_client, f"{ME}/summary", project_id=project)
    assert summary["project_id"] == project
    assert summary["assignments"] == {"active": 1, "closed": 0}
    assert summary["submissions"]["evaluation_pending"] == 1
    assert sum(summary["submissions"].values()) == 1 and summary["award_totals"] == []


async def test_summary_reports_nonempty_award_totals_as_exact_decimal_strings(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    selected = []

    async def totals(repository, contributor_id, project_ids):
        selected.append(project_ids)
        return (ContributorAwardTotal("money", "USD", Decimal("12.50")),
                ContributorAwardTotal("project_points", "points", Decimal("1E+3")))

    monkeypatch.setattr(ContributionAwardReadRepository, "read_award_totals", totals)
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    summary = await get_ok(task_client, f"{ME}/summary", project_id=project)
    assert [str(item) for item in selected[0]] == [project]
    assert summary["award_totals"] == [
        {"instrument": "money", "unit": "USD", "quantity": "12.50"},
        {"instrument": "project_points", "unit": "points", "quantity": "1000"},
    ]


def _execution(eligible):
    checks = tuple({
        "check_id": check_id,
        "status": "passed" if eligible or index < 2 else "failed" if index == 2 else "not_run",
        "failure_code": None if eligible or index != 2 else "high_confidence_secret_detected",
        "finding_count": 0 if eligible or index != 2 else 1,
    } for index, check_id in enumerate(WORKSTREAM_DEFAULT_CHECK_IDS))
    return SelectedPreSubmitExecutionFacts(
        policy_sha256="sha256:" + "1" * 64, required_external_count=0, external_members=(), eligible=eligible,
        workstream_default=WorkstreamDefaultCheckerResult(
            behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256, eligible=eligible, checks=checks, warnings=(),
        ),
    )


_ADMISSION, _SUBMISSION = uuid4(), uuid4()


@pytest.mark.parametrize("status,terminal,custody,expected", [
    ("queued", None, None, ("pending", "checking", None, None, None)),
    ("running", None, ("put_in_flight", None, None, None), ("pending", "checking", "put_in_flight", None, None)),
    ("infrastructure_failed", SimpleNamespace(execution=None, infrastructure_failure_code="deadline_exceeded"),
     None, ("infrastructure_failed", "infrastructure_failed", None, None, None)),
    ("completed", False, None, ("failed", "checks_failed", None, None, None)),
    ("completed", True, None, ("passed", "storing", None, None, None)),
    ("completed", True, ("put_in_flight", None, None, None), ("passed", "storing", "put_in_flight", None, None)),
    ("completed", True, ("observed_confirmed", _ADMISSION, "ready", None),
     ("passed", "ready", "observed_confirmed", _ADMISSION, None)),
    ("completed", True, ("observed_confirmed", _ADMISSION, "consumed", _SUBMISSION),
     ("passed", "submitted", "observed_confirmed", None, _SUBMISSION)),
    ("completed", True, ("observed_confirmed", _ADMISSION, "stale", None),
     ("passed", "stale", "observed_confirmed", None, None)),
])
async def test_preparation_projection_maps_every_check_and_custody_state(status, terminal, custody, expected):
    if isinstance(terminal, bool):
        terminal = SimpleNamespace(execution=_execution(terminal), infrastructure_failure_code=None)
    now = datetime.now(UTC)
    view = SelectedPreSubmitRunView(
        run_id=uuid4(), actor_profile_id=uuid4(), task_id=uuid4(), assignment_id=uuid4(), status=status,
        archive_sha256="sha256:" + "a" * 64, archive_byte_count=10, queued_at=now,
        completed_at=None if terminal is None else now, terminal=terminal,
    )
    runs = SimpleNamespace(read_contributor_runs=AsyncMock(return_value=((view,), False)))
    rows = [] if custody is None else [(str(view.run_id), *custody)]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))
    (item,), more = await SubmissionBundlePreparationReader(session, runs=runs).read(
        actor_profile_id=uuid4(), task_id=view.task_id, preparation_id=None, limit=1, before=None,
    )
    storage = None if item.storage_status is None else item.storage_status.value
    assert (item.outcome, item.state, storage, item.admission_id, item.submission_id) == expected
    assert more is False and item.preparation_id == view.run_id
    execution = None if terminal is None else terminal.execution
    assert (item.finding_counts is None) == (execution is None)
    assert bool(item.findings) == (execution is not None)
    if status == "infrastructure_failed":
        assert item.infrastructure_failure_code == "deadline_exceeded"
    if expected[1] == "checks_failed":
        assert item.finding_counts.blocking >= 1
