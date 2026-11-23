"""Retained provider cleanup remains exact-ID only after inference cutover."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.projects.guide_compilation.models import (
    ProjectGuideRuntimeAllocation,
)
from app.modules.projects.guide_compilation.runtime_resources import (
    RetainedGuideRuntimeCleanupCandidate,
    SqlAlchemyGuideRuntimeCleanupCustody,
    pending_runtime_resource_cleanup,
)
from .helpers import runtime_configuration

RETAINED_RUNTIME = "openai_agents_sdk"


def _historical_configuration():
    current = runtime_configuration()
    return {
        "capability_key": current.capability_key,
        "runtime_key": RETAINED_RUNTIME,
        "model_provider": "openai",
        "model": "gpt-5.6-terra",
        "model_api": "responses",
        "instruction_id": current.instruction_id,
        "instruction_version": current.instruction_version,
        "instructions": current.instructions,
        "instructions_sha256": current.instructions_sha256,
        "timeout_seconds": 30,
        "request_timeout_seconds": 30,
        "maximum_retries": 2,
        "retry_backoff_multiplier": 2,
        "retry_jitter": True,
        "retry_initial_delay_seconds": 1,
        "retry_max_delay_seconds": 30,
        "circuit_failure_threshold": 3,
        "circuit_cooldown_seconds": 60,
        "maximum_manifest_bytes": current.maximum_manifest_bytes,
        "maximum_documents": current.maximum_documents,
        "maximum_document_bytes": current.maximum_document_bytes,
        "maximum_total_document_bytes": current.maximum_total_document_bytes,
        "maximum_turns": current.maximum_turns,
        "maximum_hosted_tool_calls": 80,
        "compaction_threshold_tokens": 32_000,
        "container_expiry_minutes": 20,
        "file_expiry_seconds": 3600,
        "cleanup_timeout_seconds": 30,
    }


@asynccontextmanager
async def _retained_history(database_url, migration_lock, *, include_unknown=False):
    """Create genuine 0058 allocation facts, then exercise the real 0059 upgrade."""
    from tests.test_alembic import (
        _alembic_config,
        _execute,
        _seed_retained_guide_runtime_rows,
    )

    config = _alembic_config()
    prepared = False
    engine = None
    try:
        with migration_lock():
            await _execute(database_url, "drop schema public cascade; create schema public")
            await asyncio.to_thread(command.upgrade, config, "0058_compensation_unit_create")
            seeded = await _seed_retained_guide_runtime_rows(
                database_url,
                status="compilation_provider_uncertain",
                include_unknown=include_unknown,
            )
            await asyncio.to_thread(command.upgrade, config, "head")
        prepared = True
        engine = create_async_engine(database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        grant = SimpleNamespace(_sessions=sessions, _attempt_id=seeded["attempt_id"])
        yield grant, seeded["context"], seeded["allocation_ids"], seeded["unknown_id"]
    finally:
        if engine is not None:
            await engine.dispose()
        if not prepared:
            with migration_lock():
                await _execute(database_url, "drop schema public cascade; create schema public")
                await asyncio.to_thread(command.upgrade, config, "head")


@pytest.fixture
async def retained_history_case(clean_postgres_database, migration_lock):
    async with _retained_history(clean_postgres_database, migration_lock) as case:
        yield case


@pytest.fixture
async def retained_history_with_unknown_case(clean_postgres_database, migration_lock):
    async with _retained_history(
        clean_postgres_database, migration_lock, include_unknown=True
    ) as case:
        yield case


async def persisted_states(grant):
    async with grant._sessions() as session:
        rows = (
            await session.execute(
                select(
                    ProjectGuideRuntimeAllocation.id,
                    ProjectGuideRuntimeAllocation.state,
                    ProjectGuideRuntimeAllocation.deleted_at,
                ).where(ProjectGuideRuntimeAllocation.attempt_id == grant._attempt_id)
            )
        ).all()
    return {row.id: (row.state, row.deleted_at) for row in rows}


async def test_retained_cleanup_selection_preserves_old_config_and_exact_ids(
    retained_history_case,
):
    grant, context, identifiers, _unknown = retained_history_case
    async with grant._sessions() as session:
        selected = await pending_runtime_resource_cleanup(
            session, retained_runtime_key=RETAINED_RUNTIME
        )
    assert selected == (
        RetainedGuideRuntimeCleanupCandidate(
            grant._attempt_id, context.material.sha256, RETAINED_RUNTIME
        ),
    )
    custody = SqlAlchemyGuideRuntimeCleanupCustody(
        grant._sessions, grant._attempt_id, context.material.sha256, RETAINED_RUNTIME
    )
    resources = await custody.cleanup_resources()
    assert {item.allocation_id for item in resources} == identifiers
    assert {item.provider_id for item in resources} == {
        "cntr_retained",
        "file-retained",
        "cfile_retained",
    }


async def test_cleanup_failure_replay_and_deletion_are_monotonic(retained_history_case):
    grant, context, identifiers, _unknown = retained_history_case
    custody = SqlAlchemyGuideRuntimeCleanupCustody(
        grant._sessions, grant._attempt_id, context.material.sha256, RETAINED_RUNTIME
    )
    for identifier in identifiers:
        await custody.record_cleanup_failed(identifier)
    assert {state for state, _ in (await persisted_states(grant)).values()} == {"cleanup_failed"}
    for identifier in identifiers:
        await custody.record_deleted(identifier)
    before = await persisted_states(grant)
    assert all(state == "deleted" and timestamp is not None for state, timestamp in before.values())
    for identifier in identifiers:
        await custody.record_deleted(identifier)
        await custody.record_cleanup_failed(identifier)
    assert await persisted_states(grant) == before
    assert await custody.cleanup_resources() == ()


@pytest.mark.parametrize("field", ["attempt", "manifest", "runtime"])
async def test_cleanup_rejects_cross_scope_substitution(retained_history_case, field):
    grant, context, identifiers, _unknown = retained_history_case
    custody = SqlAlchemyGuideRuntimeCleanupCustody(
        grant._sessions,
        uuid4() if field == "attempt" else grant._attempt_id,
        "sha256:" + "f" * 64 if field == "manifest" else context.material.sha256,
        "foreign_runtime" if field == "runtime" else RETAINED_RUNTIME,
    )
    before = await persisted_states(grant)
    with pytest.raises(RuntimeError, match="cleanup scope is unavailable"):
        await custody.cleanup_resources()
    with pytest.raises(RuntimeError, match="cleanup scope is unavailable"):
        await custody.record_deleted(next(iter(identifiers)))
    assert await persisted_states(grant) == before


async def test_unknown_allocation_cannot_be_confirmed_or_selected(
    retained_history_with_unknown_case,
):
    grant, context, identifiers, unknown = retained_history_with_unknown_case
    custody = SqlAlchemyGuideRuntimeCleanupCustody(
        grant._sessions, grant._attempt_id, context.material.sha256, RETAINED_RUNTIME
    )
    assert {item.allocation_id for item in await custody.cleanup_resources()} == identifiers
    async with grant._sessions() as session:
        assert (
            await pending_runtime_resource_cleanup(session, retained_runtime_key=RETAINED_RUNTIME)
            == ()
        )
    with pytest.raises(ValueError, match="unknown resource deletion cannot be confirmed"):
        await custody.record_deleted(unknown)
    await custody.record_cleanup_failed(unknown)
    assert (await persisted_states(grant))[unknown] == ("uncertain", None)


async def test_current_provider_selection_cannot_redirect_retained_cleanup(
    retained_history_case,
):
    grant, _context, _identifiers, _unknown = retained_history_case
    async with grant._sessions() as session:
        assert (
            await pending_runtime_resource_cleanup(session, retained_runtime_key="another_runtime")
            == ()
        )
        assert (
            len(
                await pending_runtime_resource_cleanup(
                    session, retained_runtime_key=RETAINED_RUNTIME
                )
            )
            == 1
        )


@pytest.mark.parametrize("fail", [False, True])
async def test_cleanup_composition_uses_only_selected_typed_adapter(retained_history_case, fail):
    from app.adapters.projects import cleanup_project_guide_runtime_resources
    from workstream_external_services import (
        ExternalServiceAdapterFactory,
        ExternalServiceAdapterIdentity,
    )
    from app.modules.projects.api.guide_documents import (
        GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY,
        GuideRuntimeResourceCleanupAdapter,
    )

    grant, _context, identifiers, _unknown = retained_history_case
    calls = []

    class CleanupAdapter:
        identity = ExternalServiceAdapterIdentity(
            GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY,
            RETAINED_RUNTIME,
        )

        async def cleanup(self, custody):
            rows = await custody.cleanup_resources()
            calls.append({row.allocation_id for row in rows})
            if fail:
                raise RuntimeError("provider unavailable")
            for row in rows:
                await custody.record_deleted(row.allocation_id)
            return True

    cleanup_adapters = ExternalServiceAdapterFactory[
        GuideRuntimeResourceCleanupAdapter
    ](GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY)
    cleanup_adapters.register(RETAINED_RUNTIME, CleanupAdapter)

    result = await cleanup_project_guide_runtime_resources(
        grant._sessions,
        retained_runtime_key=RETAINED_RUNTIME,
        cleanup_adapter_factory=cleanup_adapters,
    )
    assert result == {"selected": 1, "completed": int(not fail)}
    assert calls == [identifiers]
    if fail:
        assert {state for state, _ in (await persisted_states(grant)).values()} == {"allocated"}


async def test_cleanup_composition_rejects_unregistered_retained_identity_without_constructing(
    retained_history_case,
):
    from app.adapters.projects import cleanup_project_guide_runtime_resources
    from workstream_external_services import ExternalServiceAdapterFactory
    from app.modules.projects.api.guide_documents import (
        GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY,
        GuideRuntimeResourceCleanupAdapter,
    )

    grant, _context, _identifiers, _unknown = retained_history_case
    cleanup_adapters = ExternalServiceAdapterFactory[
        GuideRuntimeResourceCleanupAdapter
    ](GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY)
    constructed = []
    cleanup_adapters.register(
        "another_runtime",
        lambda: constructed.append(True),
    )

    result = await cleanup_project_guide_runtime_resources(
        grant._sessions,
        retained_runtime_key=RETAINED_RUNTIME,
        cleanup_adapter_factory=cleanup_adapters,
    )

    assert result == {"selected": 1, "completed": 0}
    assert constructed == []
    assert {state for state, _ in (await persisted_states(grant)).values()} == {"allocated"}


async def test_cleanup_composition_rejects_wrong_adapter_identity_before_cleanup(
    retained_history_case,
):
    from app.adapters.projects import cleanup_project_guide_runtime_resources
    from workstream_external_services import (
        ExternalServiceAdapterFactory,
        ExternalServiceAdapterIdentity,
    )
    from app.modules.projects.api.guide_documents import (
        GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY,
        GuideRuntimeResourceCleanupAdapter,
    )

    grant, _context, _identifiers, _unknown = retained_history_case
    cleanup_calls = []

    class WrongIdentityAdapter:
        identity = ExternalServiceAdapterIdentity(
            GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY,
            "another_runtime",
        )

        async def cleanup(self, custody):
            cleanup_calls.append(custody)
            return True

    cleanup_adapters = ExternalServiceAdapterFactory[
        GuideRuntimeResourceCleanupAdapter
    ](GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY)
    cleanup_adapters.register(RETAINED_RUNTIME, WrongIdentityAdapter)

    result = await cleanup_project_guide_runtime_resources(
        grant._sessions,
        retained_runtime_key=RETAINED_RUNTIME,
        cleanup_adapter_factory=cleanup_adapters,
    )

    assert result == {"selected": 1, "completed": 0}
    assert cleanup_calls == []
    assert {state for state, _ in (await persisted_states(grant)).values()} == {"allocated"}
