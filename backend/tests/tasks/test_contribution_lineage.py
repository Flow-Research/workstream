"""Exact initial TASK/assignment policy custody against migrated PostgreSQL."""

from app.core.config import get_settings
import json

from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.modules.projects.models import ProjectGuide
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project,
    create_started_task,
    create_ready_task,
    create_draft_task,
)
from tests.projects.guide_activation.pg_support import publish_policy


async def test_no_payment_screen_claim_and_start_copy_exact_guide_policy(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        guide = await session.scalar(
            select(ProjectGuide).where(
                ProjectGuide.project_id == project["id"], ProjectGuide.status == "active"
            )
        )
        stored = await session.get(WorkstreamTask, task["id"])
        assignment = await session.scalar(
            select(TaskAssignment).where(TaskAssignment.task_id == task["id"])
        )
        assert guide.contribution_policy_version_id is not None
        assert stored.locked_contribution_policy_version_id == guide.contribution_policy_version_id
        assert (
            assignment.submitter_contribution_policy_version_id
            == guide.contribution_policy_version_id
        )
        assert assignment.project_id == project["id"]
        assert stored.status == "in_progress"



async def _reject_assignment_selection_and_stamp(session, statement, params):
    """Prove both current selection and the independent policy stamp guard."""
    trigger_query = text(
        "SELECT pg_get_triggerdef(oid), tgenabled::text AS tgenabled FROM pg_trigger "
        "WHERE tgrelid='public.task_assignments'::regclass "
        "AND tgname='assignment_reward_selection'"
    )
    trigger_before = (await session.execute(trigger_query)).one()
    assert trigger_before.tgenabled == "O"
    rows_query = text("SELECT to_jsonb(a) FROM public.task_assignments a ORDER BY id")
    rows_before = list(await session.scalars(rows_query))
    with pytest.raises(DBAPIError, match="assignment reward selection differs") as failure:
        async with session.begin_nested():
            await session.execute(statement, params)
    assert failure.value.orig.sqlstate == "23514"
    assert list(await session.scalars(rows_query)) == rows_before
    # The earlier stamp guard must still reject the tuple independently. Drop
    # only the newer trigger inside a savepoint that is always rolled back.
    async with session.begin_nested() as discriminator:
        await session.execute(text(
            "DROP TRIGGER assignment_reward_selection ON public.task_assignments"
        ))
        with pytest.raises(DBAPIError, match="assignment contribution stamp differs from task") as failure:
            async with session.begin_nested():
                await session.execute(statement, params)
                await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        assert failure.value.orig.sqlstate == "23514"
        await discriminator.rollback()
    assert (await session.execute(trigger_query)).one() == trigger_before
    assert list(await session.scalars(rows_query)) == rows_before


async def test_assignment_insert_rejects_same_project_wrong_stamp_direct_sql(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    _, other = await publish_policy(factory, UUID(project["id"]))
    async with factory() as session:
        stored = await session.get(WorkstreamTask, task["id"])
        expected = stored.locked_contribution_policy_version_id
        actor = stored.created_by
        assert other.contribution_policy_version_id != expected
        statement = text(
            "INSERT INTO task_assignments(id,task_id,project_id,contributor_id,assigned_by,status,"
            "submitter_contribution_policy_version_id,submitter_task_size,submitter_award_definition_id) "
            "VALUES(:id,:task,:project,:actor,:assigned_by,'active',:policy,:size,:definition)"
        )
        params = dict(
            id=str(new_record_id()),
            task=task["id"],
            project=project["id"],
            actor=actor,
            assigned_by=actor,
            policy=other.contribution_policy_version_id,
            size=stored.task_size,
            definition=stored.locked_submission_award_definition_id,
        )
        await _reject_assignment_selection_and_stamp(session, statement, params)
        assert (
            await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == task["id"]))
            is None
        )
        # The otherwise identical positive control reaches the same direct SQL insert.
        await session.execute(statement, params | {"policy": expected})
        await session.commit()


async def test_non_draft_insert_cannot_invent_initial_stamp(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="task contribution stamp requires initial screening"):
            async with session.begin_nested():
                await session.execute(
                    text(
                        "INSERT INTO workstream_tasks SELECT (jsonb_populate_record(NULL::workstream_tasks, "
                        "to_jsonb(t) || jsonb_build_object('id',CAST(:id AS text)))).* FROM workstream_tasks t WHERE id=:task"
                    ),
                    {"id": str(new_record_id()), "task": task["id"]},
                )


