"""PostgreSQL proofs for atomic durable-byte admission before provider I/O."""

# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import (  # type: ignore[import-not-found]
    async_sessionmaker,
    create_async_engine,
)

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
    ArtifactPutObservationReceipt,
    ArtifactPutAttempt,
    ArtifactPutAttemptCharge,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.interfaces.artifacts import (
    ArtifactObjectMissingError,
    ArtifactPutObservation,
    ArtifactPutResult,
    ArtifactStoreError,
    ArtifactStoreNamespaceClaim,
    ArtifactStoreUnavailableError,
)
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.authorization import (
    PreparedGuideArtifactAuthorization,
    guide_ingest_prepared_request_digest,
)
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    ArtifactInternalResourceType,
    CheckerOutputArtifactAdmissionRequest,
    GuideArtifactAdmissionRequest,
)
from app.modules.artifacts.service import (
    ArtifactAdmissionRelationshipError,
    ArtifactAdmissionService,
    ArtifactStorageNamespaceSpec,
    ArtifactStorageNamespaceError,
    ArtifactStorageOrchestrator,
    ArtifactPendingWorkScanner,
    _put_authority_facts,
    _verification_authority_facts,
    artifact_storage_namespace_spec,
)
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationContext,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    ServiceAuthorizationContext,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.models import AdminRoleGrant
from app.modules.projects.models import (
    GuideSourceArtifactIngest,
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    PaymentPolicy,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    ProjectGuide,
    ReviewPolicy,
    RevisionPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.projects.policy_lineage import (
    ReviewPolicySemantics,
    RevisionPolicySemantics,
    policy_digest,
)
from project_create_fixtures import seed_historical_project, suspend_historical_product_custody
from app.modules.tasks.models import AuditEvent, Submission, WorkstreamTask
from tests.artifact_store_helpers import (
    artifact_admission_limit_settings,
    minted_source,
)


class _AllowArtifactAuthority:
    """Explicit test-only authority exercising both phases."""

    def __init__(self) -> None:
        self.prepares = 0
        self.terminals = 0
        self.phase: str | None = None
        self.prepared_phases: list[str] = []
        self.consumed_phases: list[str] = []

    async def prepare(self, **values: object) -> None:
        self.prepares += 1
        self.phase = str(values["phase"])
        self.prepared_phases.append(self.phase)

    async def consume(self, **_values: object) -> None:
        self.terminals += 1
        assert self.phase is not None
        self.consumed_phases.append(self.phase)

    def discard(self) -> None:
        self.phase = None


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

    async def consume(self, **values: object) -> None:
        self.terminals += 1
        assert values["service_identity"] == self.service_identity
        assert values["action_id"] == self.action_id
        assert values["facts"].resource_type == self.resource_type
        if self.phase == "terminal":
            raise ArtifactAuthorityDeniedError(self.reason)


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return config


@pytest.fixture
def admission_database_env(isolated_database_env: str) -> Iterator[str]:
    """Provide the clean migrated database for artifact admission tests."""
    yield isolated_database_env


async def _reset_admission_test_schema(database_url: str) -> None:
    """Reset the schema only for tests that explicitly exercise migrations."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("drop schema if exists public cascade"), {})
            await conn.execute(text("create schema public"), {})
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
    common = dict(
        actor_profile_id=actor_profile_id or uuid4(),
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=identity_link_id or uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    if actor_kind is ActorKind.SERVICE:
        return ServiceAuthorizationContext(
            actor_kind=ActorKind.SERVICE,
            service_identity=ServiceIdentity.ARTIFACT_CHECKER_OUTPUT,
            **common,
        )
    return HumanAuthorizationContext(actor_kind=ActorKind.HUMAN, **common)


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
    await seed_historical_project(
        session,
        project_id=project_id,
        name="Admission project",
        slug=f"admission-{project_id}",
    )
    await session.flush()
    async with suspend_historical_product_custody(
        session,
        table="project_guides",
        triggers=("guide_mutation_product_custody",),
    ):
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
    async with suspend_historical_product_custody(
        session,
        table="guide_source_snapshots",
        triggers=("source_snapshot_product_custody",),
    ):
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
    async with suspend_historical_product_custody(
        session,
        table="guide_source_snapshot_items",
        triggers=("guide_source_snapshot_items_custody",),
    ):
        session.add(
            GuideSourceSnapshotItem(
                id=item_id,
                source_snapshot_id=snapshot_id,
                item_order=0,
                source_kind="inline",
                source_label="guide.md",
                ingestion_adapter="inline",
                media_type=media_type,
            )
        )
        await session.flush()
    await session.commit()
    return project_id, item_id


async def _seed_checker_output_relationships(session) -> tuple[str, str, str]:
    """Persist one complete checker-run ownership chain for admission proof."""
    project_id = str(uuid4())
    guide_id = str(uuid4())
    snapshot_id = str(uuid4())
    submission_policy_id = str(uuid4())
    effective_policy_id = str(uuid4())
    pre_submit_policy_id = str(uuid4())
    post_submit_policy_id = str(uuid4())
    review_policy_id = str(uuid4())
    revision_policy_id = str(uuid4())
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
    review_hash = policy_digest(
        "review",
        ReviewPolicySemantics(
            review_preference_window_seconds=3600,
            review_lease_duration_seconds=1800,
            allowed_decisions=("accept", "needs_revision", "reject"),
        ),
    )
    revision_hash = policy_digest(
        "revision",
        RevisionPolicySemantics(
            max_revision_rounds=1,
            revision_deadline_hours=24,
            allowed_resubmission_states=("needs_revision",),
        ),
    )

    await seed_historical_project(
        session,
        project_id=project_id,
        name="Checker project",
        slug=f"checker-{project_id}",
    )
    await session.flush()
    async with suspend_historical_product_custody(
        session,
        table="project_guides",
        triggers=("guide_mutation_product_custody",),
    ):
        session.add(
            ProjectGuide(
                id=guide_id,
                project_id=project_id,
                version=guide_version,
                status="draft",
                content_markdown="# Checker guide",
                approved_by="setup-actor",
                effective_at=now,
                created_by="setup-actor",
            )
        )
        await session.flush()
    async with suspend_historical_product_custody(
        session,
        table="guide_source_snapshots",
        triggers=("source_snapshot_product_custody",),
    ):
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
    async with (
        suspend_historical_product_custody(
            session,
            table="review_policies",
            triggers=("review_policy_mutation_custody",),
        ),
        suspend_historical_product_custody(
            session,
            table="revision_policies",
            triggers=("revision_policy_mutation_custody",),
        ),
    ):
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
                    id=review_policy_id,
                    project_id=project_id,
                    guide_version=guide_version,
                    policy_generation=1,
                    policy_hash=review_hash,
                    semantics_status="legacy_incomplete",
                    review_preference_window_seconds=3600,
                    review_lease_duration_seconds=1800,
                    max_active_review_leases_per_reviewer=1,
                    self_review_allowed=False,
                    reject_policy="close_task",
                    finding_evidence_requirement="optional",
                    requires_second_review=False,
                    allowed_decisions=["accept", "needs_revision", "reject"],
                    minimum_finding_fields=[],
                ),
                RevisionPolicy(
                    id=revision_policy_id,
                    project_id=project_id,
                    guide_version=guide_version,
                    policy_generation=1,
                    policy_hash=revision_hash,
                    semantics_status="legacy_incomplete",
                    max_revision_rounds=1,
                    revision_deadline_hours=24,
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
    async with suspend_historical_product_custody(
        session,
        table="project_guides",
        triggers=("guide_mutation_product_custody", "guide_lineage_lifecycle_guard"),
    ):
        guide = await session.get(ProjectGuide, guide_id)
        assert guide is not None
        guide.selected_review_policy_id = review_policy_id
        guide.selected_review_policy_generation = 1
        guide.selected_review_policy_hash = review_hash
        guide.selected_revision_policy_id = revision_policy_id
        guide.selected_revision_policy_generation = 1
        guide.selected_revision_policy_hash = revision_hash
        guide.status = "active"
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
            locked_review_policy_id=review_policy_id,
            locked_review_policy_generation=1,
            locked_review_policy_hash=review_hash,
            locked_revision_policy_id=revision_policy_id,
            locked_revision_policy_generation=1,
            locked_revision_policy_hash=revision_hash,
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
            locked_review_policy_id=review_policy_id,
            locked_review_policy_generation=1,
            locked_review_policy_hash=review_hash,
            locked_revision_policy_id=revision_policy_id,
            locked_revision_policy_generation=1,
            locked_revision_policy_hash=revision_hash,
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
            locked_review_policy_id=review_policy_id,
            locked_review_policy_generation=1,
            locked_review_policy_hash=review_hash,
            locked_revision_policy_id=revision_policy_id,
            locked_revision_policy_generation=1,
            locked_revision_policy_hash=revision_hash,
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


def _guide_operation(item_id: str) -> str:
    return canonical_json_hash({"request_type": "guide", "guide_source_item_id": item_id})


class _AllowGuidePreparedAuthorization:
    """Stand in for the issuer-local PREP consumer in lower-level ART tests."""

    def __init__(self, actor_profile_id: UUID) -> None:
        self.actor_profile_id = actor_profile_id
        self.handle = object.__new__(PreparedAuthorizationHandle)

    async def consume(self, *, prepared_authorization, facts) -> UUID:
        assert prepared_authorization is self.handle
        assert facts.byte_count >= 0
        return self.actor_profile_id


class _DenyGuidePreparedAuthorization(_AllowGuidePreparedAuthorization):
    async def consume(self, *, prepared_authorization, facts) -> UUID:
        del prepared_authorization, facts
        raise ArtifactAuthorityDeniedError("guide artifact ingest is unavailable")


async def _admit_guide_source(session, settings, namespace, context, source):
    """Create one guide attempt for execution/fencing tests."""
    _, guide_item_id = await _seed_guide(
        session,
        context=context,
        content_hash=source.commitment.sha256,
        media_type=source.commitment.media_type,
    )
    prepared = _AllowGuidePreparedAuthorization(context.actor_profile_id)
    return await ArtifactAdmissionService(session, settings, namespace).admit(
        GuideArtifactAdmissionRequest(
            guide_source_item_id=UUID(guide_item_id),
            source=source,
            operation_identity=_guide_operation(guide_item_id),
            request_digest="sha256:" + "a" * 64,
        ),
        guide_prepared_authorization=prepared,  # type: ignore[arg-type]
        prepared_authorization=prepared.handle,
    )


async def _admit_checker_output(session, settings, namespace, source):
    """Create one exact task-scoped checker-output attempt for shared-path tests."""
    actor_id, link_id = uuid4(), uuid4()
    context = _context(
        actor_profile_id=actor_id,
        identity_link_id=link_id,
        actor_kind=ActorKind.SERVICE,
    )
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
            subject=f"checker-output-{actor_id}",
            subject_kind="service",
            status="active",
            linked_by="test",
        )
    )
    await session.commit()
    result = await ArtifactAdmissionService(session, settings, namespace).admit(
        CheckerOutputArtifactAdmissionRequest(
            authorization_context=context,
            checker_run_id=UUID(checker_run_id),
            logical_role="platform-review",
            source=source,
        )
    )
    return project_id, task_id, checker_run_id, result


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
                        guide_source_item_id=UUID(guide_item_id),
                        source=source,
                        operation_identity=_guide_operation(guide_item_id),
                        request_digest="sha256:" + "a" * 64,
                    ),
                    guide_prepared_authorization=(
                        prepared := _AllowGuidePreparedAuthorization(context.actor_profile_id)
                    ),  # type: ignore[arg-type]
                    prepared_authorization=prepared.handle,
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
                assert [
                    replica.verification_state,
                    replica.availability_state,
                    replica.integrity_state,
                ] == ["verified", "available", "valid"]
                assert await _count(session, ArtifactOperationReceipt) == 1
                assert await _count(session, ArtifactVerificationReceipt) == 1
                await session.rollback()
                assert await orchestrator.verify_object(job_id) == "stale"
                assert authority.prepares == 5
                assert authority.terminals == 5
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
                        guide_source_item_id=UUID(guide_item_id),
                        source=source,
                        operation_identity=_guide_operation(guide_item_id),
                        request_digest="sha256:" + "a" * 64,
                    ),
                    guide_prepared_authorization=(
                        prepared := _AllowGuidePreparedAuthorization(context.actor_profile_id)
                    ),  # type: ignore[arg-type]
                    prepared_authorization=prepared.handle,
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
                assert authority.prepares == 2
                assert authority.terminals == 2
                assert authority.prepared_phases == ["claim", "terminal"]
                assert authority.consumed_phases == ["claim", "terminal"]
    finally:
        bootstrap.close()
        await engine.dispose()


@pytest.mark.parametrize("mode", ["caller_put", "observation"])
async def test_put_paths_recheck_authorized_facts_before_provider_io(
    admission_database_env: str,
    tmp_path: Path,
    mode: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    provider = SimpleNamespace(
        identity=SimpleNamespace(provider_key=namespace.adapter),
        put=AsyncMock(side_effect=AssertionError("provider put must not execute")),
        observe_put_result=AsyncMock(
            side_effect=AssertionError("provider observation must not execute")
        ),
        open=AsyncMock(side_effect=AssertionError("provider read must not execute")),
    )
    try:
        async with factory() as session:
            async with minted_source(tmp_path / f"put-fact-drift-{mode}", b"authorized") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                attempt_id = admission.attempt_id
                await session.commit()

                class DriftPutFactsAuthority(_AllowArtifactAuthority):
                    async def prepare(self, **_values: object) -> None:
                        await super().prepare(**_values)
                        async with factory() as drift_session, drift_session.begin():
                            drifted_attempt = await drift_session.get(
                                ArtifactPutAttempt, str(attempt_id), with_for_update=True
                            )
                            assert drifted_attempt is not None
                            drifted_attempt.operation_identity = "sha256:" + "f" * 64

                orchestrator = ArtifactStorageOrchestrator(
                    session, provider, namespace, settings, DriftPutFactsAuthority()
                )
                result = (
                    await orchestrator.execute_committed_put(attempt_id=attempt_id, source=source)
                    if mode == "caller_put"
                    else await orchestrator.resolve_put_attempt(attempt_id)
                )
                assert result == "stale"
                provider.put.assert_not_awaited()
                provider.observe_put_result.assert_not_awaited()
                provider.open.assert_not_awaited()
                attempt = await session.get(ArtifactPutAttempt, str(attempt_id))
                assert attempt is not None
                assert attempt.status == "prepared"
                assert attempt.execution_generation == 0
                assert attempt.executor_id is None
    finally:
        await engine.dispose()


@pytest.mark.parametrize("mode", ["caller_put", "observation"])
async def test_put_paths_recheck_authorized_facts_after_provider_io(
    admission_database_env: str,
    tmp_path: Path,
    mode: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with minted_source(
                tmp_path / f"post-io-put-drift-{mode}", b"authorized"
            ) as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                attempt_id = admission.attempt_id
                attempt = await session.get(ArtifactPutAttempt, str(attempt_id))
                assert attempt is not None
                provider_object_ref = attempt.canonical_target
                await session.commit()

                async def drift_facts() -> None:
                    async with factory() as drift_session, drift_session.begin():
                        drifted_attempt = await drift_session.get(
                            ArtifactPutAttempt, str(attempt_id), with_for_update=True
                        )
                        assert drifted_attempt is not None
                        drifted_attempt.operation_identity = "sha256:" + "e" * 64

                async def put(_source: object) -> ArtifactPutResult:
                    await drift_facts()
                    return ArtifactPutResult(provider_object_ref, replayed=False)

                async def observe_put_result(_commitment: object) -> ArtifactPutObservation:
                    await drift_facts()
                    return ArtifactPutObservation(provider_object_ref, committed=False)

                provider = SimpleNamespace(
                    identity=SimpleNamespace(provider_key=namespace.adapter),
                    put=AsyncMock(side_effect=put),
                    observe_put_result=AsyncMock(side_effect=observe_put_result),
                    open=AsyncMock(side_effect=AssertionError("provider read must not execute")),
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, provider, namespace, settings, _AllowArtifactAuthority()
                )
                result = (
                    await orchestrator.execute_committed_put(attempt_id=attempt_id, source=source)
                    if mode == "caller_put"
                    else await orchestrator.resolve_put_attempt(attempt_id)
                )
                assert result == "stale"
                attempt = await session.get(ArtifactPutAttempt, str(attempt_id))
                assert attempt is not None
                assert attempt.status == "put_in_flight"
                assert attempt.execution_generation == 1
                assert attempt.terminal_at is None
                assert await _count(session, ArtifactPutObservationReceipt) == 0
                assert await _count(session, ArtifactOperationReceipt) == 0
                assert await _count(session, ArtifactReplica) == 0
                assert await _count(session, ArtifactVerificationJob) == 0
                assert await _count(session, AuditEvent) == 0
    finally:
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
            first_facts = _put_authority_facts(
                first_claim,
                first_executor,
                first_claim.execution_generation,
            )
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
            assert (
                await stale._record_put_absence(first_claim, first_executor, first_facts) == "stale"
            )
            attempt = await stale_session.get(ArtifactPutAttempt, str(admission.attempt_id))
            assert attempt is not None
            assert attempt.execution_generation == 2
            assert attempt.executor_id == str(second_executor)
            assert await _count(stale_session, ArtifactPutObservationReceipt) == 0
            assert await _count(stale_session, ArtifactReplica) == 0
            assert await _count(stale_session, AuditEvent) == 0
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
                assert await _count(session, AuditEvent) == 0
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
            assert await _count(stale_session, AuditEvent) == 0
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
                    await orchestrator.resume_committed_put(
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
                assert await _count(session, ArtifactOperationReceipt) == 1
                assert await _count(session, ArtifactVerificationJob) == 1
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


async def test_verification_resource_drift_after_read_is_stale_without_terminal_facts(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "verification-drift", b"expected") as source:
                admission = await _admit_guide_source(
                    session, settings, namespace, _context(), source
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                await orchestrator.execute_committed_put(
                    attempt_id=admission.attempt_id, source=source
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                job = await session.scalar(select(ArtifactVerificationJob))
                assert attempt is not None and attempt.replica_id is not None and job is not None
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
                assert original_replica is not None
                assert job.status == "running"
                assert unrelated_replica.verification_state == "pending"
                assert original_replica.verification_state == "pending"
                assert await _count(session, ArtifactVerificationReceipt) == 0
    finally:
        bootstrap.close()
        await engine.dispose()


async def test_verification_rechecks_relationship_after_prepare_before_io(
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
                    async def prepare(self, **_values: object) -> None:
                        await super().prepare(**_values)
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


async def test_verification_relationship_conflict_uses_fresh_terminal_authority(
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

    class PhaseAuthority(_AllowArtifactAuthority):
        def __init__(self) -> None:
            super().__init__()
            self.phases: list[str] = []

        async def prepare(self, **values: object) -> None:
            await super().prepare(**values)
            self.phases.append(str(values["phase"]))

    try:
        async with factory() as session:
            attempts: list[ArtifactPutAttempt] = []
            for name, value in (("first", b"first"), ("second", b"second")):
                async with minted_source(tmp_path / name, value) as source:
                    admission = await _admit_guide_source(
                        session, settings, namespace, _context(), source
                    )
                    await ArtifactStorageOrchestrator(
                        session, store, namespace, settings, _AllowArtifactAuthority()
                    ).execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                    attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                    assert attempt is not None and attempt.replica_id is not None
                    attempts.append(attempt)
            job = await session.scalar(
                select(ArtifactVerificationJob).where(
                    ArtifactVerificationJob.originating_put_attempt_id == attempts[0].id
                )
            )
            assert job is not None
            job.replica_id = attempts[1].replica_id
            await session.commit()

            authority = PhaseAuthority()
            verifying = ArtifactStorageOrchestrator(session, store, namespace, settings, authority)
            verifying._read_complete = AsyncMock(
                side_effect=AssertionError("relationship conflict must not read provider bytes")
            )

            assert await verifying.verify_object(UUID(job.id)) == "conflict"
            verifying._read_complete.assert_not_awaited()
            await session.refresh(job)
            assert job.status == "conflict"
            assert authority.phases == ["claim", "terminal"]
            assert authority.terminals == 2
            receipt = await session.scalar(
                select(ArtifactVerificationReceipt).where(
                    ArtifactVerificationReceipt.verification_job_id == job.id
                )
            )
            assert receipt is not None and receipt.outcome == "conflict"
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
                    async def prepare(self, **_values: object) -> None:
                        await super().prepare(**_values)
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
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with minted_source(tmp_path / "postread-object-ref-drift", b"expected") as source:
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
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert job is not None and attempt is not None and attempt.replica_id is not None
                job_id, replica_id = UUID(job.id), attempt.replica_id
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
                assert replica is not None
                assert job.status == "running"
                assert replica.verification_state == "pending"
                assert await _count(session, ArtifactVerificationReceipt) == 0
    finally:
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
                expected_sha256 = source.commitment.sha256
                expected_byte_count = source.commitment.byte_count
                project_id, item_id = await _seed_guide(
                    session,
                    context=context,
                    content_hash="sha256:" + "f" * 64,
                    media_type=source.commitment.media_type,
                )
                lineage = await ArtifactRepository(session).get_guide_lineage(item_id)
                assert lineage is not None
                await session.rollback()
                with pytest.raises(
                    ArtifactAuthorityDeniedError,
                    match="guide artifact ingest is unavailable",
                ):
                    denied = _DenyGuidePreparedAuthorization(uuid4())
                    await ArtifactAdmissionService(
                        session,
                        settings,
                        namespace,
                    ).admit(
                        GuideArtifactAdmissionRequest(
                            guide_source_item_id=UUID(item_id),
                            source=source,
                            operation_identity=_guide_operation(item_id),
                            request_digest="sha256:" + "a" * 64,
                        ),
                        guide_prepared_authorization=denied,  # type: ignore[arg-type]
                        prepared_authorization=denied.handle,
                    )
                assert await _count(session, ArtifactStorageNamespace) == 0
                assert await _count(session, ArtifactAdmissionScope) == 0
                assert await _count(session, ArtifactAdmissionCharge) == 0
                assert await _count(session, ArtifactPutAttempt) == 0
                await session.rollback()
                mismatched = _AllowGuidePreparedAuthorization(context.actor_profile_id)
                with pytest.raises(
                    ArtifactAdmissionRelationshipError,
                    match="canonical lineage",
                ):
                    await ArtifactAdmissionService(session, settings, namespace).admit(
                        GuideArtifactAdmissionRequest(
                            project_id=uuid4(),
                            guide_id=UUID(lineage.guide_id),
                            guide_source_snapshot_id=UUID(lineage.guide_source_snapshot_id),
                            guide_source_item_id=UUID(item_id),
                            source=source,
                            operation_identity=_guide_operation(item_id),
                            request_digest="sha256:" + "a" * 64,
                        ),
                        guide_prepared_authorization=mismatched,  # type: ignore[arg-type]
                        prepared_authorization=mismatched.handle,
                    )
                assert await _count(session, ArtifactAdmissionScope) == 0
                assert await _count(session, ArtifactAdmissionCharge) == 0
                assert await _count(session, ArtifactPutAttempt) == 0
                await session.rollback()
                prepared = _AllowGuidePreparedAuthorization(context.actor_profile_id)
                async with session.begin():
                    result = await ArtifactAdmissionService(
                        session,
                        settings,
                        namespace,
                    ).admit(
                        GuideArtifactAdmissionRequest(
                            project_id=UUID(lineage.project_id),
                            guide_id=UUID(lineage.guide_id),
                            guide_source_snapshot_id=UUID(lineage.guide_source_snapshot_id),
                            guide_source_item_id=UUID(item_id),
                            source=source,
                            operation_identity=_guide_operation(item_id),
                            request_digest="sha256:" + "a" * 64,
                        ),
                        guide_prepared_authorization=prepared,  # type: ignore[arg-type]
                        prepared_authorization=prepared.handle,
                        existing_transaction=True,
                    )
                assert not session.in_transaction()

            async with minted_source(
                tmp_path / "wrong-source",
                b"different guide bytes",
                media_type="text/markdown",
            ) as wrong_source:
                with pytest.raises(
                    ArtifactAdmissionRelationshipError,
                    match="guide source ingest conflicts with prepared bytes",
                ):
                    wrong_prepared = _AllowGuidePreparedAuthorization(context.actor_profile_id)
                    await ArtifactAdmissionService(
                        session,
                        settings,
                        namespace,
                    ).admit(
                        GuideArtifactAdmissionRequest(
                            guide_source_item_id=UUID(item_id),
                            source=wrong_source,
                            operation_identity=_guide_operation(item_id),
                            request_digest="sha256:" + "a" * 64,
                        ),
                        guide_prepared_authorization=wrong_prepared,  # type: ignore[arg-type]
                        prepared_authorization=wrong_prepared.handle,
                    )

            attempt = await session.get(ArtifactPutAttempt, str(result.attempt_id))
            staged = await session.scalar(
                select(GuideSourceArtifactIngest).where(
                    GuideSourceArtifactIngest.source_item_id == item_id
                )
            )
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
            assert staged is not None
            assert staged.sha256 == expected_sha256
            assert staged.byte_count == expected_byte_count
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
            with pytest.raises(DBAPIError):
                await session.execute(
                    text(
                        "update artifact_put_attempts "
                        "set producer_request_type='contributor' where id=:attempt_id"
                    ),
                    {"attempt_id": str(result.attempt_id)},
                )
            await session.rollback()
    finally:
        await engine.dispose()


async def test_guide_admission_consumes_real_project_manager_prep_atomically(
    admission_database_env: str,
    tmp_path: Path,
) -> None:
    """Bind one real PM capability to locked lineage and server-owned bytes."""
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    context = _context()
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            project_id, item_id = await _seed_guide(
                session,
                context=context,
                content_hash="sha256:" + "f" * 64,
                media_type="application/octet-stream",
            )
            lineage = await ArtifactRepository(session).get_guide_lineage(item_id)
            assert lineage is not None
            await session.rollback()
            bootstrap_grant_id = uuid4()
            session.add(
                AdminRoleGrant(
                    id=bootstrap_grant_id,
                    target_actor_profile_id=str(context.actor_profile_id),
                    role="access_administrator",
                    scope_type="system",
                    scope_project_id=None,
                    status="active",
                    version=1,
                    granted_by_system_principal="workstream:system:bootstrap",
                    grant_reason="guide ingest fixture bootstrap",
                    granted_at=datetime.now(UTC),
                )
            )
            await session.flush()
            await session.execute(
                text(
                    "update authority_control set bootstrap_completed=true, "
                    "bootstrap_grant_id=:grant_id, version=1 where id=1"
                ),
                {"grant_id": bootstrap_grant_id},
            )
            project_manager_grant_id = uuid4()
            session.add(
                AdminRoleGrant(
                    id=project_manager_grant_id,
                    target_actor_profile_id=str(context.actor_profile_id),
                    role="project_manager",
                    scope_type="project",
                    scope_project_id=project_id,
                    status="active",
                    version=1,
                    granted_by_actor_profile_id=str(context.actor_profile_id),
                    granted_by_admin_role_grant_id=bootstrap_grant_id,
                    grant_reason="guide ingest authorization proof",
                    granted_at=datetime.now(UTC),
                )
            )
            await session.commit()
            idempotency_key = uuid4()
            denied_authority = PreparedGuideArtifactAuthorization(session)
            with pytest.raises(
                ArtifactAuthorityDeniedError,
                match="guide artifact ingest is unavailable",
            ):
                async with denied_authority.transaction():
                    await denied_authority.prepare(
                        authorization_context=context,
                        project_id=uuid4(),
                        guide_id=UUID(lineage.guide_id),
                        guide_source_snapshot_id=UUID(lineage.guide_source_snapshot_id),
                        guide_source_item_id=UUID(item_id),
                        idempotency_key=uuid4(),
                    )
            assert await _count(session, ArtifactAdmissionScope) == 0
            assert await _count(session, ArtifactAdmissionCharge) == 0
            assert await _count(session, ArtifactPutAttempt) == 0
            assert await _count(session, AuditEvent) == 0
            await session.rollback()

            link = await session.get(ActorIdentityLink, str(context.identity_link_id))
            assert link is not None
            link.status = "revoked"
            link.revoked_by = str(context.actor_profile_id)
            link.revoked_at = datetime.now(UTC)
            link.revoked_reason = "guide ingest denial proof"
            await session.commit()
            revoked_link_authority = PreparedGuideArtifactAuthorization(session)
            with pytest.raises(ArtifactAuthorityDeniedError):
                async with revoked_link_authority.transaction():
                    await revoked_link_authority.prepare(
                        authorization_context=context,
                        project_id=UUID(project_id),
                        guide_id=UUID(lineage.guide_id),
                        guide_source_snapshot_id=UUID(lineage.guide_source_snapshot_id),
                        guide_source_item_id=UUID(item_id),
                        idempotency_key=uuid4(),
                    )
            assert await _count(session, ArtifactPutAttempt) == 0
            assert await _count(session, AuditEvent) == 0
            await session.rollback()
            link = await session.get(ActorIdentityLink, str(context.identity_link_id))
            assert link is not None
            link.status = "active"
            link.revoked_by = None
            link.revoked_at = None
            link.revoked_reason = None
            link.reactivated_by = str(context.actor_profile_id)
            link.reactivated_at = datetime.now(UTC)
            link.reactivation_reason = "guide ingest test restoration"
            await session.commit()

            grant = await session.get(AdminRoleGrant, project_manager_grant_id)
            assert grant is not None
            grant.status = "revoked"
            grant.version = 2
            grant.revoked_by_actor_profile_id = str(context.actor_profile_id)
            grant.revoked_by_admin_role_grant_id = bootstrap_grant_id
            grant.revoked_reason = "guide ingest denial proof"
            grant.revoked_at = datetime.now(UTC)
            await session.commit()
            revoked_grant_authority = PreparedGuideArtifactAuthorization(session)
            with pytest.raises(ArtifactAuthorityDeniedError):
                async with revoked_grant_authority.transaction():
                    await revoked_grant_authority.prepare(
                        authorization_context=context,
                        project_id=UUID(project_id),
                        guide_id=UUID(lineage.guide_id),
                        guide_source_snapshot_id=UUID(lineage.guide_source_snapshot_id),
                        guide_source_item_id=UUID(item_id),
                        idempotency_key=uuid4(),
                    )
            assert await _count(session, ArtifactPutAttempt) == 0
            assert await _count(session, AuditEvent) == 0
            await session.rollback()
            session.add(
                AdminRoleGrant(
                    id=uuid4(),
                    target_actor_profile_id=str(context.actor_profile_id),
                    role="project_manager",
                    scope_type="project",
                    scope_project_id=project_id,
                    status="active",
                    version=1,
                    granted_by_actor_profile_id=str(context.actor_profile_id),
                    granted_by_admin_role_grant_id=bootstrap_grant_id,
                    grant_reason="guide ingest authorization replacement",
                    granted_at=datetime.now(UTC),
                )
            )
            await session.commit()
            authority = PreparedGuideArtifactAuthorization(session)
            async with minted_source(
                tmp_path / "real-guide-prep",
                b"authorized guide",
                media_type="application/octet-stream",
            ) as source:
                async with authority.transaction():
                    handle = await authority.prepare(
                        authorization_context=context,
                        project_id=UUID(project_id),
                        guide_id=UUID(lineage.guide_id),
                        guide_source_snapshot_id=UUID(lineage.guide_source_snapshot_id),
                        guide_source_item_id=UUID(item_id),
                        idempotency_key=idempotency_key,
                    )
                    result = await ArtifactAdmissionService(session, settings, namespace).admit(
                        GuideArtifactAdmissionRequest(
                            project_id=UUID(project_id),
                            guide_id=UUID(lineage.guide_id),
                            guide_source_snapshot_id=UUID(lineage.guide_source_snapshot_id),
                            guide_source_item_id=UUID(item_id),
                            source=source,
                            operation_identity=_guide_operation(item_id),
                            request_digest=guide_ingest_prepared_request_digest(
                                project_id=UUID(project_id),
                                guide_id=UUID(lineage.guide_id),
                                guide_source_snapshot_id=UUID(lineage.guide_source_snapshot_id),
                                guide_source_item_id=UUID(item_id),
                                idempotency_key=idempotency_key,
                            ),
                        ),
                        guide_prepared_authorization=authority,
                        prepared_authorization=handle,
                        existing_transaction=True,
                    )
            assert not session.in_transaction()
            assert await session.get(ArtifactPutAttempt, str(result.attempt_id)) is not None
            staged = await session.scalar(
                select(GuideSourceArtifactIngest).where(
                    GuideSourceArtifactIngest.source_item_id == item_id
                )
            )
            assert staged is not None
            assert staged.actor_profile_id == str(context.actor_profile_id)
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
                facts = await ArtifactRepository(lock_session).get_guide_lineage(item_id)
                assert facts is not None

                mutations = (
                    (
                        "update projects set status = 'active' where id = :project_id",
                        {"project_id": facts.project_id},
                        "lock timeout",
                    ),
                    (
                        "update project_guides set status = 'active' where id = :guide_id",
                        {"guide_id": facts.guide_id},
                        "lock timeout|guide lifecycle mutation requires activation authority",
                    ),
                    (
                        "update guide_source_snapshot_items "
                        "set media_type = 'application/json' where id = :item_id",
                        {"item_id": item_id},
                        "guide source snapshot items are immutable",
                    ),
                    (
                        "update guide_source_snapshots set captured_by = :captured_by "
                        "where id = (select source_snapshot_id "
                        "from guide_source_snapshot_items where id = :item_id)",
                        {
                            "captured_by": str(uuid4()),
                            "item_id": item_id,
                        },
                        "lock timeout",
                    ),
                )
                for statement, parameters, denial in mutations:
                    async with factory() as session:
                        with pytest.raises(DBAPIError, match=denial):
                            async with session.begin():
                                await session.execute(
                                    text("set local lock_timeout = '200ms'"),
                                    {},
                                )
                                await session.execute(
                                    text(statement),
                                    parameters,
                                )

        async with factory() as assertion_session:
            assert await _count(assertion_session, ArtifactAdmissionScope) == 0
            assert await _count(assertion_session, ArtifactAdmissionCharge) == 0
            assert await _count(assertion_session, ArtifactPutAttempt) == 0
            async with suspend_historical_product_custody(
                assertion_session,
                table="project_guides",
                triggers=(
                    "guide_lineage_lifecycle_guard",
                    "guide_mutation_product_custody",
                ),
            ):
                await assertion_session.execute(
                    text("update project_guides set status = 'inactive' where id = :guide_id"),
                    {"guide_id": facts.guide_id},
                )
                await assertion_session.flush()
            assert await ArtifactRepository(assertion_session).get_guide_lineage(item_id) is None
            await assertion_session.rollback()
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
                    locked_review_policy_id=canonical_task.locked_review_policy_id,
                    locked_review_policy_generation=(
                        canonical_task.locked_review_policy_generation
                    ),
                    locked_review_policy_hash=canonical_task.locked_review_policy_hash,
                    locked_revision_policy_id=canonical_task.locked_revision_policy_id,
                    locked_revision_policy_generation=(
                        canonical_task.locked_revision_policy_generation
                    ),
                    locked_revision_policy_hash=(canonical_task.locked_revision_policy_hash),
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
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

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


@pytest.mark.parametrize(
    ("read_result", "expected_outcome"),
    (
        (None, "verified"),
        (ArtifactObjectMissingError("missing"), "missing"),
        (("sha256:" + "0" * 64, 1), "integrity_mismatch"),
    ),
)
async def test_checker_output_shared_put_and_verification_lifecycle(
    admission_database_env: str,
    tmp_path: Path,
    read_result: object,
    expected_outcome: str,
) -> None:
    """Task-scoped checker output survives every shared terminal byte outcome."""
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    engine = create_async_engine(admission_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with minted_source(
                tmp_path / f"checker-{expected_outcome}", b"checker lifecycle"
            ) as source:
                project_id, task_id, checker_run_id, admission = await _admit_checker_output(
                    session, settings, namespace, source
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                assert (
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id, source=source
                    )
                    == "stored_pending_verification"
                )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                receipt = await session.scalar(
                    select(ArtifactOperationReceipt).where(
                        ArtifactOperationReceipt.put_attempt_id == str(admission.attempt_id)
                    )
                )
                job = await session.scalar(
                    select(ArtifactVerificationJob).where(
                        ArtifactVerificationJob.originating_put_attempt_id
                        == str(admission.attempt_id)
                    )
                )
                assert attempt is not None and receipt is not None and job is not None
                job_id = UUID(job.id)
                assert attempt.producer_request_type == "checker_output"
                assert (attempt.project_id, attempt.task_id, attempt.checker_run_id) == (
                    project_id,
                    task_id,
                    checker_run_id,
                )
                assert receipt.checker_run_id == checker_run_id
                with pytest.raises(DBAPIError):
                    await session.execute(
                        text(
                            "update artifact_operation_receipts set contract_version=1 "
                            "where id=:receipt_id"
                        ),
                        {"receipt_id": receipt.id},
                    )
                await session.rollback()
                if isinstance(read_result, Exception):
                    orchestrator._read_complete = AsyncMock(side_effect=read_result)
                elif read_result is not None:
                    orchestrator._read_complete = AsyncMock(return_value=read_result)
                assert await orchestrator.verify_object(job_id) == expected_outcome
                job = await session.get(ArtifactVerificationJob, str(job_id))
                assert job is not None
                assert job.status == expected_outcome
                verification = await session.scalar(
                    select(ArtifactVerificationReceipt).where(
                        ArtifactVerificationReceipt.verification_job_id == job.id
                    )
                )
                assert verification is not None
                assert verification.outcome == expected_outcome
    finally:
        bootstrap.close()
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


@pytest.mark.postgres_schema_contract
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
            assert list(asyncio.run(state())) == [1, True]
            command.downgrade(config, "0026_actor_profile_lifecycle")
            assert list(asyncio.run(state())) == [1, False]
            command.upgrade(config, "0028_artifact_admission")
            assert list(asyncio.run(state())) == [1, True]
            asyncio.run(cleanup())
        finally:
            asyncio.run(_reset_admission_test_schema(isolated_database_env))
            command.upgrade(config, "head")


@pytest.mark.postgres_schema_contract
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
                await _seed_human_actor(session, context)
                project_id, guide_id, snapshot_id, item_id = (str(uuid4()) for _ in range(4))
                await session.execute(
                    text(
                        "insert into projects (id,name,slug,status) values "
                        "(:id,'Admission migration',:slug,'draft')"
                    ),
                    {"id": project_id, "slug": f"admission-migration-{project_id}"},
                )
                await session.execute(
                    text(
                        "insert into project_guides "
                        "(id,project_id,version,status,content_markdown,created_by) values "
                        "(:id,:project_id,'v1','draft','# Guide','test')"
                    ),
                    {"id": guide_id, "project_id": project_id},
                )
                await session.execute(
                    text(
                        "insert into guide_source_snapshots "
                        "(id,project_id,guide_id,guide_version,manifest_schema_version,"
                        "manifest_json,bundle_hash,captured_by) values "
                        "(:id,:project_id,:guide_id,'v1','v1',:manifest,:bundle_hash,:actor)"
                    ),
                    {
                        "id": snapshot_id,
                        "project_id": project_id,
                        "guide_id": guide_id,
                        "manifest": '{"items": []}',
                        "bundle_hash": canonical_json_hash({"items": []}),
                        "actor": str(context.actor_profile_id),
                    },
                )
                await session.execute(
                    text(
                        "insert into guide_source_snapshot_items "
                        "(id,source_snapshot_id,item_order,source_kind,durable_ref,"
                        "ingestion_adapter,content_hash,media_type) values "
                        "(:id,:snapshot_id,0,'inline','guide.md','inline',"
                        ":content_hash,'text/markdown')"
                    ),
                    {
                        "id": item_id,
                        "snapshot_id": snapshot_id,
                        "content_hash": "sha256:" + "a" * 64,
                    },
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
            command.upgrade(config, "head")
