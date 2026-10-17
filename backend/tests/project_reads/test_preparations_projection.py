"""The project preparation read shares the contributor projection and maps outcomes to stored facts."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.artifacts.api.submission_preparation import ProjectSubmissionBundlePreparation
from app.modules.artifacts.preparation_reads import SubmissionBundlePreparationReader

WHEN = datetime(2026, 10, 1, tzinfo=UTC)


class _Session:
    """No intake custody exists for these runs."""

    async def execute(self, _statement):
        return SimpleNamespace(all=lambda: [])


class _Runs:
    """Record the stored filter each outcome requests and return the given views."""

    def __init__(self, views):
        self.views, self.calls = views, []

    async def read_project_runs(self, **call):
        self.calls.append(call)
        return self.views, False

    async def read_contributor_runs(self, **_call):
        return self.views, False


def _execution(*, eligible, blocking=0):
    checks = [SimpleNamespace(check_id=f"c{index}", status="passed", failure_code=None, finding_count=0)
              for index in range(3)]
    checks.append(SimpleNamespace(check_id="c3", status="passed" if eligible else "failed",
                                  failure_code=None if eligible else "blocked", finding_count=blocking))
    default = SimpleNamespace(checks=tuple(checks), warnings=())
    return SimpleNamespace(eligible=eligible, workstream_default=default, external_members=())


def _view(status, execution=None):
    terminal = None if status in {"queued", "running"} else SimpleNamespace(
        execution=execution, infrastructure_failure_code="checker_unavailable" if execution is None else None,
    )
    return SimpleNamespace(
        run_id=uuid4(), actor_profile_id=uuid4(), task_id=uuid4(), assignment_id=uuid4(), status=status,
        archive_sha256="sha256:" + "a" * 64, archive_byte_count=10, queued_at=WHEN,
        completed_at=None if terminal is None else WHEN, terminal=terminal,
    )


@pytest.mark.parametrize(("outcome", "statuses", "eligible"), [
    ("pending", ("queued", "running"), None),
    ("passed", ("completed",), True),
    ("failed", ("completed",), False),
    ("infrastructure_failed", ("infrastructure_failed",), None),
    (None, None, None),
])
async def test_outcome_filters_on_the_stored_status_and_eligibility(outcome, statuses, eligible):
    runs = _Runs(())
    project = uuid4()
    await SubmissionBundlePreparationReader(_Session(), runs=runs).read_project(
        project_id=project, outcome=outcome, limit=5, before=None,
    )
    assert runs.calls == [
        {"project_id": project, "statuses": statuses, "eligible": eligible, "limit": 5, "before": None},
    ]


async def test_failed_preparation_carries_counts_and_contributor_but_no_findings():
    views = (_view("completed", _execution(eligible=False, blocking=2)), _view("infrastructure_failed"),
             _view("queued"))
    reader = SubmissionBundlePreparationReader(_Session(), runs=_Runs(views))
    items, more = await reader.read_project(project_id=uuid4(), outcome=None, limit=5, before=None)
    assert more is False and all(type(item) is ProjectSubmissionBundlePreparation for item in items)
    failed, infrastructure, pending = items
    assert (failed.outcome, failed.state, failed.actor_profile_id) == ("failed", "checks_failed",
                                                                      views[0].actor_profile_id)
    assert failed.finding_counts.blocking == 2
    assert (infrastructure.outcome, infrastructure.infrastructure_failure_code) == (
        "infrastructure_failed", "checker_unavailable",
    )
    assert (pending.outcome, pending.state, pending.finding_counts) == ("pending", "checking", None)
    assert all("findings" not in item.model_dump() for item in items)
    # The contributor's own read projects the same fields from the same views.
    own, _ = await reader.read(actor_profile_id=uuid4(), task_id=uuid4(), preparation_id=None, limit=5, before=None)
    assert [item.model_dump(exclude={"findings"}) for item in own] == [
        item.model_dump(exclude={"actor_profile_id"}) for item in items
    ]
    assert own[0].findings
