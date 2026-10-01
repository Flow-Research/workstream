"""Stored upstream prerequisites for checker/review-owner tests.

These fixtures use ART preparation, verification and consumption owners with
a scripted provider, then seed retained Submission projections with locked
lineage. They do not expose public intake or claim live post-submit authority.
"""

from uuid import UUID
from tests.retained_material_fixtures import retained_admission, RetainedBindingAuthority
from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService
from app.modules.artifacts.api import SubmissionAdmissionConsumptionRequest
from app.modules.tasks.api import TaskSubmissionContextRequest
from app.modules.tasks.repository import TaskRepository
from app.core.config import get_settings

from app.adapters.tasks import task_service

from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.tasks.models import EvidenceItem, Submission, TaskAssignment, WorkstreamTask
from app.modules.tasks.schemas import SubmissionCreate
from app.modules.tasks.submission_composition import build_submission
from datetime import UTC, datetime


async def seed_retained_submission(
    task_id: str, payload: dict, *, predecessor_id: str | None = None,
) -> str:
    """Seed a retained locked packet with guards enabled; not an intake proof."""
    packet = SubmissionCreate.model_validate(payload)
    submission_id = str(new_record_id())
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
        session.expunge_all()
        await session.rollback()
        # Detached selectors remain fixture inputs; real preparation rechecks them.
        admission_id = await retained_admission(
            db_session.get_session_factory(), task, assignment, link, packet, predecessor_id,
        )
        task = await session.get(WorkstreamTask, task_id)
        context = await TaskRepository(session).lock_submission_context(TaskSubmissionContextRequest(
            UUID(task_id), UUID(assignment.id), UUID(task.assigned_to),
            UUID(predecessor_id) if predecessor_id else None,
        ))
        service = task_service(session, settings=get_settings())
        await service._load_locked_task_context(task)
        submission = build_submission(
            submission_id=submission_id, task=task, contributor_id=task.assigned_to,
            task_assignment_id=assignment.id,
            contribution_policy_version_id=assignment.submitter_contribution_policy_version_id,
            # Retained packet projection; ART supplies the canonical byte references.
            version=predecessor.version + 1 if predecessor else 1, summary=packet.summary,
            worker_attestation=packet.worker_attestation,
            package_uri=packet.package_uri, package_hash=packet.package_hash,
            artifact_hash_manifest=[entry.model_dump() for entry in packet.artifact_hash_manifest],
            supersedes_submission_id=predecessor_id,
            evidence_items=[EvidenceItem(
                id=str(new_record_id()), submission_id=submission_id, type=item.type,
                label=item.label, uri=item.uri, hash=item.hash,
                size_bytes=item.size_bytes, metadata_json=item.metadata,
            ) for item in packet.evidence_items],
        )
        session.add(submission)
        await session.flush()
        consumed = await SubmissionAdmissionConsumptionService(
            session, RetainedBindingAuthority(),
        ).consume(SubmissionAdmissionConsumptionRequest(
            UUID(admission_id), UUID(submission_id), submission.version, context,
        ))
        assert consumed.status == "consumed"
        submission.submission_bundle_admission_id = admission_id
        submission.artifact_binding_id = str(consumed.binding_id)
        submission.artifact_content_id = str(consumed.content_id)
        task.status = "submitted"
        await session.flush()
        locked_at = datetime.now(UTC)
        submission.locked_at = locked_at
        for item in submission.evidence_items:
            item.locked_at = locked_at
        await session.commit()
    return submission_id


async def seed_retained_checker_run(submission_id: str, *, failures=(), state="completed", generation=1) -> str:
    """Seed closed history through real CHECKERS custody, with controlled phase authority."""
    from tests.checkers.execution.storage_fixture import seed_storage_run
    return await seed_storage_run(db_session.get_session_factory(), submission_id,
                                  failures=failures, state=state, generation=generation)
