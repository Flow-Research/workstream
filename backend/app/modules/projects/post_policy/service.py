"""Canonical, zero-inference post-policy projection and exact manager decisions."""

from datetime import UTC, datetime
from uuid import UUID, uuid5

from app.core.identifiers import new_record_id

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.authorization.api import ActorIdentityFacts
from app.modules.authorization.api.guide_proposal_review import GuideProposalAuthorizationPort
from app.modules.checkers.api.external_policy import (
    LockedExternalPostSubmitPolicy,
    validate_stored_external_checker_policies,
)
from app.modules.authorization.api.post_policy import (
    PostPolicyAuthorizationFacts,
    PostPolicyAuthorizationLocator,
    PreparedPostPolicyOperation,
    PostPolicyAuthorizationPort,
)
from app.modules.projects.api.guide_proposals import (
    GuideProposalApprovalReceipt,
    GuideProposalError,
)
from app.modules.projects.api.post_policy import (
    PostPolicyReceipt,
    PostPolicyReviewPackage,
    PostPolicySelection,
    PostPolicyTarget,
    PostPolicyApproval,
    PostPolicyCorrection,
    PostPolicyDerive,
    post_policy_derive_authorization_selector,
    post_policy_human_authorization_selector,
)
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
from app.modules.projects.models import PostSubmitCheckerPolicy
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.api.guide_activation_context import (
    GuideActivationContext,
    GuidePolicySelection,
    GuideContributionDiscoveryPort,
)

from .compiler import compile_saved_post_policy
from .custody import load_post_policy_custody, operation_receipt, require_post_authority
from .models import PostPolicyOperation
from .repository import PostPolicyRepository


