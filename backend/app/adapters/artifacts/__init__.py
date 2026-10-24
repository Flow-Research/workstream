"""Artifact-store composition and shared scratch construction."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import Callable
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.api_controls import request_ids
from app.api.deps.authorization import get_authorization_actor_identity
from app.adapters.projects import project_locked_policy_context_port
from app.adapters.tasks import task_submission_context_port
from app.db.session import get_db_session, get_session_factory
from app.interfaces.artifact_operations import GuideArtifactIngestCommand
from app.modules.projects.api.guide_documents import GuideDocumentUploadTargetPort
from app.modules.model_usage.api import (
    SetupModelArtifactOutputPort,
    SetupModelOutputBindingPort,
    SetupModelUsageOwnerPort,
)
from app.modules.artifacts.api import SubmissionBundlePreparationCommand
from app.modules.artifacts.api.task_import_source import TaskImportSourceCommandPort
from app.modules.checkers.api.materialization import PostSubmissionMaterializationPort
from app.modules.checkers.api.materialization import (
    PostSubmissionMaterialConsumer,
    PostSubmissionMaterializationResult,
)
from app.modules.checkers.api.execution import ExecuteFacts
from app.modules.checkers.api.output_custody import (
    CheckerArtifactOutputPort,
    CheckerOutputBindingPort,
)
from app.interfaces.artifacts import (
    ARTIFACT_STORE_CAPABILITY_KEY,
    ArtifactConfigurationError,
    ArtifactProviderActivationGuard,
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
from app.modules.projects.api.guide_reads import ProjectGuideDocumentContentPort


async def get_submission_bundle_preparation_actor(
    actor: Annotated[
        ActorIdentityFacts,
        Depends(get_authorization_actor_identity),
    ],
) -> ActorIdentityFacts:
    """Return dependency-safe AUTH facts to the route-facing ART command."""
    return actor


def artifact_provider_activation_guard(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession] | None = None,
) -> ArtifactProviderActivationGuard | None:
    """Compose the ART-owned guard and resolve DB state only for native AWS."""
    if not (
        settings.artifact_store_backend == "s3_compatible"
        and settings.artifact_s3_provider_profile == "aws_s3"
    ):
        return None
    from app.modules.artifacts.provider_activation import (
        SqlAlchemyArtifactProviderActivationGuard,
    )

    sessions = sessions or get_session_factory()
    return SqlAlchemyArtifactProviderActivationGuard(sessions, settings)


def create_artifact_store_bootstrap(
    settings: Settings,
    *,
    activation_guard: ArtifactProviderActivationGuard | None,
) -> ArtifactStoreBootstrap:
    """Construct the selected store bootstrap through one typed factory.

    Args:
        settings: Validated application settings.

    Returns:
        Non-mutating configured artifact store bootstrap.

    Raises:
        ExternalServiceConfigurationError: If the provider is not registered.
    """
    if (
        settings.artifact_store_backend == "s3_compatible"
        and settings.artifact_s3_provider_profile == "aws_s3"
        and activation_guard is None
    ):
        raise ArtifactProviderLiveProofRequiredError(
            "AWS artifact provider requires an activation guard"
        )
    from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
    from app.adapters.artifacts.s3_compatible import (
        create_s3_compatible_artifact_store_bootstrap,
    )

    factory = ExternalServiceAdapterFactory[ArtifactStoreBootstrap](ARTIFACT_STORE_CAPABILITY_KEY)

    def create_local_store() -> ArtifactStoreBootstrap:
        """Pin the configured development-only LocalStorage provider root."""
        if activation_guard is not None:
            raise ArtifactConfigurationError("local artifact storage cannot use AWS activation")
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
        lambda: create_s3_compatible_artifact_store_bootstrap(
            settings,
            activation_guard=activation_guard,
        ),
    )
    return factory.create(settings.artifact_store_backend)


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


def artifact_preparation_service(manager: ArtifactScratchManager) -> ArtifactPreparationService:
    """Construct the public composition root's canonical stream preparation owner."""
    return ArtifactPreparationService(manager)


def configured_artifact_storage_namespace(settings: Settings, bootstrap):
    """Derive the immutable namespace through the existing ART composition root."""
    from app.modules.artifacts.service import artifact_storage_namespace_spec

    return artifact_storage_namespace_spec(settings, bootstrap)


async def validate_configured_artifact_storage_namespace(bootstrap, settings, sessions):
    """Validate startup namespace custody without exposing the private ART service."""
    from app.modules.artifacts.service import validate_artifact_storage_namespace_at_startup

    return await validate_artifact_storage_namespace_at_startup(bootstrap, settings, sessions)


