"""activate durable guide-sufficiency authorization custody

Revision ID: 0050_guide_sufficiency_authority
Revises: 0049_rev_auth_readiness
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0050_guide_sufficiency_authority"
down_revision = "0049_rev_auth_readiness"
branch_labels = depends_on = None

_CREATION_COLUMNS = (
    ("created_by_actor_profile_id", sa.String(36)),
    ("created_via_identity_link_id", sa.String(36)),
    ("created_by_admin_role_grant_id", sa.Uuid()),
    ("created_by_service_identity", sa.String(160)),
    ("creation_scope_type", sa.String(16)),
    ("creation_scope_project_id", sa.String(36)),
    ("creation_action_id", sa.String(160)),
    ("authorization_decision_event_id", sa.String(36)),
)
_ACK_COLUMNS = (
    ("warnings_acknowledged_by_actor_profile_id", sa.String(36)),
    ("warnings_acknowledged_via_identity_link_id", sa.String(36)),
    ("warnings_acknowledged_by_admin_role_grant_id", sa.Uuid()),
    ("warning_acknowledgement_scope_type", sa.String(16)),
    ("warning_acknowledgement_scope_project_id", sa.String(36)),
    ("warning_acknowledgement_action_id", sa.String(160)),
    ("warning_acknowledgement_decision_event_id", sa.String(36)),
)


def upgrade() -> None:
    """Install replay and complete authorization provenance shapes."""
    for name, column_type in (*_CREATION_COLUMNS, *_ACK_COLUMNS):
        op.add_column("guide_sufficiency_reports", sa.Column(name, column_type))
    for constraint, name, remote_table, remote_column in (
        ("fk_suff_create_actor", "created_by_actor_profile_id", "actor_profiles", "id"),
        ("fk_suff_create_link", "created_via_identity_link_id", "actor_identity_links", "id"),
        ("fk_suff_create_grant", "created_by_admin_role_grant_id", "admin_role_grants", "id"),
        ("fk_suff_create_project", "creation_scope_project_id", "projects", "id"),
        ("fk_suff_create_decision", "authorization_decision_event_id", "audit_events", "id"),
        ("fk_suff_ack_actor", "warnings_acknowledged_by_actor_profile_id", "actor_profiles", "id"),
        (
            "fk_suff_ack_link",
            "warnings_acknowledged_via_identity_link_id",
            "actor_identity_links",
            "id",
        ),
        (
            "fk_suff_ack_grant",
            "warnings_acknowledged_by_admin_role_grant_id",
            "admin_role_grants",
            "id",
        ),
        ("fk_suff_ack_project", "warning_acknowledgement_scope_project_id", "projects", "id"),
        ("fk_suff_ack_decision", "warning_acknowledgement_decision_event_id", "audit_events", "id"),
    ):
        op.create_foreign_key(
            constraint,
            "guide_sufficiency_reports",
            remote_table,
            [name],
            [remote_column],
        )
    op.create_check_constraint(
        op.f("ck_guide_sufficiency_creation_authority_shape"),
        "guide_sufficiency_reports",
        "(created_by_actor_profile_id is null and created_via_identity_link_id is null "
        "and created_by_admin_role_grant_id is null and created_by_service_identity is null "
        "and creation_scope_type is null and creation_scope_project_id is null "
        "and creation_action_id is null and authorization_decision_event_id is null) or "
        "(created_by_actor_profile_id is not null and created_via_identity_link_id is not null "
        "and creation_scope_project_id is not null and creation_action_id in "
        "('project.guide_sufficiency_report.create','project.guide_sufficiency.run') "
        "and authorization_decision_event_id is not null and "
        "((created_by_admin_role_grant_id is not null and created_by_service_identity is null "
        "and creation_scope_type in ('system','project')) or "
        "(created_by_admin_role_grant_id is null "
        "and created_by_service_identity = 'workstream.project.setup' "
        "and creation_scope_type = 'service' "
        "and creation_action_id = 'project.guide_sufficiency.run' "
        "and project_setup_run_id is not null and setup_generation is not null "
        "and agent_material_sha256 is not null and agent_material_byte_count is not null)))",
    )
    op.create_check_constraint(
        op.f("ck_guide_sufficiency_ack_authority_shape"),
        "guide_sufficiency_reports",
        "(warnings_acknowledged_by_actor_profile_id is null "
        "and warnings_acknowledged_via_identity_link_id is null "
        "and warnings_acknowledged_by_admin_role_grant_id is null "
        "and warning_acknowledgement_scope_type is null "
        "and warning_acknowledgement_scope_project_id is null "
        "and warning_acknowledgement_action_id is null "
        "and warning_acknowledgement_decision_event_id is null) or "
        "(warnings_acknowledged_by_actor_profile_id is not null "
        "and warnings_acknowledged_via_identity_link_id is not null "
        "and warnings_acknowledged_by_admin_role_grant_id is not null "
        "and warning_acknowledgement_scope_type in ('system','project') "
        "and warning_acknowledgement_scope_project_id is not null "
        "and warning_acknowledgement_action_id = "
        "'project.guide_sufficiency.warnings.acknowledge' "
        "and warning_acknowledgement_decision_event_id is not null)",
    )
    op.create_table(
        "guide_sufficiency_mutation_idempotency_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "actor_profile_id",
            sa.String(36),
            sa.ForeignKey("actor_profiles.id"),
            nullable=False,
        ),
        sa.Column(
            "identity_link_id",
            sa.String(36),
            sa.ForeignKey("actor_identity_links.id"),
            nullable=False,
        ),
        sa.Column("action_id", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("resource_context_digest", sa.String(71), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("guide_id", sa.String(36), sa.ForeignKey("project_guides.id"), nullable=False),
        sa.Column(
            "source_snapshot_id",
            sa.String(36),
            sa.ForeignKey("guide_source_snapshots.id"),
            nullable=False,
        ),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("guide_sufficiency_reports.id")),
        sa.Column("setup_run_id", sa.String(36), sa.ForeignKey("project_setup_runs.id")),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response_json", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "actor_profile_id",
            "idempotency_key",
            name="uq_sufficiency_mutation_replay_namespace",
        ),
        sa.UniqueConstraint("operation_id", name="uq_sufficiency_mutation_operation_identity"),
        sa.CheckConstraint(
            "action_id in ('project.guide_sufficiency_report.create',"
            "'project.guide_sufficiency.run',"
            "'project.guide_sufficiency.warnings.acknowledge')",
            name="ck_sufficiency_mutation_action",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "resource_context_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_sufficiency_mutation_digests",
        ),
        sa.CheckConstraint("setup_generation > 0", name="ck_sufficiency_mutation_generation"),
        sa.CheckConstraint(
            "status in ('pending','committed')", name="ck_sufficiency_mutation_status"
        ),
        sa.CheckConstraint(
            "(status='pending' and response_json is null and committed_at is null) or "
            "(status='committed' and response_json is not null and report_id is not null "
            "and committed_at is not null)",
            name="ck_sufficiency_mutation_state_shape",
        ),
    )
    op.execute(
        """
        create function reject_sufficiency_replay_mutation() returns trigger
        language plpgsql as $$
        begin
          if tg_op = 'DELETE' then
            raise exception 'guide sufficiency replay rows are append-only';
          end if;
          if old.status = 'committed' or new.status <> 'committed'
             or (new.id,new.actor_profile_id,new.identity_link_id,new.action_id,
                 new.idempotency_key,new.request_digest,
                 new.resource_context_digest,
                 new.operation_id,new.project_id,new.guide_id,new.source_snapshot_id,
                 new.setup_run_id,new.setup_generation,new.created_at)
                is distinct from
                (old.id,old.actor_profile_id,old.identity_link_id,old.action_id,
                 old.idempotency_key,old.request_digest,
                 old.resource_context_digest,
                 old.operation_id,old.project_id,old.guide_id,old.source_snapshot_id,
                 old.setup_run_id,old.setup_generation,old.created_at)
          then
            raise exception 'invalid guide sufficiency replay mutation';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        """
        create trigger trg_sufficiency_replay_immutable
        before update or delete on guide_sufficiency_mutation_idempotency_records
        for each row execute function reject_sufficiency_replay_mutation()
        """
    )
    op.execute(
        """
        create function reject_sufficiency_replay_truncate() returns trigger
        language plpgsql as $$
        begin
          raise exception 'guide sufficiency replay rows are append-only';
        end $$
        """
    )
    op.execute(
        """
        create trigger trg_sufficiency_replay_no_truncate
        before truncate on guide_sufficiency_mutation_idempotency_records
        for each statement execute function reject_sufficiency_replay_truncate()
        """
    )


