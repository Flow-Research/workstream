"""bind ART authorization evidence to its exact resource context

Revision ID: 0037_art_auth_context_evidence
Revises: 0036_art_auth_catalogue
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0037_art_auth_context_evidence"
down_revision = "0036_art_auth_catalogue"
branch_labels = depends_on = None

_OLD_KEYS = """                'scope_type', 'scope_id', 'effective', 'allowed'
"""
_NEW_KEYS = """                'scope_type', 'scope_id', 'effective', 'allowed',
                'resource_context_digest'
"""
_OLD_ALLOWED_CASE = """                when 'allowed' then json_typeof(item.value) <> 'boolean'
                else true
"""
_NEW_ALLOWED_CASE = """                when 'allowed' then json_typeof(item.value) <> 'boolean'
                when 'resource_context_digest' then (item.value #>> '{}') !~
                  '^sha256:[0-9a-f]{64}$'
                else true
"""
_OLD_ALLOWED_BRANCH = """            when 'SensitiveAuthorizationAllowed' then return before_state is null and after_state::jsonb='{"allowed": true}'::jsonb;
            when 'SensitiveAuthorizationDenied' then return before_state is null and after_state::jsonb='{"allowed": false}'::jsonb;
"""
_NEW_ALLOWED_BRANCH = """            when 'SensitiveAuthorizationAllowed' then
              return before_state is null and (
                after_state::jsonb = '{"allowed": true}'::jsonb or (
                  after_state::jsonb->'allowed' = 'true'::jsonb
                  and after_state::jsonb ? 'resource_context_digest'
                  and (select count(*) from json_each(after_state)) = 2
                )
              );
            when 'SensitiveAuthorizationDenied' then
              return before_state is null and (
                after_state::jsonb = '{"allowed": false}'::jsonb or (
                  after_state::jsonb->'allowed' = 'false'::jsonb
                  and after_state::jsonb ? 'resource_context_digest'
                  and (select count(*) from json_each(after_state)) = 2
                )
              );
"""


def _definition(signature: str) -> str:
    value = op.get_bind().execute(
        sa.text("select pg_get_functiondef(to_regprocedure(:signature))"),
        {"signature": signature},
    ).scalar_one_or_none()
    if not isinstance(value, str):
        raise RuntimeError("required authority evidence function is unavailable")
    return value


def _replace_once(definition: str, old: str, new: str) -> str:
    if definition.count(old) != 1:
        raise RuntimeError("unexpected authority evidence function definition")
    return definition.replace(old, new)


def _replace(*, forward: bool) -> None:
    facts = _definition("authority_facts_are_safe(json)")
    events = _definition("authority_event_facts_are_safe(text,json,json,text)")
    if forward:
        facts = _replace_once(facts, _OLD_KEYS, _NEW_KEYS)
        facts = _replace_once(facts, _OLD_ALLOWED_CASE, _NEW_ALLOWED_CASE)
        events = _replace_once(events, _OLD_ALLOWED_BRANCH, _NEW_ALLOWED_BRANCH)
    else:
        facts = _replace_once(facts, _NEW_KEYS, _OLD_KEYS)
        facts = _replace_once(facts, _NEW_ALLOWED_CASE, _OLD_ALLOWED_CASE)
        events = _replace_once(events, _NEW_ALLOWED_BRANCH, _OLD_ALLOWED_BRANCH)
    op.execute(facts)
    op.execute(events)


def upgrade() -> None:
    op.execute("lock table audit_events in access exclusive mode")
    _replace(forward=True)


def downgrade() -> None:
    op.execute("lock table audit_events in access exclusive mode")
    exists = op.get_bind().execute(
        sa.text(
            "select exists(select 1 from audit_events where event_domain='authority' "
            "and after_facts::jsonb ? 'resource_context_digest')"
        )
    ).scalar_one()
    if exists:
        raise RuntimeError("artifact authorization context evidence prevents downgrade")
    _replace(forward=False)
