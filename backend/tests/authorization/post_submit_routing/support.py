"""Strict detached routing values and real-owner preparation helpers."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.outbox.api import OutboxClaim
from app.modules.authorization.domain.post_submit_routing import (
    AutomatedAcceptanceConsequence,
    HumanAdmissionConsequence,
    PostSubmitRoutingResourceContext,
)
from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsRequest
from app.modules.tasks.api.post_submit_routing import (
    TaskPostSubmitSourceProposal,
    TaskRoutingRequestFacts,
    TaskRoutingSelection,
    task_routing_request_digest,
)
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequests
from app.adapters.checkers import evaluation_coordinator
from tests.tasks.post_submit_routing.contract_fixtures import SHA_A, _source_values
from tests.tasks.post_submit_routing.support import (
    completion_for,
    joined_source_facts,
    source_values,
)


def detached_request_and_source(
    *, human_review_required: bool = True
) -> tuple[TaskRoutingRequestFacts, TaskPostSubmitSourceProposal]:
    """Build mutually exact values; neither value asserts storage or authority."""
    source_values_ = _source_values(human_review_required=human_review_required)
    selection = TaskRoutingSelection(
        project_id=source_values_["project_id"],
        task_id=source_values_["task_id"],
        submission_id=source_values_["submission_id"],
        submission_version=source_values_["submission_version"],
        checker_run_id=source_values_["checker_run_id"],
        evaluation_request_id=source_values_["evaluation_request_id"],
        evaluation_request_digest=source_values_["request_digest"],
        evaluation_generation=source_values_["evaluation_generation"],
        result_id=source_values_["result_id"],
        result_digest=source_values_["result_digest"],
        completion_event_id=source_values_["completion_event_id"],
        routing_recommendation="allow_review",
    )
    request = TaskRoutingRequestFacts(
        **selection.model_dump(),
        route_operation_id=new_record_id(),
        routing_manifest_id=new_record_id(),
        route_request_digest=task_routing_request_digest(selection),
        created_at=datetime(2026, 1, 3, tzinfo=UTC),
    )
    source_values_["id"] = request.routing_manifest_id
    return request, TaskPostSubmitSourceProposal(
        **{k: v for k, v in source_values_.items() if k != "created_at"}
    )


def claim_for(request: TaskRoutingRequestFacts) -> OutboxClaim:
    """Return a well-shaped untrusted claim aligned with the completion."""
    claimed_at = datetime(2026, 1, 3, 1, tzinfo=UTC)
    return OutboxClaim(
        event_id=request.completion_event_id,
        project_id=request.project_id,
        payload_digest=SHA_A,
        claim_generation=1,
        claim_owner="workstream.task.post_submit_router:test",
        claimed_at=claimed_at,
        claim_expires_at=claimed_at + timedelta(minutes=5),
    )


def accepted_effects_for(source: TaskPostSubmitSourceProposal) -> TaskAcceptedEffectsRequest:
    """Select the exact source lineage for the false-policy branch."""
    return TaskAcceptedEffectsRequest(
        project_id=source.project_id,
        task_id=source.task_id,
        assignment_id=source.assignment_id,
        submission_id=source.submission_id,
        submission_version=source.submission_version,
        contributor_id=source.contributor_id,
        contribution_policy_version_id=source.contribution_policy_version_id,
        content_id=source.content_id,
        content_sha256=source.content_sha256,
        final_acceptance_id=new_record_id(),
        expected_task_status="evaluation_pending",
    )


def resource_for(*, human_review_required: bool = True) -> PostSubmitRoutingResourceContext:
    """Build one internally exact resource for the selected locked-policy branch."""
    request, source = detached_request_and_source(
        human_review_required=human_review_required
    )
    consequence = (
        HumanAdmissionConsequence()
        if human_review_required
        else AutomatedAcceptanceConsequence(
            task_effects=accepted_effects_for(source), authorized_lifecycle_generation=2
        )
    )
    return PostSubmitRoutingResourceContext(
        router_actor_id=new_record_id(),
        router_identity_link_id=new_record_id(),
        resource_id=request.routing_manifest_id,
        scope_project_id=request.project_id,
        request=request,
        source=source,
        claim=claim_for(request),
        consequence=consequence,
    )


def changed_request(
    request: TaskRoutingRequestFacts, **changes: object
) -> TaskRoutingRequestFacts:
    """Change selectors while preserving TASK request's own digest invariant."""
    values = request.model_dump()
    values.update(changes)
    selection = TaskRoutingSelection(
        **{name: values[name] for name in TaskRoutingSelection.model_fields}
    )
    values["route_request_digest"] = task_routing_request_digest(selection)
    return TaskRoutingRequestFacts(**values)


async def stage_real_request(h) -> TaskRoutingRequestFacts:
    """Commit one request through TASK's genuine reservation operation."""
    async with h.factory() as session, session.begin():
        return await TaskRoutingRequests(session, evaluation_coordinator(session)).stage(
            h.source["completion_event_id"], completion_for(h)
        )


async def provision_router(factory) -> None:
    """Persist the fixed router profile and link through the real actor schema."""
    async with factory() as session, session.begin():
        existing = await session.scalar(
            select(ActorProfile.id).where(
                ActorProfile.service_identity
                == ServiceIdentity.TASK_POST_SUBMIT_ROUTER.value
            )
        )
        if existing is not None:
            return
        actor_id, link_id = new_record_id(), new_record_id()
        session.add(
            ActorProfile(
                id=str(actor_id),
                actor_kind="service",
                status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=ServiceIdentity.TASK_POST_SUBMIT_ROUTER.value,
                created_by="arch04e2a-test",
            )
        )
        session.add(
            ActorIdentityLink(
                id=str(link_id),
                actor_profile_id=str(actor_id),
                issuer="flow-test",
                subject=str(actor_id),
                subject_kind="service",
                status="active",
                linked_by="arch04e2a-test",
            )
        )


async def real_source_facts(h, request: TaskRoutingRequestFacts) -> TaskPostSubmitSourceProposal:
    """Join genuine completed owners into the source allocated by the request."""
    stored = await source_values(h)
    async with h.factory() as session:
        stored["created_at"] = await session.scalar(text("SELECT clock_timestamp()"))
    stored["id"] = request.routing_manifest_id
    joined = await joined_source_facts(h, stored)
    return TaskPostSubmitSourceProposal(**joined.model_dump(exclude={"created_at"}))


async def effect_snapshot(session):
    """Observe exact authorization/source/product rows around planned denial."""
    return (
        await session.execute(
            text(
                """
                SELECT
                  (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.route_operation_id)
                     FROM public.task_post_submit_routing_requests r),
                  (SELECT jsonb_agg(to_jsonb(m) ORDER BY m.id)
                     FROM public.task_post_submit_routing_manifests m),
                  (SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id) FROM public.audit_events a),
                  (SELECT jsonb_agg(to_jsonb(q) ORDER BY q.id) FROM public.review_queue_entries q),
                  (SELECT jsonb_agg(to_jsonb(f) ORDER BY f.id) FROM public.final_acceptances f),
                  (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM public.contribution_records c),
                  (SELECT jsonb_agg(to_jsonb(w) ORDER BY w.id) FROM public.compensation_awards w),
                  (SELECT jsonb_agg(to_jsonb(t) ORDER BY t.id) FROM public.workstream_tasks t),
                  (SELECT jsonb_agg(to_jsonb(s) ORDER BY s.id) FROM public.submissions s)
                """
            )
        )
    ).one()
