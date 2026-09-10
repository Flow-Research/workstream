"""Exact audit vocabulary migration and direct-SQL privacy regression proof."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from .postgresql_support import world, snapshot
from tests.migration_fixtures import current_schema_revision, run_guarded_revision_downgrade, run_alembic_revision

PRIOR = "0011_review_policy_human_review"
OWN = "0012_contribution_policy_audit_resource"

CURRENT_HEAD = current_schema_revision()
TOKEN = ", ('contribution_policy'::character varying)::text"
CONSTRAINTS = (
    "ck_audit_events_authority_privacy_bounds",
    "ck_audit_events_authorization_action_evidence",
    "ck_audit_events_authority_registries",
)
ACTION_FRAGMENTS = tuple(
    " OR (((action_id)::text = 'contribution.policy."
    + operation
    + "'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text))"
    for operation in ("read", "create_draft", "update_draft", "publish", "retire")
)


async def schema_value(statement):
    """Read installed schema facts through an independent session."""
    async with db_session.get_session_factory()() as session:
        return await session.scalar(text(statement))


async def definition():
    """Read both amended checks and the untouched permission/reason registry."""
    return {
        name: await schema_value(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass and conname='" + name + "'"
        )
        for name in CONSTRAINTS
    }


async def migrate(direction, revision, migration_lock):
    """Run actual Alembic under the canonical schema-owner lock."""
    await db_session.dispose_engine()
    with migration_lock():
        await run_alembic_revision(direction, revision)


@pytest.fixture
def prior_audit_schema(auth_database_env, migration_lock, migration_schema_at):
    """Create the scenario before the async test starts, without a production downgrade."""
    with migration_lock():
        migration_schema_at(PRIOR)


@pytest.mark.asyncio
@pytest.mark.postgres_schema_contract
async def test_audit_resource_migration_roundtrip_preserves_every_other_clause(
    prior_audit_schema, migration_lock
):
    before = await definition()
    assert TOKEN not in before[CONSTRAINTS[0]]
    await migrate("upgrade", OWN, migration_lock)
    after = await definition()
    assert after[CONSTRAINTS[0]].count(TOKEN) == 1
    assert after[CONSTRAINTS[0]].replace(TOKEN, "", 1) == before[CONSTRAINTS[0]]
    actions = after[CONSTRAINTS[1]]
    for fragment in ACTION_FRAGMENTS:
        assert fragment not in before[CONSTRAINTS[1]]
        assert actions.count(fragment) == 2
        actions = actions.replace(fragment, "")
    assert actions == before[CONSTRAINTS[1]]
    assert after[CONSTRAINTS[2]] == before[CONSTRAINTS[2]]
    await migrate("downgrade", PRIOR, migration_lock)
    assert await definition() == before
    await migrate("upgrade", OWN, migration_lock)
    assert await definition() == after
    assert await schema_value("select version_num from alembic_version") == OWN


@pytest.mark.asyncio
@pytest.mark.postgres_schema_contract
@pytest.mark.parametrize("retained_shape", ("both", "action_only", "resource_only"))
async def test_audit_resource_downgrade_preserves_retained_policy_evidence(
    admin_access, migration_lock, retained_shape
):
    target = await world(admin_access)
    if retained_shape == "both":
        await target.execute("create_draft", target.request("create_draft"))
    else:
        async with db_session.get_session_factory()() as session:
            event = await session.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.event_type == "SensitiveAuthorizationAllowed",
                    AuditEvent.action_id == "admin_role_grant.issue",
                )
                .order_by(AuditEvent.id)
                .limit(1)
            )
        assert event is not None and event.resource_type != "contribution_policy"
        identity = await clone_decision(
            event,
            {
                "resource_type": "project"
                if retained_shape == "action_only"
                else "contribution_policy",
                "action_id": "contribution.policy.read"
                if retained_shape == "action_only"
                else "project.read",
                "permission_id": "compensation.policy.manage"
                if retained_shape == "action_only"
                else "project.read",
                "project_id": str(target.project),
                "resource_id": str(target.project),
                "after_facts": {"allowed": True, "resource_context_digest": "sha256:" + "a" * 64},
            },
        )
        async with db_session.get_session_factory()() as session:
            retained = await session.get(AuditEvent, identity)
            assert retained.project_id == retained.resource_id == str(target.project)
            assert (retained.resource_type == "contribution_policy") is (
                retained_shape == "resource_only"
            )
            assert retained.action_id.startswith("contribution.policy.") is (
                retained_shape == "action_only"
            )
    before, constraint = await snapshot(target.project), await definition()
    with pytest.raises(RuntimeError, match="ContributionPolicy audit history prevents downgrade"):
        with migration_lock():
            await run_guarded_revision_downgrade(db_session.get_engine().url.render_as_string(hide_password=False), OWN)
    assert await snapshot(target.project) == before
    assert await definition() == constraint
    assert await schema_value("select version_num from alembic_version") == CURRENT_HEAD


async def clone_decision(event, changes):
    """Bypass Python input validation to exercise the database's closed vocabulary."""
    identity = str(uuid4())
    payload = {"id": identity, "entity_id": identity, **changes}
    async with db_session.get_session_factory()() as session, session.begin():
        await session.execute(
            text(
                "insert into audit_events select (jsonb_populate_record(null::audit_events, to_jsonb(a) || cast(:changes as jsonb))).* from audit_events a where a.id=:id"
            ),
            {"id": event.id, "changes": json.dumps(payload)},
        )
    return identity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper,constraint",
    (
        ("resource", "ck_audit_events_authority_privacy_bounds"),
        ("private_fact", "ck_audit_events_fact_bounds"),
        ("digest", "ck_audit_events_fact_bounds"),
        ("unknown_action", "ck_audit_events_authorization_action_evidence"),
        ("wrong_permission", "ck_audit_events_authorization_action_evidence"),
        ("wrong_action", "ck_audit_events_authorization_action_evidence"),
    ),
)
async def test_policy_audit_sql_retains_resource_and_private_fact_guards(
    admin_access, tamper, constraint
):
    target = await world(admin_access)
    await target.execute("create_draft", target.request("create_draft"))
    async with db_session.get_session_factory()() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.project_id == str(target.project),
                AuditEvent.action_id == "contribution.policy.create_draft",
            )
        )
    control = await clone_decision(event, {})
    async with db_session.get_session_factory()() as session:
        assert (await session.get(AuditEvent, control)).resource_type == "contribution_policy"
    changes = {
        "resource": {"resource_type": "unregistered_policy_resource"},
        "private_fact": {
            "after_facts": {**event.after_facts, "private_material": "must-not-persist"}
        },
        "digest": {"after_facts": {**event.after_facts, "resource_context_digest": "bad"}},
        "unknown_action": {"action_id": "contribution.policy.unregistered"},
        "wrong_permission": {"permission_id": "project.read"},
        "wrong_action": {"action_id": "project.read"},
    }[tamper]
    before = await snapshot(target.project)
    with pytest.raises(DBAPIError, match=constraint):
        await clone_decision(event, changes)
    assert await snapshot(target.project) == before


