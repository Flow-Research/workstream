"""Real immutable source fixtures; no runtime recognition or payment authority."""

from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import insert, select, text

from app.core.identifiers import new_record_id
from app.modules.compensation.awards.models import CompensationAward
from app.modules.contributions.models import ContributionAwardDefinition
from app.modules.contributions.records.models import ContributionRecord
from app.modules.contributions.records.schemas import ContributionRecordInput


@asynccontextmanager
async def reviewer_contribution_source(tmp_path, url, *, decision="accept", paid=False, **options):
    """Persist a real Review only; reviewer contribution storage is a separate fact."""
    from tests.reviews.decision.support import review_source, finding, insert_review

    async with review_source(
        tmp_path, url, contribution_awards=("money", "project_points") if paid else (), **options
    ) as h:
        h.review = h.review.model_copy(
            update={
                "decision": decision,
                "findings": (finding(),) if decision == "needs_revision" else (),
            }
        )
        async with h.factory() as session, session.begin():
            await insert_review(session, h.review)
            h.submitter_id = await session.scalar(
                text("SELECT contributor_id FROM public.submissions WHERE id=:id"),
                {"id": h.request.submission_id},
            )
        h.reviewer_record = ContributionRecordInput(
            id=new_record_id(),
            project_id=h.review.project_id,
            task_id=h.review.task_id,
            submission_id=h.review.submission_id,
            artifact_hash=h.review.artifact_hash,
            contribution_type="completed_review",
            contributor_id=h.review.reviewer_id,
            source_review_id=h.review.id,
            source_review_lease_id=h.review.review_lease_id,
            source_final_acceptance_id=None,
            source_task_assignment_id=None,
            contribution_policy_version_id=h.review.reviewer_contribution_policy_version_id,
        )
        yield h


@asynccontextmanager
async def authorized_submitter_source(
    tmp_path, url, *, paid=False, contribution_awards=None, retire_before_outcome=False, **options
):
    """Create all submitter facts through the actual authorized outcome; never a standalone CON insert."""
    from tests.tasks.post_submit_routing.outcome_support import (
        authorized_routing_source,
        apply_outcome,
    )
    from app.modules.reviews.api.acceptance import FinalAcceptanceFacts
    from tests.contributions.participation.support import request_for, participant
    import json

    awards = (
        tuple(contribution_awards)
        if contribution_awards is not None
        else (("money", "project_points") if paid else ())
    )
    async with authorized_routing_source(tmp_path, url, contribution_awards=awards, **options) as h:
        if retire_before_outcome:
            await retire_policy_and_suspend_bindings(h)
        async with h.factory() as session, session.begin():
            h.outcome = await apply_outcome(session, h, 2)
        async with h.factory() as session:
            value = await session.scalar(
                text("SELECT to_jsonb(f) FROM public.final_acceptances f WHERE id=:id"),
                {"id": h.outcome["final_acceptance_id"]},
            )
            h.acceptance = FinalAcceptanceFacts.model_validate_json(json.dumps(value))
            value = await session.scalar(
                text("SELECT to_jsonb(c) FROM public.contribution_records c WHERE id=:id"),
                {"id": h.outcome["economic"].contribution_record_id},
            )
            value.pop("created_at")
            h.submitter_record = ContributionRecordInput.model_validate_json(json.dumps(value))
            h.route_operation_id = UUID(
                await session.scalar(
                    text(
                        "SELECT authority_context#>>'{request,route_operation_id}' FROM public.task_post_submit_routing_manifests WHERE id=:id"
                    ),
                    {"id": h.outcome["routing_manifest_id"]},
                )
            )
        async with h.factory() as session, session.begin():
            h.participation = await participant(session).participate_submitter(
                request_for(h, acceptance_disposition="replay")
            )
        yield h


async def insert_record(session, record, **changes):
    values = record.model_dump() | changes
    for name in ("project_id", "task_id", "submission_id", "contributor_id", "source_task_assignment_id"):
        if values[name] is not None:
            values[name] = str(values[name])
    await session.execute(insert(ContributionRecord).values(**values))