def _guide_original_runtime(settings: Settings):
    """Open the provider, namespace and scratch only when a verified original read begins."""
    from app.modules.artifacts.service import artifact_storage_namespace_spec

    @asynccontextmanager
    async def runtime():
        bootstrap = create_artifact_store_bootstrap(
            settings,
            activation_guard=artifact_provider_activation_guard(settings),
        )
        manager = None
        try:
            manager = create_artifact_scratch_manager(settings)
            namespace = artifact_storage_namespace_spec(settings, bootstrap)
            store = bootstrap.initialize_after_namespace_claim(
                ArtifactStoreNamespaceClaim(
                    adapter_identity=bootstrap.identity,
                    namespace_identity=bootstrap.namespace_identity,
                    namespace_fingerprint=namespace.namespace_fingerprint,
                )
            )
            yield store, namespace, ArtifactPreparationService(manager)
        finally:
            if manager is not None:
                manager.close()
            bootstrap.close()

    return runtime


def task_guide_documents_port(session: AsyncSession, settings: Settings) -> TaskGuideDocumentsPort:
    """Compose exact contributor originals without opening a provider for metadata."""
    from app.adapters.projects import project_guide_document_scope_port
    from app.modules.artifacts.guide_documents import SqlAlchemyGuideDocumentManifest
    from app.modules.artifacts.task_guide_documents import ArtifactTaskGuideDocuments

    scope = project_guide_document_scope_port(session)
    return ArtifactTaskGuideDocuments(
        session,
        scope=scope,
        manifest=SqlAlchemyGuideDocumentManifest(session, scope),
        runtime=_guide_original_runtime(settings),
    )


