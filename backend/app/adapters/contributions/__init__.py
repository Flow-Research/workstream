"""CONTRIBUTIONS-owned composition adapters."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.compensation import policy_adapter_binding_port
from app.adapters.projects import project_contribution_policy_eligibility_port
from app.modules.contributions.api import (
    ContributionPolicyMutationAuthorizationPort,
    ContributionPolicyReadAuthorizationPort,
)
from app.modules.contributions.service import ContributionPolicyService


def contribution_policy_service(
    session: AsyncSession,
    *,
    read_authorization: ContributionPolicyReadAuthorizationPort | None = None,
    mutation_authorization: ContributionPolicyMutationAuthorizationPort | None = None,
) -> ContributionPolicyService:
    """Compose hidden policy behavior exclusively through public owner ports."""
    return ContributionPolicyService(
        session,
        read_authorization=read_authorization,
        mutation_authorization=mutation_authorization,
        projects=project_contribution_policy_eligibility_port(session),
        bindings=policy_adapter_binding_port(session),
    )
