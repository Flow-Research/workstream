"""PROJECTS orchestration of the sole live guide-compilation operation."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.projects.api.guide_documents import GuideDocumentManifestPort
from app.modules.projects.api.task_examples import (
    GuideTaskExampleInputError, require_task_example_commitment,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ProjectGuideCompilationAuthorizationPort,
)
from app.modules.checkers.api.pre_submit_catalogue import PreSubmissionCapabilityProjection
from app.modules.checkers.api.post_submit_catalogue import PostSubmitCatalogue
from app.modules.projects.api.guide_compilation import (
    ProjectGuideCompilationDelivery,
    ProjectGuideCompilationDeliveryError,
    ProjectGuideCompilationExecutionCommand,
    ProjectGuideCompilationExecutionPort,
    ProjectGuideCompilationExecutionClassification,
    ProjectGuideSetupFinalizationCommand,
)
from app.modules.projects.api.guide_compilation_projections import ProjectGuideProjectionCommand
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.models import ProjectSetupRun
from .source_state import is_compilation_source_setup
from .diagnostics import compilation_setup_response
from .automatic_request import AutomaticCompilationInputs, automatic_operation_id
from .models import (
    ProjectGuideCompilationAttempt,
    ProjectGuideCompilation,
    ProjectGuideSetupFinalization,
)
from .repository import GuideCompilationIntegrityError
from .service import GuideCompilationService
from .finalization import GuideCompilationFinalizationService

RequestAuthority = Callable[
    [AsyncSession, UUID],
    AbstractAsyncContextManager[
        tuple[ProjectGuideCompilationAuthorizationPort, ActorIdentityFacts]
    ],
]


class LiveGuideCompilationCoordinator:
    """Reuse request, execution, projection and finalization owners in their transactions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        material_factory: Callable[[AsyncSession], GuideDocumentManifestPort],
        pre_capabilities: PreSubmissionCapabilityProjection,
        post_capabilities: PostSubmitCatalogue,
        request_authority: RequestAuthority,
        configuration_factory: Callable[[], ProjectGuideRuntimeConfiguration],
        execution: ProjectGuideCompilationExecutionPort,
        projections,
        finalization_authorization_factory,
    ) -> None:
        self._sessions = session_factory
        self._material = material_factory
        self._pre = pre_capabilities
        self._post = post_capabilities
        self._request_authority = request_authority
        self._configuration = configuration_factory
        self._execution = execution
        self._projections = projections
        self._finalization_authorization = finalization_authorization_factory

    async def run(self, delivery: ProjectGuideCompilationDelivery) -> dict:
        """Admit the exact delivery and finish only its existing immutable generation."""
        try:
            finalization, has_attempt, snapshot = await self._admit(delivery)
        except GuideTaskExampleInputError as exc:
            return {
                "status": "setup_input_invalid", "error_code": exc.code,
                "error_summary": "Create a new guide version with at least one task example.",
            }
        if finalization is not None:
            return await self._finalize(finalization)
        if has_attempt and snapshot is None:
            raise GuideCompilationIntegrityError("compilation runtime configuration unavailable")
        configuration = (
            ProjectGuideRuntimeConfiguration.model_validate(snapshot)
            if snapshot is not None else self._configuration()
        )
        operation_id = automatic_operation_id(delivery.setup_run_id, delivery.setup_generation)
        async with self._sessions() as session:
            async with self._request_authority(session, operation_id) as (authority, actor):
                request = await GuideCompilationService(
                    session,
                    authority,
                    automatic_inputs=AutomaticCompilationInputs(
                        self._material(session),
                        self._pre,
                        self._post,
                        configuration,
                    ),
                ).request_automatic(actor=actor, setup_run_id=delivery.setup_run_id)
        outcome = await self._execution.execute(
            ProjectGuideCompilationExecutionCommand(attempt_id=request.attempt_id)
        )
        if outcome.classification is not ProjectGuideCompilationExecutionClassification.PERSISTED:
            async with self._sessions() as session:
                setup = await session.get(ProjectSetupRun, str(delivery.setup_run_id))
                if setup is None:
                    raise GuideCompilationIntegrityError("compilation setup unavailable")
                diagnostic = await compilation_setup_response(session, setup)
            return {
                "status": diagnostic.status,
                "attempt_id": str(outcome.attempt_id),
                "error_code": diagnostic.error_code,
                "error_summary": diagnostic.error_summary,
                "finished_at": diagnostic.finished_at.isoformat()
                if diagnostic.finished_at
                else None,
            }
        async with self._sessions() as session:
            compilation = await session.scalar(
                select(ProjectGuideCompilation).where(
                    ProjectGuideCompilation.id == outcome.compilation_id,
                    ProjectGuideCompilation.attempt_id == outcome.attempt_id,
                    ProjectGuideCompilation.setup_run_id == str(delivery.setup_run_id),
                )
            )
            if compilation is None:
                raise GuideCompilationIntegrityError("persisted compilation unavailable")
            blocked = compilation.canonical_result["status"] == "guide_blocked"
        command = ProjectGuideProjectionCommand(attempt_id=outcome.attempt_id)
        await self._projections.project_guide_sufficiency(command)
        if not blocked:
            await self._projections.project_submission_artifact_policy(command)
        return await self._finalize(
            ProjectGuideSetupFinalizationCommand(
                project_id=delivery.project_id,
                guide_id=delivery.guide_id,
                setup_run_id=delivery.setup_run_id,
                setup_generation=delivery.setup_generation,
                compilation_id=outcome.compilation_id,
            )
        )

    async def _admit(self, delivery: ProjectGuideCompilationDelivery):
        """Normalize only the exact transport claim, before any compilation effects."""
        expected_task = project_guide_compilation_task_id(
            str(delivery.setup_run_id),
            delivery.setup_generation,
        )
        if str(delivery.task_id) != expected_task:
            raise ProjectGuideCompilationDeliveryError()
        async with self._sessions() as session, session.begin():
            repository = ProjectRepository(session)
            guide = await repository.lock_project_guide(str(delivery.guide_id))
            if (
                guide is None
                or guide.project_id != str(delivery.project_id)
                or guide.status != "draft"
            ):
                raise ProjectGuideCompilationDeliveryError()
            source = await repository.lock_latest_guide_source_snapshot(
                str(delivery.project_id),
                guide.id,
                guide.version,
            )
            setup = await repository.lock_latest_project_setup_run(
                str(delivery.project_id),
                guide.id,
                guide.version,
            )
            if (
                source is None
                or setup is None
                or setup.id != str(delivery.setup_run_id)
                or setup.source_snapshot_id != str(delivery.source_snapshot_id)
                or source.id != setup.source_snapshot_id
                or source.bundle_hash != setup.source_snapshot_hash
                or setup.setup_generation != delivery.setup_generation
                or setup.celery_task_id != expected_task
            ):
                raise ProjectGuideCompilationDeliveryError()
            finalization = await session.scalar(
                select(ProjectGuideSetupFinalization).where(
                    ProjectGuideSetupFinalization.setup_run_id == setup.id,
                    ProjectGuideSetupFinalization.setup_generation == setup.setup_generation,
                )
            )
            if finalization is not None:
                return (
                    ProjectGuideSetupFinalizationCommand(
                        project_id=delivery.project_id,
                        guide_id=delivery.guide_id,
                        setup_run_id=delivery.setup_run_id,
                        setup_generation=delivery.setup_generation,
                        compilation_id=finalization.compilation_id,
                    ),
                    True,
                    None,
                )
            require_task_example_commitment(
                guide.task_examples, guide.task_examples_hash, manifest=source.manifest_json,
            )
            if setup.status == "dispatch_pending" and setup.current_step == "dispatch":
                setup.status = "queued"
                setup.current_step = "queued"
            elif setup.status != "queued" or setup.current_step != "queued":
                raise ProjectGuideCompilationDeliveryError()
            if not is_compilation_source_setup(setup, expected_task):
                raise ProjectGuideCompilationDeliveryError()
            attempt = await session.scalar(
                select(ProjectGuideCompilationAttempt).where(
                    ProjectGuideCompilationAttempt.setup_run_id == setup.id,
                    ProjectGuideCompilationAttempt.setup_generation == setup.setup_generation,
                )
            )
            return None, attempt is not None, attempt.runtime_configuration if attempt else None

    async def _finalize(self, command: ProjectGuideSetupFinalizationCommand) -> dict:
        """Create or replay the existing finalizer's receipt under fresh authority."""
        async with self._sessions() as session, session.begin():
            receipt = await GuideCompilationFinalizationService(
                session,
                self._finalization_authorization(session),
            ).finalize(command)
        return {"status": receipt.setup_outcome, **receipt.model_dump(mode="json")}
