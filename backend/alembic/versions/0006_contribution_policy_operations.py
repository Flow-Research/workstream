"""Install ContributionPolicy mutation-operation and event custody."""

from alembic import op
import sqlalchemy as sa

revision = "0006_contribution_policy_operations"
down_revision = "0005_compensation_adapter_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contribution_policy_versions",
        sa.Column("last_updated_by", sa.String(36)),
    )
    op.add_column(
        "contribution_policy_versions",
        sa.Column("last_updated_at", sa.DateTime(timezone=True)),
    )
    op.create_foreign_key(
        "fk_contribution_policy_version_updated_by",
        "contribution_policy_versions",
        "actor_profiles",
        ["last_updated_by"],
        ["id"],
    )
    op.create_table(
        "contribution_policy_lifecycle_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("actor_profile_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("contribution_policy_id", sa.Uuid(), nullable=False),
        sa.Column("contribution_policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("prior_current_version_id", sa.Uuid()),
        sa.Column("prior_current_version_number", sa.Integer()),
        sa.Column("from_policy_status", sa.String(16)),
        sa.Column("to_policy_status", sa.String(16), nullable=False),
        sa.Column("from_version_status", sa.String(16)),
        sa.Column("to_version_status", sa.String(16), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_profile_id"], ["actor_profiles.id"],
            name="fk_contribution_policy_event_actor",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_contribution_policy_event_project",
        ),
        sa.ForeignKeyConstraint(
            ["contribution_policy_id"], ["contribution_policies.id"],
            name="fk_contribution_policy_event_policy",
        ),
        sa.ForeignKeyConstraint(
            ["contribution_policy_version_id"], ["contribution_policy_versions.id"],
            name="fk_contribution_policy_event_version",
        ),
        sa.UniqueConstraint(
            "operation_id", name="uq_contribution_policy_event_operation"
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_contribution_policy_event_digest",
        ),
        sa.CheckConstraint(
            "event_type in ('draft_created','draft_updated','published','retired')",
            name="ck_contribution_policy_event_type",
        ),
        sa.CheckConstraint(
            "(event_type='draft_created' and from_version_status is null "
            "and to_version_status='draft') or "
            "(event_type='draft_updated' and from_version_status='draft' "
            "and to_version_status='draft') or "
            "(event_type='published' and from_version_status='draft' "
            "and to_version_status='published') or "
            "(event_type='retired' and from_version_status='published' "
            "and to_version_status='retired')",
            name="ck_contribution_policy_event_transition",
        ),
    )
    op.execute(
        """
        create function guard_contribution_policy_event_insert() returns trigger
        language plpgsql as $$
        declare
          policy contribution_policies%rowtype;
          version contribution_policy_versions%rowtype;
          prior_version_number integer;
        begin
          select * into policy from contribution_policies
            where id=new.contribution_policy_id;
          select * into version from contribution_policy_versions
            where id=new.contribution_policy_version_id;
          if policy.id is null or version.id is null
             or policy.project_id<>new.project_id
             or version.project_id<>new.project_id
             or version.contribution_policy_id<>new.contribution_policy_id
             or version.version_number<>new.version_number
             or version.status<>new.to_version_status
             or policy.status<>new.to_policy_status then
            raise exception 'invalid contribution policy lifecycle event'
              using errcode='23514';
          end if;
          if policy.current_published_version_id is not null then
            select version_number into prior_version_number
              from contribution_policy_versions
              where id=policy.current_published_version_id;
          end if;
          if new.prior_current_version_id
                is distinct from policy.current_published_version_id
             or new.prior_current_version_number
                is distinct from prior_version_number then
            raise exception 'contribution policy event prior version mismatch'
              using errcode='23514';
          end if;
          if (new.event_type='draft_created' and version.version_number=1
                 and (new.from_policy_status is not null or policy.status<>'draft'))
             or (new.event_type='draft_created' and version.version_number>1
                 and (new.from_policy_status<>'active' or policy.status<>'active'))
             or (new.event_type='draft_updated'
                 and new.from_policy_status<>policy.status) then
            raise exception 'contribution policy event prior state mismatch'
              using errcode='23514';
          end if;
          if (new.event_type='draft_created' and version.created_by<>new.actor_profile_id)
             or (new.event_type='draft_updated'
                 and version.last_updated_by<>new.actor_profile_id)
             or (new.event_type='published'
                 and version.published_by<>new.actor_profile_id)
             or (new.event_type='retired'
                 and version.retired_by<>new.actor_profile_id) then
            raise exception 'contribution policy event attribution mismatch'
              using errcode='23514';
          end if;
          new.occurred_at := clock_timestamp();
          return new;
        end;
        $$
        """
    )
    op.execute(
        "create trigger contribution_policy_event_insert_guard before insert on "
        "contribution_policy_lifecycle_events for each row execute function "
        "guard_contribution_policy_event_insert()"
    )
    op.execute(
        """
        create function reject_contribution_policy_event_change() returns trigger
        language plpgsql as $$
        begin
          raise exception 'contribution policy lifecycle events are immutable'
            using errcode='55000';
        end;
        $$
        """
    )
    op.execute(
        "create trigger contribution_policy_event_change_guard before update or delete on "
        "contribution_policy_lifecycle_events for each row execute function "
        "reject_contribution_policy_event_change()"
    )
    op.execute(
        "create trigger contribution_policy_event_truncate_guard before truncate on "
        "contribution_policy_lifecycle_events execute function "
        "reject_contribution_policy_event_change()"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Workstream v0.1 migrations cannot be downgraded; recreate the database"
    )
