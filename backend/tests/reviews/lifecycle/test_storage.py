"""Direct SQL cannot invent or activate another lifecycle generation."""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import get_session_factory


async def test_genesis_and_sql_immutability(clean_postgres_database):
    factory = get_session_factory()
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    text("SELECT to_jsonb(c) FROM public.joint_lifecycle_release_control c")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        original = rows[0]
        assert UUID(original["id"]).version == 7
        assert original["singleton"] is True
        assert original["phase"] == "disabled" and original["generation"] == 0
        assert await session.scalar(
            text(
                "SELECT created_at <= clock_timestamp() FROM public.joint_lifecycle_release_control"
            )
        )
    for statement in (
        "INSERT INTO public.joint_lifecycle_release_control SELECT * FROM public.joint_lifecycle_release_control",
        "UPDATE public.joint_lifecycle_release_control SET phase='live',generation=1",
        "UPDATE public.joint_lifecycle_release_control SET id='01950000-0000-7000-8000-000000000001'",
        "UPDATE public.joint_lifecycle_release_control SET created_at='2000-01-01'",
        "DELETE FROM public.joint_lifecycle_release_control",
        "TRUNCATE public.joint_lifecycle_release_control CASCADE",
    ):
        async with factory() as session:
            with pytest.raises(DBAPIError, match="joint lifecycle (custody is immutable|transition custody invalid)"):
                await session.execute(text(statement))
                await session.commit()
        async with factory() as session:
            assert (
                await session.scalar(
                    text("SELECT to_jsonb(c) FROM public.joint_lifecycle_release_control c")
                )
                == original
            )

    from conftest import _reset_test_database_state

    await _reset_test_database_state(clean_postgres_database)
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT to_jsonb(c) FROM public.joint_lifecycle_release_control c")
            )
            == original
        )
