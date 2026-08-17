"""Real PostgreSQL proof for hidden ContributionPolicy behavior."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.compensation import policy_adapter_binding_port
from app.adapters.projects import project_contribution_policy_eligibility_port
from app.core.config import get_settings
from app.db import session as db_session
from app.modules.compensation.api import CompensationInstrumentType
from app.modules.contributions.api import (
    ContributionPolicyCreateDraftRequest,
    ContributionPolicyMutationAuthorizationFacts,
    ContributionPolicyMutationResult,
    ContributionPolicyReadRequest,
    ContributionPolicyUpdateDraftRequest,
    PolicyDefinitionInput,
    PolicyRuleInput,
)
from app.modules.contributions.models import (
    ContributionAwardDefinition,
    ContributionPolicy,
    ContributionPolicyLifecycleEvent,
    ContributionPolicyVersion,
    ContributionRule,
)
from app.modules.contributions.repository import ContributionPolicyRepository
from app.modules.contributions.service import ContributionPolicyService
from test_contributions import _seed_project
from tests.contributions.policy_test_support import AllowAuthorization


class _ParticipantAuthorization(AllowAuthorization):
    """Stage transaction-local authorization evidence during consumption."""

    def __init__(self, actor_id: UUID, session: AsyncSession) -> None:
        super().__init__(actor_id)
        self._session = session

    async def consume_contribution_policy_mutation(
        self, prepared: object, facts: ContributionPolicyMutationAuthorizationFacts
    ) -> UUID:
        actor = await super().consume_contribution_policy_mutation(prepared, facts)
        await self._session.execute(
            text("insert into cp04a_staged_authorization_effects values (:operation_id)"),
            {"operation_id": str(facts.operation_id)},
        )
        return actor


class _LateFailingRepository(ContributionPolicyRepository):
    """Fail only after the complete replacement graph has reached PostgreSQL."""

    async def replace_graph(self, version, rules, definitions, event) -> None:
        await super().replace_graph(version, rules, definitions, event)
        raise RuntimeError("late_product_write_failed")


@pytest.fixture(name="policy_database_env")
def _policy_database_env(
    monkeypatch: pytest.MonkeyPatch,
    clean_postgres_database: str,
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()


async def _exercise_policy() -> tuple[
    UUID, ContributionPolicyMutationResult, ContributionPolicyMutationResult
]:
    project, creator, _, money_binding, _ = await _seed_project()
    actor_id, project_id = UUID(creator), UUID(project)
    authorization = AllowAuthorization(actor_id)
    async with db_session.get_session_factory()() as session:
        async with session.begin():
            service = ContributionPolicyService(
                session,
                read_authorization=authorization,
                mutation_authorization=authorization,
                projects=project_contribution_policy_eligibility_port(session),
                bindings=policy_adapter_binding_port(session),
            )
            created = await service.create_draft(
                ContributionPolicyCreateDraftRequest(
                    operation_id=uuid4(),
                    actor_profile_id=actor_id,
                    project_id=project_id,
                    name="Integrated policy",
                )
            )
            updated = await service.update_draft(
                ContributionPolicyUpdateDraftRequest(
                    operation_id=uuid4(),
                    actor_profile_id=actor_id,
                    project_id=project_id,
                    contribution_policy_id=created.contribution_policy_id,
                    contribution_policy_version_id=created.contribution_policy_version_id,
                    rules=(
                        PolicyRuleInput(
                            contribution_type="accepted_submission",
                            compensation_mode="compensated",
                            definitions=(
                                PolicyDefinitionInput(
                                    instrument_type=CompensationInstrumentType.MONEY,
                                    unit_code="USD",
                                    quantity="25.50",
                                    adapter_binding_id=money_binding,
                                ),
                            ),
                        ),
                        PolicyRuleInput(
                            contribution_type="completed_review",
                            compensation_mode="unpaid",
                        ),
                    ),
                )
            )
            view = await service.read(
                ContributionPolicyReadRequest(
                    actor_profile_id=actor_id,
                    project_id=project_id,
                    contribution_policy_id=created.contribution_policy_id,
                    contribution_policy_version_id=created.contribution_policy_version_id,
                )
            )
            assert updated.event_type == "draft_updated"
            assert len(view.rules) == 2
    return project_id, created, updated


@pytest.mark.asyncio
async def test_real_service_persists_complete_graph_and_events(
    policy_database_env: str,
) -> None:
    del policy_database_env
    project_id, created, updated = await _exercise_policy()
    async with db_session.get_session_factory()() as session:
        count = await session.scalar(
            select(func.count()).select_from(ContributionPolicyLifecycleEvent).where(
                ContributionPolicyLifecycleEvent.project_id == str(project_id)
            )
        )
        assert count == 2
        assert created.event_id != updated.event_id


@pytest.mark.asyncio
async def test_late_database_failure_rolls_back_product_and_authorization_effects(
    policy_database_env: str,
) -> None:
    del policy_database_env
    project, creator, _, money_binding, _ = await _seed_project()
    actor_id, project_id = UUID(creator), UUID(project)
    async with (
        db_session.get_engine().connect() as connection,
        AsyncSession(bind=connection, expire_on_commit=False) as session,
    ):
        async with session.begin():
            await session.execute(
                text(
                    "create temporary table cp04a_staged_authorization_effects "
                    "(operation_id uuid primary key) on commit preserve rows"
                )
            )
        authorization = _ParticipantAuthorization(actor_id, session)
        service = ContributionPolicyService(
            session,
            read_authorization=authorization,
            mutation_authorization=authorization,
            projects=project_contribution_policy_eligibility_port(session),
            bindings=policy_adapter_binding_port(session),
        )
        service._repository = _LateFailingRepository(session)  # noqa: SLF001
        with pytest.raises(RuntimeError, match="late_product_write_failed"):
            async with session.begin():
                created = await service.create_draft(
                    ContributionPolicyCreateDraftRequest(
                        operation_id=uuid4(),
                        actor_profile_id=actor_id,
                        project_id=project_id,
                        name="Rolled back policy",
                    )
                )
                await service.update_draft(
                    ContributionPolicyUpdateDraftRequest(
                        operation_id=uuid4(),
                        actor_profile_id=actor_id,
                        project_id=project_id,
                        contribution_policy_id=created.contribution_policy_id,
                        contribution_policy_version_id=(
                            created.contribution_policy_version_id
                        ),
                        rules=(
                            PolicyRuleInput(
                                contribution_type="accepted_submission",
                                compensation_mode="compensated",
                                definitions=(
                                    PolicyDefinitionInput(
                                        instrument_type=CompensationInstrumentType.MONEY,
                                        unit_code="USD",
                                        quantity="25.50",
                                        adapter_binding_id=money_binding,
                                    ),
                                ),
                            ),
                            PolicyRuleInput(
                                contribution_type="completed_review",
                                compensation_mode="unpaid",
                            ),
                        ),
                    )
                )
        assert len(authorization.closed) == 2
        async with session.begin():
            for model in (
                ContributionAwardDefinition,
                ContributionRule,
                ContributionPolicyLifecycleEvent,
                ContributionPolicyVersion,
                ContributionPolicy,
            ):
                assert await session.scalar(select(func.count()).select_from(model)) == 0
            assert await session.scalar(
                text("select count(*) from cp04a_staged_authorization_effects")
            ) == 0
