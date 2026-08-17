"""Small fakes for hidden ContributionPolicy service tests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import app.db.models  # noqa: F401
from app.modules.compensation.api import (
    CompensationInstrumentType,
    LockedPolicyAdapterBindingFacts,
)
from app.modules.contributions.api import (
    ContributionPolicyCreateDraftRequest,
    ContributionPolicyMutationAuthorizationFacts,
    ContributionPolicyReadRequest,
    PolicyDefinitionInput,
    PolicyRuleInput,
)
from app.modules.contributions.service import ContributionPolicyService
from app.modules.projects.api import ProjectContributionPolicyEligibilityFacts


class FakeSession:
    """Expose only transaction state and database time used by the service."""

    def __init__(self) -> None:
        self.transaction = object()

    def in_transaction(self) -> bool:
        return True

    def in_nested_transaction(self) -> bool:
        return False

    async def scalar(self, statement: object) -> datetime:
        del statement
        return datetime.now(UTC)


class AllowAuthorization:
    """Record opaque PREP lifecycle calls."""

    def __init__(self, actor_id: UUID) -> None:
        self.actor_id = actor_id
        self.prepared: list[ContributionPolicyMutationAuthorizationFacts] = []
        self.consumed: list[ContributionPolicyMutationAuthorizationFacts] = []
        self.closed: list[object] = []
        self.reads: list[ContributionPolicyReadRequest] = []

    async def authorize_contribution_policy_read(
        self, request: ContributionPolicyReadRequest
    ) -> None:
        self.reads.append(request)

    async def prepare_contribution_policy_mutation(
        self, facts: ContributionPolicyMutationAuthorizationFacts
    ) -> object:
        self.prepared.append(facts)
        return object()

    async def consume_contribution_policy_mutation(
        self, prepared: object, facts: ContributionPolicyMutationAuthorizationFacts
    ) -> UUID:
        del prepared
        self.consumed.append(facts)
        return self.actor_id

    def close_contribution_policy_mutation(self, prepared: object) -> None:
        self.closed.append(prepared)


class AllowProject:
    async def lock_contribution_policy_project(
        self, project_id: UUID
    ) -> ProjectContributionPolicyEligibilityFacts:
        return ProjectContributionPolicyEligibilityFacts(project_id=project_id)


class AllowBinding:
    async def lock_policy_adapter_binding(
        self,
        *,
        project_id: UUID,
        adapter_binding_id: UUID,
        instrument_type: CompensationInstrumentType,
    ) -> LockedPolicyAdapterBindingFacts:
        return LockedPolicyAdapterBindingFacts(
            project_id=project_id,
            adapter_binding_id=adapter_binding_id,
            instrument_type=instrument_type,
            binding_lifecycle_version=1,
        )


def service_fixture() -> SimpleNamespace:
    actor_id, project_id = uuid4(), uuid4()
    authorization = AllowAuthorization(actor_id)
    service = ContributionPolicyService(
        FakeSession(),  # type: ignore[arg-type]
        read_authorization=authorization,
        mutation_authorization=authorization,
        projects=AllowProject(),
        bindings=AllowBinding(),
    )
    repository = SimpleNamespace(
        lock_operation=AsyncMock(),
        get_event_by_operation=AsyncMock(return_value=None),
        lock_project_scope=AsyncMock(),
        get_open_draft=AsyncMock(return_value=None),
        get_reusable_policy=AsyncMock(return_value=None),
        next_version_number=AsyncMock(return_value=1),
        add_policy_version_event=AsyncMock(),
        get_policy=AsyncMock(return_value=None),
        get_version=AsyncMock(return_value=None),
        get_selected_version=AsyncMock(return_value=None),
        lock_unit=AsyncMock(
            return_value=SimpleNamespace(status="active")
        ),
        replace_graph=AsyncMock(),
    )
    service._repository = repository  # noqa: SLF001
    return SimpleNamespace(
        actor_id=actor_id,
        project_id=project_id,
        authorization=authorization,
        service=service,
        repository=repository,
    )


def create_request(fixture: SimpleNamespace) -> ContributionPolicyCreateDraftRequest:
    return ContributionPolicyCreateDraftRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        name="Canonical contribution policy",
    )


def complete_rules() -> tuple[PolicyRuleInput, ...]:
    return (
        PolicyRuleInput(
            contribution_type="accepted_submission",
            compensation_mode="compensated",
            definitions=(
                PolicyDefinitionInput(
                    instrument_type=CompensationInstrumentType.MONEY,
                    unit_code="USD",
                    quantity="10.00",
                    adapter_binding_id=uuid4(),
                ),
            ),
        ),
        PolicyRuleInput(
            contribution_type="completed_review",
            compensation_mode="unpaid",
        ),
    )
