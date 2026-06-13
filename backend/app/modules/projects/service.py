"""Service layer for project and project-guide lifecycle operations."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_any_role
from app.modules.checkers.runner import UnknownChecker, default_checker_registry
from app.modules.projects.models import (
    CheckerPolicy,
    PaymentPolicy,
    Project,
    ProjectGuide,
    RevisionPolicy,
    ReviewPolicy,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import (
    ActiveGuideResponse,
    CheckerPolicyInput,
    CheckerPolicyResponse,
    PaymentPolicyInput,
    PaymentPolicyResponse,
    ProjectCreate,
    ProjectGuideCreate,
    ProjectGuideResponse,
    ProjectGuideUpdate,
    ProjectResponse,
    RevisionPolicyInput,
    RevisionPolicyResponse,
    ReviewPolicyInput,
    ReviewPolicyResponse,
)
from app.schemas.auth import ActorContext

PROJECT_SETUP_ROLES = {"admin", "project_manager"}
ALLOWED_REVIEW_DECISIONS = {"accept", "needs_revision", "reject"}
ALLOWED_REVISION_RESUBMISSION_STATES = {"needs_revision"}


class ProjectServiceError(Exception):
    """Base error for project service failures mapped to API responses."""

    status_code = 400


class ProjectNotFound(ProjectServiceError):
    """Raised when a project id does not match a stored project."""

    status_code = 404


class GuideNotFound(ProjectServiceError):
    """Raised when a project guide id is missing or outside the project."""

    status_code = 404


class GuideActivationBlocked(ProjectServiceError):
    """Raised when a guide is not ready to become active."""

    status_code = 422


class GuideEditBlocked(ProjectServiceError):
    """Raised when a non-draft guide is edited."""

    status_code = 409


class GuideActivationConflict(ProjectServiceError):
    """Raised when another transaction wins the guide activation race."""

    status_code = 409


class ProjectService:
    """Coordinates project guide rules, persistence, and response shaping.

    The service owns business rules for project setup and guide activation. It
    keeps routers thin and repositories focused on database access.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Create a service instance bound to one database session.

        Args:
            session: Async SQLAlchemy session for the current request.
        """
        self._session = session
        self._repo = ProjectRepository(session)

    async def create_project(self, actor: ActorContext, payload: ProjectCreate) -> ProjectResponse:
        """Create a draft project record after project setup authorization.

        Args:
            actor: Verified Flow actor context for the current request.
            payload: Validated project creation fields.

        Returns:
            Created project response.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        project = Project(
            id=str(uuid4()),
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            status="draft",
            base_amount=payload.base_amount,
            currency=payload.currency,
        )
        project = await self._repo.add_project(project)
        await self._session.commit()
        await self._session.refresh(project)
        return ProjectResponse.model_validate(project)

    async def get_project(self, actor: ActorContext, project_id: str) -> ProjectResponse:
        """Return one project visible to project setup operators.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project identifier to load.

        Returns:
            Matching project response.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            ProjectNotFound: If the project id is unknown.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        project = await self._repo.get_project(project_id)
        if project is None:
            raise ProjectNotFound("project not found")
        return ProjectResponse.model_validate(project)

    async def create_guide(
        self,
        actor: ActorContext,
        project_id: str,
        payload: ProjectGuideCreate,
    ) -> ProjectGuideResponse:
        """Create a draft guide and optional policy records for one project.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            payload: Guide content plus optional checker, review, revision, and payment policies.

        Returns:
            Created draft guide response.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            ProjectNotFound: If the parent project is unknown.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        project = await self._repo.get_project(project_id)
        if project is None:
            raise ProjectNotFound("project not found")
        guide = ProjectGuide(
            id=str(uuid4()),
            project_id=project_id,
            version=payload.version,
            status="draft",
            content_markdown=payload.content_markdown,
            required_task_fields=payload.required_task_fields,
            required_submission_fields=payload.required_submission_fields,
            task_instructions=payload.task_instructions,
            output_requirements=payload.output_requirements,
            acceptance_criteria=payload.acceptance_criteria,
            rejection_criteria=payload.rejection_criteria,
            reviewer_rubric=payload.reviewer_rubric,
            forbidden_actions=payload.forbidden_actions,
            required_skills=payload.required_skills,
            difficulty_scale=payload.difficulty_scale,
            estimated_time_policy=payload.estimated_time_policy,
            common_rejection_reasons=payload.common_rejection_reasons,
            evidence_policy=payload.evidence_policy,
            unacceptable_work_policy=payload.unacceptable_work_policy,
            change_summary=payload.change_summary,
            created_by=actor.actor_id,
        )
        guide = await self._repo.add_guide(guide)
        await self._upsert_optional_policies(project_id, payload.version, payload)
        await self._session.commit()
        await self._session.refresh(guide)
        return ProjectGuideResponse.model_validate(guide)

    async def update_draft_guide(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
        payload: ProjectGuideUpdate,
    ) -> ProjectGuideResponse:
        """Apply edits to a draft guide and its optional policy records.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            guide_id: Draft guide to update.
            payload: Partial guide and policy fields to apply.

        Returns:
            Updated draft guide response.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            GuideNotFound: If the guide is missing or outside the project.
            GuideEditBlocked: If the guide is no longer a draft.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._get_project_guide(project_id, guide_id)
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can be edited")

        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            if field in {"checker_policy", "review_policy", "revision_policy", "payment_policy"}:
                continue
            setattr(guide, field, value)
        await self._upsert_optional_policies(project_id, guide.version, payload)
        await self._session.commit()
        await self._session.refresh(guide)
        return ProjectGuideResponse.model_validate(guide)

    async def activate_guide(
        self,
        actor: ActorContext,
        project_id: str,
        guide_id: str,
    ) -> ActiveGuideResponse:
        """Promote a complete draft guide and supersede any prior active guide.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project that owns the guide.
            guide_id: Draft guide to activate.

        Returns:
            Active guide response with checker, review, revision, and payment policies.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            GuideNotFound: If the guide is missing or outside the project.
            GuideActivationBlocked: If the guide or its policy context is incomplete.
            GuideActivationConflict: If another activation wins the database race.
            ProjectNotFound: If the parent project disappears during activation.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._get_project_guide(project_id, guide_id)
        if guide.status != "draft":
            raise GuideActivationBlocked("only draft guides can be activated")

        checker_policy = await self._repo.get_checker_policy(project_id, guide.version)
        review_policy = await self._repo.get_review_policy(project_id, guide.version)
        revision_policy = await self._repo.get_revision_policy(project_id, guide.version)
        payment_policy = await self._repo.get_payment_policy(project_id, guide.version)
        self._validate_activation_ready(
            guide,
            checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
        )
        project = await self._repo.get_project(project_id)
        if project is None:
            raise ProjectNotFound("project not found")

        now = datetime.now(UTC)
        for active_guide in await self._repo.list_active_guides(project_id):
            active_guide.status = "superseded"
            active_guide.superseded_at = now
        await self._session.flush()

        guide.status = "active"
        guide.approved_by = actor.actor_id
        guide.effective_at = now

        project.status = "active"
        project.base_amount = payment_policy.base_amount
        project.currency = payment_policy.currency

        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise GuideActivationConflict(
                "guide activation conflicted with a concurrent update; retry"
            ) from exc
        await self._session.refresh(guide)
        await self._session.refresh(checker_policy)
        await self._session.refresh(review_policy)
        await self._session.refresh(revision_policy)
        await self._session.refresh(payment_policy)
        return self._active_response(
            guide,
            checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
        )

    async def get_active_guide(self, actor: ActorContext, project_id: str) -> ActiveGuideResponse:
        """Return the active guide with checker, review, revision, and payment context.

        Args:
            actor: Verified Flow actor context for the current request.
            project_id: Project whose active guide should be loaded.

        Returns:
            Active guide response with all required policy records.

        Raises:
            PermissionDenied: If the actor cannot manage project setup.
            GuideNotFound: If no active guide exists for the project.
            GuideActivationBlocked: If the active guide policy context is incomplete.
        """
        require_any_role(actor, PROJECT_SETUP_ROLES)
        guide = await self._repo.get_active_guide(project_id)
        if guide is None:
            raise GuideNotFound("active guide not found")
        checker_policy = await self._repo.get_checker_policy(project_id, guide.version)
        review_policy = await self._repo.get_review_policy(project_id, guide.version)
        revision_policy = await self._repo.get_revision_policy(project_id, guide.version)
        payment_policy = await self._repo.get_payment_policy(project_id, guide.version)
        if (
            checker_policy is None
            or review_policy is None
            or revision_policy is None
            or payment_policy is None
        ):
            raise GuideActivationBlocked("active guide policy context is incomplete")
        return self._active_response(
            guide,
            checker_policy,
            review_policy,
            revision_policy,
            payment_policy,
        )

    async def _get_project_guide(self, project_id: str, guide_id: str) -> ProjectGuide:
        """Load a guide and ensure it belongs to the requested project.

        Args:
            project_id: Project id expected to own the guide.
            guide_id: Guide id to load.

        Returns:
            Matching guide model.

        Raises:
            GuideNotFound: If the guide is missing or belongs to another project.
        """
        guide = await self._repo.get_guide(guide_id)
        if guide is None or guide.project_id != project_id:
            raise GuideNotFound("guide not found")
        return guide

    async def _upsert_optional_policies(
        self,
        project_id: str,
        guide_version: str,
        payload: ProjectGuideCreate | ProjectGuideUpdate,
    ) -> None:
        """Create or replace policy records supplied with guide payloads.

        Args:
            project_id: Project that owns the policies.
            guide_version: Guide version the policies apply to.
            payload: Guide create or update payload carrying optional policies.
        """
        if payload.checker_policy is not None:
            await self._repo.upsert_checker_policy(
                self._checker_policy_model(project_id, guide_version, payload.checker_policy)
            )
        if payload.review_policy is not None:
            await self._repo.upsert_review_policy(
                self._review_policy_model(project_id, guide_version, payload.review_policy)
            )
        if payload.revision_policy is not None:
            await self._repo.upsert_revision_policy(
                self._revision_policy_model(project_id, guide_version, payload.revision_policy)
            )
        if payload.payment_policy is not None:
            await self._repo.upsert_payment_policy(
                self._payment_policy_model(project_id, guide_version, payload.payment_policy)
            )

    def _validate_activation_ready(
        self,
        guide: ProjectGuide,
        checker_policy: CheckerPolicy | None,
        review_policy: ReviewPolicy | None,
        revision_policy: RevisionPolicy | None,
        payment_policy: PaymentPolicy | None,
    ) -> None:
        """Enforce the minimum guide and policy contract required to activate.

        Args:
            guide: Draft guide being promoted.
            checker_policy: Checker policy for the guide version.
            review_policy: Review policy for the guide version.
            revision_policy: Revision policy for the guide version.
            payment_policy: Payment policy for the guide version.

        Raises:
            GuideActivationBlocked: If a required field or policy is missing.
        """
        if not guide.evidence_policy:
            raise GuideActivationBlocked("guide evidence policy is required before activation")
        if checker_policy is None or not checker_policy.required_checkers:
            raise GuideActivationBlocked("checker policy with required checkers is required")
        checker_names = set(checker_policy.required_checkers or []).union(
            checker_policy.warning_checkers or []
        )
        try:
            default_checker_registry().require_registered(checker_names)
        except UnknownChecker as exc:
            raise GuideActivationBlocked(str(exc)) from exc
        if review_policy is None or not review_policy.allowed_decisions:
            raise GuideActivationBlocked("review policy with allowed decisions is required")
        if not set(review_policy.allowed_decisions).issubset(ALLOWED_REVIEW_DECISIONS):
            raise GuideActivationBlocked("review policy contains invalid decisions")
        if revision_policy is None:
            raise GuideActivationBlocked("revision policy is required")
        if (
            revision_policy.max_revision_rounds < 1
            or revision_policy.revision_deadline_hours < 1
            or not revision_policy.allowed_resubmission_states
        ):
            raise GuideActivationBlocked("revision policy is incomplete")
        if not set(revision_policy.allowed_resubmission_states).issubset(
            ALLOWED_REVISION_RESUBMISSION_STATES
        ):
            raise GuideActivationBlocked("revision policy contains invalid resubmission states")
        if payment_policy is None:
            raise GuideActivationBlocked("payment policy is required")
        if (
            payment_policy.base_amount is None
            or payment_policy.base_amount < Decimal("0")
            or not payment_policy.currency
            or not payment_policy.payout_type
            or not payment_policy.accepted_payment_rule
        ):
            raise GuideActivationBlocked("payment policy is incomplete")

    def _checker_policy_model(
        self,
        project_id: str,
        guide_version: str,
        payload: CheckerPolicyInput,
    ) -> CheckerPolicy:
        """Build a checker policy model from API input.

        Args:
            project_id: Project that owns the policy.
            guide_version: Guide version the policy applies to.
            payload: Validated checker policy input.

        Returns:
            Unsaved checker policy model.
        """
        return CheckerPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_version=guide_version,
            required_checkers=payload.required_checkers,
            warning_checkers=payload.warning_checkers,
            blocking_severities=payload.blocking_severities,
        )

    def _review_policy_model(
        self,
        project_id: str,
        guide_version: str,
        payload: ReviewPolicyInput,
    ) -> ReviewPolicy:
        """Build a review policy model from API input.

        Args:
            project_id: Project that owns the policy.
            guide_version: Guide version the policy applies to.
            payload: Validated review policy input.

        Returns:
            Unsaved review policy model.
        """
        return ReviewPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_version=guide_version,
            requires_second_review=payload.requires_second_review,
            allowed_decisions=payload.allowed_decisions,
            minimum_finding_fields=payload.minimum_finding_fields,
            sla_hours=payload.sla_hours,
        )

    def _revision_policy_model(
        self,
        project_id: str,
        guide_version: str,
        payload: RevisionPolicyInput,
    ) -> RevisionPolicy:
        """Build a revision policy model from API input.

        Args:
            project_id: Project that owns the policy.
            guide_version: Guide version the policy applies to.
            payload: Validated revision policy input.

        Returns:
            Unsaved revision policy model.
        """
        return RevisionPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_version=guide_version,
            max_revision_rounds=payload.max_revision_rounds,
            revision_deadline_hours=payload.revision_deadline_hours,
            auto_reject_after_limit=payload.auto_reject_after_limit,
            allowed_resubmission_states=payload.allowed_resubmission_states,
            reviewer_reassignment_rule=payload.reviewer_reassignment_rule,
        )

    def _payment_policy_model(
        self,
        project_id: str,
        guide_version: str,
        payload: PaymentPolicyInput,
    ) -> PaymentPolicy:
        """Build a payment policy model from API input.

        Args:
            project_id: Project that owns the policy.
            guide_version: Guide version the policy applies to.
            payload: Validated payment policy input.

        Returns:
            Unsaved payment policy model.
        """
        return PaymentPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_version=guide_version,
            base_amount=payload.base_amount,
            currency=payload.currency,
            payout_type=payload.payout_type,
            revision_payment_rule=payload.revision_payment_rule,
            rejection_payment_rule=payload.rejection_payment_rule,
            accepted_payment_rule=payload.accepted_payment_rule,
        )

    def _active_response(
        self,
        guide: ProjectGuide,
        checker_policy: CheckerPolicy,
        review_policy: ReviewPolicy,
        revision_policy: RevisionPolicy,
        payment_policy: PaymentPolicy,
    ) -> ActiveGuideResponse:
        """Shape the active guide payload returned by lifecycle endpoints.

        Args:
            guide: Active project guide model.
            checker_policy: Checker policy attached to the active guide version.
            review_policy: Review policy attached to the active guide version.
            revision_policy: Revision policy attached to the active guide version.
            payment_policy: Payment policy attached to the active guide version.

        Returns:
            API response containing the active guide and policy context.
        """
        return ActiveGuideResponse(
            guide=ProjectGuideResponse.model_validate(guide),
            checker_policy=CheckerPolicyResponse.model_validate(checker_policy),
            review_policy=ReviewPolicyResponse.model_validate(review_policy),
            revision_policy=RevisionPolicyResponse.model_validate(revision_policy),
            payment_policy=PaymentPolicyResponse.model_validate(payment_policy),
        )
