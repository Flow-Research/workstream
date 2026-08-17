"""Hidden ContributionPolicy read and draft mutation orchestration."""

from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compensation.api import (
    CompensationInstrumentType,
    PolicyAdapterBindingPort,
    PolicyAdapterBindingUnavailable,
)
from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyCreateDraftRequest,
    ContributionPolicyMutationAuthorizationFacts,
    ContributionPolicyMutationAuthorizationPort,
    ContributionPolicyMutationResult,
    ContributionPolicyProjectEligibilityPort,
    ContributionPolicyReadAuthorizationPort,
    ContributionPolicyReadRequest,
    ContributionPolicyPublishRequest,
    ContributionPolicyRetireRequest,
    ContributionPolicyUnavailable,
    ContributionPolicyUpdateDraftRequest,
    ContributionPolicyView,
    DenyContributionPolicyAuthorization,
    PolicyAction,
    PolicyDefinitionView,
    PolicyEventType,
    PolicyRuleInput,
    PolicyRuleView,
)
from app.modules.contributions.models import (
    ContributionAwardDefinition,
    ContributionPolicy,
    ContributionPolicyLifecycleEvent,
    ContributionPolicyVersion,
    ContributionRule,
)
from app.modules.contributions.policy_validation import (
    policy_request_digest,
    validate_policy_graph,
    validate_policy_name,
)
from app.modules.contributions.policy_publication import ContributionPolicyPublicationService
from app.modules.contributions.policy_mutation_support import (
    begin_and_recover_policy_mutation,
)
from app.modules.contributions.repository import ContributionPolicyRepository
from app.modules.projects.api import ProjectContributionPolicyUnavailable


