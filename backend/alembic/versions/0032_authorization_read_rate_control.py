"""add durable authorization-read rate-control scope

Revision ID: 0032_authorization_read_rate
Revises: 0031_project_role_grants
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0032_authorization_read_rate"
down_revision = "0031_project_role_grants"
branch_labels = depends_on = None

_TABLE = "api_rate_control_counters"
_CONSTRAINT = "ck_api_rate_control_counters_scope_token"
_OLD_SCOPE_SQL = "control_scope in ('first_access', 'admin_mutation')"
_NEW_SCOPE_SQL = (
    "control_scope in ('first_access', 'admin_mutation', 'authorization_read')"
)
_OLD_SCOPE_EXPRESSION = (
    "((control_scope)::text = ANY ((ARRAY['first_access'::character varying, "
    "'admin_mutation'::character varying])::text[]))"
)
_NEW_SCOPE_EXPRESSION = (
    "((control_scope)::text = ANY ((ARRAY['first_access'::character varying, "
    "'admin_mutation'::character varying, 'authorization_read'::character varying])::text[]))"
)


def _require_scope_constraint(expected: str) -> None:
    definition = op.get_bind().execute(
        sa.text(
            "select pg_get_expr(conbin,conrelid) from pg_constraint "
            "where conrelid=cast(:table as regclass) and conname=:constraint"
        ),
        {"table": _TABLE, "constraint": _CONSTRAINT},
    ).scalar_one_or_none()
    if definition != expected:
        raise RuntimeError("unexpected API rate-control scope constraint")


def _replace_scope_constraint(definition: str) -> None:
    op.execute(sa.text(f"alter table {_TABLE} drop constraint {_CONSTRAINT}"))
    op.execute(
        sa.text(
            f"alter table {_TABLE} add constraint {_CONSTRAINT} check ({definition})"
        )
    )


def upgrade() -> None:
    """Add one closed scope while preserving all existing counters."""
    op.execute(sa.text(f"lock table {_TABLE} in access exclusive mode"))
    _require_scope_constraint(_OLD_SCOPE_EXPRESSION)
    _replace_scope_constraint(_NEW_SCOPE_SQL)


def downgrade() -> None:
    """Restore the prior scope only when no authorization-read counters exist."""
    bind = op.get_bind()
    bind.execute(sa.text(f"lock table {_TABLE} in access exclusive mode"))
    _require_scope_constraint(_NEW_SCOPE_EXPRESSION)
    has_rows = bind.execute(
        sa.text(
            f"select exists(select 1 from {_TABLE} "
            "where control_scope='authorization_read')"
        )
    ).scalar_one()
    if has_rows:
        raise RuntimeError("cannot downgrade live authorization-read rate controls")
    _replace_scope_constraint(_OLD_SCOPE_SQL)
