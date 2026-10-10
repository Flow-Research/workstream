"""Artifact-store composition and shared scratch construction."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.api_controls import request_ids
from app.api.deps.authorization import get_authorization_actor_identity
from app.adapters.checkers import PreSubmitCheckerExecutionAdapter, post_submission_executor, checker_output_reservations
from app.adapters.projects import project_locked_policy_context_port
from app.adapters.tasks import task_submission_context_port
from app.db.session import get_db_session, get_session_factory
from app.interfaces.artifact_operations import GuideArtifactIngestCommand
from app.modules.projects.api.guide_documents import GuideDocumentUploadTargetPort
from app.modules.artifacts.api import SubmissionBundlePreparationCommand
from app.modules.artifacts.api.task_import_source import TaskImportSourceCommandPort
from app.modules.checkers.api.materialization import PostSubmissionMaterializationPort
from app.modules.checkers.api.output_custody import (
    CheckerArtifactOutputPort,
    CheckerOutputBindingPort,
)
from app.interfaces.artifacts import (
    ARTIFACT_STORE_CAPABILITY_KEY,
    ArtifactConfigurationError,
    ArtifactProviderLiveProofRequiredError,
    ArtifactStoreBootstrap,
    ArtifactStoreNamespaceClaim,
)
from app.interfaces.external_services import ExternalServiceAdapterFactory
from app.modules.artifacts.preparation import (
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
)
from app.modules.artifacts.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.submission_authorization import (
    SubmissionBundlePreparationAuthorization,
)
from app.modules.artifacts.schemas import (
    ArtifactInternalAuthority,
)
from app.modules.artifacts.authorization import (
    GuideArtifactPreparedAuthorization,
    PreparedArtifactInternalAuthority,
    get_artifact_authorization_context,
    get_guide_artifact_prepared_authorization,
)
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.api import ActorIdentityFacts
from app.modules.tasks.api.guide_documents import TaskGuideDocumentsPort


from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.artifacts.pre_submit_evidence import PreSubmitEvidencePersistenceResult
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationRequest,
    PreparedBundlePreSubmitEvidenceService,
)
from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationRequest,
    PostSubmissionEvaluationResult,
    PostSubmissionExecutionPort,
)


class CheckerPhaseService:
    """One command per phase, composed from the canonical ART and CHECKER owners."""

    def __init__(
        self, *, pre_submission: PreparedBundlePreSubmitEvidenceService,
        post_submission: PostSubmissionExecutionPort,
    ) -> None:
        self._pre_submission = pre_submission
        self._post_submission = post_submission

    async def evaluate_pre_submission(
        self, request: PreparedBundleMaterializationRequest, reservation: object, *,
        preparation_request: SubmissionBundlePreparationRequest,
    ) -> PreSubmitEvidencePersistenceResult:
        """Finish ART's committed selection, preserving its exact canonical result."""
        if request.prepared_authorization is not None:
            raise ValueError("pre_submission_phase_requires_consumed_authorization")
        if isinstance(reservation, PreSubmitEvidencePersistenceResult):
            return reservation
        return await self._pre_submission.execute_reserved(
            request, reservation, preparation_request=preparation_request,
        )

    async def evaluate_post_submission(
        self, request: PostSubmissionEvaluationRequest,
    ) -> PostSubmissionEvaluationResult:
        """Delegate the closed post contract; production execution remains unavailable."""
        request = PostSubmissionEvaluationRequest.model_validate(request)
        result = PostSubmissionEvaluationResult.model_validate(
            await self._post_submission.evaluate_post_submission(request)
        )
        result.validate_request(request)
        return result


async def get_submission_bundle_preparation_actor(
    actor: Annotated[
        ActorIdentityFacts,
        Depends(get_authorization_actor_identity),
    ],
) -> ActorIdentityFacts:
    """Return dependency-safe AUTH facts to the route-facing ART command."""
    return actor


