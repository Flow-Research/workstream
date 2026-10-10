"""Packets built from real activated guides, admitted ZIPs and executed checker runs."""

from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select, text

from app.core.identifiers import new_record_id
from app.modules.artifacts.api.review_packet import (
    ReviewGuideMember,
    ReviewPacketMembership,
    ReviewPacketMembershipRequest,
    ReviewSubmissionMember,
)
from app.modules.projects.models import (
    GuideMutationIdempotencyRecord,
    GuideSourceArtifactIngest,
    GuideSourceSnapshotItem,
    ProjectGuide,
)
from app.modules.reviews.repository import ReviewQueueRepository
from app.modules.reviews.schemas import (
    ReviewLeaseInput,
    ReviewQueueEntryInput,
    ReviewRoutingMode,
    ReviewRoutingReason,
)
from app.modules.tasks.models import Submission
from tests.tasks.post_submit_routing.support import completed_source
from tests.test_review_lease_persistence import _human_actor


@asynccontextmanager
async def packet_source(
    tmp_path,
    database_url,
    *,
    lease_duration=timedelta(days=1),
    completed_source_factory=completed_source,
    **source_options,
):
    async with completed_source_factory(tmp_path, database_url, **source_options) as h:
        await prepare_packet(h, lease_duration=lease_duration)
        yield h


async def prepare_packet(h, *, lease_duration=timedelta(days=1)):
    """Attach canonical packet membership and a committed lease to a completed source."""
    async with h.factory() as session:
        submission = await session.get(Submission, str(h.request.submission_id))
        guide = await session.scalar(
            select(ProjectGuide).where(
                ProjectGuide.project_id == str(h.source["project_id"]),
                ProjectGuide.version == submission.locked_guide_version,
            )
        )
        activation = await session.scalar(
            select(GuideMutationIdempotencyRecord).where(
                GuideMutationIdempotencyRecord.operation_id == guide.activation_operation_id,
            )
        )
        proposal = activation.response_json["command"]["target"]["proposal"]
        rows = (
            await session.execute(
                select(GuideSourceSnapshotItem, GuideSourceArtifactIngest)
                .join(
                    GuideSourceArtifactIngest,
                    GuideSourceArtifactIngest.source_item_id == GuideSourceSnapshotItem.id,
                )
                .where(
                    GuideSourceSnapshotItem.source_snapshot_id
                    == submission.locked_guide_source_snapshot_id
                )
                .order_by(GuideSourceSnapshotItem.item_order)
            )
        ).all()
        h.membership = ReviewPacketMembership(
            request=ReviewPacketMembershipRequest(
                project_id=h.source["project_id"],
                task_id=h.request.task_id,
                submission_id=h.request.submission_id,
                submission_version=submission.version,
                checker_run_id=h.result.attempt_id,
                result_id=h.source["result_id"],
                guide_id=UUID(guide.id),
                guide_version=guide.version,
                source_snapshot_id=UUID(submission.locked_guide_source_snapshot_id),
                project_setup_run_id=UUID(proposal["setup_run_id"]),
                setup_generation=proposal["setup_generation"],
            ),
            submission=ReviewSubmissionMember(
                binding_id=UUID(submission.artifact_binding_id),
                logical_role="submission_bundle_original",
                media_type="application/zip",
            ),
            guide_documents=tuple(
                ReviewGuideMember(
                    ingest_id=UUID(ingest.id),
                    source_item_id=UUID(item.id),
                    item_order=item.item_order,
                    logical_role="guide_source_original",
                    media_type=item.media_type,
                )
                for item, ingest in rows
            ),
        )
        repository = ReviewQueueRepository(session)
        queue = await repository.add_queue_entry(
            ReviewQueueEntryInput(
                id=new_record_id(),
                project_id=str(h.source["project_id"]),
                task_id=str(h.request.task_id),
                submission_id=submission.id,
                submission_version=submission.version,
                admitting_checker_run_id=str(h.result.attempt_id),
                routing_mode=ReviewRoutingMode.OPEN,
                routing_reason=ReviewRoutingReason.FIRST_SUBMISSION,
            )
        )
        await session.commit()
        actor_id = await _human_actor(session, label="packet-reviewer")
        database_now = await session.scalar(select(func.clock_timestamp()))
        lease = await repository.add_lease(
            ReviewLeaseInput(
                id=new_record_id(),
                review_queue_entry_id=queue.id,
                project_id=queue.project_id,
                task_id=queue.task_id,
                submission_id=submission.id,
                submission_version=submission.version,
                reviewer_id=actor_id,
                reviewer_contribution_policy_version_id=h.source["contribution_policy_version_id"],
                attempt_generation=1,
                expires_at=database_now + lease_duration,
            )
        )
        queue.queue_state = "leased"
        queue.active_lease_id = lease.id
        await session.commit()
        h.lease_id, h.queue_id = lease.id, queue.id


async def raw_insert(session, h, *, header=None, members=None):
    """SQL insertion bypassing repository validation; defer canonical reconciliation."""
    from app.core.hashing import canonical_json_hash

    values = dict(
        id=new_record_id(),
        review_lease_id=h.lease_id,
        review_queue_entry_id=h.queue_id,
        packet_manifest_generation=1,
        **h.membership.request.model_dump(),
        submission_binding_id=h.membership.submission.binding_id,
        submission_logical_role=h.membership.submission.logical_role,
        submission_media_type=h.membership.submission.media_type,
    )
    import json

    actual_members = h.membership.guide_documents if members is None else members
    values.update(header or {})
    body = {
        "request": {key: values[key] for key in ReviewPacketMembershipRequest.model_fields},
        "submission": {
            "binding_id": values["submission_binding_id"],
            "logical_role": values["submission_logical_role"],
            "media_type": values["submission_media_type"],
        },
    }
    body["guide_documents"] = [
        m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in actual_members
    ]
    values["packet_manifest_digest"] = (header or {}).get(
        "packet_manifest_digest", canonical_json_hash(json.loads(json.dumps(body, default=str)))
    )
    await session.execute(
        text(
            "INSERT INTO public.review_packet_manifests ("
            + ",".join(values)
            + ") VALUES ("
            + ",".join(":" + key for key in values)
            + ")"
        ),
        values,
    )
    for member in h.membership.guide_documents if members is None else members:
        item = dict(
            packet_id=values["id"],
            **(member.model_dump() if hasattr(member, "model_dump") else member),
        )
        await session.execute(
            text(
                "INSERT INTO public.review_packet_guide_items ("
                + ",".join(item)
                + ") VALUES ("
                + ",".join(":" + key for key in item)
                + ")"
            ),
            item,
        )
    return values["id"]


async def wait_for_lease_expiry(session, lease_id):
    """Wait for the actual database deadline without rewriting immutable lease facts."""
    await session.execute(
        text(
            "SELECT pg_sleep(GREATEST(0, EXTRACT(EPOCH FROM "
            "(expires_at-clock_timestamp())))::double precision + 0.01) "
            "FROM public.review_leases WHERE id=:id"
        ),
        {"id": lease_id},
    )
    assert (
        await session.scalar(
            text(
                "SELECT status='active' AND expires_at<=clock_timestamp() "
                "FROM public.review_leases WHERE id=:id"
            ),
            {"id": lease_id},
        )
        is True
    )
