"""Publish explicit human guide requests through the existing setup queue."""

from dataclasses import replace
from uuid import UUID

from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.model_usage.api import ModelCallUnavailable, ModelProfileReaderPort

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.authorization.api import ActorIdentityFacts, ProjectGuideCompilationAuthorizationPort
from app.modules.projects.api.guide_proposals import GuideProposalSelection
from .request_inputs import CompilationRequestInputs, select_model_runtime_configuration
from sqlalchemy.exc import SQLAlchemyError

from app.modules.authorization.api import AuthorizationDenied, AuthorizationUnavailable, PreparedAuthorizationInvalid
from app.modules.projects.api.guide_proposals import GuideProposalDispatchResponse, GuideProposalError, GuideCompilationDispatchResponse
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from app.modules.projects.models import ProjectSetupRun
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.api.guide_documents import GuideDocumentUnavailable
from app.modules.projects.setup_queue import dispatch_project_guide_compilation_after_commit

from .models import ProjectGuideCompilationAttempt, ProjectGuideProposalCorrection
from .repository import GuideCompilationIntegrityError, GuideCompilationStorageError
from .service import GuideCompilationService
from .diagnostics import compilation_setup_response


class GuideCompilationDispatchService:
    """Use canonical request custody, then publish only after its transaction commits."""

    def __init__(
        self, session: AsyncSession, authorization: ProjectGuideCompilationAuthorizationPort,
        inputs: CompilationRequestInputs, *, profiles: ModelProfileReaderPort,
    ) -> None:
        self.session = session
        self.authorization = authorization
        self.inputs = inputs
        self.profiles = profiles

    async def request_initial(
        self, project_id: UUID, guide_id: UUID, idempotency_key: UUID, *,
        actor: ActorIdentityFacts, inference_required: bool,
    ) -> GuideCompilationDispatchResponse:
        """Resolve current immutable guide inputs, authorize once, then publish."""
        try:
            async with self.session.begin():
                await self.authorization.lock_request_scope(actor=actor, project_id=project_id)
                setup = await ProjectRepository(self.session).get_latest_project_setup_run(
                    str(project_id), str(guide_id),
                )
                if setup is None:
                    raise GuideProposalError("proposal_unavailable")
                setup_id, generation, source_id = setup.id, setup.setup_generation, setup.source_snapshot_id
                inputs = await self._selected_inputs(project_id, setup_id, generation)
            receipt = await GuideCompilationService(
                self.session, self.authorization, request_inputs=inputs,
            ).request_initial(actor=actor, setup_run_id=UUID(setup_id),
                              idempotency_key=idempotency_key, inference_required=inference_required)
            await dispatch_project_guide_compilation_after_commit(
                self.session, project_id=str(project_id), guide_id=str(guide_id),
                source_snapshot_id=source_id, setup_run_id=setup_id, setup_generation=generation,
                claimed_task_id=project_guide_compilation_task_id(setup_id, generation),
            )
            await self.session.rollback()
            async with self.session.begin():
                setup = await self.session.get(ProjectSetupRun, setup_id, populate_existing=True)
                state = await compilation_setup_response(self.session, setup)
                return GuideCompilationDispatchResponse(operation_id=receipt.operation_id,
                    setup_run_id=UUID(setup_id), setup_generation=generation, status=state.status)
        except (AuthorizationDenied, AuthorizationUnavailable, PreparedAuthorizationInvalid):
            raise GuideProposalError("authority_unavailable") from None
        except (SQLAlchemyError, GuideCompilationStorageError):
            raise GuideProposalError("storage_unavailable") from None
        except (GuideCompilationIntegrityError, GuideDocumentUnavailable, ModelCallUnavailable):
            raise GuideProposalError("operation_conflict") from None

    async def dispatch(
        self, selection: GuideProposalSelection, correction_operation_id: UUID, *,
        actor: ActorIdentityFacts,
    ) -> GuideProposalDispatchResponse:
        """Scope an immutable correction ID before fresh human request admission."""
        try:
            async with self.session.begin():
                correction = await self.session.scalar(
                    select(ProjectGuideProposalCorrection).where(
                        ProjectGuideProposalCorrection.operation_id == correction_operation_id,
                        ProjectGuideProposalCorrection.project_id == str(selection.project_id),
                        ProjectGuideProposalCorrection.guide_id == str(selection.guide_id),
                        ProjectGuideProposalCorrection.compilation_id == selection.compilation_id,
                    )
                )
                if correction is None:
                    raise GuideProposalError("proposal_unavailable")
                setup_id = correction.successor_setup_run_id
                generation = correction.successor_setup_generation
                source_id = correction.target_json["source_snapshot_id"]
                inputs = await self._selected_inputs(selection.project_id, setup_id, generation)
            requests = GuideCompilationService(
                self.session, self.authorization, request_inputs=inputs
            )
            await requests.request_correction(actor=actor, correction_operation_id=correction_operation_id)
            task_id = project_guide_compilation_task_id(setup_id, generation)
            await dispatch_project_guide_compilation_after_commit(
                self.session, project_id=str(selection.project_id), guide_id=str(selection.guide_id),
                source_snapshot_id=source_id, setup_run_id=setup_id,
                setup_generation=generation, claimed_task_id=task_id,
            )
            # Publication is separately committed. Release any dispatch inspection
            # transaction before reading the bounded current status.
            await self.session.rollback()
            async with self.session.begin():
                setup = await self.session.get(ProjectSetupRun, setup_id, populate_existing=True)
                if setup is None:
                    raise GuideProposalError("proposal_unavailable")
                state = await compilation_setup_response(self.session, setup)
                return GuideProposalDispatchResponse(
                    correction_operation_id=correction_operation_id,
                    setup_run_id=setup_id, setup_generation=generation, status=state.status,
                )
        except ModelCallUnavailable:
            raise GuideProposalError("proposal_unavailable") from None
        except (AuthorizationDenied, AuthorizationUnavailable, PreparedAuthorizationInvalid):
            raise GuideProposalError("authority_unavailable") from None
        except (SQLAlchemyError, GuideCompilationStorageError):
            raise GuideProposalError("storage_unavailable") from None
        except GuideCompilationIntegrityError:
            raise GuideProposalError("operation_conflict") from None

    async def _selected_inputs(
        self, project_id: UUID, setup_id: str, generation: int,
    ) -> CompilationRequestInputs:
        """Reuse a retained attempt's exact profile; select only for a fresh request."""
        attempt = await self.session.scalar(
            select(ProjectGuideCompilationAttempt).where(
                ProjectGuideCompilationAttempt.setup_run_id == setup_id,
                ProjectGuideCompilationAttempt.setup_generation == generation,
            )
        )
        if attempt is not None:
            configuration = ProjectGuideRuntimeConfiguration.model_validate(
                attempt.runtime_configuration
            )
        else:
            if self.inputs.runtime_configuration is None:
                raise GuideCompilationIntegrityError("compilation runtime configuration unavailable")
            configuration = await select_model_runtime_configuration(
                self.inputs.runtime_configuration, self.profiles, project_id
            )
        return replace(self.inputs, runtime_configuration=configuration)