async def award_values(session, record):
    definitions = (await session.scalars(select(ContributionAwardDefinition).where(
        ContributionAwardDefinition.contribution_policy_version_id == record.contribution_policy_version_id,
        ContributionAwardDefinition.contribution_type == record.contribution_type,
    ).order_by(ContributionAwardDefinition.instrument_type))).all()
    return [dict(
        id=new_record_id(), project_id=record.project_id, contribution_record_id=record.id,
        contributor_id=record.contributor_id,
        contribution_policy_version_id=record.contribution_policy_version_id,
        award_definition_id=d.id, adapter_binding_id=d.adapter_binding_id,
        instrument_type=d.instrument_type, unit_code=d.unit_code, quantity=d.quantity,
        correlation_id=new_record_id(),
    ) for d in definitions]


async def insert_award(session, values, **changes):
    values = values | changes
    for name in ("project_id", "contributor_id"):
        values[name] = str(values[name])
    await session.execute(insert(CompensationAward).values(**values))


async def rows(session, table):
    assert table in {"contribution_records", "compensation_awards", "final_acceptances", "reviews"}
    return list((await session.scalars(text(
        f"SELECT to_jsonb(r) FROM public.{table} r ORDER BY id"
    ))).all())


async def retire_policy_and_suspend_bindings(h):
    """Change current availability through real Finance owners after work is frozen."""
    from types import SimpleNamespace
    from app.adapters.auth import compensation_adapter_binding_authorization
    from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
    from app.modules.authorization.runtime import HumanAuthorizationContext, ActorKind, ActorStatus, IdentityLinkStatus
    from app.modules.compensation.api import AdapterBindingSuspendRequest
    from app.modules.compensation.service import AdapterBindingService
    from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility
    from tests.authorization.contribution_policies.postgresql_support import PolicyWorld
    from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor

    project_id = h.request.project_id
    async with h.factory() as session:
        frozen_policy_id = await session.scalar(
            text("SELECT contribution_policy_version_id FROM public.submissions WHERE id=:id"),
            {"id": h.request.submission_id},
        )
    actor, grant = await seed_review_actor(h.factory, project_id, role="finance_authority")
    context = HumanAuthorizationContext(
        actor_profile_id=actor.actor_profile_id, identity_link_id=actor.identity_link_id,
        actor_kind=ActorKind.HUMAN, actor_status=ActorStatus.ACTIVE,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=new_record_id(), correlation_id=new_record_id(),
    )
    world = PolicyWorld(None, project_id, new_record_id(), context, str(grant))
    async with h.factory() as session, session.begin():
        policy_id = await session.scalar(
            text(
                "SELECT contribution_policy_id FROM public.contribution_policy_versions WHERE id=:id"
            ),
            {"id": frozen_policy_id},
        )
        prior = SimpleNamespace(
            contribution_policy_id=policy_id, contribution_policy_version_id=frozen_policy_id
        )
        await world.service(session).retire(world.request("retire", prior))
    async with h.factory() as session:
        bindings = (await session.execute(text(
            "SELECT DISTINCT adapter_binding_id FROM public.contribution_award_definitions "
            "WHERE contribution_policy_version_id=:id"
        ), {"id": prior.contribution_policy_version_id})).scalars().all()
    for binding in bindings:
        async with h.factory() as session, session.begin():
            service = AdapterBindingService(
                session, mutation_authorization=compensation_adapter_binding_authorization(session, context),
                projects=ProjectCompensationBindingEligibility(session),
                actors=CompensationAdapterActorEligibility(session),
            )
            await service.suspend(
                AdapterBindingSuspendRequest(
                    operation_id=new_record_id(),
                    actor_profile_id=context.actor_profile_id,
                    project_id=project_id,
                    adapter_binding_id=UUID(str(binding)),
                    expected_lifecycle_version=1,
                )
            )
    async with h.factory() as session:
        assert await session.scalar(text(
            "SELECT status FROM public.contribution_policy_versions WHERE id=:id"
        ), {"id": prior.contribution_policy_version_id}) == "retired"
        states = (
            await session.scalars(
                text(
                    "SELECT status FROM public.project_compensation_adapter_bindings WHERE project_id=:id"
                ),
                {"id": project_id},
            )
        ).all()
        assert len(states) == 2 and set(states) == {"suspended"}
