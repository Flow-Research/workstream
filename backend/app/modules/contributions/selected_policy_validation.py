"""CON-owned exact selection validation inside the caller's transaction."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.modules.compensation.api import PolicyAdapterBindingPort
from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyUnavailable,
    ContributionPolicyValidationFacts,
    ContributionPolicyValidationPurpose,
    ContributionPolicyValidationRequest,
)
from app.modules.contributions.policy_eligibility import (
    lock_policy_resources,
    require_complete_policy_graph,
)
from app.modules.contributions.policy_graph import publication_graph_facts
from app.modules.contributions.repository import ContributionPolicyRepository
from app.modules.projects.api import (
    ProjectContributionPolicyEligibilityPort,
    ProjectContributionPolicyUnavailable,
)


class SelectedContributionPolicyValidation:
    """Validate resources without authorizing or writing a guide or work attempt."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        projects: ProjectContributionPolicyEligibilityPort,
        bindings: PolicyAdapterBindingPort,
    ) -> None:
        """Explicitly compose owner ports in the same caller-owned session."""
        self._session = session
        self._repository = ContributionPolicyRepository(session)
        self._projects = projects
        self._bindings = bindings

    async def validate_contribution_policy(
        self, request: ContributionPolicyValidationRequest
    ) -> ContributionPolicyValidationFacts:
        """Lock exact eligibility; returned facts are not transferable authority."""
        self._require_request(request)
        try:
            return await self._validate(request)
        except (ContributionPolicyConflict, ProjectContributionPolicyUnavailable):
            raise ContributionPolicyUnavailable("contribution_policy_unavailable") from None

    async def _validate(
        self, request: ContributionPolicyValidationRequest
    ) -> ContributionPolicyValidationFacts:
        """Follow publication's project-first lock order without selecting a version."""
        project = await self._projects.lock_contribution_policy_project(request.project_id)
        if project.project_id != request.project_id:
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        await self._repository.lock_project_scope(request.project_id)
        policy = await self._repository.get_policy(
            request.project_id, request.contribution_policy_id, for_update=True
        )
        if policy is None or policy.status not in {"active", "retired"}:
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        if request.purpose is ContributionPolicyValidationPurpose.GUIDE_ACTIVATION and (
            policy.status != "active"
            or policy.current_published_version_id != request.contribution_policy_version_id
        ):
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        version = await self._repository.get_version(
            request.project_id,
            request.contribution_policy_id,
            request.contribution_policy_version_id,
            for_update=True,
        )
        if version is None or version.status not in {"published", "retired"}:
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        if (
            request.purpose is ContributionPolicyValidationPurpose.GUIDE_ACTIVATION
            and version.status != "published"
        ):
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        rules, definitions = await self._repository.lock_publication_graph(version.id)
        require_complete_policy_graph(version, rules, definitions)
        set_committed_value(version, "rules", rules)
        await lock_policy_resources(
            self._repository, self._bindings, request.project_id, definitions
        )
        digest, binding_ids = publication_graph_facts(version)
        return ContributionPolicyValidationFacts(
            project_id=request.project_id,
            contribution_policy_id=policy.id,
            contribution_policy_version_id=version.id,
            purpose=request.purpose,
            version_number=version.version_number,
            rules_and_definitions_digest=digest,
            adapter_binding_ids=binding_ids,
        )

    def _require_request(self, request: object) -> None:
        """Reject malformed selections and missing/rootless transaction custody."""
        if (
            type(request) is not ContributionPolicyValidationRequest
            or not self._session.in_transaction()
            or self._session.in_nested_transaction()
            or type(request.purpose) is not ContributionPolicyValidationPurpose
            or any(
                not isinstance(getattr(request, field), UUID)
                for field in (
                    "project_id",
                    "contribution_policy_id",
                    "contribution_policy_version_id",
                )
            )
        ):
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
