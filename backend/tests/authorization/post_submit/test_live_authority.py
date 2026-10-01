"""Exact live authority, replay and revocation through production composition."""

import asyncio
from datetime import timedelta
from uuid import UUID

import pytest

from app.modules.actors.api import ServiceIdentity
from app.modules.audit.service import AuditService
from app.modules.checkers.api.execution import CheckerExecutionUnavailable, ExecuteFacts
from app.modules.checkers.api.materialization import PostSubmissionMaterializationUnavailable
from app.modules.checkers.models import CheckerRun
from tests.checkers.execution.support import live_executor, material_execution, reserve, service_link_state
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_post_submit_materialization import Consumer
from tests.checkers.post_submit.support import change_request
from .test_receipt_custody import snapshot


async def test_terminal_replay_validates_both_stored_receipts_without_side_effects(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        result = await executor.evaluate_post_submission(h.request)
        before, opened = await snapshot(h), len(h.store.opens)
        assert await executor.evaluate_post_submission(h.request) == result
        assert await snapshot(h) == before and len(h.store.opens) == opened
        async with h.factory() as session:
            final_id = UUID((await session.get(CheckerRun, str(result.attempt_id))).finalize_evidence_id)
        original, seen = AuditService.get_authority_event, []

        async def hide_final(service, event_id):
            seen.append(event_id)
            return None if event_id == final_id else await original(service, event_id)

        with monkeypatch.context() as patch:
            patch.setattr(AuditService, "get_authority_event", hide_final)
            with pytest.raises(CheckerExecutionUnavailable, match="authority_unavailable"):
                await executor.evaluate_post_submission(h.request)
        assert final_id in seen and len(seen) == 2
        assert await snapshot(h) == before and len(h.store.opens) == opened
        await service_link_state(h.factory, ServiceIdentity.CHECKER_POST_SUBMIT, active=False)
        with pytest.raises(CheckerExecutionUnavailable):
            await executor.evaluate_post_submission(h.request)
        assert await snapshot(h) == before and len(h.store.opens) == opened
        await service_link_state(h.factory, ServiceIdentity.CHECKER_POST_SUBMIT, active=True)
        assert await executor.evaluate_post_submission(h.request) == result


@pytest.mark.parametrize("field", ["lease_id", "lease_generation", "expires_at"])
async def test_materialization_rejects_substituted_live_lease_before_io(
    tmp_path, isolated_database_env, field,
):
    from app.core.identifiers import new_record_id
    async with material_fixture(tmp_path, isolated_database_env) as h:
        facts = await material_execution(h)
        changed = {"lease_id": new_record_id(), "lease_generation": facts.lease.lease_generation+1,
                   "expires_at": facts.lease.expires_at + timedelta(microseconds=1)}[field]
        substituted = facts.model_copy(update={"lease": facts.lease.model_copy(update={field: changed})})
        before = await snapshot(h)
        consumer = Consumer(h.files)
        with pytest.raises(PostSubmissionMaterializationUnavailable):
            await h.service.materialize(substituted, consumer)
        assert await snapshot(h) == before
        assert h.store.opens == [] and consumer.calls == 0 and not h.preparation._active
        await h.service.materialize(facts, consumer)
        assert consumer.calls == 1


@pytest.mark.parametrize("field", ["binding_id", "content_id", "submission_id"])
async def test_materialization_rejects_mixed_valid_stored_lineage_before_io(
    tmp_path, isolated_database_env, field,
):
    async with material_fixture(tmp_path / "one", isolated_database_env) as h:
        async with material_fixture(tmp_path / "two", isolated_database_env,
                                    provision_services=False, storage_settings=h.settings) as other:
            facts = await material_execution(h)
            await material_execution(other)
            mixed_request = change_request(h.request, **{field: getattr(other.request, field)})
            mixed_reservation = facts.lease.reservation.model_copy(update={
                "request_digest": mixed_request.request_sha256,
            })
            mixed = ExecuteFacts(request=mixed_request,
                lease=facts.lease.model_copy(update={"reservation": mixed_reservation}))
            # Well-typed internally consistent selectors mix two genuine stored
            # lineages; they do not match either committed current execution.
            before = await snapshot(h)
            consumer = Consumer(h.files)
            with pytest.raises(PostSubmissionMaterializationUnavailable):
                await h.service.materialize(mixed, consumer)
            assert await snapshot(h) == before
            assert h.store.opens == [] and consumer.calls == 0 and not h.preparation._active
            await h.service.materialize(facts, consumer)
            assert consumer.calls == 1


@pytest.mark.parametrize("identity", [ServiceIdentity.ARTIFACT_MATERIALIZER, ServiceIdentity.CHECKER_POST_SUBMIT])
async def test_revoked_after_consumer_cannot_publish(tmp_path, isolated_database_env, monkeypatch, identity):
    import app.modules.checkers.execution as execution
    async with material_fixture(tmp_path, isolated_database_env) as h:
        reserved = await reserve(h)
        entered, release = asyncio.Event(), asyncio.Event()
        original = execution._StructuralConsumer.evaluate
        calls = []

        async def paused(consumer, request, material):
            value = await original(consumer, request, material)
            calls.append(value)
            entered.set()
            await release.wait()
            return value

        monkeypatch.setattr(execution._StructuralConsumer, "evaluate", paused)
        operation = asyncio.create_task(live_executor(h).evaluate_post_submission(h.request))
        try:
            await asyncio.wait_for(entered.wait(), 15)
            before = await snapshot(h)
            await service_link_state(h.factory, identity, active=False)
            release.set()
            expected = PostSubmissionMaterializationUnavailable if identity is ServiceIdentity.ARTIFACT_MATERIALIZER else CheckerExecutionUnavailable
            with pytest.raises(expected):
                await asyncio.wait_for(operation, 15)
            assert await snapshot(h) == before
            assert len(h.store.opens) == len(calls) == 1 and not h.preparation._active
            async with h.factory() as session:
                run = await session.get(CheckerRun, str(reserved.attempt_id))
                assert run.status == "running" and run.execute_evidence_id is not None
                assert run.finalize_evidence_id is run.result_json is run.material_custody is run.completion_event_id is None
        finally:
            release.set()
            await asyncio.gather(operation, return_exceptions=True)


@pytest.mark.parametrize("field", ["attempt_id", "result_id", "evaluation_request_id", "evaluation_generation", "project_id"])
async def test_execution_identity_substitution_denies_before_material_access(tmp_path, isolated_database_env, field):
    async with material_fixture(tmp_path / "one", isolated_database_env) as h:
        async with material_fixture(tmp_path / "two", isolated_database_env,
                                    provision_services=False, storage_settings=h.settings) as other:
            facts = await material_execution(h)
            foreign = await material_execution(other)
            request, reservation = facts.request, facts.lease.reservation
            if field in {"attempt_id", "result_id"}:
                reservation = reservation.model_copy(update={field: getattr(foreign.lease.reservation, field)})
            elif field == "project_id":
                request = change_request(request, project_id=other.request.project_id,
                    policy=other.request.policy, expected_context=other.request.expected_context,
                    structural_input=other.request.structural_input)
            elif field == "evaluation_request_id":
                request = change_request(request, evaluation_request_id=other.request.evaluation_request_id)
            else:
                request = change_request(request, evaluation_generation=request.evaluation_generation + 1)
            reservation = reservation.model_copy(update={
                "request_digest": request.request_sha256, "request_id": request.evaluation_request_id,
                "evaluation_generation": request.evaluation_generation,
            })
            mixed = ExecuteFacts(request=request, lease=facts.lease.model_copy(update={"reservation": reservation}))
            before = await snapshot(h)
            consumer = Consumer(h.files)
            with pytest.raises(PostSubmissionMaterializationUnavailable):
                await h.service.materialize(mixed, consumer)
            assert await snapshot(h) == before
            assert not h.store.opens and consumer.calls == 0 and not h.preparation._active
            await h.service.materialize(facts, consumer)
            assert consumer.calls == 1
