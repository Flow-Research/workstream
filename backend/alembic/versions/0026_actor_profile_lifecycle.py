"""repair actor lifecycle provenance and authority evidence

Revision ID: 0026_actor_profile_lifecycle
Revises: 0025_artifact_store_v2
Create Date: 2026-07-18
"""

from __future__ import annotations

from alembic import op
import re
import sqlalchemy as sa

revision = "0026_actor_profile_lifecycle"
down_revision = "0025_artifact_store_v2"
branch_labels = depends_on = None

_NEW_DENIAL_CODES = (
    "identity_link_already_revoked",
    "identity_link_not_revoked",
)
# Historical capture of str.strip() across the supported Python runtimes.
_PYTHON_STRIP_CHARACTERS_SQL = (
    "(E' \\t\\n\\r\\f\\013'"
    "||chr(28)||chr(29)||chr(30)||chr(31)||chr(133)||chr(160)||chr(5760)"
    "||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)"
    "||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)"
    "||chr(8233)||chr(8239)||chr(8287)||chr(12288))"
)


def _replace_denial_registry(*, add: bool) -> None:
    """Extend the exact prior registry without coupling history to live constants."""
    bind = op.get_bind()
    name = "ck_audit_events_authority_registries"
    definition = bind.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass and conname=:name"
        ),
        {"name": name},
    ).scalar_one()
    cast = r"(?P<cast>::(?:character varying|text))?"
    marker = re.compile(rf"'identity_link_conflict'{cast}")
    if add:
        matches = tuple(marker.finditer(definition))
        if len(matches) != 1 or any(value in definition for value in _NEW_DENIAL_CODES):
            raise RuntimeError("unexpected authority denial registry definition")
        match = matches[0]
        suffix = match.group("cast") or ""
        inserted = ", ".join(f"'{value}'{suffix}" for value in _NEW_DENIAL_CODES)
        replacement = definition[: match.end()] + ", " + inserted + definition[match.end() :]
    else:
        first = (
            r"(?:\('identity_link_already_revoked'::character varying\)::text|"
            r"'identity_link_already_revoked'(?:::(?:character varying|text))?)"
        )
        second = (
            r"(?:\('identity_link_not_revoked'::character varying\)::text|"
            r"'identity_link_not_revoked'(?:::(?:character varying|text))?)"
        )
        removal = re.compile(
            rf",\s*{first}\s*,\s*{second}"
        )
        if len(tuple(removal.finditer(definition))) != 1:
            raise RuntimeError("unexpected authority denial registry definition")
        replacement = removal.sub("", definition, count=1)
    op.drop_constraint("authority_registries", "audit_events", type_="check")
    op.execute(f"alter table audit_events add constraint {name} {replacement}")


