"""Exact policy selection and caller custody through real CON/AUTH PostgreSQL owners."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.adapters.contributions import contribution_policy_validation_port
from app.db import session as db_session
from app.modules.contributions.api import (
    ContributionPolicyUnavailable,
    ContributionPolicyValidationPurpose as Purpose,
    ContributionPolicyValidationRequest as Request,
)
from app.modules.contributions.models import ContributionAwardDefinition, ContributionRule
from .postgresql_support import world, snapshot
from .concurrency import ordered_policy_calls
from .foreign_fixtures import foreign_project


async def published_world(admin_access, *, compensated=True):
    """Publish through real Finance Authority, returning exact immutable lineage."""
    target = await world(admin_access)
    draft = await target.execute("create_draft", target.request("create_draft"))
    draft = await target.execute(
        "update_draft", target.request("update_draft", draft, compensated=compensated)
    )
    published = await target.execute("publish", target.request("publish", draft))
    request = Request(
        project_id=target.project,
        contribution_policy_id=published.contribution_policy_id,
        contribution_policy_version_id=published.contribution_policy_version_id,
        purpose=Purpose.GUIDE_ACTIVATION,
    )
    return target, published, request


async def validate(request):
    """Commit only the caller transaction after validation has returned."""
    async with db_session.get_session_factory()() as session, session.begin():
        return await contribution_policy_validation_port(session).validate_contribution_policy(
            request
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("compensated", [False, True])
async def test_selected_validation_returns_exact_graph_without_product_or_auth_writes(
    admin_access, auth_database_env, compensated
):
    target, published, request = await published_world(admin_access, compensated=compensated)
    before = await snapshot(target.project)
    result = await validate(request)
    assert result.contribution_policy_version_id == published.contribution_policy_version_id
    assert result.adapter_binding_ids == ((target.binding,) if compensated else ())
    assert await snapshot(target.project) == before


@pytest.mark.asyncio
async def test_later_publication_preserves_bound_version_but_blocks_new_stale_binding(
    admin_access, auth_database_env
):
    target, prior, request = await published_world(admin_access)
    frozen = await validate(request)
    draft = await target.execute("create_draft", target.request("create_draft"))
    draft = await target.execute("update_draft", target.request("update_draft", draft))
    current = await target.execute("publish", target.request("publish", draft))
    with pytest.raises(ContributionPolicyUnavailable):
        await validate(request)
    rebound = await validate(replace(request, purpose=Purpose.REVISION_ADOPTION))
    assert rebound == replace(frozen, purpose=Purpose.REVISION_ADOPTION)
    assert rebound.contribution_policy_version_id != current.contribution_policy_version_id
    assert frozen.contribution_policy_version_id == prior.contribution_policy_version_id
    assert (
        await validate(
            replace(request, contribution_policy_version_id=current.contribution_policy_version_id)
        )
    ).version_number == 2
    await target.execute("retire", target.request("retire", current))
    assert await validate(replace(request, purpose=Purpose.REVISION_ADOPTION)) == rebound


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["project_id", "contribution_policy_id", "contribution_policy_version_id"]
)
async def test_selection_denies_each_foreign_identifier(admin_access, auth_database_env, field):
    target, _, request = await published_world(admin_access)
    foreign_id, _ = await foreign_project(target)
    await admin_access.signed.grant(
        admin_access.admin,
        admin_access.target,
        role="finance_authority",
        project_id=foreign_id,
    )
    other = replace(target, project=foreign_id)
    draft = await other.execute("create_draft", other.request("create_draft"))
    draft = await other.execute("update_draft", other.request("update_draft", draft))
    published = await other.execute("publish", other.request("publish", draft))
    foreign = replace(
        request,
        project_id=foreign_id,
        contribution_policy_id=published.contribution_policy_id,
        contribution_policy_version_id=published.contribution_policy_version_id,
    )
    assert (await validate(foreign)).project_id == foreign_id
    before = await snapshot(target.project)
    with pytest.raises(ContributionPolicyUnavailable, match="^contribution_policy_unavailable$"):
        await validate(replace(request, **{field: getattr(foreign, field)}))
    assert await snapshot(target.project) == before
    assert (
        await validate(request)
    ).contribution_policy_version_id == request.contribution_policy_version_id


@pytest.mark.asyncio
async def test_validation_and_late_caller_effect_roll_back_together(
    admin_access, auth_database_env
):
    target, _, request = await published_world(admin_access)
    before = await snapshot(target.project)
    marker = "cp06-" + uuid4().hex
    with pytest.raises(RuntimeError, match="late_caller_failure"):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(
                text("create temporary table cp06_caller_effect (value text) on commit drop")
            )
            await session.execute(text("insert into cp06_caller_effect values (:v)"), {"v": marker})
            await contribution_policy_validation_port(session).validate_contribution_policy(request)
            assert await session.scalar(text("select value from cp06_caller_effect")) == marker
            raise RuntimeError("late_caller_failure")
    assert await snapshot(target.project) == before
    assert (
        await validate(request)
    ).contribution_policy_version_id == request.contribution_policy_version_id


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_row", ["definition", "rule"])
async def test_preloaded_graph_is_refreshed_after_draft_edit_and_publication(
    admin_access, auth_database_env, changed_row
):
    target = await world(admin_access)
    draft = await target.execute("create_draft", target.request("create_draft"))
    draft = await target.execute(
        "update_draft", target.request("update_draft", draft, compensated=True)
    )
    request = Request(
        project_id=target.project,
        contribution_policy_id=draft.contribution_policy_id,
        contribution_policy_version_id=draft.contribution_policy_version_id,
        purpose=Purpose.GUIDE_ACTIVATION,
    )
    async with db_session.get_session_factory()() as session, session.begin():
        definition = await session.scalar(
            select(ContributionAwardDefinition).where(
                ContributionAwardDefinition.contribution_policy_version_id
                == draft.contribution_policy_version_id
            )
        )
        rule = await session.scalar(
            select(ContributionRule).where(
                ContributionRule.contribution_policy_version_id
                == draft.contribution_policy_version_id,
                ContributionRule.contribution_type == "completed_review",
            )
        )
        assert definition.quantity == 2 and rule.compensation_mode == "unpaid"
        async with db_session.get_session_factory()() as concurrent, concurrent.begin():
            if changed_row == "definition":
                await concurrent.execute(
                    text("update contribution_award_definitions set quantity=3 where id=:id"),
                    {"id": definition.id},
                )
            else:
                await concurrent.execute(
                    text(
                        "update contribution_rules set compensation_mode='compensated' where id=:id"
                    ),
                    {"id": rule.id},
                )
                concurrent.add(
                    ContributionAwardDefinition(
                        id=uuid4(),
                        contribution_rule_id=rule.id,
                        contribution_policy_version_id=draft.contribution_policy_version_id,
                        project_id=str(target.project),
                        contribution_type="completed_review",
                        instrument_type="money",
                        unit_code="USD",
                        quantity=2,
                        adapter_binding_id=target.binding,
                    )
                )
                await concurrent.flush()
            await target.service(concurrent).publish(target.request("publish", draft))
        expected = await validate(request)
        assert definition.quantity == 2 and rule.compensation_mode == "unpaid"
        result = await contribution_policy_validation_port(session).validate_contribution_policy(
            request
        )
        assert result == expected
        if changed_row == "definition":
            assert definition.quantity == 3
        else:
            assert rule.compensation_mode == "compensated"


@pytest.mark.asyncio
async def test_validation_retains_unit_and_binding_locks_until_caller_rollback(
    admin_access, auth_database_env
):
    target, _, request = await published_world(admin_access)
    async with db_session.get_session_factory()() as session:
        transaction = await session.begin()
        await contribution_policy_validation_port(session).validate_contribution_policy(request)
        for sql, params in (
            (
                "select unit_code from project_compensation_units where project_id=:p and instrument_type='money' for update",
                {"p": str(target.project)},
            ),
            (
                "select id from project_compensation_adapter_bindings where id=:b for update",
                {"b": target.binding},
            ),
        ):
            async with db_session.get_session_factory()() as contender, contender.begin():
                await contender.execute(text("set local lock_timeout='100ms'"))
                with pytest.raises(DBAPIError) as exc:
                    await contender.execute(text(sql), params)
                assert exc.value.orig.sqlstate == "55P03"
        await transaction.rollback()
    assert (await validate(request)).adapter_binding_ids == (target.binding,)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["publish", "retire"])
@pytest.mark.parametrize("validation_first", [False, True])
async def test_real_authority_publication_and_retirement_serialize_with_validation(
    admin_access, auth_database_env, monkeypatch, operation, validation_first
):
    target, published, request = await published_world(admin_access)
    prior = published
    if operation == "publish":
        prior = await target.execute("create_draft", target.request("create_draft"))
        prior = await target.execute("update_draft", target.request("update_draft", prior))
    mutation = target.request(operation, prior)

    async def validate_or_deny():
        try:
            return await validate(request)
        except ContributionPolicyUnavailable:
            return "denied"

    calls = (validate_or_deny, lambda: target.execute(operation, mutation))
    if not validation_first:
        calls = calls[::-1]
    results = await ordered_policy_calls(*calls, auth_database_env, monkeypatch)
    validation_result = results[0 if validation_first else 1]
    mutation_result = results[1 if validation_first else 0]
    assert mutation_result.operation_id == mutation.operation_id
    if validation_first:
        assert (
            validation_result.contribution_policy_version_id
            == request.contribution_policy_version_id
        )
    else:
        assert validation_result == "denied"
    with pytest.raises(ContributionPolicyUnavailable):
        await validate(request)
