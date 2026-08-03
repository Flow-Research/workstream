"""register unavailable REV authorization actions and service identities

Revision ID: 0049_rev_auth_readiness
Revises: 0048_policy_authority
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0049_rev_auth_readiness"
down_revision = "0048_policy_authority"
branch_labels = depends_on = None

_ACTIONS = (
    ("review.revision_context.repair", "project.task.manage"),
    ("review.revision_obligation.close", "project.task.manage"),
    ("review.revision_context.legacy_close", "operations.reconcile.run"),
    ("review.lifecycle.activation.manage", "operations.reconcile.run"),
)
_HISTORICAL_IDENTITIES = (
    "workstream.artifact.verifier",
    "workstream.artifact.put_resolver",
    "workstream.artifact.scheduler",
    "workstream.artifact.binding",
    "workstream.artifact.guide_reader",
    "workstream.artifact.materializer",
    "workstream.artifact.checker_output",
    "workstream.project.setup",
)
_REV_IDENTITIES = (
    "workstream.review.preference_expiry",
    "workstream.review.lease_expiry",
    "workstream.review.authority_invalidation_reconciliation",
    "workstream.review.reconciliation",
    "workstream.review.artifact_reference_reconciliation",
    "workstream.review.projection",
)


def _action_definition() -> str:
    return (
        op.get_bind()
        .execute(
            sa.text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid='audit_events'::regclass "
                "and conname='ck_audit_events_authorization_action_evidence'"
            )
        )
        .scalar_one()
    )


def _replace_action_definition(definition: str) -> None:
    op.drop_constraint("authorization_action_evidence", "audit_events", type_="check")
    op.execute(
        "alter table audit_events add constraint "
        f"ck_audit_events_authorization_action_evidence {definition}"
    )


def _pair_token(action: str, permission: str) -> str:
    return (
        f"(((action_id)::text = '{action}'::text) AND "
        f"((permission_id)::text = '{permission}'::text))"
    )


def _rewrite_action_registry(*, add: bool) -> None:
    definition = _action_definition()
    additions = " OR " + " OR ".join(_pair_token(*pair) for pair in _ACTIONS)
    marker = _pair_token("review.projection.rebuild", "operations.projection.rebuild")
    if add:
        if definition.count(marker) != 2 or any(
            _pair_token(*pair) in definition for pair in _ACTIONS
        ):
            raise RuntimeError("unexpected REV authorization action registry definition")
        definition = definition.replace(marker, marker + additions)
    else:
        if definition.count(additions) != 2:
            raise RuntimeError("unexpected REV authorization action registry definition")
        definition = definition.replace(additions, "")
    _replace_action_definition(definition)


def _identity_tokens(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


def _replace_identity_constraint(values: tuple[str, ...]) -> None:
    op.drop_constraint("kind_service_identity", "actor_profiles", type_="check")
    op.create_check_constraint(
        "kind_service_identity",
        "actor_profiles",
        "(actor_kind='human' and service_identity is null) or "
        f"(actor_kind='service' and service_identity in ({_identity_tokens(values)}))",
    )


def _lock_protected_state() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("lock table authority_idempotency_records in share row exclusive mode"))
    bind.execute(sa.text("lock table audit_events in access exclusive mode"))
    bind.execute(sa.text("lock table actor_profiles in access exclusive mode"))


def _has_action_evidence() -> bool:
    actions = [action for action, _ in _ACTIONS]
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "select exists(select 1 from audit_events where action_id = any(:actions)) or "
                "exists(select 1 from authority_idempotency_records record "
                "join audit_events event on event.idempotency_reference=record.id "
                "where event.action_id = any(:actions))"
            ),
            {"actions": actions},
        )
        .scalar_one()
    )


def _has_rev_service_identity() -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "select exists(select 1 from actor_profiles "
                "where service_identity = any(:identities))"
            ),
            {"identities": list(_REV_IDENTITIES)},
        )
        .scalar_one()
    )


def upgrade() -> None:
    """Register unavailable REV authority without creating any principal."""
    _lock_protected_state()
    _rewrite_action_registry(add=True)
    _replace_identity_constraint((*_HISTORICAL_IDENTITIES, *_REV_IDENTITIES))


def downgrade() -> None:
    """Restore 0048 only when no new action or identity has been used."""
    _lock_protected_state()
    if _has_action_evidence():
        raise RuntimeError("cannot downgrade non-empty REV authorization action evidence")
    if _has_rev_service_identity():
        raise RuntimeError("cannot downgrade in-use REV service identities")
    _rewrite_action_registry(add=False)
    _replace_identity_constraint(_HISTORICAL_IDENTITIES)
