"""Stored upstream prerequisites for checker/review-owner tests.

These fixtures do not prove Submission creation or ART admission, return an
HTTP response, or make a hidden endpoint public. They seed a stored Submission
with valid locked lineage; they never execute a checker or enqueue work.
"""

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
        service = task_service(session, settings=get_settings())
        await service._load_locked_task_context(task)
        submission = build_submission(
            submission_id=submission_id, task=task, contributor_id=task.assigned_to,
            task_assignment_id=assignment.id,
            contribution_policy_version_id=assignment.submitter_contribution_policy_version_id,
            # Existing CHECKERS/REV prerequisites, pending ARCH-04B/04C. Exact
            # TASK assignment custody is required; no ART facts are invented and
            # this fixture does not prove canonical intake or hidden creation.
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
        task.status = "submitted"
        await session.flush()
        locked_at = datetime.now(UTC)
        submission.locked_at = locked_at
        for item in submission.evidence_items:
            item.locked_at = locked_at
        await session.commit()
    return submission_id


async def seed_retained_checker_run(submission_id: str, *, routing="allow_review", results=(), status="completed") -> str:
    """Seed retained CHECKERS evidence under real foreign keys and immutable guards.

    This is a storage prerequisite, not a claim that runtime evaluation executed.
    """
    from app.modules.checkers.models import CheckerRun, CheckerResult
    from app.modules.checkers.runner import canonical_artifact_manifest_hash

    run_id = str(new_record_id())
    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, submission_id)
        assert submission is not None
        now = datetime.now(UTC)
        run = CheckerRun(
            id=run_id, task_id=submission.task_id, submission_id=submission.id,
            submission_version=submission.version, trigger_source="retained_evidence",
            status="running", routing_recommendation=routing, outcome_source="auto_checker",
            triggered_by=submission.contributor_id, triggered_by_subject="retained-subject",
            triggered_by_issuer="retained-issuer", trigger_auth_source="flow",
            attempt_number=1, is_current_for_submission=True,
            **{column.name: getattr(submission, column.name) for column in CheckerRun.__table__.columns
               if column.name.startswith("locked_")},
            package_hash=submission.package_hash,
            artifact_hash_manifest=submission.artifact_hash_manifest,
            artifact_manifest_hash=canonical_artifact_manifest_hash(submission.artifact_hash_manifest),
            created_at=now, queued_at=now, started_at=now, completed_at=None,
            results=[CheckerResult(**dict(dict(
                id=str(new_record_id()), checker_run_id=run_id, task_id=submission.task_id,
                submission_id=submission.id, checker_name="check_evidence_present",
                status="passed", severity="info", blocks_review=False,
                message="internal sentinel", worker_message="Evidence present",
                worker_suggested_fix=None, worker_visible=True,
            ), **item)) for item in results],
        )
        session.add(run)
        await session.flush()  # Result insertion occurs before the terminal outcome.
        run.status = status
        run.completed_at = now if status in {"completed", "failed"} else None
        await session.commit()
    return run_id
