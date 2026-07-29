"""register planned project-mutation action evidence

Revision ID: 0041_project_mutation_evidence
Revises: 0040_guide_materialization
Create Date: 2026-07-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0041_project_mutation_evidence"
down_revision = "0040_guide_materialization"
branch_labels = depends_on = None

_ACTIONS = (
    ("project.create", "project.create"),
    ("project.guide.create", "project.guide.manage"),
    ("project.guide.update", "project.guide.manage"),
    ("project.guide_source_snapshot.create", "project.guide.manage"),
    ("project.review_policy.update", "project.review_policy.manage"),
    ("project.revision_policy.update", "project.review_policy.manage"),
    ("project.guide_sufficiency_report.create", "project.guide.manage"),
    ("project.guide_sufficiency.run", "project.guide.manage"),
    ("project.guide_sufficiency.warnings.acknowledge", "project.guide.manage"),
    ("project.submission_artifact_policy.create", "project.effective_policy.manage"),
    ("project.submission_artifact_policy.derive", "project.effective_policy.manage"),
    ("project.submission_artifact_policy.update", "project.effective_policy.manage"),
    ("project.submission_artifact_policy.approve", "project.effective_policy.manage"),
    ("project.post_submit_checker_policy.approve", "project.effective_policy.manage"),
    (
        "project.post_submit_checker_policy.correction.request",
        "project.effective_policy.manage",
    ),
    ("project.post_submit_checker_policy.derive", "project.effective_policy.manage"),
    ("project.setup_run.update", "project.guide.manage"),
    ("project.guide.activate", "project.guide.manage"),
)


def _definition() -> str:
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


def _replace(definition: str) -> None:
    op.drop_constraint(
        "ck_audit_events_authorization_action_evidence",
        "audit_events",
        type_="check",
    )
    op.execute(
        "alter table audit_events add constraint "
        f"ck_audit_events_authorization_action_evidence {definition}"
    )


def _pair_token(action: str, permission: str) -> str:
    return (
        f"(((action_id)::text = '{action}'::text) AND "
        f"((permission_id)::text = '{permission}'::text))"
    )


def _rewrite(*, add: bool) -> None:
    definition = _definition()
    additions = " OR " + " OR ".join(_pair_token(*pair) for pair in _ACTIONS)
    marker = _pair_token("project.active_guide.read", "project.read")
    if add:
        if definition.count(marker) != 2 or any(
            _pair_token(*pair) in definition for pair in _ACTIONS
        ):
            raise RuntimeError("unexpected project-mutation action registry definition")
        definition = definition.replace(marker, marker + additions)
    else:
        if definition.count(additions) != 2:
            raise RuntimeError("unexpected project-mutation action registry definition")
        definition = definition.replace(additions, "")
    _replace(definition)


def _lock_evidence() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("lock table authority_idempotency_records in share row exclusive mode"))
    bind.execute(sa.text("lock table audit_events in access exclusive mode"))


def _has_evidence() -> bool:
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


def upgrade() -> None:
    """Register the eighteen project-mutation pairs without activating them."""
    _lock_evidence()
    _rewrite(add=True)


def downgrade() -> None:
    """Remove project-mutation pairs only when no forward evidence exists."""
    _lock_evidence()
    if _has_evidence():
        raise RuntimeError("cannot downgrade non-empty project-mutation action evidence")
    _rewrite(add=False)
