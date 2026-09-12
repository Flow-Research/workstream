"""Publish a committed human correction through the existing setup queue."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.modules.authorization.api import AuthorizationDenied, AuthorizationUnavailable, PreparedAuthorizationInvalid
from app.modules.projects.api.guide_proposals import GuideProposalDispatchResponse, GuideProposalError
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from app.modules.projects.models import ProjectSetupRun
from app.modules.projects.setup_queue import dispatch_project_guide_compilation_after_commit

from .models import ProjectGuideProposalCorrection
from .repository import GuideCompilationIntegrityError, GuideCompilationStorageError
from .service import GuideCompilationService
from .diagnostics import compilation_setup_response


class GuideCorrectionDispatchService:
    """Use canonical request custody, then publish only after its transaction commits."""

    def __init__(self, session, authorization, inputs):
        self.session = session
        self.requests = GuideCompilationService(session, authorization, request_inputs=inputs)

    async def dispatch(self, selection, correction_operation_id: UUID, *, actor):
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
            await self.requests.request_correction(actor=actor, correction_operation_id=correction_operation_id)
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
                setup = await self.session.get(ProjectSetupRun, setup_id)
                if setup is None:
                    raise GuideProposalError("proposal_unavailable")
                state = await compilation_setup_response(self.session, setup)
                return GuideProposalDispatchResponse(
                    correction_operation_id=correction_operation_id,
                    setup_run_id=setup_id, setup_generation=generation, status=state.status,
                )
        except (AuthorizationDenied, AuthorizationUnavailable, PreparedAuthorizationInvalid):
            raise GuideProposalError("authority_unavailable") from None
        except GuideCompilationIntegrityError:
            raise GuideProposalError("operation_conflict") from None
        except (SQLAlchemyError, GuideCompilationStorageError):
            raise GuideProposalError("storage_unavailable") from None
