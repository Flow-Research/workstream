"""Isolated storage fixtures; these are not authorized product decisions."""

import zipfile
from contextlib import asynccontextmanager
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import insert, select, text

from app.adapters.tasks import submitted_bundle_port, task_submission_context_port
from app.core.identifiers import new_record_id
from app.modules.actors.models import ActorIdentityLink
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
from app.modules.artifacts.api.submission_manifest import (
    build_submission_manifest,
)
from app.modules.checkers.models import CheckerRun
from app.modules.reviews.decision.models import (
    FindingResolution,
    Review,
    ReviewDecisionRequest,
    ReviewFinding,
)
from app.modules.reviews.decision.schemas import ReviewFindingInput, ReviewSourceInput
from app.modules.reviews.packet.repository import ReviewPacketRepository
from app.modules.tasks.api.submission_context import TaskSubmissionContextRequest
from app.modules.tasks.api.submitted_bundle import SubmittedBundleRequest
from app.modules.tasks.models import Submission
from tests.checkers.execution.support import live_executor, reserve
from tests.reviews.packet.support import packet_source, prepare_packet
from tests.post_submit_materialization_helpers import create_source_submission
from tests.tasks.post_submit_routing.support import next_request, source_values
from tests.test_artifact_admission import _context


@asynccontextmanager
async def review_source(tmp_path, database_url, **options):
    from tests.checkers.external.support import post_registry_spec

    options.setdefault("post_submit_registry_spec", post_registry_spec())
    async with packet_source(tmp_path, database_url, **options) as h:
        await attach_review_source(h)
        yield h


async def attach_review_source(h):
    async with h.factory() as session:
        packet = await ReviewPacketRepository(session).store(h.lease_id, h.membership)
        await session.commit()
        row = (
            (
                await session.execute(
                    text("""
            SELECT s.*, l.reviewer_id, l.reviewer_contribution_policy_version_id,
                   c.sha256 FROM public.submissions s
            JOIN public.review_leases l ON l.id=:lease
            JOIN public.artifact_contents c ON c.id=s.artifact_content_id
            WHERE s.id=:submission
        """),
                    {"lease": h.lease_id, "submission": h.request.submission_id},
                )
            )
            .mappings()
            .one()
        )
        h.review = ReviewSourceInput(
            id=new_record_id(),
            project_id=h.membership.request.project_id,
            task_id=UUID(str(row["task_id"])),
            task_assignment_id=UUID(str(row["task_assignment_id"])),
            submission_id=UUID(str(row["id"])),
            submission_version=row["version"],
            review_queue_entry_id=h.queue_id,
            review_lease_id=h.lease_id,
            packet_manifest_id=packet.packet_manifest_id,
            packet_manifest_digest=packet.packet_manifest_digest,
            artifact_hash=row["sha256"],
            reviewer_id=UUID(str(row["reviewer_id"])),
            reviewer_contribution_policy_version_id=row["reviewer_contribution_policy_version_id"],
            locked_guide_version=row["locked_guide_version"],
            locked_review_policy_id=UUID(str(row["locked_review_policy_id"])),
            locked_review_policy_generation=row["locked_review_policy_generation"],
            locked_review_policy_hash=row["locked_review_policy_hash"],
            predecessor_review_id=None,
            decision="accept",
            summary="Verified the exact submitted work.",
            findings=(),
            resolutions=(),
        )


def finding(*, kind="blocking", label="Required result"):
    return ReviewFindingInput(
        id=new_record_id(),
        finding_kind=kind,
        area="Deliverable",
        issue=label,
        required_fix="Correct the documented result.",
    )


