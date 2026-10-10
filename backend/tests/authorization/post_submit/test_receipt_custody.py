"""Real AUTH receipts cannot be borrowed for another run, lease or terminal outcome."""

from contextlib import nullcontext
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.adapters.auth import post_submit_execution_authority
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    ExecuteFacts, ExecutionLease, FinalizeAuthorityFacts, execution_authority_digest,
)
from app.modules.checkers.execution_repository import ExecutionRepository, reservation
from app.modules.checkers.models import CheckerRun, CheckerResult
from app.modules.checkers.post_submit_contracts import make_post_submit_result
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import AuditEvent
from tests.checkers.execution.support import live_executor, reserve
from tests.checkers.execution.test_concurrency import final_facts
from tests.checkers.execution.material_storage_helpers import stage_terminal
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_post_submit_materialization import Consumer


async def snapshot(h):
    async with h.factory() as session:
        return (
            list((await session.scalars(text("select to_jsonb(r) from checker_runs r order by id"))).all()),
            await session.scalar(select(func.count()).select_from(AuditEvent)),
            await session.scalar(select(func.count()).select_from(CheckerResult)),
            await session.scalar(select(func.count()).select_from(OutboxEvent)),
        )


async def next_lease(h, borrowed=None, *, shadow=False):
    """Simulate a faulty owner attaching a different real receipt after AUTH consumption."""
    async with h.factory() as session, session.begin():
        async with post_submit_execution_authority(session).prepare_execution(h.request) as prepared:
            repo = ExecutionRepository(session)
            run = await repo.lock_current(h.request)
            lease = ExecutionLease(
                reservation=reservation(run), lease_id=new_record_id(),
                lease_generation=run.worker_lease_generation + 1,
                expires_at=await repo.now() + timedelta(seconds=300),
            )
            facts = ExecuteFacts(request=h.request, lease=lease)
            receipt = await prepared.consume(facts)
            run.worker_lease_id = str(lease.lease_id)
            run.worker_lease_generation = lease.lease_generation
            run.worker_lease_expires_at = lease.expires_at
            run.execute_evidence_id = str(borrowed if borrowed is not None else receipt.evidence_id)
            await session.flush()
            if shadow:
                for table in ("checker_runs", "audit_events", "actor_profiles", "actor_identity_links"):
                    await session.execute(text(f"CREATE TEMP TABLE {table} ON COMMIT DROP AS SELECT * FROM public.{table} WHERE false"))
                await session.execute(text("SET LOCAL search_path = pg_temp, public, pg_catalog"))
            if borrowed is None:
                digest = await session.scalar(text(
                    "select public.checker_post_submit_authority_digest(r,'execute') "
                    "from public.checker_runs r where r.id=:id"
                ), {"id": run.id})
                assert digest == execution_authority_digest(facts)
            return lease


@pytest.mark.parametrize(
    "substitution",
    ["previous_lease", "foreign_attempt", "material_read", "nonexistent", "shadow_tables"],
)
async def test_execute_receipt_substitution_rejected(tmp_path, isolated_database_env, substitution, monkeypatch):
    import app.modules.checkers.execution as execution
    monkeypatch.setattr(execution, "LEASE_SECONDS", 5)
    async with material_fixture(tmp_path / "one", isolated_database_env) as h:
        await reserve(h)
        lease, _ = await live_executor(h)._claim(h.request)
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
            borrowed = UUID(run.execute_evidence_id)
        if substitution == "foreign_attempt":
            async with material_fixture(tmp_path / "two", isolated_database_env,
                                        provision_services=False, storage_settings=h.settings) as other:
                await reserve(other)
                foreign, _ = await live_executor(other)._claim(other.request)
                async with h.factory() as session:
                    borrowed = UUID((await session.get(CheckerRun, str(foreign.reservation.attempt_id))).execute_evidence_id)
        elif substitution == "material_read":
            await h.service.materialize(ExecuteFacts(request=h.request, lease=lease), Consumer(h.files))
            async with h.factory() as session:
                borrowed = UUID(await session.scalar(select(AuditEvent.id).where(
                    AuditEvent.action_id == "artifact.post_submit.checker_input.materialize",
                    AuditEvent.resource_id == str(lease.reservation.attempt_id),
                )))
        elif substitution == "nonexistent":
            borrowed = new_record_id()
        await wait_for_expiry(h, lease)
        before = await snapshot(h)
        with pytest.raises(IntegrityError, match="receipt custody|foreign key"):
            await next_lease(h, borrowed, shadow=substitution == "shadow_tables")
        assert await snapshot(h) == before
        valid = await next_lease(h)
        assert valid.lease_generation == lease.lease_generation + 1