async def test_task_stamp_rejects_valid_successor_context_direct_sql(task_client):
    import json

    from app.adapters.projects import project_locked_policy_context_port
    from app.adapters.tasks import task_service
    from tests.test_tasks import (
        auth_headers,
        complete_guide_payload,
        create_policy_bundle_for_guide,
    )
    from tests.project_create_fixtures import seed_active_guide_for_downstream_test

    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    draft = await create_draft_task(task_client, project["id"])
    created = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload("v2"),
    )
    assert created.status_code == 201, created.text
    guide = created.json()
    await create_policy_bundle_for_guide(task_client, project["id"], guide["id"])
    factory = db_session.get_session_factory()
    await seed_active_guide_for_downstream_test(
        factory, project_id=project["id"], guide_id=guide["id"]
    )
    async with factory() as session:
        original = await session.get(WorkstreamTask, task["id"])
        old_stamp = original.locked_contribution_policy_version_id
        context = await project_locked_policy_context_port(session).lock_active_policy_context(
            UUID(project["id"])
        )
        stamps = task_service(session, settings=get_settings())._policy_stamps(context)
        assert stamps["locked_contribution_policy_version_id"] != old_stamp
        updates = []
        for key, value in stamps.items():
            if isinstance(value, dict):
                stamps[key] = json.dumps(value)
                updates.append(f"{key}=CAST(:{key} AS json)")
            else:
                updates.append(f"{key}=:{key}")
        with pytest.raises(DBAPIError, match="task revision context lacks current preparation"):
            async with session.begin_nested():
                await session.execute(
                    text("UPDATE workstream_tasks SET " + ",".join(updates) + " WHERE id=:task_id"),
                    stamps | {"task_id": task["id"]},
                )
        # Draft lineage is allowed by the preparation guard, but inventing a
        # contribution stamp outside initial screening remains forbidden.
        with pytest.raises(DBAPIError, match="task contribution stamp is immutable"):
            async with session.begin_nested():
                await session.execute(text(
                    "UPDATE public.workstream_tasks SET locked_contribution_policy_version_id=:stamp WHERE id=:id"
                ), {"stamp": stamps["locked_contribution_policy_version_id"], "id": draft["id"]})
        draft_row = await session.get(WorkstreamTask, draft["id"])
        assert draft_row.locked_contribution_policy_version_id is None
        assert draft_row.status == "draft"
        await session.refresh(original)
        assert original.locked_contribution_policy_version_id == old_stamp
        assert original.locked_guide_version == "v1"
        assert original.status == "ready"


