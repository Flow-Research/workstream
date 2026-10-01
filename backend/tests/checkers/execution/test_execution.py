"""Execution through real verified input, immutable results and shared outbox."""

import pytest
from sqlalchemy import select, func

from app.modules.checkers.api.execution import CheckerExecutionUnavailable, COMPLETION_EVENT
from app.modules.checkers.execution_coordination import EvaluationCoordinator
from app.modules.checkers.models import CheckerRun, CheckerResult
from app.modules.outbox.models import OutboxEvent
from tests.post_submit_materialization_helpers import material_fixture
from .support import live_executor, reserve, service_link_state
from app.modules.actors.api import ServiceIdentity


@pytest.fixture
def autoflush_clock(monkeypatch):
    """Exercise a real ORM query flush at the database-clock boundary."""
    from app.modules.checkers.execution_repository import ExecutionRepository

    original = ExecutionRepository.now

    async def read_clock(repo):
        assert repo.session.autoflush
        # ORM SELECTs trigger autoflush even when the installed SQLAlchemy version
        # does not autoflush a scalar SQL-function SELECT. Keep real DB guards on.
        await repo.session.scalar(select(CheckerRun.id).limit(1))
        return await original(repo)

    monkeypatch.setattr(ExecutionRepository, "now", read_clock)


async def test_missing_checker_principal_denies_before_access(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env, provision_checker=False) as h:
        await reserve(h)
        with pytest.raises(CheckerExecutionUnavailable, match="authority_unavailable"):
            await live_executor(h).evaluate_post_submission(h.request)
        assert h.store.opens == [] and not h.preparation._active


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_verified_material_execution_and_replay(
    tmp_path, isolated_database_env, provider, autoflush_clock
):
    if provider == "minio":
        from tests.test_s3_artifact_store import provision_minio_bucket

        await provision_minio_bucket.__wrapped__()
    async with material_fixture(tmp_path, isolated_database_env, provider=provider) as h:
        reservation = await reserve(h)
        executor = live_executor(h)
        result = await executor.evaluate_post_submission(h.request)
        assert result.outcome == "completed"
        assert (
            result.attempt_id == reservation.attempt_id
            and result.result_id == reservation.result_id
        )
        result.validate_request(h.request)
        opened = len(h.store.opens)
        assert opened == 1
        assert await executor.evaluate_post_submission(h.request) == result
        assert len(h.store.opens) == opened
        async with h.factory() as session, session.begin():
            current = await EvaluationCoordinator(session).read_current_result(h.request)
            assert current.result == result
            run = await session.get(CheckerRun, str(result.attempt_id))
            assert run.material_custody == {
                "submission_id": str(h.created.submission_id),
                "submission_version": h.created.submission_version,
                "admission_id": str(h.created.admission_id),
                "binding_id": str(h.created.artifact_binding_id),
                "content_id": str(h.created.artifact_content_id),
                "replica_id": str(h.replica_id),
                "content_sha256": h.request.content_sha256,
                "byte_count": len(h.data),
                "semantic_manifest_sha256": h.manifest.sha256,
            }
            assert current.routing_recommendation in {"allow_review", "needs_revision"}
            rows = list(
                await session.scalars(
                    select(CheckerResult)
                    .where(CheckerResult.checker_run_id == str(result.attempt_id))
                    .order_by(CheckerResult.member_order)
                )
            )
            assert tuple(row.checker_name for row in rows) == tuple(
                m.checker_id for m in result.member_results
            )
            assert len(rows) == len(h.request.policy.entries)
            event = await session.scalar(
                select(OutboxEvent).where(OutboxEvent.event_type == COMPLETION_EVENT)
            )
            assert event.payload["reference"]["result_digest"] == result.result_digest
            assert event.payload["output_binding_ids"] == []
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
        assert not h.preparation._active
        assert list((h.scratch / "workspaces").iterdir()) == []


