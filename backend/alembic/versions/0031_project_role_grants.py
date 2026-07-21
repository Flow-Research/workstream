"""add independent project-role grants and qualification evidence

Revision ID: 0031_project_role_grants
Revises: 0030_artifact_verification
Create Date: 2026-07-21
"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0031_project_role_grants"
down_revision = "0030_artifact_verification"
branch_labels = depends_on = None

_ACTIONS = (
    ("project.contributor_candidate.list", "project.role_grant.manage"),
    ("project_role_grant.list", "project.role_grant.read"),
    ("project_role_grant.read", "project.role_grant.read"),
    ("project_role_grant.issue", "project.role_grant.manage"),
    ("project_role_grant.revoke", "project.role_grant.manage"),
)
_DENIALS = (
    "project_role_grant_already_revoked",
    "project_role_grant_replay_state_changed",
)
_STRIP = (
    "(E' \\t\\n\\r\\f\\013'||chr(28)||chr(29)||chr(30)||chr(31)||chr(133)||chr(160)"
    "||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)"
    "||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)"
    "||chr(8239)||chr(8287)||chr(12288))"
)


def _constraint_definition(name: str) -> str:
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


def _replace_constraint(name: str, definition: str) -> None:
    op.drop_constraint(name, "audit_events", type_="check")
    op.execute(f"alter table audit_events add constraint ck_audit_events_{name} {definition}")


def _replace_action_registry(*, add: bool) -> None:
    definition = _constraint_definition("authorization_action_evidence")
    marker = (
        "(((action_id)::text = 'actor.service.provision'::text) AND "
        "((permission_id)::text = 'actor.service.provision'::text))"
    )
    additions = " OR ".join(
        f"(((action_id)::text = '{action}'::text) AND ((permission_id)::text = '{permission}'::text))"
        for action, permission in _ACTIONS
    )
    if add:
        if definition.count(marker) != 2 or any(action in definition for action, _ in _ACTIONS):
            raise RuntimeError("unexpected authority action registry definition")
        definition = definition.replace(marker, marker + " OR " + additions)
    else:
        suffix = " OR " + additions
        if definition.count(suffix) != 2:
            raise RuntimeError("unexpected authority action registry definition")
        definition = definition.replace(suffix, "")
    _replace_constraint("authorization_action_evidence", definition)


def _replace_authority_registries(*, add: bool) -> None:
    definition = _constraint_definition("authority_registries")
    if add:
        obsolete = re.compile(
            r"\s+OR \(\(\(event_type\)::text = 'ProjectRoleGrantReplaced'::text\) "
            r"AND \(reason = 'authority_replacement'::text\)\)"
        )
        if len(tuple(obsolete.finditer(definition))) != 1:
            raise RuntimeError("unexpected authority registry definition")
        definition = obsolete.sub("", definition, count=1)
        marker = "('identity_link_conflict'::character varying)::text"
        additions = ", ".join(f"('{value}'::character varying)::text" for value in _DENIALS)
        if definition.count(marker) != 1 or any(value in definition for value in _DENIALS):
            raise RuntimeError("unexpected authority denial registry definition")
        definition = definition.replace(marker, marker + ", " + additions)
    else:
        additions = ", " + ", ".join(f"('{value}'::character varying)::text" for value in _DENIALS)
        if definition.count(additions) != 1:
            raise RuntimeError("unexpected authority denial registry definition")
        definition = definition.replace(additions, "")
        marker = (
            "(((event_type)::text = 'ProjectRoleGrantIssued'::text) AND "
            "(reason = 'authority_assignment'::text))"
        )
        restored = (
            marker + " OR (((event_type)::text = 'ProjectRoleGrantReplaced'::text) "
            "AND (reason = 'authority_replacement'::text))"
        )
        if definition.count(marker) != 1:
            raise RuntimeError("unexpected authority registry definition")
        definition = definition.replace(marker, restored, 1)
    _replace_constraint("authority_registries", definition)


def _function_definition(name: str) -> str:
    return (
        op.get_bind()
        .execute(sa.text("select pg_get_functiondef(cast(:name as regproc))"), {"name": name})
        .scalar_one()
    )


def _replace_audit_functions(*, add: bool) -> None:
    facts = _function_definition("authority_event_facts_are_safe")
    linked = _function_definition("validate_linked_authority_event")
    old_roles = "array['submitter','reviewer','both']"
    new_roles = "array['submitter','reviewer','adjudicator']"
    replacement_case = re.compile(
        r"\s*when 'ProjectRoleGrantReplaced' then return.*?;(?=\s+when)", re.S
    )
    if add:
        if old_roles not in facts or len(replacement_case.findall(facts)) != 1:
            raise RuntimeError("unexpected authority fact validator definition")
        facts = facts.replace(old_roles, new_roles)
        facts = replacement_case.sub("", facts, count=1)
        linked_pairs = (
            ("'ProjectRoleGrantIssued','ProjectRoleGrantReplaced'", "'ProjectRoleGrantIssued'"),
        )
    else:
        if new_roles not in facts or replacement_case.search(facts):
            raise RuntimeError("unexpected authority fact validator definition")
        facts = facts.replace(new_roles, old_roles)
        marker = "when 'ProjectRoleQualificationSnapshotCaptured' then"
        restored = (
            "when 'ProjectRoleGrantReplaced' then return\n"
            "              authority_grant_facts_are_safe(before_state,array['submitter','reviewer','both'],'active',true,envelope_project_id)\n"
            "              and authority_grant_facts_are_safe(after_state,array['submitter','reviewer','both'],'active',true,envelope_project_id)\n"
            "              and before_state->>'scope_id'=after_state->>'scope_id';\n            "
        )
        if facts.count(marker) != 1:
            raise RuntimeError("unexpected authority fact validator definition")
        facts = facts.replace(marker, restored + marker)
        linked_pairs = (
            ("'ProjectRoleGrantIssued'", "'ProjectRoleGrantIssued','ProjectRoleGrantReplaced'"),
        )
    changed = 0
    for old, new in linked_pairs:
        count = linked.count(old)
        if count:
            linked = linked.replace(old, new)
            changed += count
    if changed != 3:
        raise RuntimeError("unexpected linked authority validator definition")
    op.execute(facts)
    op.execute(linked)


def _create_helpers() -> None:
    statements = (
        r"""
        create function project_role_reference_token_is_safe(value text) returns boolean
        language sql immutable strict as $$
          select value ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$' and strpos(value, '://')=0
        $$
        """,
        r"""
        create function project_role_reference_array_is_safe(value jsonb, uuid_only boolean)
        returns boolean language sql immutable strict as $$
          select jsonb_typeof(value)='array' and jsonb_array_length(value)<=20
            and not exists (
              select 1 from jsonb_array_elements(value) item
              where jsonb_typeof(item)<>'string' or
                case when uuid_only then not (item #>> '{}') ~
                  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                else not project_role_reference_token_is_safe(item #>> '{}') end
            )
        $$
        """,
        r"""
        create function project_role_availability_is_safe(value jsonb) returns boolean
        language sql immutable strict as $$
          select jsonb_typeof(value)='object' and
            (select count(*)=3 from jsonb_object_keys(value)) and
            value ?& array['availability','reference_ids','unavailable_reason'] and
            project_role_reference_array_is_safe(value->'reference_ids',false) and (
              (value->>'availability'='available' and jsonb_array_length(value->'reference_ids')>0
                and value->'unavailable_reason'='null'::jsonb) or
              (value->>'availability'='unavailable' and jsonb_array_length(value->'reference_ids')=0
                and value->>'unavailable_reason' in ('not_collected','source_unavailable','no_record'))
            )
        $$
        """,
        r"""
        create function project_role_reason_is_safe(value text) returns boolean
        language plpgsql immutable strict as $$
        declare point integer; index integer;
        begin
          if octet_length(value) not between 1 and 500 or value <> btrim(value, """
        + _STRIP
        + r""") then return false; end if;
          for index in 1..char_length(value) loop
            point := ascii(substr(value,index,1));
            if point between 0 and 31 or point between 127 and 159
               or point in (173,1536,1537,1538,1539,1757,1807,6068,6069,6070,6071,6072,6073,6158,8203,8204,8205,8206,8207,8234,8235,8236,8237,8238,8288,8289,8290,8291,8292,8293,8294,8295,8296,8297,8298,8299,8300,8301,8302,8303,65279) then
              return false;
            end if;
          end loop;
          return true;
        end $$
        """,
    )
    for statement in statements:
        op.execute(statement)


def _create_history_guards() -> None:
    statements = (
        """
        create function guard_project_role_snapshot_history() returns trigger language plpgsql as $$
        begin
          if tg_op='INSERT' then new.captured_at := clock_timestamp(); return new; end if;
          raise exception 'project-role qualification snapshots are immutable' using errcode='55000';
        end $$
        """,
        """
        create trigger trg_project_role_qualification_snapshots_immutable
        before insert or update or delete on project_role_qualification_snapshots
        for each row execute function guard_project_role_snapshot_history()
        """,
        """
        create function guard_project_role_grant_history() returns trigger language plpgsql as $$
        begin
          if tg_op='INSERT' then new.granted_at := clock_timestamp(); return new; end if;
          if tg_op='DELETE' then raise exception 'project-role grants are immutable history' using errcode='55000'; end if;
          if (new.id,new.project_id,new.actor_profile_id,new.role,new.grant_method,
              new.qualification_snapshot_id,new.granted_by_actor_profile_id,
              new.granted_by_admin_role_grant_id,new.grant_reason,new.granted_at)
             is distinct from
             (old.id,old.project_id,old.actor_profile_id,old.role,old.grant_method,
              old.qualification_snapshot_id,old.granted_by_actor_profile_id,
              old.granted_by_admin_role_grant_id,old.grant_reason,old.granted_at)
             or old.status<>'active' or old.version<>1 or new.status<>'revoked' or new.version<>2
             or new.revoked_by_actor_profile_id is null or new.revoked_by_admin_role_grant_id is null
             or new.revoked_reason is null then
            raise exception 'invalid project-role grant history transition' using errcode='23514';
          end if;
          new.revoked_at := clock_timestamp();
          return new;
        end $$
        """,
        """
        create trigger trg_project_role_grants_history before insert or update or delete on project_role_grants
        for each row execute function guard_project_role_grant_history()
        """,
        """
        create function reject_project_role_history_truncate() returns trigger language plpgsql as $$
        begin raise exception 'project-role history cannot be truncated' using errcode='55000'; end $$
        """,
        """
        create trigger trg_project_role_snapshots_reject_truncate before truncate
        on project_role_qualification_snapshots execute function reject_project_role_history_truncate()
        """,
        """
        create trigger trg_project_role_grants_reject_truncate before truncate
        on project_role_grants execute function reject_project_role_history_truncate()
        """,
    )
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    """Install exact-role history only after proving no replacement-era state exists."""
    bind = op.get_bind()
    bind.execute(
        sa.text("lock table audit_events, authority_idempotency_records in access exclusive mode")
    )
    blocked = bind.execute(
        sa.text("""
      select exists(select 1 from audit_events where event_domain='authority' and (
        before_facts->>'role'='both' or after_facts->>'role'='both' or
        before_facts::jsonb ? 'replaced_grant_id' or after_facts::jsonb ? 'replaced_grant_id' or
        event_type='ProjectRoleGrantReplaced' or reason='authority_replacement')) or
      exists(select 1 from authority_idempotency_records where operation in
        ('project_role_grant.issue','project_role_grant.revoke'))
    """)
    ).scalar_one()
    if blocked:
        raise RuntimeError("cannot safely upgrade replacement-era project-role evidence")
    _create_helpers()
    op.create_table(
        "project_role_qualification_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "actor_profile_id", sa.String(36), sa.ForeignKey("actor_profiles.id"), nullable=False
        ),
        sa.Column("requested_role", sa.String(24), nullable=False),
        sa.Column("skills_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("reputation_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("prior_project_work_refs", postgresql.JSONB(), nullable=False),
        sa.Column("external_expertise_refs", postgresql.JSONB(), nullable=False),
        sa.Column(
            "captured_by_actor_profile_id",
            sa.String(36),
            sa.ForeignKey("actor_profiles.id"),
            nullable=False,
        ),
        sa.Column(
            "captured_by_admin_role_grant_id",
            sa.Uuid(),
            sa.ForeignKey("admin_role_grants.id"),
            nullable=False,
        ),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("requested_role in ('submitter','reviewer','adjudicator')", name="role"),
        sa.CheckConstraint(
            "project_role_availability_is_safe(skills_snapshot) and project_role_availability_is_safe(reputation_snapshot)",
            name="availability",
        ),
        sa.CheckConstraint(
            "project_role_reference_array_is_safe(prior_project_work_refs,true)",
            name="prior_work_refs",
        ),
        sa.CheckConstraint(
            "project_role_reference_array_is_safe(external_expertise_refs,false)",
            name="external_expertise_refs",
        ),
        sa.UniqueConstraint(
            "id", "actor_profile_id", "project_id", "requested_role", name="grant_reference"
        ),
    )
    op.create_index(
        "ix_project_role_qualification_snapshots_history",
        "project_role_qualification_snapshots",
        ["project_id", "actor_profile_id", "requested_role", "captured_at"],
    )
    op.create_table(
        "project_role_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "actor_profile_id", sa.String(36), sa.ForeignKey("actor_profiles.id"), nullable=False
        ),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("grant_method", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("qualification_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column(
            "granted_by_actor_profile_id",
            sa.String(36),
            sa.ForeignKey("actor_profiles.id"),
            nullable=False,
        ),
        sa.Column(
            "granted_by_admin_role_grant_id",
            sa.Uuid(),
            sa.ForeignKey("admin_role_grants.id"),
            nullable=False,
        ),
        sa.Column("grant_reason", sa.Text(), nullable=False),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revoked_by_actor_profile_id", sa.String(36), sa.ForeignKey("actor_profiles.id")),
        sa.Column(
            "revoked_by_admin_role_grant_id", sa.Uuid(), sa.ForeignKey("admin_role_grants.id")
        ),
        sa.Column("revoked_reason", sa.Text()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role in ('submitter','reviewer','adjudicator')", name="role"),
        sa.CheckConstraint("grant_method='manual'", name="grant_method"),
        sa.CheckConstraint(
            "project_role_reason_is_safe(grant_reason) and (revoked_reason is null or project_role_reason_is_safe(revoked_reason))",
            name="reason",
        ),
        sa.CheckConstraint(
            "(status='active' and version=1 and revoked_by_actor_profile_id is null and revoked_by_admin_role_grant_id is null and revoked_reason is null and revoked_at is null) or (status='revoked' and version=2 and revoked_by_actor_profile_id is not null and revoked_by_admin_role_grant_id is not null and revoked_reason is not null and revoked_at is not null)",
            name="lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["qualification_snapshot_id", "actor_profile_id", "project_id", "role"],
            [
                "project_role_qualification_snapshots.id",
                "project_role_qualification_snapshots.actor_profile_id",
                "project_role_qualification_snapshots.project_id",
                "project_role_qualification_snapshots.requested_role",
            ],
            name="qualification_ownership",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_project_role_grants_active_exact_role",
        "project_role_grants",
        ["project_id", "actor_profile_id", "role"],
        unique=True,
        postgresql_where=sa.text("status='active'"),
    )
    op.create_index(
        "ix_project_role_grants_project_actor_role_status",
        "project_role_grants",
        ["project_id", "actor_profile_id", "role", "status"],
    )
    op.create_index(
        "ix_project_role_grants_actor_role_status",
        "project_role_grants",
        ["actor_profile_id", "role", "status"],
    )
    _create_history_guards()
    _replace_authority_registries(add=True)
    _replace_action_registry(add=True)
    _replace_audit_functions(add=True)


def downgrade() -> None:
    """Restore 0030 only when no 10A-owned truth or evidence exists."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table project_role_grants, project_role_qualification_snapshots, audit_events in access exclusive mode"
        )
    )
    blocked = bind.execute(
        sa.text("""
      select exists(select 1 from project_role_grants) or
      exists(select 1 from project_role_qualification_snapshots) or
      exists(select 1 from audit_events where event_domain='authority' and (
        before_facts->>'role'='adjudicator' or after_facts->>'role'='adjudicator' or
        action_id in ('project.contributor_candidate.list','project_role_grant.list',
          'project_role_grant.read','project_role_grant.issue','project_role_grant.revoke') or
        denial_code in ('project_role_grant_already_revoked','project_role_grant_replay_state_changed')))
    """)
    ).scalar_one()
    if blocked:
        raise RuntimeError("cannot downgrade project-role grant evidence")
    _replace_audit_functions(add=False)
    _replace_action_registry(add=False)
    _replace_authority_registries(add=False)
    op.drop_table("project_role_grants")
    op.drop_table("project_role_qualification_snapshots")
    op.execute("drop function guard_project_role_grant_history()")
    op.execute("drop function guard_project_role_snapshot_history()")
    op.execute("drop function reject_project_role_history_truncate()")
    op.execute("drop function project_role_availability_is_safe(jsonb)")
    op.execute("drop function project_role_reference_array_is_safe(jsonb,boolean)")
    op.execute("drop function project_role_reference_token_is_safe(text)")
    op.execute("drop function project_role_reason_is_safe(text)")
