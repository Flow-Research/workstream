"""Independent PostgreSQL sessions serialize reservations and finalization."""

import asyncio

import pytest
from sqlalchemy import select, func, text

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    CheckerRequestConflict,
    CheckerExecutionUnavailable,
    FinalizeFacts,
    VerifiedMaterialFacts,
)
from app.adapters.checkers import evaluation_coordinator
from app.modules.checkers.models import CheckerRun
from tests.checkers.post_submit.support import change_request
from tests.checkers.post_submit.test_result_contract import result
from tests.post_submit_materialization_helpers import material_fixture
from .support import reserve, live_executor


async def final_facts(h, lease):
    """A controlled closed result for lease races, not a byte-evaluation assertion."""
    from tests.checkers.execution.storage_fixture import authorize_stored_material
    from app.modules.checkers.api.execution import ExecuteFacts

    material = VerifiedMaterialFacts(
        submission_id=h.request.submission_id,
        submission_version=h.request.submission_version,
        admission_id=h.created.admission_id,
        binding_id=h.request.binding_id,
        content_id=h.request.content_id,
        replica_id=h.replica_id,
        content_sha256=h.request.content_sha256,
        byte_count=h.request.byte_count,
        semantic_manifest_sha256=h.manifest.sha256,
    )
    receipt = await authorize_stored_material(
        h.factory, ExecuteFacts(request=h.request, lease=lease), material
    )
    return FinalizeFacts(
        request=h.request,
        lease=lease,
        result=result(
            h.request,
            attempt_id=lease.reservation.attempt_id,
            result_id=lease.reservation.result_id,
        ),
        material=material,
        input_materialization_evidence_id=receipt,
        output_binding_ids=(),
    )