async def test_infrastructure_failure_is_terminal(tmp_path, isolated_database_env, autoflush_clock):
    from app.modules.checkers.runner import CheckerRegistry

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h, registry=CheckerRegistry())
        failed = await executor.evaluate_post_submission(h.request)
        assert failed.outcome == "infrastructure_failed"
        assert failed.infrastructure_failure_code == "implementation_unavailable"
        assert failed.member_results == ()
        opens = len(h.store.opens)
        assert await executor.evaluate_post_submission(h.request) == failed
        assert len(h.store.opens) == opens == 1
        async with h.factory() as session, session.begin():
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(OutboxEvent.event_type == COMPLETION_EVENT)
                )
                == 0
            )
            with pytest.raises(CheckerExecutionUnavailable, match="current_result"):
                await EvaluationCoordinator(session).read_current_result(h.request)


@pytest.mark.parametrize("substitution", ["prepared", "receipt"])
async def test_action_authority_is_not_interchangeable(
    tmp_path, isolated_database_env, substitution
):
    from contextlib import asynccontextmanager
    from app.modules.checkers.api.execution import execution_authority_digest
    from app.core.identifiers import new_record_id
    from app.modules.checkers.api.execution import (
        PreparedExecution,
        PreparedFinalization,
        ExecuteEvidence,
        FinalizeEvidence,
    )
    from .test_concurrency import final_facts
    from app.modules.authorization.post_submit_authorization import PostSubmitExecutionAuthorization

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = final_facts(h, lease)

        # Hold the other boundary valid so each type guard is independently exercised.
        class WrongPrepared(
            PreparedExecution if substitution == "prepared" else PreparedFinalization
        ):
            async def validate_replay(self, facts, evidence_id):
                pytest.fail("wrong-phase receipt reached replay")

            async def consume(self, value):
                receipt = FinalizeEvidence if substitution == "prepared" else ExecuteEvidence
                return receipt(
                    evidence_id=new_record_id(),
                    facts_digest=execution_authority_digest(value),
                )

        class WrongAuthority(PostSubmitExecutionAuthorization):
            @asynccontextmanager
            async def prepare_finalization(self, request):
                yield WrongPrepared()

        original_authority = executor._finalize_authority
        executor._finalize_authority = WrongAuthority
        with pytest.raises(
            CheckerExecutionUnavailable, match="authority_unavailable|action_evidence_unavailable"
        ):
            await executor.finalize(facts)
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
            assert run.status == "running" and run.result_json is None
            assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
        executor._finalize_authority = original_authority
        assert await executor.finalize(facts) == facts.result


async def test_zero_output_finalization(tmp_path, isolated_database_env):
    from pydantic import ValidationError
    from app.core.identifiers import new_record_id
    from app.modules.checkers.api.output_custody import (
        CheckerOutputSelector,
        CheckerOutputUnavailable,
    )
    from app.modules.checkers.execution_coordination import CheckerOutputReservations
    from .test_concurrency import final_facts

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        selector = CheckerOutputSelector(
            evaluation=h.request,
            checker_run_id=lease.reservation.attempt_id,
            worker_lease_id=lease.lease_id,
            worker_lease_generation=lease.lease_generation,
            slot_key="invented",
        )
        async with h.factory() as session, session.begin():
            slots = await CheckerOutputReservations(session).resolve(selector)
            assert slots.slots == ()
            with pytest.raises(CheckerOutputUnavailable, match="slot_unavailable"):
                slots.select(selector)
        facts = final_facts(h, lease)
        with pytest.raises(ValidationError):
            await executor.finalize(
                facts.model_copy(update={"output_binding_ids": (new_record_id(),)})
            )
        assert await executor.finalize(facts) == facts.result
        async with h.factory() as session:
            from app.modules.artifacts.models import ArtifactBinding

            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactBinding)
                    .where(ArtifactBinding.resource_type == "checker_run")
                )
                == 0
            )


