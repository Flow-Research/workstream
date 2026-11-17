"""Focused PostgreSQL proof for contribution-policy persistence."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID
from app.core.identifiers import new_record_id

from pydantic import ValidationError
import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.adapter_binding_fixtures import created_binding_events
from app.core.config import get_settings
from app.adapters.compensation import policy_adapter_binding_port
from app.adapters.projects import project_contribution_policy_eligibility_port
from app.db import session as db_session
from app.db.base import Base
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.api import ServiceIdentity
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.contributions.models import (
    ContributionAwardDefinition,
    ContributionPolicy,
    ContributionPolicyVersion,
    ContributionRule,
)
from app.modules.contributions.units.models import (
    ProjectCompensationUnit,
)
from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyPublishRequest,
    ContributionPolicyRetireRequest,
)
from app.modules.contributions.service import ContributionPolicyService
from app.modules.contributions.schemas import (
    ContributionAwardDefinitionInput,
    ISO_4217_CURRENCY_CODES,
    ProjectCompensationUnitInput,
)
from tests.project_create_fixtures import insert_historical_project
from tests.contributions.policy_test_support import AllowAuthorization


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
    project_id = str(new_record_id())
    creator_id = str(new_record_id())
    adapter_actor_id = str(new_record_id())
    money_binding_id = new_record_id()
    points_binding_id = new_record_id()
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
                    id=str(new_record_id()),
                    actor_profile_id=creator_id,
                    issuer="https://contributions.test",
                    subject=f"creator-{creator_id}",
                    subject_kind="human",
                    status="active",
                    linked_by=creator_id,
                    last_verified_at=datetime.now(UTC),
                ),
                ActorIdentityLink(
                    id=str(new_record_id()),
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
    financial_header: tuple[str, str, UUID] | None = None,
) -> tuple[UUID, UUID]:
    policy_id = policy_id or new_record_id()
    version_id = new_record_id()
    instrument, unit, binding = financial_header if financial_header is not None else (None, None, None)
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
                instrument_type=instrument,
                unit_code=unit,
                adapter_binding_id=binding,
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
    with_awards: bool = False,
) -> UUID:
    """Seed a rule; optional current awards copy only its declared common header."""
    rule_id = new_record_id()
    async with db_session.get_session_factory()() as session:
        session.add(ContributionRule(
            id=rule_id, contribution_policy_version_id=version_id,
            project_id=project_id, contribution_type=contribution_type,
            compensation_mode=compensation_mode,
        ))
        if with_awards:
            version = await session.get(ContributionPolicyVersion, version_id)
            assert version.project_id == project_id
            assert all(value is not None for value in (
                version.instrument_type, version.unit_code, version.adapter_binding_id,
            ))
            sizes = ("small", "medium", "large") if contribution_type == "accepted_submission" else (None,)
            base = Decimal("25.5") if version.instrument_type == "money" else Decimal("25")
            for index, size in enumerate(sizes, start=1):
                session.add(ContributionAwardDefinition(
                    id=new_record_id(), contribution_rule_id=rule_id,
                    contribution_policy_version_id=version_id, project_id=project_id,
                    contribution_type=contribution_type, task_size=size,
                    instrument_type=version.instrument_type, unit_code=version.unit_code,
                    quantity=base * index, adapter_binding_id=version.adapter_binding_id,
                ))
        await session.commit()
    return rule_id


async def _graph_snapshot(version_id: UUID) -> dict[str, tuple[str, ...]]:
    async with db_session.get_session_factory()() as session:
        return {table: tuple((await session.execute(text(
            f"SELECT to_jsonb(r)::text FROM public.{table} r "
            "WHERE contribution_policy_version_id=:id ORDER BY id"
        ), {"id": version_id})).scalars()) for table in (
            "contribution_rules", "contribution_award_definitions",
        )}


async def _publish_version(
    version_id: UUID,
    creator_id: str,
    *,
    lock_timeout: str | None = None,
) -> None:
    async with db_session.get_session_factory()() as session, session.begin():
        if lock_timeout is not None:
            await session.execute(text("set local lock_timeout=:timeout"), {"timeout": lock_timeout})
        version = await session.get(ContributionPolicyVersion, version_id)
        assert version is not None
        actor_id = UUID(creator_id)
        authorization = AllowAuthorization(actor_id)
        service = ContributionPolicyService(
            session,
            read_authorization=authorization,
            mutation_authorization=authorization,
            projects=project_contribution_policy_eligibility_port(session),
            bindings=policy_adapter_binding_port(session),
        )
        await service.publish(
            ContributionPolicyPublishRequest(
                operation_id=new_record_id(),
                actor_profile_id=actor_id,
                project_id=UUID(version.project_id),
                contribution_policy_id=version.contribution_policy_id,
                contribution_policy_version_id=version.id,
            )
        )


async def _retire_version(version_id: UUID, creator_id: str) -> None:
    async with db_session.get_session_factory()() as session, session.begin():
        version = await session.get(ContributionPolicyVersion, version_id)
        assert version is not None
        actor_id = UUID(creator_id)
        authorization = AllowAuthorization(actor_id)
        service = ContributionPolicyService(
            session,
            read_authorization=authorization,
            mutation_authorization=authorization,
            projects=project_contribution_policy_eligibility_port(session),
            bindings=policy_adapter_binding_port(session),
        )
        await service.retire(
            ContributionPolicyRetireRequest(
                operation_id=new_record_id(),
                actor_profile_id=actor_id,
                project_id=UUID(version.project_id),
                contribution_policy_id=version.contribution_policy_id,
                contribution_policy_version_id=version.id,
            )
        )


async def _complete_published_policy(
    project_id: str,
    creator_id: str,
    binding_id: UUID,
) -> tuple[UUID, UUID, UUID]:
    policy_id, version_id = await _draft_policy(project_id, creator_id, financial_header=("money", "USD", binding_id))
    unpaid_rule_id = await _add_rule(
        version_id, project_id, "accepted_submission", "unpaid"
    )
    await _add_rule(
        version_id,
        project_id,
        "completed_review",
        "compensated",
        with_awards=True,
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
        "last_transition_operation_id",
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
        "instrument_type",
        "unit_code",
        "adapter_binding_id",
        "created_by",
        "created_at",
        "published_by",
        "published_at",
        "retired_by",
        "retired_at",
        "last_updated_by",
        "last_updated_at",
        "last_transition_operation_id",
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
            id=new_record_id(),
            contribution_rule_id=new_record_id(),
            contribution_policy_version_id=new_record_id(),
            project_id=str(new_record_id()),
            contribution_type="accepted_submission",
            instrument_type="money",
            unit_code="USD",
            quantity=quantity,
            adapter_binding_id=new_record_id(),
        )


@pytest.mark.parametrize(
    ("instrument", "unit"),
    (("money", "usd"), ("money", "USDX"), ("project_points", "bad unit")),
)
def test_award_definition_input_rejects_wrong_unit_shape(instrument: str, unit: str) -> None:
    with pytest.raises(ValidationError):
        ContributionAwardDefinitionInput(
            id=new_record_id(),
            contribution_rule_id=new_record_id(),
            contribution_policy_version_id=new_record_id(),
            project_id=str(new_record_id()),
            contribution_type="accepted_submission",
            instrument_type=instrument,
            unit_code=unit,
            quantity="1.25",
            adapter_binding_id=new_record_id(),
        )


def test_award_definition_input_returns_exact_decimal() -> None:
    value = ContributionAwardDefinitionInput(
        id=new_record_id(),
        contribution_rule_id=new_record_id(),
        contribution_policy_version_id=new_record_id(),
        project_id=str(new_record_id()),
        contribution_type="accepted_submission",
        instrument_type="money",
        unit_code="USD",
        quantity="1.230000000000000000",
        adapter_binding_id=new_record_id(),
    )
    assert value.quantity_decimal() == Decimal("1.230000000000000000")


def test_project_compensation_unit_input_rejects_unknown_currency() -> None:
    with pytest.raises(ValidationError):
        ProjectCompensationUnitInput(
            project_id=str(new_record_id()),
            instrument_type="money",
            unit_code="ZZZ",
            created_by=str(new_record_id()),
        )


@pytest.mark.parametrize("quantity", ("1.0", "1.5"))
def test_award_definition_input_rejects_fractional_project_points(quantity: str) -> None:
    with pytest.raises(ValidationError):
        ContributionAwardDefinitionInput(
            id=new_record_id(),
            contribution_rule_id=new_record_id(),
            contribution_policy_version_id=new_record_id(),
            project_id=str(new_record_id()),
            contribution_type="accepted_submission",
            instrument_type="project_points",
            unit_code="merit.points",
            quantity=quantity,
            adapter_binding_id=new_record_id(),
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
        with pytest.raises(DBAPIError):
            await session.execute(
                update(ContributionPolicy)
                .where(ContributionPolicy.id == policy_id)
                .values(status="active", current_published_version_id=version_id)
            )
            await session.commit()


@pytest.mark.asyncio
async def test_incomplete_or_unpaid_definition_graph_cannot_publish(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    _, version_id = await _draft_policy(project_id, creator_id, financial_header=("money", "USD", money_binding_id))
    await _add_rule(
        version_id,
        project_id,
        "accepted_submission",
        "unpaid",
        with_awards=True,
    )
    with pytest.raises(ContributionPolicyConflict, match="contribution_policy_conflict"):
        await _publish_version(version_id, creator_id)


@pytest.mark.asyncio
async def test_each_incomplete_policy_graph_shape_is_rejected(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()

    for only_type in ("accepted_submission", "completed_review"):
        _, version_id = await _draft_policy(project_id, creator_id)
        await _add_rule(version_id, project_id, only_type, "unpaid")
        with pytest.raises(ContributionPolicyConflict, match="contribution_policy_conflict"):
            await _publish_version(version_id, creator_id)

    _, unpaid_version_id = await _draft_policy(project_id, creator_id, financial_header=("money", "USD", money_binding_id))
    await _add_rule(
        unpaid_version_id,
        project_id,
        "accepted_submission",
        "unpaid",
        with_awards=True,
    )
    await _add_rule(unpaid_version_id, project_id, "completed_review", "compensated", with_awards=True)
    with pytest.raises(ContributionPolicyConflict, match="contribution_policy_conflict"):
        await _publish_version(unpaid_version_id, creator_id)

    _, empty_version_id = await _draft_policy(project_id, creator_id, financial_header=("money", "USD", money_binding_id))
    await _add_rule(empty_version_id, project_id, "accepted_submission", "compensated")
    await _add_rule(empty_version_id, project_id, "completed_review", "unpaid")
    with pytest.raises(ContributionPolicyConflict, match="contribution_policy_conflict"):
        await _publish_version(empty_version_id, creator_id)

    _, duplicate_version_id = await _draft_policy(project_id, creator_id, financial_header=("money", "USD", money_binding_id))
    rule_id = await _add_rule(
        duplicate_version_id,
        project_id,
        "accepted_submission",
        "compensated",
        with_awards=True,
    )
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="uq_award_definition_size"):
            session.add(
                ContributionAwardDefinition(
                    id=new_record_id(),
                    contribution_rule_id=rule_id,
                    contribution_policy_version_id=duplicate_version_id,
                    project_id=project_id,
                    contribution_type="accepted_submission",
                    task_size="small",
                    instrument_type="money",
                    unit_code="USD",
                    quantity=Decimal("1"),
                    adapter_binding_id=money_binding_id,
                )
            )
            await session.flush()


@pytest.mark.asyncio
async def test_definition_binding_must_match_project_and_instrument(contribution_database_env: str) -> None:
    project, creator, _, money, points = await _seed_project()
    _, version = await _draft_policy(project, creator, financial_header=("money", "USD", money))
    rule = await _add_rule(version, project, "accepted_submission", "compensated")
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="fk_contribution_award_definition_binding") as caught:
            session.add(ContributionAwardDefinition(
                id=new_record_id(), contribution_rule_id=rule,
                contribution_policy_version_id=version, project_id=project,
                contribution_type="accepted_submission", task_size="small",
                instrument_type="money", unit_code="USD", quantity=Decimal("1"),
                adapter_binding_id=points,
            ))
            await session.flush()
        assert caught.value.orig.sqlstate == "23503"


@pytest.mark.asyncio
async def test_database_rejects_unconfigured_units_and_fractional_points(contribution_database_env: str) -> None:
    project, creator, _, money, points = await _seed_project()
    for instrument, unit, quantity, binding, constraint, state in (
        ("money", "EUR", Decimal("1"), money, "fk_contribution_award_definition_unit", "23503"),
        ("project_points", "merit.points", Decimal("1.5"), points,
         "ck_contribution_award_definitions_project_points_whole", "23514"),
    ):
        declared_unit = "USD" if instrument == "money" else "merit.points"
        _, version = await _draft_policy(project, creator, financial_header=(instrument, declared_unit, binding))
        rule = await _add_rule(version, project, "accepted_submission", "compensated")
        async with db_session.get_session_factory()() as session:
            with pytest.raises(IntegrityError, match=constraint) as caught:
                session.add(ContributionAwardDefinition(
                    id=new_record_id(), contribution_rule_id=rule,
                    contribution_policy_version_id=version, project_id=project,
                    contribution_type="accepted_submission", task_size="small",
                    instrument_type=instrument, unit_code=unit, quantity=quantity,
                    adapter_binding_id=binding,
                ))
                await session.flush()
            assert caught.value.orig.sqlstate == state


@pytest.mark.asyncio
async def test_database_rejects_unknown_iso_code_and_overprecision(
    contribution_database_env: str,
) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="fk_project_compensation_unit_iso_currency"):
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
        with pytest.raises(IntegrityError, match="ck_project_compensation_units_unit_identity"):
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

    _, version_id = await _draft_policy(project_id, creator_id, financial_header=("money", "USD", money_binding_id))
    rule_id = await _add_rule(version_id, project_id, "accepted_submission", "compensated")
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="ck_contribution_award_definitions_quantity_exact_bounds"):
            session.add(
                ContributionAwardDefinition(
                    id=new_record_id(),
                    contribution_rule_id=rule_id,
                    contribution_policy_version_id=version_id,
                    project_id=project_id,
                    contribution_type="accepted_submission",
                    task_size="small",
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
    _, version_id = await _draft_policy(project_id, creator_id, financial_header=("money", "USD", money_binding_id))
    rule_id = await _add_rule(version_id, project_id, "accepted_submission", "compensated")
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="ck_contribution_award_definitions_quantity_exact_bounds"):
            session.add(
                ContributionAwardDefinition(
                    id=new_record_id(),
                    contribution_rule_id=rule_id,
                    contribution_policy_version_id=version_id,
                    project_id=project_id,
                    contribution_type="accepted_submission",
                    task_size="small",
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
    _, version_id = await _draft_policy(project_id, creator_id, financial_header=("money", "USD", money_binding_id))
    rule_id = await _add_rule(version_id, project_id, "accepted_submission", "compensated")
    maximum = Decimal("99999999999999999999.999999999999999999")
    async with db_session.get_session_factory()() as session:
        definition = ContributionAwardDefinition(
            id=new_record_id(),
            contribution_rule_id=rule_id,
            contribution_policy_version_id=version_id,
            project_id=project_id,
            contribution_type="accepted_submission",
            task_size="small",
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
    await _retire_version(version_id, creator_id)

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
async def test_published_definition_cannot_be_reparented_to_draft_version(contribution_database_env: str) -> None:
    project, creator, _, money, _ = await _seed_project()
    _, published = await _draft_policy(project, creator, financial_header=("money", "USD", money))
    await _add_rule(published, project, "accepted_submission", "compensated", with_awards=True)
    await _add_rule(published, project, "completed_review", "unpaid")
    await _publish_version(published, creator)
    _, draft = await _draft_policy(project, creator, financial_header=("money", "USD", money))
    draft_rule = await _add_rule(draft, project, "accepted_submission", "compensated")
    before = (await _graph_snapshot(published), await _graph_snapshot(draft))
    async with db_session.get_session_factory()() as session:
        with pytest.raises(DBAPIError, match="published contribution policy rules and definitions are immutable") as caught:
            await session.execute(update(ContributionAwardDefinition).where(
                ContributionAwardDefinition.contribution_policy_version_id == published,
                ContributionAwardDefinition.task_size == "small",
            ).values(contribution_rule_id=draft_rule, contribution_policy_version_id=draft))
        assert caught.value.orig.sqlstate == "55000"
    assert (await _graph_snapshot(published), await _graph_snapshot(draft)) == before


@pytest.mark.asyncio
async def test_active_policy_race_has_one_winner(contribution_database_env: str) -> None:
    project_id, creator_id, _, money_binding_id, _ = await _seed_project()
    versions: list[UUID] = []
    for _ in range(2):
        _, version_id = await _draft_policy(project_id, creator_id, financial_header=("money", "USD", money_binding_id))
        await _add_rule(
            version_id,
            project_id,
            "accepted_submission",
            "compensated",
            with_awards=True,
        )
        await _add_rule(version_id, project_id, "completed_review", "unpaid")
        versions.append(version_id)

    async def activate(version_id: UUID) -> str:
        try:
            await _publish_version(version_id, creator_id)
            return "active"
        except (ContributionPolicyConflict, DBAPIError):
            return "conflict"

    assert sorted(
        await asyncio.gather(
            activate(versions[0]),
            activate(versions[1]),
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
                    id=new_record_id(),
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
            await _publish_version(version_id, creator_id, lock_timeout="500ms")
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
async def test_publish_lock_rejects_concurrent_draft_child_mutation(contribution_database_env: str) -> None:
    project, creator, _, money, _ = await _seed_project()
    _, version = await _draft_policy(project, creator, financial_header=("money", "USD", money))
    rule = await _add_rule(version, project, "accepted_submission", "compensated", with_awards=True)
    await _add_rule(version, project, "completed_review", "unpaid")
    before = await _graph_snapshot(version)
    mutation = update(ContributionAwardDefinition).where(
        ContributionAwardDefinition.contribution_rule_id == rule,
        ContributionAwardDefinition.task_size == "small",
    ).values(quantity=Decimal("26.5"))
    async with db_session.get_session_factory()() as session:
        changed = await session.execute(mutation)
        assert changed.rowcount == 1
        await session.rollback()
    assert await _graph_snapshot(version) == before
    publish_locked, child_attempted = asyncio.Event(), asyncio.Event()

    async def publish() -> str:
        class PausingAuthorization(AllowAuthorization):
            async def consume_contribution_policy_mutation(self, prepared, facts):
                publish_locked.set()
                await child_attempted.wait()
                return await super().consume_contribution_policy_mutation(prepared, facts)

        async with db_session.get_session_factory()() as session, session.begin():
            authorization = PausingAuthorization(UUID(creator))
            service = ContributionPolicyService(
                session, read_authorization=authorization, mutation_authorization=authorization,
                projects=project_contribution_policy_eligibility_port(session),
                bindings=policy_adapter_binding_port(session),
            )
            row = await session.get(ContributionPolicyVersion, version)
            await service.publish(ContributionPolicyPublishRequest(
                operation_id=new_record_id(), actor_profile_id=UUID(creator),
                project_id=UUID(project), contribution_policy_id=row.contribution_policy_id,
                contribution_policy_version_id=version,
            ))
            return "published"

    async def mutate_child() -> str:
        await publish_locked.wait()
        async with db_session.get_session_factory()() as session:
            try:
                await session.execute(text("set local lock_timeout='500ms'"))
                await session.execute(mutation)
                raise AssertionError("publication did not retain its child fence")
            except DBAPIError as caught:
                assert caught.orig.sqlstate == "55P03"
                return "rejected"
            finally:
                await session.rollback()
                child_attempted.set()

    assert sorted(await asyncio.gather(publish(), mutate_child())) == ["published", "rejected"]
    assert await _graph_snapshot(version) == before
