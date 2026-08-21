"""Committed dispatch handoff, cancellation, and provider-boundary proof."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.projects.guide_compilation.service import GuideCompilationService

from .helpers import context, identity, seed_database, service_actor
from .test_authorized_execution_service import _execution_service, _preflight
from .test_authorized_request_service import _authorized_service, _request, _seed_human


async def _requested(database_url: str):
    values = await seed_database(database_url)
    human, link, _grant = await _seed_human(database_url, values)
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            receipt = await _authorized_service(session, actor).authorize_request(
                actor=actor,
                facts=_request(values),
                identity=identity(context(values)),
            )
    finally:
        await engine.dispose()
    return values, receipt


@pytest.mark.asyncio
async def test_fence_is_visible_to_a_fresh_process_before_any_provider_call(
    clean_postgres_database: str,
) -> None:
    values, requested = await _requested(clean_postgres_database)
    service, facts = service_actor(values), _preflight(values, requested.attempt_id)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            receipt = await _execution_service(session, service).fence_dispatch(
                actor=service, facts=facts
            )
        script = (
            "import asyncio,asyncpg,json,os\n"
            "async def main():\n"
            " c=await asyncpg.connect(os.environ['WORKSTREAM_TEST_DATABASE_URL'].replace('+asyncpg',''));\n"
            " r=await c.fetchrow('select status,provider_idempotency_key::text from "
            "project_guide_compilation_attempts where id=$1::uuid',os.environ['ATTEMPT']);\n"
            " await c.close();print(json.dumps(dict(r)))\n"
            "asyncio.run(main())"
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            env={
                **os.environ,
                "WORKSTREAM_TEST_DATABASE_URL": clean_postgres_database,
                "ATTEMPT": str(requested.attempt_id),
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        assert process.returncode == 0, stderr.decode()
        observed = json.loads(stdout)
        assert observed == {
            "status": "compilation_provider_uncertain",
            "provider_idempotency_key": str(receipt.provider_idempotency_key),
        }
    finally:
        await engine.dispose()


class _CancelledPreflight:
    async def authorize_execute_preflight(self, **_kwargs):
        raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_cancellation_before_fence_commit_leaves_attempt_reserved(
    clean_postgres_database: str,
) -> None:
    values, requested = await _requested(clean_postgres_database)
    service, facts = service_actor(values), _preflight(values, requested.attempt_id)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            with pytest.raises(asyncio.CancelledError):
                await GuideCompilationService(
                    session, _CancelledPreflight()  # type: ignore[arg-type]
                ).fence_dispatch(actor=service, facts=facts)
        async with factory() as session:
            status = await session.scalar(
                text("select status from project_guide_compilation_attempts where id=:id"),
                {"id": requested.attempt_id},
            )
            await session.rollback()
        assert status == "compilation_reserved"
    finally:
        await engine.dispose()


def test_coordinator_cannot_import_or_call_a_provider() -> None:
    source = (
        Path(__file__).resolve().parents[3]
        / "app/modules/projects/guide_compilation/service.py"
    ).read_text(encoding="utf-8")
    assert "compile_project_guide" not in source
    assert "app.workers" not in source
    assert "celery" not in source.lower()