async def test_finalization_outbox_failure_rolls_back(tmp_path, isolated_database_env):
    from sqlalchemy import event, text
    from app.adapters.outbox import outbox_append
    from app.modules.outbox.api import OutboxPersistenceError
    from .test_concurrency import final_facts

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = final_facts(h, lease)
        from tests.authorization.post_submit.test_receipt_custody import snapshot
        from app.modules.tasks.models import AuditEvent
        before = await snapshot(h)
        async with h.factory() as session, session.begin():
            await session.execute(
                text("""create function test_checker_outbox_failure() returns trigger language plpgsql as $$
              begin if NEW.event_type='PostSubmissionEvaluationCompleted' then
                raise exception 'controlled checker completion insert failure' using errcode='23514';
              end if; return NEW; end $$""")
            )
            await session.execute(
                text(
                    "create trigger test_checker_outbox_failure before insert on outbox_events for each row execute function test_checker_outbox_failure()"
                )
            )
        observations = []

        def failed_insert(context):
            if "controlled checker completion insert failure" in str(context.original_exception):
                observations.append(
                    context.statement.lower().startswith("insert into outbox_events")
                )

        event.listen(h.engine.sync_engine, "handle_error", failed_insert)

        class ObservingAppend:
            def __init__(self, session):
                self.session = session

            async def append(self, value):
                assert await self.session.scalar(
                    select(func.count()).select_from(CheckerResult)
                ) == len(h.request.policy.entries)
                assert await self.session.scalar(select(func.count()).select_from(AuditEvent)) == before[1] + 1
                assert await self.session.scalar(select(AuditEvent.action_id).where(
                    AuditEvent.action_id == "checker.post_submit.finalize",
                    AuditEvent.resource_id == str(lease.reservation.attempt_id),
                )) == "checker.post_submit.finalize"
                return await outbox_append(self.session).append(value)

        executor._outbox = ObservingAppend
        try:
            with pytest.raises(OutboxPersistenceError):
                await executor.finalize(facts)
            assert observations == [True]
            assert await snapshot(h) == before
            async with h.factory() as session:
                run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
                assert (
                    run.status == "running"
                    and run.result_json is None
                    and run.completion_event_id is None
                )
                assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(OutboxEvent)
                        .where(OutboxEvent.event_type == COMPLETION_EVENT)
                    )
                    == 0
                )
        finally:
            event.remove(h.engine.sync_engine, "handle_error", failed_insert)
            async with h.factory() as session, session.begin():
                await session.execute(
                    text("drop trigger test_checker_outbox_failure on outbox_events")
                )
                await session.execute(text("drop function test_checker_outbox_failure()"))
        executor._outbox = outbox_append
        assert await executor.finalize(facts) == facts.result


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
async def test_unreadable_stored_bytes_terminalize_and_replay(
    tmp_path, isolated_database_env, monkeypatch, damage
):
    from tests.test_local_artifact_store import object_path

    async with material_fixture(tmp_path, isolated_database_env) as h:
        reservation = await reserve(h)
        digest = h.request.content_sha256
        path = object_path(h.settings.artifact_local_root, f"sha256/{digest[7:9]}/{digest[9:]}")
        assert path.read_bytes() == h.data
        if damage == "missing":
            path.unlink()
        else:
            path.chmod(0o600)
            path.write_bytes(bytes([h.data[0] ^ 1]) + h.data[1:])
            path.chmod(0o400)
        executor = live_executor(h)

        async def forbidden_checker(*args, **kwargs):
            pytest.fail("unverified stored bytes reached a checker")

        monkeypatch.setattr(executor._registry, "run", forbidden_checker)
        # The byte failure cannot bypass the separate finalization authority.
        pending = []
        finalize = executor.finalize

        async def retain_finalization(facts):
            pending.append(facts)
            await service_link_state(h.factory, ServiceIdentity.CHECKER_POST_SUBMIT, active=False)
            return await finalize(facts)

        monkeypatch.setattr(executor, "finalize", retain_finalization)
        with pytest.raises(CheckerExecutionUnavailable, match="authority_unavailable"):
            await executor.evaluate_post_submission(h.request)
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(reservation.attempt_id))
            assert run.status == "running" and run.result_json is None
            assert run.finalize_evidence_id is None and run.completion_event_id is None
        await service_link_state(h.factory, ServiceIdentity.CHECKER_POST_SUBMIT, active=True)
        monkeypatch.setattr(executor, "finalize", finalize)
        assert len(pending) == 1
        result = await finalize(pending[0])
        assert result.outcome == "infrastructure_failed"
        assert result.infrastructure_failure_code == "material_unavailable"
        assert result.member_results == ()
        assert not h.preparation._active
        assert list((h.scratch / "workspaces").iterdir()) == []
        opened = len(h.store.opens)
        assert opened == 1
        assert await executor.evaluate_post_submission(h.request) == result
        assert len(h.store.opens) == opened
        async with h.factory() as session, session.begin():
            run = await session.get(CheckerRun, str(reservation.attempt_id))
            assert run.status == "infrastructure_failed" and run.failure_code == "material_unavailable"
            assert run.material_custody is None and run.completion_event_id is None
            assert run.finalize_evidence_id is not None
            assert run.routing_recommendation == "not_evaluated"
            assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
            with pytest.raises(CheckerExecutionUnavailable, match="current_result"):
                await EvaluationCoordinator(session).read_current_result(h.request)