def create_artifact_store_bootstrap(settings: Settings) -> ArtifactStoreBootstrap:
    """Construct the selected store bootstrap through one typed factory.

    Args:
        settings: Validated application settings.

    Returns:
        Non-mutating configured artifact store bootstrap.

    Raises:
        ExternalServiceConfigurationError: If the provider is not registered.
    """
    require_artifact_runtime_eligible(settings)

    from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
    from app.adapters.artifacts.s3_compatible import (
        create_minio_artifact_store_bootstrap,
    )

    factory = ExternalServiceAdapterFactory[ArtifactStoreBootstrap](ARTIFACT_STORE_CAPABILITY_KEY)

    def create_local_store() -> ArtifactStoreBootstrap:
        """Pin the configured development-only LocalStorage provider root."""
        if settings.artifact_local_root is None:
            raise ArtifactConfigurationError("local artifact root is not configured")
        return LocalStorageBootstrap(
            LocalStorageAdapter(
                root=settings.artifact_local_root,
                buffer_bytes=settings.artifact_stream_buffer_bytes,
                lock_timeout_seconds=settings.artifact_operation_lock_timeout_seconds,
            )
        )

    factory.register("local", create_local_store)
    factory.register(
        "s3_compatible",
        lambda: create_minio_artifact_store_bootstrap(settings),
    )
    return factory.create(settings.artifact_store_backend)


def require_artifact_runtime_eligible(settings: Settings) -> None:
    """Reject configured providers that this chunk has not activated."""
    if (
        settings.artifact_store_backend == "s3_compatible"
        and settings.artifact_s3_provider_profile == "aws_s3"
    ):
        raise ArtifactProviderLiveProofRequiredError(
            "AWS artifact provider requires live deployment proof"
        )


def artifact_preparation_limits(settings: Settings) -> ArtifactPreparationLimits:
    """Map validated settings to the one process-independent scratch contract."""
    return ArtifactPreparationLimits(
        aggregate_reserved_bytes=settings.artifact_scratch_aggregate_reserved_bytes,
        maximum_files=settings.artifact_scratch_maximum_files,
        maximum_concurrency=settings.artifact_scratch_maximum_concurrency,
        minimum_free_bytes=settings.artifact_scratch_minimum_free_bytes,
        reservation_ttl_seconds=settings.artifact_scratch_reservation_ttl_seconds,
        total_deadline_seconds=settings.artifact_preparation_total_deadline_seconds,
        cleanup_margin_seconds=settings.artifact_scratch_cleanup_margin_seconds,
        stream_buffer_bytes=settings.artifact_stream_buffer_bytes,
        maximum_source_bytes=settings.artifact_maximum_bytes,
        maximum_workspace_entries=settings.artifact_scratch_maximum_workspace_entries,
    )


def submission_archive_limits(settings: Settings) -> SubmissionArchiveLimits:
    """Map validated settings to the fixed outer-ZIP safety contract."""
    return SubmissionArchiveLimits(
        maximum_entries=settings.artifact_submission_zip_maximum_entries,
        maximum_path_bytes=settings.artifact_submission_zip_maximum_path_bytes,
        maximum_path_depth=settings.artifact_submission_zip_maximum_path_depth,
        maximum_central_directory_bytes=(
            settings.artifact_submission_zip_maximum_central_directory_bytes
        ),
        maximum_entry_bytes=settings.artifact_submission_zip_maximum_entry_bytes,
        maximum_expanded_bytes=settings.artifact_submission_zip_maximum_expanded_bytes,
        maximum_compression_ratio=(settings.artifact_submission_zip_maximum_compression_ratio),
        maximum_inspection_seconds=(settings.artifact_submission_zip_maximum_inspection_seconds),
    )


def create_artifact_scratch_manager(settings: Settings) -> ArtifactScratchManager:
    """Construct a scratch manager from the canonical settings mapping."""
    if settings.artifact_scratch_root is None:
        raise ArtifactConfigurationError("artifact scratch root is not configured")
    return ArtifactScratchManager(
        root=settings.artifact_scratch_root,
        limits=artifact_preparation_limits(settings),
    )


