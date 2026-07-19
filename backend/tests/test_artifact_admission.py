"""PostgreSQL proofs for atomic durable-byte admission before provider I/O."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ActorService
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.checkers.models import CheckerRun
from app.modules.artifacts.models import (
    ArtifactAdmissionCharge,
    ArtifactAdmissionScope,
    ArtifactBinding,
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactPutObservationReceipt,
    ArtifactPutAttempt,
    ArtifactPutAttemptCharge,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactUploadItem,
    ArtifactUploadSession,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.interfaces.artifacts import (
    ArtifactObjectMissingError,
    ArtifactStoreError,
    ArtifactStoreNamespaceClaim,
    ArtifactStoreUnavailableError,
)
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    ArtifactInternalResourceType,
    CheckerOutputArtifactAdmissionRequest,
    ContributorArtifactAdmissionRequest,
    GuideArtifactAdmissionRequest,
)
from app.modules.artifacts.service import (
    ArtifactAdmissionCapacityError,
    ArtifactAdmissionConflictError,
    ArtifactAdmissionRelationshipError,
    ArtifactAdmissionService,
    ArtifactStorageNamespaceSpec,
    ArtifactStorageNamespaceError,
    ArtifactStorageOrchestrator,
    ArtifactPendingWorkScanner,
    _verification_authority_facts,
    artifact_storage_namespace_spec,
)
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    PaymentPolicy,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    Project,
    ProjectGuide,
    ReviewPolicy,
    RevisionPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.tasks.models import AuditEvent, Submission, WorkstreamTask
from tests.artifact_store_helpers import (
    artifact_admission_limit_settings,
    minted_source,
)


class _AllowArtifactAuthority:
    """Explicit test-only authority exercising both phases."""

    def __init__(self) -> None:
        self.preflights = 0
        self.terminals = 0

    async def preflight(self, **_values: object) -> None:
        self.preflights += 1

    async def revalidate_terminal(self, **_values: object) -> None:
        self.terminals += 1


class _RevokeTerminalArtifactAuthority(_AllowArtifactAuthority):
    """Test authority modelling any terminal actor/resource invalidation."""

    def __init__(
        self,
        *,
        reason: str,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        resource_type: ArtifactInternalResourceType,
    ) -> None:
        super().__init__()
        self.reason = reason
        self.service_identity = service_identity
        self.action_id = action_id
        self.resource_type = resource_type

    async def revalidate_terminal(self, **values: object) -> None:
        self.terminals += 1
        assert values["service_identity"] == self.service_identity
        assert values["action_id"] == self.action_id
        assert values["facts"].resource_type == self.resource_type
        raise ArtifactAuthorityDeniedError(self.reason)


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return config


@pytest.fixture
def admission_database_env(
    isolated_database_env: str,
    migration_lock,
) -> str:
    """Provide the exact head schema and remove all test evidence afterward."""
    config = _alembic_config()
    with migration_lock():
        asyncio.run(_reset_admission_test_schema(isolated_database_env))
        command.upgrade(config, "head")
        try:
            yield isolated_database_env
        finally:
            asyncio.run(_reset_admission_test_schema(isolated_database_env))


async def _reset_admission_test_schema(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("drop schema if exists public cascade"))
            await connection.execute(text("create schema public"))
    finally:
        await engine.dispose()


def _settings(tmp_path: Path, *, maximum_bytes: int = 1024) -> Settings:
    durable_root = tmp_path / "durable"
    durable_root.mkdir(mode=0o700, parents=True)
    return Settings(
        **artifact_admission_limit_settings(maximum_bytes),
        environment="test",
        artifact_store_backend="local",
        artifact_local_root=durable_root,
        artifact_scratch_root=tmp_path / "scratch",
        artifact_scratch_minimum_free_bytes=0,
    )


def _namespace(settings: Settings) -> ArtifactStorageNamespaceSpec:
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    try:
        return artifact_storage_namespace_spec(settings, bootstrap)
    finally:
        bootstrap.close()


def _context(
    *,
    actor_profile_id: UUID | None = None,
    identity_link_id: UUID | None = None,
    actor_kind: ActorKind = ActorKind.HUMAN,
) -> AuthorizationContext:
    return AuthorizationContext(
        actor_profile_id=actor_profile_id or uuid4(),
        actor_kind=actor_kind,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=identity_link_id or uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )


async def _seed_human_actor(
    session,
    context: AuthorizationContext,
) -> None:
    """Persist the exact active human actor carried by a test context."""
    actor_profile_id = str(context.actor_profile_id)
    if await session.get(ActorProfile, actor_profile_id) is not None:
        return
    session.add(
        ActorProfile(
            id=actor_profile_id,
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            service_identity=None,
            created_by="test",
        )
    )
    await session.flush()
    session.add(
        ActorIdentityLink(
            id=str(context.identity_link_id),
            actor_profile_id=actor_profile_id,
            issuer="https://issuer.example.test",
            subject=f"human-{actor_profile_id}",
            subject_kind="human",
            status="active",
            linked_by="test",
            last_verified_at=datetime.now(UTC),
        )
    )
    await session.flush()


async def _seed_guide(
    session,
    *,
    context: AuthorizationContext,
    content_hash: str,
    media_type: str,
) -> tuple[str, str]:
    await _seed_human_actor(session, context)
    captured_by = str(context.actor_profile_id)
    project_id = str(uuid4())
    guide_id = str(uuid4())
    snapshot_id = str(uuid4())
    item_id = str(uuid4())
    session.add(
        Project(
            id=project_id,
            name="Admission project",
            slug=f"admission-{project_id}",
        )
    )
    await session.flush()
    session.add(
        ProjectGuide(
            id=guide_id,
            project_id=project_id,
            version="v1",
            status="draft",
            content_markdown="# Guide",
            created_by="test",
        )
    )
    await session.flush()
    session.add(
        GuideSourceSnapshot(
            id=snapshot_id,
            project_id=project_id,
            guide_id=guide_id,
            guide_version="v1",
            manifest_schema_version="v1",
            manifest_json={"items": [item_id]},
            bundle_hash=canonical_json_hash({"items": [item_id]}),
            captured_by=captured_by,
        )
    )
    await session.flush()
    session.add(
        GuideSourceSnapshotItem(
            id=item_id,
            source_snapshot_id=snapshot_id,
            item_order=0,
            source_kind="inline",
            durable_ref="guide.md",
            ingestion_adapter="inline",
            content_hash=content_hash,
            media_type=media_type,
        )
    )
    await session.commit()
    return project_id, item_id


async def _seed_contributor_items(
    session,
    *,
    context: AuthorizationContext,
    commitments: tuple[tuple[str, int, str], ...],
) -> tuple[str, str, tuple[str, ...]]:
    await _seed_human_actor(session, context)
    actor_profile_id = str(context.actor_profile_id)
    project_id = str(uuid4())
    task_id = str(uuid4())
    upload_session_id = str(uuid4())
    session.add(
        Project(
            id=project_id,
            name="Contributor project",
            slug=f"contributor-{project_id}",
        )
    )
    await session.flush()
    session.add(
        WorkstreamTask(
            id=task_id,
            project_id=project_id,
            title="Admission task",
            description="Prove artifact admission.",
            status="draft",
            created_by="test",
        )
    )
    await session.flush()
    total_bytes = sum(byte_count for _, byte_count, _ in commitments)
    session.add(
        ArtifactUploadSession(
            id=upload_session_id,
            actor_id=actor_profile_id,
            project_id=project_id,
            task_id=task_id,
            permitted_roles=["submission"],
            state="open",
            maximum_bytes=max(total_bytes, 1),
            current_bytes=0,
            reserved_bytes=total_bytes,
            maximum_items=len(commitments),
            current_items=0,
            reserved_items=len(commitments),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            cas_version=0,
        )
    )
    await session.flush()
    item_ids = []
    for index, (sha256, byte_count, media_type) in enumerate(commitments):
        item_id = str(uuid4())
        item_ids.append(item_id)
        session.add(
            ArtifactUploadItem(
                id=item_id,
                session_id=upload_session_id,
                logical_role=f"submission-{index}",
                display_name=f"result-{index}.bin",
                media_type=media_type,
                reserved_bytes=byte_count,
                expected_sha256=sha256,
                expected_size=byte_count,
                idempotency_key=f"put-{item_id}",
                request_digest=canonical_json_hash(
                    {
                        "sha256": sha256,
                        "byte_count": byte_count,
                        "media_type": media_type,
                    }
                ),
                state="reserved",
                cas_version=0,
            )
        )
    await session.commit()
    return project_id, task_id, tuple(item_ids)


async def _seed_checker_output_relationships(session) -> tuple[str, str, str]:
    """Persist one complete checker-run ownership chain for admission proof."""
    project_id = str(uuid4())
    guide_id = str(uuid4())
    snapshot_id = str(uuid4())
    submission_policy_id = str(uuid4())
    effective_policy_id = str(uuid4())
    pre_submit_policy_id = str(uuid4())
    post_submit_policy_id = str(uuid4())
    task_id = str(uuid4())
    submission_id = str(uuid4())
    contributor_id = str(uuid4())
    contributor_link_id = str(uuid4())
    checker_run_id = str(uuid4())
    guide_version = "v1"
    snapshot_hash = canonical_json_hash({"items": []})
    submission_policy_body = {"required_artifacts": []}
    submission_policy_hash = canonical_json_hash(submission_policy_body)
    effective_policy_body = {"required_artifacts": [], "artifact_hash_algorithm": "sha256"}
    effective_policy_hash = canonical_json_hash(effective_policy_body)
    pre_submit_bundle = {"schema_version": "v1", "rules": []}
    pre_submit_bundle_hash = canonical_json_hash(pre_submit_bundle)
    post_submit_policy_body = {"required_checkers": []}
    post_submit_policy_hash = canonical_json_hash(post_submit_policy_body)
    now = datetime.now(UTC)

    session.add(Project(id=project_id, name="Checker project", slug=f"checker-{project_id}"))
    await session.flush()
    session.add(
        ProjectGuide(
            id=guide_id,
            project_id=project_id,
            version=guide_version,
            status="active",
            content_markdown="# Checker guide",
            approved_by="setup-actor",
            effective_at=now,
            created_by="setup-actor",
        )
    )
    await session.flush()
    session.add(
        GuideSourceSnapshot(
            id=snapshot_id,
            project_id=project_id,
            guide_id=guide_id,
            guide_version=guide_version,
            manifest_schema_version="v1",
            manifest_json={"items": []},
            bundle_hash=snapshot_hash,
            captured_by="setup-actor",
        )
    )
    await session.flush()
    session.add(
        SubmissionArtifactPolicy(
            id=submission_policy_id,
            project_id=project_id,
            guide_id=guide_id,
            guide_version=guide_version,
            source_snapshot_id=snapshot_id,
            source_snapshot_hash=snapshot_hash,
            policy_version="v1",
            lifecycle_status="approved",
            policy_body=submission_policy_body,
            policy_hash=submission_policy_hash,
            derivation_source="test",
            source_material_refs=[],
            created_by="setup-actor",
            approved_by_role="admin",
            approved_by_actor="setup-actor",
            approved_at=now,
        )
    )
    await session.flush()
    session.add(
        EffectiveProjectSubmissionArtifactPolicy(
            id=effective_policy_id,
            project_id=project_id,
            guide_id=guide_id,
            guide_version=guide_version,
            source_snapshot_id=snapshot_id,
            source_snapshot_hash=snapshot_hash,
            submission_artifact_policy_id=submission_policy_id,
            submission_artifact_policy_hash=submission_policy_hash,
            lifecycle_status="approved",
            merge_algorithm_version="v1",
            effective_policy=effective_policy_body,
            effective_policy_hash=effective_policy_hash,
            created_by="setup-actor",
        )
    )
    await session.flush()
    session.add(
        PreSubmitCheckerPolicy(
            id=pre_submit_policy_id,
            project_id=project_id,
            guide_id=guide_id,
            guide_version=guide_version,
            source_snapshot_id=snapshot_id,
            source_snapshot_hash=snapshot_hash,
            effective_policy_id=effective_policy_id,
            effective_policy_hash=effective_policy_hash,
            lifecycle_status="compiled",
            compiler_version="v1",
            compiled_bundle=pre_submit_bundle,
            compiled_bundle_hash=pre_submit_bundle_hash,
            checker_names=[],
            checker_configs={},
            created_by="setup-actor",
        )
    )
    await session.flush()
    session.add_all(
        [
            PostSubmitCheckerPolicy(
                id=post_submit_policy_id,
                project_id=project_id,
                guide_id=guide_id,
                guide_version=guide_version,
                source_snapshot_id=snapshot_id,
                source_snapshot_hash=snapshot_hash,
                effective_policy_id=effective_policy_id,
                effective_policy_hash=effective_policy_hash,
                pre_submit_checker_policy_id=pre_submit_policy_id,
                pre_submit_checker_bundle_hash=pre_submit_bundle_hash,
                required_checkers=[],
                warning_checkers=[],
                blocking_severities=["error"],
                policy_hash=post_submit_policy_hash,
                policy_body=post_submit_policy_body,
                lifecycle_status="approved",
                approved_by_role="admin",
                approved_by_actor="setup-actor",
                approved_at=now,
                created_by="setup-actor",
            ),
            ReviewPolicy(
                id=str(uuid4()),
                project_id=project_id,
                guide_version=guide_version,
                requires_second_review=False,
                allowed_decisions=["accept", "needs_revision", "reject"],
                minimum_finding_fields=[],
            ),
            RevisionPolicy(
                id=str(uuid4()),
                project_id=project_id,
                guide_version=guide_version,
                max_revision_rounds=1,
                revision_deadline_hours=24,
                auto_reject_after_limit=True,
                allowed_resubmission_states=["needs_revision"],
            ),
            PaymentPolicy(
                id=str(uuid4()),
                project_id=project_id,
                guide_version=guide_version,
            ),
        ]
    )
    await session.flush()
    session.add(
        WorkstreamTask(
            id=task_id,
            project_id=project_id,
            locked_guide_version=guide_version,
            locked_post_submit_checker_policy_id=post_submit_policy_id,
            locked_post_submit_checker_policy_version=guide_version,
            locked_post_submit_checker_policy_hash=post_submit_policy_hash,
            locked_post_submit_checker_policy_body=post_submit_policy_body,
            locked_review_policy_version=guide_version,
            locked_revision_policy_version=guide_version,
            locked_payment_policy_version=guide_version,
            locked_guide_source_snapshot_id=snapshot_id,
            locked_guide_source_snapshot_hash=snapshot_hash,
            locked_effective_project_submission_artifact_policy_id=effective_policy_id,
            locked_effective_project_submission_artifact_policy_hash=effective_policy_hash,
            locked_pre_submit_checker_policy_id=pre_submit_policy_id,
            locked_pre_submit_checker_bundle_hash=pre_submit_bundle_hash,
            title="Checker admission task",
            description="Prove checker output admission.",
            status="draft",
            created_by="setup-actor",
        )
    )
    await session.flush()
    session.add(
        ActorProfile(
            id=contributor_id,
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            service_identity=None,
            created_by="test",
        )
    )
    await session.flush()
    session.add(
        ActorIdentityLink(
            id=contributor_link_id,
            actor_profile_id=contributor_id,
            issuer="https://issuer.example.test",
            subject=f"human-{contributor_id}",
            subject_kind="human",
            status="active",
            linked_by="test",
            last_verified_at=now,
        )
    )
    await session.flush()
    session.add(
        Submission(
            id=submission_id,
            task_id=task_id,
            contributor_id=contributor_id,
            version=1,
            status="submitted",
            summary="Checker source submission",
            package_hash=canonical_json_hash({"submission": submission_id}),
            artifact_hash_manifest=[],
            worker_attestation="complete",
            locked_guide_version=guide_version,
            locked_post_submit_checker_policy_id=post_submit_policy_id,
            locked_post_submit_checker_policy_version=guide_version,
            locked_post_submit_checker_policy_hash=post_submit_policy_hash,
            locked_post_submit_checker_policy_body=post_submit_policy_body,
            locked_review_policy_version=guide_version,
            locked_revision_policy_version=guide_version,
            locked_payment_policy_version=guide_version,
            locked_guide_source_snapshot_id=snapshot_id,
            locked_guide_source_snapshot_hash=snapshot_hash,
            locked_effective_project_submission_artifact_policy_id=effective_policy_id,
            locked_effective_project_submission_artifact_policy_hash=effective_policy_hash,
            locked_pre_submit_checker_policy_id=pre_submit_policy_id,
            locked_pre_submit_checker_bundle_hash=pre_submit_bundle_hash,
        )
    )
    await session.flush()
    session.add(
        CheckerRun(
            id=checker_run_id,
            task_id=task_id,
            submission_id=submission_id,
            submission_version=1,
            trigger_source="submission_finalized",
            status="queued",
            routing_recommendation="not_evaluated",
            outcome_source="none",
            triggered_by="setup-actor",
            triggered_by_subject="setup-subject",
            triggered_by_issuer="https://issuer.example.test",
            trigger_auth_source="test",
            attempt_number=1,
            is_current_for_submission=True,
            locked_guide_version=guide_version,
            locked_post_submit_checker_policy_id=post_submit_policy_id,
            locked_post_submit_checker_policy_version=guide_version,
            locked_post_submit_checker_policy_hash=post_submit_policy_hash,
            locked_post_submit_checker_policy_body=post_submit_policy_body,
            locked_review_policy_version=guide_version,
            locked_revision_policy_version=guide_version,
            locked_payment_policy_version=guide_version,
            package_hash=canonical_json_hash({"submission": submission_id}),
            artifact_hash_manifest=[],
            artifact_manifest_hash=canonical_json_hash([]),
        )
    )
    await session.commit()
    return project_id, task_id, checker_run_id


async def _count(session, model: type) -> int:
    value = await session.scalar(select(func.count()).select_from(model))
    assert value is not None
    return value


async def _admit_guide_source(session, settings, namespace, context, source):
    """Create one guide attempt for execution/fencing tests."""
    _, guide_item_id = await _seed_guide(
        session,
        context=context,
        content_hash=source.commitment.sha256,
        media_type=source.commitment.media_type,
    )
    return await ArtifactAdmissionService(session, settings, namespace).admit(
        GuideArtifactAdmissionRequest(
            authorization_context=context,
            guide_source_item_id=UUID(guide_item_id),
            source=source,
        )
    )


async def test_committed_put_and_independent_verification_are_fenced(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    authority = _AllowArtifactAuthority()
    try:
        async with factory() as session:
            async with minted_source(
                tmp_path / "fenced-guide-source",
                b"independently verified bytes",
                media_type="text/plain",
            ) as source:
                _, guide_item_id = await _seed_guide(
                    session,
                    context=context,
                    content_hash=source.commitment.sha256,
                    media_type=source.commitment.media_type,
                )
                admission = await ArtifactAdmissionService(session, settings, namespace).admit(
                    GuideArtifactAdmissionRequest(
                        authorization_context=context,
                        guide_source_item_id=UUID(guide_item_id),
                        source=source,
                    )
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, authority
                )
                assert (await orchestrator.ensure_storage_namespace()).id == "primary"
                assert (
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                    == "stored_pending_verification"
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.status == "object_confirmed"
                assert attempt.executor_id is None
                assert attempt.execution_generation == 1
                job = await session.scalar(
                    select(ArtifactVerificationJob).where(
                        ArtifactVerificationJob.originating_put_attempt_id == attempt.id
                    )
                )
                assert job is not None
                job_id = UUID(job.id)
                await session.rollback()
                assert await orchestrator.verify_object(job_id) == "verified"
                await session.refresh(job)
                assert job.status == "verified"
                assert job.executor_id is None
                assert job.execution_generation == 1
                replica = await session.get(ArtifactReplica, job.replica_id)
                assert replica is not None
                assert (
                    replica.verification_state,
                    replica.availability_state,
                    replica.integrity_state,
                ) == ("verified", "available", "valid")
                assert await _count(session, ArtifactOperationReceipt) == 1
                assert await _count(session, ArtifactVerificationReceipt) == 1
                await session.rollback()
                assert await orchestrator.verify_object(job_id) == "stale"
                assert authority.preflights == 3
                assert authority.terminals == 2
                for operation in ("update", "delete"):
                    statement = (
                        "update artifact_verification_receipts set execution_generation = "
                        "execution_generation + 1"
                        if operation == "update"
                        else "delete from artifact_verification_receipts"
                    )
                    with pytest.raises(DBAPIError):
                        async with factory() as mutation_session, mutation_session.begin():
                            await mutation_session.execute(text(statement))
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_every_provider_operation_revalidates_namespace_before_io(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )

    class DriftStore:
        identity = replace(store.identity, provider_key="drift")

        async def put(self, _source):
            raise AssertionError("put must not run after namespace drift")

        async def observe_put_result(self, _commitment):
            raise AssertionError("observation must not run after namespace drift")

        def open(self, _provider_object_ref):
            raise AssertionError("read must not run after namespace drift")

    try:
        async with factory() as session:
            async with minted_source(tmp_path / "namespace-fence", b"fenced") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                drifted = ArtifactStorageOrchestrator(
                    session, DriftStore(), namespace, settings, _AllowArtifactAuthority()
                )
                with pytest.raises(ArtifactStorageNamespaceError):
                    await drifted.execute_committed_put(
                        attempt_id=admission.attempt_id, source=source
                    )
                with pytest.raises(ArtifactStorageNamespaceError):
                    await drifted.resolve_put_attempt(admission.attempt_id)

                real = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await real.execute_committed_put(attempt_id=admission.attempt_id, source=source)
                job = await session.scalar(select(ArtifactVerificationJob))
                assert job is not None
                replica = await session.get(ArtifactReplica, job.replica_id)
                assert replica is not None
                replica.adapter = "drift"
                await session.commit()
                with pytest.raises(ArtifactStorageNamespaceError):
                    await real.verify_object(UUID(job.id))
                await session.refresh(job)
                assert job.status == "pending"
                assert await _count(session, ArtifactVerificationReceipt) == 0
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_preacknowledgement_absence_releases_capacity_without_write(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    authority = _AllowArtifactAuthority()
    try:
        async with factory() as session:
            async with minted_source(
                tmp_path / "missing-guide-source",
                b"provider object is deliberately absent",
                media_type="text/plain",
            ) as source:
                _, guide_item_id = await _seed_guide(
                    session,
                    context=context,
                    content_hash=source.commitment.sha256,
                    media_type=source.commitment.media_type,
                )
                admission = await ArtifactAdmissionService(session, settings, namespace).admit(
                    GuideArtifactAdmissionRequest(
                        authorization_context=context,
                        guide_source_item_id=UUID(guide_item_id),
                        source=source,
                    )
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, authority
                )
                assert await orchestrator.resolve_put_attempt(admission.attempt_id) == "missing"
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.status == "absent_replay_required"
                assert attempt.observation_count == 1
                charges = (await session.execute(select(ArtifactAdmissionCharge))).scalars().all()
                scopes = (await session.execute(select(ArtifactAdmissionScope))).scalars().all()
                assert charges and {charge.state for charge in charges} == {"released"}
                assert scopes and {scope.counted_bytes for scope in scopes} == {0}
                assert await _count(session, ArtifactPutObservationReceipt) == 1
                assert await _count(session, ArtifactOperationReceipt) == 0
                assert authority.preflights == 1
                assert authority.terminals == 1
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_preacknowledgement_mismatch_fails_contributor_item_and_keeps_charge(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    authority = _AllowArtifactAuthority()
    try:
        async with factory() as session:
            async with minted_source(
                tmp_path / "mismatch-contributor-source",
                b"expected immutable bytes",
                media_type="text/plain",
            ) as source:
                _, _, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(
                        (
                            source.commitment.sha256,
                            source.commitment.byte_count,
                            source.commitment.media_type,
                        ),
                    ),
                )
                admission = await ArtifactAdmissionService(session, settings, namespace).admit(
                    ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[0]),
                        source=source,
                    )
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                prefix, filename = attempt.canonical_target.removeprefix("sha256/").split("/")
                provider_path = settings.artifact_local_root / "objects" / "sha256" / prefix
                provider_path.mkdir(mode=0o700)
                corrupt_object = provider_path / filename
                corrupt_object.write_bytes(b"different provider bytes")
                corrupt_object.chmod(0o400)
                await session.rollback()
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, authority
                )
                assert (
                    await orchestrator.resolve_put_attempt(admission.attempt_id)
                    == "integrity_mismatch"
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.status == "integrity_mismatch"
                assert attempt.replica_id is not None
                replica = await session.get(ArtifactReplica, attempt.replica_id)
                assert replica is not None
                assert (
                    replica.verification_state,
                    replica.availability_state,
                    replica.integrity_state,
                ) == ("integrity_mismatch", "available", "invalid")
                charges = (await session.execute(select(ArtifactAdmissionCharge))).scalars().all()
                assert charges and {charge.state for charge in charges} == {"completed"}
                item = await session.get(ArtifactUploadItem, item_ids[0])
                assert item is not None
                assert item.state == "failed"
                assert item.error_code == "artifact_integrity_failure"
                assert item.cas_version == 1
                assert await _count(session, ArtifactPutObservationReceipt) == 1
                assert await _count(session, ArtifactOperationReceipt) == 0
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_simultaneous_put_claims_have_one_generation_winner(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as seed_session:
            async with minted_source(tmp_path / "simultaneous", b"claim once") as source:
                admission = await _admit_guide_source(
                    seed_session, settings, namespace, _context(), source
                )

        async def claim(executor_id: UUID):
            async with factory() as claim_session, claim_session.begin():
                return await ArtifactRepository(claim_session).claim_put_attempt(
                    attempt_id=admission.attempt_id,
                    executor_id=executor_id,
                    lease_seconds=30,
                    mode="observation",
                    expected_generation=0,
                )

        first, second = await asyncio.gather(claim(uuid4()), claim(uuid4()))
        winners = [result for result in (first, second) if result is not None]
        assert len(winners) == 1
        assert winners[0].execution_generation == 1
        async with factory() as check_session:
            attempt = await check_session.get(ArtifactPutAttempt, str(admission.attempt_id))
            assert attempt is not None
            assert attempt.status == "put_in_flight"
            assert attempt.execution_generation == 1
            assert await _count(check_session, ArtifactPutObservationReceipt) == 0
            assert await _count(check_session, ArtifactReplica) == 0
    finally:
        await engine.dispose()


async def test_expired_lease_takeover_rejects_stale_terminal_completion(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_executor = uuid4()
    second_executor = uuid4()
    try:
        async with factory() as seed_session:
            async with minted_source(tmp_path / "takeover", b"take over") as source:
                admission = await _admit_guide_source(
                    seed_session, settings, namespace, _context(), source
                )
        async with factory() as first_session, first_session.begin():
            first_claim = await ArtifactRepository(first_session).claim_put_attempt(
                attempt_id=admission.attempt_id,
                executor_id=first_executor,
                lease_seconds=30,
                mode="observation",
                expected_generation=0,
            )
            assert first_claim is not None
        async with factory() as expire_session, expire_session.begin():
            await expire_session.execute(
                text(
                    "update artifact_put_attempts "
                    "set lease_expires_at = clock_timestamp() - interval '1 second' where id = :id"
                ),
                {"id": str(admission.attempt_id)},
            )
        async with factory() as second_session, second_session.begin():
            second_claim = await ArtifactRepository(second_session).claim_put_attempt(
                attempt_id=admission.attempt_id,
                executor_id=second_executor,
                lease_seconds=30,
                mode="observation",
                expected_generation=1,
            )
            assert second_claim is not None
            assert second_claim.execution_generation == 2
        async with factory() as stale_session:
            stale = ArtifactStorageOrchestrator(
                stale_session, object(), namespace, settings, _AllowArtifactAuthority()
            )
            assert await stale._record_put_absence(first_claim, first_executor) == "stale"
            attempt = await stale_session.get(ArtifactPutAttempt, str(admission.attempt_id))
            assert attempt is not None
            assert attempt.execution_generation == 2
            assert attempt.executor_id == str(second_executor)
            assert await _count(stale_session, ArtifactPutObservationReceipt) == 0
            assert await _count(stale_session, ArtifactReplica) == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "revocation_kind",
    ["actor_suspended", "link_revoked"],
)
async def test_terminal_authority_revocation_writes_zero_terminal_facts(
    admission_database_env: str,
    tmp_path: Path,
    revocation_kind: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(
                tmp_path / revocation_kind, revocation_kind.encode()
            ) as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session,
                    store,
                    namespace,
                    settings,
                    _RevokeTerminalArtifactAuthority(
                        reason=revocation_kind,
                        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                        action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                        resource_type=ArtifactInternalResourceType.PUT_ATTEMPT,
                    ),
                )
                with pytest.raises(ArtifactAuthorityDeniedError, match=revocation_kind):
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.status == "put_in_flight"
                assert attempt.terminal_at is None
                assert attempt.terminal_result_code is None
                assert await _count(session, ArtifactOperationReceipt) == 0
                assert await _count(session, ArtifactPutObservationReceipt) == 0
                assert await _count(session, ArtifactVerificationReceipt) == 0
                assert await _count(session, ArtifactReplica) == 0
                assert await _count(session, ArtifactVerificationJob) == 0
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_put_observation_unavailable_retries_then_exhausts_without_facts(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"artifact_provider_observation_maximum_attempts": 2}
    )
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    class UnavailableObservationStore:
        identity = SimpleNamespace(provider_key=namespace.adapter)

        async def observe_put_result(self, _commitment):
            raise ArtifactStoreUnavailableError("provider unavailable")

    try:
        async with factory() as session:
            async with minted_source(tmp_path / "put-unavailable", b"observe") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session,
                    UnavailableObservationStore(),
                    namespace,
                    settings,
                    _AllowArtifactAuthority(),
                )
                assert (
                    await orchestrator.resolve_put_attempt(admission.attempt_id)
                    == "acknowledgement_unknown"
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.observation_count == 1
                assert attempt.next_run_at is not None
                assert attempt.terminal_at is None
                assert attempt.executor_id is None
                charges = (await session.execute(select(ArtifactAdmissionCharge))).scalars().all()
                assert charges and {charge.state for charge in charges} == {"provisional"}
                await session.execute(
                    text(
                        "update artifact_put_attempts set next_run_at = "
                        "clock_timestamp() - interval '1 second' where id = :id"
                    ),
                    {"id": attempt.id},
                )
                await session.commit()
                assert (
                    await orchestrator.resolve_put_attempt(admission.attempt_id)
                    == "provider_unavailable"
                )
                await session.refresh(attempt)
                assert attempt.observation_count == 2
                assert attempt.next_run_at is None
                assert attempt.terminal_at is not None
                assert attempt.terminal_result_code == "provider_unavailable"
                assert attempt.executor_id is None
                assert await _count(session, ArtifactOperationReceipt) == 0
                assert await _count(session, ArtifactPutObservationReceipt) == 0
                assert await _count(session, ArtifactReplica) == 0
                assert await _count(session, ArtifactVerificationJob) == 0
    finally:
        await engine.dispose()


async def test_scanner_uses_due_time_page_bound_and_duplicate_publication(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path).model_copy(update={"artifact_pending_work_scan_page_size": 2})
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    attempt_ids: list[str] = []
    try:
        async with factory() as session:
            for index in range(3):
                async with minted_source(
                    tmp_path / f"scan-{index}", f"scan-{index}".encode()
                ) as source:
                    admission = await _admit_guide_source(
                        session, settings, namespace, _context(), source
                    )
                    attempt_ids.append(str(admission.attempt_id))
            await session.execute(
                text(
                    "update artifact_put_attempts set prepared_at = "
                    "clock_timestamp() - interval '30 seconds' where id = :id"
                ),
                {"id": attempt_ids[0]},
            )
            await session.execute(
                text(
                    "update artifact_put_attempts set status = 'acknowledgement_unknown', "
                    "next_run_at = clock_timestamp() - interval '20 seconds' where id = :id"
                ),
                {"id": attempt_ids[1]},
            )
            await session.execute(
                text(
                    "update artifact_put_attempts set status = 'put_in_flight', "
                    "executor_id = :executor, execution_mode = 'observation', "
                    "lease_expires_at = clock_timestamp() - interval '10 seconds' where id = :id"
                ),
                {"id": attempt_ids[2], "executor": str(uuid4())},
            )
            await session.commit()
            published: list[str] = []

            async def publish_put(attempt_id: str) -> None:
                published.append(attempt_id)

            async def publish_job(_job_id: str) -> None:
                raise AssertionError("no verification job should be published")

            scanner = ArtifactPendingWorkScanner(
                session,
                settings,
                _AllowArtifactAuthority(),
                publish_put,
                publish_job,
            )
            assert await scanner.scan() == 2
            assert published == attempt_ids[:2]
            assert await scanner.scan() == 2
            assert published == attempt_ids[:2] * 2

            async def fail_publication(_attempt_id: str) -> None:
                raise RuntimeError("broker unavailable")

            failing_scanner = ArtifactPendingWorkScanner(
                session,
                settings,
                _AllowArtifactAuthority(),
                fail_publication,
                publish_job,
            )
            with pytest.raises(RuntimeError, match="broker unavailable"):
                await failing_scanner.scan()
            assert await scanner.scan() == 2
            assert published == attempt_ids[:2] * 3
            states = (
                (
                    await session.execute(
                        select(ArtifactPutAttempt.status)
                        .where(ArtifactPutAttempt.id.in_(attempt_ids))
                        .order_by(ArtifactPutAttempt.id)
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(states) == ["acknowledgement_unknown", "prepared", "put_in_flight"]
    finally:
        await engine.dispose()


async def test_acknowledgement_loss_is_observed_without_second_put(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "ack-loss", b"ack was lost") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                await store.put(source)
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                assert (
                    await orchestrator.resolve_put_attempt(admission.attempt_id)
                    == "observed_confirmed"
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.status == "object_confirmed"
                assert attempt.terminal_result_code == "observed_confirmed"
                assert await _count(session, ArtifactPutObservationReceipt) == 1
                assert await _count(session, ArtifactOperationReceipt) == 0
                assert await _count(session, ArtifactVerificationJob) == 1
                for operation in ("update", "delete"):
                    statement = (
                        "update artifact_put_observation_receipts set execution_generation = "
                        "execution_generation + 1"
                        if operation == "update"
                        else "delete from artifact_put_observation_receipts"
                    )
                    with pytest.raises(DBAPIError):
                        async with factory() as mutation_session, mutation_session.begin():
                            await mutation_session.execute(text(statement))
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_verification_claim_takeover_and_scanner_due_order_are_fenced(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path).model_copy(update={"artifact_pending_work_scan_page_size": 2})
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        job_ids: list[str] = []
        async with factory() as seed_session:
            orchestrator = ArtifactStorageOrchestrator(
                seed_session, store, namespace, settings, _AllowArtifactAuthority()
            )
            for index in range(3):
                async with minted_source(
                    tmp_path / f"verification-scan-{index}", f"job-{index}".encode()
                ) as source:
                    admission = await _admit_guide_source(
                        seed_session, settings, namespace, _context(), source
                    )
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id, source=source
                    )
            job_ids = list(
                (
                    await seed_session.execute(
                        select(ArtifactVerificationJob.id).order_by(
                            ArtifactVerificationJob.created_at,
                            ArtifactVerificationJob.id,
                        )
                    )
                ).scalars()
            )
            await seed_session.rollback()

        first_executor = uuid4()
        async with factory() as claim_session, claim_session.begin():
            first_claim = await ArtifactRepository(claim_session).claim_verification_job(
                job_id=UUID(job_ids[2]),
                executor_id=first_executor,
                lease_seconds=30,
                expected_generation=0,
            )
            assert first_claim is not None
        async with factory() as expire_session, expire_session.begin():
            await expire_session.execute(
                text(
                    "update artifact_verification_jobs set lease_expires_at = "
                    "clock_timestamp() - interval '10 seconds' where id = :id"
                ),
                {"id": job_ids[2]},
            )
            await expire_session.execute(
                text(
                    "update artifact_verification_jobs set status = 'provider_unavailable', "
                    "attempt_count = 1, next_run_at = clock_timestamp() - interval '20 seconds' "
                    "where id = :id"
                ),
                {"id": job_ids[1]},
            )
            await expire_session.execute(
                text(
                    "update artifact_verification_jobs set created_at = "
                    "clock_timestamp() - interval '30 seconds' where id = :id"
                ),
                {"id": job_ids[0]},
            )
        async with factory() as due_session:
            due_ids = await ArtifactRepository(due_session).list_due_verification_job_ids(
                cutoff=datetime.now(UTC), limit=3
            )
            assert due_ids == tuple(job_ids)
        second_executor = uuid4()
        async with factory() as takeover_session, takeover_session.begin():
            takeover = await ArtifactRepository(takeover_session).claim_verification_job(
                job_id=UUID(job_ids[2]),
                executor_id=second_executor,
                lease_seconds=30,
                expected_generation=1,
            )
            assert takeover is not None and takeover.execution_generation == 2
        async with factory() as facts_session:
            facts_repo = ArtifactRepository(facts_session)
            first_replica = await facts_repo.lock_replica(first_claim.replica_id)
            first_attempt = await facts_repo.lock_put_attempt(
                first_claim.originating_put_attempt_id
            )
            assert first_replica is not None and first_attempt is not None
            first_facts = _verification_authority_facts(
                first_claim,
                first_replica,
                first_attempt,
                first_executor,
                first_claim.execution_generation,
            )
            await facts_session.rollback()
        async with factory() as stale_session:
            stale = ArtifactStorageOrchestrator(
                stale_session, store, namespace, settings, _AllowArtifactAuthority()
            )
            assert (
                await stale._complete_verification(
                    first_claim,
                    first_executor,
                    first_facts,
                    "verified",
                    "sha256:" + "1" * 64,
                    1,
                )
                == "stale"
            )
            assert await _count(stale_session, ArtifactVerificationReceipt) == 0
            await stale_session.rollback()
            due_ids = await ArtifactRepository(stale_session).list_due_verification_job_ids(
                cutoff=datetime.now(UTC), limit=2
            )
            assert due_ids == tuple(job_ids[:2])
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_caller_replay_reacquires_released_capacity_before_put(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "reacquire", b"replay bytes") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                assert await orchestrator.resolve_put_attempt(admission.attempt_id) == "missing"
                assert (
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                    == "stored_pending_verification"
                )
                charges = (await session.execute(select(ArtifactAdmissionCharge))).scalars().all()
                scopes = (await session.execute(select(ArtifactAdmissionScope))).scalars().all()
                assert charges and {charge.state for charge in charges} == {"completed"}
                assert scopes and all(
                    scope.counted_bytes == source.commitment.byte_count for scope in scopes
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.execution_generation == 2
                assert attempt.status == "object_confirmed"
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_existing_replica_immutable_fact_conflict_is_fenced(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "replica-conflict", b"expected bytes") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await orchestrator.ensure_storage_namespace()
                conflicting_content = ArtifactContent(
                    id=str(uuid4()),
                    sha256="sha256:" + "f" * 64,
                    byte_count=999,
                    media_type="application/octet-stream",
                    normalized_display_name=None,
                )
                session.add(conflicting_content)
                await session.flush()
                conflict_attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert conflict_attempt is not None
                session.add(
                    ArtifactReplica(
                        id=str(uuid4()),
                        content_id=conflicting_content.id,
                        storage_namespace_id="primary",
                        namespace_fingerprint=namespace.namespace_fingerprint,
                        adapter=store.identity.provider_key,
                        provider_profile=namespace.provider_profile,
                        provider_object_ref=conflict_attempt.canonical_target,
                        verification_state="pending",
                        availability_state="unknown",
                        integrity_state="unknown",
                    )
                )
                await session.commit()
                assert (
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                    == "conflict"
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.status == "conflict"
                assert attempt.replica_id is None
                assert await _count(session, ArtifactPutObservationReceipt) == 1
                assert await _count(session, ArtifactOperationReceipt) == 0
                assert await _count(session, ArtifactVerificationJob) == 0
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_verification_resource_drift_returns_stale_without_mutation(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "verification-drift", b"expected") as source:
                _, _, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(
                        (
                            source.commitment.sha256,
                            source.commitment.byte_count,
                            source.commitment.media_type,
                        ),
                    ),
                )
                admission = await ArtifactAdmissionService(session, settings, namespace).admit(
                    ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[0]),
                        source=source,
                    )
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await orchestrator.execute_committed_put(
                    attempt_id=admission.attempt_id, source=source
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                job = await session.scalar(select(ArtifactVerificationJob))
                assert attempt is not None and attempt.replica_id is not None
                assert job is not None
                original_replica_id = attempt.replica_id
                unrelated_content = ArtifactContent(
                    id=str(uuid4()),
                    sha256="sha256:" + "f" * 64,
                    byte_count=999,
                    media_type="application/octet-stream",
                    normalized_display_name=None,
                )
                session.add(unrelated_content)
                await session.flush()
                unrelated_replica = ArtifactReplica(
                    id=str(uuid4()),
                    content_id=unrelated_content.id,
                    storage_namespace_id=attempt.storage_namespace_id,
                    namespace_fingerprint=attempt.namespace_fingerprint,
                    adapter=store.identity.provider_key,
                    provider_profile=namespace.provider_profile,
                    provider_object_ref="sha256/ff/" + "f" * 62,
                    verification_state="pending",
                    availability_state="unknown",
                    integrity_state="unknown",
                )
                session.add(unrelated_replica)
                await session.flush()
                job_id = UUID(job.id)
                await session.commit()

                async def drift_job_after_claim(_provider_object_ref: str):
                    async with factory() as drift_session, drift_session.begin():
                        drifted_job = await drift_session.get(
                            ArtifactVerificationJob, str(job_id), with_for_update=True
                        )
                        assert drifted_job is not None and drifted_job.status == "running"
                        drifted_job.replica_id = unrelated_replica.id
                    return source.commitment.sha256, source.commitment.byte_count

                orchestrator._read_complete = drift_job_after_claim
                assert await orchestrator.verify_object(job_id) == "stale"
                await session.refresh(job)
                await session.refresh(unrelated_replica)
                original_replica = await session.get(ArtifactReplica, original_replica_id)
                item = await session.get(ArtifactUploadItem, item_ids[0])
                assert original_replica is not None and item is not None
                assert job.status == "running"
                assert unrelated_replica.verification_state == "pending"
                assert original_replica.verification_state == "pending"
                assert item.state == "stored_pending_verification"
                assert item.content_id == original_replica.content_id
                receipt = await session.scalar(select(ArtifactVerificationReceipt))
                assert receipt is None
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_verification_rechecks_relationship_after_preflight_before_io(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "preclaim-drift", b"expected") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                allowing = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await allowing.execute_committed_put(attempt_id=admission.attempt_id, source=source)
                job = await session.scalar(select(ArtifactVerificationJob))
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert job is not None and attempt is not None
                unrelated_content = ArtifactContent(
                    id=str(uuid4()),
                    sha256="sha256:" + "e" * 64,
                    byte_count=777,
                    media_type="application/octet-stream",
                    normalized_display_name=None,
                )
                session.add(unrelated_content)
                await session.flush()
                unrelated_replica = ArtifactReplica(
                    id=str(uuid4()),
                    content_id=unrelated_content.id,
                    storage_namespace_id=attempt.storage_namespace_id,
                    namespace_fingerprint=attempt.namespace_fingerprint,
                    adapter=store.identity.provider_key,
                    provider_profile=namespace.provider_profile,
                    provider_object_ref="sha256/ee/" + "e" * 62,
                    verification_state="pending",
                    availability_state="unknown",
                    integrity_state="unknown",
                )
                session.add(unrelated_replica)
                job_id = UUID(job.id)
                await session.commit()

                class DriftBeforeClaimAuthority(_AllowArtifactAuthority):
                    async def preflight(self, **_values: object) -> None:
                        await super().preflight(**_values)
                        async with factory() as drift_session, drift_session.begin():
                            drifted_job = await drift_session.get(
                                ArtifactVerificationJob, str(job_id), with_for_update=True
                            )
                            assert drifted_job is not None and drifted_job.status == "pending"
                            drifted_job.replica_id = unrelated_replica.id

                verifying = ArtifactStorageOrchestrator(
                    session,
                    store,
                    namespace,
                    settings,
                    DriftBeforeClaimAuthority(),
                )
                verifying._read_complete = AsyncMock(
                    side_effect=AssertionError("provider read must not execute")
                )
                assert await verifying.verify_object(job_id) == "stale"
                verifying._read_complete.assert_not_awaited()
                await session.refresh(job)
                await session.refresh(unrelated_replica)
                assert job.status == "pending"
                assert unrelated_replica.verification_state == "pending"
                receipt = await session.scalar(select(ArtifactVerificationReceipt))
                assert receipt is None
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_verification_rechecks_authorized_object_ref_before_io(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "preclaim-object-ref-drift", b"expected") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                allowing = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await allowing.execute_committed_put(attempt_id=admission.attempt_id, source=source)
                job = await session.scalar(select(ArtifactVerificationJob))
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert job is not None and attempt is not None and attempt.replica_id is not None
                job_id = UUID(job.id)
                replica_id = attempt.replica_id
                await session.commit()

                class DriftObjectRefBeforeClaimAuthority(_AllowArtifactAuthority):
                    async def preflight(self, **_values: object) -> None:
                        await super().preflight(**_values)
                        async with factory() as drift_session, drift_session.begin():
                            drifted_replica = await drift_session.get(
                                ArtifactReplica, replica_id, with_for_update=True
                            )
                            assert drifted_replica is not None
                            drifted_replica.provider_object_ref = "sha256/aa/" + "a" * 62

                verifying = ArtifactStorageOrchestrator(
                    session,
                    store,
                    namespace,
                    settings,
                    DriftObjectRefBeforeClaimAuthority(),
                )
                verifying._read_complete = AsyncMock(
                    side_effect=AssertionError("provider read must not execute")
                )
                assert await verifying.verify_object(job_id) == "stale"
                verifying._read_complete.assert_not_awaited()
                await session.refresh(job)
                assert job.status == "pending"
                receipt = await session.scalar(select(ArtifactVerificationReceipt))
                assert receipt is None
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_verification_rechecks_authorized_object_ref_after_io(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "postread-object-ref-drift", b"expected") as source:
                _, _, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(
                        (
                            source.commitment.sha256,
                            source.commitment.byte_count,
                            source.commitment.media_type,
                        ),
                    ),
                )
                admission = await ArtifactAdmissionService(session, settings, namespace).admit(
                    ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[0]),
                        source=source,
                    )
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await orchestrator.execute_committed_put(
                    attempt_id=admission.attempt_id, source=source
                )
                job = await session.scalar(select(ArtifactVerificationJob))
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert job is not None and attempt is not None and attempt.replica_id is not None
                job_id = UUID(job.id)
                replica_id = attempt.replica_id
                await session.commit()

                async def drift_object_ref_during_read(_provider_object_ref: str):
                    async with factory() as drift_session, drift_session.begin():
                        drifted_replica = await drift_session.get(
                            ArtifactReplica, replica_id, with_for_update=True
                        )
                        assert drifted_replica is not None
                        drifted_replica.provider_object_ref = "sha256/bb/" + "b" * 62
                    return source.commitment.sha256, source.commitment.byte_count

                orchestrator._read_complete = drift_object_ref_during_read
                assert await orchestrator.verify_object(job_id) == "stale"
                await session.refresh(job)
                replica = await session.get(ArtifactReplica, replica_id)
                item = await session.get(ArtifactUploadItem, item_ids[0])
                assert replica is not None and item is not None
                assert job.status == "running"
                assert replica.verification_state == "pending"
                assert item.state == "stored_pending_verification"
                assert await session.scalar(select(func.count(ArtifactVerificationReceipt.id))) == 0
    finally:
        bootstrap.close()
        await engine.dispose()


@pytest.mark.parametrize("bound", [False, True])
async def test_post_ack_missing_replays_only_unbound_contributor_item(
    admission_database_env: str,
    tmp_path: Path,
    bound: bool,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / f"missing-{bound}", b"contributor") as source:
                project_id, task_id, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(
                        (
                            source.commitment.sha256,
                            source.commitment.byte_count,
                            source.commitment.media_type,
                        ),
                    ),
                )
                admission = await ArtifactAdmissionService(session, settings, namespace).admit(
                    ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[0]),
                        source=source,
                    )
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                assert (
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                    == "stored_pending_verification"
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None and attempt.replica_id is not None
                replica = await session.get(ArtifactReplica, attempt.replica_id)
                assert replica is not None
                if bound:
                    session.add(
                        ArtifactBinding(
                            id=str(uuid4()),
                            content_id=replica.content_id,
                            project_id=project_id,
                            resource_type="task",
                            resource_id=task_id,
                            logical_role="submission",
                            scope_version=1,
                            actor_id=str(context.actor_profile_id),
                            attribution_type="human",
                            supersedes_binding_id=None,
                        )
                    )
                    await session.commit()
                job = await session.scalar(
                    select(ArtifactVerificationJob).where(
                        ArtifactVerificationJob.originating_put_attempt_id == attempt.id
                    )
                )
                assert job is not None
                job_id = UUID(job.id)
                await session.rollback()
                orchestrator._read_complete = AsyncMock(
                    side_effect=ArtifactObjectMissingError("missing")
                )
                assert await orchestrator.verify_object(job_id) == "missing"
                item = await session.get(ArtifactUploadItem, item_ids[0])
                assert item is not None
                assert item.state == ("stored_pending_verification" if bound else "replay_required")
                assert (item.content_id is not None) is bound
                assert (item.provider_object_ref is not None) is bound
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_missing_transition_serializes_concurrent_binding_insert(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    content_locked = asyncio.Event()
    allow_missing_completion = asyncio.Event()
    binding_flush_started = asyncio.Event()

    class PausingContentLockRepository(ArtifactRepository):
        async def lock_content(self, content_id: str):
            content = await super().lock_content(content_id)
            content_locked.set()
            await allow_missing_completion.wait()
            return content

    try:
        async with factory() as session:
            async with minted_source(tmp_path / "binding-race", b"serialize") as source:
                project_id, task_id, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(
                        (
                            source.commitment.sha256,
                            source.commitment.byte_count,
                            source.commitment.media_type,
                        ),
                    ),
                )
                admission = await ArtifactAdmissionService(session, settings, namespace).admit(
                    ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[0]),
                        source=source,
                    )
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await orchestrator.execute_committed_put(
                    attempt_id=admission.attempt_id, source=source
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None and attempt.replica_id is not None
                replica = await session.get(ArtifactReplica, attempt.replica_id)
                assert replica is not None
                content_id = replica.content_id
                job = await session.scalar(select(ArtifactVerificationJob))
                assert job is not None
                job_id = UUID(job.id)
                await session.rollback()
                orchestrator._repo = PausingContentLockRepository(session)
                orchestrator._read_complete = AsyncMock(
                    side_effect=ArtifactObjectMissingError("missing")
                )
                verification = asyncio.create_task(orchestrator.verify_object(job_id))
                await asyncio.wait_for(content_locked.wait(), timeout=2)

                async def insert_binding() -> None:
                    async with factory() as binding_session, binding_session.begin():
                        binding_session.add(
                            ArtifactBinding(
                                id=str(uuid4()),
                                content_id=content_id,
                                project_id=project_id,
                                resource_type="task",
                                resource_id=task_id,
                                logical_role="submission",
                                scope_version=1,
                                actor_id=str(context.actor_profile_id),
                                attribution_type="human",
                                supersedes_binding_id=None,
                            )
                        )
                        binding_flush_started.set()
                        await binding_session.flush()

                binding_insert = asyncio.create_task(insert_binding())
                await asyncio.wait_for(binding_flush_started.wait(), timeout=2)
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(binding_insert), timeout=0.2)
                allow_missing_completion.set()
                assert await verification == "missing"
                await asyncio.wait_for(binding_insert, timeout=2)
                item = await session.get(ArtifactUploadItem, item_ids[0])
                assert item is not None and item.state == "replay_required"
                assert await _count(session, ArtifactBinding) == 1
    finally:
        allow_missing_completion.set()
        bootstrap.close()
        await engine.dispose()


@pytest.mark.parametrize(
    ("provider_result", "expected"),
    [
        (("sha256:" + "e" * 64, 7), "integrity_mismatch"),
        (ArtifactStoreError("conflict"), "conflict"),
    ],
)
async def test_verification_terminal_result_matrix(
    admission_database_env: str,
    tmp_path: Path,
    provider_result: tuple[str, int] | Exception,
    expected: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / expected, b"verification matrix") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await orchestrator.execute_committed_put(
                    attempt_id=admission.attempt_id, source=source
                )
                job = await session.scalar(select(ArtifactVerificationJob))
                assert job is not None
                job_id = UUID(job.id)
                await session.rollback()
                orchestrator._read_complete = (
                    AsyncMock(side_effect=provider_result)
                    if isinstance(provider_result, Exception)
                    else AsyncMock(return_value=provider_result)
                )
                assert await orchestrator.verify_object(job_id) == expected
                await session.refresh(job)
                replica = await session.get(ArtifactReplica, job.replica_id)
                assert replica is not None
                assert job.status == expected
                assert replica.verification_state == (
                    "integrity_mismatch" if expected == "integrity_mismatch" else "pending"
                )
                assert await _count(session, ArtifactVerificationReceipt) == 1
    finally:
        bootstrap.close()
        await engine.dispose()


@pytest.mark.parametrize("denial_reason", ["actor_deactivated", "resource_drift"])
async def test_verification_terminal_authority_denial_writes_zero_result_facts(
    admission_database_env: str,
    tmp_path: Path,
    denial_reason: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(
                tmp_path / f"verify-{denial_reason}", denial_reason.encode()
            ) as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                allowing = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await allowing.execute_committed_put(attempt_id=admission.attempt_id, source=source)
                job = await session.scalar(select(ArtifactVerificationJob))
                assert job is not None
                job_id = UUID(job.id)
                await session.rollback()
                denying = ArtifactStorageOrchestrator(
                    session,
                    store,
                    namespace,
                    settings,
                    _RevokeTerminalArtifactAuthority(
                        reason=denial_reason,
                        service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                        action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
                        resource_type=ArtifactInternalResourceType.VERIFICATION_JOB,
                    ),
                )
                with pytest.raises(ArtifactAuthorityDeniedError, match=denial_reason):
                    await denying.verify_object(job_id)
                job = await session.get(ArtifactVerificationJob, str(job_id))
                assert job is not None
                assert job.status == "running"
                assert job.terminal_at is None
                assert job.terminal_result_code is None
                replica = await session.get(ArtifactReplica, job.replica_id)
                assert replica is not None
                assert replica.verification_state == "pending"
                assert await _count(session, ArtifactVerificationReceipt) == 0
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_verification_unavailable_retries_then_exhausts(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"artifact_provider_observation_maximum_attempts": 2}
    )
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "unavailable", b"retry") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await orchestrator.execute_committed_put(
                    attempt_id=admission.attempt_id, source=source
                )
                job = await session.scalar(select(ArtifactVerificationJob))
                assert job is not None
                job_id = UUID(job.id)
                await session.rollback()
                orchestrator._read_complete = AsyncMock(
                    side_effect=ArtifactStoreUnavailableError("unavailable")
                )
                assert await orchestrator.verify_object(job_id) == "provider_unavailable"
                await session.refresh(job)
                assert job.attempt_count == 1
                assert job.next_run_at is not None
                assert job.terminal_at is None
                await session.execute(
                    text(
                        "update artifact_verification_jobs set next_run_at = "
                        "clock_timestamp() - interval '1 second' where id = :id"
                    ),
                    {"id": job.id},
                )
                await session.commit()
                assert await orchestrator.verify_object(job_id) == "provider_unavailable"
                await session.refresh(job)
                assert job.attempt_count == 2
                assert job.next_run_at is None
                assert job.terminal_at is not None
                assert job.terminal_result_code == "provider_unavailable"
                assert await _count(session, ArtifactVerificationReceipt) == 0
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_0029_populated_contributor_receipt_upgrade_and_guarded_downgrade(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    """Prove populated v1 receipt compatibility and refusal to erase v2 evidence."""
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    receipt_id = str(uuid4())
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "migration-0029", b"legacy receipt") as source:
                _, _, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(
                        (
                            source.commitment.sha256,
                            source.commitment.byte_count,
                            source.commitment.media_type,
                        ),
                    ),
                )
                admission = await ArtifactAdmissionService(session, settings, namespace).admit(
                    ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[0]),
                        source=source,
                    )
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                content = ArtifactContent(
                    id=str(uuid4()),
                    sha256=attempt.sha256,
                    byte_count=attempt.byte_count,
                    media_type=attempt.media_type,
                    normalized_display_name=None,
                )
                session.add(content)
                await session.flush()
                replica = ArtifactReplica(
                    id=str(uuid4()),
                    content_id=content.id,
                    storage_namespace_id=attempt.storage_namespace_id,
                    namespace_fingerprint=attempt.namespace_fingerprint,
                    adapter="local",
                    provider_profile=namespace.provider_profile,
                    provider_object_ref=attempt.canonical_target,
                    verification_state="pending",
                    availability_state="unknown",
                    integrity_state="unknown",
                )
                session.add(replica)
                await session.flush()
                session.add(
                    ArtifactOperationReceipt(
                        id=receipt_id,
                        contract_version=1,
                        put_attempt_id=None,
                        upload_item_id=item_ids[0],
                        guide_source_item_id=None,
                        checker_run_id=None,
                        logical_role=None,
                        replica_id=replica.id,
                        operation="put",
                        idempotency_key="legacy-put",
                        request_digest=attempt.request_digest,
                        provider_object_ref=attempt.canonical_target,
                        replayed=False,
                        outcome="stored_pending_verification",
                        attempt_number=1,
                        correlation_id="legacy-correlation",
                        details=[],
                    )
                )
                await session.flush()
                attempt.status = "object_confirmed"
                attempt.replica_id = replica.id
                attempt.receipt_id = receipt_id
                attempt.terminal_result_code = "acknowledged"
                attempt.terminal_at = datetime.now(UTC)
                await session.commit()
    finally:
        await engine.dispose()

    config = _alembic_config()
    await asyncio.to_thread(command.downgrade, config, "0028_artifact_admission")
    await asyncio.to_thread(command.upgrade, config, "0029_artifact_verification")
    engine = create_async_engine(admission_database_env)
    try:
        async with engine.begin() as connection:
            migrated = (
                (
                    await connection.execute(
                        text(
                            "select contract_version, put_attempt_id, upload_item_id "
                            "from artifact_operation_receipts where id = :id"
                        ),
                        {"id": receipt_id},
                    )
                )
                .mappings()
                .one()
            )
            assert dict(migrated) == {
                "contract_version": 2,
                "put_attempt_id": str(admission.attempt_id),
                "upload_item_id": item_ids[0],
            }
            await connection.execute(
                text(
                    "insert into artifact_put_observation_receipts "
                    "(id, put_attempt_id, execution_generation, outcome, expected_sha256, "
                    "expected_byte_count) values (:id, :attempt, 1, 'observed_missing', "
                    ":sha256, :byte_count)"
                ),
                {
                    "id": str(uuid4()),
                    "attempt": str(admission.attempt_id),
                    "sha256": attempt.sha256,
                    "byte_count": attempt.byte_count,
                },
            )
    finally:
        await engine.dispose()
    with pytest.raises(RuntimeError, match="cannot downgrade populated artifact verification"):
        await asyncio.to_thread(command.downgrade, config, "0028_artifact_admission")


async def test_guide_admission_derives_three_scopes_without_provider_evidence(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            context = _context()
            async with minted_source(
                tmp_path / "scratch-source",
                b"guide",
                media_type="text/markdown",
            ) as source:
                project_id, item_id = await _seed_guide(
                    session,
                    context=context,
                    content_hash=source.commitment.sha256,
                    media_type=source.commitment.media_type,
                )
                with pytest.raises(
                    ArtifactAdmissionRelationshipError,
                    match="artifact admission human identity is unavailable",
                ):
                    await ArtifactAdmissionService(
                        session,
                        settings,
                        namespace,
                    ).admit(
                        GuideArtifactAdmissionRequest(
                            authorization_context=_context(),
                            guide_source_item_id=UUID(item_id),
                            source=source,
                        )
                    )
                assert await _count(session, ArtifactStorageNamespace) == 0
                assert await _count(session, ArtifactAdmissionScope) == 0
                assert await _count(session, ArtifactAdmissionCharge) == 0
                assert await _count(session, ArtifactPutAttempt) == 0
                await session.rollback()
                result = await ArtifactAdmissionService(
                    session,
                    settings,
                    namespace,
                ).admit(
                    GuideArtifactAdmissionRequest(
                        authorization_context=context,
                        guide_source_item_id=UUID(item_id),
                        source=source,
                    )
                )

            async with minted_source(
                tmp_path / "wrong-source",
                b"different guide bytes",
                media_type="text/markdown",
            ) as wrong_source:
                with pytest.raises(
                    ArtifactAdmissionRelationshipError,
                    match="guide source item relationship is unavailable",
                ):
                    await ArtifactAdmissionService(
                        session,
                        settings,
                        namespace,
                    ).admit(
                        GuideArtifactAdmissionRequest(
                            authorization_context=context,
                            guide_source_item_id=UUID(item_id),
                            source=wrong_source,
                        )
                    )

            attempt = await session.get(ArtifactPutAttempt, str(result.attempt_id))
            scopes = (
                (
                    await session.execute(
                        select(ArtifactAdmissionScope).order_by(ArtifactAdmissionScope.scope_type)
                    )
                )
                .scalars()
                .all()
            )
            assert attempt is not None
            assert attempt.status == "prepared"
            assert attempt.project_id == project_id
            assert attempt.task_id is None
            assert attempt.executor_id is None
            assert attempt.lease_expires_at is None
            assert attempt.next_run_at is None
            assert attempt.execution_generation == 0
            assert {scope.scope_type for scope in scopes} == {
                "deployment",
                "producer",
                "project",
            }
            assert len(result.charge_ids) == 3
            assert await _count(session, ArtifactPutAttempt) == 1
            assert await _count(session, ArtifactContent) == 0
            assert await _count(session, ArtifactReplica) == 0
            assert await _count(session, ArtifactOperationReceipt) == 0
    finally:
        await engine.dispose()


async def test_human_admission_revalidates_exact_active_profile_and_link(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with minted_source(
                tmp_path / "guide-source",
                b"guide",
                media_type="text/markdown",
            ) as guide_source:
                _, guide_item_id = await _seed_guide(
                    session,
                    context=context,
                    content_hash=guide_source.commitment.sha256,
                    media_type=guide_source.commitment.media_type,
                )
                async with minted_source(
                    tmp_path / "contributor-source",
                    b"work",
                ) as contributor_source:
                    _, _, upload_item_ids = await _seed_contributor_items(
                        session,
                        context=context,
                        commitments=(
                            (
                                contributor_source.commitment.sha256,
                                contributor_source.commitment.byte_count,
                                contributor_source.commitment.media_type,
                            ),
                        ),
                    )
                    requests = (
                        GuideArtifactAdmissionRequest(
                            authorization_context=context,
                            guide_source_item_id=UUID(guide_item_id),
                            source=guide_source,
                        ),
                        ContributorArtifactAdmissionRequest(
                            authorization_context=context,
                            upload_item_id=UUID(upload_item_ids[0]),
                            source=contributor_source,
                        ),
                    )
                    forged_context = context.model_copy(update={"identity_link_id": uuid4()})
                    for request in requests:
                        with pytest.raises(
                            ArtifactAdmissionRelationshipError,
                            match="artifact admission human identity is unavailable",
                        ):
                            await ArtifactAdmissionService(session, settings, namespace).admit(
                                replace(
                                    request,
                                    authorization_context=forged_context,
                                )
                            )

                    link = await session.get(
                        ActorIdentityLink,
                        str(context.identity_link_id),
                    )
                    assert link is not None
                    link.status = "revoked"
                    link.revoked_by = "test"
                    link.revoked_at = datetime.now(UTC)
                    link.revoked_reason = "test revocation"
                    await session.commit()
                    for request in requests:
                        with pytest.raises(
                            ArtifactAdmissionRelationshipError,
                            match="artifact admission human identity is unavailable",
                        ):
                            await ArtifactAdmissionService(session, settings, namespace).admit(
                                request
                            )

                    link.status = "active"
                    link.revoked_by = None
                    link.revoked_at = None
                    link.revoked_reason = None
                    link.reactivated_by = "test"
                    link.reactivated_at = datetime.now(UTC)
                    link.reactivation_reason = "test reactivation"
                    profile = await session.get(
                        ActorProfile,
                        str(context.actor_profile_id),
                    )
                    assert profile is not None
                    profile.status = "suspended"
                    profile.suspended_by = "test"
                    profile.suspended_at = datetime.now(UTC)
                    profile.suspension_reason = "test suspension"
                    await session.commit()
                    for request in requests:
                        with pytest.raises(
                            ArtifactAdmissionRelationshipError,
                            match="artifact admission human identity is unavailable",
                        ):
                            await ArtifactAdmissionService(session, settings, namespace).admit(
                                request
                            )

            assert await _count(session, ArtifactStorageNamespace) == 0
            assert await _count(session, ArtifactAdmissionScope) == 0
            assert await _count(session, ArtifactAdmissionCharge) == 0
            assert await _count(session, ArtifactPutAttempt) == 0
    finally:
        await engine.dispose()


async def test_guide_admission_facts_lock_snapshot_and_item(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as seed_session:
            _, item_id = await _seed_guide(
                seed_session,
                context=context,
                content_hash="sha256:" + "a" * 64,
                media_type="text/markdown",
            )

        async with factory() as lock_session:
            async with lock_session.begin():
                facts = await ArtifactRepository(lock_session).get_guide_admission_facts(item_id)
                assert facts is not None

                mutations = (
                    (
                        "update guide_source_snapshot_items "
                        "set media_type = 'application/json' where id = :item_id",
                        {"item_id": item_id},
                    ),
                    (
                        "update guide_source_snapshots set captured_by = :captured_by "
                        "where id = (select source_snapshot_id "
                        "from guide_source_snapshot_items where id = :item_id)",
                        {
                            "captured_by": str(uuid4()),
                            "item_id": item_id,
                        },
                    ),
                )
                for statement, parameters in mutations:
                    async with factory() as mutation_session:
                        with pytest.raises(DBAPIError, match="lock timeout"):
                            async with mutation_session.begin():
                                await mutation_session.execute(
                                    text("set local lock_timeout = '200ms'")
                                )
                                await mutation_session.execute(
                                    text(statement),
                                    parameters,
                                )

        async with factory() as assertion_session:
            assert await _count(assertion_session, ArtifactAdmissionScope) == 0
            assert await _count(assertion_session, ArtifactAdmissionCharge) == 0
            assert await _count(assertion_session, ArtifactPutAttempt) == 0
    finally:
        await engine.dispose()


async def test_actor_admission_proof_locks_exact_profile_then_link(
    admission_database_env: str,
) -> None:
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as seed_session:
            await _seed_human_actor(seed_session, context)
            await seed_session.commit()

        async with factory() as lock_session:
            async with lock_session.begin():
                proof = await ActorService(lock_session).lock_admission_proof(
                    context.actor_profile_id,
                    context.identity_link_id,
                )
                assert proof is not None
                assert proof.actor_profile_id == str(context.actor_profile_id)
                assert proof.identity_link_id == str(context.identity_link_id)

                mutations = (
                    (
                        "update actor_profiles set status = 'suspended' where id = :id",
                        str(context.actor_profile_id),
                    ),
                    (
                        "update actor_identity_links set status = 'revoked' where id = :id",
                        str(context.identity_link_id),
                    ),
                )
                for statement, row_id in mutations:
                    async with factory() as mutation_session:
                        with pytest.raises(DBAPIError, match="lock timeout"):
                            async with mutation_session.begin():
                                await mutation_session.execute(
                                    text("set local lock_timeout = '200ms'")
                                )
                                await mutation_session.execute(
                                    text(statement),
                                    {"id": row_id},
                                )
    finally:
        await engine.dispose()


async def test_exact_replay_returns_one_attempt_and_one_charge_set(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "scratch-source", b"same") as source:
                _, _, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(
                        (
                            source.commitment.sha256,
                            source.commitment.byte_count,
                            source.commitment.media_type,
                        ),
                    ),
                )
                request = ContributorArtifactAdmissionRequest(
                    authorization_context=context,
                    upload_item_id=UUID(item_ids[0]),
                    source=source,
                )
                first = await ArtifactAdmissionService(
                    session,
                    settings,
                    namespace,
                ).admit(request)
                replay = await ArtifactAdmissionService(
                    session,
                    settings,
                    namespace,
                ).admit(request)

            assert replay.replayed is True
            assert replay.attempt_id == first.attempt_id
            assert replay.charge_ids == first.charge_ids
            assert await _count(session, ArtifactPutAttempt) == 1
            assert await _count(session, ArtifactAdmissionCharge) == 4
            assert await _count(session, ArtifactPutAttemptCharge) == 4
    finally:
        await engine.dispose()


async def test_exact_replay_reacquires_released_charges_under_capacity(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, maximum_bytes=4)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "first-source", b"aaaa") as first_source:
                async with minted_source(tmp_path / "second-source", b"bbbb") as second_source:
                    first_sha256 = first_source.commitment.sha256
                    second_sha256 = second_source.commitment.sha256
                    _, _, item_ids = await _seed_contributor_items(
                        session,
                        context=context,
                        commitments=(
                            (
                                first_source.commitment.sha256,
                                first_source.commitment.byte_count,
                                first_source.commitment.media_type,
                            ),
                            (
                                second_source.commitment.sha256,
                                second_source.commitment.byte_count,
                                second_source.commitment.media_type,
                            ),
                        ),
                    )
                    first_request = ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[0]),
                        source=first_source,
                    )
                    second_request = ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[1]),
                        source=second_source,
                    )
                    first = await ArtifactAdmissionService(session, settings, namespace).admit(
                        first_request
                    )
                    first_attempt = await session.get(
                        ArtifactPutAttempt,
                        str(first.attempt_id),
                    )
                    assert first_attempt is not None
                    first_attempt.status = "absent_replay_required"
                    counters = (
                        (await session.execute(select(ArtifactAdmissionScope))).scalars().all()
                    )
                    first_charges = (
                        (
                            await session.execute(
                                select(ArtifactAdmissionCharge).where(
                                    ArtifactAdmissionCharge.sha256 == first_sha256
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    released_at = datetime.now(UTC)
                    for charge in first_charges:
                        charge.state = "released"
                        charge.released_at = released_at
                        charge.cas_version += 1
                    for counter in counters:
                        counter.counted_bytes = 0
                        counter.cas_version += 1
                    await session.commit()

                    await ArtifactAdmissionService(session, settings, namespace).admit(
                        second_request
                    )
                    with pytest.raises(ArtifactAdmissionCapacityError):
                        await ArtifactAdmissionService(session, settings, namespace).admit(
                            first_request
                        )

                    second_charges = (
                        (
                            await session.execute(
                                select(ArtifactAdmissionCharge).where(
                                    ArtifactAdmissionCharge.sha256 == second_sha256
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    counters = (
                        (await session.execute(select(ArtifactAdmissionScope))).scalars().all()
                    )
                    for charge in second_charges:
                        charge.state = "released"
                        charge.released_at = datetime.now(UTC)
                        charge.cas_version += 1
                    for counter in counters:
                        counter.counted_bytes = 0
                        counter.cas_version += 1
                    await session.commit()

                    replay = await ArtifactAdmissionService(session, settings, namespace).admit(
                        first_request
                    )

            assert replay.replayed is True
            assert replay.attempt_id == first.attempt_id
            refreshed_first_charges = (
                (
                    await session.execute(
                        select(ArtifactAdmissionCharge).where(
                            ArtifactAdmissionCharge.sha256 == first_sha256
                        )
                    )
                )
                .scalars()
                .all()
            )
            refreshed_counters = (
                (await session.execute(select(ArtifactAdmissionScope))).scalars().all()
            )
            assert {charge.state for charge in refreshed_first_charges} == {"provisional"}
            assert {charge.released_at for charge in refreshed_first_charges} == {None}
            assert {counter.counted_bytes for counter in refreshed_counters} == {4}
            assert await _count(session, ArtifactPutAttempt) == 2
    finally:
        await engine.dispose()


async def test_contributor_admission_rejects_cross_project_task_relationship(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "scratch-source", b"contributor") as source:
                _, _, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(
                        (
                            source.commitment.sha256,
                            source.commitment.byte_count,
                            source.commitment.media_type,
                        ),
                    ),
                )
                item = await session.get(ArtifactUploadItem, item_ids[0])
                assert item is not None
                upload_session = await session.get(ArtifactUploadSession, item.session_id)
                assert upload_session is not None
                unrelated_project_id = str(uuid4())
                session.add(
                    Project(
                        id=unrelated_project_id,
                        name="Unrelated admission project",
                        slug=f"unrelated-{unrelated_project_id}",
                    )
                )
                await session.flush()
                upload_session.project_id = unrelated_project_id
                await session.commit()

                with pytest.raises(
                    ArtifactAdmissionRelationshipError,
                    match="contributor upload item relationship is unavailable",
                ):
                    await ArtifactAdmissionService(session, settings, namespace).admit(
                        ContributorArtifactAdmissionRequest(
                            authorization_context=context,
                            upload_item_id=UUID(item_ids[0]),
                            source=source,
                        )
                    )

            assert await _count(session, ArtifactStorageNamespace) == 0
            assert await _count(session, ArtifactAdmissionScope) == 0
            assert await _count(session, ArtifactAdmissionCharge) == 0
            assert await _count(session, ArtifactPutAttempt) == 0
            assert await _count(session, AuditEvent) == 0
    finally:
        await engine.dispose()


async def test_same_content_distinct_operations_deduplicate_scope_bytes(
    admission_database_env: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    contexts = (_context(), _context())
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    original_reserve = ArtifactRepository.ensure_and_lock_admission_scopes
    ready_count = 0
    ready_lock = asyncio.Lock()
    start = asyncio.Event()

    async def synchronized_reserve(repository, scopes):
        nonlocal ready_count
        async with ready_lock:
            ready_count += 1
            if ready_count == 2:
                start.set()
        await start.wait()
        return await original_reserve(repository, scopes)

    monkeypatch.setattr(
        ArtifactRepository,
        "ensure_and_lock_admission_scopes",
        synchronized_reserve,
    )
    try:
        async with minted_source(tmp_path / "scratch-source", b"same") as source:
            async with factory() as seed_session:
                commitment = (
                    source.commitment.sha256,
                    source.commitment.byte_count,
                    source.commitment.media_type,
                )
                item_ids = []
                for context in contexts:
                    _, _, context_item_ids = await _seed_contributor_items(
                        seed_session,
                        context=context,
                        commitments=(commitment,),
                    )
                    item_ids.append(context_item_ids[0])
                seed_session.add(
                    ArtifactStorageNamespace(
                        id="primary",
                        backend=namespace.backend,
                        adapter=namespace.adapter,
                        provider_profile=namespace.provider_profile,
                        namespace_descriptor=namespace.namespace_descriptor,
                        namespace_fingerprint=namespace.namespace_fingerprint,
                    )
                )
                await seed_session.commit()

            async def admit(item_id: str, context: AuthorizationContext):
                async with factory() as session:
                    return await ArtifactAdmissionService(
                        session,
                        settings,
                        namespace,
                    ).admit(
                        ContributorArtifactAdmissionRequest(
                            authorization_context=context,
                            upload_item_id=UUID(item_id),
                            source=source,
                        )
                    )

            results = await asyncio.gather(
                *(admit(item_id, context) for item_id, context in zip(item_ids, contexts))
            )

        async with factory() as session:
            assert all(result.replayed is False for result in results)
            counters = (await session.execute(select(ArtifactAdmissionScope))).scalars().all()
            assert {counter.counted_bytes for counter in counters} == {4}
            assert await _count(session, ArtifactAdmissionCharge) == 7
            assert await _count(session, ArtifactPutAttempt) == 2
            assert await _count(session, ArtifactPutAttemptCharge) == 8
    finally:
        await engine.dispose()


async def test_completed_charge_deduplicates_and_released_charge_is_reacquired(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with minted_source(tmp_path / "scratch-source", b"same") as source:
            async with factory() as session:
                commitment = (
                    source.commitment.sha256,
                    source.commitment.byte_count,
                    source.commitment.media_type,
                )
                _, _, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(commitment, commitment, commitment),
                )
                service = ArtifactAdmissionService(session, settings, namespace)
                await service.admit(
                    ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[0]),
                        source=source,
                    )
                )

                charges = (await session.execute(select(ArtifactAdmissionCharge))).scalars().all()
                completed_at = datetime.now(UTC)
                for charge in charges:
                    charge.state = "completed"
                    charge.completed_at = completed_at
                await session.commit()

                await service.admit(
                    ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[1]),
                        source=source,
                    )
                )
                counters = (await session.execute(select(ArtifactAdmissionScope))).scalars().all()
                assert {counter.counted_bytes for counter in counters} == {4}

                released_at = datetime.now(UTC)
                for charge in charges:
                    charge.state = "released"
                    charge.completed_at = None
                    charge.released_at = released_at
                for counter in counters:
                    counter.counted_bytes = 0
                    counter.cas_version += 1
                await session.commit()

                await service.admit(
                    ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[2]),
                        source=source,
                    )
                )

                refreshed_charges = (
                    (await session.execute(select(ArtifactAdmissionCharge))).scalars().all()
                )
                refreshed_counters = (
                    (await session.execute(select(ArtifactAdmissionScope))).scalars().all()
                )
                assert {charge.state for charge in refreshed_charges} == {"provisional"}
                assert {charge.released_at for charge in refreshed_charges} == {None}
                assert {charge.cas_version for charge in refreshed_charges} == {1}
                assert {counter.counted_bytes for counter in refreshed_counters} == {4}
                assert await _count(session, ArtifactAdmissionCharge) == 4
                assert await _count(session, ArtifactPutAttempt) == 3
                assert await _count(session, ArtifactPutAttemptCharge) == 12
    finally:
        await engine.dispose()


async def test_concurrent_distinct_content_cannot_oversubscribe_any_scope(
    admission_database_env: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path, maximum_bytes=6)
    namespace = _namespace(settings)
    contexts = (_context(), _context())
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    original_reserve = ArtifactRepository.ensure_and_lock_admission_scopes
    ready_count = 0
    ready_lock = asyncio.Lock()
    start = asyncio.Event()

    async def synchronized_reserve(repository, scopes):
        nonlocal ready_count
        async with ready_lock:
            ready_count += 1
            if ready_count == 2:
                start.set()
        await start.wait()
        return await original_reserve(repository, scopes)

    monkeypatch.setattr(
        ArtifactRepository,
        "ensure_and_lock_admission_scopes",
        synchronized_reserve,
    )
    try:
        async with minted_source(tmp_path / "scratch-a", b"aaaa") as first_source:
            async with minted_source(tmp_path / "scratch-b", b"bbbb") as second_source:
                async with factory() as seed_session:
                    item_ids = []
                    for context, source in zip(
                        contexts,
                        (first_source, second_source),
                    ):
                        _, _, context_item_ids = await _seed_contributor_items(
                            seed_session,
                            context=context,
                            commitments=(
                                (
                                    source.commitment.sha256,
                                    source.commitment.byte_count,
                                    source.commitment.media_type,
                                ),
                            ),
                        )
                        item_ids.append(context_item_ids[0])
                    seed_session.add(
                        ArtifactStorageNamespace(
                            id="primary",
                            backend=namespace.backend,
                            adapter=namespace.adapter,
                            provider_profile=namespace.provider_profile,
                            namespace_descriptor=namespace.namespace_descriptor,
                            namespace_fingerprint=namespace.namespace_fingerprint,
                        )
                    )
                    await seed_session.commit()

                async def admit(item_id: str, source, context: AuthorizationContext):
                    async with factory() as session:
                        return await ArtifactAdmissionService(
                            session,
                            settings,
                            namespace,
                        ).admit(
                            ContributorArtifactAdmissionRequest(
                                authorization_context=context,
                                upload_item_id=UUID(item_id),
                                source=source,
                            )
                        )

                outcomes = await asyncio.gather(
                    admit(item_ids[0], first_source, contexts[0]),
                    admit(item_ids[1], second_source, contexts[1]),
                    return_exceptions=True,
                )

        assert sum(not isinstance(value, BaseException) for value in outcomes) == 1
        assert sum(isinstance(value, ArtifactAdmissionCapacityError) for value in outcomes) == 1
        async with factory() as session:
            counters = (await session.execute(select(ArtifactAdmissionScope))).scalars().all()
            assert {counter.counted_bytes for counter in counters} == {4}
            assert await _count(session, ArtifactPutAttempt) == 1
            assert await _count(session, ArtifactAdmissionCharge) == 4
    finally:
        await engine.dispose()


async def test_capacity_failure_rolls_back_namespace_scopes_charges_and_attempt(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, maximum_bytes=3)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "scratch-source", b"four") as source:
                _, _, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(
                        (
                            source.commitment.sha256,
                            source.commitment.byte_count,
                            source.commitment.media_type,
                        ),
                    ),
                )
                with pytest.raises(ArtifactAdmissionCapacityError):
                    await ArtifactAdmissionService(
                        session,
                        settings,
                        namespace,
                    ).admit(
                        ContributorArtifactAdmissionRequest(
                            authorization_context=context,
                            upload_item_id=UUID(item_ids[0]),
                            source=source,
                        )
                    )

            assert await _count(session, ArtifactStorageNamespace) == 0
            assert await _count(session, ArtifactAdmissionScope) == 0
            assert await _count(session, ArtifactAdmissionCharge) == 0
            assert await _count(session, ArtifactPutAttempt) == 0
    finally:
        await engine.dispose()


async def test_changed_input_for_existing_operation_fails_closed(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "scratch-a", b"aaaa") as first_source:
                _, _, item_ids = await _seed_contributor_items(
                    session,
                    context=context,
                    commitments=(
                        (
                            first_source.commitment.sha256,
                            first_source.commitment.byte_count,
                            first_source.commitment.media_type,
                        ),
                    ),
                )
                await ArtifactAdmissionService(session, settings, namespace).admit(
                    ContributorArtifactAdmissionRequest(
                        authorization_context=context,
                        upload_item_id=UUID(item_ids[0]),
                        source=first_source,
                    )
                )

            async with minted_source(tmp_path / "scratch-b", b"bbbb") as changed_source:
                item = await session.get(ArtifactUploadItem, item_ids[0])
                assert item is not None
                item.expected_sha256 = changed_source.commitment.sha256
                item.expected_size = changed_source.commitment.byte_count
                await session.commit()
                with pytest.raises(ArtifactAdmissionConflictError):
                    await ArtifactAdmissionService(session, settings, namespace).admit(
                        ContributorArtifactAdmissionRequest(
                            authorization_context=context,
                            upload_item_id=UUID(item_ids[0]),
                            source=changed_source,
                        )
                    )
    finally:
        await engine.dispose()


async def test_checker_output_requires_exact_active_fixed_service_identity(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    actor_id = uuid4()
    link_id = uuid4()
    context = _context(
        actor_profile_id=actor_id,
        identity_link_id=link_id,
        actor_kind=ActorKind.SERVICE,
    )
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            project_id, task_id, checker_run_id = await _seed_checker_output_relationships(session)
            session.add(
                ActorProfile(
                    id=str(actor_id),
                    actor_kind="service",
                    status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity=ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
                    created_by="test",
                )
            )
            session.add(
                ActorIdentityLink(
                    id=str(link_id),
                    actor_profile_id=str(actor_id),
                    issuer="https://issuer.example.test",
                    subject="checker-output-service",
                    subject_kind="service",
                    status="active",
                    linked_by="test",
                )
            )
            await session.commit()
            canonical_task = await session.get(WorkstreamTask, task_id)
            assert canonical_task is not None
            unrelated_task_id = str(uuid4())
            session.add(
                WorkstreamTask(
                    id=unrelated_task_id,
                    project_id=project_id,
                    locked_guide_version=canonical_task.locked_guide_version,
                    locked_post_submit_checker_policy_id=(
                        canonical_task.locked_post_submit_checker_policy_id
                    ),
                    locked_post_submit_checker_policy_version=(
                        canonical_task.locked_post_submit_checker_policy_version
                    ),
                    locked_post_submit_checker_policy_hash=(
                        canonical_task.locked_post_submit_checker_policy_hash
                    ),
                    locked_post_submit_checker_policy_body=(
                        canonical_task.locked_post_submit_checker_policy_body
                    ),
                    locked_review_policy_version=canonical_task.locked_review_policy_version,
                    locked_revision_policy_version=(canonical_task.locked_revision_policy_version),
                    locked_payment_policy_version=(canonical_task.locked_payment_policy_version),
                    locked_guide_source_snapshot_id=(
                        canonical_task.locked_guide_source_snapshot_id
                    ),
                    locked_guide_source_snapshot_hash=(
                        canonical_task.locked_guide_source_snapshot_hash
                    ),
                    locked_effective_project_submission_artifact_policy_id=(
                        canonical_task.locked_effective_project_submission_artifact_policy_id
                    ),
                    locked_effective_project_submission_artifact_policy_hash=(
                        canonical_task.locked_effective_project_submission_artifact_policy_hash
                    ),
                    locked_pre_submit_checker_policy_id=(
                        canonical_task.locked_pre_submit_checker_policy_id
                    ),
                    locked_pre_submit_checker_bundle_hash=(
                        canonical_task.locked_pre_submit_checker_bundle_hash
                    ),
                    title="Unrelated checker task",
                    description="Must not own the checker output.",
                    status="draft",
                    created_by="setup-actor",
                )
            )
            await session.flush()
            checker_run = await session.get(CheckerRun, checker_run_id)
            assert checker_run is not None
            checker_run.task_id = unrelated_task_id
            await session.commit()

            async with minted_source(tmp_path / "scratch-source", b"checker") as source:
                service = ArtifactAdmissionService(session, settings, namespace)
                forged = context.model_copy(update={"identity_link_id": uuid4()})
                with pytest.raises(
                    ArtifactAdmissionRelationshipError,
                    match="service identity is unavailable",
                ):
                    await service.admit(
                        CheckerOutputArtifactAdmissionRequest(
                            authorization_context=forged,
                            checker_run_id=UUID(checker_run_id),
                            logical_role="platform-review",
                            source=source,
                        )
                    )
                assert await _count(session, ArtifactStorageNamespace) == 0
                assert await _count(session, ArtifactAdmissionScope) == 0
                assert await _count(session, ArtifactAdmissionCharge) == 0
                assert await _count(session, ArtifactPutAttempt) == 0
                await session.rollback()

                with pytest.raises(
                    ArtifactAdmissionRelationshipError,
                    match="checker run relationship is unavailable",
                ):
                    await service.admit(
                        CheckerOutputArtifactAdmissionRequest(
                            authorization_context=context,
                            checker_run_id=UUID(checker_run_id),
                            logical_role="platform-review",
                            source=source,
                        )
                    )
                assert await _count(session, ArtifactStorageNamespace) == 0
                assert await _count(session, ArtifactAdmissionScope) == 0
                assert await _count(session, ArtifactAdmissionCharge) == 0
                assert await _count(session, ArtifactPutAttempt) == 0
                await session.rollback()

                checker_run = await session.get(CheckerRun, checker_run_id)
                assert checker_run is not None
                checker_run.task_id = task_id
                await session.commit()

                request = CheckerOutputArtifactAdmissionRequest(
                    authorization_context=context,
                    checker_run_id=UUID(checker_run_id),
                    logical_role="platform-review",
                    source=source,
                )
                result = await service.admit(request)
                replay = await service.admit(request)

            attempt = await session.get(ArtifactPutAttempt, str(result.attempt_id))
            scopes = (
                (
                    await session.execute(
                        select(ArtifactAdmissionScope).order_by(
                            ArtifactAdmissionScope.scope_type,
                            ArtifactAdmissionScope.scope_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            links = (
                (
                    await session.execute(
                        select(ArtifactPutAttemptCharge).where(
                            ArtifactPutAttemptCharge.attempt_id == str(result.attempt_id)
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert attempt is not None
            assert replay.attempt_id == result.attempt_id
            assert replay.charge_ids == result.charge_ids
            assert attempt.status == "prepared"
            assert attempt.producer_request_type == "checker_output"
            assert attempt.producer_type == "service_identity"
            assert attempt.producer_ref == ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value
            assert attempt.project_id == project_id
            assert attempt.task_id == task_id
            assert attempt.checker_run_id == checker_run_id
            assert attempt.logical_role == "platform-review"
            assert attempt.executor_id is None
            assert attempt.lease_expires_at is None
            assert attempt.next_run_at is None
            assert attempt.execution_generation == 0
            assert {scope.scope_type for scope in scopes} == {
                "deployment",
                "producer",
                "project",
                "task",
            }
            assert len(result.charge_ids) == 4
            assert len(links) == 4
            assert await _count(session, ArtifactPutAttempt) == 1
            assert await _count(session, ArtifactAdmissionCharge) == 4
            assert await _count(session, ArtifactContent) == 0
            assert await _count(session, ArtifactReplica) == 0
            assert await _count(session, ArtifactOperationReceipt) == 0
    finally:
        await engine.dispose()


async def test_invalid_checker_role_precedes_namespace_drift(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            session.add(
                ArtifactStorageNamespace(
                    id="primary",
                    backend=namespace.backend,
                    adapter=namespace.adapter,
                    provider_profile=namespace.provider_profile,
                    namespace_descriptor=namespace.namespace_descriptor,
                    namespace_fingerprint="sha256:" + "f" * 64,
                )
            )
            await session.commit()
            async with minted_source(tmp_path / "scratch-source", b"checker") as source:
                with pytest.raises(
                    ArtifactAdmissionRelationshipError,
                    match="logical role is invalid",
                ):
                    await ArtifactAdmissionService(session, settings, namespace).admit(
                        CheckerOutputArtifactAdmissionRequest(
                            authorization_context=_context(actor_kind=ActorKind.SERVICE),
                            checker_run_id=uuid4(),
                            logical_role="é" * 100,
                            source=source,
                        )
                    )
            assert await _count(session, ArtifactStorageNamespace) == 1
            assert await _count(session, ArtifactAdmissionScope) == 0
            assert await _count(session, ArtifactAdmissionCharge) == 0
            assert await _count(session, ArtifactPutAttempt) == 0
    finally:
        await engine.dispose()


def test_artifact_admission_migration_preserves_prior_rows_and_round_trips_empty(
    isolated_database_env: str,
    migration_lock,
) -> None:
    config = _alembic_config()
    namespace_fingerprint = "sha256:" + "a" * 64

    async def seed_prior_namespace() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "insert into artifact_storage_namespaces "
                        "(id,backend,adapter,provider_profile,namespace_descriptor,"
                        "namespace_fingerprint) values "
                        "('primary','local','local','local-v2','{}',:fingerprint)"
                    ),
                    {"fingerprint": namespace_fingerprint},
                )
        finally:
            await engine.dispose()

    async def state() -> tuple[int, bool]:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.connect() as connection:
                count = await connection.scalar(
                    text("select count(*) from artifact_storage_namespaces")
                )
                table_exists = await connection.scalar(
                    text("select to_regclass('artifact_put_attempts') is not null")
                )
                return int(count or 0), bool(table_exists)
        finally:
            await engine.dispose()

    async def cleanup() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("truncate table artifact_storage_namespaces cascade"))
        finally:
            await engine.dispose()

    with migration_lock():
        try:
            asyncio.run(_reset_admission_test_schema(isolated_database_env))
            command.upgrade(config, "0026_actor_profile_lifecycle")
            asyncio.run(seed_prior_namespace())
            command.upgrade(config, "0028_artifact_admission")
            assert asyncio.run(state()) == (1, True)
            command.downgrade(config, "0026_actor_profile_lifecycle")
            assert asyncio.run(state()) == (1, False)
            command.upgrade(config, "0028_artifact_admission")
            assert asyncio.run(state()) == (1, True)
            asyncio.run(cleanup())
        finally:
            asyncio.run(_reset_admission_test_schema(isolated_database_env))


def test_artifact_admission_migration_refuses_populated_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    config = _alembic_config()

    async def seed_attempt_only() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                context = _context()
                project_id, item_id = await _seed_guide(
                    session,
                    context=context,
                    content_hash="sha256:" + "b" * 64,
                    media_type="text/markdown",
                )
                namespace_fingerprint = "sha256:" + "c" * 64
                await session.execute(
                    text(
                        "insert into artifact_storage_namespaces "
                        "(id,backend,adapter,provider_profile,namespace_descriptor,"
                        "namespace_fingerprint) values "
                        "('primary','local','local','local-v2','{}',:fingerprint)"
                    ),
                    {"fingerprint": namespace_fingerprint},
                )
                await session.execute(
                    text(
                        "insert into artifact_put_attempts "
                        "(id,producer_request_type,producer_type,producer_ref,"
                        "project_id,guide_source_item_id,sha256,byte_count,media_type,"
                        "storage_namespace_id,namespace_fingerprint,canonical_target,"
                        "operation_identity,request_digest,status,"
                        "execution_generation,cas_version,prepared_at) values "
                        "(:id,'guide','actor_profile',:producer_ref,:project_id,"
                        ":item_id,:sha256,1,'text/markdown','primary',:fingerprint,"
                        ":target,:operation_identity,:request_digest,'prepared',"
                        "0,0,now())"
                    ),
                    {
                        "id": str(uuid4()),
                        "producer_ref": str(context.actor_profile_id),
                        "project_id": project_id,
                        "item_id": item_id,
                        "sha256": "sha256:" + "b" * 64,
                        "fingerprint": namespace_fingerprint,
                        "target": "sha256/bb/" + "b" * 62,
                        "operation_identity": "sha256:" + "d" * 64,
                        "request_digest": "sha256:" + "e" * 64,
                    },
                )
                await session.commit()
        finally:
            await engine.dispose()

    async def cleanup() -> None:
        engine = create_async_engine(isolated_database_env)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "truncate table artifact_put_attempt_charges, "
                        "artifact_put_attempts, artifact_admission_charges, "
                        "artifact_admission_scopes cascade"
                    )
                )
        finally:
            await engine.dispose()

    with migration_lock():
        try:
            asyncio.run(_reset_admission_test_schema(isolated_database_env))
            command.upgrade(config, "0028_artifact_admission")
            asyncio.run(seed_attempt_only())
            with pytest.raises(
                RuntimeError,
                match="cannot downgrade populated artifact admission ledger",
            ):
                command.downgrade(config, "0026_actor_profile_lifecycle")
            asyncio.run(cleanup())
            command.downgrade(config, "0026_actor_profile_lifecycle")
        finally:
            asyncio.run(_reset_admission_test_schema(isolated_database_env))