async def insert_review(
    session,
    source,
    *,
    header=None,
    request=None,
    close=True,
    include_request=True,
    include_children=True,
):
    """Stage raw owner rows in the caller transaction; SQL performs validation."""
    values = source.model_dump(exclude={"findings", "resolutions"})
    values.update(
        finding_count=len(source.findings),
        blocking_finding_count=sum(f.finding_kind == "blocking" for f in source.findings),
        resolution_count=len(source.resolutions),
        aggregate_digest=source.aggregate_digest,
    )
    values.update(header or {})
    for field in (
        "project_id",
        "task_id",
        "task_assignment_id",
        "submission_id",
        "reviewer_id",
        "locked_review_policy_id",
    ):
        values[field] = str(values[field])
    await session.execute(insert(Review).values(**values))
    if include_children:
        for order, member in enumerate(source.findings):
            await session.execute(
                insert(ReviewFinding).values(
                    **member.model_dump(), review_id=source.id, item_order=order
                )
            )
        for order, member in enumerate(source.resolutions):
            await session.execute(
                insert(FindingResolution).values(
                    **member.model_dump(), review_id=source.id, item_order=order
                )
            )
    if include_request:
        request_values = dict(
            id=new_record_id(),
            operation_id=new_record_id(),
            project_id=source.project_id,
            reviewer_id=source.reviewer_id,
            idempotency_key=new_record_id(),
            review_id=source.id,
            request_digest=source.request_digest,
        )
        request_values.update(request or {})
        for field in ("project_id", "reviewer_id"):
            request_values[field] = str(request_values[field])
        await session.execute(insert(ReviewDecisionRequest).values(**request_values))
    if close:
        await close_review_lease(session, source)


async def close_review_lease(session, source):
    await session.execute(
        text("""
        UPDATE public.review_leases SET status='consumed', close_reason='review_recorded',
          closed_at=clock_timestamp() WHERE id=:lease;
    """),
        {"lease": source.review_lease_id},
    )
    await session.execute(
        text("""
        UPDATE public.review_queue_entries SET queue_state='closed',closed_reason='review_recorded',
          active_lease_id=NULL,closed_at=clock_timestamp() WHERE id=:queue
    """),
        {"queue": source.review_queue_entry_id},
    )


async def _route_replacement_cause(h):
    """Route a later real contributor failure without changing the reviewed run."""
    from app.adapters.tasks import evaluation_completion_handler
    from app.modules.outbox.api import HandlerOutcome
    from tests.authorization.post_submit_routing.support import provision_router
    from tests.checkers.execution.support import ControlledSelectedExecution
    from tests.tasks.post_submit_routing.outcome_support import invoked_completion

    async with h.factory() as session:
        current = (
            await session.execute(
                text("""
            SELECT t.status, f.current_run_id FROM public.workstream_tasks t
            JOIN public.checker_submission_fences f ON f.submission_id=:submission
            WHERE t.id=:task
        """),
                {"submission": h.request.submission_id, "task": h.request.task_id},
            )
        ).one()
        assert current.status == "evaluation_pending"
        assert str(current.current_run_id) == str(h.result.attempt_id)
    failure = SimpleNamespace(**vars(h))
    await next_request(failure)
    await reserve(failure)
    failure.result = await live_executor(
        failure, selected_execution=ControlledSelectedExecution(verdict="failed")
    ).evaluate_post_submission(failure.request)
    async with h.factory() as session:
        run = await session.get(CheckerRun, str(failure.result.attempt_id))
        assert run.status == "completed" and run.routing_recommendation == "needs_revision"
        failure.material = dict(run.material_custody)
    failure.source = await source_values(failure)
    async with h.factory() as session, session.begin():
        await session.execute(
            text("UPDATE public.task_assignments SET accepted_at=clock_timestamp() WHERE id=:id"),
            {"id": h.request.assignment_id},
        )
    await provision_router(h.factory)
    failure.envelope = await invoked_completion(failure)
    assert (
        await evaluation_completion_handler(sessions=h.factory)(failure.envelope)
        is HandlerOutcome.ACKNOWLEDGE
    )
    async with h.factory() as session:
        assert (
            await session.scalar(
                text("SELECT status FROM public.workstream_tasks WHERE id=:id"),
                {"id": h.request.task_id},
            )
            == "needs_revision"
        )
        assert (
            await session.scalar(
                text("""
            SELECT public.task_routing_outcome_complete(m)
            FROM public.task_post_submit_routing_manifests m
            WHERE m.checker_run_id=:run
        """),
                {"run": failure.result.attempt_id},
            )
            is True
        )


