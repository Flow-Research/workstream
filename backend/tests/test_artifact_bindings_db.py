"""PostgreSQL transaction proof for ART admission consumption."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.artifacts.models import (
    ArtifactBinding,
    ArtifactContent,
    SubmissionBundleAdmission, SubmissionBindingReceipt,
)
from app.modules.artifacts.submission_bindings import (
    SubmissionAdmissionConsumptionService,
)
from app.modules.artifacts.api import SubmissionAdmissionConsumptionError
from app.modules.tasks.models import Submission, SubmissionDispatch
from app.modules.tasks.models import AuditEvent
from test_artifact_bindings import _Allow, _lineage, _request, _replay_request


_TABLES = (
    ArtifactContent.__table__,
    SubmissionBundleAdmission.__table__,
    ArtifactBinding.__table__,
    Submission.__table__,
    AuditEvent.__table__, SubmissionBindingReceipt.__table__, SubmissionDispatch.__table__,
)


def _column_sql(column, dialect) -> str:
    name = dialect.identifier_preparer.quote(column.name)
    type_sql = column.type.compile(dialect=dialect)
    primary = " primary key" if column.primary_key else ""
    return f"{name} {type_sql}{primary}"


@asynccontextmanager
async def _isolated_binding_schema(database_url: str):
    engine = create_async_engine(database_url)
    schema = f"binding_{new_record_id().hex}"
    dialect = engine.dialect
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'create schema "{schema}"'))
            for table in _TABLES:
                columns = ", ".join(_column_sql(column, dialect) for column in table.columns)
                await connection.execute(
                    text(f'create table "{schema}"."{table.name}" ({columns})')
                )
            await connection.execute(
                text(
                    f'create unique index uq_binding_scope on "{schema}".artifact_bindings '
                    "(project_id, resource_type, resource_id, logical_role, scope_version)"
                )
            )
            await connection.execute(
                text(
                    f'alter table "{schema}".artifact_bindings add constraint '
                    "scope_version_predecessor check "
                    "((scope_version=1 and supersedes_binding_id is null) or "
                    "(scope_version>1 and supersedes_binding_id is not null))"
                )
            )
            await connection.execute(
                text(
                    f'create unique index uq_admission_consumer on "{schema}".'
                    "submission_bundle_admissions (consumed_by_submission_id) "
                    "where consumed_by_submission_id is not null"
                )
            )
            await connection.execute(
                text(
                    f'alter table "{schema}".submission_bundle_admissions add constraint '
                    "terminal_shape check ("
                    "(status='ready' and consumed_at is null and "
                    "consumed_by_submission_id is null and "
                    "consumed_by_submission_version is null and stale_at is null and "
                    "stale_reason is null) or "
                    "(status='consumed' and consumed_at is not null and "
                    "consumed_by_submission_id is not null and "
                    "consumed_by_submission_version > 0 and stale_at is null and "
                    "stale_reason is null) or "
                    "(status='stale' and consumed_at is null and "
                    "consumed_by_submission_id is null and "
                    "consumed_by_submission_version is null and stale_at is not null and "
                    "octet_length(stale_reason) between 1 and 500))"
                )
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        yield schema, factory
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'drop schema if exists "{schema}" cascade'))
        await engine.dispose()


async def _set_schema(session, schema: str) -> None:
    await session.execute(text(f'set local search_path to "{schema}"'))


async def _seed(session, schema: str, request) -> None:
    admission, content = _lineage(request)
    await _set_schema(session, schema)
    await session.execute(
        ArtifactContent.__table__.insert().values(
            id=content.id,
            sha256=content.sha256,
            byte_count=content.byte_count,
        )
    )
    await session.execute(
        SubmissionBundleAdmission.__table__.insert().values(
            **vars(admission), durable_intent_id=str(new_record_id()), put_attempt_id=str(new_record_id()),
            verified_replica_id=str(new_record_id()), verification_receipt_id=str(new_record_id()),
            put_operation_receipt_id=str(new_record_id()), put_observation_receipt_id=None,
            ready_at=text("now()"),
        )
    )


@pytest.mark.asyncio
async def test_postgresql_consumption_is_concurrent_and_rollback_safe(
    isolated_database_env: str,
) -> None:
    request = _request()
    request = type(request)(
        packet_sha256=request.packet_sha256,
        admission_id=request.admission_id,
        submission_id=request.submission_id,
        submission_version=2,
        task_context=request.task_context,
    )
    async with _isolated_binding_schema(isolated_database_env) as (schema, factory):
        async with factory.begin() as seed:
            await _seed(seed, schema, request)

        async def consume_once():
            async with factory() as session:
                async with session.begin():
                    await _set_schema(session, schema)
                    try:
                        return await SubmissionAdmissionConsumptionService(session, _Allow()).consume(request)
                    except SubmissionAdmissionConsumptionError as exc:
                        assert exc.code == "submission_bundle_admission_already_consumed"
                        return None

        contenders = [asyncio.create_task(consume_once()) for _ in range(2)]
        try:
            outcomes = await asyncio.gather(*contenders)
        finally:
            # Join both transactions before schema teardown even if one fails.
            await asyncio.gather(*contenders, return_exceptions=True)
        assert sum(result is not None for result in outcomes) == 1
        original = next(result for result in outcomes if result is not None)
        async with factory.begin() as session:
            await _set_schema(session, schema)
            replay = await SubmissionAdmissionConsumptionService(session, _Allow()).read_consumed(_replay_request(request))
            assert replay.replayed and replay.binding_id == original.binding_id
            assert replay.binding_decision_id == original.binding_decision_id
        async with factory() as session:
            await _set_schema(session, schema)
            status = await session.scalar(
                text("select status from submission_bundle_admissions where id=:id"),
                {"id": str(request.admission_id)},
            )
            binding_count = await session.scalar(
                text("select count(*) from artifact_bindings where resource_id=:id"),
                {"id": str(request.submission_id)},
            )
            assert status == "consumed"
            assert binding_count == 1

        first_competing = _request(submission_id=new_record_id())
        competing = replace(first_competing, admission_id=new_record_id())
        async with factory.begin() as seed:
            await _seed(seed, schema, first_competing)
            await _seed(seed, schema, competing)

        async def consume_competing(value):
            async with factory() as session:
                async with session.begin():
                    await _set_schema(session, schema)
                    try:
                        await SubmissionAdmissionConsumptionService(
                            session, _Allow()
                        ).consume(value)
                    except SubmissionAdmissionConsumptionError as exc:
                        return exc.code
                    return (await session.get(
                        SubmissionBundleAdmission, str(value.admission_id)
                    )).status

        contenders = [
            asyncio.create_task(consume_competing(first_competing)),
            asyncio.create_task(consume_competing(competing)),
        ]
        try:
            outcomes = await asyncio.gather(*contenders)
        finally:
            await asyncio.gather(*contenders, return_exceptions=True)
        assert sorted(outcomes) == [
            "consumed",
            "stale",
        ]
        async with factory() as session:
            await _set_schema(session, schema)
            binding_count = await session.scalar(
                text("select count(*) from artifact_bindings where resource_id=:id"),
                {"id": str(first_competing.submission_id)},
            )
            statuses = list(
                await session.scalars(
                    text(
                        "select status from submission_bundle_admissions "
                        "where id in (:first,:second) order by status"
                    ),
                    {
                        "first": str(first_competing.admission_id),
                        "second": str(competing.admission_id),
                    },
                )
            )
            assert binding_count == 1
            assert statuses == ["consumed", "stale"]

        rollback_request = _request()
        async with factory.begin() as seed:
            await _seed(seed, schema, rollback_request)
        async with factory() as session:
            transaction = await session.begin()
            await _set_schema(session, schema)
            await SubmissionAdmissionConsumptionService(session, _Allow()).consume(
                rollback_request
            )
            await transaction.rollback()
        async with factory() as session:
            await _set_schema(session, schema)
            status = await session.scalar(
                text(
                    "select status from submission_bundle_admissions where id=:id"
                ),
                {"id": str(rollback_request.admission_id)},
            )
            bindings = await session.scalar(
                text(
                    "select count(*) from artifact_bindings where resource_id=:id"
                ),
                {"id": str(rollback_request.submission_id)},
            )
            assert status == "ready"
            assert bindings == 0
