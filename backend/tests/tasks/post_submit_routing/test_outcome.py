"""Real authorized routing composition; production registration remains absent."""

import pytest
from sqlalchemy import select, text

from app.adapters.tasks import task_post_submit_outcome
from app.modules.tasks.models import WorkstreamTask
from tests.authorization.post_submit_routing.support import provision_router
from tests.tasks.post_submit_routing.test_source_preparation import routing_source
from tests.tasks.post_submit_routing.outcome_support import invoked_completion, outcome_snapshot


async def test_true_branch_does_not_acquire_acceptance(tmp_path, isolated_database_env):
    async with routing_source(tmp_path, isolated_database_env) as h:
        await provision_router(h.factory)
        envelope = await invoked_completion(h)
        async with h.factory() as session, session.begin():
            operation = task_post_submit_outcome(session, h.factory)

            class ForbiddenAcceptance:
                def prepare(self, generation):
                    pytest.fail("human handoff entered REV/CON")

            operation._acceptance = ForbiddenAcceptance()
            result = await operation.apply(envelope, current_generation=None)
            assert result["final_acceptance_id"] is None and result["economic"] is None
        async with h.factory() as session:
            assert (
                await session.scalar(
                    select(WorkstreamTask.status).where(WorkstreamTask.id == str(h.request.task_id))
                )
                == "review_pending"
            )
            assert await session.scalar(text("SELECT count(*) FROM public.final_acceptances")) == 0
            assert (
                await session.scalar(text("SELECT count(*) FROM public.contribution_records")) == 0
            )
        async with h.factory() as session, session.begin():
            replay = await task_post_submit_outcome(session, h.factory).apply(
                envelope, current_generation=None
            )
            assert replay == result | {"replayed": True}


async def test_false_branch_records_one_acceptance_and_submitter_contribution(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
):
    async with routing_source(tmp_path, isolated_database_env, human_review_required=False) as h:
        await provision_router(h.factory)
        envelope = await invoked_completion(h)
        async with h.factory() as session, session.begin():
            result = await task_post_submit_outcome(session, h.factory).apply(
                envelope, current_generation=2
            )
            assert result["final_acceptance_id"] is not None
        async with h.factory() as session:
            assert (
                await session.scalar(
                    select(WorkstreamTask.status).where(WorkstreamTask.id == str(h.request.task_id))
                )
                == "accepted"
            )
            assert await session.scalar(text("SELECT count(*) FROM public.final_acceptances")) == 1
            assert (
                await session.scalar(text("SELECT count(*) FROM public.contribution_records")) == 1
            )
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 0
            assert (
                await session.scalar(text("SELECT count(*) FROM public.compensation_awards")) == 0
            )
            retained = (
                (
                    await session.execute(
                        text("""
                SELECT public.task_routing_receipt_valid(m) AS receipt_valid,
                  public.task_routing_acceptance_matches(m.id,m.final_acceptance_id,m.authorization_decision_id,
                    m.router_actor_id,m.project_id,m.task_id,m.submission_id,
                    (m.authority_context#>>'{source,locked_policy,locked_review_policy_id}')::uuid,2,false) AS replay_valid,
                  public.task_routing_outcome_complete(m) AS complete
                FROM public.task_post_submit_routing_manifests m
            """)
                    )
                )
                .mappings()
                .one()
            )
            assert dict(retained) == {"receipt_valid": True, "replay_valid": True, "complete": True}
        async with h.factory() as session, session.begin():
            replay = await task_post_submit_outcome(session, h.factory).apply(
                envelope, current_generation=2
            )
            assert replay == result | {"replayed": True}


async def test_orphan_routing_allow_cannot_commit(tmp_path, isolated_database_env):
    from sqlalchemy.exc import DBAPIError
    from app.adapters.tasks import routing_source_preparer
    from app.adapters.auth import task_routing_authorization
    from app.modules.checkers.api.execution import EvaluationCompletion

    async with routing_source(tmp_path, isolated_database_env) as h:
        await provision_router(h.factory)
        envelope = await invoked_completion(h)
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        async with h.factory() as session:
            with pytest.raises(
                DBAPIError, match="routing authority requires its complete governed outcome"
            ):
                async with session.begin():
                    source = await routing_source_preparer(session).prepare(
                        envelope.claim.event_id,
                        EvaluationCompletion.model_validate_json(envelope.payload_json),
                    )
                    async with task_routing_authorization(session).prepare(
                        source.request
                    ) as authority:
                        receipt = await authority.consume(source, envelope.claim, None, None)
                        assert receipt.decision_id is not None
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before
        # Identical valid input can still commit through the complete operation.
        async with h.factory() as session, session.begin():
            await task_post_submit_outcome(session, h.factory).apply(
                envelope, current_generation=None
            )


@pytest.mark.parametrize("human", [True, False])
async def test_caller_rollback_and_late_failure_leave_no_partial_outcome(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
    human,
):
    from sqlalchemy.exc import DBAPIError

    async with routing_source(tmp_path, isolated_database_env, human_review_required=human) as h:
        await provision_router(h.factory)
        envelope = await invoked_completion(h)
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        for late_failure in (False, True):
            async with h.factory() as session:
                await session.begin()
                await task_post_submit_outcome(session, h.factory).apply(
                    envelope, current_generation=None if human else 2
                )
                if late_failure:
                    with pytest.raises(DBAPIError, match="division by zero"):
                        await session.execute(text("SELECT 1/0"))
                await session.rollback()
            async with h.factory() as session:
                assert await outcome_snapshot(session) == before