class PostPolicyService:
    """Use caller-owned root transactions and explicitly supplied nominal authority."""

    def __init__(self, session: AsyncSession, authorization: PostPolicyAuthorizationPort) -> None:
        self.session, self.authorization = session, authorization
        self.repository = PostPolicyRepository(session)

    def _require_transaction(self):
        if (
            not self.session.in_transaction()
            or self.session.in_nested_transaction()
            or self.session.new
            or self.session.dirty
            or self.session.deleted
        ):
            raise GuideProposalError("proposal_unavailable")

    async def derive(
        self, command: PostPolicyDerive, *, actor: ActorIdentityFacts, request_id: UUID
    ) -> PostPolicyReceipt:
        """Project one exact approved result once; no document/runtime dependency exists."""
        self._require_transaction()
        selector_id = post_policy_derive_authorization_selector(
            command.upstream_approval_operation_id
        )
        locator = self._locator(command.selection, actor, request_id, selector_id, "derive")
        async with GuideProposalService._bounded_errors():
            async with self.authorization.prepare_post_policy_operation(locator) as prepared:
                self._require_prepared(prepared)
                locked = await self.repository.lock_proposal(command.selection)
                existing = await self.repository.derive_operation(
                    command.upstream_approval_operation_id
                )
                if existing:
                    receipt = operation_receipt(existing)
                    _, _, custody = await self.repository.lock_policy(
                        self._selection(receipt.target)
                    )
                    if custody.projection.operation_id != existing.operation_id:
                        raise GuideProposalError("operation_conflict")
                    return await self._replay(existing, command, actor, locator, prepared)
                upstream = await self.repository.require_current_upstream(locked)
                if (
                    upstream.operation_id != command.upstream_approval_operation_id
                    or upstream.output_digest != command.upstream_approval_output_digest
                ):
                    raise GuideProposalError("proposal_stale")
                compiled = compile_saved_post_policy(
                    policies=validate_stored_external_checker_policies(
                        upstream.effective_pre_submit_plan
                    ),
                )
                previous = await self.repository.latest_policy(locked.target.guide_id)
                if previous:
                    old = await load_post_policy_custody(self.session, previous)
                    if old.target.proposal.setup_generation >= locked.target.setup_generation:
                        raise GuideProposalError("proposal_stale")
                operation_id = new_record_id()
                target = PostPolicyTarget(
                    proposal=locked.target,
                    upstream=GuideProposalApprovalReceipt.model_validate(upstream.receipt_json),
                    upstream_output_digest=upstream.output_digest,
                    policy_id=new_record_id(),
                    projection_operation_id=operation_id,
                    policy_hash=compiled.policy_sha256,
                    predecessor_policy_id=UUID(previous.id) if previous else None,
                )
                receipt = PostPolicyReceipt(operation_id=operation_id, kind="derive", target=target)
                facts = self._facts(locator, command, receipt)
                authority = await prepared.consume_new(facts)
                require_post_authority(authority, facts, actor)
            now = datetime.now(UTC)
            if previous and previous.lifecycle_status != "superseded":
                self._supersede(previous, operation_id, now, "upstream_policy_changed")
                await self.session.flush()
            self.session.add(self._policy_row(target, compiled, actor))
            await self._persist(
                command, actor, receipt, facts, authority, command.upstream_approval_operation_id
            )
            return receipt

    async def approve(
        self, command: PostPolicyApproval, *, actor: ActorIdentityFacts, request_id: UUID
    ) -> PostPolicyReceipt:
        """Record separate human approval without accepting replacement policy content."""
        self._require_transaction()
        selector_id = self._human_operation_id(actor, command.idempotency_key, "approve")
        target = command.target
        locator = self._locator(target.proposal, actor, request_id, selector_id, "approve")
        async with GuideProposalService._bounded_errors():
            async with self.authorization.prepare_post_policy_operation(locator) as prepared:
                self._require_prepared(prepared)
                locked, policy, custody = await self.repository.lock_policy(self._selection(target))
                if custody.target != target:
                    raise GuideProposalError("proposal_stale")
                existing = await self.repository.human_operation(
                    actor.actor_profile_id, "approve", command.idempotency_key
                )
                if existing:
                    return await self._replay(existing, command, actor, locator, prepared)
                await self.repository.require_current_upstream(locked)
                if policy.lifecycle_status != "compiled" or custody.approval is not None:
                    raise GuideProposalError("proposal_stale")
                compiled = compile_saved_post_policy(
                    policies=validate_stored_external_checker_policies(
                        locked.view.approval_custody.operation.effective_pre_submit_plan
                    ),
                )
                if compiled.policy_sha256 != target.policy_hash:
                    raise GuideProposalError("approval_blocked")
                operation_id = new_record_id()
                receipt = PostPolicyReceipt(
                    operation_id=operation_id, kind="approve", target=target
                )
                facts = self._facts(locator, command, receipt)
                authority = await prepared.consume_new(facts)
                require_post_authority(authority, facts, actor)
            policy.lifecycle_status = "approved"
            policy.approved_at = datetime.now(UTC)
            policy.approval_operation_id = operation_id
            await self._persist(command, actor, receipt, facts, authority, command.idempotency_key)
            return receipt

    async def review_package(
        self,
        selection: PostPolicySelection,
        *,
        actor: ActorIdentityFacts,
        request_id: UUID,
        contribution: GuideContributionDiscoveryPort,
    ) -> PostPolicyReviewPackage[LockedExternalPostSubmitPolicy]:
        """Disclose the complete exact policy and safe findings through existing read authority."""
        self._require_transaction()
        locator = self._locator(
            selection, actor, request_id, uuid5(request_id, "post-policy-read"), "read"
        )
        async with GuideProposalService._bounded_errors():
            async with self.authorization.prepare_post_policy_operation(locator) as prepared:
                self._require_prepared(prepared)
                projects = ProjectRepository(self.session)
                if await projects.get_project(str(selection.project_id), for_update=True) is None:
                    raise GuideProposalError("proposal_unavailable")
                locked, policy, custody = await self.repository.lock_policy(selection)
                previous = await projects.lock_active_guide(str(selection.project_id))
                guide = locked.view.guide
                review = await projects.lock_review_policy(guide.project_id, guide.version)
                revision = await projects.lock_revision_policy(guide.project_id, guide.version)

                def selected(row):
                    return (
                        None
                        if row is None
                        else GuidePolicySelection(
                            policy_id=row.id,
                            generation=row.policy_generation,
                            policy_hash=row.policy_hash,
                        )
                    )

                activation = GuideActivationContext(
                    guide_mutation_generation=guide.mutation_generation,
                    review=selected(review),
                    revision=selected(revision),
                    contribution=await contribution.published_selection(selection.project_id),
                    expected_previous_active_guide_id=previous.id if previous else None,
                    expected_previous_active_guide_generation=previous.mutation_generation
                    if previous
                    else None,
                    post_approval_operation_id=custody.approval.operation_id
                    if custody.approval
                    else None,
                    post_approval_output_digest=custody.approval.output_digest
                    if custody.approval
                    else None,
                )
                proposal = await self.repository.proposals.package(locked)
                package = PostPolicyReviewPackage[LockedExternalPostSubmitPolicy](
                    target=custody.target,
                    policy=custody.compiled,
                    proposal=proposal,
                    activation_context=activation,
                    lifecycle_status=policy.lifecycle_status,
                    current=locked.current
                    and policy.lifecycle_status != "superseded"
                    and proposal.current_approval_operation_id
                    == custody.target.upstream.operation_id,
                    approval_operation_id=policy.approval_operation_id,
                    correction=operation_receipt(custody.correction).correction
                    if custody.correction
                    else None,
                )
                facts = self._facts(
                    locator,
                    selection,
                    package,
                    target=custody.target,
                    lifecycle_status=policy.lifecycle_status,
                )
                await prepared.authorize_read(facts)
            return package

    async def request_correction(
        self,
        command: PostPolicyCorrection,
        *,
        actor: ActorIdentityFacts,
        request_id: UUID,
        guide_authorization: GuideProposalAuthorizationPort,
    ) -> PostPolicyReceipt:
        """Both authorities precede product locks; the existing successor owner persists once."""
        from .correction import request_post_policy_correction

        self._require_transaction()
        async with GuideProposalService._bounded_errors():
            return await request_post_policy_correction(
                self,
                command,
                actor,
                request_id,
                guide_authorization,
            )

    @staticmethod
    def _require_prepared(prepared):
        if not isinstance(prepared, PreparedPostPolicyOperation):
            raise GuideProposalError("authority_unavailable")

    @staticmethod
    def _selection(target):
        return PostPolicySelection(
            project_id=target.proposal.project_id,
            guide_id=target.proposal.guide_id,
            compilation_id=target.proposal.compilation_id,
            policy_id=target.policy_id,
        )

    @staticmethod
    def _human_operation_id(actor, key, kind):
        return post_policy_human_authorization_selector(actor.actor_profile_id, key, kind)

    @staticmethod
    def _locator(selection, actor, request_id, operation_id, kind):
        action = (
            "project.guide_compilation.review_package.read"
            if kind == "read"
            else (
                "project.post_submit_checker_policy."
                + ("correction.request" if kind == "correction" else kind)
            )
        )
        return PostPolicyAuthorizationLocator(
            project_id=selection.project_id,
            guide_id=selection.guide_id,
            compilation_id=selection.compilation_id,
            actor_profile_id=actor.actor_profile_id,
            identity_link_id=actor.identity_link_id,
            request_id=request_id,
            operation_id=operation_id,
            action_id=action,
        )

    @staticmethod
    def _facts(locator, command, output, *, target=None, lifecycle_status="compiled"):
        target = target if target is not None else output.target
        return PostPolicyAuthorizationFacts(
            locator=locator,
            policy_id=target.policy_id,
            finalization_id=target.proposal.finalization_id,
            setup_run_id=target.proposal.setup_run_id,
            setup_generation=target.proposal.setup_generation,
            upstream_approval_operation_id=target.upstream.operation_id,
            upstream_approval_output_digest=target.upstream_output_digest,
            policy_hash=target.policy_hash,
            guide_version=target.proposal.guide_version,
            source_snapshot_id=target.proposal.source_snapshot_id,
            source_snapshot_hash=target.proposal.source_snapshot_hash,
            result_hash=target.proposal.result_hash,
            post_component_hash=target.proposal.component_hashes.post_submit_hash,
            requirement_inventory_hash=target.proposal.component_hashes.requirement_inventory_hash,
            effective_policy_id=target.upstream.effective_policy_id,
            effective_policy_hash=target.upstream.effective_policy_hash,
            pre_submit_policy_id=target.upstream.pre_submit_policy_id,
            pre_submit_bundle_hash=target.upstream.pre_submit_bundle_hash,
            projection_operation_id=target.projection_operation_id,
            lifecycle_status=lifecycle_status,
            target_digest=target.digest,
            request_digest=canonical_json_hash(command.model_dump(mode="json")),
            output_digest=canonical_json_hash(output.model_dump(mode="json")),
        )

    async def _replay(self, existing, command, actor, locator, prepared):
        receipt = operation_receipt(existing)
        facts = self._facts(
            locator,
            command,
            receipt,
            lifecycle_status=existing.resource_context_json["lifecycle_status"],
        )
        if (
            existing.actor_profile_id != str(actor.actor_profile_id)
            or existing.identity_link_id != str(actor.identity_link_id)
            or facts.digest != existing.resource_context_digest
        ):
            raise GuideProposalError("operation_conflict")
        await prepared.validate_replay(facts, UUID(existing.authorization_decision_event_id))
        return receipt

    @staticmethod
    def _supersede(policy, operation_id, now, kind):
        policy.lifecycle_status = "superseded"
        policy.superseded_at = now
        policy.supersession_operation_id = operation_id
        policy.supersession_kind = kind

    @staticmethod
    def _policy_row(target, compiled, actor):
        proposal, upstream = target.proposal, target.upstream
        return PostSubmitCheckerPolicy(
            id=str(target.policy_id),
            project_id=str(proposal.project_id),
            guide_id=str(proposal.guide_id),
            guide_version=proposal.guide_version,
            source_snapshot_id=str(proposal.source_snapshot_id),
            source_snapshot_hash=proposal.source_snapshot_hash,
            effective_policy_id=str(upstream.effective_policy_id),
            effective_policy_hash=upstream.effective_policy_hash,
            pre_submit_checker_policy_id=str(upstream.pre_submit_policy_id),
            pre_submit_checker_bundle_hash=upstream.pre_submit_bundle_hash,
            required_checkers=[item.registry.capability_id for item in compiled.entries],
            warning_checkers=[],
            blocking_severities=["critical", "high"],
            policy_body=compiled.model_dump(mode="json"),
            policy_hash=compiled.policy_sha256,
            lifecycle_status="compiled",
            projection_operation_id=target.projection_operation_id,
            supersedes_policy_id=str(target.predecessor_policy_id)
            if target.predecessor_policy_id
            else None,
            created_by=str(actor.actor_profile_id),
        )

    async def _persist(self, command, actor, receipt, facts, authority, key):
        target = receipt.target
        self.session.add(
            PostPolicyOperation(
                operation_id=receipt.operation_id,
                kind=receipt.kind,
                idempotency_key=key,
                project_id=str(target.proposal.project_id),
                guide_id=str(target.proposal.guide_id),
                compilation_id=target.proposal.compilation_id,
                policy_id=str(target.policy_id),
                upstream_approval_operation_id=target.upstream.operation_id,
                target_json=target.model_dump(mode="json"),
                target_digest=target.digest,
                request_json=command.model_dump(mode="json"),
                request_digest=facts.request_digest,
                resource_context_json=facts.resource_json(),
                resource_context_digest=facts.digest,
                receipt_json=receipt.model_dump(mode="json"),
                output_digest=facts.output_digest,
                actor_profile_id=str(actor.actor_profile_id),
                identity_link_id=str(actor.identity_link_id),
                admin_role_grant_id=authority.admin_role_grant_id,
                service_identity=authority.service_identity,
                authorization_decision_event_id=str(authority.authorization_decision_event_id),
            )
        )
        await self.session.flush()

    (post_policy_derive_authorization_selector,)
    (post_policy_human_authorization_selector,)
