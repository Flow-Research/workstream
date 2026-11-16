"""PostgreSQL proof for project points-unit creation, replay and immutability."""

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.adapters.contributions import project_compensation_unit_service
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.contributions.api import (
    CompensationUnitCreateAuthorizationFacts,
    ContributionPolicyAuthorizationUnavailable,
    ContributionPolicyConflict,
    ContributionPolicyUnavailable,
    ProjectCompensationUnitCreateRequest,
)
from app.modules.contributions.units.service import ProjectCompensationUnitService
from app.modules.contributions.units.models import (
    ProjectCompensationUnit,
)
from app.modules.contributions.repository import ContributionPolicyRepository
from app.modules.contributions.units.models import ProjectCompensationUnitCreationEvent
from app.modules.projects.api import (
    ProjectContributionPolicyEligibilityFacts,
    ProjectContributionPolicyUnavailable,
)
from project_create_fixtures import insert_historical_project
from tests.contributions.policy_test_support import AllowAuthorization


@pytest.fixture(name="unit_database_env")
def _unit_database_env(
    monkeypatch: pytest.MonkeyPatch, clean_postgres_database: str
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()


async def _seed() -> tuple[UUID, UUID]:
    """Insert one active human actor and one project; return (project, actor)."""
    project_id, actor_id = new_record_id(), new_record_id()
    async with db_session.get_session_factory()() as session, session.begin():
        session.add(ActorProfile(
            id=str(actor_id), actor_kind="human", status="active",
            provisioning_method="automatic_first_access", created_by=str(actor_id),
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(new_record_id()), actor_profile_id=str(actor_id),
            issuer="https://units.test", subject=f"finance-{actor_id}", subject_kind="human",
            status="active", linked_by=str(actor_id), last_verified_at=datetime.now(UTC),
        ))
        await insert_historical_project(
            session, project_id=str(project_id), name="Unit project",
            slug=f"unit-{project_id.hex}",
        )
    return project_id, actor_id


def _request(project_id: UUID, actor_id: UUID, **changes) -> ProjectCompensationUnitCreateRequest:
    values = dict(
        operation_id=new_record_id(), actor_profile_id=actor_id, project_id=project_id,
        instrument_type="project_points", unit_code="FLOW",
    )
    values.update(changes)
    return ProjectCompensationUnitCreateRequest(**values)


async def _create(request, authorization, *, service_factory=None):
    async with db_session.get_session_factory()() as session, session.begin():
        if service_factory is None:
            service = project_compensation_unit_service(
                session, mutation_authorization=authorization
            )
        else:
            service = service_factory(session)
        return await service.create(request)


async def _counts() -> tuple[int, int]:
    async with db_session.get_session_factory()() as session:
        units = await session.scalar(select(func.count()).select_from(ProjectCompensationUnit))
        events = await session.scalar(
            select(func.count()).select_from(ProjectCompensationUnitCreationEvent)
        )
    return units, events


@pytest.mark.asyncio
async def test_create_persists_active_unit_event_and_exact_authority_facts(
    unit_database_env: str,
) -> None:
    project_id, actor_id = await _seed()
    authorization = AllowAuthorization(actor_id)
    request = _request(project_id, actor_id)

    result = await _create(request, authorization)

    assert (result.project_id, result.instrument_type, result.unit_code) == (
        project_id, "project_points", "FLOW"
    )
    assert result.actor_profile_id == actor_id and result.operation_id == request.operation_id
    assert result.request_digest.startswith("sha256:")
    async with db_session.get_session_factory()() as session:
        unit = await session.get(ProjectCompensationUnit, (str(project_id), "project_points", "FLOW"))
    assert unit is not None and unit.status == "active" and unit.created_by == str(actor_id)
    assert unit.iso_currency_code is None
    assert authorization.scopes == [{
        "action": "contribution.compensation_unit.create",
        "actor_profile_id": actor_id, "project_id": project_id,
    }]
    assert authorization.prepared == authorization.consumed == [
        CompensationUnitCreateAuthorizationFacts(
            action="contribution.compensation_unit.create", actor_profile_id=actor_id,
            operation_id=request.operation_id, request_digest=result.request_digest,
            project_id=project_id, instrument_type="project_points", unit_code="FLOW",
        )
    ]
    assert authorization.closed == authorization.prepared_handles
    assert await _counts() == (1, 1)


@pytest.mark.asyncio
async def test_identical_replay_returns_stored_result_after_fresh_scope_authority(
    unit_database_env: str,
) -> None:
    project_id, actor_id = await _seed()
    request = _request(project_id, actor_id)
    first = await _create(request, AllowAuthorization(actor_id))
    replay_authorization = AllowAuthorization(actor_id)

    replayed = await _create(request, replay_authorization)

    assert replayed == first
    assert len(replay_authorization.scopes) == 1 and replay_authorization.prepared == []
    assert await _counts() == (1, 1)


@pytest.mark.parametrize("change", ["unit_code", "actor", "project"])
@pytest.mark.asyncio
async def test_changed_replay_of_one_operation_conflicts_without_effects(
    unit_database_env: str, change: str
) -> None:
    project_id, actor_id = await _seed()
    other_project, other_actor = await _seed()
    request = _request(project_id, actor_id)
    await _create(request, AllowAuthorization(actor_id))
    changed = {
        "unit_code": replace(request, unit_code="OTHER"),
        "actor": replace(request, actor_profile_id=other_actor),
        "project": replace(request, project_id=other_project),
    }[change]

    with pytest.raises(ContributionPolicyConflict, match="compensation_unit_conflict"):
        await _create(changed, AllowAuthorization(changed.actor_profile_id))
    assert await _counts() == (1, 1)


@pytest.mark.asyncio
async def test_existing_unit_under_new_operation_conflicts_before_authority_consumption(
    unit_database_env: str,
) -> None:
    project_id, actor_id = await _seed()
    await _create(_request(project_id, actor_id), AllowAuthorization(actor_id))
    authorization = AllowAuthorization(actor_id)

    with pytest.raises(ContributionPolicyConflict, match="compensation_unit_conflict"):
        await _create(_request(project_id, actor_id), authorization)
    assert authorization.prepared == [] and await _counts() == (1, 1)


@pytest.mark.asyncio
async def test_same_code_in_another_project_is_a_distinct_unit(unit_database_env: str) -> None:
    first_project, actor_id = await _seed()
    second_project, _ = await _seed()
    await _create(_request(first_project, actor_id), AllowAuthorization(actor_id))
    await _create(_request(second_project, actor_id), AllowAuthorization(actor_id))
    assert await _counts() == (2, 2)


@pytest.mark.parametrize(
    "changes",
    [
        {"unit_code": "1FLOW"}, {"unit_code": ""}, {"unit_code": "F" * 33},
        {"unit_code": "FLOW POINTS"}, {"unit_code": 7}, {"instrument_type": "money"},
        {"instrument_type": "money", "unit_code": "USD"},
    ],
)
@pytest.mark.asyncio
async def test_invalid_unit_identity_is_rejected_before_authority(
    unit_database_env: str, changes: dict
) -> None:
    project_id, actor_id = await _seed()
    authorization = AllowAuthorization(actor_id)
    with pytest.raises(ContributionPolicyConflict, match="compensation_unit_invalid"):
        await _create(_request(project_id, actor_id, **changes), authorization)
    assert authorization.scopes == [] and await _counts() == (0, 0)


@pytest.mark.asyncio
async def test_unknown_project_is_concealed_as_not_found(unit_database_env: str) -> None:
    _, actor_id = await _seed()
    authorization = AllowAuthorization(actor_id)
    with pytest.raises(ContributionPolicyConflict, match="compensation_unit_not_found"):
        await _create(_request(new_record_id(), actor_id), authorization)
    assert authorization.prepared == [] and await _counts() == (0, 0)


class _ProjectPort:
    def __init__(self, *, result: UUID | None = None, fail: bool = False) -> None:
        self.result, self.fail = result, fail

    async def lock_contribution_policy_project(self, project_id: UUID):
        if self.fail:
            raise ProjectContributionPolicyUnavailable("project_unavailable")
        return ProjectContributionPolicyEligibilityFacts(project_id=self.result or project_id)


@pytest.mark.asyncio
async def test_project_owner_mismatch_or_absent_port_fails_closed(unit_database_env: str) -> None:
    project_id, actor_id = await _seed()
    mismatch = _ProjectPort(result=new_record_id())
    with pytest.raises(ContributionPolicyConflict, match="compensation_unit_not_found"):
        await _create(
            _request(project_id, actor_id), AllowAuthorization(actor_id),
            service_factory=lambda session: ProjectCompensationUnitService(
                session, mutation_authorization=AllowAuthorization(actor_id), projects=mismatch,
            ),
        )
    with pytest.raises(ContributionPolicyUnavailable, match="compensation_unit_unavailable"):
        await _create(
            _request(project_id, actor_id), None,
            service_factory=lambda session: ProjectCompensationUnitService(
                session, mutation_authorization=AllowAuthorization(actor_id)
            ),
        )
    assert await _counts() == (0, 0)


@pytest.mark.asyncio
async def test_deny_default_composition_creates_nothing(unit_database_env: str) -> None:
    project_id, actor_id = await _seed()
    with pytest.raises(ContributionPolicyUnavailable, match="contribution_policy_unavailable"):
        await _create(_request(project_id, actor_id), None)
    assert await _counts() == (0, 0)


@pytest.mark.asyncio
async def test_request_type_selectors_and_transaction_shape_fail_closed(
    unit_database_env: str,
) -> None:
    project_id, actor_id = await _seed()
    authorization = AllowAuthorization(actor_id)
    async with db_session.get_session_factory()() as session:
        service = project_compensation_unit_service(session, mutation_authorization=authorization)
        with pytest.raises(ContributionPolicyUnavailable):
            await service.create(_request(project_id, actor_id))  # no transaction
        async with session.begin():
            with pytest.raises(ContributionPolicyUnavailable):
                await service.create(object())  # type: ignore[arg-type]
            with pytest.raises(ContributionPolicyUnavailable):
                await service.create(_request(project_id, str(actor_id)))
            async with session.begin_nested():
                with pytest.raises(ContributionPolicyUnavailable):
                    await service.create(_request(project_id, actor_id))
    assert authorization.scopes == [] and await _counts() == (0, 0)


@pytest.mark.parametrize(
    "statement",
    [
        "update project_compensation_unit_creation_events set unit_code='OTHER'",
        "delete from project_compensation_unit_creation_events",
        "truncate project_compensation_unit_creation_events",
    ],
)
@pytest.mark.asyncio
async def test_creation_events_are_immutable(unit_database_env: str, statement: str) -> None:
    project_id, actor_id = await _seed()
    await _create(_request(project_id, actor_id), AllowAuthorization(actor_id))
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="immutable"):
            async with session.begin():
                await session.execute(text(statement))
    assert await _counts() == (1, 1)


