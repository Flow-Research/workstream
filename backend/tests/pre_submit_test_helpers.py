"""Shared dependency-safe construction for focused pre-submit tests."""

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from uuid import UUID, uuid4

from app.adapters.checkers import PreSubmitCheckerExecutionAdapter
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationService,
    PreparedBundlePreSubmitEvidenceService,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.tasks.repository import TaskRepository
from app.modules.artifacts.pre_submit_attempts import PreSubmitAttemptClaim
from app.modules.artifacts.pre_submit_evidence import PreSubmitEvidencePersistenceResult


async def materialize_member_fixture(service, request):
    """Isolate existing member/scratch tests from SQL; this is not attempt-custody proof."""
    claim = object.__new__(PreSubmitAttemptClaim)
    claim.attempt_id, claim._nonce = uuid4(), uuid4()
    claim.request_digest = "sha256:" + "1" * 64
    claim._request = replace(request, prepared_authorization=None)
    claim._started, claim._execution = False, None
    claim._session = service._session
    service._session.in_transaction = lambda: True
    service._session.in_nested_transaction = lambda: False
    service._session.scalar = AsyncMock(return_value=SimpleNamespace(
        status="reserved", evidence_set_id=None, claim_nonce=str(claim._nonce),
        request_digest=claim.request_digest,
        prepared_generation_id=str(request.prepared_artifact.generation_id),
    ))
    return await service.materialize_prepared_bundle(request, claim=claim)


async def execute_evidence_workflow(workflow, request, *, preparation_request):
    """Exercise real reservation/commit/execution/evidence owners in PostgreSQL fixtures."""
    async with workflow._session.begin():
        selected = await workflow.reserve(request, preparation_request=preparation_request)
    if isinstance(selected, PreSubmitEvidencePersistenceResult):
        return selected
    return await workflow.execute_reserved(request, selected, preparation_request=preparation_request)


def checker_execution(inspector, catalogue) -> PreSubmitCheckerExecutionAdapter:
    """Build the owner adapter used by ART materialization tests."""
    return PreSubmitCheckerExecutionAdapter(
        archive_inspector=inspector,
        catalogue=catalogue,
    )


def submission_preparation_request(
    request,
    *,
    actor_profile_id: UUID,
    identity_link_id: UUID,
) -> SubmissionBundlePreparationRequest:
    """Project one private materialization fixture into the public ART request."""
    return SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(
            actor_profile_id=actor_profile_id,
            identity_link_id=identity_link_id,
            actor_kind=ActorKind.HUMAN,
        ),
        request_id=uuid4(),
        correlation_id=uuid4(),
        task_id=request.task_id,
        assignment_id=request.assignment_id,
        predecessor_submission_id=None,
        idempotency_key=uuid4(),
        summary=request.packet.summary,
        contributor_attestation=request.packet.contributor_attestation,
        media_type="application/zip",
        byte_source=_empty_bytes(),
    )


async def _empty_bytes():
    if False:  # pragma: no cover - preserve the async-iterable request shape
        yield b""


def evidence_workflow(
    *, session, preparation, inspector, catalogue, materialization_authorization,
    preparation_authorization,
) -> PreparedBundlePreSubmitEvidenceService:
    """Compose the exact public-port evidence workflow for database proof."""
    return PreparedBundlePreSubmitEvidenceService(
        session=session,
        materialization=PreparedBundleMaterializationService(
            session=session,
            authorization=materialization_authorization,
            preparation=preparation,
            checker_execution=checker_execution(inspector, catalogue),
            storage_scheme="s3",
        ),
        preparation_authorization=preparation_authorization,
        task_contexts=TaskRepository(session),
        project_contexts=ProjectLockedPolicyRepository(session),
    )


