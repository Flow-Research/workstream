"""Real authorization INSERT failures leave every protected phase unchanged."""

import pytest
from sqlalchemy import text

from app.modules.checkers.api.execution import CheckerExecutionUnavailable, ExecuteFacts
from app.modules.checkers.api.materialization import PostSubmissionMaterializationUnavailable
from tests.checkers.execution.support import live_executor, reserve
from tests.checkers.execution.test_concurrency import final_facts
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_post_submit_materialization import Consumer
from .test_receipt_custody import snapshot


@pytest.mark.parametrize("phase", ["execute", "materialize", "finalize"])
async def test_real_audit_insert_failure_rolls_back(tmp_path, isolated_database_env, phase):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease = None
        if phase != "execute":
            lease, _ = await executor._claim(h.request)
        action = ("artifact.post_submit.checker_input.materialize" if phase == "materialize"
                  else "checker.post_submit." + phase)
        before = await snapshot(h)
        opened = len(h.store.opens)
        consumer = Consumer(h.files)
        async with h.factory() as session, session.begin():
            await session.execute(text("CREATE SEQUENCE test_post_submit_audit_attempt"))
            await session.execute(text("""CREATE FUNCTION test_post_submit_audit_failure() RETURNS trigger
              LANGUAGE plpgsql AS $$ BEGIN
                PERFORM nextval('test_post_submit_audit_attempt');
                RAISE EXCEPTION 'post-submit audit insert rejected' USING ERRCODE='23514';
              END $$"""))
            # Action is a closed test parameter, never caller input.
            await session.execute(text(f"""CREATE TRIGGER test_post_submit_audit_failure
              BEFORE INSERT ON audit_events FOR EACH ROW WHEN (NEW.action_id='{action}')
              EXECUTE FUNCTION test_post_submit_audit_failure()"""))

        async def invoke():
            if phase == "execute":
                return await executor._claim(h.request)
            if phase == "materialize":
                return await h.service.materialize(ExecuteFacts(request=h.request, lease=lease), consumer)
            return await executor.finalize(final_facts(h, lease))

        try:
            error = PostSubmissionMaterializationUnavailable if phase == "materialize" else CheckerExecutionUnavailable
            with pytest.raises(error, match="authority_unavailable"):
                await invoke()
            assert await snapshot(h) == before
            assert len(h.store.opens) == opened
            assert consumer.calls == 0 and not h.preparation._active
            assert list((h.scratch / "workspaces").iterdir()) == []
            async with h.factory() as session:
                # Sequence effects survive rollback: the real INSERT trigger ran.
                assert (await session.execute(text(
                    "SELECT last_value,is_called FROM test_post_submit_audit_attempt"
                ))).one() == (1, True)
        finally:
            async with h.factory() as session, session.begin():
                await session.execute(text("DROP TRIGGER test_post_submit_audit_failure ON audit_events"))
                await session.execute(text("DROP FUNCTION test_post_submit_audit_failure()"))
                await session.execute(text("DROP SEQUENCE test_post_submit_audit_attempt"))
        assert await invoke() is not None
