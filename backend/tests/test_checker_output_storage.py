"""Direct PostgreSQL proofs for exact checker output intent and binding custody."""

from __future__ import annotations

from tests.checker_output_admission_helpers import seed_checker_output_relationships

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
import runpy
from types import SimpleNamespace
from uuid import UUID

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.models import (
    ArtifactPutAttempt,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.artifacts.service import ArtifactStorageOrchestrator
from projects.unified_policy_fixtures import create_standalone_unified_policy
from tests.artifact_store_helpers import artifact_preparation_limits, minted_source
from tests.test_artifact_admission import (
    _AllowArtifactAuthority,
    _admit_checker_output,
    _local_store,
    _namespace,
    _settings,
)


async def _store_verified_output(
    *,
    factory,
    settings,
    namespace,
    store,
    policy_bundle,
    source_path: Path,
    payload: bytes,
):
    """Store and independently verify one output using shared test infrastructure."""
    async with factory() as session:
        limits = replace(
            artifact_preparation_limits(),
            reservation_ttl_seconds=360,
            total_deadline_seconds=300,
        )
        relationships = await seed_checker_output_relationships(session, namespace, policy_bundle=policy_bundle)
        async with minted_source(
            source_path,
            payload,
            media_type="text/plain",
            limits=limits,
        ) as source:
            project_id, task_id, checker_run_id, admission = await _admit_checker_output(
                session,
                settings,
                namespace,
                source,
                relationships=relationships,
            )
            orchestrator = ArtifactStorageOrchestrator(
                session,
                store,
                namespace,
                settings,
                _AllowArtifactAuthority(),
            )
            await orchestrator.ensure_storage_namespace()
            assert await orchestrator.execute_committed_put(
                attempt_id=admission.attempt_id,
                source=source,
            ) == "stored_pending_verification"
            job_id = await session.scalar(
                select(ArtifactVerificationJob.id).where(
                    ArtifactVerificationJob.originating_put_attempt_id
                    == str(admission.attempt_id)
                )
            )
            assert job_id is not None
            await session.rollback()
            assert await orchestrator.verify_object(UUID(job_id)) == "verified"
            receipt_id = await session.scalar(
                select(ArtifactVerificationReceipt.id).where(
                    ArtifactVerificationReceipt.verification_job_id == job_id,
                    ArtifactVerificationReceipt.outcome == "verified",
                )
            )
            attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
            assert attempt is not None and receipt_id is not None
            assert attempt.replica_id is not None
            logical_role = attempt.logical_role
            replica_id = attempt.replica_id
            content_id = await session.scalar(
                text("select content_id from artifact_replicas where id=:replica_id"),
                {"replica_id": replica_id},
            )
            assert content_id is not None
            await session.rollback()
            return SimpleNamespace(
                factory=factory,
                project_id=project_id,
                task_id=task_id,
                checker_run_id=checker_run_id,
                put_attempt_id=str(admission.attempt_id),
                verification_job_id=str(job_id),
                replica_id=str(replica_id),
                verification_receipt_id=receipt_id,
                content_id=str(content_id),
                logical_role=logical_role,
                namespace=namespace,
                policy_bundle=policy_bundle,
            )


@asynccontextmanager
async def _verified_output(database_url: str, tmp_path: Path):
    """Create one real local put and independently verified checker output."""
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bootstrap, store = _local_store(settings, namespace)
    policy_bundle = await create_standalone_unified_policy(factory, namespace)
    try:
        case = await _store_verified_output(
            factory=factory,
            settings=settings,
            namespace=namespace,
            store=store,
            policy_bundle=policy_bundle,
            source_path=tmp_path / "checker-output",
            payload=b"exact checker output",
        )
        case.settings = settings
        case.store = store
        case.engine = engine
        yield case
    finally:
        bootstrap.close()
        await engine.dispose()


def _binding_values(case, **changes):
    values = {
        "id": str(new_record_id()),
        "content_id": case.content_id,
        "project_id": case.project_id,
        "resource_type": "checker_run",
        "resource_id": case.checker_run_id,
        "logical_role": case.logical_role,
        "scope_version": 1,
        "actor_id": ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
        "attribution_type": "service_identity",
        "put_attempt_id": case.put_attempt_id,
        "verification_receipt_id": case.verification_receipt_id,
        "supersedes_binding_id": None,
    }
    values.update(changes)
    return values


_INSERT_BINDING = text(
    """insert into artifact_bindings(
       id,content_id,project_id,resource_type,resource_id,logical_role,scope_version,
       actor_id,attribution_type,put_attempt_id,verification_receipt_id,supersedes_binding_id)
       values(:id,:content_id,:project_id,:resource_type,:resource_id,:logical_role,
       :scope_version,:actor_id,:attribution_type,:put_attempt_id,
       :verification_receipt_id,:supersedes_binding_id)"""
)

_ANCESTOR_MUTATIONS = {
    "attempt": (
        "artifact_put_attempts",
        "put_attempt_id",
        "cas_version=cas_version+1",
        "checker_output_put_attempt_custody",
        "checker output put attempt custody is immutable",
    ),
    "job": (
        "artifact_verification_jobs",
        "verification_job_id",
        "cas_version=cas_version+1",
        "checker_output_verification_job_custody",
        "checker output verification job custody is immutable",
    ),
    "replica": (
        "artifact_replicas",
        "replica_id",
        "provider_profile=provider_profile || '-changed'",
        "checker_output_replica_custody",
        "checker output replica custody is immutable",
    ),
}


async def _sealed_chain(session, case) -> tuple[bool, bool, bool]:
    values = []
    for table, attribute in (
        ("artifact_verification_jobs", "verification_job_id"),
        ("artifact_replicas", "replica_id"),
        ("artifact_put_attempts", "put_attempt_id"),
    ):
        value = await session.scalar(
            text(
                f"select checker_output_custody_sealed from {table} "
                "where id=:id"
            ),
            {"id": getattr(case, attribute)},
        )
        values.append(bool(value))
    return tuple(values)


async def _wait_for_lock(session, backend_pid: int) -> None:
    for _ in range(500):
        waiting = await session.scalar(
            text(
                "select exists(select 1 from pg_locks "
                "where pid=:pid and not granted)"
            ),
            {"pid": backend_pid},
        )
        if waiting:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("competing ancestry transaction did not wait")


async def _transaction(connection, isolation: str):
    transaction = await connection.begin()
    await connection.execute(text(f"set transaction isolation level {isolation}"))
    return transaction


def _ancestor_update(case, ancestor: str):
    table, attribute, assignment, _trigger, _error = _ANCESTOR_MUTATIONS[ancestor]
    return text(f"update {table} set {assignment} where id=:id"), {
        "id": getattr(case, attribute)
    }


def _invalid_ancestor_update(case, ancestor: str):
    table, attribute, _assignment, _trigger, _error = _ANCESTOR_MUTATIONS[ancestor]
    assignment = {
        "attempt": (
            "status='conflict', terminal_result_code='conflict', "
            "terminal_at=clock_timestamp(), cas_version=cas_version+1"
        ),
        "job": (
            "status='conflict', terminal_result_code='conflict', "
            "terminal_at=clock_timestamp(), cas_version=cas_version+1"
        ),
        "replica": "provider_object_ref=provider_object_ref || '-moved'",
    }[ancestor]
    return text(f"update {table} set {assignment} where id=:id"), {
        "id": getattr(case, attribute)
    }


async def _ancestor_without_seal(session, case, ancestor: str):
    table, attribute, _assignment, _trigger, _error = _ANCESTOR_MUTATIONS[ancestor]
    return await session.scalar(
        text(
            f"select to_jsonb(value) - 'checker_output_custody_sealed' "
            f"from {table} value where id=:id"
        ),
        {"id": getattr(case, attribute)},
    )


def _assert_concurrent_rejection(
    error: DBAPIError,
    *,
    isolation: str,
    expected: str,
) -> None:
    message = str(error)
    if isolation == "REPEATABLE READ":
        assert expected in message or "could not serialize access" in message
    else:
        assert expected in message


async def _binding_first_race(case, ancestor: str, isolation: str) -> None:
    async with case.factory() as session:
        before = await _ancestor_without_seal(session, case, ancestor)
    binder = await case.engine.connect()
    updater = await case.engine.connect()
    binding_transaction = await _transaction(binder, isolation)
    update_transaction = await _transaction(updater, isolation)
    pending_update = None
    try:
        updater_pid = await updater.scalar(text("select pg_backend_pid()"))
        assert await _sealed_chain(updater, case) == (False, False, False)
        assert await _ancestor_without_seal(updater, case, ancestor) == before
        await binder.execute(_INSERT_BINDING, _binding_values(case))
        statement, parameters = _ancestor_update(case, ancestor)
        pending_update = asyncio.create_task(updater.execute(statement, parameters))
        async with case.engine.connect() as observer:
            await _wait_for_lock(observer, updater_pid)
        await binding_transaction.commit()
        with pytest.raises(DBAPIError) as rejected:
            await pending_update
        _assert_concurrent_rejection(
            rejected.value,
            isolation=isolation,
            expected=_ANCESTOR_MUTATIONS[ancestor][4],
        )
        await update_transaction.rollback()
    finally:
        if pending_update is not None and not pending_update.done():
            pending_update.cancel()
            await asyncio.gather(pending_update, return_exceptions=True)
        if binding_transaction.is_active:
            await binding_transaction.rollback()
        if update_transaction.is_active:
            await update_transaction.rollback()
        await binder.close()
        await updater.close()
    async with case.factory() as session:
        assert await _sealed_chain(session, case) == (True, True, True)
        assert await _ancestor_without_seal(session, case, ancestor) == before
        assert await session.scalar(
            text(
                "select count(*) from artifact_bindings "
                "where put_attempt_id=:put_attempt_id"
            ),
            {"put_attempt_id": case.put_attempt_id},
        ) == 1


async def _update_first_race(case, ancestor: str, isolation: str) -> None:
    async with case.factory() as session:
        before = await _ancestor_without_seal(session, case, ancestor)
    updater = await case.engine.connect()
    binder = await case.engine.connect()
    update_transaction = await _transaction(updater, isolation)
    binding_transaction = await _transaction(binder, isolation)
    pending_binding = None
    try:
        binder_pid = await binder.scalar(text("select pg_backend_pid()"))
        statement, parameters = _invalid_ancestor_update(case, ancestor)
        await updater.execute(statement, parameters)
        assert await _sealed_chain(binder, case) == (False, False, False)
        assert await _ancestor_without_seal(binder, case, ancestor) == before
        pending_binding = asyncio.create_task(
            binder.execute(_INSERT_BINDING, _binding_values(case))
        )
        async with case.engine.connect() as observer:
            await _wait_for_lock(observer, binder_pid)
        await update_transaction.commit()
        with pytest.raises(DBAPIError) as rejected:
            await pending_binding
        _assert_concurrent_rejection(
            rejected.value,
            isolation=isolation,
            expected="checker output binding verified ancestry mismatch",
        )
        await binding_transaction.rollback()
    finally:
        if pending_binding is not None and not pending_binding.done():
            pending_binding.cancel()
            await asyncio.gather(pending_binding, return_exceptions=True)
        if update_transaction.is_active:
            await update_transaction.rollback()
        if binding_transaction.is_active:
            await binding_transaction.rollback()
        await updater.close()
        await binder.close()
    async with case.factory() as session:
        assert await _sealed_chain(session, case) == (False, False, False)
        assert await _ancestor_without_seal(session, case, ancestor) != before
        assert await session.scalar(
            text(
                "select count(*) from artifact_bindings "
                "where put_attempt_id=:put_attempt_id"
            ),
            {"put_attempt_id": case.put_attempt_id},
        ) == 0


@pytest.mark.asyncio
async def test_exact_verified_checker_output_binding_and_generic_binding_remain_valid(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    async with _verified_output(isolated_database_env, tmp_path) as case:
        async with case.factory() as session, session.begin():
            await session.execute(_INSERT_BINDING, _binding_values(case))
            await session.execute(
                _INSERT_BINDING,
                _binding_values(
                    case,
                    id=str(new_record_id()),
                    resource_type="task",
                    resource_id=case.task_id,
                    logical_role="diagnostic",
                    actor_id="test-actor",
                    attribution_type="human",
                    put_attempt_id=None,
                    verification_receipt_id=None,
                ),
            )
        async with case.factory() as session:
            assert await session.scalar(
                text(
                    "select count(*) from artifact_bindings "
                    "where resource_type in ('checker_run','task')"
                )
            ) == 2


@pytest.mark.asyncio
async def test_checker_binding_rejects_null_verification_terminal_result(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    async with _verified_output(isolated_database_env, tmp_path) as case:
        async with case.factory() as session:
            control = await session.begin()
            await session.execute(_INSERT_BINDING, _binding_values(case))
            assert await _sealed_chain(session, case) == (True, True, True)
            await control.rollback()

        async with case.factory() as session, session.begin():
            await session.execute(
                text(
                    "update artifact_verification_jobs "
                    "set terminal_result_code=null where id=:id"
                ),
                {"id": case.verification_job_id},
            )

        with pytest.raises(
            DBAPIError,
            match="checker output binding verified ancestry mismatch",
        ):
            async with case.factory() as session, session.begin():
                await session.execute(_INSERT_BINDING, _binding_values(case))
        async with case.factory() as session:
            assert await _sealed_chain(session, case) == (False, False, False)
            assert await session.scalar(
                text(
                    "select count(*) from artifact_bindings "
                    "where put_attempt_id=:put_attempt_id"
                ),
                {"put_attempt_id": case.put_attempt_id},
            ) == 0

        async with case.factory() as session:
            mutation = await session.begin()
            definition = await session.scalar(
                text(
                    "select pg_get_functiondef("
                    "'guard_checker_output_binding_insert()'::regprocedure)"
                )
            )
            assert definition is not None
            null_safe = "job.terminal_result_code IS DISTINCT FROM 'verified'"
            old_comparison = "job.terminal_result_code <> 'verified'"
            assert definition.count(null_safe) == 1
            await session.execute(text(definition.replace(null_safe, old_comparison)))
            await session.execute(_INSERT_BINDING, _binding_values(case))
            assert await _sealed_chain(session, case) == (True, True, True)
            await mutation.rollback()

        async with case.factory() as session:
            assert await _sealed_chain(session, case) == (False, False, False)
            assert await session.scalar(
                text(
                    "select count(*) from artifact_bindings "
                    "where put_attempt_id=:put_attempt_id"
                ),
                {"put_attempt_id": case.put_attempt_id},
            ) == 0


@pytest.mark.asyncio
async def test_checker_binding_rejects_mixed_or_foreign_ancestry(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    async with _verified_output(isolated_database_env, tmp_path) as case:
        other = await _store_verified_output(
            factory=case.factory,
            settings=case.settings,
            namespace=case.namespace,
            store=case.store,
            policy_bundle=case.policy_bundle,
            source_path=tmp_path / "other-checker-output",
            payload=b"distinct independently verified checker output",
        )
        assert case.put_attempt_id != other.put_attempt_id
        assert case.verification_receipt_id != other.verification_receipt_id
        assert case.content_id != other.content_id
        assert case.namespace.namespace_fingerprint == other.namespace.namespace_fingerprint

        async with case.factory() as session, session.begin():
            control = await session.begin_nested()
            await session.execute(_INSERT_BINDING, _binding_values(case))
            await session.execute(_INSERT_BINDING, _binding_values(other))
            assert await session.scalar(
                text("select count(*) from artifact_bindings where resource_type='checker_run'")
            ) == 2
            await control.rollback()
            assert await session.scalar(
                text("select count(*) from artifact_bindings where resource_type='checker_run'")
            ) == 0

        mixed_lineages = (
            {
                "put_attempt_id": other.put_attempt_id,
                "verification_receipt_id": other.verification_receipt_id,
                "content_id": other.content_id,
            },
            {"put_attempt_id": other.put_attempt_id},
            {"verification_receipt_id": other.verification_receipt_id},
            {"content_id": other.content_id},
        )
        for mixed in mixed_lineages:
            with pytest.raises(
                DBAPIError,
                match="checker output binding verified ancestry mismatch",
            ):
                async with case.factory() as session, session.begin():
                    await session.execute(
                        _INSERT_BINDING,
                        _binding_values(case, **mixed),
                    )
        async with case.factory() as session:
            assert await session.scalar(
                text("select count(*) from artifact_bindings where resource_type='checker_run'")
            ) == 0


@pytest.mark.asyncio
async def test_checker_attempt_static_custody_allows_only_execution_lifecycle(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    async with _verified_output(isolated_database_env, tmp_path) as case:
        for assignment in (
            "checker_request_digest='sha256:' || repeat('b',64)",
            "request_digest='sha256:' || repeat('b',64)",
            "sha256='sha256:' || repeat('b',64)",
            "submission_id='00000000-0000-7000-8000-000000000001'::uuid",
            "logical_role='substituted-slot'",
            "namespace_fingerprint='sha256:' || repeat('b',64)",
        ):
            with pytest.raises(
                DBAPIError,
                match="checker output put attempt custody is immutable",
            ):
                async with case.factory() as session, session.begin():
                    await session.execute(
                        text(
                            f"update artifact_put_attempts set {assignment} where id=:id"
                        ),
                        {"id": case.put_attempt_id},
                    )
        with pytest.raises(
            DBAPIError,
            match="checker output put attempt custody is immutable",
        ):
            async with case.factory() as session, session.begin():
                await session.execute(
                    text("delete from artifact_put_attempts where id=:id"),
                    {"id": case.put_attempt_id},
                )
        with pytest.raises(
            DBAPIError,
            match="checker output put attempt custody is immutable",
        ):
            async with case.factory() as session, session.begin():
                await session.execute(text("truncate artifact_put_attempts cascade"))
        async with case.factory() as session, session.begin():
            await session.execute(
                text(
                    "update artifact_put_attempts set cas_version=cas_version+1, "
                    "updated_at=clock_timestamp() where id=:id"
                ),
                {"id": case.put_attempt_id},
            )


@pytest.mark.asyncio
async def test_binding_seals_exact_ancestry_but_preserves_replica_health(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    async with _verified_output(isolated_database_env, tmp_path) as case:
        for ancestor in _ANCESTOR_MUTATIONS:
            table, attribute, _assignment, _trigger, _error = _ANCESTOR_MUTATIONS[ancestor]
            with pytest.raises(DBAPIError, match="seal requires binding"):
                async with case.factory() as session, session.begin():
                    await session.execute(
                        text(
                            f"update {table} set checker_output_custody_sealed=true "
                            "where id=:id"
                        ),
                        {"id": getattr(case, attribute)},
                    )

        async with case.factory() as session, session.begin():
            await session.execute(
                text(
                    "update artifact_put_attempts set cas_version=cas_version+1 "
                    "where id=:id"
                ),
                {"id": case.put_attempt_id},
            )
            await session.execute(
                text(
                    "update artifact_verification_jobs set cas_version=cas_version+1 "
                    "where id=:id"
                ),
                {"id": case.verification_job_id},
            )
            await session.execute(
                text(
                    "update artifact_replicas set last_reconciled_at=clock_timestamp(), "
                    "updated_at=clock_timestamp() where id=:id"
                ),
                {"id": case.replica_id},
            )
            await session.execute(_INSERT_BINDING, _binding_values(case))
            assert await _sealed_chain(session, case) == (True, True, True)

        for ancestor in _ANCESTOR_MUTATIONS:
            table, attribute, assignment, _trigger, error = _ANCESTOR_MUTATIONS[ancestor]
            with pytest.raises(DBAPIError, match=error):
                async with case.factory() as session, session.begin():
                    await session.execute(
                        text(f"update {table} set {assignment} where id=:id"),
                        {"id": getattr(case, attribute)},
                    )
            with pytest.raises(DBAPIError, match=error):
                async with case.factory() as session, session.begin():
                    await session.execute(
                        text(f"delete from {table} where id=:id"),
                        {"id": getattr(case, attribute)},
                    )

        async with case.factory() as session, session.begin():
            await session.execute(
                text(
                    "update artifact_replicas set verification_state='missing', "
                    "availability_state='unavailable', integrity_state='invalid', "
                    "last_reconciled_at=clock_timestamp(), updated_at=clock_timestamp() "
                    "where id=:id"
                ),
                {"id": case.replica_id},
            )
            assert await _sealed_chain(session, case) == (True, True, True)

        for ancestor in _ANCESTOR_MUTATIONS:
            table, attribute, assignment, trigger, _error = _ANCESTOR_MUTATIONS[ancestor]
            async with case.factory() as session:
                before = await session.scalar(
                    text(f"select to_jsonb(value) from {table} value where id=:id"),
                    {"id": getattr(case, attribute)},
                )
                transaction = await session.begin_nested()
                await session.execute(text(f"alter table {table} disable trigger {trigger}"))
                await session.execute(
                    text(f"update {table} set {assignment} where id=:id"),
                    {"id": getattr(case, attribute)},
                )
                after = await session.scalar(
                    text(f"select to_jsonb(value) from {table} value where id=:id"),
                    {"id": getattr(case, attribute)},
                )
                assert after != before
                await transaction.rollback()
                assert await session.scalar(
                    text(f"select to_jsonb(value) from {table} value where id=:id"),
                    {"id": getattr(case, attribute)},
                ) == before
                await session.rollback()


@pytest.mark.asyncio
async def test_binding_rollback_removes_all_ancestry_seals(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    async with _verified_output(isolated_database_env, tmp_path) as case:
        binding_id = str(new_record_id())
        async with case.factory() as session:
            transaction = await session.begin()
            await session.execute(
                _INSERT_BINDING,
                _binding_values(case, id=binding_id),
            )
            assert await _sealed_chain(session, case) == (True, True, True)
            await transaction.rollback()
        async with case.factory() as session:
            assert await _sealed_chain(session, case) == (False, False, False)
            assert await session.scalar(
                text("select count(*) from artifact_bindings where id=:id"),
                {"id": binding_id},
            ) == 0


@pytest.mark.parametrize("ancestor", tuple(_ANCESTOR_MUTATIONS))
@pytest.mark.parametrize("isolation", ("READ COMMITTED", "REPEATABLE READ"))
@pytest.mark.asyncio
async def test_binding_and_ancestor_updates_serialize_fail_closed(
    isolated_database_env: str,
    tmp_path: Path,
    ancestor: str,
    isolation: str,
) -> None:
    async with _verified_output(isolated_database_env, tmp_path) as case:
        await _binding_first_race(case, ancestor, isolation)

        other = await _store_verified_output(
            factory=case.factory,
            settings=case.settings,
            namespace=case.namespace,
            store=case.store,
            policy_bundle=case.policy_bundle,
            source_path=tmp_path / f"update-first-{ancestor}",
            payload=f"update-first-{isolation}-{ancestor}".encode(),
        )
        other.engine = case.engine
        await _update_first_race(other, ancestor, isolation)


@pytest.mark.asyncio
async def test_artifact_binding_truncate_custody_blocks_direct_and_cascade_deletion(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    """Table-wide deletion cannot bypass immutable artifact binding custody."""
    async with _verified_output(isolated_database_env, tmp_path) as case:
        binding_id = str(new_record_id())
        async with case.factory() as session, session.begin():
            await session.execute(
                _INSERT_BINDING,
                _binding_values(case, id=binding_id),
            )

        for statement in (
            "truncate artifact_bindings",
            "truncate artifact_contents cascade",
        ):
            with pytest.raises(DBAPIError, match="artifact_bindings rows are immutable"):
                async with case.factory() as session, session.begin():
                    await session.execute(text(statement))
            async with case.factory() as session:
                assert await session.scalar(
                    text("select count(*) from artifact_bindings where id=:id"),
                    {"id": binding_id},
                ) == 1

        async with case.factory() as session:
            transaction = await session.begin()
            try:
                await session.execute(
                    text(
                        "alter table artifact_bindings disable trigger "
                        "trg_artifact_bindings_no_truncate"
                    )
                )
                await session.execute(text("truncate artifact_bindings"))
                assert await session.scalar(
                    text("select count(*) from artifact_bindings where id=:id"),
                    {"id": binding_id},
                ) == 0
            finally:
                await transaction.rollback()

        async with case.factory() as session:
            assert await session.scalar(
                text("select count(*) from artifact_bindings where id=:id"),
                {"id": binding_id},
            ) == 1
            trigger_definition = await session.scalar(
                text(
                    "select pg_get_triggerdef(oid) from pg_trigger "
                    "where tgrelid='artifact_bindings'::regclass "
                    "and tgname='trg_artifact_bindings_no_truncate'"
                )
            )
            assert trigger_definition is not None
            assert "BEFORE TRUNCATE" in trigger_definition
            assert "EXECUTE FUNCTION reject_artifact_fact_mutation()" in trigger_definition


@pytest.mark.asyncio
async def test_binding_guard_uses_only_artifact_ancestry_and_exact_owner_fks(
    isolated_database_env: str,
) -> None:
    engine = create_async_engine(isolated_database_env)
    try:
        async with engine.connect() as connection:
            definition = await connection.scalar(
                text(
                    "select pg_get_functiondef("
                    "'guard_checker_output_binding_insert()'::regprocedure)"
                )
            )
            assert definition is not None
            assert "checker_runs" not in definition
            assert "submissions" not in definition
            assert "workstream_tasks" not in definition
            constraints = dict(
                (await connection.execute(text(
                    "select conname,pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid='artifact_put_attempts'::regclass and conname in "
                    "('fk_artifact_put_attempts_checker_run_ownership',"
                    "'fk_artifact_put_attempts_submission_version',"
                    "'fk_artifact_put_attempts_task_project')"
                ))).all()
            )
            assert set(constraints) == {
                "fk_artifact_put_attempts_checker_run_ownership",
                "fk_artifact_put_attempts_submission_version",
                "fk_artifact_put_attempts_task_project",
            }
            assert "FOREIGN KEY (checker_run_id, task_id, submission_id)" in constraints[
                "fk_artifact_put_attempts_checker_run_ownership"
            ]
            assert "FOREIGN KEY (submission_id, task_id, submission_version)" in constraints[
                "fk_artifact_put_attempts_submission_version"
            ]
            assert "FOREIGN KEY (task_id, project_id)" in constraints[
                "fk_artifact_put_attempts_task_project"
            ]
    finally:
        await engine.dispose()


async def _restore_pre_0007_schema(connection) -> None:
    """Remove only 0007 custody inside the caller's rollback-only transaction."""
    for table, trigger in (
        ("artifact_bindings", "checker_output_binding_seal"),
        ("artifact_bindings", "checker_output_binding_insert"),
        ("artifact_bindings", "trg_artifact_bindings_no_truncate"),
        ("artifact_verification_jobs", "checker_output_verification_job_custody"),
        ("artifact_replicas", "checker_output_replica_custody"),
        ("artifact_put_attempts", "checker_output_put_attempt_custody"),
        ("artifact_put_attempts", "checker_output_put_attempt_no_truncate"),
    ):
        await connection.execute(text(f"drop trigger {trigger} on {table}"))
    for function in (
        "seal_checker_output_binding_ancestry()",
        "guard_checker_output_binding_insert()",
        "guard_checker_output_verification_job_custody()",
        "guard_checker_output_replica_custody()",
        "guard_checker_output_put_attempt_custody()",
        "guard_checker_output_put_attempt_truncate()",
    ):
        await connection.execute(text(f"drop function {function}"))
    for constraint in (
        "ck_artifact_bindings_checker_output_lineage",
        "fk_artifact_bindings_checker_put_attempt",
        "fk_artifact_bindings_checker_verification_receipt",
    ):
        await connection.execute(
            text(f"alter table artifact_bindings drop constraint {constraint}")
        )
    for index in (
        "ix_artifact_bindings_put_attempt_id",
        "ix_artifact_bindings_verification_receipt_id",
    ):
        await connection.execute(text(f"drop index {index}"))
    await connection.execute(
        text(
            "alter table artifact_bindings drop column put_attempt_id, "
            "drop column verification_receipt_id"
        )
    )
    for constraint in (
        "fk_artifact_put_attempts_task_project",
        "fk_artifact_put_attempts_checker_run_ownership",
        "fk_artifact_put_attempts_submission_version",
        "ck_artifact_put_attempts_checker_request_digest",
        "ck_artifact_put_attempts_producer_reference",
    ):
        await connection.execute(
            text(f"alter table artifact_put_attempts drop constraint {constraint}")
        )
    await connection.execute(text("drop index ix_artifact_put_attempts_submission_id"))
    await connection.execute(
        text(
            "alter table artifact_put_attempts add constraint "
            "ck_artifact_put_attempts_producer_reference check ("
            "(producer_request_type='guide' and guide_source_item_id is not null "
            "and checker_run_id is null and task_id is null and logical_role is null) or "
            "(producer_request_type='checker_output' and guide_source_item_id is null "
            "and checker_run_id is not null and task_id is not null "
            "and octet_length(logical_role) between 1 and 100) or "
            "(producer_request_type='submission_bundle' and guide_source_item_id is null "
            "and checker_run_id is null and task_id is not null and logical_role is null))"
        )
    )
    await connection.execute(
        text(
            "alter table artifact_put_attempts drop column submission_id, "
            "drop column submission_version, drop column checker_request_digest, "
            "drop column checker_output_custody_sealed"
        )
    )
    await connection.execute(
        text(
            "alter table artifact_verification_jobs "
            "drop column checker_output_custody_sealed"
        )
    )
    await connection.execute(
        text(
            "alter table artifact_replicas "
            "drop column checker_output_custody_sealed"
        )
    )


def _run_0007_upgrade(connection) -> None:
    module = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "alembic/versions/0007_checker_output_custody.py"
        )
    )
    with Operations.context(MigrationContext.configure(connection)):
        module["upgrade"]()


@pytest.mark.asyncio
async def test_migration_refuses_unprovable_or_inconsistent_retained_checker_attempts(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    """The old schema lacks evaluation/slot custody, so retained attempts fail closed."""
    async with _verified_output(isolated_database_env, tmp_path / "retained") as case:
        async with case.factory() as seed_session:
            _, other_task_id, _ = await seed_checker_output_relationships(
                seed_session,
                case.namespace,
                policy_bundle=case.policy_bundle,
            )
        async with case.factory() as session:
            connection = await session.connection()
            await _restore_pre_0007_schema(connection)
            before = await session.scalar(
                text("select to_jsonb(a) from artifact_put_attempts a where id=:id"),
                {"id": case.put_attempt_id},
            )
            with pytest.raises(
                DBAPIError,
                match="retained checker output request custody is unprovable",
            ):
                async with connection.begin_nested():
                    await connection.run_sync(_run_0007_upgrade)
            assert await session.scalar(
                text("select to_jsonb(a) from artifact_put_attempts a where id=:id"),
                {"id": case.put_attempt_id},
            ) == before

            await session.execute(
                text("update artifact_put_attempts set task_id=:task where id=:id"),
                {"id": case.put_attempt_id, "task": other_task_id},
            )
            mismatched = await session.scalar(
                text("select to_jsonb(a) from artifact_put_attempts a where id=:id"),
                {"id": case.put_attempt_id},
            )
            with pytest.raises(
                DBAPIError,
                match="retained checker output attempt ownership is inconsistent",
            ):
                async with connection.begin_nested():
                    await connection.run_sync(_run_0007_upgrade)
            assert await session.scalar(
                text("select to_jsonb(a) from artifact_put_attempts a where id=:id"),
                {"id": case.put_attempt_id},
            ) == mismatched
            await session.rollback()
