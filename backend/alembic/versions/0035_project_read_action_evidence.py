"""register project-read permissions and action evidence

Revision ID: 0035_project_read_evidence
Revises: 0034_project_role_issue_evidence
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0035_project_read_evidence"
down_revision = "0034_project_role_issue_evidence"
branch_labels = depends_on = None

_PERMISSIONS = (
    "project.setup_diagnostic.read",
    "project.effective_policy.read",
)
_ACTIONS = (
    ("project.read", "project.read"),
    ("actor.authorization_context.read", "actor.profile.read_self"),
    ("project.setup_run.read", _PERMISSIONS[0]),
    ("project.guide_sufficiency_report.list", _PERMISSIONS[0]),
    ("project.guide_sufficiency_report.read", _PERMISSIONS[0]),
    ("project.submission_artifact_policy.list", _PERMISSIONS[1]),
    ("project.submission_artifact_policy.read", _PERMISSIONS[1]),
    ("project.post_submit_checker_policy_setup.read", _PERMISSIONS[1]),
    ("project.effective_submission_artifact_policy.read", _PERMISSIONS[1]),
    ("project.pre_submit_checker_policy.read", _PERMISSIONS[1]),
    ("project.active_guide.read", "project.read"),
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


def _permission_tokens(*, add: bool) -> None:
    marker = "('project.role_grant.manage'::character varying)::text"
    addition = ", " + ", ".join(
        f"('{permission}'::character varying)::text" for permission in _PERMISSIONS
    )
    for name in ("authority_registries", "authority_privacy_bounds"):
        definition = _definition(name)
        if add:
            if definition.count(marker) < 1 or any(value in definition for value in _PERMISSIONS):
                raise RuntimeError(f"unexpected {name} permission registry definition")
            definition = definition.replace(marker, marker + addition)
        else:
            if definition.count(addition) < 1:
                raise RuntimeError(f"unexpected {name} permission registry definition")
            definition = definition.replace(addition, "")
        _replace(name, definition)


def _action_pairs(*, add: bool) -> None:
    name = "authorization_action_evidence"
    definition = _definition(name)
    marker = (
        "(((action_id)::text = 'project_role_grant.revoke'::text) AND "
        "((permission_id)::text = 'project.role_grant.manage'::text))"
    )
    additions = " OR ".join(
        f"(((action_id)::text = '{action}'::text) AND ((permission_id)::text = '{permission}'::text))"
        for action, permission in _ACTIONS
    )
    suffix = " OR " + additions
    if add:
        if definition.count(marker) != 2 or any(action in definition for action, _ in _ACTIONS):
            raise RuntimeError("unexpected authorization action registry definition")
        definition = definition.replace(marker, marker + suffix)
    else:
        if definition.count(suffix) != 2:
            raise RuntimeError("unexpected authorization action registry definition")
        definition = definition.replace(suffix, "")
    _replace(name, definition)


def _action_permission_tokens(*, add: bool) -> None:
    name = "authorization_action_evidence"
    definition = _definition(name)
    marker = "('review.queue.override'::character varying)::text"
    addition = ", " + ", ".join(
        f"('{permission}'::character varying)::text" for permission in _PERMISSIONS
    )
    if add:
        if definition.count(marker) != 1 or addition in definition:
            raise RuntimeError("unexpected authorization permission registry definition")
        definition = definition.replace(marker, marker + addition)
    else:
        if definition.count(addition) != 1:
            raise RuntimeError("unexpected authorization permission registry definition")
        definition = definition.replace(addition, "")
    _replace(name, definition)


def upgrade() -> None:
    """Add availability-neutral project-read registry parity."""
    _permission_tokens(add=True)
    _action_pairs(add=True)
    _action_permission_tokens(add=True)


def downgrade() -> None:
    """Remove project-read parity only when no forward evidence exists."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table audit_events in access exclusive mode"))
    blocked = bind.execute(
        sa.text(
            "select exists(select 1 from audit_events where "
            "action_id = any(:actions) or permission_id = any(:permissions) or "
            "(target_ref_kind='permission_registry' and target_ref_id = any(:permissions)) or "
            "(invalidation_target_kind='permission_registry' and invalidation_target_ref = any(:permissions)))"
        ),
        {"actions": [action for action, _ in _ACTIONS], "permissions": list(_PERMISSIONS)},
    ).scalar_one()
    if blocked:
        raise RuntimeError("cannot downgrade non-empty project-read action evidence")
    _action_permission_tokens(add=False)
    _action_pairs(add=False)
    _permission_tokens(add=False)
