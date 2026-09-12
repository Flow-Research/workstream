"""Concrete AUTH with real finalized proposal, audit and deferred database custody."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.adapters.artifacts import guide_document_manifest_port
from app.modules.authorization.api import ActorKind
from app.modules.authorization.guide_proposal_authorization import GuideProposalAuthorizationAdapter
from app.modules.authorization.runtime import (
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.checkers.catalogue import (
    build_pre_submission_checker_catalogue,
    project_guide_pre_submission_capabilities,
)
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.api.guide_proposals import (
    GuideProposalApproval,
    GuideProposalCorrection,
    GuideProposalSelection,
    GuideProposalError,
)
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
from tests.projects.guide_compilation.proposals.pg_support import (
    proposal_case,
    seed_review_actor,
    revoke_review_grant,
)


@asynccontextmanager
async def service(factory, actor):
    async with factory() as session, session.begin():
        request = uuid4()
        context = HumanAuthorizationContext(
            actor_profile_id=actor.actor_profile_id,
            identity_link_id=actor.identity_link_id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=request,
            correlation_id=uuid4(),
        )
        try:
            yield (
                session,
                GuideProposalService(session, GuideProposalAuthorizationAdapter(session, context)),
                request,
            )
        except GuideProposalError as exc:
            raise exc from exc.__context__


async def package(factory, command, actor):
    async with service(factory, actor) as (_, owner, request):
        return await owner.review_package(
            GuideProposalSelection(
                project_id=command.project_id,
                guide_id=command.guide_id,
                compilation_id=command.compilation_id,
            ),
            actor=actor,
            request_id=request,
        )


async def mutate(factory, actor, payload):
    async with service(factory, actor) as (session, owner, request):
        if isinstance(payload, GuideProposalCorrection):
            return await owner.request_correction(payload, actor=actor, request_id=request)
        planner = build_pre_submission_checker_catalogue()
        return await owner.approve(
            payload,
            actor=actor,
            request_id=request,
            material=guide_document_manifest_port(session),
            pre_capabilities=project_guide_pre_submission_capabilities(planner),
            post_capabilities=current_post_submit_catalogue(),
            planner=planner,
        )


async def evidence_state(factory):
    async with factory() as session:
        events = (
            (
                await session.execute(
                    text(
                        "SELECT id,actor_id,action_id,project_id,resource_type,resource_id,after_facts,correlation_id,request_id FROM audit_events WHERE action_id IN ('project.guide_compilation.review_package.read','project.guide_compilation.correction.request','project.submission_artifact_policy.approve') ORDER BY id"
                    )
                )
            )
            .mappings()
            .all()
        )
        finalizations = (
            (
                await session.execute(
                    text(
                        "SELECT row_to_json(r) FROM project_guide_setup_finalizations r ORDER BY id"
                    )
                )
            )
            .scalars()
            .all()
        )
        return [dict(e) for e in events], finalizations


@pytest.mark.parametrize("action", ["approve", "correct"])
async def test_real_proposal_transaction_replay_and_revocation(clean_postgres_database, action):
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        review = await package(factory, command, actor)
        before_events, before_finalizations = await evidence_state(factory)
        assert len(before_events) == 1
        assert before_events[0]["resource_type"] == "project_guide_compilation_review_package"
        assert before_events[0]["resource_id"] == str(command.compilation_id)
        payload = (
            GuideProposalApproval(
                target=review.target,
                idempotency_key=uuid4(),
                acknowledged_warning_hashes=review.warning_hashes,
            )
            if action == "approve"
            else GuideProposalCorrection(
                target=review.target,
                idempotency_key=uuid4(),
                reason="Reconsider the proposed requirements.",
            )
        )
        receipt = await mutate(factory, actor, payload)
        after_events, after_finalizations = await evidence_state(factory)
        assert len(after_events) == 2
        assert after_finalizations == before_finalizations
        assert await mutate(factory, actor, payload) == receipt
        assert await evidence_state(factory) == (after_events, after_finalizations)
        mutation = next(
            e
            for e in after_events
            if e["action_id"] != "project.guide_compilation.review_package.read"
        )
        assert str(mutation["correlation_id"]) == str(receipt.operation_id)
        assert set(mutation["after_facts"]) == {"allowed", "resource_context_digest"}
        await revoke_review_grant(factory, actor, grant)
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            await mutate(factory, actor, payload)
        assert await evidence_state(factory) == (after_events, after_finalizations)


@pytest.mark.parametrize("action", ["read", "approve", "correct"])
@pytest.mark.parametrize(
    "authority", ["operator", "audit_authority", "foreign", "system_manager", "revoked"]
)
async def test_real_authority_denial_has_no_product_or_allowed_writes(
    clean_postgres_database, action, authority
):
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        review = await package(factory, command, actor)
        before = await evidence_state(factory)
        if authority == "revoked":
            await revoke_review_grant(factory, actor, grant)
        elif authority == "foreign":
            from project_create_fixtures import seed_authorized_project

            other_project = uuid4()
            async with factory() as session, session.begin():
                await seed_authorized_project(
                    session,
                    project_id=str(other_project),
                    name="Other project",
                    slug=str(other_project),
                )
            actor, _ = await seed_review_actor(factory, other_project)
        elif authority == "system_manager":
            actor, _ = await seed_review_actor(
                factory, None, role="project_manager", scope="system"
            )
        else:
            actor, _ = await seed_review_actor(factory, None, role=authority, scope="system")
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            if action == "read":
                await package(factory, command, actor)
            elif action == "approve":
                await mutate(
                    factory,
                    actor,
                    GuideProposalApproval(
                        target=review.target,
                        idempotency_key=uuid4(),
                        acknowledged_warning_hashes=review.warning_hashes,
                    ),
                )
            else:
                await mutate(
                    factory,
                    actor,
                    GuideProposalCorrection(
                        target=review.target, idempotency_key=uuid4(), reason="Inspect again."
                    ),
                )
        assert await evidence_state(factory) == before
        async with factory() as session:
            for table in ("project_guide_proposal_approvals", "project_guide_proposal_corrections"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