@pytest.mark.parametrize(
    "shape", ("missing_anchor", "duplicate_anchor", "existing_token", "first_token")
)
def test_audit_resource_migration_rejects_ambiguous_constraint_shape(monkeypatch, shape):
    """A malformed installed expression cannot reach either constraint DDL call."""
    import importlib.util
    from unittest.mock import Mock

    path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/0012_contribution_policy_audit_resource.py"
    )
    spec = importlib.util.spec_from_file_location("cp05_audit_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expressions = {
        "missing_anchor": "CHECK (true)",
        "duplicate_anchor": module._ANCHOR + module._ANCHOR,
        "existing_token": module._ANCHOR + module._TOKEN,
        "first_token": module._RESOURCE + module._ANCHOR,
    }
    connection = Mock()
    connection.execute.return_value.scalar_one.return_value = expressions[shape]
    monkeypatch.setattr(module.op, "get_bind", lambda: connection)
    ddl = Mock()
    monkeypatch.setattr(module.op, "execute", ddl)
    with pytest.raises(RuntimeError, match="audit resource constraint shape changed"):
        module.upgrade()
    assert (
        str(connection.execute.call_args_list[0].args[0])
        == "lock table audit_events in access exclusive mode"
    )
    ddl.assert_not_called()


@pytest.mark.parametrize(
    "shape", ("valid", "missing_anchor", "extra_anchor", "partial_pair", "unexpected_pair")
)
def test_action_constraint_amendment_preserves_exact_existing_branches(shape):
    """Exercise the installed-baseline expression without running a database locally."""
    import importlib.util

    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "cp05_action_migration",
        root / "alembic/versions/0012_contribution_policy_audit_resource.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baseline = (root / "alembic/baseline/v01_schema.sql").read_text()
    original = (
        baseline.split("CONSTRAINT ck_audit_events_authorization_action_evidence ", 1)[1]
        .split("\n", 1)[0]
        .removesuffix(",")
    )
    if shape == "valid":
        amended = module._action_evidence(original, add=True)
        for fragment in ACTION_FRAGMENTS:
            assert amended.count(fragment) == 2
        assert module._action_evidence(amended, add=False) == original
        return
    malformed = {
        "missing_anchor": original.replace(module._ACTION_ANCHOR, "true", 1),
        "extra_anchor": original + module._ACTION_ANCHOR,
        "partial_pair": original + module._ACTION_PAIRS[0],
        "unexpected_pair": original + "'contribution.policy.read'",
    }[shape]
    with pytest.raises(RuntimeError, match="audit action constraint shape changed"):
        module._action_evidence(malformed, add=True)
