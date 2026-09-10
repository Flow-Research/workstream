"""Migration/schema parity and immutable generation fork prevention."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError

from app.modules.projects.guide_compilation.models import ProjectGuideSetupFinalization
from .pg_support import database_case, finalize, stored_state


async def test_finalization_schema_matches_model_columns_and_composite_custody(
    clean_postgres_database,
):
    async with database_case(clean_postgres_database) as (_, factory, _):
        async with factory() as session:
            columns = set(
                (
                    await session.execute(
                        text(
                            "select column_name from information_schema.columns "
                            "where table_schema='public' and table_name='project_guide_setup_finalizations'"
                        )
                    )
                ).scalars()
            )
            constraints = set(
                (
                    await session.execute(
                        text(
                            "select conname from pg_constraint "
                            "where conrelid='project_guide_setup_finalizations'::regclass"
                        )
                    )
                ).scalars()
            )
        table = ProjectGuideSetupFinalization.__table__
        assert columns == set(table.columns.keys())
        preparer = postgresql.dialect().identifier_preparer
        assert {
            preparer.format_constraint(constraint, _alembic_quote=False)
            for constraint in table.constraints
        } | {"finalization_atomic_custody"} == constraints
        assert {
            "fk_finalization_exact_attempt",
            "fk_finalization_exact_setup",
            "fk_finalization_sufficiency_lineage",
            "fk_finalization_policy_lineage",
            "uq_finalization_setup_generation",
            "uq_finalization_compilation",
            "uq_finalization_operation",
        } <= constraints


async def test_distinct_operations_cannot_finalize_one_setup_generation(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        await finalize(factory, values, command)
        before = await stored_state(factory, command)
        columns = list(ProjectGuideSetupFinalization.__table__.columns.keys())
        selected = [
            ":new_id" if name == "id" else ":operation" if name == "operation_id" else name
            for name in columns
        ]
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                await session.execute(
                    text(
                        "insert into project_guide_setup_finalizations (" + ",".join(columns) + ") "
                        "select "
                        + ",".join(selected)
                        + " from project_guide_setup_finalizations where setup_run_id=:setup"
                    ),
                    {"new_id": uuid4(), "operation": uuid4(), "setup": str(command.setup_run_id)},
                )
        assert await stored_state(factory, command) == before