@pytest.mark.parametrize("failure", ["authority", "cancel", "unexpected", "scratch", "cleanup"])
async def test_nonrecordable_material_failure_leaves_attempt_recoverable(
    tmp_path, isolated_database_env, monkeypatch, failure
):
    import asyncio
    from app.modules.artifacts.preparation import ArtifactScratchIntegrityError
    from app.modules.checkers.api.materialization import (
        PostSubmissionMaterializationUnavailable, PostSubmissionMaterializationFailure,
    )

    async with material_fixture(tmp_path, isolated_database_env) as h:
        if failure == "cleanup":
            from tests.checkers.post_submit.support import change_request

            h.request = change_request(h.request, structural_input=h.request.structural_input.model_copy(
                update={"manifest": ()},
            ))
        reservation = await reserve(h)
        executor = live_executor(h)
        if failure == "authority":
            await service_link_state(h.factory, ServiceIdentity.ARTIFACT_MATERIALIZER, active=False)
            expected = PostSubmissionMaterializationUnavailable
        elif failure == "cleanup":
            import sys
            from app.modules.artifacts.sources import PreparedArtifact

            expected = ArtifactScratchIntegrityError
            original_close, preceding = PreparedArtifact.close, []

            async def fail_close(prepared):
                preceding.append(sys.exception())
                await original_close(prepared)
                raise ArtifactScratchIntegrityError("controlled close failure")

            monkeypatch.setattr(PreparedArtifact, "close", fail_close)
        else:
            expected = {
                "cancel": asyncio.CancelledError,
                "unexpected": RuntimeError,
                "scratch": ArtifactScratchIntegrityError,
            }[failure]

            async def fail_prepare(*args, **kwargs):
                raise expected("controlled nonrecordable failure")

            monkeypatch.setattr(h.preparation, "prepare", fail_prepare)
        with pytest.raises(expected):
            await executor.evaluate_post_submission(h.request)
        if failure == "cleanup":
            assert len(preceding) == 1
            assert isinstance(preceding[0], PostSubmissionMaterializationFailure)
            assert str(preceding[0]) == "post_submit_material_manifest_mismatch"
        assert len(h.store.opens) == (0 if failure == "authority" else 1)
        assert not h.preparation._active
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(reservation.attempt_id))
            assert run.status == "running" and run.result_json is None
            assert run.finalize_evidence_id is None and run.completion_event_id is None
            assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