def task_guide_documents_port(session: AsyncSession, settings: Settings) -> TaskGuideDocumentsPort:
    """Compose exact contributor originals without opening a provider for metadata."""
    from app.adapters.projects import project_guide_document_scope_port
    from app.modules.artifacts.guide_documents import SqlAlchemyGuideDocumentManifest
    from app.modules.artifacts.task_guide_documents import ArtifactTaskGuideDocuments
    from app.modules.artifacts.service import artifact_storage_namespace_spec

    @asynccontextmanager
    async def runtime():
        bootstrap = create_artifact_store_bootstrap(settings)
        manager = None
        try:
            manager = create_artifact_scratch_manager(settings)
            namespace = artifact_storage_namespace_spec(settings, bootstrap)
            store = bootstrap.initialize_after_namespace_claim(ArtifactStoreNamespaceClaim(
                adapter_identity=bootstrap.identity, namespace_identity=bootstrap.namespace_identity,
                namespace_fingerprint=namespace.namespace_fingerprint,
            ))
            yield store, namespace, ArtifactPreparationService(manager)
        finally:
            if manager is not None:
                manager.close()
            bootstrap.close()

    scope = project_guide_document_scope_port(session)
    return ArtifactTaskGuideDocuments(
        session, scope=scope, manifest=SqlAlchemyGuideDocumentManifest(session, scope), runtime=runtime,
    )


