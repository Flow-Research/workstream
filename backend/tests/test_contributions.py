"""Focused PostgreSQL proof for contribution-policy persistence."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import ValidationError
import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from adapter_binding_fixtures import created_binding_events
from app.core.config import get_settings
from app.db import session as db_session
from app.db.base import Base
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.contributions.models import (
    ContributionAwardDefinition,
    ContributionPolicy,
    ContributionPolicyVersion,
    ContributionRule,
    ProjectCompensationUnit,
)
from app.modules.contributions.schemas import (
    ContributionAwardDefinitionInput,
    ISO_4217_CURRENCY_CODES,
    ProjectCompensationUnitInput,
)
from project_create_fixtures import insert_historical_project


@pytest.fixture
def contribution_database_env(
    monkeypatch: pytest.MonkeyPatch,
    clean_postgres_database: str,
) -> Iterator[str]:
    """Bind contribution tests to a runner-owned isolated PostgreSQL database."""
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()


async def _seed_project() -> tuple[str, str, str, UUID, UUID]:
    project_id = str(uuid4())
    creator_id = str(uuid4())
    adapter_actor_id = str(uuid4())
    money_binding_id = uuid4()
    points_binding_id = uuid4()
    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                ActorProfile(
                    id=creator_id,
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=creator_id,
                ),
                ActorProfile(
                    id=adapter_actor_id,
                    actor_kind="service",
                    status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value,
                    created_by=creator_id,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=creator_id,
                    issuer="https://contributions.test",
                    subject=f"creator-{creator_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=creator_id,
                    last_verified_at=datetime.now(UTC),
                ),
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=adapter_actor_id,
                    issuer="https://contributions.test",
                    subject=f"adapter-{adapter_actor_id}",
                    subject_kind="service",
                    status="active",
                    linked_by=creator_id,
                ),
            ]
        )
        await insert_historical_project(
            session,
            project_id=project_id,
            name="Contribution project",
            slug=f"contribution-{project_id[:8]}",
        )
        session.add_all(
            [
                ProjectCompensationAdapterBinding(
                    id=money_binding_id,
                    project_id=project_id,
                    instrument_type="money",
                    adapter_actor_id=adapter_actor_id,
                    route_key="contribution.money",
                    status="active",
                    binding_lifecycle_version=1,
                    created_by=creator_id,
                ),
                ProjectCompensationAdapterBinding(
                    id=points_binding_id,
                    project_id=project_id,
                    instrument_type="project_points",
                    adapter_actor_id=adapter_actor_id,
                    route_key="contribution.points",
                    status="active",
                    binding_lifecycle_version=1,
                    created_by=creator_id,
                ),
            ]
        )
        # Created-event custody validates the persisted binding state.
        await session.flush()
        session.add_all(
            created_binding_events(
                project_id, creator_id, money_binding_id, points_binding_id
            )
        )
        session.add_all(
            [
                ProjectCompensationUnit(
                    project_id=project_id,
                    instrument_type="money",
                    unit_code="USD",
                    iso_currency_code="USD",
                    status="active",
                    created_by=creator_id,
                ),
                ProjectCompensationUnit(
                    project_id=project_id,
                    instrument_type="project_points",
                    unit_code="merit.points",
                    status="active",
                    created_by=creator_id,
                ),
            ]
        )
        await session.commit()
    return project_id, creator_id, adapter_actor_id, money_binding_id, points_binding_id


async def _draft_policy(
    project_id: str,
    creator_id: str,
    *,
    policy_id: UUID | None = None,
) -> tuple[UUID, UUID]:
    policy_id = policy_id or uuid4()
    version_id = uuid4()
    async with db_session.get_session_factory()() as session:
        session.add(
            ContributionPolicy(
                id=policy_id,
                project_id=project_id,
                name=f"Policy {policy_id}",
                status="draft",
                created_by=creator_id,
            )
        )
        await session.flush()
        session.add(
            ContributionPolicyVersion(
                id=version_id,
                contribution_policy_id=policy_id,
                project_id=project_id,
                version_number=1,
                status="draft",
                created_by=creator_id,
            )
        )
        await session.commit()
    return policy_id, version_id


async def _add_rule(
    version_id: UUID,
    project_id: str,
    contribution_type: str,
    compensation_mode: str,
    *,
    binding_id: UUID | None = None,
) -> UUID:
    rule_id = uuid4()
    async with db_session.get_session_factory()() as session:
        session.add(
            ContributionRule(
                id=rule_id,
                contribution_policy_version_id=version_id,
                project_id=project_id,
                contribution_type=contribution_type,
                compensation_mode=compensation_mode,
            )
        )
        if binding_id is not None:
            session.add(
                ContributionAwardDefinition(
                    id=uuid4(),
                    contribution_rule_id=rule_id,
                    contribution_policy_version_id=version_id,
                    project_id=project_id,
                    contribution_type=contribution_type,
                    instrument_type="money",
                    unit_code="USD",
                    quantity="25.500000000000000000",
                    adapter_binding_id=binding_id,
                )
            )
        await session.commit()
    return rule_id


async def _publish_version(version_id: UUID, creator_id: str) -> None:
    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(ContributionPolicyVersion)
            .where(ContributionPolicyVersion.id == version_id)
            .values(status="published", published_by=creator_id, published_at=datetime.now(UTC))
        )
        await session.commit()


async def _complete_published_policy(
    project_id: str,
    creator_id: str,
    binding_id: UUID,
) -> tuple[UUID, UUID, UUID]:
    policy_id, version_id = await _draft_policy(project_id, creator_id)
    unpaid_rule_id = await _add_rule(
        version_id, project_id, "accepted_submission", "unpaid"
    )
    await _add_rule(
        version_id,
        project_id,
        "completed_review",
        "compensated",
        binding_id=binding_id,
    )
    await _publish_version(version_id, creator_id)
    return policy_id, version_id, unpaid_rule_id


def test_contribution_models_register_closed_canonical_tables() -> None:
    assert set(Base.metadata.tables["contribution_policies"].columns.keys()) == {
        "id",
        "project_id",
        "name",
        "status",
        "current_published_version_id",
        "created_by",
        "created_at",
        "retired_by",
        "retired_at",
    }
    assert set(Base.metadata.tables["contribution_policy_versions"].columns.keys()) == {
        "id",
        "contribution_policy_id",
        "project_id",
        "version_number",
        "status",
        "created_by",
        "created_at",
        "published_by",
        "published_at",
        "retired_by",
        "retired_at",
        "last_updated_by",
        "last_updated_at",
    }
    assert {
        "iso_4217_currency_codes",
        "project_compensation_units",
    } <= set(Base.metadata.tables)


@pytest.mark.parametrize(
    "quantity",
    (
        1,
        1.5,
        Decimal("1"),
        "",
        "+1",
        "-1",
        "0",
        "0.0",
        "01",
        ".5",
        "1.",
        "1e2",
        "NaN",
        "Infinity",
        "100000000000000000000",
        "1.0000000000000000000",
    ),
)
def test_award_definition_input_rejects_noncanonical_quantity(quantity: object) -> None:
    with pytest.raises(ValidationError):
        ContributionAwardDefinitionInput(
            id=uuid4(),
            contribution_rule_id=uuid4(),
            contribution_policy_version_id=uuid4(),
            project_id=str(uuid4()),
            contribution_type="accepted_submission",
            instrument_type="money",
            unit_code="USD",
            quantity=quantity,
            adapter_binding_id=uuid4(),
        )


@pytest.mark.parametrize(
    ("instrument", "unit"),
    (("money", "usd"), ("money", "USDX"), ("project_points", "bad unit")),
)
def test_award_definition_input_rejects_wrong_unit_shape(instrument: str, unit: str) -> None:
    with pytest.raises(ValidationError):
        ContributionAwardDefinitionInput(
            id=uuid4(),
            contribution_rule_id=uuid4(),
            contribution_policy_version_id=uuid4(),
            project_id=str(uuid4()),
            contribution_type="accepted_submission",
            instrument_type=instrument,
            unit_code=unit,
            quantity="1.25",
            adapter_binding_id=uuid4(),
        )


def test_award_definition_input_returns_exact_decimal() -> None:
    value = ContributionAwardDefinitionInput(
        id=uuid4(),
        contribution_rule_id=uuid4(),
        contribution_policy_version_id=uuid4(),
        project_id=str(uuid4()),
        contribution_type="accepted_submission",
        instrument_type="money",
        unit_code="USD",
        quantity="1.230000000000000000",
        adapter_binding_id=uuid4(),
    )
    assert value.quantity_decimal() == Decimal("1.230000000000000000")


def test_project_compensation_unit_input_rejects_unknown_currency() -> None:
    with pytest.raises(ValidationError):
        ProjectCompensationUnitInput(
            project_id=str(uuid4()),
            instrument_type="money",
            unit_code="ZZZ",
            created_by=str(uuid4()),
        )


@pytest.mark.parametrize("quantity", ("1.0", "1.5"))
def test_award_definition_input_rejects_fractional_project_points(quantity: str) -> None:
    with pytest.raises(ValidationError):
        ContributionAwardDefinitionInput(
            id=uuid4(),
            contribution_rule_id=uuid4(),
            contribution_policy_version_id=uuid4(),
            project_id=str(uuid4()),
            contribution_type="accepted_submission",
            instrument_type="project_points",
            unit_code="merit.points",
            quantity=quantity,
            adapter_binding_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_database_iso_registry_matches_schema_precheck(
    contribution_database_env: str,
) -> None:
    async with db_session.get_session_factory()() as session:
        codes = set(await session.scalars(text("select code from iso_4217_currency_codes")))
    assert codes == ISO_4217_CURRENCY_CODES


@pytest.mark.asyncio
async def test_complete_policy_graph_can_publish_and_become_active(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    policy_id, version_id, _ = await _complete_published_policy(
        project_id, creator_id, money_binding_id
    )
    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(ContributionPolicy)
            .where(ContributionPolicy.id == policy_id)
            .values(status="active", current_published_version_id=version_id)
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        policy = await session.get(ContributionPolicy, policy_id)
        assert policy is not None
        assert (policy.status, policy.current_published_version_id) == ("active", version_id)


@pytest.mark.asyncio
async def test_active_policy_cannot_select_a_draft_version(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, _, _ = await _seed_project()
    policy_id, version_id = await _draft_policy(project_id, creator_id)
    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(ContributionPolicy)
            .where(ContributionPolicy.id == policy_id)
            .values(status="active", current_published_version_id=version_id)
        )
        with pytest.raises(DBAPIError):
            await session.commit()


@pytest.mark.asyncio
async def test_incomplete_or_unpaid_definition_graph_cannot_publish(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    _, version_id = await _draft_policy(project_id, creator_id)
    await _add_rule(
        version_id,
        project_id,
        "accepted_submission",
        "unpaid",
        binding_id=money_binding_id,
    )
    with pytest.raises(DBAPIError):
        await _publish_version(version_id, creator_id)


@pytest.mark.asyncio
async def test_each_incomplete_policy_graph_shape_is_rejected(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()

    for only_type in ("accepted_submission", "completed_review"):
        _, version_id = await _draft_policy(project_id, creator_id)
        await _add_rule(version_id, project_id, only_type, "unpaid")
        with pytest.raises(DBAPIError):
            await _publish_version(version_id, creator_id)

    _, unpaid_version_id = await _draft_policy(project_id, creator_id)
    await _add_rule(
        unpaid_version_id,
        project_id,
        "accepted_submission",
        "unpaid",
        binding_id=money_binding_id,
    )
    await _add_rule(unpaid_version_id, project_id, "completed_review", "unpaid")
    with pytest.raises(DBAPIError):
        await _publish_version(unpaid_version_id, creator_id)

    _, empty_version_id = await _draft_policy(project_id, creator_id)
    await _add_rule(empty_version_id, project_id, "accepted_submission", "compensated")
    await _add_rule(empty_version_id, project_id, "completed_review", "unpaid")
    with pytest.raises(DBAPIError):
        await _publish_version(empty_version_id, creator_id)

    _, duplicate_version_id = await _draft_policy(project_id, creator_id)
    rule_id = await _add_rule(
        duplicate_version_id,
        project_id,
        "accepted_submission",
        "compensated",
        binding_id=money_binding_id,
    )
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError):
            session.add(
                ContributionAwardDefinition(
                    id=uuid4(),
                    contribution_rule_id=rule_id,
                    contribution_policy_version_id=duplicate_version_id,
                    project_id=project_id,
                    contribution_type="accepted_submission",
                    instrument_type="money",
                    unit_code="USD",
                    quantity=Decimal("1"),
                    adapter_binding_id=money_binding_id,
                )
            )
            await session.flush()

@pytest.mark.asyncio
async def test_definition_binding_must_match_project_and_instrument(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, _, points_binding_id = await _seed_project()
    _, version_id = await _draft_policy(project_id, creator_id)
    with pytest.raises(IntegrityError):
        await _add_rule(
            version_id,
            project_id,
            "accepted_submission",
            "compensated",
            binding_id=points_binding_id,
        )


@pytest.mark.asyncio
async def test_database_rejects_unconfigured_units_and_fractional_points(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, points_binding_id = await _seed_project()
    _, version_id = await _draft_policy(project_id, creator_id)
    rule_id = await _add_rule(
        version_id,
        project_id,
        "accepted_submission",
        "compensated",
        binding_id=money_binding_id,
    )
    invalid_definitions = (
        ContributionAwardDefinition(
            id=uuid4(),
            contribution_rule_id=rule_id,
            contribution_policy_version_id=version_id,
            project_id=project_id,
            contribution_type="accepted_submission",
            instrument_type="money",
            unit_code="EUR",
            quantity=Decimal("1"),
            adapter_binding_id=money_binding_id,
        ),
        ContributionAwardDefinition(
            id=uuid4(),
            contribution_rule_id=rule_id,
            contribution_policy_version_id=version_id,
            project_id=project_id,
            contribution_type="accepted_submission",
            instrument_type="project_points",
            unit_code="merit.points",
            quantity=Decimal("1.5"),
            adapter_binding_id=points_binding_id,
        ),
    )
    for definition in invalid_definitions:
        async with db_session.get_session_factory()() as session:
            with pytest.raises(IntegrityError):
                session.add(definition)
                await session.flush()


@pytest.mark.asyncio
async def test_database_rejects_unknown_iso_code_and_overprecision(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError):
            session.add(
                ProjectCompensationUnit(
                    project_id=project_id,
                    instrument_type="money",
                    unit_code="ZZZ",
                    iso_currency_code="ZZZ",
                    status="active",
                    created_by=creator_id,
                )
            )
            await session.flush()

    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError):
            session.add(
                ProjectCompensationUnit(
                    project_id=project_id,
                    instrument_type="money",
                    unit_code="ZZZ",
                    iso_currency_code=None,
                    status="active",
                    created_by=creator_id,
                )
            )
            await session.flush()

    _, version_id = await _draft_policy(project_id, creator_id)
    rule_id = await _add_rule(version_id, project_id, "accepted_submission", "compensated")
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError):
            session.add(
                ContributionAwardDefinition(
                    id=uuid4(),
                    contribution_rule_id=rule_id,
                    contribution_policy_version_id=version_id,
                    project_id=project_id,
                    contribution_type="accepted_submission",
                    instrument_type="money",
                    unit_code="USD",
                    quantity=Decimal("1.0000000000000000001"),
                    adapter_binding_id=money_binding_id,
                )
            )
            await session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quantity",
    (
        Decimal("0"),
        Decimal("-1"),
        Decimal("100000000000000000000"),
        Decimal("1.0000000000000000001"),
    ),
)
async def test_database_rejects_each_invalid_quantity_edge(
    contribution_database_env: str,
    quantity: Decimal,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    _, version_id = await _draft_policy(project_id, creator_id)
    rule_id = await _add_rule(version_id, project_id, "accepted_submission", "compensated")
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError):
            session.add(
                ContributionAwardDefinition(
                    id=uuid4(),
                    contribution_rule_id=rule_id,
                    contribution_policy_version_id=version_id,
                    project_id=project_id,
                    contribution_type="accepted_submission",
                    instrument_type="money",
                    unit_code="USD",
                    quantity=quantity,
                    adapter_binding_id=money_binding_id,
                )
            )
            await session.flush()


@pytest.mark.asyncio
async def test_database_accepts_exact_maximum_quantity_edge(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    _, version_id = await _draft_policy(project_id, creator_id)
    rule_id = await _add_rule(version_id, project_id, "accepted_submission", "compensated")
    maximum = Decimal("99999999999999999999.999999999999999999")
    async with db_session.get_session_factory()() as session:
        definition = ContributionAwardDefinition(
            id=uuid4(),
            contribution_rule_id=rule_id,
            contribution_policy_version_id=version_id,
            project_id=project_id,
            contribution_type="accepted_submission",
            instrument_type="money",
            unit_code="USD",
            quantity=maximum,
            adapter_binding_id=money_binding_id,
        )
        session.add(definition)
        await session.flush()
        assert definition.quantity == maximum


@pytest.mark.asyncio
async def test_published_rules_definitions_and_version_identity_are_immutable(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    _, version_id, unpaid_rule_id = await _complete_published_policy(
        project_id, creator_id, money_binding_id
    )
    statements = (
        update(ContributionRule)
        .where(ContributionRule.id == unpaid_rule_id)
        .values(compensation_mode="compensated"),
        delete(ContributionRule).where(ContributionRule.id == unpaid_rule_id),
        update(ContributionAwardDefinition)
        .where(ContributionAwardDefinition.contribution_policy_version_id == version_id)
        .values(quantity="99.000000000000000000"),
        delete(ContributionAwardDefinition).where(
            ContributionAwardDefinition.contribution_policy_version_id == version_id
        ),
        update(ContributionPolicyVersion)
        .where(ContributionPolicyVersion.id == version_id)
        .values(version_number=2),
    )
    for statement in statements:
        async with db_session.get_session_factory()() as session:
            with pytest.raises(DBAPIError):
                await session.execute(statement)


@pytest.mark.asyncio
async def test_retired_policy_version_and_children_are_immutable(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    _, version_id, unpaid_rule_id = await _complete_published_policy(
        project_id, creator_id, money_binding_id
    )
    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(ContributionPolicyVersion)
            .where(ContributionPolicyVersion.id == version_id)
            .values(
                status="retired",
                retired_by=creator_id,
                retired_at=datetime.now(UTC),
            )
        )
        await session.commit()

    statements = (
        update(ContributionPolicyVersion)
        .where(ContributionPolicyVersion.id == version_id)
        .values(version_number=2),
        delete(ContributionPolicyVersion).where(ContributionPolicyVersion.id == version_id),
        update(ContributionRule)
        .where(ContributionRule.id == unpaid_rule_id)
        .values(compensation_mode="compensated"),
        delete(ContributionRule).where(ContributionRule.id == unpaid_rule_id),
        update(ContributionAwardDefinition)
        .where(ContributionAwardDefinition.contribution_policy_version_id == version_id)
        .values(quantity=Decimal("99")),
        delete(ContributionAwardDefinition).where(
            ContributionAwardDefinition.contribution_policy_version_id == version_id
        ),
    )
    for statement in statements:
        async with db_session.get_session_factory()() as session:
            with pytest.raises(DBAPIError):
                await session.execute(statement)


@pytest.mark.asyncio
async def test_policy_and_unit_tables_reject_truncate(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    await _complete_published_policy(project_id, creator_id, money_binding_id)
    for table_name in (
        "contribution_award_definitions",
        "contribution_rules",
        "contribution_policy_versions",
        "contribution_policies",
        "project_compensation_units",
        "iso_4217_currency_codes",
    ):
        async with db_session.get_session_factory()() as session:
            with pytest.raises(DBAPIError):
                await session.execute(text(f"truncate table {table_name} cascade"))


@pytest.mark.asyncio
async def test_published_definition_cannot_be_reparented_to_draft_version(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, points_binding_id = await _seed_project()
    _, published_version_id = await _draft_policy(project_id, creator_id)
    compensated_rule_id = await _add_rule(
        published_version_id,
        project_id,
        "accepted_submission",
        "compensated",
        binding_id=money_binding_id,
    )
    async with db_session.get_session_factory()() as session:
        session.add(
            ContributionAwardDefinition(
                id=uuid4(),
                contribution_rule_id=compensated_rule_id,
                contribution_policy_version_id=published_version_id,
                project_id=project_id,
                contribution_type="accepted_submission",
                instrument_type="project_points",
                unit_code="merit.points",
                quantity=Decimal("10"),
                adapter_binding_id=points_binding_id,
            )
        )
        await session.commit()
    await _add_rule(published_version_id, project_id, "completed_review", "unpaid")
    await _publish_version(published_version_id, creator_id)

    _, draft_version_id = await _draft_policy(project_id, creator_id)
    draft_rule_id = await _add_rule(
        draft_version_id, project_id, "accepted_submission", "compensated"
    )
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(ContributionAwardDefinition)
                .where(
                    ContributionAwardDefinition.contribution_policy_version_id
                    == published_version_id,
                    ContributionAwardDefinition.instrument_type == "project_points",
                )
                .values(
                    contribution_rule_id=draft_rule_id,
                    contribution_policy_version_id=draft_version_id,
                )
            )


@pytest.mark.asyncio
async def test_active_policy_race_has_one_winner(contribution_database_env: str) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    first_policy, first_version, _ = await _complete_published_policy(
        project_id, creator_id, money_binding_id
    )
    second_policy, second_version, _ = await _complete_published_policy(
        project_id, creator_id, money_binding_id
    )

    async def activate(policy_id: UUID, version_id: UUID) -> str:
        async with db_session.get_session_factory()() as session:
            try:
                await session.execute(
                    update(ContributionPolicy)
                    .where(ContributionPolicy.id == policy_id)
                    .values(status="active", current_published_version_id=version_id)
                )
                await session.commit()
                return "active"
            except (DBAPIError, IntegrityError):
                await session.rollback()
                return "conflict"

    assert sorted(
        await asyncio.gather(
            activate(first_policy, first_version),
            activate(second_policy, second_version),
        )
    ) == ["active", "conflict"]


@pytest.mark.asyncio
async def test_publishability_race_cannot_use_uncommitted_rule(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, _, _ = await _seed_project()
    _, version_id = await _draft_policy(project_id, creator_id)
    await _add_rule(version_id, project_id, "accepted_submission", "unpaid")
    rule_staged = asyncio.Event()
    allow_rule_commit = asyncio.Event()

    async def add_missing_rule() -> str:
        async with db_session.get_session_factory()() as session:
            session.add(
                ContributionRule(
                    id=uuid4(),
                    contribution_policy_version_id=version_id,
                    project_id=project_id,
                    contribution_type="completed_review",
                    compensation_mode="unpaid",
                )
            )
            await session.flush()
            rule_staged.set()
            await allow_rule_commit.wait()
            await session.commit()
            return "rule_committed"

    async def publish_without_visible_rule() -> str:
        await rule_staged.wait()
        try:
            async with db_session.get_session_factory()() as session:
                await session.execute(text("set local lock_timeout='500ms'"))
                await session.execute(
                    update(ContributionPolicyVersion)
                    .where(ContributionPolicyVersion.id == version_id)
                    .values(
                        status="published",
                        published_by=creator_id,
                        published_at=datetime.now(UTC),
                    )
                )
                await session.commit()
                return "published"
        except DBAPIError:
            return "rejected"
        finally:
            allow_rule_commit.set()

    assert sorted(await asyncio.gather(add_missing_rule(), publish_without_visible_rule())) == [
        "rejected",
        "rule_committed",
    ]


@pytest.mark.asyncio
async def test_publish_lock_rejects_concurrent_draft_child_mutation(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, points_binding_id = await _seed_project()
    _, version_id = await _draft_policy(project_id, creator_id)
    compensated_rule_id = await _add_rule(
        version_id,
        project_id,
        "accepted_submission",
        "compensated",
        binding_id=money_binding_id,
    )
    await _add_rule(version_id, project_id, "completed_review", "unpaid")
    publish_locked = asyncio.Event()
    child_attempted = asyncio.Event()

    async def publish() -> str:
        async with db_session.get_session_factory()() as session:
            await session.execute(
                update(ContributionPolicyVersion)
                .where(ContributionPolicyVersion.id == version_id)
                .values(
                    status="published",
                    published_by=creator_id,
                    published_at=datetime.now(UTC),
                )
            )
            publish_locked.set()
            await child_attempted.wait()
            await session.commit()
            return "published"

    async def mutate_child() -> str:
        await publish_locked.wait()
        async with db_session.get_session_factory()() as session:
            try:
                await session.execute(text("set local lock_timeout='500ms'"))
                session.add(
                    ContributionAwardDefinition(
                        id=uuid4(),
                        contribution_rule_id=compensated_rule_id,
                        contribution_policy_version_id=version_id,
                        project_id=project_id,
                        contribution_type="accepted_submission",
                        instrument_type="project_points",
                        unit_code="merit.points",
                        quantity=Decimal("5"),
                        adapter_binding_id=points_binding_id,
                    )
                )
                await session.flush()
                return "mutated"
            except DBAPIError:
                return "rejected"
            finally:
                child_attempted.set()

    assert sorted(await asyncio.gather(publish(), mutate_child())) == [
        "published",
        "rejected",
    ]
