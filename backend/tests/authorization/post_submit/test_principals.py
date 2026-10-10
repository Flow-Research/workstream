"""Persisted service lifecycle and the closed service/action matrix govern each phase."""

import pytest
from sqlalchemy import text

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.domain.post_submit import EXECUTE, FINALIZE, MATERIALIZE, post_submit_prepare_values
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.authorization.runtime import (
    PreparedAuthorizationInput, PreparedAuthorityScope, PreparedAuthorityScopeKind,
    PreparedAuthorizationUnsupported,
)
from app.modules.checkers.api.execution import CheckerExecutionUnavailable, ExecuteFacts
from app.modules.checkers.api.materialization import PostSubmissionMaterializationUnavailable
from tests.checkers.execution.support import live_executor, reserve
from tests.checkers.execution.test_concurrency import final_facts
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_post_submit_materialization import Consumer
from .test_receipt_custody import snapshot


@pytest.mark.parametrize("phase", ["execute", "materialize", "finalize"])
async def test_inactive_fixed_actor_denies_phase(tmp_path, isolated_database_env, phase):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease = None
        if phase != "execute":
            lease, _ = await executor._claim(h.request)
        final = await final_facts(h, lease) if phase == "finalize" else None
        identity = ServiceIdentity.ARTIFACT_MATERIALIZER if phase == "materialize" else ServiceIdentity.CHECKER_POST_SUBMIT
        async with h.factory() as session, session.begin():
            await session.execute(text("""UPDATE actor_profiles SET status='suspended',
                suspended_by='test',suspended_at=clock_timestamp(),suspension_reason='test'
                WHERE service_identity=:identity"""), {"identity": identity.value})
        before = await snapshot(h)
        consumer = Consumer(h.files)

        async def invoke():
            if phase == "execute":
                return await executor._claim(h.request)
            if phase == "materialize":
                return await h.service.materialize(ExecuteFacts(request=h.request, lease=lease), consumer)
            return await executor.finalize(final)

        expected = PostSubmissionMaterializationUnavailable if phase == "materialize" else CheckerExecutionUnavailable
        with pytest.raises(expected):
            await invoke()
        assert await snapshot(h) == before
        assert not h.store.opens and not h.preparation._active and consumer.calls == 0
        # Restore the fixture to prove that the same complete operation is valid.
        async with h.factory() as session, session.begin():
            await session.execute(text("""UPDATE actor_profiles SET status='active', suspended_by=NULL,
                suspended_at=NULL,suspension_reason=NULL,deactivated_by=NULL,deactivated_at=NULL,
                deactivation_reason=NULL,reactivated_by='test',reactivated_at=clock_timestamp(),
                reactivation_reason='test' WHERE service_identity=:identity"""), {"identity": identity.value})
        assert await invoke() is not None


@pytest.mark.parametrize("action", [EXECUTE, FINALIZE, MATERIALIZE])
async def test_real_foreign_service_cannot_prepare_phase(tmp_path, isolated_database_env, action):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        lease, _ = await live_executor(h)._claim(h.request)
        execution = ExecuteFacts(request=h.request, lease=lease)
        canonical = ServiceIdentity.ARTIFACT_MATERIALIZER if action == MATERIALIZE else ServiceIdentity.CHECKER_POST_SUBMIT
        foreign = ServiceIdentity.CHECKER_POST_SUBMIT if action == MATERIALIZE else ServiceIdentity.ARTIFACT_MATERIALIZER
        caller = PreparedAuthorizationInput(idempotency_key=h.request.evaluation_request_id,
            request_value=post_submit_prepare_values(action, h.request, execution if action == MATERIALIZE else None))
        scope = PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT, project_id=h.request.project_id)
        before = await snapshot(h)
        async with h.factory() as session, session.begin():
            async with fixed_service_prepared_authorization(session, service_identity=foreign,
                    request_id=h.request.evaluation_request_id, correlation_id=h.request.evaluation_request_id) as authority:
                with pytest.raises(PreparedAuthorizationUnsupported):
                    await authority.service.prepare(action, caller, scope)
        assert await snapshot(h) == before
        async with h.factory() as session, session.begin():
            async with fixed_service_prepared_authorization(session, service_identity=canonical,
                    request_id=h.request.evaluation_request_id, correlation_id=h.request.evaluation_request_id) as authority:
                assert await authority.service.prepare(action, caller, scope) is not None
        assert await snapshot(h) == before
