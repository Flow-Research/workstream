"""Focused behavior proof for hidden admission-backed Submission composition."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.tasks.api import (
    SubmissionPredecessorFacts,
    SubmissionArtifactAdmissionResult,
    SubmissionCreationRequest,
    SubmissionCreationUnavailable,
    TaskLockedProjectContextReferences,
    TaskSubmissionContextFacts,
)
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.adapters.tasks import TransactionalSubmissionCreationCommand
from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService
from app.modules.artifacts.authorization import PreparedSubmissionBindingAuthorization
from app.modules.authorization.prepared import (
    PreparedSubmissionCreationAuthorization,
)
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)


class _Session:
    def in_transaction(self):
        return True

    def in_nested_transaction(self):
        return False

    async def flush(self):
        return None


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
        "id": str(uuid4()),
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


@pytest.mark.parametrize(
    ("actor_status", "link_status"),
    [
        (ActorStatus.SUSPENDED, IdentityLinkStatus.ACTIVE),
        (ActorStatus.ACTIVE, IdentityLinkStatus.REVOKED),
    ],
)
@pytest.mark.asyncio
async def test_human_lifecycle_denial_precedes_task_state(
    actor_status, link_status,
):
    request = _request()
    context = HumanAuthorizationContext(
        actor_profile_id=request.contributor_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=actor_status,
        identity_link_id=uuid4(),
        identity_link_status=link_status,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    authority = PreparedSubmissionCreationAuthorization(object(), context)
    service = TaskSubmissionCreationService(
        _Session(), authorization=authority, admissions=None
    )
    service._repository = SimpleNamespace(
        lock_submission_context=lambda value: pytest.fail("TASK state was revealed")
    )
    with pytest.raises(SubmissionCreationUnavailable):
        await service.create(request)


@pytest.mark.asyncio
async def test_command_orders_authority_task_art_persistence_and_final_consumption():
    request = _request()
    events = []

    class Authority:
        async def authorize(self, facts): events.append(("authorize", facts.task_id))
        async def prepare(self, facts):
            events.append(("prepare", facts.submission_version))
            return "prepared"
        async def consume(self, handle, facts):
            assert handle == "prepared"
            events.append(("final", facts.submission_version))
        def close(self, handle): assert handle == "prepared"

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
    assert [event[0] for event in events] == [
        "authorize", "task", "prepare", "persist", "art", "final"
    ]
    assert result.submission_version == 1


@pytest.mark.asyncio
async def test_denial_precedes_task_lock_and_all_mutation():
    class Authority:
        async def authorize(self, facts): raise SubmissionCreationUnavailable
        async def prepare(self, facts): raise AssertionError("unreachable")
        async def consume(self, handle, facts): raise AssertionError("unreachable")
        def close(self, handle): raise AssertionError("unreachable")

    service = TaskSubmissionCreationService(_Session(), authorization=Authority(), admissions=None)
    service._repository = SimpleNamespace(
        lock_submission_context=lambda value: pytest.fail("TASK state was revealed")
    )
    with pytest.raises(SubmissionCreationUnavailable):
        await service.create(_request())


@pytest.mark.parametrize("revocation", ["identity_link_revoked", "submitter_grant_missing"])
@pytest.mark.asyncio
async def test_fresh_authority_denial_precedes_art_and_mutation(revocation):
    request = _request()
    events = []

    class Authority:
        async def authorize(self, facts): pass
        async def prepare(self, facts):
            events.append(revocation)
            raise SubmissionCreationUnavailable("submission creation is unavailable")
        async def consume(self, handle, facts): raise AssertionError("unreachable")
        def close(self, handle): raise AssertionError("unreachable")

    class Admissions:
        async def consume(self, value):
            raise AssertionError("ART admission state was inspected")

    service = TaskSubmissionCreationService(_Session(), authorization=Authority(), admissions=Admissions())
    persisted = []

    class Repository:
        async def lock_submission_context(self, value): return _context(request)
        async def get_task(self, task_id): return _task()
        async def add_submission(self, submission): persisted.append(submission)

    service._repository = Repository()
    with pytest.raises(SubmissionCreationUnavailable):
        await service.create(request)
    assert events == [revocation]
    assert persisted == []


@pytest.mark.asyncio
async def test_invalid_admission_result_denies_before_lineage_and_final_authority():
    request = _request()
    events = []

    class Authority:
        async def authorize(self, facts): events.append("authorize")
        async def prepare(self, facts):
            events.append("prepare")
            return "prepared"
        async def consume(self, handle, facts): events.append("final")
        def close(self, handle): assert handle == "prepared"

    class Admissions:
        async def consume(self, value):
            events.append("art")
            return SimpleNamespace(binding_id=None, content_id=uuid4())

    service = TaskSubmissionCreationService(
        _Session(), authorization=Authority(), admissions=Admissions()
    )
    persisted = []

    class Repository:
        async def lock_submission_context(self, value): return _context(request)
        async def get_task(self, task_id): return _task()
        async def add_submission(self, submission): persisted.append(submission)

    service._repository = Repository()
    with pytest.raises(RuntimeError, match="exact binding facts"):
        await service.create(request)
    assert events == ["authorize", "prepare", "art"]
    assert len(persisted) == 1
    assert persisted[0].artifact_binding_id is None


def test_hidden_composition_uses_both_active_authority_adapters() -> None:
    session = SimpleNamespace()
    context = SimpleNamespace()
    command = compose_hidden_submission_creation_command(
        session, context, request_id=uuid4(), correlation_id=uuid4()
    )
    assert type(command) is TransactionalSubmissionCreationCommand
    assert type(command._authorization) is PreparedSubmissionCreationAuthorization
    assert type(command._admissions) is SubmissionAdmissionConsumptionService
    assert type(command._admissions._authorization) is PreparedSubmissionBindingAuthorization


@pytest.mark.asyncio
async def test_revision_increments_and_binds_the_exact_predecessor():
    predecessor = SubmissionPredecessorFacts(submission_id=uuid4(), version=1)
    initial = _request()
    request = SubmissionCreationRequest(
        admission_id=initial.admission_id, task_id=initial.task_id,
        assignment_id=initial.assignment_id, contributor_id=initial.contributor_id,
        predecessor_submission_id=predecessor.submission_id,
        summary=initial.summary, contributor_attestation=initial.contributor_attestation,
    )
    context = _context(request)
    context = TaskSubmissionContextFacts(
        task_id=context.task_id, assignment_id=context.assignment_id,
        contributor_id=context.contributor_id, status="needs_revision", kind="revision",
        predecessor=predecessor, locked_project_context=context.locked_project_context,
    )
    seen = {}

    class Authority:
        async def authorize(self, facts): pass
        async def prepare(self, facts):
            seen["prepared"] = facts
            return "prepared"
        async def consume(self, handle, facts):
            assert handle == "prepared"
            seen.update(final=facts)
        def close(self, handle): assert handle == "prepared"

    class Admissions:
        async def consume(self, value):
            seen["art"] = value
            return SubmissionArtifactAdmissionResult(binding_id=uuid4(), content_id=uuid4())

    service = TaskSubmissionCreationService(_Session(), authorization=Authority(), admissions=Admissions())

    class Repository:
        async def lock_submission_context(self, value): return context
        async def get_task(self, task_id): return _task()
        async def add_submission(self, submission): seen.update(submission=submission)

    service._repository = Repository()
    result = await service.create(request)
    assert result.submission_version == 2
    assert seen["submission"].supersedes_submission_id == str(predecessor.submission_id)
    assert seen["art"].submission_version == 2
    assert seen["final"].predecessor_submission_id == predecessor.submission_id
