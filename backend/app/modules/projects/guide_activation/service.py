"""One complete-guide activation operation in the caller root transaction."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from app.core.identifiers import new_record_id

from app.interfaces.project_agents import RequirementDisposition
from app.modules.authorization.api import ActorKind
from app.modules.checkers.api.external_policy import (
    validate_stored_external_checker_policies,
)
from app.modules.checkers.api.external import ExternalCheckerRegistryPort
from app.modules.projects.api.guide_activation import (
    GuideActivationCommand,
    GuideActivationCondition,
    GuideActivationFacts,
    GuideActivationLocator,
    GuideActivationReadiness,
    GuideActivationReceipt,
    GuideContributionPolicyFacts,
    PreparedGuideActivation,
)
from app.modules.projects.api.guide_activation_context import GuideContributionDiscoveryPort
from app.modules.projects.api.guide_proposals import GuideProposalError, MissingCheckerCapability
from app.modules.projects.api.post_policy import PostPolicySelection
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
from app.modules.projects.guide_mutation_repository import GuideMutationRepository
from app.modules.projects.post_policy.custody import load_post_policy_custody
from app.modules.projects.post_policy.repository import PostPolicyRepository
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.service import GuideActivationBlocked, ProjectService, ProjectServiceError

from .custody import ACTION, activation_custody, load_guide_activation, require_authority


def activation_authorization_selector(actor_profile_id: UUID, idempotency_key: UUID) -> UUID:
    """Return the stable non-row selector used only for activation PREP."""
    return uuid5(
        NAMESPACE_URL,
        f"workstream.guide.activate:{actor_profile_id}:{idempotency_key}",
    )


class GuideActivationService:
    """AUTH-12H supplies live manager authority; composition without it denies."""

    def __init__(
        self,
        session,
        *,
        contribution,
        authorization=None,
        registry: ExternalCheckerRegistryPort | None = None,
    ):
        self.session = session
        self.authorization = authorization
        self.contribution = contribution
        self.projects = ProjectRepository(session)
        self.replay = GuideMutationRepository(session)
        self.post = PostPolicyRepository(session)
        self.registry = registry

    async def activate(
        self, command: GuideActivationCommand, *, actor, request_id: UUID
    ) -> GuideActivationReceipt:
        """Validate both approvals, consume exact authority, and commit no partial effects."""
        if (
            self.authorization is None
            or actor.actor_kind is not ActorKind.HUMAN
            or not self.session.in_transaction()
            or self.session.in_nested_transaction()
            or self.session.new
            or self.session.dirty
            or self.session.deleted
        ):
            raise GuideProposalError("authority_unavailable")
        command = GuideActivationCommand.model_validate(command.model_dump(mode="json"))
        target = command.target.proposal
        authorization_selector_id = activation_authorization_selector(
            actor.actor_profile_id, command.idempotency_key
        )
        locator = GuideActivationLocator(
            project_id=target.project_id,
            guide_id=target.guide_id,
            actor_profile_id=actor.actor_profile_id,
            identity_link_id=actor.identity_link_id,
            operation_id=authorization_selector_id,
            request_id=request_id,
        )
        async with GuideProposalService._bounded_errors():
            # Enter full AUTH control/caller/link/grant scope before owner locks.
            async with self.authorization.lock_activation_scope(locator) as prepared:
                if not isinstance(prepared, PreparedGuideActivation):
                    raise GuideProposalError("authority_unavailable")
                project = await self.projects.get_project(str(target.project_id), for_update=True)
                if project is None:
                    raise GuideProposalError("proposal_unavailable")
                existing = await self.replay.find(
                    str(actor.actor_profile_id), ACTION, command.idempotency_key
                )
                if existing is not None:
                    receipt, facts, authority = activation_custody(existing, request_id=request_id)
                    if receipt.command != command or facts.locator != locator:
                        raise GuideProposalError("operation_conflict")
                    guide = await self.projects.lock_project_guide(str(target.guide_id))
                    if guide is None or await load_guide_activation(self.session, guide) != receipt:
                        raise GuideProposalError("operation_conflict")
                    await prepared.validate_replay(facts, authority.authorization_decision_event_id)
                    return receipt
                checked = await self._evaluate(
                    _ActivationConditions(collect=False),
                    project,
                    PostPolicySelection(
                        project_id=target.project_id,
                        guide_id=target.guide_id,
                        compilation_id=target.compilation_id,
                        policy_id=command.target.policy_id,
                    ),
                    expected=command,
                    contribution_selection=(
                        command.contribution_policy_id,
                        command.contribution_policy_version_id,
                    ),
                )
                guide, previous, contribution = checked.guide, checked.previous, checked.contribution
                operation_id = new_record_id()
                receipt = GuideActivationReceipt(
                    operation_id=operation_id,
                    command=command,
                    contribution=contribution,
                    activation_generation=command.guide_mutation_generation + 1,
                    effective_at=datetime.now(UTC),
                    prior_project_status=project.status,
                )
                facts = GuideActivationFacts(locator=locator, receipt=receipt)
                authority = await prepared.consume_new(facts)
                require_authority(authority, facts)
            # A failed capability close cannot leave a reservation or lifecycle write.
            disposition, record = await self.replay.reserve(
                actor_profile_id=str(actor.actor_profile_id),
                identity_link_id=str(actor.identity_link_id),
                action_id=ACTION,
                idempotency_key=command.idempotency_key,
                request_digest=command.digest,
                resource_context_digest=facts.digest,
                operation_id=operation_id,
                project_id=guide.project_id,
                resource_id=guide.id,
                operation_generation=receipt.activation_generation,
                activation_facts_json=facts.resource_json(),
                activation_authority_json=authority.model_dump(mode="json"),
            )
            if disposition != "claimed":
                raise GuideProposalError("operation_conflict")
            if previous is not None:
                previous.status, previous.superseded_at = "superseded", receipt.effective_at
                await self.session.flush()
            guide.status, guide.effective_at, guide.approved_by = (
                "active",
                receipt.effective_at,
                record.actor_profile_id,
            )
            guide.contribution_policy_id = command.contribution_policy_id
            guide.contribution_policy_version_id = command.contribution_policy_version_id
            guide.activation_operation_id = operation_id
            guide.mutation_generation = receipt.activation_generation
            guide.last_mutated_by_actor_profile_id = record.actor_profile_id
            guide.last_mutated_via_identity_link_id = record.identity_link_id
            guide.last_mutated_by_admin_role_grant_id = authority.admin_role_grant_id
            guide.last_mutation_action_id = ACTION
            guide.last_mutation_scope_type = "project"
            guide.last_mutation_scope_project_id = guide.project_id
            guide.last_authorization_decision_event_id = str(
                authority.authorization_decision_event_id
            )
            if project.status == "draft":
                project.status = "active"
            await self.session.flush()
            await self.replay.complete(record, response_json=receipt.model_dump(mode="json"))
            return receipt

    async def readiness(
        self,
        project_id: UUID,
        guide_id: UUID,
        *,
        contribution: GuideContributionDiscoveryPort,
    ) -> GuideActivationReadiness:
        """Dry-run activation's own conditions over the current selections.

        Evaluates the same ``_evaluate`` path as ``activate`` with the guide's
        latest derived post-submit policy, its current approval, selected
        review and revision policies, the current active guide and the
        project's current published contribution policy version. It takes the
        same transactional row locks as the post-policy review read, until the
        caller ends its transaction, and never prepares or consumes activation
        authority, reserves replay or writes. Product refusals become unmet
        conditions in activation's order; storage and authority failures
        raise ``GuideProposalError``.
        """
        if (
            not self.session.in_transaction()
            or self.session.in_nested_transaction()
            or self.session.new
            or self.session.dirty
            or self.session.deleted
        ):
            raise GuideProposalError("storage_unavailable")
        conditions = _ActivationConditions(collect=True)
        try:
            async with GuideProposalService._bounded_errors():
                project = await self.projects.get_project(str(project_id), for_update=True)
                if project is None:
                    raise GuideProposalError("proposal_unavailable")
                latest = await self.post.latest_policy(guide_id)
                selection = None
                if latest is not None and latest.project_id == str(project_id):
                    custody = await load_post_policy_custody(self.session, latest)
                    selection = PostPolicySelection(
                        project_id=project_id,
                        guide_id=guide_id,
                        compilation_id=custody.target.proposal.compilation_id,
                        policy_id=UUID(latest.id),
                    )
                published = await contribution.published_selection(project_id)
                await self._evaluate(
                    conditions,
                    project,
                    selection,
                    expected=None,
                    contribution_selection=None
                    if published is None
                    else (published.contribution_policy_id, published.contribution_policy_version_id),
                )
        except GuideProposalError as exc:
            if exc.code not in _PRODUCT_REFUSALS:
                raise
            # Evaluation stopped at an integrity fault activation would also refuse.
            conditions.fail(exc.code, "activation_integrity_failed")
        if self.session.new or self.session.dirty or self.session.deleted:
            raise GuideProposalError("storage_unavailable")
        unmet = tuple(conditions.unmet)
        return GuideActivationReadiness(
            project_id=project_id, guide_id=guide_id, ready=not unmet, unmet=unmet
        )

    async def _evaluate(
        self,
        conditions: "_ActivationConditions",
        project,
        selection: PostPolicySelection | None,
        *,
        expected: GuideActivationCommand | None,
        contribution_selection: tuple[UUID, UUID] | None,
    ) -> "_CheckedActivation | None":
        """Every activation precondition, in activation's order, shared by activate and readiness.

        ``expected`` is the manager's displayed selection on activation and
        ``None`` on a readiness read, which compares only against the current
        records. ``conditions`` raises the first unmet condition for
        activation and collects every evaluable one for readiness.
        """
        if project.status not in {"draft", "active"}:
            conditions.fail("approval_blocked", "project_not_activatable")
        if selection is None:
            conditions.fail("proposal_unavailable", "post_policy_unavailable")
            return None
        try:
            # The same mapping activation's outer boundary applies to a refused lineage.
            async with GuideProposalService._bounded_errors():
                locked, policy, post_custody = await self.post.lock_policy(selection)
        except GuideProposalError as exc:
            if not conditions.collect or exc.code not in _PRODUCT_REFUSALS:
                raise
            # The lock admits only a draft guide; name that cause with the
            # lock's own refusal code, which activation raises unchanged.
            guide = await self.projects.get_guide(str(selection.guide_id))
            conditions.fail(exc.code, "guide_not_draft" if guide is not None and guide.status != "draft"
                            else "post_policy_unavailable")
            return None
        try:
            await self.post.require_current_upstream(locked)
        except GuideProposalError as exc:
            if not conditions.collect:
                raise
            conditions.fail(exc.code, "upstream_approval_not_current")
        if post_custody.approval is None:
            conditions.fail("proposal_stale", "post_policy_not_approved")
        elif expected is not None and (
            post_custody.target != expected.target
            or post_custody.approval.operation_id != expected.post_approval_operation_id
            or post_custody.approval.output_digest != expected.post_approval_output_digest
        ):
            conditions.fail("proposal_stale", "selection_stale")
        guide = locked.view.guide
        if expected is not None and guide.mutation_generation != expected.guide_mutation_generation:
            conditions.fail("proposal_stale", "selection_stale")
        previous = await self.projects.lock_active_guide(str(selection.project_id))
        if expected is not None and (
            (UUID(previous.id) if previous else None) != expected.expected_previous_active_guide_id
            or (previous.mutation_generation if previous else None)
            != expected.expected_previous_active_guide_generation
        ):
            conditions.fail("proposal_stale", "selection_stale")
        review = await self.projects.lock_review_policy(guide.project_id, guide.version)
        revision = await self.projects.lock_revision_policy(guide.project_id, guide.version)
        for kind, row in (("review", review), ("revision", revision)):
            if row is None:
                conditions.fail("proposal_stale", f"{kind}_policy_unselected")
            elif expected is not None:
                chosen = getattr(expected, kind)
                if (row.id, row.policy_generation, row.policy_hash) != (
                    str(chosen.policy_id),
                    chosen.generation,
                    chosen.policy_hash,
                ):
                    conditions.fail("proposal_stale", "selection_stale")
        if review is not None and revision is not None:
            source_items = await self.projects.lock_guide_source_snapshot_items(
                locked.view.snapshot.id
            )
            try:
                await ProjectService(self.session).validate_source_snapshot_integrity(
                    locked.view.snapshot,
                    GuideActivationBlocked,
                    persisted_items=source_items,
                )
                snapshot_invalid = False
            except ProjectServiceError:
                snapshot_invalid = True
            if snapshot_invalid:
                conditions.fail("approval_blocked", "source_snapshot_invalid")
            await self._readiness(conditions, locked, policy, post_custody, review, revision)
        contribution = None
        if contribution_selection is None:
            conditions.fail("proposal_stale", "contribution_policy_unpublished")
        else:
            try:
                selected = await self.contribution.validate_for_activation(
                    selection.project_id, *contribution_selection
                )
            except ValueError:
                selected = None
            if selected is None:
                conditions.fail("proposal_stale", "contribution_policy_invalid")
            else:
                contribution = GuideContributionPolicyFacts.model_validate(selected)
        return _CheckedActivation(guide, previous, contribution)

    async def _readiness(self, conditions, locked, policy, post, review, revision):
        """Checker, requirement and approval-chain readiness of the locked approved generation."""
        approval = locked.view.approval_custody
        external = (
            approval.operation.effective_pre_submit_plan.get("schema_version")
            == "external_checker_policies.v1"
        )
        if not external or self.registry is None:
            conditions.fail("approval_blocked", "checker_policy_unsupported")
            return
        policies = validate_stored_external_checker_policies(
            approval.operation.effective_pre_submit_plan
        )
        if policies.pre_submit.model_dump(mode="json") != approval.pre.compiled_bundle:
            conditions.fail("approval_blocked", "checker_policy_mismatch")
        for binding in (*policies.pre_submit.entries, *policies.post_submit.entries):
            current = await self.registry.read_exact(
                binding.registry.registry_entry_id,
                binding.registry.entry_digest,
            )
            if current != binding.registry:
                conditions.fail("approval_blocked", "checker_registry_changed")
                break
        if locked.result.capability_suggestions:
            conditions.fail(
                "approval_blocked",
                "checker_capability_missing",
                tuple(
                    MissingCheckerCapability(
                        requirement_id=item.requirement_id,
                        stage=item.stage,
                        title=item.title,
                    )
                    for item in locked.result.capability_suggestions
                ),
            )
        if not review.human_review_required and any(
            item.disposition is RequirementDisposition.HUMAN_REVIEW
            for item in locked.result.requirements
        ):
            conditions.fail("approval_blocked", "human_review_required_by_guide")
        try:
            ProjectService(self.session).validate_activation_ready(
                locked.view.guide,
                locked.view.snapshot,
                locked.view.report,
                locked.view.policy,
                approval.effective,
                approval.pre,
                policy,
                review,
                revision,
                approval_custody=approval,
                post_policy_custody=post,
            )
            blocked = False
        except ProjectServiceError:
            blocked = True
        if blocked:
            conditions.fail("approval_blocked", "activation_requirements_unmet")


_PRODUCT_REFUSALS = frozenset({"proposal_unavailable", "proposal_stale", "approval_blocked"})


@dataclass(frozen=True, slots=True)
class _CheckedActivation:
    """The locked rows activation writes after every condition holds."""

    guide: object
    previous: object | None
    contribution: GuideContributionPolicyFacts | None


class _ActivationConditions:
    """Activation raises the first unmet condition; readiness collects them all."""

    def __init__(self, *, collect: bool) -> None:
        self.collect = collect
        self.unmet: list[GuideActivationCondition] = []

    def fail(self, code, reason, missing_capabilities=()) -> None:
        """Refuse activation now, or record the condition for a readiness read.

        ``selection_stale`` compares a displayed selection, which only
        activation has, so that reason never reaches a readiness answer.
        """
        if not self.collect:
            raise GuideProposalError(code, missing_capabilities=missing_capabilities)
        self.unmet.append(GuideActivationCondition.of(code, reason, missing_capabilities))
