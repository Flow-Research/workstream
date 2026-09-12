"""Hidden manager review over one exact immutable compilation result."""

from contextlib import asynccontextmanager
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.authorization.api import (
    ActorIdentityFacts,
    AuthorizationDenied,
    AuthorizationUnavailable,
    PreparedAuthorizationInvalid,
)
from app.modules.authorization.api.guide_proposal_review import (
    GuideProposalAuthorizationFacts,
    GuideProposalAuthorizationLocator,
    GuideProposalAuthorizationPort,
    PreparedGuideProposalOperation,
)
from app.modules.projects.api.guide_compilation import ProjectGuideSetupFinalizationError
from app.modules.projects.api.guide_proposals import (
    GuideProposalError,
    GuideProposalSelection,
    GuideProposalApproval,
    GuideProposalApprovalReceipt,
    GuideProposalCorrection,
    GuideProposalCorrectionReceipt,
)
from app.modules.projects.api.guide_documents import GuideDocumentManifestPort
from app.modules.checkers.api.pre_submit_catalogue import PreSubmissionCapabilityProjection
from app.modules.checkers.api.post_submit_catalogue import PostSubmitCatalogue
from app.modules.checkers.api.policy_compilation import PreSubmissionPolicyCompilationPort
from app.modules.projects.api.guide_proposal_package import GuideProposalReviewPackage

from .proposal_repository import GuideProposalRepository
from .repository import GuideCompilationIntegrityError


class _UnavailableProposalAuthorization:
    """No product caller receives approval or disclosure authority by default."""

    @asynccontextmanager
    async def prepare_proposal_operation(self, _locator):
        raise AuthorizationUnavailable("guide proposal authority is unavailable")
        yield


class GuideProposalService:
    """Use caller-owned transactions and explicitly supplied request authority."""

    def __init__(
        self,
        session: AsyncSession,
        authorization: GuideProposalAuthorizationPort | None = None,
    ) -> None:
        self.session = session
        self.authorization = (
            authorization if authorization is not None else _UnavailableProposalAuthorization()
        )
        self.repository = GuideProposalRepository(session)

    async def review_package(
        self,
        selection: GuideProposalSelection,
        *,
        actor: ActorIdentityFacts,
        request_id: UUID,
    ) -> GuideProposalReviewPackage:
        """Authorize the exact complete safe response; never read a latest substitute."""
        self._require_transaction()
        locator = GuideProposalAuthorizationLocator(
            project_id=selection.project_id,
            guide_id=selection.guide_id,
            compilation_id=selection.compilation_id,
            actor_profile_id=actor.actor_profile_id,
            identity_link_id=actor.identity_link_id,
            action_id="project.guide_compilation.review_package.read",
            operation_id=uuid5(
                NAMESPACE_URL,
                f"workstream.guide-proposal-read:{actor.actor_profile_id}:{request_id}",
            ),
            request_id=request_id,
        )
        async with self._bounded_errors():
            async with self.authorization.prepare_proposal_operation(locator) as prepared:
                if not isinstance(prepared, PreparedGuideProposalOperation):
                    raise GuideProposalError("authority_unavailable")
                locked = await self.repository.lock(selection)
                package = await self.repository.package(locked)
                facts = GuideProposalAuthorizationFacts(
                    locator=locator,
                    finalization_id=locked.target.finalization_id,
                    artifact_policy_id=locked.target.artifact_policy_id,
                    setup_run_id=locked.target.setup_run_id,
                    setup_generation=locked.target.setup_generation,
                    target_digest=locked.target.digest,
                    request_digest=canonical_json_hash(selection.model_dump(mode="json")),
                    output_digest=canonical_json_hash(package.model_dump(mode="json")),
                    current_approval_operation_id=package.current_approval_operation_id,
                    current_approval_output_digest=package.current_approval_output_digest,
                )
                await prepared.authorize_read(facts)
            return package

    async def approve(
        self,
        command: GuideProposalApproval,
        *,
        actor: ActorIdentityFacts,
        request_id: UUID,
        material: GuideDocumentManifestPort,
        pre_capabilities: PreSubmissionCapabilityProjection,
        post_capabilities: PostSubmitCatalogue,
        planner: PreSubmissionPolicyCompilationPort,
    ) -> GuideProposalApprovalReceipt:
        """Approve through the sole hidden owner, without committing or invoking a model."""
        from .proposal_approval import approve_proposal

        self._require_transaction()
        async with self._bounded_errors():
            return await approve_proposal(
                self.session,
                self.authorization,
                command,
                actor=actor,
                request_id=request_id,
                material=material,
                pre_capabilities=pre_capabilities,
                post_capabilities=post_capabilities,
                planner=planner,
            )

    def _require_transaction(self) -> None:
        if (
            not self.session.in_transaction()
            or self.session.in_nested_transaction()
            or self.session.new
            or self.session.dirty
            or self.session.deleted
        ):
            raise GuideProposalError("proposal_unavailable")

    async def request_correction(
        self,
        command: GuideProposalCorrection,
        *,
        actor: ActorIdentityFacts,
        request_id: UUID,
    ) -> GuideProposalCorrectionReceipt:
        """Allocate a successor while leaving provider execution separately authorized."""
        from .proposal_correction import request_proposal_correction

        self._require_transaction()
        async with self._bounded_errors():
            return await request_proposal_correction(
                self.session,
                self.authorization,
                command,
                actor=actor,
                request_id=request_id,
            )

    @staticmethod
    @asynccontextmanager
    async def _bounded_errors():
        try:
            yield
        except GuideProposalError:
            raise
        except (AuthorizationDenied, AuthorizationUnavailable, PreparedAuthorizationInvalid):
            raise GuideProposalError("authority_unavailable") from None
        except (
            GuideCompilationIntegrityError,
            ProjectGuideSetupFinalizationError,
            ValidationError,
            ValueError,
        ):
            raise GuideProposalError("proposal_unavailable") from None
        except SQLAlchemyError:
            raise GuideProposalError("storage_unavailable") from None
