"""The real migration admission guard protects current persisted facts before DDL."""

from pathlib import Path
from runpy import run_path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import text

from app.db import session as db_session
from tests.authorization.contribution_policies.postgresql_support import world


def _admit(connection):
    migration = Path(__file__).resolve().parents[2] / "alembic/versions/0069_sized_reward_policy.py"
    with Operations.context(MigrationContext.configure(connection)):
        run_path(str(migration))["_admit_transition"]()


@pytest.mark.parametrize("unpaid_rules", [False, True])
async def test_transition_admission_accepts_unpublished_nonfinancial_drafts(admin_access, unpaid_rules):
    target = await world(admin_access)
    draft = await target.execute("create_draft", target.request("create_draft"))
    if unpaid_rules:
        draft = await target.execute("update_draft", target.request("update_draft", draft))
    async with db_session.get_session_factory()() as session, session.begin():
        connection = await session.connection()
        await connection.run_sync(_admit)
        assert await session.scalar(text(
            "SELECT status FROM contribution_policy_versions WHERE id=:id"
        ), {"id": draft.contribution_policy_version_id}) == "draft"
        assert await session.scalar(text("SELECT count(*) FROM compensation_awards")) == 0


async def test_transition_admission_refuses_financial_definitions_without_rewriting(admin_access):
    target = await world(admin_access)
    draft = await target.execute("create_draft", target.request("create_draft"))
    draft = await target.execute("update_draft", target.request("update_draft", draft, compensated=True))
    query = text("SELECT id,unit_code,quantity::text FROM contribution_award_definitions "
                 "WHERE contribution_policy_version_id=:id ORDER BY id")
    parameters = {"id": draft.contribution_policy_version_id}
    async with db_session.get_session_factory()() as session, session.begin():
        before = (await session.execute(query, parameters)).all()
        assert len(before) == 3
        connection = await session.connection()
        with pytest.raises(RuntimeError, match="economic_definitions") as failure:
            await connection.run_sync(_admit)
        assert str(before[0].id) in str(failure.value)
        assert (await session.execute(query, parameters)).all() == before
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0070_task_size"
        assert await session.scalar(text("SELECT count(*) FROM compensation_awards")) == 0