def get_artifact_internal_authority(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreparedArtifactInternalAuthority:
    """Use the activated fixed-service resolver for post-commit provider work."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    return PreparedArtifactInternalAuthority(
        session,
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        request_id=request_id,
        correlation_id=correlation_id,
    )


def get_guide_artifact_ingest_command(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[
        GuideArtifactPreparedAuthorization,
        Depends(get_guide_artifact_prepared_authorization),
    ],
    internal_authority: Annotated[
        PreparedArtifactInternalAuthority,
        Depends(get_artifact_internal_authority),
    ],
    targets: GuideDocumentUploadTargetPort,
) -> GuideArtifactIngestCommand:
    """Compose real guide ingest lazily so denial performs no provider I/O."""
    from app.modules.artifacts.service import (
        ArtifactAdmissionService,
        ArtifactStorageOrchestrator,
        GuideArtifactIngestService,
        PreparedGuideArtifactIngestCommand,
        artifact_storage_namespace_spec,
    )

    settings = request.app.state.settings

    @asynccontextmanager
    async def runtime():
        bootstrap = create_artifact_store_bootstrap(settings)
        try:
            manager = create_artifact_scratch_manager(settings)
        except BaseException:
            bootstrap.close()
            raise
        try:
            namespace = artifact_storage_namespace_spec(settings, bootstrap)
            store = bootstrap.initialize_after_namespace_claim(
                ArtifactStoreNamespaceClaim(
                    adapter_identity=bootstrap.identity,
                    namespace_identity=bootstrap.namespace_identity,
                    namespace_fingerprint=namespace.namespace_fingerprint,
                )
            )
            async with internal_authority.denial_boundary():
                yield (
                    ArtifactPreparationService(manager),
                    ArtifactAdmissionService(session, settings, namespace),
                    ArtifactStorageOrchestrator(
                        session,
                        store,
                        namespace,
                        settings,
                        internal_authority,
                    ),
                )
        finally:
            manager.close()
            bootstrap.close()

    from app.adapters.artifacts.internal_workers import continue_guide_setup_after_stored_document
    service = GuideArtifactIngestService(runtime, authority, continue_guide_setup_after_stored_document)
    return PreparedGuideArtifactIngestCommand(
        service, authority, targets,
        maximum_document_bytes=min(settings.artifact_maximum_bytes, settings.project_agent_max_document_bytes),
        maximum_total_bytes=settings.project_agent_max_total_document_bytes,
    )


def get_submission_bundle_preparation_authorization(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    context: Annotated[
        object,
        Depends(get_artifact_authorization_context),
    ],
):
    """Compose the active contributor PREP adapter from canonical AUTH context."""
    from app.modules.artifacts.authorization import (
        PreparedSubmissionBundlePreparationAuthorization,
    )

    return PreparedSubmissionBundlePreparationAuthorization(session, context)


def submission_admission_consumption_port(
    session: AsyncSession,
    *,
    request_id: UUID,
    correlation_id: UUID,
):
    """Compose the active fixed-service ART participant for the hidden transaction."""
    from app.modules.artifacts.authorization import PreparedSubmissionBindingAuthorization
    from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService

    return SubmissionAdmissionConsumptionService(
        session,
        PreparedSubmissionBindingAuthorization(
            session,
            request_id=request_id,
            correlation_id=correlation_id,
        ),
    )


def get_submission_bundle_preparation_command(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    internal_authority: Annotated[
        ArtifactInternalAuthority,
        Depends(get_artifact_internal_authority),
    ],
    authority: Annotated[
        SubmissionBundlePreparationAuthorization,
        Depends(get_submission_bundle_preparation_authorization),
    ],
) -> SubmissionBundlePreparationCommand:
    """Compose the sole hidden contributor preparation path from closed ART ports."""
    from app.modules.artifacts.authorization import (
        PreparedPreSubmitMaterializationAuthorization,
    )
    from app.modules.artifacts.service import (
        ArtifactAdmissionService,
        ArtifactStorageOrchestrator,
        artifact_storage_namespace_spec,
    )
    from app.modules.artifacts.submission_admission import SubmissionBundleDurablePutService
    from app.modules.artifacts.submission_archive import SubmissionArchiveInspector
    from app.modules.artifacts.submission_materialization import (
        PreparedBundleMaterializationService,
        PreparedBundlePreSubmitEvidenceService,
    )
    from app.modules.artifacts.submission_admission import (
        PreparedSubmissionBundlePreparationCommand,
        SubmissionBundlePreparationRuntime,
    )
    settings = request.app.state.settings
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    task_contexts = task_submission_context_port(session)
    project_contexts = project_locked_policy_context_port(session)

    @asynccontextmanager
    async def runtime():
        bootstrap = create_artifact_store_bootstrap(settings)
        try:
            manager = create_artifact_scratch_manager(settings)
        except BaseException:
            bootstrap.close()
            raise
        try:
            materialization_authority = PreparedPreSubmitMaterializationAuthorization(
                session,
                request_id=request_id,
                correlation_id=correlation_id,
            )
        except BaseException:
            manager.close()
            bootstrap.close()
            raise
        try:
            namespace = artifact_storage_namespace_spec(settings, bootstrap)
            store = bootstrap.initialize_after_namespace_claim(
                ArtifactStoreNamespaceClaim(
                    adapter_identity=bootstrap.identity,
                    namespace_identity=bootstrap.namespace_identity,
                    namespace_fingerprint=namespace.namespace_fingerprint,
                )
            )
            preparation = ArtifactPreparationService(manager)
            catalogue = request.app.state.pre_submission_checker_catalogue
            inspector = SubmissionArchiveInspector(submission_archive_limits(settings))
            checker_execution = PreSubmitCheckerExecutionAdapter(
                catalogue=catalogue,
                archive_inspector=inspector,
            )
            storage_schemes = {"local": "local", "s3_compatible": "s3"}
            try:
                storage_scheme = storage_schemes[settings.artifact_store_backend]
            except KeyError as exc:
                raise RuntimeError("unsupported artifact store backend") from exc
            materialization = PreparedBundleMaterializationService(
                session=session,
                authorization=materialization_authority,
                preparation=preparation,
                checker_execution=checker_execution,
                storage_scheme=storage_scheme,
            )
            admission = ArtifactAdmissionService(session, settings, namespace)
            storage = ArtifactStorageOrchestrator(
                session,
                store,
                namespace,
                settings,
                internal_authority,
            )
            evidence = PreparedBundlePreSubmitEvidenceService(
                session=session,
                materialization=materialization,
                preparation_authorization=authority,
                task_contexts=task_contexts,
                project_contexts=project_contexts,
            )
            from app.adapters.checkers import submission_evaluation_content

            yield SubmissionBundlePreparationRuntime(
                evaluation_content=submission_evaluation_content,
                preparation=preparation,
                inspector=inspector,
                catalogue=catalogue,
                materialization=materialization,
                evidence=evidence,
                checker_service=CheckerPhaseService(
                    pre_submission=evidence,
                    post_submission=post_submission_executor(
                        sessions=get_session_factory(), materialization=post_submission_materialization(
                            sessions=get_session_factory(), store=store, namespace=namespace,
                            preparation=preparation, inspector=inspector)),
                ),
                durable_put=SubmissionBundleDurablePutService(
                    session=session,
                    admission=admission,
                    storage=storage,
                    authorization=authority,
                    task_contexts=task_contexts,
                    project_contexts=project_contexts,
                ),
            )
        finally:
            materialization_authority.close()
            manager.close()
            bootstrap.close()

    return PreparedSubmissionBundlePreparationCommand(
        session=session,
        authority=authority,
        task_contexts=task_contexts,
        project_contexts=project_contexts,
        runtime_factory=runtime,
    )


async def cleanup_stale_artifact_scratch(settings: Settings) -> int:
    """Run one database-independent stale cleanup with shared construction."""
    require_artifact_runtime_eligible(settings)
    manager = create_artifact_scratch_manager(settings)
    try:
        return await manager.cleanup_stale()
    finally:
        manager.close()


def guide_document_manifest_port(session: AsyncSession):
    """Compose ART's metadata-only current document manifest capability."""
    from app.modules.artifacts.guide_documents import SqlAlchemyGuideDocumentManifest
    from app.adapters.projects import project_guide_document_scope_port
    return SqlAlchemyGuideDocumentManifest(session, project_guide_document_scope_port(session))


@asynccontextmanager
async def guide_document_access_runtime(session_factory, attempt_id, manifest, configuration):
    """Own ART provider/scratch composition for the already-fenced setup attempt."""
    from uuid import uuid4
    from app.core.config import get_settings
    from app.adapters.artifacts.internal_workers import (
        initialize_artifact_internal_runtime, _artifact_internal_runtime,
    )
    from app.adapters.projects import project_guide_document_scope_port
    from app.modules.artifacts.guide_document_access import ScopedGuideDocumentGrant
    from app.modules.artifacts.authorization import PreparedGuideSourceReadAuthorization

    await initialize_artifact_internal_runtime()
    manager = create_artifact_scratch_manager(get_settings())
    try:
        with _artifact_internal_runtime() as (store, namespace):
            def authority(session):
                request_id = uuid4()
                return PreparedGuideSourceReadAuthorization(
                    session, request_id=request_id, correlation_id=request_id,
                )
            grant = ScopedGuideDocumentGrant(
                session_factory, store, namespace, ArtifactPreparationService(manager), authority,
                scope_factory=project_guide_document_scope_port, manifest_factory=guide_document_manifest_port,
                attempt_id=attempt_id, manifest=manifest,
                lifetime_seconds=configuration.timeout_seconds,
                maximum_document_bytes=configuration.maximum_document_bytes,
            )
            try:
                yield grant
            finally:
                await grant.close()
    finally:
        manager.close()


def post_submission_materialization(*, sessions, store, namespace, preparation, inspector) -> PostSubmissionMaterializationPort:
    """Compose exact input with fresh materializer authority and CHECKERS lease custody."""
    from app.adapters.tasks import submitted_bundle_port
    from app.modules.artifacts.post_submit_materialization import PostSubmissionMaterializer
    from app.adapters.auth import post_submit_materialization_authority
    from app.adapters.checkers import current_post_submit_execution
    return PostSubmissionMaterializer(
        sessions=sessions, tasks=submitted_bundle_port, store=store, namespace=namespace,
        preparation=preparation, inspector=inspector,
        authority=post_submit_materialization_authority,
        current_execution=current_post_submit_execution,
    )


def checker_output_storage(
    *, sessions, store, namespace, preparation, settings
) -> CheckerArtifactOutputPort:
    """Compose hidden output custody; live producer and write authority remain absent."""
    from app.modules.artifacts.checker_outputs import CheckerArtifactOutputService, DenyCheckerOutputWriteAuthority
    from app.modules.artifacts.schemas import DenyArtifactInternalAuthority
    return CheckerArtifactOutputService(
        sessions=sessions, store=store, namespace=namespace, preparation=preparation, settings=settings,
        reservations=checker_output_reservations,
        authority=lambda session: DenyCheckerOutputWriteAuthority(),
        internal_authority=lambda session: DenyArtifactInternalAuthority(),
    )


def checker_output_binding(session, *, namespace) -> CheckerOutputBindingPort:
    """Compose a deny-only caller-transaction binding participant."""
    from app.modules.artifacts.checker_output_bindings import CheckerOutputBindingService, DenyCheckerOutputBindingAuthority
    return CheckerOutputBindingService(session, namespace_fingerprint=namespace.namespace_fingerprint,
        reservations=checker_output_reservations(session), authority=DenyCheckerOutputBindingAuthority())


async def get_task_import_source_commands(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    context: Annotated[object, Depends(get_artifact_authorization_context)],
) -> TaskImportSourceCommandPort:
    """Compose exact source commands in ART's registered owner root."""
    from app.adapters.auth import task_import_source_authorization
    from app.modules.artifacts.service import (
        ArtifactAdmissionService, ArtifactStorageOrchestrator, artifact_storage_namespace_spec,
    )
    from app.modules.artifacts.task_import_sources import ArtifactTaskImportSourceCommands, TaskImportSourceRuntime

    settings = request.app.state.settings
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    # Identity provisioning is committed by its owner. As in TASK commands,
    # discard the resolver's read-only refresh before ART owns each root.
    await session.rollback()

    @asynccontextmanager
    async def runtime():
        bootstrap = create_artifact_store_bootstrap(settings)
        manager = None
        authorities = []
        try:
            manager = create_artifact_scratch_manager(settings)
            namespace = artifact_storage_namespace_spec(settings, bootstrap)
            store = bootstrap.initialize_after_namespace_claim(ArtifactStoreNamespaceClaim(
                adapter_identity=bootstrap.identity, namespace_identity=bootstrap.namespace_identity,
                namespace_fingerprint=namespace.namespace_fingerprint,
            ))
            for identity in (ServiceIdentity.ARTIFACT_PUT_RESOLVER, ServiceIdentity.ARTIFACT_VERIFIER):
                authorities.append(PreparedArtifactInternalAuthority(
                    session, service_identity=identity, request_id=request_id, correlation_id=correlation_id,
                ))
            async with authorities[0].denial_boundary(), authorities[1].denial_boundary():
                yield TaskImportSourceRuntime(
                    store, namespace, ArtifactPreparationService(manager), ArtifactAdmissionService(session, settings, namespace),
                    ArtifactStorageOrchestrator(session, store, namespace, settings, authorities[0]),
                    ArtifactStorageOrchestrator(session, store, namespace, settings, authorities[1]),
                )
        finally:
            for authority in authorities:
                authority.discard()
            if manager is not None:
                manager.close()
            bootstrap.close()

    return ArtifactTaskImportSourceCommands(
        session, actor_profile_id=context.actor_profile_id,
        identity_link_id=context.identity_link_id,
        authorization=task_import_source_authorization(session, context), runtime=runtime,
    )