def _replace_linked_authority_guard(*, lifecycle_reactivation: bool) -> None:
    projection_branch = (
        "record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke',"
        "'actor_identity_link.revoke','actor_identity_link.reactivate')"
        if lifecycle_reactivation
        else "record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke')"
    )
    if lifecycle_reactivation:
        direction_checks = """
               or (record_row.operation in ('admin_role_grant.issue','actor_profile.reactivate','actor_identity_link.reactivate') and
                   (new.before_facts::jsonb <> '{"effective": false}'::jsonb or new.after_facts::jsonb <> '{"effective": true}'::jsonb))
               or (record_row.operation not in ('admin_role_grant.issue','actor_profile.reactivate','actor_identity_link.reactivate') and
                   (new.before_facts::jsonb <> '{"effective": true}'::jsonb or new.after_facts::jsonb <> '{"effective": false}'::jsonb))
        """
    else:
        direction_checks = """
               or (record_row.operation='admin_role_grant.issue' and
                   (new.before_facts::jsonb <> '{"effective": false}'::jsonb or new.after_facts::jsonb <> '{"effective": true}'::jsonb))
               or (record_row.operation='admin_role_grant.revoke' and
                   (new.before_facts::jsonb <> '{"effective": true}'::jsonb or new.after_facts::jsonb <> '{"effective": false}'::jsonb))
               or (not (record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke')) and
                   (new.before_facts::jsonb <> '{"effective": true}'::jsonb or new.after_facts::jsonb <> '{"effective": false}'::jsonb))
        """
    op.execute(
        f"""
        create or replace function validate_linked_authority_event() returns trigger
        language plpgsql as $$
        declare record_row authority_idempotency_records%rowtype;
                cause_row audit_events%rowtype; expected_permission text;
                expected_resource text; expected_invalidation_resource text;
                expected_invalidation_id text; valid_success boolean;
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
          if record_row.status <> 'pending' then raise exception 'committed authority idempotency is closed' using errcode='23514'; end if;
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
          if new.permission_id <> expected_permission or new.resource_id is null then
            raise exception 'authority event does not match operation' using errcode='23514';
          end if;
          if new.event_type='AuthorityInvalidationRequested' then
            select * into cause_row from audit_events where id=new.invalidation_cause_event_id;
            expected_invalidation_resource := case when {projection_branch} then 'actor_profile' else expected_resource end;
            expected_invalidation_id := case when {projection_branch} then cause_row.target_actor_ref else cause_row.resource_id end;
            if not found or cause_row.idempotency_reference is distinct from record_row.id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.resource_type is distinct from expected_resource
               or new.resource_type is distinct from expected_invalidation_resource
               or new.resource_id is distinct from expected_invalidation_id
               or new.invalidation_target_kind is distinct from expected_invalidation_resource
               or new.invalidation_target_ref is distinct from expected_invalidation_id
               or cause_row.target_ref_kind is distinct from cause_row.resource_type
               or cause_row.target_ref_id is distinct from cause_row.resource_id
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.project_id is distinct from new.project_id
               or new.entity_type <> 'authority_invalidation' or new.entity_id <> new.id
               or ({projection_branch} and (cause_row.target_actor_ref_kind <> 'actor_profile' or cause_row.target_actor_ref is null))
               {direction_checks}
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
            if new.resource_type <> expected_resource or new.entity_type <> expected_resource
               or new.entity_id <> new.resource_id or new.target_ref_kind is distinct from expected_resource
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null or new.invalidation_target_ref is not null
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


def _replace_lifecycle_guards(*, upgraded: bool) -> None:
    if upgraded:
        profile_function = """
        create or replace function guard_actor_profile_history() returns trigger language plpgsql as $$
        begin
          if tg_op='DELETE' then raise exception 'actor profiles are immutable history' using errcode='55000'; end if;
          if (new.id,new.actor_kind,new.provisioning_method,new.created_by,new.created_at)
             is distinct from (old.id,old.actor_kind,old.provisioning_method,old.created_by,old.created_at) then
            raise exception 'actor profile identity is immutable' using errcode='55000';
          end if;
          if old.status='deactivated' and new.status <> 'deactivated' then
            raise exception 'deactivated actor is terminal' using errcode='23514';
          end if;
          if new.status = old.status and
             (new.suspended_by,new.suspended_at,new.suspension_reason,new.reactivated_by,new.reactivated_at,new.reactivation_reason,
              new.deactivated_by,new.deactivated_at,new.deactivation_reason) is distinct from
             (old.suspended_by,old.suspended_at,old.suspension_reason,old.reactivated_by,old.reactivated_at,old.reactivation_reason,
              old.deactivated_by,old.deactivated_at,old.deactivation_reason) then
            raise exception 'actor lifecycle attribution requires a transition' using errcode='23514';
          end if;
          if old.status='active' and new.status='suspended' and
             (new.reactivated_by,new.reactivated_at,new.reactivation_reason,new.deactivated_by,new.deactivated_at,new.deactivation_reason)
             is distinct from
             (old.reactivated_by,old.reactivated_at,old.reactivation_reason,old.deactivated_by,old.deactivated_at,old.deactivation_reason) then
            raise exception 'invalid actor suspension attribution' using errcode='23514';
          end if;
          if old.status='suspended' and new.status='active' and
             ((new.suspended_by,new.suspended_at,new.suspension_reason) is distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from
                 (old.reactivated_by,old.reactivated_at,old.reactivation_reason)
              or (new.deactivated_by,new.deactivated_at,new.deactivation_reason) is distinct from
                 (old.deactivated_by,old.deactivated_at,old.deactivation_reason)) then
            raise exception 'invalid actor reactivation attribution' using errcode='23514';
          end if;
          if new.status='deactivated' and old.status in ('active','suspended') and
             (new.suspended_by,new.suspended_at,new.suspension_reason,new.reactivated_by,new.reactivated_at,new.reactivation_reason)
             is distinct from
             (old.suspended_by,old.suspended_at,old.suspension_reason,old.reactivated_by,old.reactivated_at,old.reactivation_reason) then
            raise exception 'invalid actor deactivation attribution' using errcode='23514';
          end if;
          if new.status <> old.status and not (
             (old.status='active' and new.status in ('suspended','deactivated')) or
             (old.status='suspended' and new.status in ('active','deactivated'))) then
            raise exception 'invalid actor lifecycle transition' using errcode='23514';
          end if;
          new.updated_at = statement_timestamp(); return new;
        end $$
        """
        link_function = """
        create or replace function guard_actor_identity_link_history() returns trigger language plpgsql as $$
        begin
          if tg_op='DELETE' then raise exception 'actor identity links are immutable history' using errcode='55000'; end if;
          if (new.id,new.actor_profile_id,new.issuer,new.subject,new.subject_kind,new.linked_by,new.linked_at)
             is distinct from (old.id,old.actor_profile_id,old.issuer,old.subject,old.subject_kind,old.linked_by,old.linked_at) then
            raise exception 'actor identity link anchor is immutable' using errcode='55000';
          end if;
          if new.status=old.status and
             (new.revoked_by,new.revoked_at,new.revoked_reason,new.reactivated_by,new.reactivated_at,new.reactivation_reason)
             is distinct from
             (old.revoked_by,old.revoked_at,old.revoked_reason,old.reactivated_by,old.reactivated_at,old.reactivation_reason) then
            raise exception 'identity link attribution requires a transition' using errcode='23514';
          end if;
          if old.status='active' and new.status='revoked' and
             (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is distinct from
             (old.reactivated_by,old.reactivated_at,old.reactivation_reason) then
            raise exception 'invalid identity link revocation attribution' using errcode='23514';
          end if;
          if old.status='revoked' and new.status='active' and
             ((new.revoked_by,new.revoked_at,new.revoked_reason) is distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from
                 (old.reactivated_by,old.reactivated_at,old.reactivation_reason)) then
            raise exception 'invalid identity link reactivation attribution' using errcode='23514';
          end if;
          if new.status <> old.status and not (
             (old.status='active' and new.status='revoked') or
             (old.status='revoked' and new.status='active')) then
            raise exception 'invalid identity link lifecycle transition' using errcode='23514';
          end if;
          return new;
        end $$
        """
    else:
        profile_function = """
        create or replace function guard_actor_profile_history() returns trigger language plpgsql as $$
        begin
          if tg_op='DELETE' then raise exception 'actor profiles are immutable history' using errcode='55000'; end if;
          if (new.id,new.actor_kind,new.provisioning_method,new.created_by,new.created_at)
             is distinct from (old.id,old.actor_kind,old.provisioning_method,old.created_by,old.created_at) then
            raise exception 'actor profile identity is immutable' using errcode='55000';
          end if;
          if old.status='deactivated' and new.status <> 'deactivated' then
            raise exception 'deactivated actor is terminal' using errcode='23514';
          end if;
          new.updated_at = statement_timestamp(); return new;
        end $$
        """
        link_function = """
        create or replace function guard_actor_identity_link_history() returns trigger language plpgsql as $$
        begin
          if tg_op='DELETE' then raise exception 'actor identity links are immutable history' using errcode='55000'; end if;
          if (new.id,new.actor_profile_id,new.issuer,new.subject,new.subject_kind,new.linked_by,new.linked_at)
             is distinct from (old.id,old.actor_profile_id,old.issuer,old.subject,old.subject_kind,old.linked_by,old.linked_at) then
            raise exception 'actor identity link anchor is immutable' using errcode='55000';
          end if;
          return new;
        end $$
        """
    op.execute(profile_function)
    op.execute(link_function)


def _dirty_lifecycle_rows(bind) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "select exists(select 1 from actor_identity_links where "
                "(reactivated_by is null)::int + (reactivated_at is null)::int + "
                "(reactivation_reason is null)::int not in (0,3)) or exists("
                "select 1 from actor_profiles where "
                f"(suspension_reason is not null and (suspension_reason<>btrim(suspension_reason, {_PYTHON_STRIP_CHARACTERS_SQL}) or octet_length(suspension_reason) not between 1 and 500)) or "
                f"(deactivation_reason is not null and (deactivation_reason<>btrim(deactivation_reason, {_PYTHON_STRIP_CHARACTERS_SQL}) or octet_length(deactivation_reason) not between 1 and 500))) or exists("
                "select 1 from actor_identity_links where "
                f"(revoked_reason is not null and (revoked_reason<>btrim(revoked_reason, {_PYTHON_STRIP_CHARACTERS_SQL}) or octet_length(revoked_reason) not between 1 and 500)) or "
                f"(reactivation_reason is not null and (reactivation_reason<>btrim(reactivation_reason, {_PYTHON_STRIP_CHARACTERS_SQL}) or octet_length(reactivation_reason) not between 1 and 500)))"
            )
        ).scalar_one()
    )


def upgrade() -> None:
    """Install truthful profile lifecycle provenance and evidence guards."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table actor_profiles, actor_identity_links, audit_events in access exclusive mode"))
    if _dirty_lifecycle_rows(bind):
        raise RuntimeError("cannot adopt dirty actor lifecycle rows")

    op.add_column("actor_profiles", sa.Column("reactivated_by", sa.String(120)))
    op.add_column("actor_profiles", sa.Column("reactivated_at", sa.DateTime(timezone=True)))
    op.add_column("actor_profiles", sa.Column("reactivation_reason", sa.String(500)))
    op.create_check_constraint(
        op.f("ck_actor_profiles_reactivation_fields"),
        "actor_profiles",
        "(reactivated_by is null and reactivated_at is null and reactivation_reason is null) or "
        "(reactivated_by is not null and reactivated_at is not null and reactivation_reason is not null)",
    )
    op.create_check_constraint(
        op.f("ck_actor_profiles_lifecycle_reason_bounds"),
        "actor_profiles",
        f"(suspension_reason is null or (suspension_reason=btrim(suspension_reason, {_PYTHON_STRIP_CHARACTERS_SQL}) and octet_length(suspension_reason) between 1 and 500)) and "
        f"(reactivation_reason is null or (reactivation_reason=btrim(reactivation_reason, {_PYTHON_STRIP_CHARACTERS_SQL}) and octet_length(reactivation_reason) between 1 and 500)) and "
        f"(deactivation_reason is null or (deactivation_reason=btrim(deactivation_reason, {_PYTHON_STRIP_CHARACTERS_SQL}) and octet_length(deactivation_reason) between 1 and 500))",
    )
    op.create_check_constraint(
        op.f("ck_actor_identity_links_reactivation_fields"),
        "actor_identity_links",
        "(reactivated_by is null and reactivated_at is null and reactivation_reason is null) or "
        "(reactivated_by is not null and reactivated_at is not null and reactivation_reason is not null)",
    )
    op.create_check_constraint(
        op.f("ck_actor_identity_links_lifecycle_reason_bounds"),
        "actor_identity_links",
        f"(revoked_reason is null or (revoked_reason=btrim(revoked_reason, {_PYTHON_STRIP_CHARACTERS_SQL}) and octet_length(revoked_reason) between 1 and 500)) and "
        f"(reactivation_reason is null or (reactivation_reason=btrim(reactivation_reason, {_PYTHON_STRIP_CHARACTERS_SQL}) and octet_length(reactivation_reason) between 1 and 500))",
    )
    _replace_denial_registry(add=True)
    _replace_linked_authority_guard(lifecycle_reactivation=True)
    _replace_lifecycle_guards(upgraded=True)


