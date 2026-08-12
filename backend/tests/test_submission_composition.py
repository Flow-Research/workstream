"""Focused behavior proof for hidden admission-backed Submission composition."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.tasks.api import (
    SubmissionArtifactAdmissionResult,
    SubmissionCreationRequest,
    SubmissionCreationUnavailable,
    TaskLockedProjectContextReferences,
    TaskSubmissionContextFacts,
)
from app.modules.tasks.submission_composition import TaskSubmissionCreationService


class _Session:
    def in_transaction(self):
        return True

    def in_nested_transaction(self):
        return False


def _request():
    return SubmissionCreationRequest(
        admission_id=uuid4(), task_id=uuid4(), assignment_id=uuid4(),
        contributor_id=uuid4(), predecessor_submission_id=None,
        summary="summary", contributor_attestation="attestation",
    )


def _context(request):
    return TaskSubmissionContextFacts(
        task_id=request.task_id, assignment_id=request.assignment_id,
        contributor_id=request.contributor_id, status="in_progress", kind="initial",
        predecessor=None,
        locked_project_context=TaskLockedProjectContextReferences(
            project_id=uuid4(), guide_version="1", source_snapshot_id=uuid4(),
            source_snapshot_hash="sha256:" + "1" * 64, effective_policy_id=uuid4(),
            effective_policy_hash="sha256:" + "2" * 64,
            pre_submit_policy_id=uuid4(),
            pre_submit_policy_bundle_hash="sha256:" + "3" * 64,
        ),
    )


def _task():
    values = {
        "locked_guide_version": "1", "locked_post_submit_checker_policy_id": str(uuid4()),
        "locked_post_submit_checker_policy_version": "1",
        "locked_post_submit_checker_policy_hash": "sha256:" + "4" * 64,
        "locked_post_submit_checker_policy_body": {}, "locked_review_policy_id": str(uuid4()),
        "locked_review_policy_generation": 1,
        "locked_review_policy_hash": "sha256:" + "5" * 64,
        "locked_revision_policy_id": str(uuid4()), "locked_revision_policy_generation": 1,
        "locked_revision_policy_hash": "sha256:" + "6" * 64,
        "locked_payment_policy_version": "1", "locked_guide_source_snapshot_id": str(uuid4()),
        "locked_guide_source_snapshot_hash": "sha256:" + "7" * 64,
        "locked_effective_project_submission_artifact_policy_id": str(uuid4()),
        "locked_effective_project_submission_artifact_policy_hash": "sha256:" + "8" * 64,
        "locked_pre_submit_checker_policy_id": str(uuid4()),
        "locked_pre_submit_checker_bundle_hash": "sha256:" + "9" * 64,
    }
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_command_orders_authority_task_art_persistence_and_final_consumption():
    request = _request()
    events = []

    class Authority:
        async def authorize(self, facts): events.append(("authorize", facts.submission_id))
        async def consume(self, facts): events.append(("final", facts.submission_version))

    class Admissions:
        async def consume(self, value):
            events.append(("art", value.submission_version))
            return SubmissionArtifactAdmissionResult(binding_id=uuid4(), content_id=uuid4())

    service = TaskSubmissionCreationService(_Session(), authorization=Authority(), admissions=Admissions())

    class Repository:
        async def lock_submission_context(self, value):
            events.append(("task", value.task_id))
            return _context(request)
        async def get_task(self, task_id): return _task()
        async def add_submission(self, submission): events.append(("persist", submission.version))

    service._repository = Repository()
    result = await service.create(request)
    assert [event[0] for event in events] == ["authorize", "task", "art", "persist", "final"]
    assert result.submission_version == 1


@pytest.mark.asyncio
async def test_denial_precedes_task_lock_and_all_mutation():
    class Authority:
        async def authorize(self, facts): raise SubmissionCreationUnavailable
        async def consume(self, facts): raise AssertionError("unreachable")

    service = TaskSubmissionCreationService(_Session(), authorization=Authority(), admissions=None)
    service._repository = SimpleNamespace(
        lock_submission_context=lambda value: pytest.fail("TASK state was revealed")
    )
    with pytest.raises(SubmissionCreationUnavailable):
        await service.create(_request())


@pytest.mark.asyncio
async def test_final_authority_failure_remains_inside_caller_transaction():
    request = _request()

    class Authority:
        async def authorize(self, facts): pass
        async def consume(self, facts): raise SubmissionCreationUnavailable

    class Admissions:
        async def consume(self, value):
            return SubmissionArtifactAdmissionResult(binding_id=uuid4(), content_id=uuid4())

    service = TaskSubmissionCreationService(_Session(), authorization=Authority(), admissions=Admissions())
    persisted = []

    class Repository:
        async def lock_submission_context(self, value): return _context(request)
        async def get_task(self, task_id): return _task()
        async def add_submission(self, submission): persisted.append(submission)

    service._repository = Repository()
    with pytest.raises(SubmissionCreationUnavailable):
        await service.create(request)
    assert len(persisted) == 1
