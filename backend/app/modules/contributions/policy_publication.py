"""Hidden ContributionPolicy publish and retirement orchestration."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.modules.compensation.api import (
    CompensationInstrumentType,
    PolicyAdapterBindingPort,
    PolicyAdapterBindingUnavailable,
)
from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyMutationAuthorizationPort,
    ContributionPolicyMutationResult,
    ContributionPolicyProjectEligibilityPort,
    ContributionPolicyPublishAuthorizationFacts,
    ContributionPolicyPublishRequest,
    ContributionPolicyReadAuthorizationPort,
    ContributionPolicyRetireAuthorizationFacts,
    ContributionPolicyRetireRequest,
    ContributionPolicyUnavailable,
)
from app.modules.contributions.models import (
    ContributionPolicyLifecycleEvent,
    ContributionPolicyTransitionCustody,
)
from app.modules.contributions.policy_graph import publication_graph_facts
from app.modules.contributions.policy_mutation_support import (
    begin_and_recover_policy_mutation,
    consume_and_close_policy_authority,
)
from app.modules.contributions.policy_validation import policy_request_digest
from app.modules.contributions.repository import ContributionPolicyRepository
from app.modules.projects.api import ProjectContributionPolicyUnavailable


class ContributionPolicyPublicationService:
    """Publish or terminally retire exact policy lineage without committing."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        repository: ContributionPolicyRepository,
        read_authorization: ContributionPolicyReadAuthorizationPort,
        mutation_authorization: ContributionPolicyMutationAuthorizationPort,
        projects: ContributionPolicyProjectEligibilityPort | None,
        bindings: PolicyAdapterBindingPort | None,
    ) -> None:
        self._session = session
        self._repository = repository
        self._read_authorization = read_authorization
        self._mutation_authorization = mutation_authorization
        self._projects = projects
        self._bindings = bindings

    async def publish(
        self, request: ContributionPolicyPublishRequest
    ) -> ContributionPolicyMutationResult:
        """Publish one locked complete draft and atomically replace its predecessor."""
        self._require_request(request, ContributionPolicyPublishRequest)
        digest = policy_request_digest("contribution.policy.publish", request)
        recovered = await self._begin_and_recover(request, digest, "published")
        if recovered is not None:
            return recovered
        await self._lock_project(request.project_id)
        await self._repository.lock_project_scope(request.project_id)
        policy, version = await self._lock_target(request)
        if policy.status not in {"draft", "active"} or version.status != "draft":
            raise ContributionPolicyConflict("contribution_policy_not_found")
        prior = await self._lock_prior(policy, version)
        rules, definitions = await self._repository.lock_publication_graph(version.id)
        self._require_complete_graph(rules)
        set_committed_value(version, "rules", rules)
        await self._lock_owner_resources(request.project_id, definitions)
        graph_digest, binding_ids = publication_graph_facts(version)
        facts = ContributionPolicyPublishAuthorizationFacts(
            action="contribution.policy.publish",
            actor_profile_id=request.actor_profile_id,
            operation_id=request.operation_id,
            request_digest=digest,
            project_id=request.project_id,
            contribution_policy_id=policy.id,
            contribution_policy_version_id=version.id,
            rules_and_definitions_digest=graph_digest,
            adapter_binding_ids=binding_ids,
            expected_policy_status=policy.status,
        )
        actor = await consume_and_close_policy_authority(self._mutation_authorization, facts)
        custody = self._custody(request, digest, "published", prior)
        await self._repository.create_transition_custody(custody)
        self._apply_publication(policy, version, prior, actor, custody)
        event = self._event(request, digest, "published", policy, version, prior, custody)
        await self._repository.flush_transition_event(event)
        return self._result(event)

    async def retire(
        self, request: ContributionPolicyRetireRequest
    ) -> ContributionPolicyMutationResult:
        """Terminally retire one aggregate's exact current published version."""
        self._require_request(request, ContributionPolicyRetireRequest)
        digest = policy_request_digest("contribution.policy.retire", request)
        recovered = await self._begin_and_recover(request, digest, "retired")
        if recovered is not None:
            return recovered
        await self._lock_project(request.project_id)
        await self._repository.lock_project_scope(request.project_id)
        policy, version = await self._lock_target(request)
        if (
            policy.status != "active"
            or policy.current_published_version_id != version.id
            or version.status != "published"
        ):
            raise ContributionPolicyConflict("contribution_policy_not_found")
        facts = ContributionPolicyRetireAuthorizationFacts(
            action="contribution.policy.retire",
            actor_profile_id=request.actor_profile_id,
            operation_id=request.operation_id,
            request_digest=digest,
            project_id=request.project_id,
            contribution_policy_id=policy.id,
            contribution_policy_version_id=version.id,
        )
        actor = await consume_and_close_policy_authority(self._mutation_authorization, facts)
        custody = self._custody(request, digest, "retired", version)
        await self._repository.create_transition_custody(custody)
        policy.status = version.status = "retired"
        policy.retired_by = version.retired_by = str(actor)
        policy.retired_at = version.retired_at = custody.occurred_at
        policy.last_transition_operation_id = version.last_transition_operation_id = (
            request.operation_id
        )
        event = self._event(request, digest, "retired", policy, version, version, custody)
        await self._repository.flush_transition_event(event)
        return self._result(event)

    async def _begin_and_recover(self, request, digest: str, event_type: str):
        return await begin_and_recover_policy_mutation(
            repository=self._repository,
            read_authorization=self._read_authorization,
            request=request,
            request_digest=digest,
            expected_event_type=event_type,
            result_factory=self._result,
        )

    async def _lock_project(self, project_id: UUID) -> None:
        if self._projects is None:
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        try:
            result = await self._projects.lock_contribution_policy_project(project_id)
        except ProjectContributionPolicyUnavailable as exc:
            raise ContributionPolicyConflict("contribution_policy_not_found") from exc
        if result.project_id != project_id:
            raise ContributionPolicyConflict("contribution_policy_not_found")

    async def _lock_target(self, request):
        policy = await self._repository.get_policy(
            request.project_id, request.contribution_policy_id, for_update=True
        )
        version = await self._repository.get_version(
            request.project_id,
            request.contribution_policy_id,
            request.contribution_policy_version_id,
            for_update=True,
        )
        if policy is None or version is None:
            raise ContributionPolicyConflict("contribution_policy_not_found")
        return policy, version

    async def _lock_prior(self, policy, version):
        if policy.current_published_version_id is None:
            return None
        prior = await self._repository.get_version(
            UUID(policy.project_id), policy.id, policy.current_published_version_id, for_update=True
        )
        if prior is None or prior.id == version.id or prior.status != "published":
            raise ContributionPolicyConflict("contribution_policy_not_found")
        return prior

    async def _lock_owner_resources(self, project_id: UUID, definitions) -> None:
        if self._bindings is None:
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        units = sorted({(item.instrument_type, item.unit_code) for item in definitions})
        for instrument, unit_code in units:
            unit = await self._repository.lock_unit(project_id, instrument, unit_code)
            if unit is None or unit.status != "active":
                raise ContributionPolicyConflict("contribution_policy_not_found")
        bindings = {item.adapter_binding_id: item for item in definitions}
        if any(
            bindings[item.adapter_binding_id].instrument_type != item.instrument_type
            for item in definitions
        ):
            raise ContributionPolicyConflict("contribution_policy_conflict")
        for item in (bindings[key] for key in sorted(bindings, key=str)):
            try:
                binding = await self._bindings.lock_policy_adapter_binding(
                    project_id=project_id,
                    adapter_binding_id=item.adapter_binding_id,
                    instrument_type=CompensationInstrumentType(item.instrument_type),
                )
            except (PolicyAdapterBindingUnavailable, ValueError) as exc:
                raise ContributionPolicyConflict("contribution_policy_not_found") from exc
            if (
                binding.project_id != project_id
                or binding.adapter_binding_id != item.adapter_binding_id
                or binding.instrument_type.value != item.instrument_type
            ):
                raise ContributionPolicyConflict("contribution_policy_not_found")

    @staticmethod
    def _require_complete_graph(rules) -> None:
        if len(rules) != 2 or {rule.contribution_type for rule in rules} != {
            "accepted_submission",
            "completed_review",
        }:
            raise ContributionPolicyConflict("contribution_policy_conflict")
        for rule in rules:
            count = len(rule.award_definitions)
            if (rule.compensation_mode == "unpaid" and count) or (
                rule.compensation_mode == "compensated" and not 1 <= count <= 2
            ):
                raise ContributionPolicyConflict("contribution_policy_conflict")

    def _require_request(self, request: object, expected: type[object]) -> None:
        if (
            type(request) is not expected
            or not self._session.in_transaction()
            or self._session.in_nested_transaction()
        ):
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        for name in (
            "operation_id",
            "actor_profile_id",
            "project_id",
            "contribution_policy_id",
            "contribution_policy_version_id",
        ):
            if not isinstance(getattr(request, name, None), UUID):
                raise ContributionPolicyUnavailable("contribution_policy_unavailable")

    @staticmethod
    def _custody(request, digest, event_type, prior):
        return ContributionPolicyTransitionCustody(
            operation_id=request.operation_id,
            request_digest=digest,
            event_type=event_type,
            actor_profile_id=str(request.actor_profile_id),
            project_id=str(request.project_id),
            contribution_policy_id=request.contribution_policy_id,
            contribution_policy_version_id=request.contribution_policy_version_id,
            prior_current_version_id=prior.id if prior else None,
        )

    @staticmethod
    def _apply_publication(policy, version, prior, actor, custody) -> None:
        if prior is not None:
            prior.status = "retired"
            prior.retired_by = str(actor)
            prior.retired_at = custody.occurred_at
            prior.last_transition_operation_id = custody.operation_id
        version.status = "published"
        version.published_by = str(actor)
        version.published_at = custody.occurred_at
        version.last_transition_operation_id = custody.operation_id
        policy.status = "active"
        policy.current_published_version_id = version.id
        policy.last_transition_operation_id = custody.operation_id

    @staticmethod
    def _event(request, digest, event_type, policy, version, prior, custody):
        return ContributionPolicyLifecycleEvent(
            id=uuid4(),
            operation_id=request.operation_id,
            publication_custody_operation_id=request.operation_id,
            request_digest=digest,
            event_type=event_type,
            actor_profile_id=str(request.actor_profile_id),
            project_id=str(request.project_id),
            contribution_policy_id=policy.id,
            contribution_policy_version_id=version.id,
            version_number=version.version_number,
            prior_current_version_id=prior.id if prior else None,
            prior_current_version_number=prior.version_number if prior else None,
            from_policy_status="active" if event_type == "retired" or prior else "draft",
            to_policy_status=policy.status,
            from_version_status="draft" if event_type == "published" else "published",
            to_version_status=version.status,
            occurred_at=custody.occurred_at,
        )

    @staticmethod
    def _result(event):
        return ContributionPolicyMutationResult(
            event_id=event.id,
            operation_id=event.operation_id,
            request_digest=event.request_digest,
            event_type=event.event_type,
            actor_profile_id=UUID(event.actor_profile_id),
            project_id=UUID(event.project_id),
            contribution_policy_id=event.contribution_policy_id,
            contribution_policy_version_id=event.contribution_policy_version_id,
            version_number=event.version_number,
            prior_current_version_id=event.prior_current_version_id,
            prior_current_version_number=event.prior_current_version_number,
            from_policy_status=event.from_policy_status,
            to_policy_status=event.to_policy_status,
            from_version_status=event.from_version_status,
            to_version_status=event.to_version_status,
            occurred_at=event.occurred_at,
        )