async def _admit_successor(h):
    """Create real admitted successor bytes from an authorized later failure."""

    await _route_replacement_cause(h)

    async with h.factory() as session, session.begin():
        prior = await session.get(Submission, str(h.request.submission_id))
        link = await session.scalar(
            select(ActorIdentityLink.id).where(
                ActorIdentityLink.actor_profile_id == prior.contributor_id,
                ActorIdentityLink.status == "active",
            )
        )
        context = _context(
            actor_profile_id=UUID(prior.contributor_id), identity_link_id=UUID(str(link))
        )
        current = await task_submission_context_port(session).lock_submission_context(
            TaskSubmissionContextRequest(
                task_id=h.request.task_id, assignment_id=h.request.assignment_id,
                contributor_id=context.actor_profile_id,
                predecessor_submission_id=h.request.submission_id,
            )
        )
        revision = current.revision_context
        assert revision is not None and revision.source_submission_id == h.request.submission_id

    revised_bytes = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(h.data)) as original,
        zipfile.ZipFile(revised_bytes, "w") as revised,
    ):
        for member in original.infolist():
            revised.writestr(member, original.read(member))
        revised.writestr(
            f"revision-{h.request.submission_version + 1}.txt", "The requested result is corrected."
        )
    revised_data = revised_bytes.getvalue()
    metadata = SubmissionIntakeMetadata(
        task_id=h.request.task_id,
        assignment_id=h.request.assignment_id,
        predecessor_submission_id=h.request.submission_id,
        summary=h.creation_request.summary,
        contributor_attestation=h.creation_request.contributor_attestation,
        revision_preparation_id=revision.preparation_id,
        revision_preparation_sha256=revision.preparation_sha256,
    )
    created = await create_source_submission(
        h.factory, context, h.store.wrapped, h.namespace, h.settings, metadata, revised_data,
    )
    async with h.factory() as session:
        facts = await submitted_bundle_port(session).read(
            SubmittedBundleRequest(h.request.project_id, h.request.task_id, created.submission_id)
        )

    return facts, revised_data, created


async def _evaluate_successor(h, facts, revised_data, created):
    """Run real post-submit evaluation using the new admitted content identity."""
    from app.adapters.checkers import evaluation_coordinator
    manifest = build_submission_manifest(h.inspector.inspect(BytesIO(revised_data)))
    async with h.factory() as session, session.begin():
        stored = await evaluation_coordinator(session).read_reserved_evaluation(
            project_id=h.request.project_id, task_id=h.request.task_id,
            submission_id=facts.submission_id, request_id=created.evaluation_request_id,
        )
        request = stored.request
    successor = SimpleNamespace(
        **{**vars(h), "request": request, "source": {}, "data": revised_data, "manifest": manifest}
    )
    await reserve(successor)
    successor.result = await live_executor(successor).evaluate_post_submission(request)
    async with h.factory() as session:
        run = await session.get(CheckerRun, str(successor.result.attempt_id))
        assert run.status == "completed" and run.routing_recommendation == "allow_review"
        successor.material = dict(run.material_custody)
    successor.source = await source_values(successor)
    return successor


async def successor_source(h, *, with_packet=True):
    """Build an admitted and evaluated successor, optionally with a retained packet."""
    facts, revised_data, created = await _admit_successor(h)
    successor = await _evaluate_successor(h, facts, revised_data, created)
    if with_packet:
        await prepare_packet(successor)
        await attach_review_source(successor)
    return successor
