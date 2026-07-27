"""reconcile the complete ART authorization catalogue

Revision ID: 0036_art_auth_catalogue
Revises: 0035_project_read_evidence
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0036_art_auth_catalogue"
down_revision = "0035_project_read_evidence"
branch_labels = depends_on = None

_REMOVED_PERMISSIONS = (
    "artifact.upload_session.create",
    "artifact.upload_session.read",
    "artifact.upload_item.write",
    "artifact.upload_session.seal",
    "artifact.upload_session.cancel",
    "artifact.upload_session.expire",
)
_ADDED_PERMISSIONS = ("artifact.review_packet.materialize",)
_REMOVED_ACTIONS = tuple((value, value) for value in _REMOVED_PERMISSIONS)
_ADDED_ACTIONS = (
    ("artifact.submission_bundle.prepare", "submission.create"),
    ("artifact.review_packet.materialize", "artifact.review_packet.materialize"),
    ("artifact.review_evidence.binding.create", "artifact.binding.create"),
)


def _definition(name: str) -> str:
    return (
        op.get_bind()
        .execute(
            sa.text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid='audit_events'::regclass and conname=:name"
            ),
            {"name": f"ck_audit_events_{name}"},
        )
        .scalar_one()
    )


def _replace(name: str, definition: str) -> None:
    op.drop_constraint(name, "audit_events", type_="check")
    op.execute(f"alter table audit_events add constraint ck_audit_events_{name} {definition}")


def _permission_token(value: str) -> str:
    return f"('{value}'::character varying)::text"


def _pair_token(action: str, permission: str) -> str:
    return (
        f"(((action_id)::text = '{action}'::text) AND "
        f"((permission_id)::text = '{permission}'::text))"
    )


def _rewrite_permission_registry(*, forward: bool) -> None:
    remove = _REMOVED_PERMISSIONS if forward else _ADDED_PERMISSIONS
    add = _ADDED_PERMISSIONS if forward else _REMOVED_PERMISSIONS
    marker = _permission_token("artifact.binding.create")
    for name in ("authority_registries", "authority_privacy_bounds"):
        definition = _definition(name)
        for value in remove:
            token = _permission_token(value)
            if definition.count(token) < 1:
                raise RuntimeError(f"unexpected {name} removed permission definition")
            definition = definition.replace(", " + token, "")
            if token in definition:
                raise RuntimeError(f"unexpected {name} removed permission definition")
        additions = ", ".join(_permission_token(value) for value in add)
        if definition.count(marker) < 1 or any(
            _permission_token(value) in definition for value in add
        ):
            raise RuntimeError(f"unexpected {name} added permission definition")
        replacement = marker + ", " + additions if forward else additions + ", " + marker
        definition = definition.replace(marker, replacement)
        _replace(name, definition)


def _rewrite_action_registry(*, forward: bool) -> None:
    remove = _REMOVED_ACTIONS if forward else _ADDED_ACTIONS
    add = _ADDED_ACTIONS if forward else _REMOVED_ACTIONS
    name = "authorization_action_evidence"
    definition = _definition(name)
    for action, permission in remove:
        token = _pair_token(action, permission)
        if definition.count(token) != 2:
            raise RuntimeError("unexpected removed authorization action definition")
        definition = definition.replace(" OR " + token, "")
        if token in definition:
            raise RuntimeError("unexpected removed authorization action definition")
    marker = _pair_token(
        "artifact.guide_source.ingest" if forward else "artifact.guide_source.read",
        "artifact.guide_source.ingest" if forward else "artifact.guide_source.read",
    )
    additions = " OR " + " OR ".join(_pair_token(*pair) for pair in add)
    if definition.count(marker) != 2 or any(_pair_token(*pair) in definition for pair in add):
        raise RuntimeError("unexpected added authorization action definition")
    definition = definition.replace(marker, marker + additions)
    _replace(name, definition)


def _rewrite_action_permission_registry(*, forward: bool) -> None:
    remove = _REMOVED_PERMISSIONS if forward else _ADDED_PERMISSIONS
    add = _ADDED_PERMISSIONS if forward else _REMOVED_PERMISSIONS
    name = "authorization_action_evidence"
    definition = _definition(name)
    for value in remove:
        token = _permission_token(value)
        if definition.count(token) != 1:
            raise RuntimeError("unexpected removed action permission definition")
        definition = definition.replace(", " + token, "")
        if token in definition:
            raise RuntimeError("unexpected removed action permission definition")
    marker = _permission_token("artifact.binding.create")
    additions = ", ".join(_permission_token(value) for value in add)
    if definition.count(marker) != 1 or any(
        _permission_token(value) in definition for value in add
    ):
        raise RuntimeError("unexpected added action permission definition")
    replacement = marker + ", " + additions if forward else additions + ", " + marker
    definition = definition.replace(marker, replacement)
    _replace(name, definition)


def _lock_evidence() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("lock table authority_idempotency_records in share row exclusive mode"))
    bind.execute(sa.text("lock table audit_events in access exclusive mode"))


def _evidence_predicate(*, prefix: str, action_bind: str, permission_bind: str) -> str:
    return (
        f"{prefix}action_id = any(:{action_bind}) or "
        f"{prefix}permission_id = any(:{permission_bind}) or "
        f"({prefix}target_ref_kind='permission_registry' and "
        f"{prefix}target_ref_id = any(:{permission_bind})) or "
        f"({prefix}invalidation_target_kind='permission_registry' and "
        f"{prefix}invalidation_target_ref = any(:{permission_bind}))"
    )


def _has_evidence(actions: tuple[str, ...], permissions: tuple[str, ...]) -> bool:
    direct = _evidence_predicate(prefix="", action_bind="actions", permission_bind="permissions")
    linked = _evidence_predicate(
        prefix="event.",
        action_bind="linked_actions",
        permission_bind="linked_permissions",
    )
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "select exists(select 1 from audit_events where "
                f"{direct}) or "
                "exists(select 1 from authority_idempotency_records record "
                "join audit_events event on event.idempotency_reference=record.id "
                f"where {linked})"
            ),
            {
                "actions": list(actions),
                "permissions": list(permissions),
                "linked_actions": list(actions),
                "linked_permissions": list(permissions),
            },
        )
        .scalar_one()
    )


def upgrade() -> None:
    """Replace obsolete upload authority with planned bundle/review authority."""
    _lock_evidence()
    if _has_evidence(tuple(action for action, _ in _REMOVED_ACTIONS), _REMOVED_PERMISSIONS):
        raise RuntimeError("cannot remove non-empty obsolete artifact authority evidence")
    _rewrite_permission_registry(forward=True)
    _rewrite_action_registry(forward=True)
    _rewrite_action_permission_registry(forward=True)


def downgrade() -> None:
    """Restore the prior catalogue only when new ART authority has no evidence."""
    _lock_evidence()
    if _has_evidence(tuple(action for action, _ in _ADDED_ACTIONS), _ADDED_PERMISSIONS):
        raise RuntimeError("cannot downgrade non-empty ART authorization evidence")
    _rewrite_action_permission_registry(forward=False)
    _rewrite_action_registry(forward=False)
    _rewrite_permission_registry(forward=False)
