"""make review and revision policy persistence explicit and immutable

Revision ID: 0034_review_revision_policy
Revises: 0033_authorization_read_rate
Create Date: 2026-07-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0034_review_revision_policy"
down_revision = "0033_authorization_read_rate"
branch_labels = depends_on = None


def _lock_policy_context() -> None:
    for table in ("project_guides", "review_policies", "revision_policies"):
        op.execute(sa.text(f"lock table {table} in access exclusive mode"))


def _create_review_columns() -> None:
    op.alter_column(
        "review_policies",
        "requires_second_review",
        new_column_name="legacy_requires_second_review",
        nullable=True,
    )
    op.alter_column("review_policies", "sla_hours", new_column_name="legacy_sla_hours")
    op.add_column(
        "review_policies", sa.Column("review_preference_window_seconds", sa.Integer())
    )
    op.add_column(
        "review_policies", sa.Column("review_lease_duration_seconds", sa.Integer())
    )
    op.add_column(
        "review_policies",
        sa.Column(
            "max_active_review_leases_per_reviewer",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "review_policies",
        sa.Column("self_review_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "review_policies",
        sa.Column("reject_policy", sa.String(30), nullable=False, server_default="close_task"),
    )
    op.add_column(
        "review_policies",
        sa.Column(
            "finding_evidence_requirement",
            sa.String(30),
            nullable=False,
            server_default="optional",
        ),
    )
    op.add_column(
        "review_policies",
        sa.Column("legacy_incomplete", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("review_policies", sa.Column("configured_by_actor", sa.String(100)))
    op.add_column(
        "review_policies", sa.Column("configured_at", sa.DateTime(timezone=True))
    )
    op.alter_column("review_policies", "legacy_incomplete", server_default=sa.false())


def _create_revision_columns() -> None:
    op.alter_column(
        "revision_policies",
        "auto_reject_after_limit",
        new_column_name="legacy_auto_reject_after_limit",
        nullable=True,
    )
    op.alter_column(
        "revision_policies",
        "allowed_resubmission_states",
        new_column_name="legacy_allowed_resubmission_states",
        nullable=True,
    )
    op.alter_column(
        "revision_policies",
        "reviewer_reassignment_rule",
        new_column_name="legacy_reviewer_reassignment_rule",
    )
    op.add_column(
        "revision_policies",
        sa.Column("legacy_incomplete", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("revision_policies", sa.Column("configured_by_actor", sa.String(100)))
    op.add_column(
        "revision_policies", sa.Column("configured_at", sa.DateTime(timezone=True))
    )
    op.alter_column("revision_policies", "legacy_incomplete", server_default=sa.false())


def _create_constraints() -> None:
    op.create_check_constraint(
        "ck_review_policies_fixed_v01",
        "review_policies",
        "legacy_incomplete or (max_active_review_leases_per_reviewer = 1 and "
        "self_review_allowed = false and reject_policy = 'close_task')",
    )
    op.create_check_constraint(
        "ck_review_policies_decisions_v01",
        "review_policies",
        "legacy_incomplete or allowed_decisions::jsonb = "
        "'[\"accept\",\"needs_revision\",\"reject\"]'::jsonb",
    )
    op.create_check_constraint(
        "ck_review_policies_finding_fields_v01",
        "review_policies",
        "legacy_incomplete or minimum_finding_fields::jsonb = "
        "'[\"description\",\"severity\"]'::jsonb",
    )
    op.create_check_constraint(
        "ck_review_policies_evidence_requirement",
        "review_policies",
        "legacy_incomplete or finding_evidence_requirement in "
        "('optional','required_for_blocking','required_for_all')",
    )
    op.create_check_constraint(
        "ck_review_policies_complete_or_legacy",
        "review_policies",
        "legacy_incomplete or (review_preference_window_seconds > 0 and "
        "review_lease_duration_seconds > 0 and configured_by_actor is not null and "
        "btrim(configured_by_actor) <> '' and configured_at is not null)",
    )
    op.create_check_constraint(
        "ck_review_policies_archival_shape",
        "review_policies",
        "(legacy_incomplete and review_preference_window_seconds is null and "
        "review_lease_duration_seconds is null and configured_by_actor is null and "
        "configured_at is null) or (not legacy_incomplete and "
        "legacy_requires_second_review is null and legacy_sla_hours is null)",
    )
    op.create_check_constraint(
        "ck_revision_policies_positive_limits",
        "revision_policies",
        "max_revision_rounds > 0 and revision_deadline_hours > 0",
    )
    op.create_check_constraint(
        "ck_revision_policies_complete_or_legacy",
        "revision_policies",
        "legacy_incomplete or (configured_by_actor is not null and "
        "btrim(configured_by_actor) <> '' and configured_at is not null)",
    )
    op.create_check_constraint(
        "ck_revision_policies_archival_shape",
        "revision_policies",
        "(legacy_incomplete and configured_by_actor is null and configured_at is null) "
        "or (not legacy_incomplete and legacy_auto_reject_after_limit is null and "
        "legacy_allowed_resubmission_states is null and "
        "legacy_reviewer_reassignment_rule is null)",
    )


def _create_write_guards() -> None:
    common_prefix = """
            declare
              guide_status varchar(30);
              guide_effective_at timestamptz;
              guide_superseded_at timestamptz;
            begin
              if tg_op = 'TRUNCATE' then
                raise exception 'review and revision policies cannot be truncated'
                  using errcode = '23514';
              end if;
              if tg_op = 'DELETE' then
                raise exception 'review and revision policies cannot be deleted'
                  using errcode = '23514';
              end if;
              select status, effective_at, superseded_at
                into guide_status, guide_effective_at, guide_superseded_at
                from project_guides
               where project_id = new.project_id and version = new.guide_version
               for update;
              if not found then
                raise exception 'policy guide context does not exist' using errcode = '23503';
              end if;
              if guide_status <> 'draft' or guide_effective_at is not null
                 or guide_superseded_at is not null then
                raise exception 'published review and revision policies are immutable'
                  using errcode = '23514';
              end if;
              if tg_op = 'INSERT' and new.legacy_incomplete then
                raise exception 'new policies cannot claim legacy state' using errcode = '23514';
              end if;
              if tg_op = 'UPDATE' then
                if (new.id, new.project_id, new.guide_version, new.created_at)
                   is distinct from
                   (old.id, old.project_id, old.guide_version, old.created_at) then
                  raise exception 'policy identity and context are immutable'
                    using errcode = '23514';
                end if;
                if not old.legacy_incomplete and new.legacy_incomplete then
                  raise exception 'complete policy cannot become legacy' using errcode = '23514';
                end if;
                if old.legacy_incomplete and new.legacy_incomplete then
                  raise exception 'legacy policy is immutable until atomic conversion'
                    using errcode = '23514';
                end if;
    """
    review_suffix = """
                if old.legacy_incomplete and not new.legacy_incomplete then
                  if new.legacy_requires_second_review is not null
                     or new.legacy_sla_hours is not null then
                    raise exception 'legacy review policy conversion must clear archives'
                      using errcode = '23514';
                  end if;
                elsif (new.legacy_requires_second_review, new.legacy_sla_hours)
                      is distinct from
                      (old.legacy_requires_second_review, old.legacy_sla_hours) then
                  raise exception 'review policy archives are immutable' using errcode = '23514';
                end if;
              end if;
              if not new.legacy_incomplete then
                new.configured_at := transaction_timestamp();
              end if;
              return new;
            end
    """
    revision_suffix = """
                if old.legacy_incomplete and not new.legacy_incomplete then
                  if new.legacy_auto_reject_after_limit is not null
                     or new.legacy_allowed_resubmission_states is not null
                     or new.legacy_reviewer_reassignment_rule is not null then
                    raise exception 'legacy revision policy conversion must clear archives'
                      using errcode = '23514';
                  end if;
                elsif (new.legacy_auto_reject_after_limit,
                       new.legacy_allowed_resubmission_states::jsonb,
                       new.legacy_reviewer_reassignment_rule)
                      is distinct from
                      (old.legacy_auto_reject_after_limit,
                       old.legacy_allowed_resubmission_states::jsonb,
                       old.legacy_reviewer_reassignment_rule) then
                  raise exception 'revision policy archives are immutable' using errcode = '23514';
                end if;
              end if;
              if not new.legacy_incomplete then
                new.configured_at := transaction_timestamp();
              end if;
              return new;
            end
    """
    op.execute(
        sa.text(
            "create function guard_review_policy_write() returns trigger language plpgsql as $$"
            + common_prefix
            + review_suffix
            + "$$"
        )
    )
    op.execute(
        sa.text(
            "create function guard_revision_policy_write() returns trigger language plpgsql as $$"
            + common_prefix
            + revision_suffix
            + "$$"
        )
    )
    op.execute(
        sa.text(
            "create trigger trg_review_policies_guard_write before insert or update or delete "
            "on review_policies for each row execute function "
            "guard_review_policy_write()"
        )
    )
    op.execute(
        sa.text(
            "create trigger trg_revision_policies_guard_write before insert or update or delete "
            "on revision_policies for each row execute function "
            "guard_revision_policy_write()"
        )
    )
    op.execute(
        sa.text(
            "create trigger trg_review_policies_reject_truncate before truncate "
            "on review_policies for each statement execute function "
            "guard_review_policy_write()"
        )
    )
    op.execute(
        sa.text(
            "create trigger trg_revision_policies_reject_truncate before truncate "
            "on revision_policies for each statement execute function "
            "guard_revision_policy_write()"
        )
    )


def upgrade() -> None:
    """Preserve legacy facts and install the canonical policy boundary."""
    _lock_policy_context()
    _create_review_columns()
    _create_revision_columns()
    _create_constraints()
    _create_write_guards()


def _require_lossless_downgrade() -> None:
    bind = op.get_bind()
    unsafe_review = bind.execute(
        sa.text(
            "select exists(select 1 from review_policies where not legacy_incomplete "
            "or review_preference_window_seconds is not null "
            "or review_lease_duration_seconds is not null or configured_by_actor is not null "
            "or configured_at is not null or legacy_requires_second_review is null)"
        )
    ).scalar_one()
    unsafe_revision = bind.execute(
        sa.text(
            "select exists(select 1 from revision_policies where not legacy_incomplete "
            "or configured_by_actor is not null or configured_at is not null "
            "or legacy_auto_reject_after_limit is null "
            "or legacy_allowed_resubmission_states is null)"
        )
    ).scalar_one()
    if unsafe_review or unsafe_revision:
        raise RuntimeError("cannot downgrade canonical review or revision policy facts")


def downgrade() -> None:
    """Restore 0033 only when every policy is an untouched migrated legacy row."""
    _lock_policy_context()
    _require_lossless_downgrade()
    op.execute(
        sa.text("drop trigger trg_revision_policies_reject_truncate on revision_policies")
    )
    op.execute(sa.text("drop trigger trg_review_policies_reject_truncate on review_policies"))
    op.execute(sa.text("drop trigger trg_revision_policies_guard_write on revision_policies"))
    op.execute(sa.text("drop trigger trg_review_policies_guard_write on review_policies"))
    op.execute(sa.text("drop function guard_revision_policy_write()"))
    op.execute(sa.text("drop function guard_review_policy_write()"))

    for name in (
        "ck_revision_policies_archival_shape",
        "ck_revision_policies_complete_or_legacy",
        "ck_revision_policies_positive_limits",
    ):
        op.drop_constraint(name, "revision_policies", type_="check")
    for name in (
        "ck_review_policies_archival_shape",
        "ck_review_policies_complete_or_legacy",
        "ck_review_policies_evidence_requirement",
        "ck_review_policies_finding_fields_v01",
        "ck_review_policies_decisions_v01",
        "ck_review_policies_fixed_v01",
    ):
        op.drop_constraint(name, "review_policies", type_="check")

    for column in ("configured_at", "configured_by_actor", "legacy_incomplete"):
        op.drop_column("revision_policies", column)
    op.alter_column(
        "revision_policies",
        "legacy_reviewer_reassignment_rule",
        new_column_name="reviewer_reassignment_rule",
    )
    op.alter_column(
        "revision_policies",
        "legacy_allowed_resubmission_states",
        new_column_name="allowed_resubmission_states",
        nullable=False,
    )
    op.alter_column(
        "revision_policies",
        "legacy_auto_reject_after_limit",
        new_column_name="auto_reject_after_limit",
        nullable=False,
    )

    for column in (
        "configured_at",
        "configured_by_actor",
        "legacy_incomplete",
        "finding_evidence_requirement",
        "reject_policy",
        "self_review_allowed",
        "max_active_review_leases_per_reviewer",
        "review_lease_duration_seconds",
        "review_preference_window_seconds",
    ):
        op.drop_column("review_policies", column)
    op.alter_column("review_policies", "legacy_sla_hours", new_column_name="sla_hours")
    op.alter_column(
        "review_policies",
        "legacy_requires_second_review",
        new_column_name="requires_second_review",
        nullable=False,
    )