@pytest.mark.parametrize("substitution", ["result", "material", "execute_chain"])
async def test_final_receipt_commits_only_exact_outcome(
    tmp_path, isolated_database_env, substitution, monkeypatch
):
    import app.modules.checkers.execution as execution

    if substitution == "execute_chain":
        monkeypatch.setattr(execution, "LEASE_SECONDS", 1)
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        lease, _ = await live_executor(h)._claim(h.request)
        old_execute = None
        if substitution == "execute_chain":
            async with h.factory() as session:
                old_execute = UUID((await session.get(CheckerRun, str(lease.reservation.attempt_id))).execute_evidence_id)
            await wait_for_expiry(h, lease)
            lease = await next_lease(h)
        source = await final_facts(h, lease)
        result = make_post_submit_result(
            request_id=h.request.evaluation_request_id, request_digest=h.request.request_sha256,
            attempt_id=lease.reservation.attempt_id, result_id=lease.reservation.result_id,
            evaluation_generation=h.request.evaluation_generation, outcome="infrastructure_failed",
            member_results=(), infrastructure_failure_code="deadline_exceeded",
        )
        facts = source.model_copy(update={"result": result})
        stored = facts
        if substitution == "result":
            changed = make_post_submit_result(**(result.model_dump(exclude={"result_digest"}) | {
                "infrastructure_failure_code": "invalid_output",
            }))
            stored = facts.model_copy(update={"result": changed})
        elif substitution == "material":
            stored = facts.model_copy(update={
                "material": None, "input_materialization_evidence_id": None,
            })
        before = await snapshot(h)
        with pytest.raises(IntegrityError, match="receipt custody"):
            async with h.factory() as session, session.begin():
                async with post_submit_execution_authority(session).prepare_finalization(h.request) as prepared:
                    run = await ExecutionRepository(session).require_lease(h.request, lease)
                    receipt = await prepared.consume(FinalizeAuthorityFacts(
                        **facts.model_dump(), execute_evidence_id=old_execute or UUID(run.execute_evidence_id),
                    ))
                    await stage_terminal(session, stored,
                        stored.material.model_dump(mode="json") if stored.material else None, receipt.evidence_id)
        assert await snapshot(h) == before
        assert await live_executor(h).finalize(facts) == facts.result
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
            digest = await session.scalar(text(
                "select public.checker_post_submit_authority_digest(r,'finalize') "
                "from public.checker_runs r where r.id=:id"
            ), {"id": run.id})
            assert digest == execution_authority_digest(FinalizeAuthorityFacts(
                **facts.model_dump(), execute_evidence_id=UUID(run.execute_evidence_id),
            ))


async def wait_for_expiry(h, lease):
    async with h.factory() as session:
        await session.execute(text(
            "select pg_sleep(greatest(0,extract(epoch from cast(:expiry as timestamptz)-clock_timestamp()))+0.02)"
        ), {"expiry": lease.expires_at})


@pytest.mark.parametrize("outcome", ["completed", "infrastructure_failed"])
async def test_terminal_receipt_digest_matches_database(tmp_path, isolated_database_env, outcome):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = await final_facts(h, lease)
        if outcome == "infrastructure_failed":
            facts = facts.model_copy(
                update={
                    "material": None,
                    "input_materialization_evidence_id": None,
                    "result": make_post_submit_result(
                        request_id=h.request.evaluation_request_id,
                        request_digest=h.request.request_sha256,
                        attempt_id=lease.reservation.attempt_id,
                        result_id=lease.reservation.result_id,
                        evaluation_generation=h.request.evaluation_generation,
                        outcome=outcome,
                        member_results=(),
                        infrastructure_failure_code="material_unavailable",
                    ),
                }
            )
        assert await executor.finalize(facts) == facts.result
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
            expected = FinalizeAuthorityFacts(**facts.model_dump(), execute_evidence_id=UUID(run.execute_evidence_id))
            assert await session.scalar(text(
                "select public.checker_post_submit_authority_digest(r,'finalize') from public.checker_runs r where r.id=:id"
            ), {"id": run.id}) == execution_authority_digest(expected)


