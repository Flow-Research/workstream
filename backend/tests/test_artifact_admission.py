"""PostgreSQL proofs for atomic durable-byte admission before provider I/O."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactPutAttemptCharge,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactUploadItem,
    ArtifactUploadSession,
)
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.schemas import (
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
    artifact_storage_namespace_spec,
)
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationContext,
    IdentityLinkStatus,
)
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
    bootstrap = LocalStorageBootstrap(
        LocalStorageAdapter(root=settings.artifact_local_root)
    )
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
                await session.execute(
                    select(ArtifactAdmissionScope).order_by(
                        ArtifactAdmissionScope.scope_type
                    )
                )
            ).scalars().all()
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
                    forged_context = context.model_copy(
                        update={"identity_link_id": uuid4()}
                    )
                    for request in requests:
                        with pytest.raises(
                            ArtifactAdmissionRelationshipError,
                            match="artifact admission human identity is unavailable",
                        ):
                            await ArtifactAdmissionService(
                                session, settings, namespace
                            ).admit(
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
                            await ArtifactAdmissionService(
                                session, settings, namespace
                            ).admit(request)

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
                            await ArtifactAdmissionService(
                                session, settings, namespace
                            ).admit(request)

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
                facts = await ArtifactRepository(
                    lock_session
                ).get_guide_admission_facts(item_id)
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
                async with minted_source(
                    tmp_path / "second-source", b"bbbb"
                ) as second_source:
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
                    first = await ArtifactAdmissionService(
                        session, settings, namespace
                    ).admit(first_request)
                    first_attempt = await session.get(
                        ArtifactPutAttempt,
                        str(first.attempt_id),
                    )
                    assert first_attempt is not None
                    first_attempt.status = "absent_replay_required"
                    counters = (
                        await session.execute(select(ArtifactAdmissionScope))
                    ).scalars().all()
                    first_charges = (
                        await session.execute(
                            select(ArtifactAdmissionCharge).where(
                                ArtifactAdmissionCharge.sha256
                                == first_sha256
                            )
                        )
                    ).scalars().all()
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
                        await ArtifactAdmissionService(
                            session, settings, namespace
                        ).admit(first_request)

                    second_charges = (
                        await session.execute(
                            select(ArtifactAdmissionCharge).where(
                                ArtifactAdmissionCharge.sha256
                                == second_sha256
                            )
                        )
                    ).scalars().all()
                    counters = (
                        await session.execute(select(ArtifactAdmissionScope))
                    ).scalars().all()
                    for charge in second_charges:
                        charge.state = "released"
                        charge.released_at = datetime.now(UTC)
                        charge.cas_version += 1
                    for counter in counters:
                        counter.counted_bytes = 0
                        counter.cas_version += 1
                    await session.commit()

                    replay = await ArtifactAdmissionService(
                        session, settings, namespace
                    ).admit(first_request)

            assert replay.replayed is True
            assert replay.attempt_id == first.attempt_id
            refreshed_first_charges = (
                await session.execute(
                    select(ArtifactAdmissionCharge).where(
                        ArtifactAdmissionCharge.sha256
                        == first_sha256
                    )
                )
            ).scalars().all()
            refreshed_counters = (
                await session.execute(select(ArtifactAdmissionScope))
            ).scalars().all()
            assert {charge.state for charge in refreshed_first_charges} == {
                "provisional"
            }
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
            counters = (
                await session.execute(select(ArtifactAdmissionScope))
            ).scalars().all()
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

                charges = (
                    await session.execute(select(ArtifactAdmissionCharge))
                ).scalars().all()
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
                counters = (
                    await session.execute(select(ArtifactAdmissionScope))
                ).scalars().all()
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
                    await session.execute(select(ArtifactAdmissionCharge))
                ).scalars().all()
                refreshed_counters = (
                    await session.execute(select(ArtifactAdmissionScope))
                ).scalars().all()
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
        assert sum(
            isinstance(value, ArtifactAdmissionCapacityError) for value in outcomes
        ) == 1
        async with factory() as session:
            counters = (
                await session.execute(select(ArtifactAdmissionScope))
            ).scalars().all()
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
            project_id, task_id, checker_run_id = await _seed_checker_output_relationships(
                session
            )
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
                    locked_revision_policy_version=(
                        canonical_task.locked_revision_policy_version
                    ),
                    locked_payment_policy_version=(
                        canonical_task.locked_payment_policy_version
                    ),
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
                await session.execute(
                    select(ArtifactAdmissionScope).order_by(
                        ArtifactAdmissionScope.scope_type,
                        ArtifactAdmissionScope.scope_id,
                    )
                )
            ).scalars().all()
            links = (
                await session.execute(
                    select(ArtifactPutAttemptCharge).where(
                        ArtifactPutAttemptCharge.attempt_id == str(result.attempt_id)
                    )
                )
            ).scalars().all()
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
                await connection.execute(
                    text("truncate table artifact_storage_namespaces cascade")
                )
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
