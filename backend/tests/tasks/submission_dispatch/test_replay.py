"""Retained creation cannot reset generations or borrow another owner's admission."""

import pytest
from sqlalchemy import func, select, text

from app.adapters.checkers import evaluation_coordinator
from tests.tasks.submission_dispatch.test_composition import _accepted_tasks, _receipt_key
from app.core.identifiers import new_record_id
from app.modules.actors.models import ActorProfile
from app.modules.actors.api import ServiceIdentity
from app.modules.checkers.models import CheckerRun, CheckerSubmissionFence
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.api import SubmissionCreationUnavailable
from app.modules.tasks.models import SubmissionDispatch
from tests.checkers.post_submit.support import change_request
from tests.post_submit_materialization_helpers import material_fixture


async def replay(h, key=None):
    """Read exact retained custody, without claiming current caller authority."""
    async with h.factory() as session:
        return await _accepted_tasks(session, h.settings).read_finalized(**(key or _receipt_key(h.created)))


async def test_later_generation_preserves_original_retained_dispatch(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            events = set((await session.execute(select(OutboxEvent.event_id))).scalars())
        successor = change_request(h.request, evaluation_request_id=new_record_id(), evaluation_generation=2)
        async with h.factory.begin() as session:
            newer = await evaluation_coordinator(session).reserve_current_evaluation(successor)
        assert await replay(h) == h.created
        async with h.factory() as session:
            fence = await session.get(CheckerSubmissionFence, str(h.created.submission_id))
            assert fence.current_run_id == str(newer.attempt_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 2
            assert set((await session.execute(select(OutboxEvent.event_id))).scalars()) == events


async def test_valid_foreign_receipt_members_cannot_be_mixed_into_retained_read(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path / "first", isolated_database_env) as h:
        async with material_fixture(tmp_path / "foreign", isolated_database_env,
                                    provision_services=False, storage_settings=h.settings) as foreign:
            for field in _receipt_key(h.created):
                assert getattr(h.created, field) != getattr(foreign.created, field)
                with pytest.raises(SubmissionCreationUnavailable, match="finalized dispatch differs"):
                    await replay(h, {**_receipt_key(h.created), field: getattr(foreign.created, field)})
            assert await replay(h) == h.created
            assert await replay(foreign) == foreign.created
            async with h.factory() as session:
                assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 2
                assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 2
                assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 4


async def test_live_suspension_denies_current_read_and_worker_authority(tmp_path, isolated_database_env):
    """Caller gates recheck live identities; internal retained reads grant no authority."""
    from uuid import UUID
    from app.adapters.artifacts import ConfiguredSubmissionOperationReader
    from app.modules.artifacts.api.submission_command import SubmissionOperationSelector
    from app.modules.artifacts.api.submission_intake import SubmissionIntakeFailure
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation
    from app.modules.artifacts.authorization import PreparedSubmissionFinalizationAuthorization
    from app.modules.authorization.prepared import PreparedAuthorizationUnsupported

    async with material_fixture(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            operation = (await session.execute(select(SubmissionIntakeOperation))).scalar_one()
            selector = SubmissionOperationSelector(operation_id=UUID(operation.id))
            binding_actor = await session.scalar(select(ActorProfile.id).where(
                ActorProfile.service_identity == ServiceIdentity.ARTIFACT_BINDING.value,
            ))
            events = set((await session.execute(select(OutboxEvent.event_id))).scalars())
        reader = ConfiguredSubmissionOperationReader(sessions=h.factory, context=h.actor_context)
        async def read():
            return await reader.read(h.request.task_id, selector)
        async def authorize_worker():
            async with h.factory.begin() as session:
                authority = PreparedSubmissionFinalizationAuthorization(
                    session, request_id=new_record_id(), correlation_id=selector.operation_id)
                try:
                    await authority.authorize()
                finally:
                    authority.close()
        initial = await read()
        await authorize_worker()
        for actor_id, call, error in (
            (str(h.actor_context.actor_profile_id), read, SubmissionIntakeFailure),
            (binding_actor, authorize_worker, PreparedAuthorizationUnsupported),
        ):
            async with h.factory.begin() as session:
                await session.execute(text("UPDATE public.actor_profiles SET status='suspended', suspended_by='dispatch-test', suspended_at=clock_timestamp(), suspension_reason='Recheck live authority' WHERE id=:id"), {"id": actor_id})
            try:
                with pytest.raises(error) as denied:
                    await call()
                if error is SubmissionIntakeFailure:
                    assert denied.value.code == "submission_unavailable"
            finally:
                async with h.factory.begin() as session:
                    await session.execute(text("UPDATE public.actor_profiles SET status='active', suspended_by=NULL, suspended_at=NULL, suspension_reason=NULL, reactivated_by='dispatch-test', reactivated_at=clock_timestamp(), reactivation_reason='Restore valid control' WHERE id=:id"), {"id": actor_id})
        assert await read() == initial
        await authorize_worker()
        assert await replay(h) == h.created
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert set((await session.execute(select(OutboxEvent.event_id))).scalars()) == events


async def test_missing_or_invalid_retained_dispatch_never_triggers_repair(tmp_path, isolated_database_env, monkeypatch):
    """Missing dispatch or non-true SQL custody cannot trigger new participant writes."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.modules.checkers.execution_coordination import EvaluationCoordinator
    from app.modules.outbox.service import OutboxService

    async with material_fixture(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            events = set((await session.execute(select(OutboxEvent.event_id))).scalars())
        async def forbidden(*args, **kwargs):
            pytest.fail("retained read tried to repair missing custody")
        original_scalar, original_get = AsyncSession.scalar, AsyncSession.get
        for unavailable in ("dispatch", False, None):
            seen = []
            async def read_scalar(session, statement, *args, **kwargs):
                if "public.submission_dispatch_valid(d)" in str(statement):
                    seen.append("validation")
                    parameters = kwargs.get("params") if "params" in kwargs else args[0]
                    assert parameters["id"] == str(h.created.submission_id)
                    return unavailable
                return await original_scalar(session, statement, *args, **kwargs)
            async def read_get(session, entity, ident, **kwargs):
                if unavailable == "dispatch" and entity is SubmissionDispatch:
                    assert ident == str(h.created.submission_id)
                    seen.append("dispatch")
                    return None
                return await original_get(session, entity, ident, **kwargs)
            with monkeypatch.context() as patch:
                patch.setattr(EvaluationCoordinator, "reserve_current_evaluation", forbidden)
                patch.setattr(OutboxService, "append", forbidden)
                patch.setattr(AsyncSession, "get", read_get)
                if unavailable != "dispatch":
                    patch.setattr(AsyncSession, "scalar", read_scalar)
                with pytest.raises(SubmissionCreationUnavailable, match="finalized dispatch differs"):
                    await replay(h)
            assert seen == ["dispatch" if unavailable == "dispatch" else "validation"]
        assert await replay(h) == h.created
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert set((await session.execute(select(OutboxEvent.event_id))).scalars()) == events