def downgrade() -> None:
    """Remove 12E authority only when no activated evidence exists."""
    connection = op.get_bind()
    replay_count = connection.execute(
        sa.text("select count(*) from guide_sufficiency_mutation_idempotency_records")
    ).scalar_one()
    provenance_count = connection.execute(
        sa.text(
            "select count(*) from guide_sufficiency_reports where "
            "created_by_actor_profile_id is not null or "
            "warnings_acknowledged_by_actor_profile_id is not null"
        )
    ).scalar_one()
    if replay_count or provenance_count:
        raise RuntimeError("cannot downgrade guide sufficiency authority with evidence")
    op.execute(
        "drop trigger trg_sufficiency_replay_no_truncate "
        "on guide_sufficiency_mutation_idempotency_records"
    )
    op.execute("drop function reject_sufficiency_replay_truncate()")
    op.execute(
        "drop trigger trg_sufficiency_replay_immutable on guide_sufficiency_mutation_idempotency_records"
    )
    op.execute("drop function reject_sufficiency_replay_mutation()")
    op.drop_table("guide_sufficiency_mutation_idempotency_records")
    op.drop_constraint(
        op.f("ck_guide_sufficiency_ack_authority_shape"),
        "guide_sufficiency_reports",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_guide_sufficiency_creation_authority_shape"),
        "guide_sufficiency_reports",
        type_="check",
    )
    foreign_keys = {
        "created_by_actor_profile_id": "fk_suff_create_actor",
        "created_via_identity_link_id": "fk_suff_create_link",
        "created_by_admin_role_grant_id": "fk_suff_create_grant",
        "creation_scope_project_id": "fk_suff_create_project",
        "authorization_decision_event_id": "fk_suff_create_decision",
        "warnings_acknowledged_by_actor_profile_id": "fk_suff_ack_actor",
        "warnings_acknowledged_via_identity_link_id": "fk_suff_ack_link",
        "warnings_acknowledged_by_admin_role_grant_id": "fk_suff_ack_grant",
        "warning_acknowledgement_scope_project_id": "fk_suff_ack_project",
        "warning_acknowledgement_decision_event_id": "fk_suff_ack_decision",
    }
    columns_without_foreign_keys = {
        "created_by_service_identity",
        "creation_scope_type",
        "creation_action_id",
        "warning_acknowledgement_scope_type",
        "warning_acknowledgement_action_id",
    }
    for name, _ in reversed((*_CREATION_COLUMNS, *_ACK_COLUMNS)):
        if name not in columns_without_foreign_keys:
            op.drop_constraint(foreign_keys[name], "guide_sufficiency_reports", type_="foreignkey")
        op.drop_column("guide_sufficiency_reports", name)
