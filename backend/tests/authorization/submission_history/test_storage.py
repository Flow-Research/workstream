"""Retained evidence constraints survive removal of the alternate checker writer."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.tasks.models import Submission
from app.modules.checkers.models import CheckerRun
from tests.test_tasks import create_started_task, complete_submission_payload
from tests.submission_fixtures import seed_retained_submission
from .test_reads import history_case


@pytest.mark.parametrize("damage", ["missing", "mismatched"])
async def test_submission_policy_custody_rejects_changes(task_client, monkeypatch, damage):
    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, case[2])
        original = submission.locked_post_submit_checker_policy_hash
        if damage == "missing":
            submission.locked_post_submit_checker_policy_id = None
            submission.locked_post_submit_checker_policy_version = None
            submission.locked_post_submit_checker_policy_hash = None
        else:
            submission.locked_post_submit_checker_policy_hash = "sha256:" + "0" * 64
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, case[2])
        assert submission.locked_post_submit_checker_policy_hash == original
        assert submission.locked_at is not None
        assert await session.get(CheckerRun, case[3]) is not None


async def test_checker_cannot_bind_another_tasks_submission(task_client, monkeypatch):
    case = await history_case(task_client, monkeypatch)
    other = await create_started_task(task_client, case[0], monkeypatch, subject="other-checker-owner")
    await seed_retained_submission(other["id"], complete_submission_payload())
    async with db_session.get_session_factory()() as session:
        run = await session.get(CheckerRun, case[3])
        run.task_id = other["id"]
        with pytest.raises(IntegrityError, match="fk_checker_runs_submission_version"):
            await session.commit()
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        run = await session.get(CheckerRun, case[3])
        assert run.task_id == case[1] and run.submission_id == case[2]


@pytest.mark.parametrize("duplicate", ["attempt", "current"])
async def test_checker_attempt_and_currentness_are_unique(task_client, monkeypatch, duplicate):
    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        original = await session.get(CheckerRun, case[3])
        values = {column.name: getattr(original, column.name) for column in CheckerRun.__table__.columns}
        values["id"] = str(new_record_id())
        values["is_current_for_submission"] = duplicate == "current"
        values["attempt_number"] = 2 if duplicate == "current" else original.attempt_number
        session.add(CheckerRun(**values))
        expected = "uq_checker_runs_current_per_submission" if duplicate == "current" else "uq_checker_runs_submission_attempt"
        with pytest.raises(IntegrityError, match=expected):
            await session.commit()
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        assert list(await session.scalars(select(CheckerRun.id).where(CheckerRun.submission_id == case[2]))) == [case[3]]