def project_guide_documents_port(
    session: AsyncSession, settings: Settings
) -> ProjectGuideDocumentContentPort:
    """Compose a Project Manager's verified original read; the provider opens only on ``open``."""
    from app.adapters.projects import project_guide_document_scope_port
    from app.modules.artifacts.guide_documents import SqlAlchemyGuideDocumentManifest
    from app.modules.artifacts.task_guide_documents import ArtifactProjectGuideDocuments

    return ArtifactProjectGuideDocuments(
        session,
        manifest=SqlAlchemyGuideDocumentManifest(
            session, project_guide_document_scope_port(session)
        ),
        runtime=_guide_original_runtime(settings),
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
        bootstrap = create_artifact_store_bootstrap(
            settings,
            activation_guard=artifact_provider_activation_guard(settings),
        )
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

    service = GuideArtifactIngestService(
        runtime, authority, continue_guide_setup_after_stored_document
    )
    return PreparedGuideArtifactIngestCommand(
        service,
        authority,
        targets,
        maximum_document_bytes=min(
            settings.artifact_maximum_bytes, settings.project_agent_max_document_bytes
        ),
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
        bootstrap = create_artifact_store_bootstrap(
            settings,
            activation_guard=artifact_provider_activation_guard(settings),
        )
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
            inspector = SubmissionArchiveInspector(submission_archive_limits(settings))
            from app.adapters.auth import selected_pre_submit_authority
            from app.adapters.checkers import selected_pre_submit_checker_execution
            from app.modules.artifacts.selected_pre_submit_execution import (
                SelectedPreSubmitExecutionService,
            )
            from app.adapters.checkers import selected_pre_submit_coordinator

            checker_execution = selected_pre_submit_checker_execution(
                settings=settings,
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
            selected_coordinator = selected_pre_submit_coordinator(session)

            yield SubmissionBundlePreparationRuntime(
                preparation=preparation,
                inspector=inspector,
                materialization=materialization,
                selected_coordinator=selected_coordinator,
                selected_execution=SelectedPreSubmitExecutionService(
                    session=session,
                    coordinator=selected_coordinator,
                    authority=selected_pre_submit_authority(session),
                    materialization=materialization,
                ),
                storage_scheme=storage_scheme,
                artifact_deadline_ms=int(
                    settings.artifact_preparation_total_deadline_seconds * 1000
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
        _artifact_internal_runtime,
        _artifact_worker_database,
        initialize_artifact_internal_runtime,
    )
    from app.adapters.projects import project_guide_document_scope_port
    from app.modules.artifacts.guide_document_access import ScopedGuideDocumentGrant
    from app.modules.artifacts.authorization import PreparedGuideSourceReadAuthorization

    async with _artifact_worker_database():
        await initialize_artifact_internal_runtime()
        manager = create_artifact_scratch_manager(get_settings())
        try:
            with _artifact_internal_runtime() as (store, namespace):

                def authority(session):
                    request_id = uuid4()
                    return PreparedGuideSourceReadAuthorization(
                        session,
                        request_id=request_id,
                        correlation_id=request_id,
                    )

                grant = ScopedGuideDocumentGrant(
                    session_factory,
                    store,
                    namespace,
                    ArtifactPreparationService(manager),
                    authority,
                    scope_factory=project_guide_document_scope_port,
                    manifest_factory=guide_document_manifest_port,
                    attempt_id=attempt_id,
                    manifest=manifest,
                    lifetime_seconds=configuration.timeout_seconds,
                    maximum_document_bytes=configuration.maximum_document_bytes,
                )
                try:
                    yield grant
                finally:
                    await grant.close()
        finally:
            manager.close()


def post_submission_materialization(
    *, sessions, store, namespace, preparation, inspector
) -> PostSubmissionMaterializationPort:
    """Compose exact input with fresh materializer authority and CHECKERS lease custody."""
    from app.adapters.tasks import submitted_bundle_port, task_evaluation_revision_port
    from app.modules.artifacts.post_submit_materialization import PostSubmissionMaterializer
    from app.adapters.auth import post_submit_materialization_authority
    from app.adapters.checkers import current_post_submit_execution, revision_feedback_port

    return PostSubmissionMaterializer(
        sessions=sessions,
        tasks=submitted_bundle_port,
        store=store,
        namespace=namespace,
        preparation=preparation,
        inspector=inspector,
        authority=post_submit_materialization_authority,
        current_execution=current_post_submit_execution,
        revision_tasks=task_evaluation_revision_port,
        revision_feedback=revision_feedback_port,
    )


class _WorkerPostSubmissionMaterialization:
    """Lease the Celery ART provider only while one exact materialization runs."""

    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def materialize(
        self,
        facts: ExecuteFacts,
        consumer: PostSubmissionMaterialConsumer,
    ) -> PostSubmissionMaterializationResult:
        from app.core.config import get_settings
        from app.adapters.artifacts.internal_workers import (
            _artifact_internal_runtime,
            _artifact_worker_database,
            initialize_artifact_internal_runtime,
        )
        from app.modules.artifacts.submission_archive import SubmissionArchiveInspector
        from app.modules.checkers.api.external_policy import (
            ExternalCheckerPolicyError,
            selected_post_submit_execution_budget_ms,
        )
        from app.modules.checkers.api.materialization import (
            PostSubmissionMaterializationFailure,
        )

        settings = get_settings()
        try:
            selected_post_submit_execution_budget_ms(
                facts.request.policy,
                artifact_deadline_ms=int(
                    settings.artifact_preparation_total_deadline_seconds * 1000
                ),
            )
        except ExternalCheckerPolicyError:
            raise PostSubmissionMaterializationFailure(
                "post_submit_material_deadline_unavailable"
            ) from None
        async with _artifact_worker_database():
            await initialize_artifact_internal_runtime()
            with _artifact_internal_runtime() as (store, namespace):
                manager = create_artifact_scratch_manager(settings)
                try:
                    return await post_submission_materialization(
                        sessions=self._sessions,
                        store=store,
                        namespace=namespace,
                        preparation=ArtifactPreparationService(manager),
                        inspector=SubmissionArchiveInspector(submission_archive_limits(settings)),
                    ).materialize(facts, consumer)
                finally:
                    manager.close()


def worker_post_submission_materialization(*, sessions) -> PostSubmissionMaterializationPort:
    """Build the hidden request handler's lazy worker-owned ART input port."""
    return _WorkerPostSubmissionMaterialization(sessions)


def checker_output_storage(
    *, sessions, store, namespace, preparation, settings, reservations
) -> CheckerArtifactOutputPort:
    """Compose private call evidence through canonical admission and verification."""
    from app.adapters.auth import checker_output_write_authorization
    from app.modules.artifacts.checker_outputs import CheckerArtifactOutputService
    from uuid import uuid4

    def authority(session, identity):
        request_id = uuid4()
        return PreparedArtifactInternalAuthority(
            session,
            service_identity=identity,
            request_id=request_id,
            correlation_id=request_id,
        )

    return CheckerArtifactOutputService(
        sessions=sessions,
        store=store,
        namespace=namespace,
        preparation=preparation,
        settings=settings,
        reservations=reservations,
        authority=checker_output_write_authorization,
        internal_authority=lambda session: authority(
            session, ServiceIdentity.ARTIFACT_PUT_RESOLVER
        ),
        verification_authority=lambda session: authority(
            session, ServiceIdentity.ARTIFACT_VERIFIER
        ),
    )


def checker_output_binding(session, *, namespace, reservations) -> CheckerOutputBindingPort:
    """Bind one exact private call effect to independently verified ART bytes."""
    from app.adapters.auth import checker_output_binding_authorization
    from app.modules.artifacts.checker_output_bindings import CheckerOutputBindingService

    return CheckerOutputBindingService(
        session,
        namespace_fingerprint=namespace.namespace_fingerprint,
        reservations=reservations,
        authority=checker_output_binding_authorization(session),
    )


def setup_model_output_storage(
    *,
    sessions,
    store,
    namespace,
    preparation,
    settings,
    owner: Callable[[AsyncSession], SetupModelUsageOwnerPort],
) -> SetupModelArtifactOutputPort:
    """Compose setup request/response custody without importing PROJECTS into MODEL-USAGE."""
    from app.adapters.model_usage import setup_model_output_reservations

    return cast(
        SetupModelArtifactOutputPort,
        checker_output_storage(
            sessions=sessions,
            store=store,
            namespace=namespace,
            preparation=preparation,
            settings=settings,
            reservations=lambda session: setup_model_output_reservations(
                session, owner=owner(session)
            ),
        ),
    )


def setup_model_output_binding(
    session,
    *,
    namespace,
    owner: SetupModelUsageOwnerPort,
) -> SetupModelOutputBindingPort:
    """Compose exact setup-effect publication through the shared ART binding path."""
    from app.adapters.model_usage import setup_model_output_reservations

    return cast(
        SetupModelOutputBindingPort,
        checker_output_binding(
            session,
            namespace=namespace,
            reservations=setup_model_output_reservations(session, owner=owner),
        ),
    )


def checker_model_evidence(session):
    """Expose verified call binding facts to CHECKERS without transcript bytes."""
    from app.modules.artifacts.checker_model_evidence import CheckerModelEvidence

    return CheckerModelEvidence(session)


def setup_model_evidence(session):
    """Expose verified setup-effect bindings to MODEL-USAGE without transcript bytes."""
    from app.modules.artifacts.checker_model_evidence import SetupModelEvidence

    return SetupModelEvidence(session)


async def get_task_import_source_commands(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    context: Annotated[object, Depends(get_artifact_authorization_context)],
) -> TaskImportSourceCommandPort:
    """Capture actor facts, then compose the same source owner for public commands."""
    await session.rollback()
    return task_import_source_commands(
        session, settings=request.app.state.settings, context=context
    )


def task_import_source_commands(session: AsyncSession, *, settings, context):
    """Compose source reads/bindings and lazy provider runtime through one owner path."""
    from app.adapters.auth import task_import_source_authorization
    from app.modules.artifacts.service import (
        ArtifactAdmissionService,
        ArtifactStorageOrchestrator,
        artifact_storage_namespace_spec,
    )
    from app.modules.artifacts.task_import_sources import (
        ArtifactTaskImportSourceCommands,
        TaskImportSourceRuntime,
    )

    request_id, correlation_id = context.request_id, context.correlation_id

    @asynccontextmanager
    async def runtime():
        bootstrap = create_artifact_store_bootstrap(
            settings,
            activation_guard=artifact_provider_activation_guard(settings),
        )
        manager = None
        authorities = []
        try:
            manager = create_artifact_scratch_manager(settings)
            namespace = artifact_storage_namespace_spec(settings, bootstrap)
            store = bootstrap.initialize_after_namespace_claim(
                ArtifactStoreNamespaceClaim(
                    adapter_identity=bootstrap.identity,
                    namespace_identity=bootstrap.namespace_identity,
                    namespace_fingerprint=namespace.namespace_fingerprint,
                )
            )
            for identity in (
                ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                ServiceIdentity.ARTIFACT_VERIFIER,
            ):
                authorities.append(
                    PreparedArtifactInternalAuthority(
                        session,
                        service_identity=identity,
                        request_id=request_id,
                        correlation_id=correlation_id,
                    )
                )
            yield TaskImportSourceRuntime(
                store,
                namespace,
                ArtifactPreparationService(manager),
                ArtifactAdmissionService(session, settings, namespace),
                ArtifactStorageOrchestrator(session, store, namespace, settings, authorities[0]),
                ArtifactStorageOrchestrator(session, store, namespace, settings, authorities[1]),
                authorities[0].denial_boundary,
                authorities[1].denial_boundary,
            )
        finally:
            for authority in authorities:
                authority.discard()
            if manager is not None:
                manager.close()
            bootstrap.close()

    return ArtifactTaskImportSourceCommands(
        session,
        actor_profile_id=context.actor_profile_id,
        identity_link_id=context.identity_link_id,
        authorization=task_import_source_authorization(session, context),
        runtime=runtime,
    )


def submission_bundle_preparation_reader(session: AsyncSession):
    """Compose ART's preparation projection over CHECKERS' retained selected runs."""
    from app.adapters.checkers import selected_pre_submit_run_reader
    from app.modules.artifacts.preparation_reads import SubmissionBundlePreparationReader

    return SubmissionBundlePreparationReader(session, runs=selected_pre_submit_run_reader(session))
