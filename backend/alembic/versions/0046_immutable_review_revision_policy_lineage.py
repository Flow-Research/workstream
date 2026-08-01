"""install immutable review and revision policy identity lineage

Revision ID: 0046_policy_identity_lineage
Revises: 0045_guide_metadata_authority
Create Date: 2026-08-01
"""

from __future__ import annotations

import hashlib
import json

from alembic import op
import sqlalchemy as sa


revision = "0046_policy_identity_lineage"
down_revision = "0045_guide_metadata_authority"
branch_labels = depends_on = None


def _digest(domain: str, value: dict) -> str:
    payload = json.dumps(
        {"domain": domain, "semantics": value},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _policy_columns() -> None:
    for table in ("review_policies", "revision_policies"):
        op.add_column(table, sa.Column("policy_generation", sa.Integer()))
        op.add_column(table, sa.Column("policy_hash", sa.String(71)))
        op.add_column(table, sa.Column("semantics_status", sa.String(24)))
        op.add_column(table, sa.Column("supersedes_policy_id", sa.String(36)))
        op.create_foreign_key(
            f"fk_{table}_supersedes",
            table,
            table,
            ["supersedes_policy_id"],
            ["id"],
        )
    for name, type_ in (
        ("review_preference_window_seconds", sa.Integer()),
        ("review_lease_duration_seconds", sa.Integer()),
        ("max_active_review_leases_per_reviewer", sa.Integer()),
        ("self_review_allowed", sa.Boolean()),
        ("reject_policy", sa.String(32)),
        ("finding_evidence_requirement", sa.String(32)),
    ):
        op.add_column("review_policies", sa.Column(name, type_))


def _backfill_policy_hashes() -> None:
    bind = op.get_bind()
    review_rows = bind.execute(
        sa.text(
            "select id,requires_second_review,allowed_decisions,minimum_finding_fields,sla_hours "
            "from review_policies"
        )
    ).mappings()
    for row in review_rows:
        value = {
            "requires_second_review": row["requires_second_review"],
            "allowed_decisions": row["allowed_decisions"],
            "minimum_finding_fields": row["minimum_finding_fields"],
            "legacy_sla_hours": row["sla_hours"],
        }
        bind.execute(
            sa.text(
                "update review_policies set policy_generation=1,policy_hash=:digest,"
                "semantics_status='legacy_incomplete' where id=:id"
            ),
            {"id": row["id"], "digest": _digest("workstream.review_policy.legacy.v1", value)},
        )
    revision_rows = bind.execute(
        sa.text(
            "select id,max_revision_rounds,revision_deadline_hours,auto_reject_after_limit,"
            "allowed_resubmission_states,reviewer_reassignment_rule from revision_policies"
        )
    ).mappings()
    for row in revision_rows:
        value = {
            "max_revision_rounds": row["max_revision_rounds"],
            "revision_deadline_hours": row["revision_deadline_hours"],
            "legacy_auto_reject_after_limit": row["auto_reject_after_limit"],
            "allowed_resubmission_states": row["allowed_resubmission_states"],
            "reviewer_reassignment_rule": row["reviewer_reassignment_rule"],
        }
        bind.execute(
            sa.text(
                "update revision_policies set policy_generation=1,policy_hash=:digest,"
                "semantics_status='legacy_incomplete' where id=:id"
            ),
            {"id": row["id"], "digest": _digest("workstream.revision_policy.legacy.v1", value)},
        )


def _add_lock_columns(table: str, nullable: bool) -> None:
    for kind in ("review", "revision"):
        op.add_column(
            table, sa.Column(f"locked_{kind}_policy_id", sa.String(36), nullable=nullable)
        )
        op.add_column(
            table, sa.Column(f"locked_{kind}_policy_generation", sa.Integer(), nullable=nullable)
        )
        op.add_column(
            table, sa.Column(f"locked_{kind}_policy_hash", sa.String(71), nullable=nullable)
        )


def _create_immutable_guard(table: str) -> None:
    op.execute(
        f"""
        create function guard_{table}_immutable() returns trigger language plpgsql as $$
        begin
          raise exception '{table} rows are immutable' using errcode='55000';
        end $$
        """
    )
    op.execute(
        f"create trigger {table}_immutable before update or delete on {table} "
        f"for each row execute function guard_{table}_immutable()"
    )
    op.execute(
        f"create trigger {table}_reject_truncate before truncate on {table} "
        f"execute function guard_{table}_immutable()"
    )


def upgrade() -> None:
    """Move every durable lock to immutable policy identity."""
    _policy_columns()
    _backfill_policy_hashes()
    for table in ("review_policies", "revision_policies"):
        op.alter_column(table, "policy_generation", nullable=False)
        op.alter_column(table, "policy_hash", nullable=False)
        op.alter_column(table, "semantics_status", nullable=False)

    for name in (
        "selected_review_policy_id",
        "selected_review_policy_hash",
        "selected_revision_policy_id",
        "selected_revision_policy_hash",
    ):
        op.add_column(
            "project_guides", sa.Column(name, sa.String(71 if name.endswith("hash") else 36))
        )
    op.add_column("project_guides", sa.Column("selected_review_policy_generation", sa.Integer()))
    op.add_column("project_guides", sa.Column("selected_revision_policy_generation", sa.Integer()))
    op.execute(
        """
        update project_guides g set
          selected_review_policy_id=r.id,
          selected_review_policy_generation=r.policy_generation,
          selected_review_policy_hash=r.policy_hash,
          selected_revision_policy_id=v.id,
          selected_revision_policy_generation=v.policy_generation,
          selected_revision_policy_hash=v.policy_hash
        from review_policies r, revision_policies v
        where r.project_id=g.project_id and r.guide_version=g.version
          and v.project_id=g.project_id and v.guide_version=g.version
        """
    )
    op.execute("set constraints all immediate")
    op.create_check_constraint(
        "policy_selection_shape",
        "project_guides",
        "(selected_review_policy_id is null and selected_review_policy_generation is null "
        "and selected_review_policy_hash is null and selected_revision_policy_id is null "
        "and selected_revision_policy_generation is null and "
        "selected_revision_policy_hash is null) or "
        "(selected_review_policy_id is not null and "
        "selected_review_policy_generation is not null and "
        "selected_review_policy_hash is not null and selected_revision_policy_id is not null "
        "and selected_revision_policy_generation is not null and "
        "selected_revision_policy_hash is not null)",
    )
    op.create_check_constraint(
        "active_policy_selection_required",
        "project_guides",
        "status not in ('active','superseded') or "
        "(selected_review_policy_id is not null and "
        "selected_review_policy_generation is not null and "
        "selected_review_policy_hash is not null and selected_revision_policy_id is not null "
        "and selected_revision_policy_generation is not null and "
        "selected_revision_policy_hash is not null)",
    )
    op.execute(
        """
        create function guard_project_guide_policy_selection() returns trigger language plpgsql
        as $$ begin
          if old.status in ('active','superseded') and (
            new.selected_review_policy_id is distinct from old.selected_review_policy_id or
            new.selected_review_policy_generation is distinct from
              old.selected_review_policy_generation or
            new.selected_review_policy_hash is distinct from old.selected_review_policy_hash or
            new.selected_revision_policy_id is distinct from old.selected_revision_policy_id or
            new.selected_revision_policy_generation is distinct from
              old.selected_revision_policy_generation or
            new.selected_revision_policy_hash is distinct from old.selected_revision_policy_hash
          ) then
            raise exception 'active guide policy selection is immutable' using errcode='55000';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger project_guides_policy_selection_immutable before update on "
        "project_guides for each row execute function guard_project_guide_policy_selection()"
    )

    _add_lock_columns("workstream_tasks", True)
    _add_lock_columns("submissions", True)
    _add_lock_columns("checker_runs", True)
    op.drop_constraint(
        "fk_checker_runs_submission_version", "checker_runs", type_="foreignkey"
    )
    op.create_unique_constraint(
        "uq_submissions_id_task_version", "submissions", ["id", "task_id", "version"]
    )
    op.create_foreign_key(
        "fk_checker_runs_submission_version",
        "checker_runs",
        "submissions",
        ["submission_id", "task_id", "submission_version"],
        ["id", "task_id", "version"],
    )
    op.execute(
        """
        update workstream_tasks t set
          locked_review_policy_id=r.id,
          locked_review_policy_generation=r.policy_generation,
          locked_review_policy_hash=r.policy_hash,
          locked_revision_policy_id=v.id,
          locked_revision_policy_generation=v.policy_generation,
          locked_revision_policy_hash=v.policy_hash
        from review_policies r, revision_policies v
        where r.project_id=t.project_id and r.guide_version=t.locked_review_policy_version
          and v.project_id=t.project_id and v.guide_version=t.locked_revision_policy_version
        """
    )
    op.create_check_constraint(
        "review_revision_policy_lock_shape",
        "workstream_tasks",
        "(locked_review_policy_id is null and locked_review_policy_generation is null "
        "and locked_review_policy_hash is null and locked_revision_policy_id is null "
        "and locked_revision_policy_generation is null and locked_revision_policy_hash is null) "
        "or (locked_review_policy_id is not null and "
        "locked_review_policy_generation is not null and locked_review_policy_hash is not null "
        "and locked_revision_policy_id is not null and "
        "locked_revision_policy_generation is not null and locked_revision_policy_hash is not null)",
    )
    op.create_check_constraint(
        "review_revision_policy_lock_required",
        "workstream_tasks",
        "status='draft' or (locked_review_policy_id is not null and "
        "locked_review_policy_generation is not null and locked_review_policy_hash is not null "
        "and locked_revision_policy_id is not null and "
        "locked_revision_policy_generation is not null and locked_revision_policy_hash is not null)",
    )
    for table in ("submissions", "checker_runs"):
        op.execute(
            f"""
            update {table} x set
              locked_review_policy_id=t.locked_review_policy_id,
              locked_review_policy_generation=t.locked_review_policy_generation,
              locked_review_policy_hash=t.locked_review_policy_hash,
              locked_revision_policy_id=t.locked_revision_policy_id,
              locked_revision_policy_generation=t.locked_revision_policy_generation,
              locked_revision_policy_hash=t.locked_revision_policy_hash
            from workstream_tasks t where t.id=x.task_id
            """
        )
        for kind in ("review", "revision"):
            op.alter_column(table, f"locked_{kind}_policy_id", nullable=False)
            op.alter_column(table, f"locked_{kind}_policy_generation", nullable=False)
            op.alter_column(table, f"locked_{kind}_policy_hash", nullable=False)

    for table, prefix in (
        ("submissions", "submissions_task"),
        ("checker_runs", "checker_runs_task"),
    ):
        op.drop_constraint(f"fk_{prefix}_locked_review_policy", table, type_="foreignkey")
        op.drop_constraint(f"fk_{prefix}_locked_revision_policy", table, type_="foreignkey")
    op.drop_constraint(
        "fk_workstream_tasks_locked_review_policy", "workstream_tasks", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_workstream_tasks_locked_revision_policy", "workstream_tasks", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_workstream_tasks_id_locked_review_policy", "workstream_tasks", type_="unique"
    )
    op.drop_constraint(
        "uq_workstream_tasks_id_locked_revision_policy", "workstream_tasks", type_="unique"
    )
    for table in ("workstream_tasks", "submissions", "checker_runs"):
        op.drop_column(table, "locked_review_policy_version")
        op.drop_column(table, "locked_revision_policy_version")

    op.drop_constraint("uq_review_policies_project_version", "review_policies", type_="unique")
    op.drop_constraint("uq_revision_policies_project_version", "revision_policies", type_="unique")
    op.create_unique_constraint(
        "uq_review_policies_project_version_generation",
        "review_policies",
        ["project_id", "guide_version", "policy_generation"],
    )
    op.create_unique_constraint(
        "uq_revision_policies_project_version_generation",
        "revision_policies",
        ["project_id", "guide_version", "policy_generation"],
    )
    for table, kind in (("review_policies", "review"), ("revision_policies", "revision")):
        op.create_unique_constraint(
            f"uq_{kind}_policy_lineage", table, ["id", "policy_generation", "policy_hash"]
        )
        op.create_unique_constraint(
            f"uq_{kind}_policy_scoped_lineage",
            table,
            ["project_id", "guide_version", "id", "policy_generation", "policy_hash"],
        )
        op.create_check_constraint(
            f"{kind}_policy_identity_shape",
            table,
            "policy_generation > 0 and policy_hash ~ '^sha256:[0-9a-f]{64}$' "
            "and semantics_status in ('complete','legacy_incomplete')",
        )
    op.create_check_constraint(
        "review_policy_semantics_shape",
        "review_policies",
        "(semantics_status='legacy_incomplete') or "
        "(review_preference_window_seconds > 0 and review_lease_duration_seconds > 0 "
        "and max_active_review_leases_per_reviewer=1 and self_review_allowed=false "
        "and reject_policy='close_task' and finding_evidence_requirement in "
        "('optional','required_for_blocking','required_for_all'))",
    )
    op.create_check_constraint(
        "revision_policy_semantics_shape",
        "revision_policies",
        "(semantics_status='legacy_incomplete') or "
        "(max_revision_rounds > 0 and revision_deadline_hours > 0)",
    )
    # The backfill updates tables with deferrable lineage constraints. Force
    # their queued checks to run before PostgreSQL is asked to ALTER those
    # same tables for the new composite foreign keys.
    op.execute("set constraints all immediate")
    op.create_foreign_key(
        "fk_project_guides_selected_review_policy",
        "project_guides",
        "review_policies",
        [
            "project_id",
            "version",
            "selected_review_policy_id",
            "selected_review_policy_generation",
            "selected_review_policy_hash",
        ],
        ["project_id", "guide_version", "id", "policy_generation", "policy_hash"],
    )
    op.create_foreign_key(
        "fk_project_guides_selected_revision_policy",
        "project_guides",
        "revision_policies",
        [
            "project_id",
            "version",
            "selected_revision_policy_id",
            "selected_revision_policy_generation",
            "selected_revision_policy_hash",
        ],
        ["project_id", "guide_version", "id", "policy_generation", "policy_hash"],
    )
    for kind in ("review", "revision"):
        op.create_unique_constraint(
            f"uq_workstream_tasks_id_locked_{kind}_policy",
            "workstream_tasks",
            [
                "id",
                f"locked_{kind}_policy_id",
                f"locked_{kind}_policy_generation",
                f"locked_{kind}_policy_hash",
            ],
        )
        op.create_foreign_key(
            f"fk_workstream_tasks_locked_{kind}_policy",
            "workstream_tasks",
            f"{kind}_policies",
            [
                "project_id",
                "locked_guide_version",
                f"locked_{kind}_policy_id",
                f"locked_{kind}_policy_generation",
                f"locked_{kind}_policy_hash",
            ],
            ["project_id", "guide_version", "id", "policy_generation", "policy_hash"],
        )
        for table, prefix in (
            ("submissions", "submissions_task"),
            ("checker_runs", "checker_runs_task"),
        ):
            op.create_foreign_key(
                f"fk_{prefix}_locked_{kind}_policy",
                table,
                "workstream_tasks",
                [
                    "task_id",
                    f"locked_{kind}_policy_id",
                    f"locked_{kind}_policy_generation",
                    f"locked_{kind}_policy_hash",
                ],
                [
                    "id",
                    f"locked_{kind}_policy_id",
                    f"locked_{kind}_policy_generation",
                    f"locked_{kind}_policy_hash",
                ],
            )
    op.drop_column("review_policies", "sla_hours")
    op.drop_column("revision_policies", "auto_reject_after_limit")
    _create_immutable_guard("review_policies")
    _create_immutable_guard("revision_policies")


def downgrade() -> None:
    """Restore the obsolete schema only when no policy meaning can be lost."""
    bind = op.get_bind()
    for table in ("review_policies", "revision_policies"):
        count = bind.execute(sa.text(f"select count(*) from {table}")).scalar_one()
        if count:
            raise RuntimeError("cannot downgrade populated immutable policy lineage")
    op.execute("drop trigger project_guides_policy_selection_immutable on project_guides")
    op.execute("drop function guard_project_guide_policy_selection()")
    op.drop_constraint(
        "review_revision_policy_lock_required",
        "workstream_tasks",
        type_="check",
    )
    op.drop_constraint(
        "review_revision_policy_lock_shape",
        "workstream_tasks",
        type_="check",
    )
    op.drop_constraint(
        "active_policy_selection_required",
        "project_guides",
        type_="check",
    )
    op.drop_constraint(
        "policy_selection_shape", "project_guides", type_="check"
    )
    for table in ("review_policies", "revision_policies"):
        op.execute(f"drop trigger {table}_reject_truncate on {table}")
        op.execute(f"drop trigger {table}_immutable on {table}")
        op.execute(f"drop function guard_{table}_immutable()")

    op.add_column("review_policies", sa.Column("sla_hours", sa.Integer()))
    op.add_column(
        "revision_policies",
        sa.Column(
            "auto_reject_after_limit", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
    )
    op.drop_constraint(
        "fk_checker_runs_submission_version", "checker_runs", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_submissions_id_task_version", "submissions", type_="unique"
    )
    op.create_foreign_key(
        "fk_checker_runs_submission_version",
        "checker_runs",
        "submissions",
        ["submission_id", "submission_version"],
        ["id", "version"],
    )
    for kind in ("review", "revision"):
        for table, prefix in (
            ("submissions", "submissions_task"),
            ("checker_runs", "checker_runs_task"),
        ):
            op.drop_constraint(f"fk_{prefix}_locked_{kind}_policy", table, type_="foreignkey")
        op.drop_constraint(
            f"fk_workstream_tasks_locked_{kind}_policy", "workstream_tasks", type_="foreignkey"
        )
        op.drop_constraint(
            f"uq_workstream_tasks_id_locked_{kind}_policy", "workstream_tasks", type_="unique"
        )
    op.drop_constraint(
        "fk_project_guides_selected_review_policy", "project_guides", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_project_guides_selected_revision_policy", "project_guides", type_="foreignkey"
    )
    for table in ("workstream_tasks", "submissions", "checker_runs"):
        op.add_column(table, sa.Column("locked_review_policy_version", sa.String(50)))
        op.add_column(table, sa.Column("locked_revision_policy_version", sa.String(50)))
    op.execute(
        """update workstream_tasks t set locked_review_policy_version=r.guide_version,
        locked_revision_policy_version=v.guide_version from review_policies r, revision_policies v
        where r.id=t.locked_review_policy_id and v.id=t.locked_revision_policy_id"""
    )
    for table in ("submissions", "checker_runs"):
        op.execute(
            f"""update {table} x set locked_review_policy_version=t.locked_review_policy_version,
            locked_revision_policy_version=t.locked_revision_policy_version
            from workstream_tasks t where t.id=x.task_id"""
        )
        op.alter_column(table, "locked_review_policy_version", nullable=False)
        op.alter_column(table, "locked_revision_policy_version", nullable=False)
    for table in ("workstream_tasks", "submissions", "checker_runs"):
        for kind in ("review", "revision"):
            op.drop_column(table, f"locked_{kind}_policy_hash")
            op.drop_column(table, f"locked_{kind}_policy_generation")
            op.drop_column(table, f"locked_{kind}_policy_id")
    op.create_unique_constraint(
        "uq_workstream_tasks_id_locked_review_policy",
        "workstream_tasks",
        ["id", "locked_review_policy_version"],
    )
    op.create_unique_constraint(
        "uq_workstream_tasks_id_locked_revision_policy",
        "workstream_tasks",
        ["id", "locked_revision_policy_version"],
    )
    op.create_unique_constraint(
        "uq_review_policies_project_version",
        "review_policies",
        ["project_id", "guide_version"],
    )
    op.create_unique_constraint(
        "uq_revision_policies_project_version",
        "revision_policies",
        ["project_id", "guide_version"],
    )
    op.create_foreign_key(
        "fk_workstream_tasks_locked_review_policy",
        "workstream_tasks",
        "review_policies",
        ["project_id", "locked_review_policy_version"],
        ["project_id", "guide_version"],
    )
    op.create_foreign_key(
        "fk_workstream_tasks_locked_revision_policy",
        "workstream_tasks",
        "revision_policies",
        ["project_id", "locked_revision_policy_version"],
        ["project_id", "guide_version"],
    )
    for table, prefix in (
        ("submissions", "submissions_task"),
        ("checker_runs", "checker_runs_task"),
    ):
        for kind in ("review", "revision"):
            op.create_foreign_key(
                f"fk_{prefix}_locked_{kind}_policy",
                table,
                "workstream_tasks",
                ["task_id", f"locked_{kind}_policy_version"],
                ["id", f"locked_{kind}_policy_version"],
            )
    for kind in ("review", "revision"):
        table = f"{kind}_policies"
        op.drop_constraint(f"{kind}_policy_semantics_shape", table, type_="check")
        op.drop_constraint(f"{kind}_policy_identity_shape", table, type_="check")
        op.drop_constraint(f"uq_{kind}_policy_scoped_lineage", table, type_="unique")
        op.drop_constraint(f"uq_{kind}_policy_lineage", table, type_="unique")
        op.drop_constraint(f"uq_{kind}_policies_project_version_generation", table, type_="unique")
        op.drop_constraint(f"fk_{table}_supersedes", table, type_="foreignkey")
        for column in (
            "supersedes_policy_id",
            "semantics_status",
            "policy_hash",
            "policy_generation",
        ):
            op.drop_column(table, column)
    for column in (
        "finding_evidence_requirement",
        "reject_policy",
        "self_review_allowed",
        "max_active_review_leases_per_reviewer",
        "review_lease_duration_seconds",
        "review_preference_window_seconds",
    ):
        op.drop_column("review_policies", column)
    for column in (
        "selected_revision_policy_hash",
        "selected_revision_policy_generation",
        "selected_revision_policy_id",
        "selected_review_policy_hash",
        "selected_review_policy_generation",
        "selected_review_policy_id",
    ):
        op.drop_column("project_guides", column)
