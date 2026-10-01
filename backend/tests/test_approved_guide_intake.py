"""Final intake revalidation uses exact activated owner facts, not current selectors."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.modules.artifacts.models import ArtifactPutAttempt, PreSubmitEvidenceSet, SubmissionBundleDurableIntent
from app.modules.artifacts.schemas import SubmissionBundleArtifactAdmissionRequest
from app.modules.artifacts.service import ArtifactAdmissionRelationshipError, ArtifactAdmissionService
from app.modules.artifacts.submission_custody import SubmissionBundlePreparedCustody
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.projects.models import ProjectGuide
from app.modules.projects.guide_activation.custody import load_guide_activation
from app.modules.tasks.repository import TaskRepository
from tests.pre_submit_test_helpers import execute_evidence_workflow
from tests.artifact_store_helpers import artifact_admission_limit_settings
from tests.test_pre_submit_attempt_recovery import _harness


async def _checked(harness, session):
    calls = []
    workflow = harness.workflow(session, calls)
    result = await execute_evidence_workflow(
        workflow, harness.request, preparation_request=harness.preparation_request,
    )
    assert calls == [1] and result.pass_capability is not None
    custody = SubmissionBundlePreparedCustody._from_live_preparation(
        prepared=harness.request.prepared_artifact, capability=result.pass_capability,
    )
    return SubmissionBundleArtifactAdmissionRequest(
        pre_submit_evidence_set_id=result.evidence.evidence_set_id, custody=custody,
        replay_durable_intent_id=None,
    )


def _admission(session, tmp_path):
    namespace = ArtifactStorageNamespaceSpec(
        backend="local", adapter="local", provider_profile="test",
        namespace_descriptor={"test": "submission-bundle"},
        namespace_fingerprint=canonical_json_hash({"test": "submission-bundle"}),
    )
    return ArtifactAdmissionService(session, Settings(_env_file=None, environment="test", artifact_store_backend="local",
        artifact_local_root=tmp_path / "durable", artifact_scratch_root=tmp_path / "scratch",
        artifact_scratch_minimum_free_bytes=0,
        **artifact_admission_limit_settings(1024 * 1024)), namespace)


async def _admit(session, request, authority, tmp_path, *, task_contexts=None):
    # This is the real durable-admission writer, including final AUTH and custody.
    return await _admission(session, tmp_path).admit(
        request, submission_prepared_authorization=authority,
        submission_task_contexts=task_contexts or TaskRepository(session),
        submission_project_contexts=ProjectLockedPolicyRepository(session),
        existing_transaction=True,
    )


async def _assert_intent(factory, request, admission, lineage):
    # Read committed facts independently of the writer's session.
    async with factory() as session:
        intent, evidence, attempt = (await session.execute(
            select(SubmissionBundleDurableIntent, PreSubmitEvidenceSet, ArtifactPutAttempt)
            .join(PreSubmitEvidenceSet, PreSubmitEvidenceSet.id == SubmissionBundleDurableIntent.pre_submit_evidence_set_id)
            .join(ArtifactPutAttempt, ArtifactPutAttempt.id == SubmissionBundleDurableIntent.put_attempt_id)
        )).one()
        assert intent.put_attempt_id == str(admission.attempt_id) == attempt.id
        assert intent.pre_submit_evidence_set_id == str(request.pre_submit_evidence_set_id) == evidence.id
        assert attempt.task_id == evidence.task_id
        assert attempt.project_id == evidence.project_id == str(lineage.project_id)
        assert evidence.guide_id == str(lineage.guide_id)
        assert evidence.source_snapshot_id == str(lineage.source_snapshot_id)
        assert evidence.effective_policy_id == str(lineage.effective_policy_id)
        assert evidence.pre_submit_policy_id == str(lineage.pre_submit_policy_id)
        assert evidence.locked_checker_policy_sha256 == lineage.pre_submit_policy_bundle_hash


async def test_final_intake_keeps_original_guide_after_successor(tmp_path, isolated_database_env):
    from tests.projects.guide_activation.test_successor import successor_command
    from tests.projects.guide_activation.pg_support import publish_policy
    from tests.authorization.guide_activation.pg_support import activate

    harness = await _harness(tmp_path, isolated_database_env)
    try:
        async with harness.factory() as session:
            request = await _checked(harness, session)
            async with session.begin():
                lineage = harness.request.effective_plan.lineage
                guide = await session.get(ProjectGuide, str(lineage.guide_id))
                first = await load_guide_activation(session, guide)
            target = first.command.target.proposal
            from app.modules.actors.models import ActorIdentityLink
            from app.modules.authorization.models import AdminRoleGrant
            from app.modules.authorization.api import ActorIdentityFacts, ActorKind
            from uuid import UUID
            async with harness.factory() as manager_session:
                grant_row, link = (await manager_session.execute(
                    select(AdminRoleGrant, ActorIdentityLink)
                    .join(ActorIdentityLink, ActorIdentityLink.actor_profile_id == AdminRoleGrant.target_actor_profile_id)
                    .where(AdminRoleGrant.scope_project_id == str(target.project_id),
                           AdminRoleGrant.role == "project_manager", AdminRoleGrant.status == "active",
                           AdminRoleGrant.target_actor_profile_id != str(harness.actor_id),
                           ActorIdentityLink.status == "active")
                    .order_by(AdminRoleGrant.id, ActorIdentityLink.id).limit(1)
                )).one()
                actor = ActorIdentityFacts(UUID(str(grant_row.target_actor_profile_id)), UUID(str(link.id)), ActorKind.HUMAN)
                grant = UUID(str(grant_row.id))
            _, policy = await publish_policy(harness.factory, target.project_id)
            successor = await successor_command(
                harness.factory, first.command, actor, grant, policy,
            )
            successor = successor.model_copy(update={
                "expected_previous_active_guide_id": first.command.target.proposal.guide_id,
                "expected_previous_active_guide_generation": first.activation_generation,
            })
            next_receipt = await activate(harness.factory, actor, successor)
            assert next_receipt.command.contribution_policy_version_id != first.command.contribution_policy_version_id
            async with session.begin():
                authority = harness.contributor_authority(session)
                await authority.revalidate(request=harness.preparation_request, project_id=lineage.project_id)
                admission = await _admit(session, request, authority, tmp_path)
                guide = await session.get(ProjectGuide, str(lineage.guide_id), populate_existing=True)
                assert guide.status == "superseded"
            await _assert_intent(harness.factory, request, admission, lineage)
    finally:
        await harness.close()


@pytest.mark.parametrize("drift", ["archived_project", "foreign_contribution_version"])
async def test_final_intake_rejects_invalid_owner_context(tmp_path, isolated_database_env, drift):
    harness = await _harness(tmp_path, isolated_database_env)
    try:
        async with harness.factory() as session:
            request = await _checked(harness, session)
            lineage = harness.request.effective_plan.lineage
            authority = harness.contributor_authority(session)
            async with session.begin():
                await authority.revalidate(request=harness.preparation_request, project_id=lineage.project_id)
                if drift == "archived_project":
                    await session.execute(text("UPDATE projects SET status='archived' WHERE id=:id"),
                                          {"id": str(lineage.project_id)})
                    await session.flush()
                    with pytest.raises(ArtifactAdmissionRelationshipError, match="pre_submit_locked_context_changed"):
                        await _admit(session, request, authority, tmp_path)
                else:
                    # Substitute a same-shaped owner result; database guards are not disabled.
                    from app.core.identifiers import new_record_id
                    real = TaskRepository(session)
                    from app.modules.tasks.api import TaskSubmissionContextRequest
                    facts = await real.lock_submission_context(TaskSubmissionContextRequest(
                        task_id=harness.request.task_id, assignment_id=harness.request.assignment_id,
                        contributor_id=harness.actor_id, predecessor_submission_id=None,
                    ))
                    foreign = new_record_id()
                    substituted = replace(facts,
                        submitter_contribution_policy_version_id=foreign,
                        locked_project_context=replace(facts.locked_project_context,
                            locked_contribution_policy_version_id=foreign))
                    async def wrong_context(_):
                        return substituted
                    with pytest.raises(ArtifactAdmissionRelationshipError, match="locked context changed"):
                        await _admit(session, request, authority, tmp_path,
                            task_contexts=SimpleNamespace(lock_submission_context=wrong_context))
                assert await session.scalar(select(func.count()).select_from(SubmissionBundleDurableIntent)) == 0
                await session.rollback()
            async with session.begin():
                # The same passing custody remains valid after the rejected transaction rolls back.
                await authority.revalidate(request=harness.preparation_request, project_id=lineage.project_id)
                control = await _admit(session, request, authority, tmp_path)
            await _assert_intent(harness.factory, request, control, lineage)
    finally:
        await harness.close()


async def test_command_holds_authorized_context_before_final_handoff(tmp_path, isolated_database_env):
    """Observe real row locks at the final handoff of the actual async command."""
    from contextlib import asynccontextmanager
    from sqlalchemy.exc import DBAPIError
    from app.adapters.artifacts import CheckerPhaseService
    from app.modules.artifacts.authorization import PreparedPreSubmitMaterializationAuthorization
    from app.modules.artifacts.submission_admission import (
        PreparedSubmissionBundlePreparationCommand, SubmissionBundlePreparationRuntime,
        SubmissionBundleDurablePutService, SubmissionBundleDurablePutResult,
    )
    from tests.checkers.execution.support import forbidden_post_submission
    from tests.authorization.test_pre_submit_attempt_authority import _seed_materializer
    from tests.test_default_pre_submit_execution import _archive, _bytes

    harness = await _harness(tmp_path, isolated_database_env)
    try:
        await _seed_materializer(harness.factory)
        await harness.request.prepared_artifact.close()
        async with harness.factory() as session:
            contributor = harness.contributor_authority(session)
            materializer = PreparedPreSubmitMaterializationAuthorization(
                session, request_id=harness.preparation_request.request_id,
                correlation_id=harness.preparation_request.correlation_id,
            )
            calls = []
            workflow = harness.workflow(session, calls, preparation_authorization=contributor)
            workflow._materialization._authorization = materializer
            admission = _admission(session, tmp_path)
            durable = SubmissionBundleDurablePutService(
                session=session, admission=admission, storage=object(), authorization=contributor,
                task_contexts=TaskRepository(session), project_contexts=ProjectLockedPolicyRepository(session),
            )
            observed = []
            async def final_handoff(request):
                grant_id = (await session.execute(text(
                    "SELECT id FROM project_role_grants WHERE actor_profile_id=:actor "
                    "AND project_id=:project AND role='submitter' AND status='active'"
                ), {"actor": str(harness.actor_id),
                    "project": str(harness.request.effective_plan.lineage.project_id)})).scalar_one()
                for table, record_id in (
                    ("workstream_tasks", harness.request.task_id),
                    ("task_assignments", harness.request.assignment_id),
                    ("actor_profiles", harness.actor_id),
                    ("actor_identity_links", harness.identity_link_id),
                    ("projects", harness.request.effective_plan.lineage.project_id),
                    ("project_role_grants", grant_id),
                ):
                    async with harness.factory() as probe:
                        with pytest.raises(DBAPIError, match="lock timeout"):
                            async with probe.begin():
                                await probe.execute(text("SET LOCAL lock_timeout='150ms'"))
                                await probe.execute(text(f"SELECT id FROM {table} WHERE id=:id FOR UPDATE"),
                                                    {"id": str(record_id)})
                result = await durable.admit_in_transaction(request)
                observed.append(result[2].attempt_id)
                return result

            async def stop_before_provider(prepared, evidence_id, admission_result):
                # Byte execution ends at committed durable intent in this proof.
                await prepared.close()
                return SubmissionBundleDurablePutResult(
                    put_attempt_id=admission_result.attempt_id,
                    pre_submit_evidence_set_id=evidence_id,
                    operation_identity=admission_result.operation_identity,
                    status="prepared", replayed=False, admission_id=None,
                )

            @asynccontextmanager
            async def runtime():
                yield SubmissionBundlePreparationRuntime(
                    preparation=harness.preparation, inspector=harness.inspector,
                    catalogue=harness.catalogue, materialization=workflow._materialization,
                    evidence=workflow, checker_service=CheckerPhaseService(
                        pre_submission=workflow, post_submission=forbidden_post_submission()),
                    durable_put=SimpleNamespace(admit_in_transaction=final_handoff,
                                                publish_after_commit=stop_before_provider),
                )

            command = PreparedSubmissionBundlePreparationCommand(
                session=session, authority=contributor, task_contexts=TaskRepository(session),
                project_contexts=ProjectLockedPolicyRepository(session), runtime_factory=runtime,
            )
            try:
                result = await command.prepare(replace(harness.preparation_request,
                    byte_source=_bytes(_archive(evidence_path=harness.evidence_path))))
                assert observed == [result.put_attempt_id] and calls == [1]
                async with harness.factory() as assertion:
                    intent = (await assertion.scalars(select(SubmissionBundleDurableIntent))).one()
                    assert intent.put_attempt_id == str(result.put_attempt_id)
            finally:
                materializer.close()
    finally:
        await harness.close()
