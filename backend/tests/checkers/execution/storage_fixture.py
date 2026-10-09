"""Closed history with canonical stored ART lineage and real fixed-service phase authority."""

from app.modules.checkers.api.post_submit import make_post_submit_request
from uuid import UUID

from app.modules.artifacts.models import SubmissionBundleAdmission
from app.modules.checkers.api.execution import ExecuteFacts, FinalizeFacts, VerifiedMaterialFacts
from app.modules.checkers.api.post_submit import PostSubmitMemberResult
from app.adapters.checkers import evaluation_coordinator
from app.modules.checkers.post_submit_contracts import (
    make_post_submit_result,
)
from app.modules.tasks.models import Submission
from tests.checkers.post_submit.test_result_contract import result as value_result
from tests.checkers.execution.support import live_executor, provision_checker_service
from types import SimpleNamespace


async def storage_request(session, submission_id, *, generation=1):
    from app.modules.tasks.models import SubmissionDispatch
    from app.core.identifiers import new_record_id
    receipt = await session.get(SubmissionDispatch, str(submission_id))
    assert receipt is not None
    stored = await evaluation_coordinator(session).read_reserved_evaluation(
        project_id=UUID(receipt.project_id), task_id=UUID(receipt.task_id),
        submission_id=UUID(receipt.submission_id), request_id=UUID(receipt.evaluation_request_id),
    )
    if generation == 1:
        return stored.request
    body = stored.request.model_dump(exclude={"request_sha256"})
    body.update(evaluation_generation=generation, evaluation_request_id=new_record_id())
    return make_post_submit_request(**body)


async def seed_storage_run(factory, submission_id, *, failures=(), state="completed", generation=1):
    async with factory() as session, session.begin():
        request = await storage_request(session, submission_id, generation=generation)
        receipt = await evaluation_coordinator(session).reserve_current_evaluation(request)
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
    input_receipt = await authorize_stored_material(
        factory, ExecuteFacts(request=request, lease=lease), material
    )
    await executor.finalize(
        FinalizeFacts(
            request=request,
            lease=lease,
            result=result,
            material=material,
            input_materialization_evidence_id=input_receipt,
            output_binding_ids=(),
        )
    )
    return str(receipt.attempt_id)


async def authorize_stored_material(factory, execution, material):
    """Issue real input AUTH over canonical rows for storage-only terminal fixtures.

    This authorizes a read; it does not claim provider I/O was exercised. Real
    materialization tests use the provider and compare this same retained receipt.
    """
    from sqlalchemy import select
    from app.adapters.auth import post_submit_materialization_authority
    from app.modules.artifacts.models import (
        ArtifactReplica,
        ArtifactStorageNamespace,
        ArtifactVerificationReceipt,
    )
    from app.modules.checkers.api.materialization import MaterializationFacts

    async with factory() as session, session.begin():
        async with post_submit_materialization_authority(session).prepare_materialization(
            execution
        ) as prepared:
            a, v, namespace = (
                await session.execute(
                    select(
                        SubmissionBundleAdmission,
                        ArtifactVerificationReceipt,
                        ArtifactStorageNamespace,
                    )
                    .join(
                        ArtifactVerificationReceipt,
                        ArtifactVerificationReceipt.id
                        == SubmissionBundleAdmission.verification_receipt_id,
                    )
                    .join(
                        ArtifactReplica,
                        ArtifactReplica.id == SubmissionBundleAdmission.verified_replica_id,
                    )
                    .join(
                        ArtifactStorageNamespace,
                        ArtifactStorageNamespace.id == ArtifactReplica.storage_namespace_id,
                    )
                    .where(SubmissionBundleAdmission.id == str(material.admission_id))
                )
            ).one()
            return await prepared.consume(
                MaterializationFacts(
                    execution=execution,
                    material=material,
                    evidence_id=UUID(a.pre_submit_evidence_set_id),
                    verification_receipt_id=UUID(v.id),
                    verification_job_id=UUID(v.verification_job_id),
                    verification_generation=v.execution_generation,
                    namespace_fingerprint=namespace.namespace_fingerprint,
                    semantic_manifest_id=UUID(a.semantic_manifest_id),
                )
            )
