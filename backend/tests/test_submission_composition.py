"""Accepted Submission composition and retained authorization fact contracts."""



from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID
from app.core.identifiers import new_record_id

from submission_context_fixtures import submission_context_facts

import pytest

from app.modules.tasks.api import (
    SubmissionCreationRequest,
    SubmissionCreationUnavailable,
    TaskLockedProjectContextReferences,
)
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.submission_consumption import parse_consumption_binding


class _Session:
    def in_transaction(self):
        return True

    def in_nested_transaction(self):
        return False

    async def connection(self):
        return self

    async def execute(self, statement):
        return None

    async def scalar(self, statement):
        return None

    async def flush(self):
        return None


def _request():
    return SubmissionCreationRequest(
        admission_id=new_record_id(), task_id=new_record_id(), assignment_id=new_record_id(),
        contributor_id=new_record_id(), predecessor_submission_id=None,
        summary="summary", contributor_attestation="attestation",
    )


def _context(request):
    return submission_context_facts(submitter_contribution_policy_version_id=UUID(int=100),
        task_id=request.task_id, assignment_id=request.assignment_id,
        contributor_id=request.contributor_id, status="in_progress", kind="initial",
        predecessor=None,
        locked_project_context=TaskLockedProjectContextReferences(locked_contribution_policy_version_id=UUID(int=100),
            project_id=new_record_id(), guide_version="1", source_snapshot_id=new_record_id(),
            source_snapshot_hash="sha256:" + "1" * 64, effective_policy_id=new_record_id(),
            effective_policy_hash="sha256:" + "2" * 64,
            pre_submit_policy_id=new_record_id(),
            pre_submit_policy_bundle_hash="sha256:" + "3" * 64,
        ),
    )


def _task():
    values = {
        "id": str(new_record_id()), "project_id": str(new_record_id()),
        "locked_guide_version": "1", "locked_post_submit_checker_policy_id": str(new_record_id()),
        "locked_post_submit_checker_policy_version": "1",
        "locked_post_submit_checker_policy_hash": "sha256:" + "4" * 64,
        "locked_post_submit_checker_policy_body": {}, "locked_review_policy_id": str(new_record_id()),
        "locked_review_policy_generation": 1,
        "locked_review_policy_hash": "sha256:" + "5" * 64,
        "locked_revision_policy_id": str(new_record_id()), "locked_revision_policy_generation": 1,
        "locked_revision_policy_hash": "sha256:" + "6" * 64,
        "locked_guide_source_snapshot_id": str(new_record_id()),
        "locked_guide_source_snapshot_hash": "sha256:" + "7" * 64,
        "locked_effective_project_submission_artifact_policy_id": str(new_record_id()),
        "locked_effective_project_submission_artifact_policy_hash": "sha256:" + "8" * 64,
        "locked_pre_submit_checker_policy_id": str(new_record_id()),
        "locked_pre_submit_checker_bundle_hash": "sha256:" + "9" * 64,
    }
    return SimpleNamespace(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["authority", "policy", "admission"])
async def test_accepted_creation_denial_closes_authority_and_stops_dispatch(monkeypatch, failure):
    from unittest.mock import Mock
    from app.modules.artifacts.api.submission_finalization import SubmissionFinalizationAuthorityFacts

    request = _request()
    facts = SubmissionFinalizationAuthorityFacts(
        operation_id=new_record_id(), project_id=new_record_id(),
        task_id=request.task_id, assignment_id=request.assignment_id,
        contributor_id=request.contributor_id, acceptance_decision_id=new_record_id(),
        accepted_context_sha256="a" * 64, acceptance_receipt_sha256="b" * 64,
        source_sha256="c" * 64, continuation_lease_id=new_record_id(),
        continuation_generation=1, phase="claim",
    )
    monkeypatch.setattr(
        "app.modules.tasks.accepted_submission.accepted_submission_context",
        AsyncMock(return_value=_context(request)),
    )
    authority = SimpleNamespace(
        prepare=AsyncMock(return_value=object()), consume=AsyncMock(), close=Mock(),
    )
    admissions = SimpleNamespace(consume=AsyncMock(return_value=SimpleNamespace(binding_id=None)))
    contexts = SimpleNamespace(_load_locked_task_context=AsyncMock(return_value=SimpleNamespace(facts=object())))
    if failure == "authority":
        authority.prepare.side_effect = SubmissionCreationUnavailable("authority denied")
    elif failure == "policy":
        contexts._load_locked_task_context.side_effect = SubmissionCreationUnavailable("policy denied")
    service = TaskSubmissionCreationService(
        _Session(), admissions=admissions, contexts=contexts,
        evaluations=SimpleNamespace(reserve_current_evaluation=AsyncMock()),
        events=SimpleNamespace(append=AsyncMock()),
    )
    service._repository = SimpleNamespace(
        get_task=AsyncMock(return_value=_task()), add_submission=AsyncMock(),
        get_latest_submission_for_task=AsyncMock(return_value=None),
    )
    with pytest.raises(SubmissionCreationUnavailable):
        await service.create_accepted(request, authority_facts=facts,
            finalization_authority=authority, snapshot_sha256="d" * 64,
            eligible_status="in_progress", remediation_id=None)
    authority.consume.assert_not_awaited()
    service._evaluations.reserve_current_evaluation.assert_not_awaited()
    service._events.append.assert_not_awaited()
    if failure == "authority":
        authority.close.assert_not_called()  # No prepared handle was issued.
        contexts._load_locked_task_context.assert_not_awaited()
    else:
        authority.close.assert_called_once_with()
    if failure == "admission":
        service._repository.add_submission.assert_awaited_once()
        assert service._repository.add_submission.await_args.args[0].artifact_binding_id is None
    else:
        service._repository.add_submission.assert_not_awaited()
        admissions.consume.assert_not_awaited()


