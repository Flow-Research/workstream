"""Independent SQL enforcement of attempt-bound execution configuration."""

from uuid import uuid4

import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.hashing import canonical_json_hash
from app.modules.projects.guide_compilation.models import ProjectGuideCompilationAttempt
from .helpers import context, identity, runtime_configuration, seed_database


def _row(values, configuration):
    attempt_identity = identity(context(values))
    return {
        **attempt_identity.model_dump(mode="json"),
        "id": uuid4(),
        "provider_idempotency_key": attempt_identity.provider_idempotency_key(),
        "status": "compilation_reserved",
        "runtime_configuration": configuration,
        "runtime_configuration_hash": canonical_json_hash(configuration)
        if configuration is not None
        else None,
    }


@pytest.mark.parametrize(
    "patch",
    [
        None,
        {"timeout_seconds": True},
        {"timeout_seconds": "30"},
        {"timeout_seconds": "invalid"},
        {"maximum_prompt_bytes": "invalid"},
        {"timeout_seconds": 0},
        {"timeout_seconds": 7201},
        {"maximum_prompt_bytes": 1023},
        {"maximum_prompt_bytes": 16777217},
        {"instructions": "x" * 16001},
        {"instructions_sha256": "sha256:" + "0" * 64},
        {"credential": "not-allowed"},
        {"model_provider": None},
        {"model_api": None},
        {
            "model_provider": "openai_compatible",
            "model_endpoint": "https://user:secret@models.example.test",
        },
    ],
)
async def test_sql_rejects_invalid_runtime_configuration(clean_postgres_database, patch):
    values = await seed_database(clean_postgres_database)
    configuration = (
        None if patch is None else runtime_configuration().model_dump(mode="json") | patch
    )
    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.begin() as connection:
            with pytest.raises(
                DBAPIError, match="compilation (runtime configuration|model endpoint)"
            ) as error:
                await connection.execute(
                    insert(ProjectGuideCompilationAttempt).values(**_row(values, configuration))
                )
            assert error.value.orig.sqlstate == "23514"
        # A complete control with the same lineage succeeds after the rejected insert.
        async with engine.begin() as connection:
            await connection.execute(
                insert(ProjectGuideCompilationAttempt).values(
                    **_row(values, runtime_configuration().model_dump(mode="json"))
                )
            )
    finally:
        await engine.dispose()


async def test_sql_runtime_configuration_and_hash_are_immutable(clean_postgres_database):
    values = await seed_database(clean_postgres_database)
    configuration = runtime_configuration().model_dump(mode="json")
    row = _row(values, configuration)
    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.begin() as connection:
            await connection.execute(insert(ProjectGuideCompilationAttempt).values(**row))
        for assignments in ["runtime_configuration=null", "runtime_configuration_hash=null"]:
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="runtime configuration is immutable") as error:
                    await connection.execute(
                        text(
                            "update project_guide_compilation_attempts set "
                            + assignments
                            + " where id=:id"
                        ),
                        {"id": row["id"]},
                    )
                assert error.value.orig.sqlstate == "23514"
    finally:
        await engine.dispose()


async def test_migrated_service_guards_use_provisioned_custody_not_external_literals(
    clean_postgres_database,
):
    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.connect() as connection:
            for name in [
                "guard_project_guide_compilation_insert",
                "guard_project_guide_setup_finalization",
            ]:
                definition = await connection.scalar(
                    text("select pg_get_functiondef(cast(:name as regprocedure))"),
                    {"name": name + "()"},
                )
                assert "link.issuer='workstream-internal'" not in definition
                assert "link.subject='workstream.project.setup'" not in definition
                assert "service_identity='workstream.project.setup'" in definition
                assert "actor_kind='service'" in definition
                assert "link.subject_kind='service'" in definition
                assert "link.status='active'" in definition
                assert "actor_ref_kind" in definition and "actor_profile" in definition
    finally:
        await engine.dispose()


async def test_sql_rejects_configuration_digest_substitution(clean_postgres_database):
    values = await seed_database(clean_postgres_database)
    row = _row(values, runtime_configuration().model_dump(mode="json"))
    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.begin() as connection:
            with pytest.raises(
                DBAPIError, match="compilation runtime configuration hash mismatch"
            ) as denied:
                await connection.execute(
                    insert(ProjectGuideCompilationAttempt).values(
                        **{**row, "runtime_configuration_hash": "sha256:" + "0" * 64}
                    )
                )
            assert denied.value.orig.sqlstate == "23514"
        async with engine.begin() as connection:
            await connection.execute(insert(ProjectGuideCompilationAttempt).values(**row))
    finally:
        await engine.dispose()
