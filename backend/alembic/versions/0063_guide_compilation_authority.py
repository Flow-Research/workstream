"""Activate exact unified guide-compilation authorization vocabulary.

Revision ID: 0063_compilation_authority
Revises: 0062_guide_compilation
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0063_compilation_authority"
down_revision = "0062_guide_compilation"
branch_labels = depends_on = None

_ACTION = "project.guide_compilation.request"
_EXECUTE_ACTION = "project.guide_compilation.execute"
_PERMISSION = _ACTION
_RESOURCE = "project_guide_compilation_request"


def _rewrite_constraint(name: str, marker: str, addition: str, *, add: bool) -> None:
    connection = op.get_bind()
    definition = connection.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass and conname=:name"
        ),
        {"name": f"ck_audit_events_{name}"},
    ).scalar_one()
    expanded = marker + addition
    source, target = (marker, expanded) if add else (expanded, marker)
    if definition.count(source) != 1 or (add and expanded in definition):
        raise RuntimeError(f"unexpected compilation authority {name} registry")
    op.drop_constraint(name, "audit_events", type_="check")
    op.execute(
        "alter table audit_events add constraint "
        f"ck_audit_events_{name} {definition.replace(source, target, 1)}"
    )


def _rewrite_action_evidence(*, add: bool) -> None:
    connection = op.get_bind()
    definition = connection.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authorization_action_evidence'"
        )
    ).scalar_one()
    marker = (
        "(((action_id)::text = 'project.guide_compilation.execute'::text) AND "
        "((permission_id)::text = 'project.guide_compilation.execute'::text))"
    )
    token = (
        " OR (((action_id)::text = 'project.guide_compilation.request'::text) AND "
        "((permission_id)::text = 'project.guide_compilation.request'::text))"
    )
    if add:
        if definition.count(marker) != 2 or token in definition:
            raise RuntimeError("unexpected compilation request action registry")
        definition = definition.replace(marker, marker + token)
    else:
        if definition.count(token) != 2:
            raise RuntimeError("unexpected compilation request action registry")
        definition = definition.replace(token, "")
    op.drop_constraint("authorization_action_evidence", "audit_events", type_="check")
    op.execute(
        "alter table audit_events add constraint "
        f"ck_audit_events_authorization_action_evidence {definition}"
    )


def upgrade() -> None:
    op.execute("lock table audit_events in access exclusive mode")
    _rewrite_constraint(
        "authority_privacy_bounds",
        "('project_guide_compilation_attempt'::character varying)::text",
        ", ('project_guide_compilation_request'::character varying)::text",
        add=True,
    )
    _rewrite_constraint(
        "authority_registries",
        "('project.guide_compilation.execute'::character varying)::text",
        ", ('project.guide_compilation.request'::character varying)::text",
        add=True,
    )
    _rewrite_action_evidence(add=True)


def downgrade() -> None:
    op.execute("lock table audit_events in access exclusive mode")
    retained = (
        op.get_bind()
        .execute(
            sa.text(
                "select exists(select 1 from audit_events "
                "where action_id in (:request_action, :execute_action))"
            ),
            {"request_action": _ACTION, "execute_action": _EXECUTE_ACTION},
        )
        .scalar_one()
    )
    if retained:
        raise RuntimeError("cannot downgrade retained compilation authority")
    _rewrite_action_evidence(add=False)
    _rewrite_constraint(
        "authority_registries",
        "('project.guide_compilation.execute'::character varying)::text",
        ", ('project.guide_compilation.request'::character varying)::text",
        add=False,
    )
    _rewrite_constraint(
        "authority_privacy_bounds",
        "('project_guide_compilation_attempt'::character varying)::text",
        ", ('project_guide_compilation_request'::character varying)::text",
        add=False,
    )
