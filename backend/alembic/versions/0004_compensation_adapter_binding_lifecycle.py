"""Install the hidden compensation adapter-binding lifecycle."""

from alembic import op
import sqlalchemy as sa

revision = "0004_compensation_adapter_binding_lifecycle"
down_revision = "0003_submission_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text("select exists(select 1 from project_compensation_adapter_bindings)")
    ):
        raise RuntimeError(
            "Workstream v0.1 requires a fresh database before installing the "
            "compensation adapter-binding lifecycle"
        )

    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )

    op.execute(
        "drop trigger project_compensation_binding_update_guard "
        "on project_compensation_adapter_bindings"
    )
    op.execute("drop function enforce_compensation_binding_lifecycle()")
    for name in (
        "ck_project_compensation_adapter_bindings_ck_project_com_95ba",
        "ck_project_compensation_adapter_bindings_ck_project_com_da73",
    ):
        op.drop_constraint(op.f(name), "project_compensation_adapter_bindings", type_="check")
    op.create_check_constraint(
        op.f("ck_project_compensation_adapter_bindings_status"),
        "project_compensation_adapter_bindings",
        "status in ('active','suspended')",
    )
    op.create_check_constraint(
        op.f("ck_project_compensation_adapter_bindings_lifecycle_shape"),
        "project_compensation_adapter_bindings",
        "(status='active' and suspended_by is null and suspended_at is null "
        "and retired_by is null and retired_at is null) or "
        "(status='suspended' and binding_lifecycle_version > 1 "
        "and suspended_by is not null and suspended_at is not null "
        "and retired_by is null and retired_at is null)",
    )

    op.create_table(
        "compensation_adapter_binding_lifecycle_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("adapter_binding_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("actor_profile_id", sa.String(36), nullable=False),
        sa.Column("from_status", sa.String(16)),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("from_lifecycle_version", sa.Integer(), nullable=False),
        sa.Column("to_lifecycle_version", sa.Integer(), nullable=False),
        sa.Column("prior_suspension_event_id", sa.Uuid()),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_compensation_adapter_binding_lifecycle_events_request_digest",
        ),
        sa.CheckConstraint(
            "event_type in ('created','suspended','resumed')",
            name="ck_compensation_adapter_binding_lifecycle_events_event_type",
        ),
        sa.CheckConstraint(
            "(event_type='created' and from_status is null and to_status='active' "
            "and from_lifecycle_version=0 and to_lifecycle_version=1 "
            "and prior_suspension_event_id is null) or "
            "(event_type='suspended' and from_status='active' and to_status='suspended' "
            "and from_lifecycle_version > 0 "
            "and to_lifecycle_version=from_lifecycle_version+1 "
            "and prior_suspension_event_id is null) or "
            "(event_type='resumed' and from_status='suspended' and to_status='active' "
            "and from_lifecycle_version > 0 "
            "and to_lifecycle_version=from_lifecycle_version+1 "
            "and prior_suspension_event_id is not null)",
            name="ck_compensation_adapter_binding_lifecycle_events_transition_shape",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_compensation_binding_event_project"
        ),
        sa.ForeignKeyConstraint(
            ["adapter_binding_id"],
            ["project_compensation_adapter_bindings.id"],
            name="fk_compensation_binding_event_binding",
        ),
        sa.ForeignKeyConstraint(
            ["actor_profile_id"],
            ["actor_profiles.id"],
            name="fk_compensation_binding_event_actor",
        ),
        sa.ForeignKeyConstraint(
            ["prior_suspension_event_id"],
            ["compensation_adapter_binding_lifecycle_events.id"],
            name="fk_compensation_binding_event_prior_suspension",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_compensation_adapter_binding_lifecycle_events"),
        sa.UniqueConstraint("operation_id", name="operation_id"),
        sa.UniqueConstraint(
            "adapter_binding_id",
            "to_lifecycle_version",
            name="binding_version",
        ),
    )
    op.create_index(
        "ix_compensation_binding_event_binding",
        "compensation_adapter_binding_lifecycle_events",
        ["adapter_binding_id", "to_lifecycle_version"],
    )

    op.execute(
        """
        create function enforce_compensation_binding_lifecycle() returns trigger
        language plpgsql as $$
        begin
          if (new.id,new.project_id,new.instrument_type,new.adapter_actor_id,new.route_key,
              new.created_by,new.created_at,new.retired_by,new.retired_at)
             is distinct from
             (old.id,old.project_id,old.instrument_type,old.adapter_actor_id,old.route_key,
              old.created_by,old.created_at,old.retired_by,old.retired_at) then
            raise exception 'compensation binding identity is immutable' using errcode='55000';
          end if;
          if old.status='active' and new.status='suspended'
             and new.binding_lifecycle_version=old.binding_lifecycle_version+1
             and new.suspended_by is not null then
            new.suspended_at := clock_timestamp();
            return new;
          end if;
          if old.status='suspended' and new.status='active'
             and new.binding_lifecycle_version=old.binding_lifecycle_version+1
             and new.suspended_by is null and new.suspended_at is null then
            return new;
          end if;
          raise exception 'invalid compensation binding lifecycle transition' using errcode='23514';
        end;
        $$
        """
    )
    op.execute(
        "create trigger project_compensation_binding_update_guard before update on "
        "project_compensation_adapter_bindings for each row execute function "
        "enforce_compensation_binding_lifecycle()"
    )
    op.execute(
        """
        create function guard_compensation_binding_lifecycle_event() returns trigger
        language plpgsql as $$
        declare
          binding project_compensation_adapter_bindings%rowtype;
          prior compensation_adapter_binding_lifecycle_events%rowtype;
          preceding compensation_adapter_binding_lifecycle_events%rowtype;
        begin
          select * into binding from project_compensation_adapter_bindings
            where id=new.adapter_binding_id;
          if not found or binding.project_id<>new.project_id
             or binding.status<>new.to_status
             or binding.binding_lifecycle_version<>new.to_lifecycle_version then
            raise exception 'invalid compensation binding lifecycle event' using errcode='23514';
          end if;
          if (new.event_type='created' and binding.created_by<>new.actor_profile_id)
             or (new.event_type='suspended' and binding.suspended_by<>new.actor_profile_id) then
            raise exception 'compensation binding lifecycle attribution mismatch'
              using errcode='23514';
          end if;
          new.occurred_at := clock_timestamp();
          select * into preceding from compensation_adapter_binding_lifecycle_events
            where adapter_binding_id=new.adapter_binding_id
            order by to_lifecycle_version desc limit 1;
          if new.event_type='created' then
            if found then
              raise exception 'created event must be first' using errcode='23514';
            end if;
          elsif not found or preceding.to_lifecycle_version<>new.from_lifecycle_version
                or preceding.to_status<>new.from_status then
            raise exception 'lifecycle event is not contiguous' using errcode='23514';
          end if;
          if new.event_type='resumed' then
            select * into prior from compensation_adapter_binding_lifecycle_events
              where id=new.prior_suspension_event_id;
            if not found or prior.adapter_binding_id<>new.adapter_binding_id
               or prior.event_type<>'suspended'
               or prior.id<>preceding.id
               or prior.to_lifecycle_version<>new.from_lifecycle_version then
              raise exception 'invalid prior suspension event' using errcode='23514';
            end if;
          end if;
          return new;
        end;
        $$
        """
    )
    op.execute(
        "create trigger compensation_binding_event_insert_guard before insert on "
        "compensation_adapter_binding_lifecycle_events for each row execute function "
        "guard_compensation_binding_lifecycle_event()"
    )
    op.execute(
        """
        create function reject_compensation_binding_lifecycle_event_change() returns trigger
        language plpgsql as $$
        begin
          raise exception 'compensation binding lifecycle events are immutable'
            using errcode='55000';
        end;
        $$
        """
    )
    op.execute(
        "create trigger compensation_binding_event_change_guard before update or delete on "
        "compensation_adapter_binding_lifecycle_events for each row execute function "
        "reject_compensation_binding_lifecycle_event_change()"
    )
    op.execute(
        "create trigger compensation_binding_event_truncate_guard before truncate on "
        "compensation_adapter_binding_lifecycle_events for each statement execute function "
        "reject_compensation_binding_lifecycle_event_change()"
    )
    op.execute(
        """
        create function require_compensation_binding_lifecycle_event() returns trigger
        language plpgsql as $$
        begin
          if not exists (
            select 1 from compensation_adapter_binding_lifecycle_events e
            where e.adapter_binding_id=new.id
              and e.project_id=new.project_id
              and e.to_status=new.status
              and e.to_lifecycle_version=new.binding_lifecycle_version
          ) then
            raise exception 'compensation binding transition requires lifecycle event'
              using errcode='23514';
          end if;
          return null;
        end;
        $$
        """
    )
    op.execute(
        "create constraint trigger compensation_binding_lifecycle_event_required "
        "after insert or update on project_compensation_adapter_bindings "
        "deferrable initially deferred for each row execute function "
        "require_compensation_binding_lifecycle_event()"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Workstream v0.1 migrations cannot be downgraded; recreate the database"
    )