class ContributionPolicyService:
    """Run hidden policy behavior without route or commit ownership."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        read_authorization: ContributionPolicyReadAuthorizationPort | None = None,
        mutation_authorization: ContributionPolicyMutationAuthorizationPort | None = None,
        projects: ContributionPolicyProjectEligibilityPort | None = None,
        bindings: PolicyAdapterBindingPort | None = None,
    ) -> None:
        """Compose hidden policy behavior inside a caller-owned session."""
        deny = DenyContributionPolicyAuthorization()
        self._session = session
        self._repository = ContributionPolicyRepository(session)
        self._read_authorization = read_authorization or deny
        self._mutation_authorization = mutation_authorization or deny
        self._projects = projects
        self._bindings = bindings
        self._publication = ContributionPolicyPublicationService(
            session,
            repository=self._repository,
            read_authorization=self._read_authorization,
            mutation_authorization=self._mutation_authorization,
            projects=projects,
            bindings=bindings,
        )

    async def publish(
        self, request: ContributionPolicyPublishRequest
    ) -> ContributionPolicyMutationResult:
        """Publish one exact complete draft through the hidden boundary."""
        return await self._publication.publish(request)

    async def retire(
        self, request: ContributionPolicyRetireRequest
    ) -> ContributionPolicyMutationResult:
        """Terminally retire one exact current published version."""
        return await self._publication.retire(request)

    async def read(self, request: ContributionPolicyReadRequest) -> ContributionPolicyView:
        """Return one authorized immutable policy-version view."""
        self._require_request(request, ContributionPolicyReadRequest, mutation=False)
        try:
            await self._read_authorization.authorize_contribution_policy_read(request)
        except (ContributionPolicyUnavailable, ContributionPolicyConflict) as exc:
            raise ContributionPolicyConflict("contribution_policy_not_found") from exc
        policy = await self._repository.get_policy(
            request.project_id, request.contribution_policy_id
        )
        if policy is None:
            raise ContributionPolicyConflict("contribution_policy_not_found")
        version = await self._repository.get_selected_version(
            policy, request.contribution_policy_version_id
        )
        if version is None:
            raise ContributionPolicyConflict("contribution_policy_not_found")
        return self._view(policy, version)

    async def create_draft(
        self, request: ContributionPolicyCreateDraftRequest
    ) -> ContributionPolicyMutationResult:
        """Create a first or next draft under exact project custody."""
        self._require_request(request, ContributionPolicyCreateDraftRequest, mutation=True)
        validate_policy_name(request.name)
        action: PolicyAction = "contribution.policy.create_draft"
        digest = policy_request_digest(action, request)
        recovered = await self._recover(action, request, digest)
        if recovered is not None:
            return recovered
        project = await self._lock_project(request.project_id)
        await self._repository.lock_project_scope(request.project_id)
        if project != request.project_id:
            raise ContributionPolicyConflict("contribution_policy_not_found")
        if await self._repository.get_open_draft(request.project_id) is not None:
            raise ContributionPolicyConflict("contribution_policy_conflict")
        policy = await self._repository.get_reusable_policy(request.project_id)
        # Keep the service boundary fail-closed if repository filtering regresses:
        # retired aggregates are terminal and must never receive another draft.
        if policy is not None and policy.status == "retired":
            policy = None
        if policy is None:
            policy = ContributionPolicy(
                id=uuid4(),
                project_id=str(request.project_id),
                name=request.name,
                status="draft",
                current_published_version_id=None,
                created_by=str(request.actor_profile_id),
            )
            version_number = 1
            prior_id = None
            prior_number = None
            from_policy_status = None
        else:
            version_number = await self._repository.next_version_number(policy.id)
            prior_id = policy.current_published_version_id
            prior_number = await self._prior_version_number(policy, prior_id)
            from_policy_status = policy.status
        version = ContributionPolicyVersion(
            id=uuid4(),
            contribution_policy_id=policy.id,
            project_id=str(request.project_id),
            version_number=version_number,
            status="draft",
            created_by=str(request.actor_profile_id),
        )
        facts = self._facts(
            action, request, digest, policy.id, version.id, from_policy_status, None
        )
        actor = await self._consume_and_close(facts)
        event = self._event(
            request=request,
            digest=digest,
            event_type="draft_created",
            actor=actor,
            policy=policy,
            version=version,
            prior_id=prior_id,
            prior_number=prior_number,
            from_policy_status=from_policy_status,
            from_version_status=None,
        )
        await self._repository.add_policy_version_event(policy, version, event)
        return self._result(event)

    async def update_draft(
        self, request: ContributionPolicyUpdateDraftRequest
    ) -> ContributionPolicyMutationResult:
        """Replace one exact draft graph after all owner and AUTH checks."""
        self._require_request(request, ContributionPolicyUpdateDraftRequest, mutation=True)
        rules = validate_policy_graph(request.rules)
        action: PolicyAction = "contribution.policy.update_draft"
        digest = policy_request_digest(action, request)
        recovered = await self._recover(action, request, digest)
        if recovered is not None:
            return recovered
        project = await self._lock_project(request.project_id)
        if project != request.project_id:
            raise ContributionPolicyConflict("contribution_policy_not_found")
        policy = await self._repository.get_policy(
            request.project_id, request.contribution_policy_id, for_update=True
        )
        version = await self._repository.get_version(
            request.project_id,
            request.contribution_policy_id,
            request.contribution_policy_version_id,
            for_update=True,
        )
        if (
            policy is None
            or policy.status not in {"draft", "active"}
            or version is None
            or version.status != "draft"
        ):
            raise ContributionPolicyConflict("contribution_policy_not_found")
        built_rules, definitions = await self._lock_resources_and_build(request, rules)
        facts = self._facts(
            action, request, digest, policy.id, version.id, policy.status, version.status
        )
        actor = await self._consume_and_close(facts)
        version.last_updated_by = str(actor)
        version.last_updated_at = await self._session.scalar(select(func.clock_timestamp()))
        event = self._event(
            request=request,
            digest=digest,
            event_type="draft_updated",
            actor=actor,
            policy=policy,
            version=version,
            prior_id=policy.current_published_version_id,
            prior_number=await self._prior_version_number(
                policy, policy.current_published_version_id
            ),
            from_policy_status=policy.status,
            from_version_status="draft",
        )
        await self._repository.replace_graph(version, built_rules, definitions, event)
        return self._result(event)

    def _require_request(self, request: object, expected: type[object], *, mutation: bool) -> None:
        """Reject wrong request types, transaction shape, or selector types."""
        if type(request) is not expected:
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        if mutation and (
            not self._session.in_transaction() or self._session.in_nested_transaction()
        ):
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        selectors = ("actor_profile_id", "project_id")
        if mutation:
            selectors += ("operation_id",)
        if type(request) is not ContributionPolicyCreateDraftRequest:
            selectors += ("contribution_policy_id",)
        if type(request) is ContributionPolicyUpdateDraftRequest:
            selectors += ("contribution_policy_version_id",)
        elif (
            type(request) is ContributionPolicyReadRequest
            and getattr(request, "contribution_policy_version_id", None) is not None
        ):
            selectors += ("contribution_policy_version_id",)
        for name in selectors:
            if not isinstance(getattr(request, name), UUID):
                raise ContributionPolicyUnavailable("contribution_policy_unavailable")

    async def _lock_project(self, project_id: UUID) -> UUID:
        """Acquire the PROJECTS-owned eligibility fence or conceal failure."""
        if self._projects is None:
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        try:
            facts = await self._projects.lock_contribution_policy_project(project_id)
        except ProjectContributionPolicyUnavailable as exc:
            raise ContributionPolicyConflict("contribution_policy_not_found") from exc
        return facts.project_id

    async def _lock_resources_and_build(
        self,
        request: ContributionPolicyUpdateDraftRequest,
        rules: tuple[PolicyRuleInput, ...],
    ) -> tuple[list[ContributionRule], list[ContributionAwardDefinition]]:
        """Lock referenced resources and build a complete replacement graph."""
        if self._bindings is None:
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        built_rules: list[ContributionRule] = []
        definitions: list[ContributionAwardDefinition] = []
        for rule_input in rules:
            rule_id = uuid4()
            built_rules.append(
                ContributionRule(
                    id=rule_id,
                    contribution_policy_version_id=request.contribution_policy_version_id,
                    project_id=str(request.project_id),
                    contribution_type=rule_input.contribution_type,
                    compensation_mode=rule_input.compensation_mode,
                )
            )
            for item in rule_input.definitions:
                unit = await self._repository.lock_unit(
                    request.project_id, item.instrument_type.value, item.unit_code
                )
                if unit is None or unit.status != "active":
                    raise ContributionPolicyConflict("contribution_policy_not_found")
                try:
                    binding = await self._bindings.lock_policy_adapter_binding(
                        project_id=request.project_id,
                        adapter_binding_id=item.adapter_binding_id,
                        instrument_type=item.instrument_type,
                    )
                except PolicyAdapterBindingUnavailable as exc:
                    raise ContributionPolicyConflict("contribution_policy_not_found") from exc
                if (
                    binding.project_id != request.project_id
                    or binding.adapter_binding_id != item.adapter_binding_id
                    or binding.instrument_type is not item.instrument_type
                ):
                    raise ContributionPolicyConflict("contribution_policy_not_found")
                definitions.append(
                    ContributionAwardDefinition(
                        id=uuid4(),
                        contribution_rule_id=rule_id,
                        contribution_policy_version_id=request.contribution_policy_version_id,
                        project_id=str(request.project_id),
                        contribution_type=rule_input.contribution_type,
                        instrument_type=item.instrument_type.value,
                        unit_code=item.unit_code,
                        quantity=Decimal(item.quantity),
                        adapter_binding_id=item.adapter_binding_id,
                    )
                )
        return built_rules, definitions

    def _facts(
        self,
        action: PolicyAction,
        request: object,
        digest: str,
        policy_id: UUID,
        version_id: UUID,
        policy_status: str | None,
        version_status: str | None,
    ) -> ContributionPolicyMutationAuthorizationFacts:
        """Bind exact command and lifecycle facts for mutation authorization."""
        return ContributionPolicyMutationAuthorizationFacts(
            action=action,
            actor_profile_id=cast(UUID, getattr(request, "actor_profile_id")),
            operation_id=cast(UUID, getattr(request, "operation_id")),
            request_digest=digest,
            project_id=cast(UUID, getattr(request, "project_id")),
            contribution_policy_id=policy_id,
            contribution_policy_version_id=version_id,
            expected_policy_status=policy_status,
            expected_version_status=version_status,
        )

    async def _consume_and_close(self, facts: ContributionPolicyMutationAuthorizationFacts) -> UUID:
        """Prepare, consume, and always close exact mutation authority."""
        prepared = await self._mutation_authorization.prepare_contribution_policy_mutation(facts)
        try:
            actor = await self._mutation_authorization.consume_contribution_policy_mutation(
                prepared, facts
            )
        finally:
            self._mutation_authorization.close_contribution_policy_mutation(prepared)
        if type(actor) is not UUID or actor != facts.actor_profile_id:
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        return actor

    async def _recover(
        self, action: PolicyAction, request: object, digest: str
    ) -> ContributionPolicyMutationResult | None:
        """Recover an exact prior result only after current read authorization."""
        expected = "draft_created" if action.endswith("create_draft") else "draft_updated"
        return await begin_and_recover_policy_mutation(
            repository=self._repository,
            read_authorization=self._read_authorization,
            request=request,
            request_digest=digest,
            expected_event_type=expected,
            result_factory=self._result,
        )

    async def _prior_version_number(
        self, policy: ContributionPolicy, version_id: UUID | None
    ) -> int | None:
        """Resolve the prior published version number for event lineage."""
        if version_id is None:
            return None
        version = await self._repository.get_version(UUID(policy.project_id), policy.id, version_id)
        return version.version_number if version else None

    @staticmethod
    def _event(
        *,
        request: object,
        digest: str,
        event_type: PolicyEventType,
        actor: UUID,
        policy: ContributionPolicy,
        version: ContributionPolicyVersion,
        prior_id: UUID | None,
        prior_number: int | None,
        from_policy_status: str | None,
        from_version_status: str | None,
    ) -> ContributionPolicyLifecycleEvent:
        """Build one immutable, attributable lifecycle event."""
        return ContributionPolicyLifecycleEvent(
            id=uuid4(),
            operation_id=getattr(request, "operation_id"),
            request_digest=digest,
            event_type=event_type,
            actor_profile_id=str(actor),
            project_id=policy.project_id,
            contribution_policy_id=policy.id,
            contribution_policy_version_id=version.id,
            version_number=version.version_number,
            prior_current_version_id=prior_id,
            prior_current_version_number=prior_number,
            from_policy_status=from_policy_status,
            to_policy_status=policy.status,
            from_version_status=from_version_status,
            to_version_status=version.status,
        )

    @staticmethod
    def _result(event: ContributionPolicyLifecycleEvent) -> ContributionPolicyMutationResult:
        """Project immutable lifecycle evidence into a mutation result."""
        return ContributionPolicyMutationResult(
            event_id=event.id,
            operation_id=event.operation_id,
            request_digest=event.request_digest,
            event_type=cast(PolicyEventType, event.event_type),
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

    @staticmethod
    def _view(
        policy: ContributionPolicy, version: ContributionPolicyVersion
    ) -> ContributionPolicyView:
        """Project an ORM graph into immutable public policy facts."""
        rules = tuple(
            PolicyRuleView(
                rule_id=rule.id,
                contribution_type=cast(object, rule.contribution_type),  # type: ignore[arg-type]
                compensation_mode=cast(object, rule.compensation_mode),  # type: ignore[arg-type]
                definitions=tuple(
                    PolicyDefinitionView(
                        definition_id=item.id,
                        instrument_type=CompensationInstrumentType(item.instrument_type),
                        unit_code=item.unit_code,
                        quantity=format(item.quantity, "f"),
                        adapter_binding_id=item.adapter_binding_id,
                    )
                    for item in sorted(
                        rule.award_definitions, key=lambda value: value.instrument_type
                    )
                ),
            )
            for rule in sorted(version.rules, key=lambda value: value.contribution_type)
        )
        return ContributionPolicyView(
            project_id=UUID(policy.project_id),
            contribution_policy_id=policy.id,
            name=policy.name,
            policy_status=policy.status,
            contribution_policy_version_id=version.id,
            version_number=version.version_number,
            version_status=version.status,
            rules=rules,
        )