async def approved_pre_submit_fixture(factory, namespace, *, guide_version):
    """Build supported PROJECTS custody before the ART evidence transaction."""
    from app.interfaces.project_agents import SubmissionArtifactPolicyProposal
    from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue
    from app.modules.checkers.api import EffectivePreSubmissionPlanLineage
    from app.modules.projects.models import ProjectGuide, PostSubmitCheckerPolicy
    from tests.projects.unified_policy_fixtures import create_standalone_unified_policy

    values, effective, pre = await create_standalone_unified_policy(
        factory, namespace, guide_version=guide_version,
        artifact_proposal=SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1_000_000, maximum_package_size_bytes=5_000_000,
            required_artifacts=("task.toml",), required_evidence=("results",),
            attestation_terms=("rights_confirmed",),
        ),
    )
    lineage = EffectivePreSubmissionPlanLineage(
        project_id=values["project"], guide_id=values["guide"], guide_version=guide_version,
        source_snapshot_id=values["snapshot"], source_snapshot_hash=effective["source_snapshot_hash"],
        effective_policy_id=UUID(effective["id"]), effective_policy_hash=effective["effective_policy_hash"],
        pre_submit_policy_id=UUID(pre.id), pre_submit_policy_bundle_hash=pre.compiled_bundle_hash,
    )
    plan = build_pre_submission_checker_catalogue().compile_effective_plan(
        lineage=lineage, effective_policy=effective["effective_policy"], compiled_bundle=pre.compiled_bundle,
    )
    async with factory() as session:
        guide = await session.get(ProjectGuide, str(values["guide"]))
        post = await session.scalar(select(PostSubmitCheckerPolicy).where(
            PostSubmitCheckerPolicy.effective_policy_id == effective["id"]))
        assert post is not None
        return plan, {
            "post_policy": post.id,
            "post_policy_hash": post.policy_hash,
            "post_policy_body": json.dumps(post.policy_body),
            "submission_policy": effective["submission_artifact_policy_id"],
            "review_policy": guide.selected_review_policy_id,
            "review_policy_hash": guide.selected_review_policy_hash,
            "revision_policy": guide.selected_revision_policy_id,
            "revision_policy_hash": guide.selected_revision_policy_hash,
            "guide_version": guide_version,
            "attestation_terms": effective["effective_policy"]["attestation_terms"],
            "evidence_path": "evidence/" + effective["effective_policy"]["required_evidence"][0]["key"],
        }


async def assert_pre_submit_evidence_immutable(connection):
    """Reject edits, deletes and late appends to the existing canonical evidence."""
    immutable_statements = (
        "update pre_submit_evidence_sets set terminal_status='blocked'",
        "update pre_submit_evidence_results set status='failed'",
        "delete from pre_submit_evidence_results",
        "truncate pre_submit_evidence_results",
        "insert into pre_submit_evidence_results "
        "select '00000000-0000-0000-0000-000000000001',"
        "evidence_set_id,result_order+1000,"
        "schema_version,dispatch_authority,definition_id || '.forged',"
        "definition_version,public_name,source,phase,classification,severity,status,"
        "failure_code,message_code,effective_plan_sha256,rule_instance_id,"
        "locked_policy_sha256,now(),checker_order,metadata_json "
        "from pre_submit_evidence_results limit 1",
    )
    for statement in immutable_statements:
        with pytest.raises(DBAPIError):
            async with connection.begin_nested():
                await connection.execute(text(statement))
    with pytest.raises(DBAPIError, match="pre_submit_evidence_sets rows are immutable"):
        async with connection.begin_nested():
            await connection.execute(
                text(
                    "insert into pre_submit_evidence_sets select "
                    "(jsonb_populate_record(null::pre_submit_evidence_sets, "
                    "to_jsonb(existing_row) || jsonb_build_object("
                    "'id','00000000-0000-0000-0000-000000000003',"
                    "'operation_identity','sha256:' || repeat('e',64),"
                    "'attempt_id',null,'attempt_request_digest',null,"
                    "'created_at',transaction_timestamp()))).* "
                    "from pre_submit_evidence_sets existing_row limit 1"
                )
            )
            await connection.execute(
                text(
                    "delete from pre_submit_evidence_sets "
                    "where id='00000000-0000-0000-0000-000000000003'"
                )
            )
    with pytest.raises(DBAPIError, match="pre_submit_evidence_sets rows are immutable"):
        async with connection.begin_nested():
            await connection.execute(text("truncate pre_submit_evidence_sets cascade"))
    with pytest.raises(DBAPIError, match="creation timestamp is invalid"):
        async with connection.begin_nested():
            await connection.execute(
                text(
                    "insert into pre_submit_evidence_sets select "
                    "(jsonb_populate_record(null::pre_submit_evidence_sets, "
                    "to_jsonb(existing_row) || jsonb_build_object("
                    "'id','00000000-0000-0000-0000-000000000002',"
                    "'operation_identity','sha256:' || repeat('f',64),"
                    "'created_at',existing_row.created_at - interval '1 day'))).* "
                    "from pre_submit_evidence_sets existing_row limit 1"
                )
            )


async def assert_admission_replay_state(session, evidence_id, attempt_id, admission_id, status):
    """Both recovery reads expose an admission ID only while its real SQL row is ready."""
    from app.modules.artifacts.submission_admission import (
        PreparedSubmissionBundlePreparationCommand, current_submission_bundle_admission_id,
    )
    command = PreparedSubmissionBundlePreparationCommand(
        session=session, authority=SimpleNamespace(), task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(), runtime_factory=None,
    )
    result = await command._existing_durable_result(evidence_id)
    assert result.submission_bundle_preparation_status == status
    assert result.admission_id == (UUID(admission_id) if status == "ready" else None)
    async with session.begin():
        current = await current_submission_bundle_admission_id(session, put_attempt_id=attempt_id)
        assert current == (UUID(admission_id) if status == "ready" else None)
