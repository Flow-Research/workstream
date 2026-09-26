"""Fixed SQL projections and live grant privacy over retained checker results."""

import re
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import Engine

from app.db import session as db_session
from app.modules.tasks.models import AuditEvent, Submission
from app.modules.tasks.submission_history import SubmissionHistoryRepository
from app.modules.checkers.history import CheckerHistoryRepository
from tests.submission_fixtures import seed_retained_submission, seed_retained_checker_run
from tests.test_tasks import (create_active_project, create_started_task, complete_submission_payload,
                             set_dev_actor, auth_headers, actor_id)
from .test_reads import history_paths, history_case
from .test_absence import (SUBMISSION_FIELDS, MANAGER_SUBMISSION_FIELDS, RUN_FIELDS, MANAGER_RUN_FIELDS,
                           RESULT_FIELDS, MANAGER_RESULT_FIELDS, EVIDENCE_FIELDS)


@pytest.mark.parametrize("routing", ["allow_review", "checker_retry", "task_setup_blocked"])
async def test_fixed_projection_and_selected_columns(task_client, monkeypatch, routing):
    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    submission = await seed_retained_submission(task["id"], complete_submission_payload())
    run = await seed_retained_checker_run(submission, routing=routing, results=(
        {"metadata_json": {"secret": "RAW_RESULT_SENTINEL"}},
        {"checker_name": "check_submission_packet", "worker_visible": False,
         "worker_message": "HIDDEN_RESULT_SENTINEL", "message": "hidden internal"},
    ))
    case = project["id"], task["id"], submission, run
    captured = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        lowered = statement.lower()
        if lowered.lstrip().startswith("select") and any(f"from {table}" in lowered for table in ("submissions", "checker_results", "checker_runs", "evidence_items")):
            captured.append(lowered.split("from", 1)[0])
    event.listen(Engine, "before_cursor_execute", capture)
    try:
        for manager in (False, True):
            set_dev_actor(monkeypatch, roles="", subject="project-manager-subject" if manager else "worker-one")
            for action, path in history_paths(*case, manager=manager).items():
                captured.clear()
                response = await task_client.get(path, headers=auth_headers())
                assert response.status_code == 200, response.text
                assert "RAW_RESULT_SENTINEL" not in response.text
                value = response.json()
                item = value["items"][0] if action.endswith("list") else value
                checker = "checker" in action
                expected_fields = (MANAGER_RUN_FIELDS if manager else RUN_FIELDS) if checker else (MANAGER_SUBMISSION_FIELDS if manager else SUBMISSION_FIELDS)
                assert set(item) == expected_fields
                nested_key = "results" if checker else "evidence_items"
                nested_fields = (MANAGER_RESULT_FIELDS if manager else RESULT_FIELDS) if checker else EVIDENCE_FIELDS
                assert all(set(nested) == nested_fields for nested in item[nested_key])
                # Independently fixed inventories guard selected SQL, including fields DTOs discard.
                allowed = {
                    "submissions": (MANAGER_SUBMISSION_FIELDS if manager else SUBMISSION_FIELDS) - {"evidence_items"},
                    "checker_runs": (MANAGER_RUN_FIELDS if manager else RUN_FIELDS) - {"results"},
                    "checker_results": MANAGER_RESULT_FIELDS if manager else RESULT_FIELDS,
                    "evidence_items": EVIDENCE_FIELDS,
                }
                assert captured
                for statement in captured:
                    for table, fields in allowed.items():
                        selected = set(re.findall(rf"\b{table}\.([a-z_]+)", statement))
                        # Minimal TASK ownership resolution also selects contributor_id for AUTH.
                        if table == "submissions" and "workstream_tasks.project_id" in statement:
                            assert selected == {"id", "task_id", "contributor_id"}
                        else:
                            if selected:
                                assert selected == fields, statement
                if checker:
                    expected = 2 if manager else 1 if routing == "allow_review" else 0
                    assert len(item["results"]) == expected
                    if not manager:
                        assert "HIDDEN_RESULT_SENTINEL" not in response.text
                        assert "internal" not in response.text
                for field in ("package_hash", "package_uri", "artifact_hash_manifest", "worker_attestation", "locked_payment_policy_version"):
                    assert field not in item
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
    assert captured
    for statement in captured:
        assert not any(f".{field}" in statement for field in (
            "package_uri", "package_hash", "artifact_hash_manifest", "metadata", "worker_attestation",
            "triggered_by_subject", "triggered_by_issuer", "locked_payment_policy_version",
            "uri", "hash", "locked_post_submit_checker_policy_body", "passed_count", "warning_count", "failed_count", "blocking_count",
        )), statement


