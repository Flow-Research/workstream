"""add authority idempotency and linked invalidation enforcement

Revision ID: 0019_authority_idempotency
Revises: 0018_authority_audit_evidence
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0019_authority_idempotency"
down_revision = "0018_authority_audit_evidence"
branch_labels = None
depends_on = None

OPERATIONS = (
    "service_actor.create", "admin_role_grant.issue", "admin_role_grant.revoke",
    "project_role_grant.issue", "project_role_grant.revoke", "actor_profile.suspend",
    "actor_profile.reactivate", "actor_profile.deactivate", "actor_identity_link.revoke",
    "actor_identity_link.reactivate",
)


def _tokens(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Create immutable reservations and enforce new audit-reference integrity."""
    op.create_table(
        "authority_idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("actor_ref_kind", sa.String(32), nullable=False),
        sa.Column("actor_ref", sa.String(100), nullable=False),
        sa.Column("operation", sa.String(48), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response_resource_type", sa.String(32)),
        sa.Column("response_resource_id", sa.Uuid()),
        sa.Column("response_resource_version", sa.BigInteger()),
        sa.Column("response_http_status", sa.SmallInteger()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_authority_idempotency_records"),
        sa.UniqueConstraint(
            "actor_ref_kind", "actor_ref", "operation", "idempotency_key",
            name="uq_authority_idempotency_records_replay_namespace",
        ),
        sa.UniqueConstraint(
            "id", "actor_ref_kind", "actor_ref",
            name="uq_authority_idempotency_records_actor_reference",
        ),
        sa.CheckConstraint(
            "actor_ref_kind in ('legacy_actor', 'actor_profile', 'system_principal')",
            name="actor_kind",
        ),
        sa.CheckConstraint(
            "((actor_ref_kind = 'system_principal' and actor_ref = "
            "'workstream:system:bootstrap') or (actor_ref_kind <> 'system_principal' "
            "and actor_ref ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'))",
            name="actor_reference",
        ),
        sa.CheckConstraint(
            f"operation in ({_tokens(OPERATIONS)})",
            name="operation",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="request_digest",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'committed')",
            name="status",
        ),
        sa.CheckConstraint(
            "response_resource_version is null or response_resource_version > 0",
            name="response_version",
        ),
        sa.CheckConstraint(
            "(status = 'pending' and response_resource_type is null and "
            "response_resource_id is null and response_resource_version is null and "
            "response_http_status is null and committed_at is null) or "
            "(status = 'committed' and response_resource_type is not null and "
            "response_resource_id is not null and response_http_status is not null and "
            "committed_at is not null)",
            name="state_shape",
        ),
        sa.CheckConstraint(
            "(operation = 'service_actor.create' and (response_resource_type is null or "
            "response_resource_type = 'actor_profile')) or "
            "(operation like 'admin_role_grant.%' and (response_resource_type is null or "
            "response_resource_type = 'admin_role_grant')) or "
            "(operation like 'project_role_grant.%' and (response_resource_type is null or "
            "response_resource_type = 'project_role_grant')) or "
            "(operation like 'actor_profile.%' and (response_resource_type is null or "
            "response_resource_type = 'actor_profile')) or "
            "(operation like 'actor_identity_link.%' and (response_resource_type is null or "
            "response_resource_type = 'actor_identity_link'))",
            name="response_type",
        ),
        sa.CheckConstraint(
            "response_http_status is null or ((operation in ('service_actor.create', "
            "'admin_role_grant.issue', 'project_role_grant.issue') and "
            "response_http_status = 201) or (operation not in ('service_actor.create', "
            "'admin_role_grant.issue', 'project_role_grant.issue') and "
            "response_http_status = 200))",
            name="response_status",
        ),
    )
    op.execute(
        "alter table audit_events add constraint fk_audit_events_authority_idempotency "
        "foreign key (idempotency_reference, actor_ref_kind, actor_id) references "
        "authority_idempotency_records (id, actor_ref_kind, actor_ref) not valid"
    )
    _create_functions_and_triggers()


def _create_functions_and_triggers() -> None:
    op.execute(
        """
        create function guard_authority_idempotency_record() returns trigger
        language plpgsql as $$
        declare success_count integer; invalidation_count integer; success_id text;
                success_row audit_events%rowtype;
        begin
          if tg_op = 'INSERT' then
            if new.status <> 'pending' then raise exception 'idempotency must begin pending' using errcode='23514'; end if;
            new.created_at := statement_timestamp(); new.committed_at := null; return new;
          elsif tg_op = 'DELETE' then
            raise exception 'authority idempotency records are immutable' using errcode='55000';
          end if;
          if old.status <> 'pending' or new.status <> 'committed'
             or (new.id, new.idempotency_key, new.actor_ref_kind, new.actor_ref,
                 new.operation, new.request_digest, new.created_at)
                is distinct from
                (old.id, old.idempotency_key, old.actor_ref_kind, old.actor_ref,
                 old.operation, old.request_digest, old.created_at) then
            raise exception 'invalid authority idempotency transition' using errcode='23514';
          end if;
          select count(*), min(id) into success_count, success_id
          from audit_events where event_domain='authority' and idempotency_reference=new.id
            and event_type <> 'AuthorityInvalidationRequested';
          select count(*) into invalidation_count from audit_events
          where event_domain='authority' and idempotency_reference=new.id
            and event_type='AuthorityInvalidationRequested';
          if success_count <> 1 or invalidation_count <> 1 then
            raise exception 'authority evidence pair required' using errcode='23514';
          end if;
          select * into success_row from audit_events where id=success_id;
          if success_row.resource_type <> new.response_resource_type
             or success_row.resource_id <> new.response_resource_id::text then
            raise exception 'authority response does not match evidence' using errcode='23514';
          end if;
          new.committed_at := statement_timestamp(); return new;
        end $$
        """
    )
    op.execute(
        """
        create function reject_pending_authority_idempotency() returns trigger
        language plpgsql as $$ begin
          if exists(select 1 from authority_idempotency_records where id=new.id and status='pending') then
            raise exception 'pending authority idempotency cannot commit' using errcode='23514';
          end if; return null;
        end $$
        """
    )
    op.execute(
        """
        create function reject_authority_idempotency_truncate() returns trigger
        language plpgsql as $$ begin
          raise exception 'authority idempotency records are immutable' using errcode='55000';
        end $$
        """
    )
    op.execute(
        """
        create function validate_linked_authority_event() returns trigger
        language plpgsql as $$
        declare record_row authority_idempotency_records%rowtype;
                cause_row audit_events%rowtype; expected_permission text;
                expected_resource text; valid_success boolean;
        begin
          if new.event_domain <> 'authority' then return new; end if;
          valid_success := new.event_type in (
            'ServiceActorProvisioned','AdminRoleGrantIssued','AdminRoleGrantRevoked',
            'ProjectRoleGrantIssued','ProjectRoleGrantReplaced','ProjectRoleGrantRevoked',
            'ActorProfileSuspended','ActorProfileReactivated','ActorProfileDeactivated',
            'ActorIdentityLinkRevoked','ActorIdentityLinkReactivated');
          if not valid_success and new.event_type <> 'AuthorityInvalidationRequested' then
            if new.idempotency_reference is not null then
              raise exception 'invalid authority idempotency event' using errcode='23514';
            end if; return new;
          end if;
          if new.idempotency_reference is null then
            raise exception 'authority event requires idempotency reference' using errcode='23514';
          end if;
          select * into record_row from authority_idempotency_records
          where id=new.idempotency_reference and actor_ref_kind=new.actor_ref_kind and actor_ref=new.actor_id;
          if not found then raise exception 'invalid authority idempotency reference' using errcode='23503'; end if;
          if record_row.status <> 'pending' then
            raise exception 'committed authority idempotency is closed' using errcode='23514';
          end if;
          expected_permission := case record_row.operation
            when 'service_actor.create' then 'actor.service.provision'
            when 'admin_role_grant.issue' then 'admin_role.grant'
            when 'admin_role_grant.revoke' then 'admin_role.revoke'
            when 'project_role_grant.issue' then 'project.role_grant.manage'
            when 'project_role_grant.revoke' then 'project.role_grant.manage'
            when 'actor_profile.suspend' then 'actor.profile.suspend'
            when 'actor_profile.reactivate' then 'actor.profile.reactivate'
            when 'actor_profile.deactivate' then 'actor.profile.deactivate'
            when 'actor_identity_link.revoke' then 'actor.identity_link.revoke'
            when 'actor_identity_link.reactivate' then 'actor.identity_link.reactivate' end;
          expected_resource := case
            when record_row.operation='service_actor.create' or record_row.operation like 'actor_profile.%' then 'actor_profile'
            when record_row.operation like 'admin_role_grant.%' then 'admin_role_grant'
            when record_row.operation like 'project_role_grant.%' then 'project_role_grant'
            else 'actor_identity_link' end;
          if new.permission_id <> expected_permission or new.resource_type <> expected_resource
             or new.resource_id is null then
            raise exception 'authority event does not match operation' using errcode='23514';
          end if;
          if new.event_type='AuthorityInvalidationRequested' then
            select * into cause_row from audit_events where id=new.invalidation_cause_event_id;
            if not found or cause_row.idempotency_reference is distinct from record_row.id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.resource_type is distinct from new.invalidation_target_kind
               or cause_row.resource_id is distinct from new.invalidation_target_ref
               or cause_row.resource_type is distinct from new.resource_type
               or cause_row.resource_id is distinct from new.resource_id
               or cause_row.target_ref_kind is distinct from cause_row.resource_type
               or cause_row.target_ref_id is distinct from cause_row.resource_id
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.project_id is distinct from new.project_id
               or new.entity_type <> 'authority_invalidation'
               or new.entity_id <> new.id
               or not (
                 (record_row.operation='service_actor.create' and cause_row.event_type='ServiceActorProvisioned') or
                 (record_row.operation='admin_role_grant.issue' and cause_row.event_type='AdminRoleGrantIssued') or
                 (record_row.operation='admin_role_grant.revoke' and cause_row.event_type='AdminRoleGrantRevoked') or
                 (record_row.operation='project_role_grant.issue' and cause_row.event_type in ('ProjectRoleGrantIssued','ProjectRoleGrantReplaced')) or
                 (record_row.operation='project_role_grant.revoke' and cause_row.event_type='ProjectRoleGrantRevoked') or
                 (record_row.operation='actor_profile.suspend' and cause_row.event_type='ActorProfileSuspended') or
                 (record_row.operation='actor_profile.reactivate' and cause_row.event_type='ActorProfileReactivated') or
                 (record_row.operation='actor_profile.deactivate' and cause_row.event_type='ActorProfileDeactivated') or
                 (record_row.operation='actor_identity_link.revoke' and cause_row.event_type='ActorIdentityLinkRevoked') or
                 (record_row.operation='actor_identity_link.reactivate' and cause_row.event_type='ActorIdentityLinkReactivated')) then
              raise exception 'invalid linked authority cause' using errcode='23514';
            end if;
          else
            if new.entity_type <> expected_resource or new.entity_id <> new.resource_id
               or new.target_ref_kind is distinct from expected_resource
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null
               or new.invalidation_target_ref is not null
               or not (
                 (record_row.operation='service_actor.create' and new.event_type='ServiceActorProvisioned') or
                 (record_row.operation='admin_role_grant.issue' and new.event_type='AdminRoleGrantIssued') or
                 (record_row.operation='admin_role_grant.revoke' and new.event_type='AdminRoleGrantRevoked') or
                 (record_row.operation='project_role_grant.issue' and new.event_type in ('ProjectRoleGrantIssued','ProjectRoleGrantReplaced')) or
                 (record_row.operation='project_role_grant.revoke' and new.event_type='ProjectRoleGrantRevoked') or
                 (record_row.operation='actor_profile.suspend' and new.event_type='ActorProfileSuspended') or
                 (record_row.operation='actor_profile.reactivate' and new.event_type='ActorProfileReactivated') or
                 (record_row.operation='actor_profile.deactivate' and new.event_type='ActorProfileDeactivated') or
                 (record_row.operation='actor_identity_link.revoke' and new.event_type='ActorIdentityLinkRevoked') or
                 (record_row.operation='actor_identity_link.reactivate' and new.event_type='ActorIdentityLinkReactivated')) then
              raise exception 'authority success event does not match operation' using errcode='23514';
            end if;
          end if; return new;
        end $$
        """
    )
    op.execute(
        "create trigger authority_idempotency_guard before insert or update or delete "
        "on authority_idempotency_records for each row execute function guard_authority_idempotency_record()"
    )
    op.execute(
        "create constraint trigger authority_idempotency_pending_guard after insert or update "
        "on authority_idempotency_records deferrable initially deferred for each row "
        "execute function reject_pending_authority_idempotency()"
    )
    op.execute(
        "create trigger authority_idempotency_reject_truncate before truncate "
        "on authority_idempotency_records execute function reject_authority_idempotency_truncate()"
    )
    op.execute(
        "create trigger audit_events_validate_idempotency before insert on audit_events "
        "for each row execute function validate_linked_authority_event()"
    )


def downgrade() -> None:
    """Drop 0019 only when no durable idempotency/evidence pair exists."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table authority_idempotency_records in access exclusive mode"))
    bind.execute(sa.text("lock table audit_events in access exclusive mode"))
    if bind.execute(sa.text("select exists(select 1 from authority_idempotency_records)")).scalar_one():
        raise RuntimeError("cannot downgrade non-empty authority idempotency")
    op.execute("drop trigger audit_events_validate_idempotency on audit_events")
    op.execute("drop function validate_linked_authority_event()")
    op.drop_constraint("fk_audit_events_authority_idempotency", "audit_events", type_="foreignkey")
    op.execute("drop trigger authority_idempotency_pending_guard on authority_idempotency_records")
    op.execute("drop trigger authority_idempotency_reject_truncate on authority_idempotency_records")
    op.execute("drop trigger authority_idempotency_guard on authority_idempotency_records")
    op.execute("drop function reject_pending_authority_idempotency()")
    op.execute("drop function reject_authority_idempotency_truncate()")
    op.execute("drop function guard_authority_idempotency_record()")
    op.drop_table("authority_idempotency_records")