@pytest.mark.asyncio
async def test_creation_event_must_match_its_unit_creator(unit_database_env: str) -> None:
    project_id, actor_id = await _seed()
    _, other_actor = await _seed()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="invalid project compensation-unit creation event"):
            async with session.begin():
                session.add(ProjectCompensationUnit(
                    project_id=str(project_id), instrument_type="project_points",
                    unit_code="FLOW", status="active", created_by=str(actor_id),
                ))
                await session.flush()
                session.add(ProjectCompensationUnitCreationEvent(
                    id=new_record_id(), operation_id=new_record_id(),
                    request_digest="sha256:" + "a" * 64, actor_profile_id=str(other_actor),
                    project_id=str(project_id), instrument_type="project_points", unit_code="FLOW",
                ))
                await session.flush()
    assert await _counts() == (0, 0)


class _ConsumeFailure(AllowAuthorization):
    async def consume_contribution_policy_mutation(self, prepared, facts):
        await super().consume_contribution_policy_mutation(prepared, facts)
        raise ContributionPolicyAuthorizationUnavailable("contribution_policy_unavailable")


@pytest.mark.asyncio
async def test_authority_consumption_failure_closes_handle_and_creates_nothing(
    unit_database_env: str,
) -> None:
    project_id, actor_id = await _seed()
    authorization = _ConsumeFailure(actor_id)

    with pytest.raises(ContributionPolicyAuthorizationUnavailable):
        await _create(_request(project_id, actor_id), authorization)
    assert authorization.closed == authorization.prepared_handles != []
    assert await _counts() == (0, 0)