async def test_concurrent_initial_reservation(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        first, second = await asyncio.gather(reserve(h), reserve(h))
        assert first == second
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1


async def test_cross_submission_request_collision(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path / "one", isolated_database_env) as h:
        async with material_fixture(
            tmp_path / "two",
            isolated_database_env,
            provision_services=False,
            storage_settings=h.settings,
        ) as other:
            changed = change_request(
                other.request, evaluation_request_id=h.request.evaluation_request_id
            )
            responses = await asyncio.gather(
                reserve(h), reserve(other, changed), return_exceptions=True
            )
            assert sum(isinstance(item, CheckerRequestConflict) for item in responses) == 1
            assert sum(not isinstance(item, BaseException) for item in responses) == 1
            async with h.factory() as session:
                assert set(await session.scalars(select(CheckerRun.id))) == {
                    str(h.created.evaluation_attempt_id), str(other.created.evaluation_attempt_id),
                }


@pytest.mark.parametrize("old_first", [True, False])
async def test_stale_worker_cannot_finalize_after_takeover(
    tmp_path, isolated_database_env, monkeypatch, old_first
):
    import app.modules.checkers.execution as execution

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        monkeypatch.setattr(execution, "LEASE_SECONDS", 1)
        old, _ = await executor._claim(h.request)
        old_facts = await final_facts(h, old)
        async with h.factory() as session:
            await session.execute(text("select pg_sleep(1.05)"))
        monkeypatch.setattr(execution, "LEASE_SECONDS", 300)
        current, _ = await executor._claim(h.request)
        assert (
            current.reservation == old.reservation
            and current.lease_generation == old.lease_generation + 1
        )
        current_facts = old_facts.model_copy(update={"lease": current})
        if not old_first:
            await executor.finalize(current_facts)
        with pytest.raises(CheckerExecutionUnavailable):
            await executor.finalize(old_facts)
        if old_first:
            await executor.finalize(current_facts)
        async with h.factory() as session, session.begin():
            stored = await evaluation_coordinator(session).read_current_result(h.request)
            assert stored.result == current_facts.result


@pytest.mark.parametrize("finalize_first", [True, False])
async def test_generation_advance_and_finalize_serialize(
    tmp_path, isolated_database_env, monkeypatch, finalize_first
):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = await final_facts(h, lease)
        successor = change_request(
            h.request, evaluation_request_id=new_record_id(), evaluation_generation=2
        )
        from app.modules.checkers.execution_repository import ExecutionRepository
        from tests.auth_concurrency_support import wait_for_named_database_lock

        completion_name = "checker-finalize-" + new_record_id().hex
        advance_name = "checker-advance-" + new_record_id().hex
        original = ExecutionRepository.lock_current

        async def named_lock(repo, request):
            await repo.session.execute(
                text("select set_config('application_name',:name,true)"), {"name": completion_name}
            )
            return await original(repo, request)

        monkeypatch.setattr(ExecutionRepository, "lock_current", named_lock)

        async def advance():
            async with h.factory() as session, session.begin():
                await session.execute(
                    text("select set_config('application_name',:name,true)"), {"name": advance_name}
                )
                return await evaluation_coordinator(session).reserve_current_evaluation(successor)

        async def waiting(name):
            await asyncio.wait_for(
                wait_for_named_database_lock(isolated_database_env, name), timeout=10
            )

        if finalize_first:
            # Independently hold the finalization fence while successor waits.
            async with h.factory() as session, session.begin():
                await session.execute(
                    text(
                        "select 1 from checker_submission_fences where submission_id=:id for update"
                    ),
                    {"id": str(h.request.submission_id)},
                )
                completing = asyncio.create_task(executor.finalize(facts))
                await waiting(completion_name)
                advancing = asyncio.create_task(advance())
                await waiting(advance_name)
                assert not completing.done() and not advancing.done()
            await completing
            await advancing
        else:
            async with h.factory() as session, session.begin():
                await evaluation_coordinator(session).reserve_current_evaluation(successor)
                completing = asyncio.create_task(executor.finalize(facts))
                await waiting(completion_name)
                assert not completing.done()
            with pytest.raises(CheckerExecutionUnavailable):
                await completing
        async with h.factory() as session:
            original = await session.get(CheckerRun, str(lease.reservation.attempt_id))
            assert original.status == ("completed" if finalize_first else "running")


async def test_evaluation_releases_transaction_before_materialization(
    tmp_path, isolated_database_env, monkeypatch
):
    from contextlib import asynccontextmanager
    from app.modules.authorization.post_submit_authorization import PostSubmitExecutionAuthorization
    import app.modules.checkers.execution as execution

    async with material_fixture(tmp_path, isolated_database_env) as h:
        receipt = await reserve(h)
        active_preparation = []

        class TrackingAuthority(PostSubmitExecutionAuthorization):
            @asynccontextmanager
            async def prepare_execution(self, request):
                active_preparation.append(request.evaluation_request_id)
                try:
                    async with super().prepare_execution(request) as prepared:
                        yield prepared
                finally:
                    active_preparation.clear()

        observed = []

        async def probe(phase):
            assert not active_preparation
            async with h.factory() as other, other.begin():
                fence = await other.scalar(
                    text(
                        "select current_run_id from checker_submission_fences where submission_id=:id for update nowait"
                    ),
                    {"id": str(h.request.submission_id)},
                )
                assert str(fence) == str(receipt.attempt_id)
                assert (
                    await other.scalar(
                        text("select status from checker_runs where id=:id for update nowait"),
                        {"id": str(receipt.attempt_id)},
                    )
                    == "running"
                )
            observed.append(phase)

        class MaterializationProbe:
            async def materialize(self, request, consumer):
                await probe("before_bytes")
                return await h.service.materialize(request, consumer)

        original = execution._StructuralConsumer.evaluate

        async def evaluate(consumer, request, material):
            assert material.entries
            await probe("inside_consumer")
            return await original(consumer, request, material)

        monkeypatch.setattr(execution._StructuralConsumer, "evaluate", evaluate)
        executor = live_executor(h)
        executor._execute_authority = TrackingAuthority
        executor._materialization = MaterializationProbe()
        assert (await executor.evaluate_post_submission(h.request)).outcome == "completed"
        assert observed == ["before_bytes", "inside_consumer"]


async def test_member_insertion_waits_for_terminal_parent(
    tmp_path, isolated_database_env, monkeypatch
):
    from sqlalchemy import insert
    from sqlalchemy.exc import IntegrityError
    from app.modules.checkers.models import CheckerResult
    from app.modules.checkers.execution_repository import ExecutionRepository
    from tests.auth_concurrency_support import wait_for_named_database_lock

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = await final_facts(h, lease)
        entered, release = asyncio.Event(), asyncio.Event()
        holder = []
        original = ExecutionRepository.write_members

        async def paused(repo, run, result):
            holder.append(await repo.session.scalar(text("select pg_backend_pid()")))
            entered.set()
            await release.wait()
            return await original(repo, run, result)

        monkeypatch.setattr(ExecutionRepository, "write_members", paused)
        first = facts.result.member_results[0]
        waiter = "checker-member-race-" + new_record_id().hex

        async def insert_member():
            async with h.factory() as session, session.begin():
                await session.execute(
                    text("select set_config('application_name',:name,true)"), {"name": waiter}
                )
                await session.execute(
                    insert(CheckerResult).values(
                        id=str(new_record_id()),
                        checker_run_id=str(facts.result.attempt_id),
                        task_id=str(h.request.task_id),
                        submission_id=str(h.request.submission_id),
                        member_order=0,
                        checker_name=first.checker_id,
                        definition_version=first.definition_version,
                        implementation_version=first.implementation_version,
                        status=first.status,
                        code=first.code,
                        failure_category=first.failure_category,
                        severity=first.severity,
                        counters=[],
                    )
                )

        completing = asyncio.create_task(executor.finalize(facts))
        inserting = None
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            inserting = asyncio.create_task(insert_member())
            await asyncio.wait_for(
                wait_for_named_database_lock(
                    isolated_database_env,
                    waiter,
                    expected_blocker_pid=holder[0],
                ),
                timeout=10,
            )
            assert not inserting.done()
            release.set()
            assert await completing == facts.result
            with pytest.raises(
                IntegrityError, match="finished or unclaimed checker run cannot receive results"
            ):
                await inserting
        finally:
            release.set()
            pending = [completing] + ([inserting] if inserting is not None else [])
            for task in pending:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerResult)) == len(
                facts.result.member_results
            )
            assert (
                await session.get(CheckerRun, str(facts.result.attempt_id))
            ).status == "completed"
