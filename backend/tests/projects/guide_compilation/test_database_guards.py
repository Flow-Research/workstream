"""Direct PostgreSQL attack proof for compilation custody."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.projects.guide_compilation.repository import GuideCompilationRepository
from app.modules.projects.guide_compilation.validation import TERMINAL_FAILURE_CODES

from .helpers import context, identity, seed_database


async def _reserved(database_url: str):
    values = await seed_database(database_url)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        _, attempt = await GuideCompilationRepository(session).reserve_attempt(
            identity(context(values))
        )
    return engine, attempt


@pytest.mark.asyncio
async def test_invalid_terminal_rejects_an_accepted_timestamp(
    clean_postgres_database: str,
) -> None:
    """Terminal-invalid custody cannot look like accepted provider output."""
    engine, attempt = await _reserved(clean_postgres_database)
    try:
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text(
                        "update project_guide_compilation_attempts set "
                        "status='compilation_invalid_terminal',failure_code='schema_invalid',"
                        "terminal_at=now(),accepted_at=now() where id=:id"
                    ),
                    {"id": attempt.id},
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_attempt_identity_rejects_noncanonical_source_hash(
    clean_postgres_database: str,
) -> None:
    """PostgreSQL independently rejects malformed snapshot lineage hashes."""
    engine, attempt = await _reserved(clean_postgres_database)
    try:
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text(
                        "update project_guide_compilation_attempts "
                        "set source_snapshot_hash=:hash where id=:id"
                    ),
                    {"id": attempt.id, "hash": "not-a-digest"},
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_accepted_state_rejects_null_component_hashes(
    clean_postgres_database: str,
) -> None:
    """Explicit JSON nulls cannot satisfy accepted component custody."""
    engine, attempt = await _reserved(clean_postgres_database)
    null_hashes = {
        name: None
        for name in (
            "sufficiency_hash",
            "artifact_policy_hash",
            "requirement_inventory_hash",
            "pre_submit_hash",
            "post_submit_hash",
            "capability_suggestions_hash",
            "setup_notes_hash",
        )
    }
    try:
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text(
                        "update project_guide_compilation_attempts set status='provider_result_accepted',"
                        "accepted_at=now(),canonical_result='{}'::json,result_hash=:hash,"
                        "component_hashes=cast(:components as json) where id=:id"
                    ),
                    {
                        "id": attempt.id,
                        "hash": "sha256:" + "a" * 64,
                        "components": json.dumps(null_hashes),
                    },
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_attempt_delete_is_rejected(clean_postgres_database: str) -> None:
    """A reserved generation cannot disappear through row deletion."""
    engine, attempt = await _reserved(clean_postgres_database)
    try:
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text("delete from project_guide_compilation_attempts where id=:id"),
                    {"id": attempt.id},
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_attempt_truncate_is_rejected(clean_postgres_database: str) -> None:
    """Bulk truncation cannot erase attempt custody."""
    engine, _ = await _reserved(clean_postgres_database)
    try:
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text("truncate table project_guide_compilation_attempts")
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_live_terminal_constraint_matches_closed_vocabulary(
    clean_postgres_database: str,
) -> None:
    """Migrated PostgreSQL accepts exact reason codes and rejects legacy states."""
    engine, attempt = await _reserved(clean_postgres_database)
    try:
        async with engine.connect() as connection:
            definition = await connection.scalar(
                text(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid='project_guide_compilation_attempts'::regclass "
                    "and contype='c' and pg_get_constraintdef(oid) like '%failure_code%'"
                )
            )
        assert definition is not None
        assert all(f"'{code}'" in definition for code in TERMINAL_FAILURE_CODES)
        assert "'accepted'" not in definition
        assert "'invalid_terminal'" not in definition

        for status in ("accepted", "invalid_terminal", "persisted"):
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "update project_guide_compilation_attempts "
                            "set status=:status where id=:id"
                        ),
                        {"id": attempt.id, "status": status},
                    )
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "update project_guide_compilation_attempts set "
                        "status='compilation_invalid_terminal',terminal_at=now(),"
                        "failure_code='not_allowlisted' where id=:id"
                    ),
                    {"id": attempt.id},
                )
    finally:
        await engine.dispose()