@pytest.mark.parametrize(
    "missing_event",
    [
        "TaskPostSubmitRouted",
        "SubmitterContributionRecorded",
        "CompensationAwardCreated",
    ],
)
async def test_database_rejects_missing_required_outcome_evidence(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
    missing_event,
):
    """Only one audit write is omitted; real authorization and all effects stay valid."""
    from app.adapters.audit import _TaskRoutingAudit
    from sqlalchemy.exc import DBAPIError
    from tests.tasks.post_submit_routing.outcome_support import (
        authorized_routing_source,
        apply_outcome,
    )

    async with authorized_routing_source(
        tmp_path,
        isolated_database_env,
        contribution_awards=("money",),
    ) as h:
        original = _TaskRoutingAudit._record
        omitted = []

        async def omit_one(owner, value, replay):
            if value.event_type.value == missing_event:
                omitted.append(value)
                return
            return await original(owner, value, replay)

        async with h.factory() as session:
            before = await outcome_snapshot(session)
        with monkeypatch.context() as patch:
            patch.setattr(_TaskRoutingAudit, "_record", omit_one)
            async with h.factory() as session:
                with pytest.raises(
                    DBAPIError, match="routing authority requires its complete governed outcome"
                ):
                    async with session.begin():
                        staged = await apply_outcome(session, h, 2)
                        assert staged["economic"].contribution_record_id is not None
                        assert len(staged["economic"].award_ids) == 1
                        assert len(omitted) == 1
                        # Isolate this boundary from unrelated deferred constraints.
                        await session.execute(
                            text("SET CONSTRAINTS public.task_routing_complete_outcome IMMEDIATE")
                        )
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before
        async with h.factory() as session, session.begin():
            assert (await apply_outcome(session, h, 2))["final_acceptance_id"] is not None


async def test_revoked_router_cannot_create_or_replay_an_outcome(tmp_path, isolated_database_env):
    from app.modules.actors.api import ServiceIdentity
    from app.modules.authorization.runtime import AuthorizationDenied, PreparedAuthorizationUnsupported
    from tests.checkers.execution.support import service_link_state
    from tests.tasks.post_submit_routing.outcome_support import authorized_routing_source, apply_outcome

    async with authorized_routing_source(tmp_path, isolated_database_env, human_review_required=True) as h:
        committed = None
        for replay in (False, True):
            await service_link_state(h.factory, ServiceIdentity.TASK_POST_SUBMIT_ROUTER, active=False)
            async with h.factory() as session:
                before = await outcome_snapshot(session)
            async with h.factory() as session:
                with pytest.raises((AuthorizationDenied, PreparedAuthorizationUnsupported)):
                    async with session.begin():
                        await apply_outcome(session, h, None)
            async with h.factory() as session:
                assert await outcome_snapshot(session) == before
            await service_link_state(h.factory, ServiceIdentity.TASK_POST_SUBMIT_ROUTER, active=True)
            async with h.factory() as session, session.begin():
                result = await apply_outcome(session, h, None)
                assert result["replayed"] is replay
                if committed is not None:
                    assert result == committed | {"replayed": True}
                committed = result


async def test_participant_failure_rolls_back(tmp_path, isolated_database_env, live_acceptance_lifecycle, monkeypatch):
    """Fail after each real owner has staged its effect, including the final audit."""
    from app.adapters.audit import _TaskRoutingAudit
    from app.modules.reviews.acceptance.repository import FinalAcceptanceRepository
    from app.modules.tasks.accepted_effects import TaskAcceptedEffectsParticipant
    from app.modules.tasks.post_submit_routing.outcome import TaskPostSubmitOutcome
    from app.modules.contributions.records.participant import SubmitterContributionParticipant
    from tests.tasks.post_submit_routing.outcome_support import authorized_routing_source, apply_outcome

    class StagedFailure(RuntimeError):
        pass

    boundaries = (
        (TaskPostSubmitOutcome, "_append_notice"),
        (FinalAcceptanceRepository, "persist"),
        (TaskAcceptedEffectsParticipant, "apply_accepted_effects"),
        (SubmitterContributionParticipant, "participate_submitter"),
        (_TaskRoutingAudit, "record"),
    )
    async with authorized_routing_source(tmp_path, isolated_database_env, contribution_awards=("money", "project_points")) as h:
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        for owner_type, method in boundaries:
            original = getattr(owner_type, method)
            reached = []

            async def fail_after(owner, *args, **kwargs):
                result = await original(owner, *args, **kwargs)
                reached.append(result)
                raise StagedFailure(method)

            with monkeypatch.context() as patch:
                patch.setattr(owner_type, method, fail_after)
                async with h.factory() as session:
                    with pytest.raises(StagedFailure, match=method):
                        async with session.begin():
                            await apply_outcome(session, h, 2)
                assert len(reached) == 1
            async with h.factory() as session:
                assert await outcome_snapshot(session) == before
        async with h.factory() as session, session.begin():
            assert len((await apply_outcome(session, h, 2))["economic"].award_ids) == 2
