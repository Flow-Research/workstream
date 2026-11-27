"""Each contributor read is one REPEATABLE READ snapshot; integrity gaps are retryable 503s."""

from datetime import UTC, datetime

from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitRunView
from app.modules.checkers.selected_pre_submit_reads import SelectedPreSubmitRunReader
from app.modules.tasks.contributor_reads import ContributorWorkReader
from app.modules.tasks.repository import TaskRepository
from tests.submission_fixtures import seed_retained_checker_run
from tests.test_tasks import auth_headers
from .support import ME, OWNER, as_actor, get_ok, preparations_path, submitted_case


def _observe(owner, name, observed):
    original = getattr(owner, name)

    async def observing(reader, *args, **kwargs):
        observed.append(await reader._session.scalar(text("SHOW transaction_isolation")))
        return await original(reader, *args, **kwargs)

    return observing


async def test_work_and_preparation_reads_run_in_one_repeatable_read_snapshot(task_client, monkeypatch):
    _project, task, _submission = await submitted_case(task_client, monkeypatch)
    observed = []
    monkeypatch.setattr(ContributorWorkReader, "read_assignments",
                        _observe(ContributorWorkReader, "read_assignments", observed))
    monkeypatch.setattr(SelectedPreSubmitRunReader, "read_contributor_runs",
                        _observe(SelectedPreSubmitRunReader, "read_contributor_runs", observed))
    await as_actor(task_client, monkeypatch, OWNER)
    for path in (f"{ME}/assignments", preparations_path(task)):
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 200, response.text
    assert observed == ["repeatable read", "repeatable read"]


async def _unavailable(client, path):
    response = await client.get(path, headers=auth_headers())
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "contributor_read_unavailable"


async def test_assignment_without_locked_terms_is_a_retryable_unavailable_read(task_client, monkeypatch):
    await submitted_case(task_client, monkeypatch)

    async def no_terms(repository, project_id, version_ids):
        return {}

    monkeypatch.setattr(TaskRepository, "locked_compensation", no_terms)
    await as_actor(task_client, monkeypatch, OWNER)
    await _unavailable(task_client, f"{ME}/assignments")


async def test_completed_preparation_without_execution_facts_is_unavailable(task_client, monkeypatch):
    _project, task, _submission = await submitted_case(task_client, monkeypatch)
    async def without_execution(reader, **kwargs):
        now = datetime.now(UTC)
        return (SelectedPreSubmitRunView(
            run_id=new_record_id(), actor_profile_id=kwargs["actor_profile_id"],
            task_id=kwargs["task_id"], assignment_id=new_record_id(), status="completed",
            archive_sha256="sha256:" + "a" * 64, archive_byte_count=1,
            queued_at=now, completed_at=now, terminal=None,
        ),), False

    monkeypatch.setattr(SelectedPreSubmitRunReader, "read_contributor_runs", without_execution)
    await as_actor(task_client, monkeypatch, OWNER)
    await _unavailable(task_client, preparations_path(task))


async def test_findings_committed_by_another_session_mid_read_stay_out_of_that_response(task_client, monkeypatch):
    _project, _task, submission = await submitted_case(task_client, monkeypatch)
    original = ContributorWorkReader.read_submissions
    interleaved = []

    async def interleaving(reader, query):
        await reader._session.execute(text("SELECT 1"))
        if not interleaved:
            # A second session commits a failed run with findings after this snapshot began.
            interleaved.append(await seed_retained_checker_run(submission, verdict="failed", generation=2))
        return await original(reader, query)

    monkeypatch.setattr(ContributorWorkReader, "read_submissions", interleaving)
    await as_actor(task_client, monkeypatch, OWNER)
    [during] = (await get_ok(task_client, f"{ME}/submissions"))["items"]
    [after] = (await get_ok(task_client, f"{ME}/submissions"))["items"]
    assert len(interleaved) == 1
    assert during["finding_counts"]["blocking"] == 0 < after["finding_counts"]["blocking"]
    assert during["updated_at"] < after["updated_at"]
