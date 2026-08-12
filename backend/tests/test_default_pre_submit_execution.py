"""Proof for plan-bound hidden Workstream-default pre-submit execution."""

from __future__ import annotations

import asyncio
from io import BytesIO
from dataclasses import replace
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
import zipfile
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.hashing import canonical_json_hash
from app.core.config import Settings
from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactPreparationDeadlineError,
    ArtifactScratchManager,
)
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactReplica,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
    SubmissionBundleDurableIntent,
)
from app.modules.artifacts.pre_submit_evidence import PreSubmitEvidenceConflict, _validate_execution
from app.modules.artifacts.service import (
    ArtifactAdmissionRelationshipError,
    ArtifactAdmissionService,
    ArtifactStorageNamespaceSpec,
)
from app.modules.artifacts.submission_admission import (
    SubmissionBundleAdmissionPublisher,
    SubmissionBundleDurablePutRequest,
    SubmissionBundleDurablePutService,
)
from app.modules.artifacts.operator import ArtifactOperatorService
from app.modules.artifacts.metrics import artifact_admission_metrics
from app.modules.artifacts.schemas import ArtifactOperatorAuthorizationEvidence
from app.modules.artifacts.submission_authorization import (
    DenySubmissionBundlePreparedAuthorization,
)
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_manifest import (
    build_submission_manifest,
    evaluate_submission_change,
)
from app.modules.artifacts.submission_materialization import (
    DenyPreSubmitMaterializationAuthorization,
    PreparedBundleMaterializationRequest,
    PreparedBundlePreSubmitEvidenceService,
    PreparedBundleMaterializationService,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.catalogue import ACTION_BY_ID
from app.modules.checkers.catalogue import (
    PreSubmissionCheckerPhase,
    build_pre_submission_checker_catalogue,
)
from app.modules.checkers.compiler import compile_effective_project_submission_artifact_policy
from app.modules.checkers.effective_plan import (
    EffectivePreSubmissionPlanLineage,
    compile_effective_pre_submission_execution_plan,
)
from app.modules.checkers.pre_submit_execution import (
    PreSubmissionResultStatus,
    SubmissionPacketView,
)
from app.modules.checkers.api import PreSubmissionInfrastructureUnavailableError
from tests.artifact_store_helpers import artifact_admission_limit_settings
from tests.pre_submit_test_helpers import (
    checker_execution as _CheckerExecution,
    evidence_workflow,
    submission_preparation_request,
)


async def _bytes(value: bytes):
    yield value


class _AllowSubmissionPreparedAuthorization:
    """Test-only final authority that records transaction-bound consumption."""

    def __init__(self) -> None:
        self.facts = None

    async def consume(self, *, prepared_authorization, facts) -> None:
        assert type(prepared_authorization) is PreparedAuthorizationHandle
        self.facts = facts


class _AllowOperatorAuthority:
    async def authorize(self, *, facts, **_values) -> ArtifactOperatorAuthorizationEvidence:
        return ArtifactOperatorAuthorizationEvidence(
            action_id=facts.action_id,
            permission_id=ACTION_BY_ID[facts.action_id].permission_id.value,
            decision_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_evidence_workflow_requires_transaction_free_session() -> None:
    materialization = SimpleNamespace(materialize_prepared_bundle=lambda _request: None)
    workflow = PreparedBundlePreSubmitEvidenceService(
        session=cast(Any, SimpleNamespace(in_transaction=lambda: True)),
        materialization=cast(Any, materialization),
        preparation_authorization=cast(Any, SimpleNamespace()),
        task_contexts=cast(Any, SimpleNamespace()),
        project_contexts=cast(Any, SimpleNamespace()),
    )

    with pytest.raises(RuntimeError, match="requires a transaction-free session"):
        await workflow.execute(
            cast(Any, object()),
            preparation_request=cast(Any, object()),
        )


def _archive(path: str = "task.toml", *, extra_path: str | None = None) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:

        def write(name: str, value: bytes) -> None:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            archive.writestr(entry, value)

        write(path, b"[task]\nname='proof'\n")
        if extra_path is not None:
            write(extra_path, b"blocked\n")
        if path != "evidence/results":
            write("evidence/results", b"verified\n")
    return output.getvalue()


def _effective_policy() -> dict[str, object]:
    defaults = {
        "required_packet_fields": ["summary", "worker_attestation"],
        "forbidden_artifacts": [{"pattern": ".env"}, {"pattern": ".git/**"}],
        "attestation_terms": ["rights_confirmed"],
    }
    return {
        "workstream_default_policy": defaults,
        "project_policy": {},
        "required_packet_fields": defaults["required_packet_fields"],
        "required_artifacts": [{"key": "task.toml", "path": "task.toml", "required": True}],
        "required_evidence": [{"key": "results", "required": True}],
        "forbidden_artifacts": defaults["forbidden_artifacts"],
        "attestation_terms": defaults["attestation_terms"],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["s3"],
        "maximum_file_size_bytes": 1_000_000,
        "maximum_package_size_bytes": 5_000_000,
        "packaging": {"package_required": True, "allowed_package_formats": ["zip"]},
    }


def _plan(catalogue):
    policy = _effective_policy()
    policy_hash = canonical_json_hash(policy)
    compiled = compile_effective_project_submission_artifact_policy(policy, policy_hash)
    lineage = EffectivePreSubmissionPlanLineage(
        project_id=uuid4(),
        guide_id=uuid4(),
        guide_version=1,
        source_snapshot_id=uuid4(),
        source_snapshot_hash=canonical_json_hash({}),
        effective_policy_id=uuid4(),
        effective_policy_hash=policy_hash,
        pre_submit_policy_id=uuid4(),
        pre_submit_policy_bundle_hash=compiled.compiled_bundle_hash,
    )
    return compile_effective_pre_submission_execution_plan(
        lineage=lineage,
        effective_policy=policy,
        compiled_bundle=compiled.compiled_bundle,
        catalogue=catalogue,
    )


def _rehash_plan(plan, *, entries=None, catalogue_manifest_sha256=None):
    changed = replace(
        plan,
        entries=plan.entries if entries is None else tuple(entries),
        catalogue_manifest_sha256=(
            plan.catalogue_manifest_sha256
            if catalogue_manifest_sha256 is None
            else catalogue_manifest_sha256
        ),
    )
    return replace(changed, plan_sha256=canonical_json_hash(changed.as_dict()))


def _limits() -> ArtifactPreparationLimits:
    return ArtifactPreparationLimits(
        aggregate_reserved_bytes=2 * HARD_MAXIMUM_ARTIFACT_BYTES,
        maximum_files=2,
        maximum_concurrency=2,
        minimum_free_bytes=0,
        reservation_ttl_seconds=30,
        total_deadline_seconds=10,
        cleanup_margin_seconds=5,
        stream_buffer_bytes=1024,
        maximum_source_bytes=1024 * 1024,
        maximum_workspace_entries=2_000,
    )


class _AllowAuthority:
    def __init__(self) -> None:
        self.preparation_facts = None
        self.facts = None
        self.action_id = None
        self.service_identity = None

    async def prepare(self, *, facts, idempotency_key):
        del idempotency_key
        self.preparation_facts = facts
        return _handle()

    async def consume(self, **values):
        self.facts = values["facts"]


class _TestPreparedAuthorizationHandle:
    """Typed sentinel accepted only by the bounded authorization protocol double."""


def _handle() -> PreparedAuthorizationHandle:
    return cast(PreparedAuthorizationHandle, _TestPreparedAuthorizationHandle())


async def _request(
    tmp_path: Path,
    *,
    path: str = "task.toml",
    extra_path: str | None = None,
    catalogue=None,
):
    selected_catalogue = catalogue or build_pre_submission_checker_catalogue()
    plan = _plan(selected_catalogue)
    data = _archive(path, extra_path=extra_path)
    inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=_limits())
    preparation = ArtifactPreparationService(manager)
    prepared = await preparation.prepare(_bytes(data), media_type="application/zip")
    inspection = await prepared.inspect(inspector)
    manifest = build_submission_manifest(inspection)
    change = evaluate_submission_change(
        commitment=prepared.commitment,
        manifest=manifest,
        predecessor=None,
        predecessor_exists=False,
    )
    request = PreparedBundleMaterializationRequest(
        prepared_authorization=_handle(),
        task_id=uuid4(),
        assignment_id=uuid4(),
        submission_artifact_policy_id=plan.lineage.effective_policy_id,
        checker_policy_id=plan.lineage.pre_submit_policy_id,
        predecessor_submission_version=None,
        prepared_artifact=prepared,
        effective_plan=plan,
        inspection=inspection,
        manifest=manifest,
        change_gate=change,
        packet=SubmissionPacketView(
            summary="Completed exact project work.",
            contributor_attestation=(
                "I confirm no confidential client data, credentials, or copied source "
                "material is included in this submission; rights_confirmed."
            ),
        ),
    )
    return request, inspector, manager, preparation, selected_catalogue


@pytest.mark.asyncio
async def test_authority_denial_precedes_workspace_and_checker_access(tmp_path: Path) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    service = PreparedBundleMaterializationService(
        authorization=DenyPreSubmitMaterializationAuthorization(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    with pytest.raises(ArtifactAuthorityDeniedError):
        await service.materialize_prepared_bundle(request)

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_authority_preparation_denies_before_zip_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalogue = build_pre_submission_checker_catalogue()
    plan = _plan(catalogue)
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=_limits())
    preparation = ArtifactPreparationService(manager)
    prepared = await preparation.prepare(_bytes(_archive()), media_type="application/zip")
    inspection_calls = 0

    async def forbidden_inspection(*_args, **_kwargs):
        nonlocal inspection_calls
        inspection_calls += 1
        raise AssertionError("ZIP inspection preceded authority preparation")

    monkeypatch.setattr(type(prepared), "inspect", forbidden_inspection)
    service = PreparedBundleMaterializationService(
        authorization=DenyPreSubmitMaterializationAuthorization(),
        preparation=preparation,
        checker_execution=_CheckerExecution(
            SubmissionArchiveInspector(SubmissionArchiveLimits()), catalogue
        ),
        storage_scheme="s3",
    )

    with pytest.raises(ArtifactAuthorityDeniedError):
        await service.prepare_authorization(
            task_id=uuid4(),
            assignment_id=uuid4(),
            submission_artifact_policy_id=plan.lineage.effective_policy_id,
            checker_policy_id=plan.lineage.pre_submit_policy_id,
            prepared_artifact=prepared,
            effective_plan=plan,
            idempotency_key=uuid4(),
        )

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    assert inspection_calls == 0
    await prepared.close()
    manager.close()


@pytest.mark.asyncio
async def test_manifest_drift_denies_before_authority_and_workspace(tmp_path: Path) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    first = next(entry for entry in request.inspection.entries if entry.sha256 is not None)
    forged_entry = replace(first, sha256="sha256:" + "f" * 64)
    forged_inspection = replace(
        request.inspection,
        entries=tuple(
            forged_entry if entry is first else entry for entry in request.inspection.entries
        ),
    )
    forged_manifest = build_submission_manifest(forged_inspection)
    forged_change = evaluate_submission_change(
        commitment=request.prepared_artifact.commitment,
        manifest=forged_manifest,
        predecessor=None,
        predecessor_exists=False,
    )
    authority = _AllowAuthority()
    service = PreparedBundleMaterializationService(
        authorization=authority,
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    with pytest.raises(
        PreSubmissionInfrastructureUnavailableError,
        match="materialization_context_invalid",
    ):
        await service.materialize_prepared_bundle(
            replace(request, manifest=forged_manifest, change_gate=forged_change)
        )

    assert authority.facts is None
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_two_stage_authority_uses_one_handle_and_exact_final_facts(
    tmp_path: Path,
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    authority = _AllowAuthority()
    service = PreparedBundleMaterializationService(
        authorization=authority,
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )
    handle = await service.prepare_authorization(
        task_id=request.task_id,
        assignment_id=request.assignment_id,
        submission_artifact_policy_id=request.submission_artifact_policy_id,
        checker_policy_id=request.checker_policy_id,
        prepared_artifact=request.prepared_artifact,
        effective_plan=request.effective_plan,
        idempotency_key=uuid4(),
    )

    result = await service.materialize_prepared_bundle(
        replace(request, prepared_authorization=handle)
    )

    assert result.eligible is True
    assert authority.preparation_facts is not None
    assert authority.facts is not None
    assert authority.facts.preparation == authority.preparation_facts
    assert authority.facts.semantic_manifest_sha256 == request.manifest.sha256
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_effective_evidence_workflow_persists_once_and_replays_exactly(
    tmp_path: Path,
    isolated_database_env: str,
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    actor_id = uuid4()
    identity_link_id = uuid4()
    lineage = request.effective_plan.lineage
    engine = create_async_engine(isolated_database_env)
    custody_triggers = (
        ("projects", "project_creation_custody"),
        ("project_guides", "guide_mutation_product_custody"),
        ("project_guides", "guide_lineage_lifecycle_guard"),
        ("guide_source_snapshots", "source_snapshot_product_custody"),
        ("submission_artifact_policies", "submission_policy_creation_custody"),
        (
            "effective_project_submission_artifact_policies",
            "effective_submission_policy_custody",
        ),
        ("pre_submit_checker_policies", "pre_submit_policy_custody"),
        ("review_policies", "review_policy_mutation_custody"), ("revision_policies", "revision_policy_mutation_custody"),  # noqa: E501
    )
    blocked_prepared = replay_prepared = drift_prepared = denied_prepared = None
    original_prepared_closed = bool()
    tables = (
        "artifact_contents",
        "artifact_replicas",
        "artifact_put_attempts",
        "submission_bundle_admissions",
        "submissions",
        "checker_runs",
        "review_queue_entries",
        "pre_submit_evidence_sets",
        "pre_submit_evidence_results",
    )
    try:
        async with engine.begin() as connection:
            params = {
                "actor": str(actor_id),
                "link": str(identity_link_id),
                "project": str(lineage.project_id),
                "guide": str(lineage.guide_id),
                "snapshot": str(lineage.source_snapshot_id),
                "snapshot_hash": lineage.source_snapshot_hash,
                "submission_policy": str(uuid4()),
                "effective_policy": str(lineage.effective_policy_id),
                "effective_hash": lineage.effective_policy_hash,
                "effective_body": json.dumps(_effective_policy()), "checker_body": json.dumps(compile_effective_project_submission_artifact_policy(_effective_policy(), lineage.effective_policy_hash).compiled_bundle),  # noqa: E501
                "checker_policy": str(lineage.pre_submit_policy_id),
                "checker_hash": lineage.pre_submit_policy_bundle_hash,
                "post_policy": str(uuid4()),
                "post_policy_hash": "sha256:" + "8" * 64,
                "review_policy": str(uuid4()),
                "review_policy_hash": "sha256:" + "7" * 64,
                "revision_policy": str(uuid4()),
                "revision_policy_hash": "sha256:" + "6" * 64,
                "task": str(request.task_id),
                "assignment": str(request.assignment_id),
            }
            await connection.execute(
                text(
                    "insert into actor_profiles "
                    "(id,actor_kind,status,provisioning_method,created_by) values "
                    "(:actor,'human','active','automatic_first_access','test')"
                ),
                params,
            )
            await connection.execute(
                text(
                    "insert into actor_identity_links "
                    "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,"
                    "last_verified_at) values "
                    "(:link,:actor,'flow-test',:actor,'human','active','test',now())"
                ),
                params,
            )
            for table, trigger in custody_triggers:
                await connection.execute(text(f"alter table {table} disable trigger {trigger}"))
            await connection.execute(
                text(
                    "insert into projects (id,name,slug,status) values "
                    "(:project,'Evidence project',:project,'active')"
                ),
                params,
            )
            await connection.execute(
                text(
                    "insert into project_guides "
                    "(id,project_id,version,status,content_markdown,created_by) values "
                    "(:guide,:project,'1','draft','# Guide','test')"
                ),
                params,
            )
            await connection.execute(
                text(
                    "insert into guide_source_snapshots "
                    "(id,project_id,guide_id,guide_version,manifest_schema_version,"
                    "manifest_json,bundle_hash,captured_by) values "
                    "(:snapshot,:project,:guide,'1','1','{}'::json,:snapshot_hash,'test')"
                ),
                params,
            )
            await connection.execute(
                text(
                    "insert into submission_artifact_policies "
                    "(id,project_id,guide_id,guide_version,source_snapshot_id,"
                    "source_snapshot_hash,policy_version,lifecycle_status,policy_body,"
                    "policy_hash,derivation_source,source_material_refs,created_by) values "
                    "(:submission_policy,:project,:guide,'1',:snapshot,:snapshot_hash,'1',"
                    "'draft','{}'::json,:effective_hash,'test','[]'::json,'test')"
                ),
                params,
            )
            await connection.execute(
                text(
                    "insert into effective_project_submission_artifact_policies "
                    "(id,project_id,guide_id,guide_version,source_snapshot_id,"
                    "source_snapshot_hash,submission_artifact_policy_id,"
                    "submission_artifact_policy_hash,lifecycle_status,merge_algorithm_version,"
                    "effective_policy,effective_policy_hash,created_by) values "
                    "(:effective_policy,:project,:guide,'1',:snapshot,:snapshot_hash,"
                    ":submission_policy,:effective_hash,'approved','1',cast(:effective_body as json),"
                    ":effective_hash,'test')"
                ),
                params,
            )
            await connection.execute(
                text(
                    "insert into pre_submit_checker_policies "
                    "(id,project_id,guide_id,guide_version,source_snapshot_id,"
                    "source_snapshot_hash,effective_policy_id,effective_policy_hash,"
                    "lifecycle_status,compiler_version,compiled_bundle,compiled_bundle_hash,"
                    "checker_names,checker_configs,created_by) values "
                    "(:checker_policy,:project,:guide,'1',:snapshot,:snapshot_hash,"
                    ":effective_policy,:effective_hash,'compiled','1',cast(:checker_body as json),"
                    ":checker_hash,'[]'::json,'{}'::json,'test')"
                ),
                params,
            )
            await connection.execute(
                text(
                    "insert into checker_policies "
                    "(id,project_id,guide_id,guide_version,source_snapshot_id,"
                    "source_snapshot_hash,effective_policy_id,effective_policy_hash,"
                    "pre_submit_checker_policy_id,pre_submit_checker_bundle_hash,"
                    "required_checkers,warning_checkers,blocking_severities,policy_hash,"
                    "policy_body,lifecycle_status,created_by) values "
                    "(:post_policy,:project,:guide,'1',:snapshot,:snapshot_hash,"
                    ":effective_policy,:effective_hash,:checker_policy,:checker_hash,"
                    "'[]'::json,'[]'::json,'[]'::json,:post_policy_hash,'{}'::json,"
                    "'compiled','test')"
                ),
                params,
            )
            await connection.execute(
                text(
                    "insert into review_policies "
                    "(id,project_id,guide_version,policy_generation,policy_hash,"
                    "semantics_status,requires_second_review,allowed_decisions,"
                    "minimum_finding_fields) values "
                    "(:review_policy,:project,'1',1,:review_policy_hash,"
                    "'legacy_incomplete',false,'[]'::json,'[]'::json)"
                ),
                params,
            )
            await connection.execute(
                text(
                    "with inserted_revision as (insert into revision_policies "
                    "(id,project_id,guide_version,policy_generation,policy_hash,"
                    "semantics_status,max_revision_rounds,revision_deadline_hours,"
                    "allowed_resubmission_states) values "
                    "(:revision_policy,:project,'1',1,:revision_policy_hash,"
                    "'legacy_incomplete',1,24,'[]'::json) returning id) "
                    "update project_guides set status='active',selected_review_policy_id=:review_policy,selected_review_policy_generation=1,selected_review_policy_hash=:review_policy_hash,selected_revision_policy_id=:revision_policy,selected_revision_policy_generation=1,selected_revision_policy_hash=:revision_policy_hash where id=:guide"
                ),
                params,
            )
            await connection.execute(
                text(
                    "insert into workstream_tasks "
                    "(id,project_id,locked_guide_version,locked_guide_source_snapshot_id,"
                    "locked_guide_source_snapshot_hash,"
                    "locked_effective_project_submission_artifact_policy_id,"
                    "locked_effective_project_submission_artifact_policy_hash,"
                    "locked_pre_submit_checker_policy_id,locked_pre_submit_checker_bundle_hash,"
                    "locked_post_submit_checker_policy_id,"
                    "locked_post_submit_checker_policy_version,"
                    "locked_post_submit_checker_policy_hash,"
                    "locked_post_submit_checker_policy_body,"
                    "locked_review_policy_id,locked_review_policy_generation,"
                    "locked_review_policy_hash,locked_revision_policy_id,"
                    "locked_revision_policy_generation,locked_revision_policy_hash,"
                    "source_type,title,description,skill_tags,status,assigned_to,created_by) values "
                    "(:task,:project,'1',:snapshot,:snapshot_hash,:effective_policy,"
                    ":effective_hash,:checker_policy,:checker_hash,:post_policy,'1',"
                    ":post_policy_hash,'{}'::json,:review_policy,1,:review_policy_hash,"
                    ":revision_policy,1,:revision_policy_hash,'manual','Evidence task',"
                    "'Evidence test task','[]'::json,'in_progress',:actor,'test')"
                ),
                params,
            )
            await connection.execute(
                text(
                    "insert into task_assignments "
                    "(id,task_id,contributor_id,assigned_by,status) values "
                    "(:assignment,:task,:actor,'test','active')"
                ),
                params,
            )
            before = {
                table: int(await connection.scalar(text(f"select count(*) from {table}")) or 0)
                for table in tables
            }
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            preparation_authority = cast(Any, SimpleNamespace(revalidate=AsyncMock()))
            workflow = evidence_workflow(
                session=session,
                preparation=preparation,
                inspector=inspector,
                catalogue=catalogue,
                materialization_authorization=_AllowAuthority(),
                preparation_authorization=preparation_authority,
            )
            preparation_request = submission_preparation_request(
                request,
                actor_profile_id=actor_id,
                identity_link_id=identity_link_id,
            )

            async def fresh_checked_bundle():
                prepared = await preparation.prepare(
                    _bytes(_archive()),
                    media_type="application/zip",
                )
                inspection = await prepared.inspect(inspector)
                manifest = build_submission_manifest(inspection)
                fresh_request = replace(
                    request,
                    prepared_artifact=prepared,
                    inspection=inspection,
                    manifest=manifest,
                    change_gate=evaluate_submission_change(
                        commitment=prepared.commitment,
                        manifest=manifest,
                        predecessor=None,
                        predecessor_exists=False,
                    ),
                )
                result = await workflow.execute(
                    fresh_request,
                    preparation_request=preparation_request,
                )
                assert result.pass_capability is not None
                return prepared, result

            first = await workflow.execute(
                request,
                preparation_request=preparation_request,
            )
            replay = await workflow.execute(
                request,
                preparation_request=preparation_request,
            )
            assert first.pass_capability is not None
            namespace = ArtifactStorageNamespaceSpec(
                backend="local",
                adapter="local",
                provider_profile="test",
                namespace_descriptor={"test": "submission-bundle"},
                namespace_fingerprint=canonical_json_hash({"test": "submission-bundle"}),
            )
            admission_settings = Settings(
                **artifact_admission_limit_settings(1024 * 1024),
                environment="test",
                artifact_store_backend="local",
                artifact_local_root=tmp_path / "durable",
                artifact_scratch_root=tmp_path / "scratch",
                artifact_scratch_minimum_free_bytes=0,
            )
            provider = SimpleNamespace(
                execute_committed_put=AsyncMock(),
                resume_committed_put=AsyncMock(),
            )
            final_authority = _AllowSubmissionPreparedAuthorization()
            durable_service = SubmissionBundleDurablePutService(
                session=session,
                admission=ArtifactAdmissionService(
                    session,
                    admission_settings,
                    namespace,
                ),
                storage=provider,
                authorization=final_authority,
            )
            async with session.begin():
                (
                    retained,
                    selected_evidence_id,
                    first_admission,
                ) = await durable_service.admit_in_transaction(
                    SubmissionBundleDurablePutRequest(
                        prepared_authorization=object.__new__(PreparedAuthorizationHandle),
                        prepared_artifact=request.prepared_artifact,
                        pass_capability=first.pass_capability,
                    )
                )
            provider.execute_committed_put.assert_not_awaited()
            provider.resume_committed_put.assert_not_awaited()
            intent = await session.scalar(
                select(SubmissionBundleDurableIntent).where(
                    SubmissionBundleDurableIntent.put_attempt_id == str(first_admission.attempt_id)
                )
            )
            assert intent is not None
            replay_intent_id = UUID(intent.id)
            await session.rollback()
            assert retained is request.prepared_artifact
            await retained.close()
            original_prepared_closed = True

            replay_prepared, fresh = await fresh_checked_bundle()
            async with session.begin():
                (
                    replay_retained,
                    replay_evidence_id,
                    replay_admission,
                ) = await durable_service.admit_in_transaction(
                    SubmissionBundleDurablePutRequest(
                        prepared_authorization=object.__new__(PreparedAuthorizationHandle),
                        prepared_artifact=replay_prepared,
                        pass_capability=fresh.pass_capability,
                        replay_durable_intent_id=replay_intent_id,
                    )
                )
            assert replay_admission.replayed is True
            assert replay_admission.attempt_id == first_admission.attempt_id
            assert replay_evidence_id == fresh.evidence.evidence_set_id
            await replay_retained.close()
            intent_count = int(
                await session.scalar(
                    select(func.count()).select_from(SubmissionBundleDurableIntent)
                )
                or 0
            )
            assert intent_count == 1
            await session.rollback()

            drift_prepared, drift = await fresh_checked_bundle()
            await session.execute(
                text("update task_assignments set status='inactive' where id=:assignment"),
                {"assignment": str(request.assignment_id)},
            )
            await session.commit()
            with pytest.raises(
                ArtifactAdmissionRelationshipError,
                match="passing evidence is unavailable|locked_context",
            ):
                async with session.begin():
                    await durable_service.admit_in_transaction(
                        SubmissionBundleDurablePutRequest(
                            prepared_authorization=object.__new__(PreparedAuthorizationHandle),
                            prepared_artifact=drift_prepared,
                            pass_capability=drift.pass_capability,
                        )
                    )
            await session.execute(
                text("update task_assignments set status='active' where id=:assignment"),
                {"assignment": str(request.assignment_id)},
            )
            await session.commit()

            denied_prepared, denied = await fresh_checked_bundle()
            denied_service = SubmissionBundleDurablePutService(
                session=session,
                admission=ArtifactAdmissionService(
                    session,
                    admission_settings,
                    namespace,
                ),
                storage=provider,
                authorization=DenySubmissionBundlePreparedAuthorization(),
            )
            with pytest.raises(ArtifactAuthorityDeniedError):
                async with session.begin():
                    await denied_service.admit_in_transaction(
                        SubmissionBundleDurablePutRequest(
                            prepared_authorization=object.__new__(PreparedAuthorizationHandle),
                            prepared_artifact=denied_prepared,
                            pass_capability=denied.pass_capability,
                        )
                    )
            async with session.begin():
                attempt = await session.get(
                    ArtifactPutAttempt,
                    str(first_admission.attempt_id),
                    with_for_update=True,
                )
                assert attempt is not None
                content = ArtifactContent(
                    id=str(uuid4()),
                    sha256=attempt.sha256,
                    byte_count=attempt.byte_count,
                    media_type=attempt.media_type,
                    normalized_display_name=None,
                )
                replica = ArtifactReplica(
                    id=str(uuid4()),
                    content_id=content.id,
                    storage_namespace_id=attempt.storage_namespace_id,
                    namespace_fingerprint=attempt.namespace_fingerprint,
                    adapter="local",
                    provider_profile="test",
                    provider_object_ref=attempt.canonical_target,
                    verification_state="verified",
                    availability_state="available",
                    integrity_state="valid",
                )
                session.add_all((content, replica))
                await session.flush()
                put_receipt = ArtifactOperationReceipt(
                    id=str(uuid4()),
                    put_attempt_id=attempt.id,
                    guide_source_item_id=None,
                    checker_run_id=None,
                    logical_role=None,
                    replica_id=replica.id,
                    operation="put",
                    idempotency_key=attempt.operation_identity,
                    request_digest=attempt.request_digest,
                    provider_object_ref=attempt.canonical_target,
                    replayed=False,
                    outcome="stored_pending_verification",
                    attempt_number=1,
                    correlation_id=attempt.operation_identity,
                    details=[],
                )
                job = ArtifactVerificationJob(
                    id=str(uuid4()),
                    originating_put_attempt_id=attempt.id,
                    replica_id=replica.id,
                    status="verified",
                    maximum_attempts=5,
                    execution_generation=1,
                )
                session.add_all((put_receipt, job))
                attempt.status = "object_confirmed"
                attempt.replica_id = replica.id
                attempt.receipt_id = put_receipt.id
                verification_receipt = ArtifactVerificationReceipt(
                    id=str(uuid4()),
                    verification_job_id=job.id,
                    execution_generation=1,
                    outcome="verified",
                    observed_sha256=attempt.sha256,
                    observed_byte_count=attempt.byte_count,
                )
                session.add(verification_receipt)
                await session.flush()
                job_id = job.id
                verification_receipt_id = verification_receipt.id
                attempt_byte_count = attempt.byte_count

            async def publish_ready() -> str:
                async with session_factory() as publisher_session:
                    async with publisher_session.begin():
                        ready = await SubmissionBundleAdmissionPublisher(
                            publisher_session
                        ).publish_verified(
                            verification_job_id=job_id,
                            verification_receipt_id=verification_receipt_id,
                        )
                        assert ready is not None and ready.status == "ready"
                        return ready.id

            published_ids = await asyncio.gather(publish_ready(), publish_ready())
            assert published_ids[0] == published_ids[1]
            async with session.begin():
                usage = await ArtifactOperatorService(
                    session,
                    _AllowOperatorAuthority(),
                    admission_settings,
                    artifact_admission_metrics,
                ).admission_usage(
                    authorization_context=cast(Any, object()),
                    project_id=lineage.project_id,
                    task_id=request.task_id,
                    cursor=None,
                    limit=10,
                )
                assert len(usage.items) == 3
                assert all(item["unbound_ready_count"] == 1 for item in usage.items)
                assert all(
                    item["unbound_ready_bytes"] == attempt_byte_count for item in usage.items
                )
                assert all(item["stale_count"] == 0 for item in usage.items)
            durable_counts = {
                table: int(await session.scalar(text(f"select count(*) from {table}")) or 0)
                for table in (
                    "artifact_put_attempts",
                    "submission_bundle_durable_intents",
                    "artifact_admission_charges",
                )
            }
            guide_continuation_matches = int(
                await session.scalar(
                    text(
                        "select count(*) from artifact_put_attempts attempt "
                        "join guide_source_snapshot_items item "
                        "on item.id=attempt.guide_source_item_id "
                        "where attempt.producer_request_type='submission_bundle'"
                    )
                )
                or 0
            )
            await session.rollback()
            assert durable_counts == {
                "artifact_put_attempts": 1,
                "submission_bundle_durable_intents": 1,
                "artifact_admission_charges": 4,
            }
            assert guide_continuation_matches == 0
            provider.execute_committed_put.assert_not_awaited()
            provider.resume_committed_put.assert_not_awaited()
            assert selected_evidence_id == first.evidence.evidence_set_id
            await session.execute(
                text(
                    "update submission_bundle_admissions set status='stale', "
                    "stale_at=now(), stale_reason='predecessor_advanced' where id=:id"
                ),
                {"id": published_ids[0]},
            )
            await session.commit()
            async with session.begin():
                stale_usage = await ArtifactOperatorService(
                    session,
                    _AllowOperatorAuthority(),
                    admission_settings,
                    artifact_admission_metrics,
                ).admission_usage(
                    authorization_context=cast(Any, object()),
                    project_id=lineage.project_id,
                    task_id=request.task_id,
                    cursor=None,
                    limit=10,
                )
                assert all(item["unbound_ready_count"] == 0 for item in stale_usage.items)
                assert all(item["stale_count"] == 1 for item in stale_usage.items)
                assert all(item["stale_bytes"] == attempt_byte_count for item in stale_usage.items)
            with pytest.raises(DBAPIError):
                await session.execute(
                    text(
                        "update submission_bundle_admissions set archive_sha256=:digest "
                        "where id=:id"
                    ),
                    {"id": published_ids[0], "digest": "sha256:" + "9" * 64},
                )
                await session.commit()
            await session.rollback()
            with pytest.raises(DBAPIError):
                await session.execute(
                    text("delete from submission_bundle_admissions where id=:id"),
                    {"id": published_ids[0]},
                )
                await session.commit()
            await session.rollback()
            blocked_prepared = await preparation.prepare(
                _bytes(_archive("task.toml")), media_type="application/zip"
            )
            blocked_inspection = await blocked_prepared.inspect(inspector)
            blocked_manifest = build_submission_manifest(blocked_inspection)
            blocked_request = replace(
                request,
                prepared_artifact=blocked_prepared,
                inspection=blocked_inspection,
                manifest=blocked_manifest,
                change_gate=evaluate_submission_change(
                    commitment=blocked_prepared.commitment,
                    manifest=blocked_manifest,
                    predecessor=None,
                    predecessor_exists=False,
                ),
                packet=SubmissionPacketView(
                    summary="Completed exact project work.",
                    contributor_attestation="",
                ),
            )
            blocked = await workflow.execute(
                blocked_request,
                preparation_request=preparation_request,
            )
        async with engine.begin() as connection:
            evidence_count = int(
                await connection.scalar(text("select count(*) from pre_submit_evidence_sets")) or 0
            )
            result_count = int(
                await connection.scalar(text("select count(*) from pre_submit_evidence_results"))
                or 0
            )
            after = {
                table: int(await connection.scalar(text(f"select count(*) from {table}")) or 0)
                for table in tables
            }
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
                "locked_policy_sha256,now() from pre_submit_evidence_results limit 1",
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
    finally:
        for prepared in (
            blocked_prepared,
            replay_prepared,
            drift_prepared,
            denied_prepared,
        ):
            if prepared is not None:
                await prepared.close()
        if not original_prepared_closed:
            await request.prepared_artifact.close()
        try:
            manager.close()
        finally:
            try:
                async with engine.begin() as connection:
                    for table, trigger in reversed(custody_triggers):
                        await connection.execute(
                            text(f"alter table {table} enable trigger {trigger}")
                        )
            finally:
                await engine.dispose()

    assert first.evidence.replayed is False
    assert replay.evidence.replayed is True
    assert replay.evidence.evidence_set_id == first.evidence.evidence_set_id
    assert first.pass_capability is not None
    assert replay.pass_capability is None
    assert first.failure_audit is None
    assert blocked.pass_capability is None
    assert blocked.evidence.replayed is False
    assert blocked.failure_audit is not None
    assert blocked.failure_audit["event_type"] == "pre_submission_check_failed"
    assert blocked.failure_audit["failed_count"] >= 1
    assert "task.toml" not in repr(blocked.failure_audit)
    assert evidence_count == 5
    assert result_count == 5 * len(request.effective_plan.entries)
    assert after == {
        **before,
        "artifact_contents": before["artifact_contents"] + 1,
        "artifact_replicas": before["artifact_replicas"] + 1,
            "artifact_put_attempts": before["artifact_put_attempts"] + 1,
            "submission_bundle_admissions": before["submission_bundle_admissions"] + 1,
            "pre_submit_evidence_sets": evidence_count, "pre_submit_evidence_results": result_count,  # noqa: E501
        }


@pytest.mark.asyncio
async def test_materializer_rejects_policy_lineage_mismatch_before_authority(
    tmp_path: Path,
) -> None:
    """Reject caller-selected policy identity before consuming authority."""
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    authority = _AllowAuthority()
    service = PreparedBundleMaterializationService(
        authorization=authority,
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    with pytest.raises(
        PreSubmissionInfrastructureUnavailableError,
        match="pre_submission_materialization_context_invalid",
    ):
        await service.materialize_prepared_bundle(
            replace(request, submission_artifact_policy_id=uuid4())
        )

    assert authority.facts is None
    await request.prepared_artifact.close()
    await preparation.release_prepared_artifact(request.prepared_artifact._binding)
    manager.close()


@pytest.mark.asyncio
async def test_effective_executor_uses_plan_order_and_dispatches_project_rules(
    tmp_path: Path,
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    authority = _AllowAuthority()
    service = PreparedBundleMaterializationService(
        authorization=authority,
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    result = await service.materialize_prepared_bundle(request)

    expected = [
        entry.definition_id
        for entry in request.effective_plan.entries
        if entry.phase in set(PreSubmissionCheckerPhase)
    ]
    assert [entry.definition_id for entry in result.entries] == expected
    assert any(entry.definition_id.startswith("policy.") for entry in result.entries)
    assert all(
        entry.checker_execution_status == PreSubmissionResultStatus.PASSED.value
        for entry in result.entries
    )
    assert result.eligible is True
    assert authority.facts is not None
    assert authority.facts.task_id == request.task_id
    assert authority.facts.assignment_id == request.assignment_id
    assert authority.facts.project_id == request.effective_plan.lineage.project_id
    assert authority.facts.submission_artifact_policy_id == request.submission_artifact_policy_id
    assert authority.facts.checker_policy_id == request.checker_policy_id
    assert authority.facts.prepared_generation_id == request.prepared_artifact.generation_id
    assert authority.facts.plan_sha256 == request.effective_plan.plan_sha256
    assert (
        authority.facts.catalogue_manifest_sha256
        == request.effective_plan.catalogue_manifest_sha256
    )
    assert authority.facts.archive_sha256 == request.prepared_artifact.commitment.sha256
    assert authority.facts.archive_byte_count == request.prepared_artifact.commitment.byte_count
    assert authority.facts.semantic_manifest_sha256 == request.manifest.sha256
    assert authority.facts.storage_scheme == "s3"
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_blocking_default_stops_later_dependency_without_review_decision(
    tmp_path: Path,
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path, path=".env")
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    result = await service.materialize_prepared_bundle(request)
    by_id = {entry.definition_id: entry for entry in result.entries}

    assert (
        by_id["artifact.sensitive_paths.high_confidence"].checker_execution_status
        == PreSubmissionResultStatus.FAILED.value
    )
    assert (
        by_id["artifact.quality.placeholder_signal"].checker_execution_status
        == PreSubmissionResultStatus.DEPENDENCY_NOT_RUN.value
    )
    assert result.eligible is False
    assert all(
        value not in {"accept", "needs_revision", "reject"}
        for entry in result.entries
        for value in (entry.checker_execution_status, entry.message_code, entry.failure_code)
        if value is not None
    )
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_disabled_advisory_is_explicit_and_not_skipped_success(tmp_path: Path) -> None:
    catalogue = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.quality.placeholder_signal"})
    )
    request, inspector, manager, preparation, _ = await _request(tmp_path, catalogue=catalogue)
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    result = await service.materialize_prepared_bundle(request)
    advisory = next(
        entry
        for entry in result.entries
        if entry.definition_id == "artifact.quality.placeholder_signal"
    )

    assert advisory.checker_execution_status == PreSubmissionResultStatus.ADVISORY_DISABLED.value
    assert result.eligible is True
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_quality_warning_emits_only_a_bounded_category_count(tmp_path: Path) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    request = replace(
        request,
        packet=replace(request.packet, summary="Completed work; TODO placeholder removed."),
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    result = await service.materialize_prepared_bundle(request)
    warning = next(
        entry
        for entry in result.entries
        if entry.definition_id == "artifact.quality.placeholder_signal"
    )

    assert warning.checker_execution_status == PreSubmissionResultStatus.WARNING.value
    assert warning.metadata == (("matched_category_count", 2),)
    assert result.eligible is True
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_forged_plan_identity_fails_closed_and_cleans_workspace(tmp_path: Path) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    forged = replace(request.effective_plan, plan_sha256="sha256:" + "0" * 64)
    request = replace(request, effective_plan=forged)
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    with pytest.raises(PreSubmissionInfrastructureUnavailableError, match="plan_identity"):
        await service.materialize_prepared_bundle(request)

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("invalid_state", "expected_message"),
    (
        ("stale_entry", "pre_submission_plan_entry_stale"),
        ("duplicate", "pre_submission_duplicate_result"),
        ("unknown", "pre_submission_dispatch_capability_unknown"),
    ),
)
async def test_invalid_executor_state_fails_closed_and_cleans_workspace(
    tmp_path: Path,
    invalid_state: str,
    expected_message: str,
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    entries = list(request.effective_plan.entries)
    target_index = next(
        index
        for index, entry in enumerate(entries)
        if entry.definition_id == "submission.packet.required_fields"
    )
    selected_catalogue = catalogue
    if invalid_state == "stale_entry":
        entries[target_index] = replace(entries[target_index], definition_version="stale")
    elif invalid_state == "duplicate":
        entries.insert(target_index + 1, entries[target_index])
    else:
        unknown = replace(entries[target_index], dispatch_capability="unknown.capability")
        entries[target_index] = unknown
        original = catalogue.definition(unknown.definition_id)

        class _UnknownCatalogue:
            manifest_sha256 = catalogue.manifest_sha256

            def definition(self, definition_id):
                definition = catalogue.definition(definition_id)
                if definition_id != original.stable_id:
                    return definition

                class _UnknownDefinition:
                    dispatch_capability = "unknown.capability"

                    def __getattr__(self, name):
                        return getattr(definition, name)

                return _UnknownDefinition()

        selected_catalogue = _UnknownCatalogue()
    request = replace(
        request,
        effective_plan=_rehash_plan(request.effective_plan, entries=entries),
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, selected_catalogue),
        storage_scheme="s3",
    )

    with pytest.raises(PreSubmissionInfrastructureUnavailableError, match=expected_message):
        await service.materialize_prepared_bundle(request)

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_disabled_mandatory_executor_state_fails_closed(tmp_path: Path) -> None:
    request, inspector, manager, preparation, _ = await _request(tmp_path)
    catalogue = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.outer_zip.valid"})
    )
    entries = [
        replace(entry, checker_definition_state="disabled")
        if entry.definition_id == "artifact.outer_zip.valid"
        else entry
        for entry in request.effective_plan.entries
    ]
    request = replace(
        request,
        effective_plan=_rehash_plan(
            request.effective_plan,
            entries=entries,
            catalogue_manifest_sha256=catalogue.manifest_sha256,
        ),
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    with pytest.raises(PreSubmissionInfrastructureUnavailableError):
        await service.materialize_prepared_bundle(request)

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_effective_execution_enforces_project_only_forbidden_rule(tmp_path: Path) -> None:
    catalogue = build_pre_submission_checker_catalogue()
    policy = _effective_policy()
    project_rule = {"pattern": "project-only.blocked"}
    policy["project_policy"] = {"forbidden_artifacts": [project_rule]}
    policy["forbidden_artifacts"] = [*policy["forbidden_artifacts"], project_rule]
    policy_hash = canonical_json_hash(policy)
    compiled = compile_effective_project_submission_artifact_policy(policy, policy_hash)
    lineage = replace(
        _plan(catalogue).lineage,
        effective_policy_hash=policy_hash,
        pre_submit_policy_bundle_hash=compiled.compiled_bundle_hash,
    )
    plan = compile_effective_pre_submission_execution_plan(
        lineage=lineage,
        effective_policy=policy,
        compiled_bundle=compiled.compiled_bundle,
        catalogue=catalogue,
    )
    request, inspector, manager, preparation, _ = await _request(
        tmp_path,
        extra_path="project-only.blocked",
        catalogue=catalogue,
    )
    request = replace(
        request,
        submission_artifact_policy_id=plan.lineage.effective_policy_id,
        checker_policy_id=plan.lineage.pre_submit_policy_id,
        effective_plan=plan,
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    result = await service.materialize_prepared_bundle(request)

    assert result.eligible is False
    project_result = next(
        entry for entry in result.entries if entry.definition_id == "policy.artifact.forbid"
    )
    assert project_result.checker_execution_status == PreSubmissionResultStatus.FAILED.value
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_effective_execution_enforces_server_owned_storage_scheme(tmp_path: Path) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="local",
    )

    result = await service.materialize_prepared_bundle(request)

    policy_result = next(
        entry for entry in result.entries if entry.definition_id == "policy.storage_scheme.enforce"
    )
    assert policy_result.checker_execution_status == PreSubmissionResultStatus.FAILED.value
    assert policy_result.message_code == "storage_scheme_not_allowed"
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_canonical_result_validator_rejects_forged_definition(tmp_path: Path) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )
    result = await service.materialize_prepared_bundle(request)
    first = result.entries[0]
    forged = replace(
        result,
        checker_facts=replace(
            result.checker_facts,
            entries=(
                replace(
                    first,
                    public_name="caller-selected",
                ),
                *result.entries[1:],
            ),
        ),
    )

    with pytest.raises(
        PreSubmitEvidenceConflict,
        match="pre_submission_result_context_invalid",
    ):
        _validate_execution(request.effective_plan, forged)
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_legacy_precheck_runner_is_not_an_execution_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    import app.modules.checkers.runner as legacy_runner

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy precheck path was called")

    monkeypatch.setattr(legacy_runner, "pre_submit_static_feedback", forbidden)
    monkeypatch.setattr(legacy_runner, "default_checker_registry", forbidden)
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )

    result = await service.materialize_prepared_bundle(request)

    assert result.eligible is True
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_authorized_cancellation_cleans_before_propagating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    from app.modules.checkers.pre_submit_execution import EffectivePreSubmissionProcessor

    original = EffectivePreSubmissionProcessor.process_blocking

    def blocking_process(self, reader, workspace):
        entered.set()
        assert release.wait(timeout=5)
        return original(self, reader, workspace)

    monkeypatch.setattr(EffectivePreSubmissionProcessor, "process_blocking", blocking_process)
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )
    task = asyncio.create_task(service.materialize_prepared_bundle(request))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_cancellation_during_member_projection_cleans_workspace(
    tmp_path: Path,
) -> None:
    request, _inspector, manager, preparation, catalogue = await _request(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class _BlockingProjectionInspector(SubmissionArchiveInspector):
        def _project_file(self, *args, **kwargs):
            entered.set()
            assert release.wait(timeout=5)
            return super()._project_file(*args, **kwargs)

    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(
            _BlockingProjectionInspector(SubmissionArchiveLimits()), catalogue
        ),
        storage_scheme="s3",
    )
    task = asyncio.create_task(service.materialize_prepared_bundle(request))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
async def test_timeout_during_checker_access_cleans_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, inspector, manager, preparation, catalogue = await _request(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    from app.modules.checkers.pre_submit_execution import EffectivePreSubmissionProcessor

    original = EffectivePreSubmissionProcessor.process_blocking

    def blocking_process(self, reader, workspace):
        entered.set()
        assert release.wait(timeout=5)
        return original(self, reader, workspace)

    monkeypatch.setattr(EffectivePreSubmissionProcessor, "process_blocking", blocking_process)
    preparation._active[request.prepared_artifact._binding].deadline = (
        asyncio.get_running_loop().time() + 0.01
    )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(inspector, catalogue),
        storage_scheme="s3",
    )
    task = asyncio.create_task(service.materialize_prepared_bundle(request))
    assert await asyncio.to_thread(entered.wait, 5)
    await asyncio.sleep(0.02)
    release.set()

    with pytest.raises(ArtifactPreparationDeadlineError):
        await task

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ("cancel", "timeout"))
async def test_terminal_event_during_sealing_precedes_checker_access_and_cleans(
    tmp_path: Path,
    terminal: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, _inspector, manager, preparation, catalogue = await _request(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class _BlockingSealInspector(SubmissionArchiveInspector):
        def _seal_projected_content(self, root_fd, entries):
            entered.set()
            assert release.wait(timeout=5)
            return super()._seal_projected_content(root_fd, entries)

    from app.modules.checkers.pre_submit_execution import EffectivePreSubmissionProcessor

    checker_called = threading.Event()
    original_execute = EffectivePreSubmissionProcessor._execute

    def observed_execute(self, tree):
        checker_called.set()
        return original_execute(self, tree)

    monkeypatch.setattr(EffectivePreSubmissionProcessor, "_execute", observed_execute)

    if terminal == "timeout":
        preparation._active[request.prepared_artifact._binding].deadline = (
            asyncio.get_running_loop().time() + 0.01
        )
    service = PreparedBundleMaterializationService(
        authorization=_AllowAuthority(),
        preparation=preparation,
        checker_execution=_CheckerExecution(
            _BlockingSealInspector(SubmissionArchiveLimits()), catalogue
        ),
        storage_scheme="s3",
    )
    task = asyncio.create_task(service.materialize_prepared_bundle(request))
    assert await asyncio.to_thread(entered.wait, 5)
    if terminal == "cancel":
        task.cancel()
        await asyncio.sleep(0)
    else:
        await asyncio.sleep(0.02)
    release.set()

    expected = asyncio.CancelledError if terminal == "cancel" else ArtifactPreparationDeadlineError
    with pytest.raises(expected):
        await task

    assert checker_called.is_set() is False
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await request.prepared_artifact.close()
    manager.close()