def test_task_and_assignment_policy_facts_reject_substitution():
    from dataclasses import replace

    facts = _context(_request())
    assert facts.submitter_contribution_policy_version_id == facts.locked_project_context.locked_contribution_policy_version_id
    for invalid in (None, str(facts.submitter_contribution_policy_version_id), new_record_id()):
        with pytest.raises(ValueError, match="assignment contribution policy differs from task"):
            replace(facts, submitter_contribution_policy_version_id=invalid)
    for invalid in (None, str(facts.locked_project_context.locked_contribution_policy_version_id)):
        with pytest.raises(ValueError, match="task contribution policy identity is invalid"):
            replace(facts.locked_project_context, locked_contribution_policy_version_id=invalid)


def _consumption_values(*, binding=False, remediation=False):
    values = {name: str(new_record_id()) for name in (
        "actor_profile_id", "identity_link_id", "task_id", "assignment_id",
        "admission_id", "submission_id", "source_snapshot_id", "effective_policy_id",
        "pre_submit_policy_id",
    )}
    values.update({name: "sha256:" + "1" * 64 for name in (
        "source_snapshot_sha256", "effective_policy_sha256", "pre_submit_policy_sha256",
    )})
    values.update(
        guide_version="guide-a",
        predecessor_submission_id=str(new_record_id()) if remediation else None,
        predecessor_submission_version=1 if remediation else None,
        submission_version=2 if remediation else 1,
        checker_remediation_manifest_id=str(new_record_id()) if remediation else None,
    )
    if binding:
        values.update({name: str(new_record_id()) for name in (
            "selected_pre_submit_run_id", "project_id", "guide_id", "semantic_manifest_id", "content_id",
        )})
        values.update(
            evidence_set_id=None,
            resource_type="submission_binding", resource_id=values["admission_id"],
            locked_policy_context_hash="sha256:" + "2" * 64,
            semantic_manifest_sha256="sha256:" + "3" * 64,
            sha256="sha256:" + "4" * 64, byte_count=42,
            logical_role="submission_bundle_original",
        )
    else:
        values.update(
            resource_type="submission_creation", resource_id=values["submission_id"],
            scope_project_id=str(new_record_id()),
            contribution_policy_version_id=str(new_record_id()),
            task_status="needs_revision" if remediation else "in_progress",
            submission_kind="checker_remediation" if remediation else "initial",
        )
    return values


@pytest.mark.parametrize("remediation,changes", [
    (False, {"predecessor_submission_id": str(UUID(int=123)), "predecessor_submission_version": 1}),
    (False, {"task_status": "needs_revision"}),
    (False, {"checker_remediation_manifest_id": str(UUID(int=456))}),
    (False, {"submission_kind": "checker_remediation"}),
    (True, {"predecessor_submission_id": None, "predecessor_submission_version": None}),
    (True, {"predecessor_submission_id": None}),
    (True, {"predecessor_submission_version": None}),
    (True, {"checker_remediation_manifest_id": None}),
    (True, {"task_status": "in_progress"}),
    (True, {"submission_kind": "initial"}),
    (True, {"submission_version": 1}),
    (True, {"submission_version": 3}),
    (True, {"predecessor_submission_version": 2}),
])
def test_creation_authority_parser_rejects_inconsistent_lifecycle(remediation, changes):
    values = _consumption_values(remediation=remediation)
    valid = parse_consumption_binding(ActionId.SUBMISSION_CREATE, values, ValueError)
    assert valid.submission_version == (2 if remediation else 1)
    with pytest.raises(ValueError, match="invalid prepared authorization handle"):
        parse_consumption_binding(ActionId.SUBMISSION_CREATE, values | changes, ValueError)


@pytest.mark.parametrize("remediation,version", [(True, 1), (True, 3)])
def test_binding_authority_parser_requires_exact_successor_version(remediation, version):
    values = _consumption_values(binding=True, remediation=remediation)
    action = ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE
    valid = parse_consumption_binding(action, values, ValueError)
    assert valid.submission_version == (2 if remediation else 1)
    with pytest.raises(ValueError, match="invalid prepared authorization handle"):
        parse_consumption_binding(action, values | {"submission_version": version}, ValueError)


@pytest.mark.parametrize("action,binding", [
    (ActionId.SUBMISSION_CREATE, False),
    (ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE, True),
])
def test_initial_consumption_authority_accepts_later_global_version(action, binding):
    """Initial means no predecessor in this assignment; TASK owns global sequencing."""
    values = _consumption_values(binding=binding)
    resource = parse_consumption_binding(
        action, values | {"submission_version": 5}, ValueError,
    )
    assert resource.submission_version == 5
    assert resource.predecessor_submission_id is None
