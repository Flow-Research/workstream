"""Focused proofs for the fixed-service ART prepared-authority adapter."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.modules.artifacts.authorization as artifact_authorization
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.artifacts.authorization import PreparedArtifactInternalAuthority
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    ArtifactInternalAuthority,
    ArtifactInternalResourceType,
    ArtifactPutAttemptAuthorityFacts,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    MatchedAuthorityKind,
    authorization_resource_digest,
)
from app.modules.tasks.models import AuditEvent
from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
from app.interfaces.artifacts import ArtifactStoreNamespaceClaim
from app.modules.artifacts.models import (
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactReplica,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.artifacts.service import (
    ArtifactAdmissionService,
    ArtifactPendingWorkScanner,
    ArtifactStorageOrchestrator,
)
from app.modules.artifacts.schemas import GuideArtifactAdmissionRequest
from tests.artifact_store_helpers import minted_source
from tests.test_artifact_admission import _context, _namespace, _seed_guide, _settings


class _Session:
    """Minimal stable-root transaction used by PREP unit proofs."""

    def __init__(self) -> None:
        self.root = SimpleNamespace(is_active=True)
        self.sync_session = self
        self.commits = 0

    def get_transaction(self):
        return self.root

    def in_nested_transaction(self) -> bool:
        return False

    async def commit(self) -> None:
        self.commits += 1


def _principal(status: str = "active"):
    profile = SimpleNamespace(
        id=str(uuid4()),
        actor_kind="service",
        status=status,
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER.value,
    )
    link = SimpleNamespace(
        id=str(uuid4()),
        actor_profile_id=profile.id,
        subject_kind="service",
        status="active",
    )
    return profile, link


def _facts() -> ArtifactPutAttemptAuthorityFacts:
    return ArtifactPutAttemptAuthorityFacts(
        resource_type=ArtifactInternalResourceType.PUT_ATTEMPT,
        resource_id=uuid4(),
        operation_identity="sha256:" + "1" * 64,
        namespace_fingerprint="sha256:" + "2" * 64,
        sha256="sha256:" + "3" * 64,
        byte_count=7,
        executor_id=uuid4(),
        execution_generation=1,
    )


@pytest.mark.asyncio
async def test_adapter_normalizes_malformed_resource_selector_to_denial() -> None:
    authority = PreparedArtifactInternalAuthority(
        _Session(),  # type: ignore[arg-type]
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    malformed = replace(_facts(), resource_id="not-a-uuid")  # type: ignore[arg-type]

    with pytest.raises(ArtifactAuthorityDeniedError, match="resource is invalid"):
        await authority.prepare(
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            facts=malformed,
            phase="claim",
            idempotency_key=uuid4(),
        )


class _FailAfterConsumeAuthority:
    """Inject a failure after AUTH stages allow evidence in the ART transaction."""

    def __init__(self, delegate: ArtifactInternalAuthority) -> None:
        self._delegate = delegate

    async def prepare(self, **kwargs) -> None:
        await self._delegate.prepare(**kwargs)

    async def consume(self, **kwargs):
        await self._delegate.consume(**kwargs)
        raise RuntimeError("injected failure after authorization consume")

    def discard(self) -> None:
        self._delegate.discard()


class _RecordingAuthority:
    def __init__(self, delegate: ArtifactInternalAuthority) -> None:
        self._delegate = delegate
        self.consumed = None

    async def prepare(self, **kwargs) -> None:
        await self._delegate.prepare(**kwargs)

    async def consume(self, **kwargs):
        self.consumed = kwargs["facts"]
        return await self._delegate.consume(**kwargs)

    def discard(self) -> None:
        self._delegate.discard()


def _service_principal(
    service_identity: ServiceIdentity,
    *,
    status: str = "active",
) -> tuple[ActorProfile, ActorIdentityLink]:
    profile_id, link_id = uuid4(), uuid4()
    suspended = status == "suspended"
    return (
        ActorProfile(
            id=str(profile_id),
            actor_kind="service",
            status=status,
            provisioning_method="manual_service_provisioning",
            service_identity=service_identity.value,
            created_by="test",
            suspended_by="test" if suspended else None,
            suspended_at=datetime.now(UTC) if suspended else None,
            suspension_reason="test security hold" if suspended else None,
        ),
        ActorIdentityLink(
            id=str(link_id),
            actor_profile_id=str(profile_id),
            issuer="https://issuer.example.test",
            subject=service_identity.value,
            subject_kind="service",
            status="active",
            linked_by="test",
        ),
    )


def _install_principal(monkeypatch: pytest.MonkeyPatch, *, status: str = "active"):
    profile, link = _principal(status)

    class Actors:
        async def get_service_actor(self, service_identity: str):
            assert service_identity == profile.service_identity
            return profile

        async def get_identity_link_for_actor(self, actor_profile_id: str):
            assert actor_profile_id == profile.id
            return link

    class Admin:
        def __init__(self, _session) -> None:
            pass

        async def lock_request_actor(self, identity_link_id, actor_profile_id):
            assert str(identity_link_id) == link.id
            assert str(actor_profile_id) == profile.id
            return link, profile

    monkeypatch.setattr(artifact_authorization, "ActorRepository", lambda _session: Actors())
    monkeypatch.setattr(artifact_authorization, "AdminAuthorizationRepository", Admin)


@pytest.mark.asyncio
async def test_adapter_consumes_exact_fixed_service_resource_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_principal(monkeypatch)
    staged = []

    async def stage(self, decision, _actor_profile_id):
        staged.append(decision)

    monkeypatch.setattr(AuthorizationService, "_stage_decision", stage)
    session = _Session()
    authority = PreparedArtifactInternalAuthority(
        session,  # type: ignore[arg-type]
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    facts = _facts()

    await authority.prepare(
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
        facts=facts,
        phase="claim",
        idempotency_key=facts.executor_id,
    )
    await authority.consume(
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
        facts=facts,
    )

    assert len(staged) == 1
    assert staged[0].allowed is True
    assert staged[0].matched_authority_kind is MatchedAuthorityKind.FIXED_SERVICE
    assert staged[0].resource_id == facts.resource_id


@pytest.mark.asyncio
async def test_adapter_rejects_same_resource_fence_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_principal(monkeypatch)
    staged = []

    async def stage(self, decision, _actor_profile_id):
        staged.append(decision)

    monkeypatch.setattr(AuthorizationService, "_stage_decision", stage)
    authority = PreparedArtifactInternalAuthority(
        _Session(),  # type: ignore[arg-type]
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    facts = _facts()
    await authority.prepare(
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
        facts=facts,
        phase="claim",
        idempotency_key=facts.executor_id,
    )

    with pytest.raises(artifact_authorization.ArtifactAuthorityDeniedError):
        await authority.consume(
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            facts=replace(facts, execution_generation=facts.execution_generation + 1),
        )

    authority.discard()
    assert staged == []


@pytest.mark.asyncio
async def test_adapter_restages_lifecycle_denial_only_after_caller_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_principal(monkeypatch, status="suspended")
    staged = []

    async def stage(self, decision, _actor_profile_id):
        staged.append(decision)

    monkeypatch.setattr(AuthorizationService, "_stage_decision", stage)
    session = _Session()
    authority = PreparedArtifactInternalAuthority(
        session,  # type: ignore[arg-type]
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    facts = _facts()

    with pytest.raises(AuthorizationDenied) as denied:
        await authority.prepare(
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            facts=facts,
            phase="terminal",
            idempotency_key=facts.executor_id,
        )
    assert staged == [denied.value.decision]
    assert session.commits == 0

    await authority.persist_denial()

    assert staged == [denied.value.decision, denied.value.decision]
    assert session.commits == 1
    assert staged[-1].allowed is False
    assert staged[-1].resource_id == facts.resource_id


@pytest.mark.asyncio
async def test_postgresql_fixed_service_allow_and_clean_denial_evidence(
    isolated_database_env: str,
) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    profile_id, link_id = uuid4(), uuid4()
    try:
        async with factory() as session:
            session.add(
                ActorProfile(
                    id=str(profile_id),
                    actor_kind="service",
                    status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER.value,
                    created_by="test",
                )
            )
            session.add(
                ActorIdentityLink(
                    id=str(link_id),
                    actor_profile_id=str(profile_id),
                    issuer="https://issuer.example.test",
                    subject="artifact-put-resolver",
                    subject_kind="service",
                    status="active",
                    linked_by="test",
                )
            )
            await session.commit()
            facts = _facts()
            allowed = PreparedArtifactInternalAuthority(
                session,
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
            async with session.begin():
                await allowed.prepare(
                    service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                    action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                    facts=facts,
                    phase="claim",
                    idempotency_key=facts.executor_id,
                )
                await allowed.consume(
                    service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                    action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                    facts=facts,
                )
            profile = await session.get(ActorProfile, str(profile_id))
            assert profile is not None
            profile.status = "suspended"
            profile.suspended_by = "test"
            profile.suspended_at = datetime.now(UTC)
            profile.suspension_reason = "test security hold"
            await session.commit()
            denied = PreparedArtifactInternalAuthority(
                session,
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
            with pytest.raises(AuthorizationDenied):
                async with session.begin():
                    await denied.prepare(
                        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                        action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                        facts=facts,
                        phase="terminal",
                        idempotency_key=facts.executor_id,
                    )
            await denied.persist_denial()
            events = list(
                await session.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.action_id
                        == ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE.value
                    )
                    .order_by(AuditEvent.created_at, AuditEvent.id)
                )
            )
            assert [event.after_facts["allowed"] for event in events] == [True, False]
            assert all("resource_context_digest" in event.after_facts for event in events)
            assert events[-1].denial_code == "actor_suspended"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scanner_failure_after_consume_rolls_back_evidence_and_publishes_nothing(
    isolated_database_env: str,
    tmp_path,
) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"artifact_pending_work_scan_page_size": 1}
    )
    namespace = _namespace(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    published: list[str] = []
    profile, link = _service_principal(ServiceIdentity.ARTIFACT_SCHEDULER)
    try:
        async with factory() as session:
            session.add_all((profile, link))
            await session.commit()
            actor_context = _context()
            async with minted_source(tmp_path / "scan-rollback", b"pending") as source:
                _, guide_item_id = await _seed_guide(
                    session,
                    context=actor_context,
                    content_hash=source.commitment.sha256,
                    media_type=source.commitment.media_type,
                )
                admission = await ArtifactAdmissionService(
                    session, settings, namespace
                ).admit(
                    GuideArtifactAdmissionRequest(
                        authorization_context=actor_context,
                        guide_source_item_id=UUID(guide_item_id),
                        source=source,
                    )
                )

            request_id = uuid4()
            real_authority = PreparedArtifactInternalAuthority(
                session,
                service_identity=ServiceIdentity.ARTIFACT_SCHEDULER,
                request_id=request_id,
                correlation_id=request_id,
            )

            async def publish_put(attempt_id: str) -> None:
                published.append(attempt_id)

            async def publish_job(_job_id: str) -> None:
                raise AssertionError("no verification job should be published")

            failing_scanner = ArtifactPendingWorkScanner(
                session,
                settings,
                _FailAfterConsumeAuthority(real_authority),
                publish_put,
                publish_job,
            )
            with pytest.raises(
                RuntimeError, match="injected failure after authorization consume"
            ):
                await failing_scanner.scan()

            assert published == []
            assert await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.action_id == ActionId.ARTIFACT_PENDING_WORK_SCAN.value
                )
            ) is None
            await session.rollback()

            retry_request_id = uuid4()
            recording = _RecordingAuthority(
                PreparedArtifactInternalAuthority(
                    session,
                    service_identity=ServiceIdentity.ARTIFACT_SCHEDULER,
                    request_id=retry_request_id,
                    correlation_id=retry_request_id,
                )
            )
            retry_scanner = ArtifactPendingWorkScanner(
                session,
                settings,
                recording,
                publish_put,
                publish_job,
            )
            assert await retry_scanner.scan() == 1
            assert published == [str(admission.attempt_id)]
            assert recording.consumed is not None
            assert recording.consumed.scanner_kind == "put_resolution_and_verification"
            assert recording.consumed.page_size == 1
            assert recording.consumed.put_attempt_ids == (admission.attempt_id,)
            assert recording.consumed.verification_job_ids == ()
            assert (
                datetime.fromisoformat(recording.consumed.database_cutoff_iso).tzinfo
                is not None
            )
            assert published == [str(value) for value in recording.consumed.put_attempt_ids]
            event = await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.action_id == ActionId.ARTIFACT_PENDING_WORK_SCAN.value
                )
            )
            assert event is not None and event.after_facts["allowed"] is True
            assert event.after_facts["resource_context_digest"] == (
                authorization_resource_digest(
                    artifact_authorization._resource_context(recording.consumed)
                )
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_put_claim_and_terminal_injected_failures_roll_back_both_sides(
    isolated_database_env: str,
    tmp_path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    actor_context = _context()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    profile, link = _service_principal(ServiceIdentity.ARTIFACT_PUT_RESOLVER)
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
            session.add_all((profile, link))
            await session.commit()
            async with minted_source(tmp_path / "atomic-put", b"atomic") as source:
                _, guide_item_id = await _seed_guide(
                    session,
                    context=actor_context,
                    content_hash=source.commitment.sha256,
                    media_type=source.commitment.media_type,
                )
                admission = await ArtifactAdmissionService(
                    session, settings, namespace
                ).admit(
                    GuideArtifactAdmissionRequest(
                        authorization_context=actor_context,
                        guide_source_item_id=UUID(guide_item_id),
                        source=source,
                    )
                )
                request_id = uuid4()
                authority = PreparedArtifactInternalAuthority(
                    session,
                    service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                    request_id=request_id,
                    correlation_id=request_id,
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, authority
                )
                original_claim = orchestrator._repo.claim_put_attempt

                async def fail_after_claim(**kwargs):
                    await original_claim(**kwargs)
                    raise RuntimeError("injected failure after ART claim mutation")

                orchestrator._repo.claim_put_attempt = fail_after_claim  # type: ignore[method-assign]
                with pytest.raises(
                    RuntimeError, match="injected failure after ART claim mutation"
                ):
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id, source=source
                    )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None and attempt.status == "prepared"
                assert attempt.executor_id is None and attempt.execution_generation == 0
                assert await session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.action_id
                        == ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE.value
                    )
                ) is None
                await session.rollback()

                retry_request_id = uuid4()
                retry_authority = PreparedArtifactInternalAuthority(
                    session,
                    service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                    request_id=retry_request_id,
                    correlation_id=retry_request_id,
                )
                retry = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, retry_authority
                )
                original_receipt = retry._repo.add_receipt

                async def fail_after_terminal_mutation(receipt):
                    await original_receipt(receipt)
                    raise RuntimeError("injected failure after ART terminal mutation")

                retry._repo.add_receipt = fail_after_terminal_mutation  # type: ignore[method-assign]
                with pytest.raises(
                    RuntimeError, match="injected failure after ART terminal mutation"
                ):
                    await retry.execute_committed_put(
                        attempt_id=admission.attempt_id, source=source
                    )
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None and attempt.status == "put_in_flight"
                assert attempt.executor_id is not None and attempt.execution_generation == 1
                assert await session.scalar(select(ArtifactOperationReceipt)) is None
                assert await session.scalar(select(ArtifactReplica)) is None
                events = list(
                    await session.scalars(
                        select(AuditEvent).where(
                            AuditEvent.action_id
                            == ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE.value
                        )
                    )
                )
                assert [event.after_facts["allowed"] for event in events] == [True]
                assert "resource_context_digest" in events[0].after_facts
                await session.rollback()

                await session.execute(
                    text(
                        "update artifact_put_attempts set lease_expires_at = "
                        "clock_timestamp() - interval '1 second' where id = :id"
                    ),
                    {"id": str(admission.attempt_id)},
                )
                await session.commit()
                final_request_id = uuid4()
                final = ArtifactStorageOrchestrator(
                    session,
                    store,
                    namespace,
                    settings,
                    PreparedArtifactInternalAuthority(
                        session,
                        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                        request_id=final_request_id,
                        correlation_id=final_request_id,
                    ),
                )
                assert await final.resolve_put_attempt(admission.attempt_id) == "observed_confirmed"
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None and attempt.status == "object_confirmed"
                assert await session.scalar(select(ArtifactReplica)) is not None
                events = list(
                    await session.scalars(
                        select(AuditEvent)
                        .where(
                            AuditEvent.action_id
                            == ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE.value
                        )
                        .order_by(AuditEvent.created_at, AuditEvent.id)
                    )
                )
                assert [event.after_facts["allowed"] for event in events] == [
                    True,
                    True,
                    True,
                ]
                assert all(
                    "resource_context_digest" in event.after_facts for event in events
                )
    finally:
        bootstrap.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_claim_and_scanner_denials_persist_without_art_side_effects(
    isolated_database_env: str,
    tmp_path,
) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"artifact_pending_work_scan_page_size": 1}
    )
    namespace = _namespace(settings)
    actor_context = _context()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    resolver = _service_principal(
        ServiceIdentity.ARTIFACT_PUT_RESOLVER, status="suspended"
    )
    scheduler = _service_principal(ServiceIdentity.ARTIFACT_SCHEDULER, status="suspended")
    published: list[str] = []
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
            session.add_all((*resolver, *scheduler))
            await session.commit()
            async with minted_source(tmp_path / "denied-claim", b"denied") as source:
                _, guide_item_id = await _seed_guide(
                    session,
                    context=actor_context,
                    content_hash=source.commitment.sha256,
                    media_type=source.commitment.media_type,
                )
                admission = await ArtifactAdmissionService(
                    session, settings, namespace
                ).admit(
                    GuideArtifactAdmissionRequest(
                        authorization_context=actor_context,
                        guide_source_item_id=UUID(guide_item_id),
                        source=source,
                    )
                )
                claim_request_id = uuid4()
                claim_authority = PreparedArtifactInternalAuthority(
                    session,
                    service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                    request_id=claim_request_id,
                    correlation_id=claim_request_id,
                )
                with pytest.raises(AuthorizationDenied):
                    await ArtifactStorageOrchestrator(
                        session, store, namespace, settings, claim_authority
                    ).execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                await session.rollback()
                await claim_authority.persist_denial()

            attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
            assert attempt is not None and attempt.status == "prepared"
            assert attempt.executor_id is None and attempt.execution_generation == 0
            assert await session.scalar(select(ArtifactOperationReceipt)) is None
            assert await session.scalar(select(ArtifactReplica)) is None
            await session.rollback()

            async def publish_put(attempt_id: str) -> None:
                published.append(attempt_id)

            async def publish_job(job_id: str) -> None:
                published.append(job_id)

            scan_request_id = uuid4()
            scan_authority = PreparedArtifactInternalAuthority(
                session,
                service_identity=ServiceIdentity.ARTIFACT_SCHEDULER,
                request_id=scan_request_id,
                correlation_id=scan_request_id,
            )
            with pytest.raises(AuthorizationDenied):
                await ArtifactPendingWorkScanner(
                    session,
                    settings,
                    scan_authority,
                    publish_put,
                    publish_job,
                ).scan()
            await session.rollback()
            await scan_authority.persist_denial()

            assert published == []
            events = list(
                await session.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.action_id.in_(
                            (
                                ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE.value,
                                ActionId.ARTIFACT_PENDING_WORK_SCAN.value,
                            )
                        )
                    )
                    .order_by(AuditEvent.created_at, AuditEvent.id)
                )
            )
            assert [event.after_facts["allowed"] for event in events] == [False, False]
            assert all("resource_context_digest" in event.after_facts for event in events)
            assert {event.denial_code for event in events} == {"actor_suspended"}
    finally:
        bootstrap.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_verification_claim_and_terminal_failures_roll_back_both_sides(
    isolated_database_env: str,
    tmp_path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    actor_context = _context()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    resolver = _service_principal(ServiceIdentity.ARTIFACT_PUT_RESOLVER)
    verifier = _service_principal(ServiceIdentity.ARTIFACT_VERIFIER)
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
            session.add_all((*resolver, *verifier))
            await session.commit()
            async with minted_source(tmp_path / "atomic-verify", b"verified") as source:
                _, guide_item_id = await _seed_guide(
                    session,
                    context=actor_context,
                    content_hash=source.commitment.sha256,
                    media_type=source.commitment.media_type,
                )
                admission = await ArtifactAdmissionService(
                    session, settings, namespace
                ).admit(
                    GuideArtifactAdmissionRequest(
                        authorization_context=actor_context,
                        guide_source_item_id=UUID(guide_item_id),
                        source=source,
                    )
                )
                put_request_id = uuid4()
                assert (
                    await ArtifactStorageOrchestrator(
                        session,
                        store,
                        namespace,
                        settings,
                        PreparedArtifactInternalAuthority(
                            session,
                            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                            request_id=put_request_id,
                            correlation_id=put_request_id,
                        ),
                    ).execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                    == "stored_pending_verification"
                )

            job = await session.scalar(select(ArtifactVerificationJob))
            assert job is not None
            job_id = UUID(job.id)
            await session.rollback()
            claim_request_id = uuid4()
            claim = ArtifactStorageOrchestrator(
                session,
                store,
                namespace,
                settings,
                PreparedArtifactInternalAuthority(
                    session,
                    service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                    request_id=claim_request_id,
                    correlation_id=claim_request_id,
                ),
            )
            original_claim = claim._repo.claim_verification_job

            async def fail_after_claim(**kwargs):
                await original_claim(**kwargs)
                raise RuntimeError("injected failure after verification claim mutation")

            claim._repo.claim_verification_job = fail_after_claim  # type: ignore[method-assign]
            with pytest.raises(
                RuntimeError, match="injected failure after verification claim mutation"
            ):
                await claim.verify_object(job_id)
            await session.refresh(job)
            assert job.status == "pending"
            assert job.executor_id is None and job.execution_generation == 0
            assert await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.action_id == ActionId.ARTIFACT_VERIFICATION_EXECUTE.value
                )
            ) is None
            await session.rollback()

            terminal_request_id = uuid4()
            terminal = ArtifactStorageOrchestrator(
                session,
                store,
                namespace,
                settings,
                PreparedArtifactInternalAuthority(
                    session,
                    service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                    request_id=terminal_request_id,
                    correlation_id=terminal_request_id,
                ),
            )
            original_receipt = terminal._repo.add_verification_receipt

            async def fail_after_terminal(receipt):
                await original_receipt(receipt)
                raise RuntimeError("injected failure after verification terminal mutation")

            terminal._repo.add_verification_receipt = fail_after_terminal  # type: ignore[method-assign]
            with pytest.raises(
                RuntimeError, match="injected failure after verification terminal mutation"
            ):
                await terminal.verify_object(job_id)
            await session.refresh(job)
            assert job.status == "running"
            assert job.executor_id is not None and job.execution_generation == 1
            assert await session.scalar(
                select(ArtifactVerificationReceipt)
            ) is None
            events = list(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.action_id
                        == ActionId.ARTIFACT_VERIFICATION_EXECUTE.value
                    )
                )
            )
            assert [event.after_facts["allowed"] for event in events] == [True]
            await session.rollback()

            await session.execute(
                text(
                    "update artifact_verification_jobs set lease_expires_at = "
                    "clock_timestamp() - interval '1 second' where id = :id"
                ),
                {"id": str(job_id)},
            )
            await session.commit()
            final_request_id = uuid4()
            assert (
                await ArtifactStorageOrchestrator(
                    session,
                    store,
                    namespace,
                    settings,
                    PreparedArtifactInternalAuthority(
                        session,
                        service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                        request_id=final_request_id,
                        correlation_id=final_request_id,
                    ),
                ).verify_object(job_id)
                == "verified"
            )
            await session.refresh(job)
            assert job.status == "verified"
            assert await session.scalar(
                select(ArtifactVerificationReceipt)
            ) is not None
            events = list(
                await session.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.action_id
                        == ActionId.ARTIFACT_VERIFICATION_EXECUTE.value
                    )
                    .order_by(AuditEvent.created_at, AuditEvent.id)
                )
            )
            assert [event.after_facts["allowed"] for event in events] == [
                True,
                True,
                True,
            ]
            assert all("resource_context_digest" in event.after_facts for event in events)
    finally:
        bootstrap.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_post_provider_revocation_commits_denial_but_no_terminal_artifact_facts(
    isolated_database_env: str,
    tmp_path,
) -> None:
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    actor_context = _context()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    profile_id, link_id = uuid4(), uuid4()
    assert settings.artifact_local_root is not None
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )

    class SuspendAfterPut:
        identity = store.identity

        async def put(self, source):
            result = await store.put(source)
            async with factory() as lifecycle_session:
                profile = await lifecycle_session.get(ActorProfile, str(profile_id))
                assert profile is not None
                profile.status = "suspended"
                profile.suspended_by = "test"
                profile.suspended_at = datetime.now(UTC)
                profile.suspension_reason = "post-provider security hold"
                await lifecycle_session.commit()
            return result

        async def observe_put_result(self, commitment):
            return await store.observe_put_result(commitment)

        def open(self, provider_object_ref, byte_range=None):
            return store.open(provider_object_ref, byte_range)

        async def head(self, provider_object_ref):
            return await store.head(provider_object_ref)

    try:
        async with factory() as session:
            session.add(
                ActorProfile(
                    id=str(profile_id),
                    actor_kind="service",
                    status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER.value,
                    created_by="test",
                )
            )
            session.add(
                ActorIdentityLink(
                    id=str(link_id),
                    actor_profile_id=str(profile_id),
                    issuer="https://issuer.example.test",
                    subject="artifact-put-resolver",
                    subject_kind="service",
                    status="active",
                    linked_by="test",
                )
            )
            await session.commit()
            async with minted_source(tmp_path / "post-provider-denial", b"protected") as source:
                _, guide_item_id = await _seed_guide(
                    session,
                    context=actor_context,
                    content_hash=source.commitment.sha256,
                    media_type=source.commitment.media_type,
                )
                admission = await ArtifactAdmissionService(
                    session, settings, namespace
                ).admit(
                    GuideArtifactAdmissionRequest(
                        authorization_context=actor_context,
                        guide_source_item_id=UUID(guide_item_id),
                        source=source,
                    )
                )
                request_id = uuid4()
                authority = PreparedArtifactInternalAuthority(
                    session,
                    service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                    request_id=request_id,
                    correlation_id=request_id,
                )
                orchestrator = ArtifactStorageOrchestrator(
                    session,
                    SuspendAfterPut(),
                    namespace,
                    settings,
                    authority,
                )
                with pytest.raises(AuthorizationDenied):
                    await orchestrator.execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=source,
                    )
                await session.rollback()
                await authority.persist_denial()
                attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
                assert attempt is not None
                assert attempt.status == "put_in_flight"
                assert attempt.executor_id is not None
                assert await session.scalar(select(ArtifactOperationReceipt)) is None
                assert await session.scalar(select(ArtifactReplica)) is None
                events = list(
                    await session.scalars(
                        select(AuditEvent)
                        .where(
                            AuditEvent.action_id
                            == ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE.value
                        )
                        .order_by(AuditEvent.created_at, AuditEvent.id)
                    )
                )
                assert [event.after_facts["allowed"] for event in events] == [True, False]
                assert all(
                    "resource_context_digest" in event.after_facts for event in events
                )
                assert events[-1].denial_code == "actor_suspended"
    finally:
        bootstrap.close()
        await engine.dispose()
