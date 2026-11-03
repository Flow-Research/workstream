"""Direct PostgreSQL attack proof for compilation custody."""

from __future__ import annotations

from tests.projects.guide_compilation.helpers import runtime_configuration

import json
import re

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.hashing import canonical_json_hash
from app.modules.projects.guide_compilation.repository import GuideCompilationRepository
from app.modules.projects.guide_compilation.contracts import accepted_compilation_result
from app.modules.projects.guide_compilation.validation import TERMINAL_FAILURE_CODES

from .helpers import context, identity, result, seed_database
from .runtime_fixtures import record_attempt_document_access


async def _reserved(database_url: str):
    values = await seed_database(database_url)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        _, attempt = await GuideCompilationRepository(session).reserve_attempt(
            identity(context(values)), runtime_configuration=runtime_configuration()
        )
    return engine, attempt


async def _uncertain_with_document_access(database_url: str):
    values = await seed_database(database_url)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    compilation_context = context(values)
    async with factory() as session, session.begin():
        repository = GuideCompilationRepository(session)
        _, attempt = await repository.reserve_attempt(
            identity(compilation_context), runtime_configuration=runtime_configuration()
        )
        await repository.mark_provider_uncertain(attempt.id)
    await record_attempt_document_access(factory, attempt.id, compilation_context)
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
    """Each current hash is required even when every other accepted fact is valid."""
    engine, attempt = await _uncertain_with_document_access(clean_postgres_database)
    accepted = accepted_compilation_result(result())
    hashes = accepted.component_hashes.model_dump(mode="json")
    assert hashes["schema_version"] == "project_guide_check_specification_hashes.v1"
    update = text(
        "update project_guide_compilation_attempts set status='provider_result_accepted',"
        "accepted_at=now(),canonical_result=cast(:result as json),result_hash=:hash,"
        "component_hashes=cast(:components as json) where id=:id"
    )
    base = {
        "id": attempt.id,
        "result": json.dumps(accepted.canonical_result),
        "hash": accepted.result_hash,
        "components": json.dumps(hashes),
    }
    try:
        async with engine.begin() as connection:
            valid_transition = await connection.begin_nested()
            await connection.execute(update, base)
            assert await connection.scalar(
                text("select status from project_guide_compilation_attempts where id=:id"),
                {"id": attempt.id},
            ) == "provider_result_accepted"
            await valid_transition.rollback()
            for name in hashes:
                if name == "schema_version":
                    continue
                null_hashes = {**hashes, name: None}
                with pytest.raises(
                    DBAPIError,
                    match="ck_project_guide_compilation_attempts_ck_compilation_at_31c4",
                ):
                    async with connection.begin_nested():
                        await connection.execute(
                            update, {**base, "components": json.dumps(null_hashes)}
                        )
            assert await connection.scalar(
                text("select status from project_guide_compilation_attempts where id=:id"),
                {"id": attempt.id},
            ) == "compilation_provider_uncertain"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_accepted_state_rejects_null_or_missing_json_schema_versions(
    clean_postgres_database: str,
) -> None:
    """A valid accepted transition cannot omit either current format discriminator."""
    engine, attempt = await _uncertain_with_document_access(clean_postgres_database)
    accepted = accepted_compilation_result(result())
    body = accepted.canonical_result
    hashes = accepted.component_hashes.model_dump(mode="json")
    update = text(
        "update project_guide_compilation_attempts set status='provider_result_accepted',"
        "accepted_at=now(),canonical_result=cast(:result as json),result_hash=:hash,"
        "component_hashes=cast(:components as json) where id=:id"
    )
    outcomes = {}
    try:
        async with engine.begin() as connection:
            for variant in (
                "control", "component_null", "component_missing",
                "result_null", "result_missing",
            ):
                candidate_body = dict(body)
                candidate_hashes = dict(hashes)
                if variant == "component_null":
                    candidate_hashes["schema_version"] = None
                elif variant == "component_missing":
                    candidate_hashes.pop("schema_version")
                elif variant == "result_null":
                    candidate_body["schema_version"] = None
                elif variant == "result_missing":
                    candidate_body.pop("schema_version")
                savepoint = await connection.begin_nested()
                try:
                    await connection.execute(update, {
                        "id": attempt.id,
                        "result": json.dumps(candidate_body),
                        "hash": canonical_json_hash(candidate_body),
                        "components": json.dumps(candidate_hashes),
                    })
                    outcomes[variant] = "accepted"
                except DBAPIError as exc:
                    message = str(exc.orig)
                    if "ck_project_guide_compilation_attempts_ck_compilation_at_31c4" in message:
                        outcomes[variant] = "component_hashes_constraint"
                    elif "ck_compilation_attempt_spec_result" in message:
                        outcomes[variant] = "result_schema_constraint"
                    else:
                        outcomes[variant] = message.splitlines()[0][:120]
                finally:
                    await savepoint.rollback()
            assert await connection.scalar(
                text("select status from project_guide_compilation_attempts where id=:id"),
                {"id": attempt.id},
            ) == "compilation_provider_uncertain"
    finally:
        await engine.dispose()
    assert outcomes == {
        "control": "accepted",
        "component_null": "component_hashes_constraint",
        "component_missing": "component_hashes_constraint",
        "result_null": "result_schema_constraint",
        "result_missing": "result_schema_constraint",
    }


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
                await connection.execute(text("truncate table project_guide_compilation_attempts"))
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
        allowlist = re.search(r"failure_code.*?ARRAY\[(.*?)\]", definition)
        assert allowlist is not None
        assert set(re.findall(r"'([^']+)'", allowlist.group(1))) == (TERMINAL_FAILURE_CODES)
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
