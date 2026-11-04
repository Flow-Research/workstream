"""Invalid activation selections preserve the complete prior state."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.models import ProjectGuide
from tests.projects.guide_compilation.proposals.pg_support import revoke_review_grant
from .pg_support import activation_case, activation_service


async def test_invalid_exact_selections_have_no_activation_effect(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        variants = [
            command.model_copy(
                update={"guide_mutation_generation": command.guide_mutation_generation + 1}
            ),
            command.model_copy(update={"post_approval_operation_id": uuid4()}),
            command.model_copy(update={"post_approval_output_digest": "sha256:" + "f" * 64}),
            command.model_copy(
                update={"review": command.review.model_copy(update={"policy_id": uuid4()})}
            ),
            command.model_copy(
                update={
                    "revision": command.revision.model_copy(
                        update={"policy_hash": "sha256:" + "f" * 64}
                    )
                }
            ),
            command.model_copy(update={"contribution_policy_id": uuid4()}),
            command.model_copy(update={"contribution_policy_version_id": uuid4()}),
            command.model_copy(
                update={
                    "expected_previous_active_guide_id": uuid4(),
                    "expected_previous_active_guide_generation": 1,
                }
            ),
        ]
        for variant in variants:
            with pytest.raises(GuideProposalError):
                async with factory() as session, session.begin():
                    await activation_service(session, actor, variant, grant).activate(
                        variant, actor=actor, request_id=uuid4()
                    )
        async with factory() as session:
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert guide.status == "draft" and guide.activation_operation_id is None
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM audit_events WHERE action_id='project.guide.activate'"
                    )
                )
                == 0
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 0
            )


async def test_close_failure_and_caller_rollback_leave_no_activation(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            async with factory() as session, session.begin():
                await activation_service(session, actor, command, grant, close_error=True).activate(
                    command, actor=actor, request_id=uuid4()
                )
        async with factory() as session:
            await session.begin()
            await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
            await session.rollback()
        async with factory() as session:
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert guide.status == "draft" and guide.activation_operation_id is None
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM audit_events WHERE action_id='project.guide.activate'"
                    )
                )
                == 0
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 0
            )


async def test_replay_requires_current_manager_and_original_payload(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        changed = command.model_copy(update={"contribution_policy_version_id": uuid4()})
        with pytest.raises(GuideProposalError, match="operation_conflict"):
            async with factory() as session, session.begin():
                await activation_service(session, actor, changed, grant).activate(
                    changed, actor=actor, request_id=uuid4()
                )
        await revoke_review_grant(factory, actor, grant)
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            async with factory() as session, session.begin():
                await activation_service(session, actor, command, grant).activate(
                    command, actor=actor, request_id=uuid4()
                )
        async with factory() as session:
            stored = await session.scalar(
                text(
                    "SELECT response_json FROM guide_mutation_idempotency_records WHERE operation_id=:id"
                ),
                dict(id=receipt.operation_id),
            )
            assert stored == receipt.model_dump(mode="json")


async def test_complete_false_review_setting_activates_with_real_authority(clean_postgres_database):
    from tests.authorization.guide_activation.pg_support import activate

    async with activation_case(clean_postgres_database, human_review_required=False) as (
        factory,
        command,
        actor,
        grant,
        _,
        _,
    ):
        receipt = await activate(factory, actor, command)
        async with factory() as session:
            assert (
                await session.scalar(
                    text("SELECT human_review_required FROM review_policies WHERE id=:id"),
                    dict(id=str(command.review.policy_id)),
                )
                is False
            )
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert guide.status == "active"
            assert guide.activation_operation_id == receipt.operation_id
        assert await activate(factory, actor, command) == receipt


async def test_retired_con_policy_cannot_form_a_new_binding(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (
        factory,
        command,
        actor,
        grant,
        world,
        policy,
    ):
        async with factory() as session, session.begin():
            await world.service(session).retire(world.request("retire", policy))
        with pytest.raises(GuideProposalError, match="proposal_stale"):
            async with factory() as session, session.begin():
                await activation_service(session, actor, command, grant).activate(
                    command, actor=actor, request_id=uuid4()
                )
        async with factory() as session:
            assert (
                await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            ).activation_operation_id is None
