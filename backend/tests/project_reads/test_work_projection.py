"""A Project Manager reads the project's attempts, claims and summary through public routes."""

from decimal import Decimal

from app.api.deps.project_work_reads import ProjectWorkSummary
from app.modules.tasks.api.contributor_reads import ContributorAssignmentCounts, ContributorSubmissionCounts
from app.modules.tasks.api.project_reads import ProjectWorkCounts, TaskStatusCounts
from app.modules.compensation.api.award_reads import ContributorAwardTotal
from app.core.identifiers import new_record_id
from app.modules.outbox.api import HandlerOutcome
from tests.submission_fixtures import route_retained_checker_remediation, seed_retained_checker_run
from tests.tasks.invalidation_support import invoked, revoke, setup_assignment
from tests.test_tasks import actor_id, create_draft_task
from .support import OWNER, as_manager, get_ok, project_path, submitted_case


def _present(view):
    return {name: value for name, value in view.items() if value is not None}


async def test_submission_carries_submitter_outcome_and_management_finding_counts(task_client, monkeypatch):
    project, task, submission = await submitted_case(task_client, monkeypatch)
    await route_retained_checker_remediation(submission, generation=2)
    as_manager(monkeypatch)
    [item] = (await get_ok(task_client, project_path(project, "/submissions")))["items"]
    assert (item["submission_id"], item["project_id"], item["task_id"]) == (submission, project, task)
    assert item["submitter_actor_id"] == await actor_id(OWNER)
    assert item["status"] == "needs_revision" and item["decided_at"] is not None
    history = await get_ok(task_client, project_path(project, f"/submissions/{submission}"))
    assert item["finding_counts"] == history["finding_counts"] and item["finding_counts"]["blocking"] >= 1


async def test_assignment_carries_contributor_and_the_work_context_revision(task_client, monkeypatch):
    project, task, submission = await submitted_case(task_client, monkeypatch)
    await route_retained_checker_remediation(submission, generation=2)
    as_manager(monkeypatch)
    context = (await get_ok(task_client, project_path(project, f"/tasks/{task}/work-context")))["task"]
    [item] = (await get_ok(task_client, project_path(project, "/assignments")))["items"]
    assert (item["task_id"], item["state"], item["task_status"]) == (task, "active", "needs_revision")
    assert item["contributor_actor_id"] == await actor_id(OWNER)
    assert item["latest_submission"]["submission_id"] == submission
    # The work-context route omits null fields; the values are the same projection.
    assert item["revision"] is not None and _present(item["revision"]) == _present(context["revision_context"])
    assert item["compensation"]["contribution_policy_version_id"]


async def test_a_revoked_claim_is_closed_with_only_its_contributors_facts(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    as_manager(monkeypatch)
    path = project_path(s.project["id"], "/assignments")
    [item] = (await get_ok(task_client, path, state="closed"))["items"]
    assert (item["assignment_id"], item["task_id"]) == (s.assignment["id"], s.task["id"])
    assert (item["state"], item["assignment_status"]) == ("closed", "authority_revoked")
    assert item["contributor_actor_id"] == s.grant["actor_profile_id"]
    # A closed claim projects no current task status and no revision context.
    assert item["task_status"] is None and item["revision"] is None and item["released_at"] is not None
    assert (await get_ok(task_client, path, state="active"))["items"] == []


async def test_summary_counts_tasks_claims_attempts_and_infrastructure_failures(task_client, monkeypatch):
    project, _task, submission = await submitted_case(task_client, monkeypatch)
    as_manager(monkeypatch)
    await create_draft_task(task_client, project)
    summary = await get_ok(task_client, project_path(project, "/summary"))
    assert summary["project_id"] == project
    assert summary["tasks"]["draft"] == 1 and summary["tasks"]["evaluation_pending"] == 1
    assert sum(summary["tasks"].values()) == 2
    assert summary["assignments"] == {"active": 1, "closed": 0}
    assert summary["submissions"]["evaluation_pending"] == 1 and sum(summary["submissions"].values()) == 1
    assert summary["acceptance_rate"] is None and summary["checker_infrastructure_failures"] == 0
    await seed_retained_checker_run(submission, state="infrastructure_failed", generation=2)
    assert (await get_ok(task_client, project_path(project, "/summary")))["checker_infrastructure_failures"] == 1


async def test_summary_acceptance_rate_follows_decided_attempts(task_client, monkeypatch):
    project, _task, submission = await submitted_case(task_client, monkeypatch)
    await route_retained_checker_remediation(submission, generation=2)
    as_manager(monkeypatch)
    summary = await get_ok(task_client, project_path(project, "/summary"))
    assert summary["submissions"]["needs_revision"] == 1 and summary["acceptance_rate"] == 0.0


def test_summary_rate_is_accepted_over_decided_and_totals_follow_disclosure():
    """Pure rule: pending attempts are not decided; hidden totals are null, visible totals exact."""
    counts = ProjectWorkCounts(
        tasks=TaskStatusCounts(**dict.fromkeys(TaskStatusCounts.model_fields, 0)),
        assignments=ContributorAssignmentCounts(active=0, closed=0),
        submissions=ContributorSubmissionCounts(
            evaluation_pending=5, review_pending=4, accepted=3, needs_revision=2, rejected=1,
        ),
    )
    project = new_record_id()
    hidden = ProjectWorkSummary.from_facts(project, counts, 0, None)
    assert hidden.acceptance_rate == 3 / 6 and hidden.award_totals is None
    visible = ProjectWorkSummary.from_facts(project, counts, 2, (
        ContributorAwardTotal("money", "USD", Decimal("12.50")),
    ))
    assert [total.model_dump() for total in visible.award_totals] == [
        {"instrument": "money", "unit": "USD", "quantity": "12.50"},
    ]
    assert visible.checker_infrastructure_failures == 2