@pytest.mark.parametrize("missing_execute", [True, False])
async def test_final_receipt_independently_requires_execute_receipt(
    tmp_path,
    isolated_database_env,
    missing_execute,
):
    """Isolate semantic receipt custody from the earlier run-state/immutability guard."""
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = await final_facts(h, lease)
        facts = facts.model_copy(
            update={
                "material": None,
                "input_materialization_evidence_id": None,
                "result": make_post_submit_result(
                    request_id=h.request.evaluation_request_id,
                    request_digest=h.request.request_sha256,
                    attempt_id=lease.reservation.attempt_id,
                    result_id=lease.reservation.result_id,
                    evaluation_generation=h.request.evaluation_generation,
                    outcome="infrastructure_failed",
                    member_results=(),
                    infrastructure_failure_code="material_unavailable",
                ),
            }
        )
        await executor.finalize(facts)
        before = await snapshot(h)
        replacement = new_record_id()
        expected = pytest.raises(IntegrityError, match="checker authorization receipt custody mismatch")
        with expected if missing_execute else nullcontext():
            async with h.factory() as session, session.begin():
                run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
                original_final = run.finalize_evidence_id
                original_execute = run.execute_evidence_id
                # Disable only the earlier immediate state guard. All deferred
                # receipt, foreign-key, material and terminal guards remain live.
                # Transactional DDL rolls back with the rejected write.
                await session.execute(text("ALTER TABLE public.checker_runs DISABLE TRIGGER checker_run_custody"))
                await session.execute(text("""
                    UPDATE public.checker_runs SET execute_evidence_id=:execute,
                      finalize_evidence_id=:final WHERE id=:id
                """), {"execute": None if missing_execute else original_execute,
                       "final": replacement, "id": run.id})
                # Keep real service/action provenance and every other audit fact;
                # only the event ID and digest follow the staged receipt chain.
                await session.execute(text("""
                    INSERT INTO public.audit_events
                    SELECT (jsonb_populate_record(NULL::public.audit_events,
                      to_jsonb(a) || jsonb_build_object('id',cast(:final AS text),
                        'entity_id',cast(:final AS text),
                        'after_facts',jsonb_build_object('allowed',true,
                          'resource_context_digest',
                          public.checker_post_submit_authority_digest(r,'finalize'))))).*
                    FROM public.audit_events a CROSS JOIN public.checker_runs r
                    WHERE a.id=:original AND r.id=:id
                """), {"final": str(replacement), "original": original_final, "id": run.id})
                await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                await session.execute(text("ALTER TABLE public.checker_runs ENABLE TRIGGER checker_run_custody"))
        if missing_execute:
            assert await snapshot(h) == before
        else:
            async with h.factory() as session:
                run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
                assert run.execute_evidence_id == original_execute
                assert run.finalize_evidence_id == str(replacement)


@pytest.mark.parametrize("substitution", ["missing", "execute_receipt"])
async def test_material_terminal_requires_its_actual_input_receipt(
    tmp_path,
    isolated_database_env,
    substitution,
):
    """Keep terminal material/result valid and isolate the retained input AUTH join."""
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = await final_facts(h, lease)
        async with h.factory() as session:
            execute = UUID(
                (
                    await session.get(CheckerRun, str(lease.reservation.attempt_id))
                ).execute_evidence_id
            )
        before = await snapshot(h)
        async with h.factory() as session:
            await session.begin()
            async with post_submit_execution_authority(session).prepare_finalization(
                h.request
            ) as prepared:
                final = await prepared.consume(
                    FinalizeAuthorityFacts(**facts.model_dump(), execute_evidence_id=execute)
                )
                staged = facts.model_copy(
                    update={
                        "input_materialization_evidence_id": None
                        if substitution == "missing"
                        else execute
                    }
                )
                await stage_terminal(
                    session, staged, facts.material.model_dump(mode="json"), final.evidence_id
                )
                with pytest.raises(
                    IntegrityError, match="checker input authorization custody mismatch"
                ):
                    await session.execute(
                        text("SET CONSTRAINTS public.checker_input_receipt_custody IMMEDIATE")
                    )
            await session.rollback()
        assert await snapshot(h) == before
        assert await executor.finalize(facts) == facts.result