def downgrade() -> None:
    """Restore 0025 only before any forward lifecycle evidence exists."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table actor_profiles, actor_identity_links, audit_events in access exclusive mode"))
    blocked = bind.execute(
        sa.text(
            "select exists(select 1 from actor_profiles where reactivated_by is not null or reactivated_at is not null or reactivation_reason is not null) "
            "or exists(select 1 from audit_events where event_domain='authority' and ("
            "event_type in ('ActorProfileReactivated','ActorIdentityLinkReactivated') or "
            "denial_code in ('identity_link_already_revoked','identity_link_not_revoked')))"
        )
    ).scalar_one()
    if blocked:
        raise RuntimeError("cannot downgrade actor lifecycle evidence")
    _replace_lifecycle_guards(upgraded=False)
    _replace_linked_authority_guard(lifecycle_reactivation=False)
    _replace_denial_registry(add=False)
    op.drop_constraint(op.f("ck_actor_identity_links_lifecycle_reason_bounds"), "actor_identity_links", type_="check")
    op.drop_constraint(op.f("ck_actor_identity_links_reactivation_fields"), "actor_identity_links", type_="check")
    op.drop_constraint(op.f("ck_actor_profiles_lifecycle_reason_bounds"), "actor_profiles", type_="check")
    op.drop_constraint(op.f("ck_actor_profiles_reactivation_fields"), "actor_profiles", type_="check")
    op.drop_column("actor_profiles", "reactivation_reason")
    op.drop_column("actor_profiles", "reactivated_at")
    op.drop_column("actor_profiles", "reactivated_by")
