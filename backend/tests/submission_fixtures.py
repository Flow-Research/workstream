"""Stored upstream prerequisites for checker/review-owner tests.

These fixtures do not prove Submission creation or ART admission, return an
HTTP response, or make a hidden endpoint public. They seed a stored Submission
and exercise the existing finalization/enqueue owners for downstream tests.
"""

from uuid import uuid4

from sqlalchemy import select

from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.tasks.models import EvidenceItem, Submission, TaskAssignment, WorkstreamTask
from app.modules.tasks.schemas import SubmissionCreate
from app.modules.tasks.service import TaskService
from app.modules.tasks.submission_composition import build_submission
from app.schemas.auth import ActorContext


async def seed_finalized_submission_for_checker_test(
    task_id: str, payload: dict, *, predecessor_id: str | None = None,
    raise_on_dispatch_failure: bool = True,
) -> str:
    """Seed one upstream packet, then run real finalization and checker enqueue."""
    packet = SubmissionCreate.model_validate(payload)
    submission_id = str(uuid4())
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, task_id)
        assert task is not None
        assert task.status == ("needs_revision" if predecessor_id else "in_progress")
        predecessor = await session.get(Submission, predecessor_id) if predecessor_id else None
        if predecessor_id:
            assert predecessor is not None and predecessor.task_id == task_id
            assert predecessor.contributor_id == task.assigned_to
        assignment = await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == task_id, TaskAssignment.status == "active",
        ))
        assert assignment is not None and assignment.contributor_id == task.assigned_to
        link = await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.actor_profile_id == task.assigned_to,
        ))
        assert link is not None and link.status == "active"
        actor = ActorContext(
            actor_id=task.assigned_to, external_subject=link.subject,
            external_issuer=link.issuer, roles=("worker",), claim_snapshot={},
            auth_source="dev_mock", is_dev_auth=True,
        )
        service = TaskService(session)
        await service._load_locked_task_context(task)
        submission = build_submission(
            submission_id=submission_id, task=task, contributor_id=task.assigned_to,
            # Retained packets have no ART lineage group. Do not invent half
            # of that group or claim this fixture proves admission-backed writes.
            version=predecessor.version + 1 if predecessor else 1, summary=packet.summary,
            worker_attestation=packet.worker_attestation,
            package_uri=packet.package_uri, package_hash=packet.package_hash,
            artifact_hash_manifest=[entry.model_dump() for entry in packet.artifact_hash_manifest],
            supersedes_submission_id=predecessor_id,
            evidence_items=[EvidenceItem(
                id=str(uuid4()), submission_id=submission_id, type=item.type,
                label=item.label, uri=item.uri, hash=item.hash,
                size_bytes=item.size_bytes, metadata_json=item.metadata,
            ) for item in packet.evidence_items],
        )
        session.add(submission)
        task.status = "submitted"
        await session.flush()
        await service._finalize_submission_for_evaluation(actor, task, submission)
        await session.commit()
        await service._enqueue_pre_review_gate_after_commit(
            actor, submission_id, raise_on_failure=raise_on_dispatch_failure,
        )
    return submission_id