async def test_denied_read_never_loads_private_rows(task_client, monkeypatch):
    from app.modules.authorization.models import ProjectRoleGrant
    case = await history_case(task_client, monkeypatch)
    who = await actor_id("worker-one")
    async with db_session.get_session_factory()() as session:
        grant = await session.scalar(select(ProjectRoleGrant).where(ProjectRoleGrant.actor_profile_id == who))
        grant_id = str(grant.id)
    set_dev_actor(monkeypatch, roles="", subject="project-manager-subject")
    revoke = await task_client.post(f"/api/v1/projects/{case[0]}/role-grants/{grant_id}/revoke",
                                   headers=auth_headers() | {"Idempotency-Key": str(uuid4())}, json={"reason": "Withdraw history access"})
    assert revoke.status_code == 200, revoke.text
    set_dev_actor(monkeypatch, roles="admin,project_manager,worker", subject="worker-one")
    async def forbidden(*args, **kwargs):
        pytest.fail("private projection entered without live grant")
    monkeypatch.setattr(SubmissionHistoryRepository, "read", forbidden)
    monkeypatch.setattr(CheckerHistoryRepository, "read", forbidden)
    for path in history_paths(*case).values():
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 404, response.text
    async with db_session.get_session_factory()() as session:
        events = list(await session.scalars(select(AuditEvent).where(AuditEvent.actor_id == who,
                                AuditEvent.action_id.in_(tuple(history_paths(*case))))))
        assert len(events) == 4
        assert all(event.after_facts["allowed"] is False for event in events)
        assert await session.get(Submission, case[2]) is not None


@pytest.mark.parametrize("manager", [False, True])
async def test_nested_values_match_exact_stored_parents(task_client, monkeypatch, manager):
    from app.core.identifiers import new_record_id
    from app.modules.tasks.models import EvidenceItem
    from app.modules.checkers.models import CheckerRun, CheckerResult

    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    submission = await seed_retained_submission(task["id"], complete_submission_payload())
    run = await seed_retained_checker_run(submission, results=({"worker_message": "Original visible"},
        {"worker_visible": False, "message": "Original management only"}))
    foreign_task = await create_started_task(task_client, project["id"], monkeypatch, subject="foreign-nested-owner")
    foreign_payload = complete_submission_payload()
    for item in foreign_payload["evidence_items"]:
        item["label"] = "Foreign " + item["label"]
    foreign_submission = await seed_retained_submission(foreign_task["id"], foreign_payload)
    foreign_run = await seed_retained_checker_run(foreign_submission, results=(
        {"worker_message": "Foreign visible"}, {"worker_visible": False, "message": "Foreign management only"}))
    async with db_session.get_session_factory()() as session, session.begin():
        original = await session.get(CheckerRun, run)
        values = {column.name: getattr(original, column.name) for column in CheckerRun.__table__.columns}
        sibling_id = str(new_record_id())
        values.update(id=sibling_id, attempt_number=2, is_current_for_submission=False,
                      supersedes_checker_run_id=run, status="running", completed_at=None)
        sibling = CheckerRun(**values)
        session.add(sibling)
        await session.flush()
        original_results = list(await session.scalars(select(CheckerResult).where(CheckerResult.checker_run_id == run)))
        for result in original_results:
            values = {column.key: getattr(result, column.key if column.key != "metadata" else "metadata_json")
                      for column in CheckerResult.__table__.columns}
            values["metadata_json"] = values.pop("metadata")
            values.update(id=str(new_record_id()), checker_run_id=sibling_id,
                          worker_message="Sibling visible", message="Sibling management")
            session.add(CheckerResult(**values))
        await session.flush()
        sibling.status, sibling.completed_at = "completed", original.completed_at
    async with db_session.get_session_factory()() as session:
        evidence = list(await session.scalars(select(EvidenceItem).order_by(EvidenceItem.id)))
        results = list(await session.scalars(select(CheckerResult).order_by(CheckerResult.id)))
        assert {str(row.submission_id) for row in evidence} == {submission, foreign_submission}
        assert {str(row.checker_run_id) for row in results} == {run, sibling_id, foreign_run}
        expected_evidence = [{field: str(getattr(row, field)) if field == "id" else getattr(row, field)
                              for field in EVIDENCE_FIELDS}
                             for row in evidence if str(row.submission_id) == submission]
        result_fields = MANAGER_RESULT_FIELDS if manager else RESULT_FIELDS
        expected_results = {
            run_id: [{field: str(getattr(row, field)) if field == "id" else getattr(row, field)
                      for field in result_fields}
                     for row in results if str(row.checker_run_id) == run_id and (manager or row.worker_visible)]
            for run_id in (run, sibling_id)
        }
        assert expected_evidence and all(expected_results.values())
        assert expected_results[run] != expected_results[sibling_id]
        for row in results:
            if str(row.checker_run_id) in expected_results:
                assert str(row.submission_id) == submission and str(row.task_id) == task["id"]
    set_dev_actor(monkeypatch, roles="", subject="project-manager-subject" if manager else "worker-one")
    for action, path in history_paths(project["id"], task["id"], submission, run, manager=manager).items():
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 200, response.text
        items = response.json()["items"] if action.endswith("list") else [response.json()]
        checker = "checker" in action
        expected_ids = {run, sibling_id} if action == "submission.checker_run.list" else {run} if checker else {submission}
        assert {item["id"] for item in items} == expected_ids
        for item in items:
            if checker:
                assert item["submission_id"] == submission and item["task_id"] == task["id"]
                assert item["results"] == expected_results[item["id"]]
            else:
                assert item["evidence_items"] == expected_evidence