async def test_closed_assignment_stamp_cannot_be_replaced(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    factory = db_session.get_session_factory()
    _, successor = await publish_policy(factory, UUID(project["id"]))
    async with factory() as session:
        assignment = await session.scalar(
            select(TaskAssignment).where(TaskAssignment.task_id == task["id"])
        )
        before = assignment.submitter_contribution_policy_version_id
        assignment.status = "released"
        await session.commit()
        with pytest.raises(DBAPIError, match="assignment contribution identity is immutable"):
            async with session.begin_nested():
                await session.execute(
                    text(
                        "UPDATE task_assignments SET submitter_contribution_policy_version_id=:policy WHERE id=:id"
                    ),
                    dict(policy=successor.contribution_policy_version_id, id=assignment.id),
                )
        await session.refresh(assignment)
        assert assignment.status == "released"
        assert assignment.submitter_contribution_policy_version_id == before


async def test_submission_sql_requires_exact_initial_assignment_and_freezes_its_stamp(
    task_client,
    monkeypatch,
):
    """Arrange a TASK row for SQL guards; this is not ART admission proof."""
    from app.modules.tasks.models import Submission
    from app.modules.tasks.submission_composition import build_submission

    project = await create_active_project(task_client)
    started = await create_started_task(task_client, project["id"], monkeypatch)
    factory = db_session.get_session_factory()
    _, other = await publish_policy(factory, UUID(project["id"]))
    async with factory() as session:
        task = await session.get(WorkstreamTask, started["id"])
        assignment = await session.scalar(
            select(TaskAssignment).where(TaskAssignment.task_id == task.id)
        )
        original = build_submission(
            submission_id=str(new_record_id()),
            task=task,
            contributor_id=assignment.contributor_id,
            task_assignment_id=assignment.id,
            contribution_policy_version_id=assignment.submitter_contribution_policy_version_id,
            task_size=assignment.submitter_task_size,
            contribution_award_definition_id=assignment.submitter_award_definition_id,
            version=1,
            summary="Database lineage prerequisite",
            worker_attestation="SQL guard test",
            supersedes_submission_id=None,
        )
        # Obtain a complete initial-row shape, then roll it back so each
        # malformed INSERT tests assignment custody rather than a bogus round 2.
        async with session.begin_nested() as staged:
            session.add(original)
            await session.flush()
            initial_row = await session.scalar(text(
                "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
            ), {"id": original.id})
            await staged.rollback()
        stamp = original.contribution_policy_version_id
        assert stamp != other.contribution_policy_version_id
        # Policy changes fail exact TASK stamps first. Missing/unknown
        # assignments retain the distinct assignment-stamp guard proof.
        for field, value, error in (
            ("contribution_policy_version_id", str(other.contribution_policy_version_id),
             "submission task context differs"),
            ("task_assignment_id", None, "submission contribution stamp differs from assignment"),
            ("task_assignment_id", str(new_record_id()),
             "submission contribution stamp differs from assignment"),
            ("contribution_policy_version_id", None, "submission task context differs"),
        ):
            with pytest.raises(DBAPIError, match=error):
                async with session.begin_nested():
                    await session.execute(
                        text(
                            "INSERT INTO submissions SELECT (jsonb_populate_record(NULL::submissions, "
                            "CAST(:body AS jsonb) || jsonb_build_object('id',CAST(:id AS text),"
                            f"'{field}',CAST(:value AS text)))).*"
                        ),
                        dict(id=str(new_record_id()), value=value, body=json.dumps(initial_row)),
                    )
            assert await session.scalar(select(Submission.id)) is None
        session.add(original)
        await session.commit()
        for field, value in (
            ("contribution_policy_version_id", other.contribution_policy_version_id),
            ("task_assignment_id", str(new_record_id())),
            ("contributor_id", task.created_by),
        ):
            with pytest.raises(DBAPIError, match="submission contribution identity is immutable"):
                async with session.begin_nested():
                    await session.execute(
                        text(f"UPDATE submissions SET {field}=:value WHERE id=:id"),
                        dict(value=value, id=original.id),
                    )
        await session.refresh(original)
        assert original.contribution_policy_version_id == stamp
        assert original.task_assignment_id == assignment.id
        assert list(await session.scalars(select(Submission.id))) == [original.id]


async def test_assignment_insert_rejects_foreign_project_tuples_direct_sql(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    foreign = await create_active_project(task_client, slug="foreign-project")
    foreign_task = await create_ready_task(task_client, foreign["id"])
    factory = db_session.get_session_factory()
    async with factory() as session:
        local = await session.get(WorkstreamTask, task["id"])
        other = await session.get(WorkstreamTask, foreign_task["id"])
        assert local.project_id != other.project_id
        assert local.locked_contribution_policy_version_id != other.locked_contribution_policy_version_id
        statement = text(
            "INSERT INTO task_assignments(id,task_id,project_id,contributor_id,assigned_by,status,"
            "submitter_contribution_policy_version_id,submitter_task_size,submitter_award_definition_id) "
            "VALUES(:id,:task,:project,:actor,:assigned_by,'active',:policy,:size,:definition)"
        )
        params = dict(id=str(new_record_id()), task=local.id, project=local.project_id,
                      actor=local.created_by, assigned_by=local.created_by,
                      policy=local.locked_contribution_policy_version_id,
                      size=local.task_size, definition=local.locked_submission_award_definition_id)
        # Isolate each selector, then also reject an internally valid foreign
        # tuple. A policy mismatch alone cannot prove project binding.
        for changed in (
            {"project": other.project_id},
            {"policy": other.locked_contribution_policy_version_id},
            {"project": other.project_id, "policy": other.locked_contribution_policy_version_id},
        ):
            await _reject_assignment_selection_and_stamp(session, statement, params | changed)
            assert await session.get(TaskAssignment, params["id"]) is None
        await session.execute(statement, params)
        await session.commit()
        assignment = await session.get(TaskAssignment, params["id"])
        assert assignment.project_id == local.project_id
        assert assignment.submitter_contribution_policy_version_id == local.locked_contribution_policy_version_id
