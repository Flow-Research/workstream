"""Closed history with canonical stored ART lineage and real fixed-service phase authority."""

import json
from uuid import UUID

from app.modules.artifacts.models import ArtifactContent, SubmissionBundleAdmission
from app.modules.checkers.api.execution import FinalizeFacts, VerifiedMaterialFacts
from app.modules.checkers.api.post_submit import ExpectedPostSubmitContext, PostSubmitMemberResult
from app.modules.checkers.api.post_submit_catalogue import CompiledPostSubmitPolicy
from app.modules.checkers.execution_coordination import EvaluationCoordinator
from app.modules.checkers.post_submit_contracts import (
    make_post_submit_request,
    make_post_submit_result,
)
from app.modules.tasks.models import Submission, WorkstreamTask
from tests.checkers.post_submit.support import request as value_request
from tests.checkers.post_submit.test_result_contract import result as value_result
from tests.checkers.execution.support import live_executor, provision_checker_service
from types import SimpleNamespace


async def storage_request(session, submission_id, *, generation=1):
    submission = await session.get(Submission, str(submission_id))
    task = await session.get(WorkstreamTask, submission.task_id)
    source = value_request(project_id=UUID(task.project_id))
    content = await session.get(ArtifactContent, submission.artifact_content_id)
    context = ExpectedPostSubmitContext.model_validate_json(
        json.dumps(
            dict(
                guide_version=submission.locked_guide_version,
                source_id=submission.locked_guide_source_snapshot_id,
                source_hash=submission.locked_guide_source_snapshot_hash,
                effective_policy_id=submission.locked_effective_project_submission_artifact_policy_id,
                effective_policy_hash=submission.locked_effective_project_submission_artifact_policy_hash,
                pre_policy_id=submission.locked_pre_submit_checker_policy_id,
                pre_policy_hash=submission.locked_pre_submit_checker_bundle_hash,
                post_policy_id=submission.locked_post_submit_checker_policy_id,
                post_policy_version=submission.locked_post_submit_checker_policy_version,
                post_policy_hash=submission.locked_post_submit_checker_policy_hash,
                review_policy_id=submission.locked_review_policy_id,
                review_generation=submission.locked_review_policy_generation,
                review_hash=submission.locked_review_policy_hash,
                revision_policy_id=submission.locked_revision_policy_id,
                revision_generation=submission.locked_revision_policy_generation,
                revision_hash=submission.locked_revision_policy_hash,
            )
        )
    )
    body = source.model_dump(exclude={"request_sha256"})
    body["content_sha256"], body["byte_count"] = content.sha256, content.byte_count
    body["structural_input"]["package_hash"] = content.sha256
    body["structural_input"]["summary"] = "PRIVATE_CHECKER_PACKET_SENTINEL"
    body["structural_input"]["observed_context"] = context.model_dump()
    body.update(
        evaluation_generation=generation,
        task_id=UUID(task.id),
        assignment_id=UUID(submission.task_assignment_id),
        submission_id=UUID(submission.id),
        submission_version=submission.version,
        content_id=UUID(submission.artifact_content_id),
        binding_id=UUID(submission.artifact_binding_id),
        expected_context=context,
        policy=CompiledPostSubmitPolicy.model_validate_json(
            json.dumps(submission.locked_post_submit_checker_policy_body)
        ),
    )
    return make_post_submit_request(**body)


async def seed_storage_run(factory, submission_id, *, failures=(), state="completed", generation=1):
    async with factory() as session, session.begin():
        request = await storage_request(session, submission_id, generation=generation)
        receipt = await EvaluationCoordinator(session).reserve_current_evaluation(request)
    if state == "queued":
        return str(receipt.attempt_id)
    await provision_checker_service(factory)
    executor = live_executor(SimpleNamespace(factory=factory, service=None))
    lease, replay = await executor._claim(request)
    assert replay is None
    if state == "running":
        return str(receipt.attempt_id)
    assert state in {"completed", "infrastructure_failed"}
    members = []
    for member in value_result(request).member_results:
        if member.checker_id in failures:
            definition = request.catalogue.definition(member.checker_id, member.definition_version)
            member = PostSubmitMemberResult(
                checker_id=member.checker_id,
                definition_version=member.definition_version,
                implementation_version=member.implementation_version,
                status=definition.failure_status,
                severity=definition.failure_severity,
                code=definition.failure_code,
                failure_category=definition.failure_category,
            )
        members.append(member)
    assert set(failures).issubset({member.checker_id for member in members})
    result = make_post_submit_result(
        request_id=request.evaluation_request_id,
        request_digest=request.request_sha256,
        attempt_id=receipt.attempt_id,
        result_id=receipt.result_id,
        evaluation_generation=generation,
        outcome=state,
        member_results=tuple(members) if state == "completed" else (),
        infrastructure_failure_code=None if state == "completed" else "deadline_exceeded",
    )
    async with factory() as session:
        submission = await session.get(Submission, str(submission_id))
        admission = await session.get(SubmissionBundleAdmission, submission.submission_bundle_admission_id)
        admission_id = UUID(admission.id)
    material = VerifiedMaterialFacts(
        submission_id=request.submission_id,
        submission_version=request.submission_version,
        admission_id=admission_id,
        binding_id=request.binding_id,
        content_id=request.content_id,
        replica_id=UUID(admission.verified_replica_id),
        content_sha256=request.content_sha256,
        byte_count=request.byte_count,
        semantic_manifest_sha256=admission.semantic_manifest_sha256,
    )
    await executor.finalize(
        FinalizeFacts(
            request=request, lease=lease, result=result, material=material, output_binding_ids=()
        )
    )
    return str(receipt.attempt_id)
