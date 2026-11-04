"""Real database activation, denial, atomicity and retained-evidence replay."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.guide_activation.custody import load_guide_activation
from app.modules.projects.guide_activation.service import activation_authorization_selector
from app.modules.projects.models import ProjectGuide
from tests.projects.guide_activation.pg_support import activation_case
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor, revoke_review_grant
from tests.projects.post_policy.test_authority import foreign_manager
from .pg_support import activate, service, activation_state


async def test_complete_activation_and_live_replay(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, world, policy):
        receipt = await activate(factory, actor, command)
        before = await activation_state(factory)
        assert len(before["operations"]) == len(before["events"]) == 1
        operation, event = before["operations"][0], before["events"][0]
        assert event.after_facts == dict(allowed=True, resource_context_digest=operation.resource_context_digest)
        assert str(event.matched_grant_id) == str(grant)
        assert event.correlation_id == activation_authorization_selector(
            actor.actor_profile_id, command.idempotency_key
        )
        assert operation.activation_authority_json["resource_context_digest"] == operation.resource_context_digest
        assert operation.activation_authority_json["authorization_decision_event_id"] == str(
            event.id
        )
        async with factory() as session:
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert guide.status == "active"
            assert guide.contribution_policy_version_id == command.contribution_policy_version_id
            assert await load_guide_activation(session, guide) == receipt
            for table in ("workstream_tasks", "submissions", "checker_runs"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        assert await activate(factory, actor, command) == receipt
        assert await activation_state(factory) == before
        async with factory() as session, session.begin():
            await world.service(session).retire(world.request("retire", policy))
        assert await activate(factory, actor, command) == receipt
        assert await activation_state(factory) == before
        with pytest.raises(GuideProposalError, match="operation_conflict"):
            await activate(factory, actor, command.model_copy(update={"post_approval_operation_id": uuid4()}))
        assert await activation_state(factory) == before
        await revoke_review_grant(factory, actor, grant)
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            await activate(factory, actor, command)
        assert await activation_state(factory) == before
        _, renewed_grant = await seed_review_actor(factory, command.target.proposal.project_id, actor=actor)
        assert renewed_grant != grant
        assert await activate(factory, actor, command) == receipt
        assert await activation_state(factory) == before


@pytest.mark.parametrize("authority", ["operator", "audit_authority", "finance_authority", "foreign", "system", "revoked", "link_revoked", "suspended"])
async def test_live_authority_denial_preserves_draft(clean_postgres_database, authority):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        if authority == "revoked":
            await revoke_review_grant(factory, actor, grant)
        elif authority == "foreign":
            _, actor, _, _ = await foreign_manager(factory, actor)
        elif authority in {"link_revoked", "suspended"}:
            async with factory() as session, session.begin():
                if authority == "link_revoked":
                    await session.execute(text(
                        "UPDATE actor_identity_links SET status='revoked',revoked_at=now(),revoked_by=:by,"
                        "revoked_reason='Access revoked' WHERE id=:id"
                    ), dict(by=str(actor.actor_profile_id), id=str(actor.identity_link_id)))
                else:
                    await session.execute(text("UPDATE actor_profiles SET status='suspended',suspended_by=:id,suspended_at=now(),suspension_reason='Access suspended' WHERE id=:id"), dict(id=str(actor.actor_profile_id)))
        else:
            actor, _ = await seed_review_actor(factory, None, role="project_manager" if authority == "system" else authority, scope="system")
        before = await activation_state(factory)
        assert before["guides"][0].status == "draft" and before["operations"] == []
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            await activate(factory, actor, command)
        assert await activation_state(factory) == before


@pytest.mark.parametrize("human_review_required", [True, False])
async def test_live_activation_keeps_product_readiness_guards(clean_postgres_database, human_review_required):
    compilation_outcome = None
    if not human_review_required:
        from tests.projects.guide_compilation.helpers import generated_result

        compilation_outcome = generated_result()
    async with activation_case(
        clean_postgres_database,
        human_review_required=human_review_required,
        compilation_outcome=compilation_outcome,
    ) as (factory, command, actor, _, _, _):
        before = await activation_state(factory)
        variants = [
            command.model_copy(update={"guide_mutation_generation": command.guide_mutation_generation + 1}),
            command.model_copy(update={"post_approval_operation_id": uuid4()}),
            command.model_copy(update={"post_approval_output_digest": "sha256:" + "f" * 64}),
            command.model_copy(update={"review": command.review.model_copy(update={"policy_id": uuid4()})}),
            command.model_copy(update={"revision": command.revision.model_copy(update={"policy_id": uuid4()})}),
            command.model_copy(update={"contribution_policy_version_id": uuid4()}),
        ]
        for variant in variants:
            with pytest.raises(GuideProposalError):
                await activate(factory, actor, variant)
            assert await activation_state(factory) == before
        assert (await activate(factory, actor, command)).command == command


async def test_caller_rollback_removes_activation_evidence(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, _, _, _):
        before = await activation_state(factory)
        async with service(factory, actor) as (session, owner, request, _):
            await owner.activate(command, actor=actor, request_id=request)
            assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE action_id='project.guide.activate'")) == 1
            await session.rollback()
        assert await activation_state(factory) == before
        await activate(factory, actor, command)