@pytest.mark.asyncio
async def test_event_write_failure_after_unit_flush_rolls_back_the_unit(
    unit_database_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, actor_id = await _seed()
    flushed = []

    async def fail_after_unit(self, unit, event) -> None:
        self._session.add(unit)
        await self._session.flush()
        flushed.append(unit.unit_code)
        raise RuntimeError("late_event_write_failed")

    monkeypatch.setattr(ContributionPolicyRepository, "add_unit_and_creation_event", fail_after_unit)
    with pytest.raises(RuntimeError, match="late_event_write_failed"):
        await _create(_request(project_id, actor_id), AllowAuthorization(actor_id))
    assert flushed == ["FLOW"] and await _counts() == (0, 0)


@pytest.mark.asyncio
async def test_concurrent_creations_of_one_unit_commit_and_consume_exactly_once(
    unit_database_env: str,
) -> None:
    project_id, actor_id = await _seed()
    authorizations = [AllowAuthorization(actor_id) for _ in range(4)]
    outcomes = await asyncio.gather(
        *(_create(_request(project_id, actor_id), item) for item in authorizations),
        return_exceptions=True,
    )
    conflicts = [item for item in outcomes if isinstance(item, ContributionPolicyConflict)]
    assert len(conflicts) == 3 and all(str(item) == "compensation_unit_conflict" for item in conflicts)
    assert sum(len(item.consumed) for item in authorizations) == 1
    assert await _counts() == (1, 1)


@pytest.mark.asyncio
async def test_concurrent_identical_requests_create_once_and_replay(
    unit_database_env: str,
) -> None:
    project_id, actor_id = await _seed()
    request = _request(project_id, actor_id)
    authorizations = [AllowAuthorization(actor_id) for _ in range(4)]
    results = await asyncio.gather(*(_create(request, item) for item in authorizations))
    assert all(result == results[0] for result in results)
    assert sum(len(item.consumed) for item in authorizations) == 1
    assert await _counts() == (1, 1)
