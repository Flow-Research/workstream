"""admit the exact two-event project-role issue evidence envelope

Revision ID: 0034_project_role_issue_evidence
Revises: 0033_authorization_read_rate
Create Date: 2026-07-24
"""

from __future__ import annotations

import hashlib
import re

from alembic import op
import sqlalchemy as sa


revision = "0034_project_role_issue_evidence"
down_revision = "0033_authorization_read_rate"
branch_labels = depends_on = None

_PREDECESSOR_GUARD_SHA256 = "fe4d302e7405e79d4ca0f5731275f589f2680da5d4ebf033f98d028214671498"
_PREDECESSOR_LINKED_SHA256 = "a05288dc0192e2f984a6e1592d086879bbe32c20cfba0d284a2c13fce6c7e506"
_PREDECESSOR_FACTS_SHA256 = "ee5e1bd8d2958ff60238e9200acd7ba226bf64f191f515881dc5741c7f36d9bb"
_FORWARD_GUARD_SHA256 = "4ff567e26aa28be36f28e4908039d0d4c0e9d1d8e6226dfb4d28c8b0f1523a56"
_FORWARD_LINKED_SHA256 = "e5d9dc01a65c3865267c89e79e6eedcf270ab5c559d424a593c939e3693f154e"
_FORWARD_FACTS_SHA256 = "202354d75f8fc6b60e8f3bedfd8eafcf75aa24f682c1ef4762abf81fa74a1e5d"
_FACT_CONSTRAINT_SHA256 = "c6f99a1a9ef6cc59fe52af6a117a5265cda8daa9c7fa084ed2ff8bdad851ae2f"
_PREDECESSOR_PRIVACY_SHA256 = "b76a5df89d66215f6aaba6d03ee0322497cfba99c3072404d7b06f742e71b56e"
_FORWARD_PRIVACY_SHA256 = "c02c0edccf921bbacbeff81524deb6d57cad6273784029d647c1df02ab18ed26"
_TRIGGER_SHA256 = {
    "authority_idempotency_guard": "84da74f8180fd5023b7364840b659a3fe781752c937c12dea6b2411eba5d7874",
    "audit_events_validate_idempotency": "524d24197c96ad05cbaecc867a4e5cdd2ee9e33e3a60380466e280a253a397bf",
}

_RESOURCE_MARKERS = (
    ("'project'::character varying, 'project_role_grant'::character varying", "'project'::character varying, 'qualification_snapshot'::character varying, 'project_role_grant'::character varying"),
    ("('project'::character varying)::text, ('project_role_grant'::character varying)::text", "('project'::character varying)::text, ('qualification_snapshot'::character varying)::text, ('project_role_grant'::character varying)::text"),
)

_LINKED_VALID_MARKER = (
    "'ProjectRoleGrantIssued','ProjectRoleGrantRevoked',"
)
_LINKED_VALID_FORWARD = (
    "'ProjectRoleQualificationSnapshotCaptured','ProjectRoleGrantIssued',"
    "'ProjectRoleGrantRevoked',"
)
_LINKED_BRANCH_MARKER = "          if new.event_type='AuthorityInvalidationRequested' then"
_LINKED_ISSUE_BRANCH = """          if new.event_type='ProjectRoleQualificationSnapshotCaptured' then
            if record_row.operation <> 'project_role_grant.issue'
               or new.resource_type <> 'qualification_snapshot'
               or new.entity_type <> 'qualification_snapshot'
               or new.entity_id <> new.resource_id
               or new.target_ref_kind is distinct from 'qualification_snapshot'
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null
               or new.invalidation_target_ref is not null
               or exists(select 1 from audit_events where idempotency_reference=record_row.id) then
              raise exception 'invalid project role qualification evidence' using errcode='23514';
            end if;
          elsif record_row.operation='project_role_grant.issue'
                and new.event_type='ProjectRoleGrantIssued' then
            select * into cause_row from audit_events
            where idempotency_reference=record_row.id
              and event_type='ProjectRoleQualificationSnapshotCaptured';
            if not found
               or (select count(*) from audit_events where idempotency_reference=record_row.id) <> 1
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.project_id is distinct from new.project_id
               or cause_row.target_actor_ref_kind is distinct from new.target_actor_ref_kind
               or cause_row.target_actor_ref is distinct from new.target_actor_ref
               or cause_row.matched_grant_id is distinct from new.matched_grant_id
               or new.resource_type <> 'project_role_grant'
               or new.entity_type <> 'project_role_grant'
               or new.entity_id <> new.resource_id
               or new.target_ref_kind is distinct from 'project_role_grant'
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null
               or new.invalidation_target_ref is not null then
              raise exception 'invalid project role issue evidence' using errcode='23514';
            end if;
          elsif record_row.operation='project_role_grant.revoke'
                and new.event_type='AuthorityInvalidationRequested' then
            select * into cause_row from audit_events where id=new.invalidation_cause_event_id;
            if not found or cause_row.event_type <> 'ProjectRoleGrantRevoked'
               or cause_row.idempotency_reference is distinct from record_row.id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.project_id is distinct from new.project_id
               or cause_row.target_actor_ref_kind is distinct from 'actor_profile'
               or cause_row.target_actor_ref_kind is distinct from new.target_actor_ref_kind
               or cause_row.target_actor_ref is distinct from new.target_actor_ref
               or cause_row.resource_type <> 'project_role_grant'
               or cause_row.target_ref_kind <> 'project_role_grant'
               or cause_row.target_ref_id is distinct from cause_row.resource_id
               or new.resource_type <> 'project_role_grant'
               or new.resource_id is distinct from cause_row.resource_id
               or new.target_ref_kind is distinct from 'project_role_grant'
               or new.target_ref_id is distinct from cause_row.resource_id
               or new.invalidation_target_kind <> 'project_role_grant'
               or new.invalidation_target_ref is distinct from cause_row.resource_id
               or new.entity_type <> 'authority_invalidation' or new.entity_id <> new.id
               or new.before_facts::jsonb->>'effective' <> 'true'
               or new.after_facts::jsonb->>'effective' <> 'false'
               or new.before_facts::jsonb->>'role' not in ('submitter','reviewer','adjudicator')
               or new.before_facts::jsonb->>'role' is distinct from new.after_facts::jsonb->>'role'
               or new.before_facts::jsonb->>'scope_type' <> 'project'
               or new.before_facts::jsonb->>'scope_id' is distinct from new.project_id
               or new.before_facts::jsonb->>'scope_id' is distinct from new.after_facts::jsonb->>'scope_id'
               or new.before_facts::jsonb->>'future_obligation' is distinct from new.after_facts::jsonb->>'future_obligation'
               or (new.before_facts::jsonb->>'role'='submitter' and new.before_facts::jsonb->>'future_obligation'<>'auth13_assignment')
               or (new.before_facts::jsonb->>'role'='reviewer' and new.before_facts::jsonb->>'future_obligation'<>'rev_reviewer_obligation')
               or (new.before_facts::jsonb->>'role'='adjudicator' and new.before_facts::jsonb->>'future_obligation'<>'none') then
              raise exception 'invalid project role revoke invalidation' using errcode='23514';
            end if;
          elsif record_row.operation='project_role_grant.issue'
                and new.event_type='AuthorityInvalidationRequested' then
            raise exception 'project role issue forbids invalidation' using errcode='23514';
          elsif new.event_type='AuthorityInvalidationRequested' then"""

_FACTS_TOP = """          if (before_state is not null and not authority_facts_are_safe(before_state))
             or (after_state is not null and not authority_facts_are_safe(after_state)) then
            return false;
          end if;"""
_FACTS_TOP_FORWARD = """          if not (event_name='AuthorityInvalidationRequested'
                  and before_state is not null
                  and after_state is not null
                  and coalesce(before_state::jsonb ? 'future_obligation', false)
                  and coalesce(after_state::jsonb ? 'future_obligation', false))
             and ((before_state is not null and not authority_facts_are_safe(before_state))
               or (after_state is not null and not authority_facts_are_safe(after_state))) then
            return false;
          end if;"""
_FACTS_BRANCH = """            when 'AuthorityInvalidationRequested' then return (before_state::jsonb = '{"effective": true}'::jsonb and after_state::jsonb = '{"effective": false}'::jsonb) or (before_state::jsonb = '{"effective": false}'::jsonb and after_state::jsonb = '{"effective": true}'::jsonb);"""
_FACTS_BRANCH_FORWARD = """            when 'AuthorityInvalidationRequested' then return
              (before_state::jsonb = '{"effective": true}'::jsonb
                and after_state::jsonb = '{"effective": false}'::jsonb)
              or (before_state::jsonb = '{"effective": false}'::jsonb
                and after_state::jsonb = '{"effective": true}'::jsonb)
              or (
                jsonb_typeof(before_state::jsonb)='object'
                and jsonb_typeof(after_state::jsonb)='object'
                and (select count(*) from jsonb_object_keys(before_state::jsonb))=5
                and (select count(*) from jsonb_object_keys(after_state::jsonb))=5
                and before_state::jsonb ?& array['effective','role','scope_type','scope_id','future_obligation']
                and after_state::jsonb ?& array['effective','role','scope_type','scope_id','future_obligation']
                and before_state::jsonb->'effective'='true'::jsonb
                and after_state::jsonb->'effective'='false'::jsonb
                and jsonb_typeof(before_state::jsonb->'role')='string'
                and jsonb_typeof(before_state::jsonb->'scope_type')='string'
                and jsonb_typeof(before_state::jsonb->'scope_id')='string'
                and jsonb_typeof(before_state::jsonb->'future_obligation')='string'
                and (before_state::jsonb - 'effective')=(after_state::jsonb - 'effective')
                and before_state::jsonb->>'scope_type'='project'
                and before_state::jsonb->>'scope_id'=envelope_project_id
                and ((before_state::jsonb->>'role'='submitter' and before_state::jsonb->>'future_obligation'='auth13_assignment')
                  or (before_state::jsonb->>'role'='reviewer' and before_state::jsonb->>'future_obligation'='rev_reviewer_obligation')
                  or (before_state::jsonb->>'role'='adjudicator' and before_state::jsonb->>'future_obligation'='none'))
              );"""

_PREDECESSOR_GUARD = """
create or replace function guard_authority_idempotency_record() returns trigger
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

_FORWARD_GUARD = """
create or replace function guard_authority_idempotency_record() returns trigger
language plpgsql as $$
declare success_count integer; invalidation_count integer; success_id text;
        qualification_row audit_events%rowtype; success_row audit_events%rowtype;
        grant_row project_role_grants%rowtype;
        snapshot_row project_role_qualification_snapshots%rowtype;
begin
  if tg_op = 'INSERT' then
    if new.status <> 'pending' then raise exception 'idempotency must begin pending' using errcode='23514'; end if;
    new.created_at := statement_timestamp(); new.committed_at := null; return new;
  elsif tg_op = 'DELETE' then
    raise exception 'authority idempotency records are immutable' using errcode='55000';
  end if;
  if old.status <> 'pending' or new.status <> 'committed'
     or (new.id,new.idempotency_key,new.actor_ref_kind,new.actor_ref,new.operation,
         new.request_digest,new.created_at) is distinct from
        (old.id,old.idempotency_key,old.actor_ref_kind,old.actor_ref,old.operation,
         old.request_digest,old.created_at) then
    raise exception 'invalid authority idempotency transition' using errcode='23514';
  end if;
  select count(*), min(id) into success_count, success_id from audit_events
  where event_domain='authority' and idempotency_reference=new.id
    and event_type <> 'AuthorityInvalidationRequested';
  select count(*) into invalidation_count from audit_events
  where event_domain='authority' and idempotency_reference=new.id
    and event_type='AuthorityInvalidationRequested';
  if new.operation='project_role_grant.issue' then
    if success_count <> 2 or invalidation_count <> 0
       or (select count(*) from audit_events where idempotency_reference=new.id
             and event_type='ProjectRoleQualificationSnapshotCaptured') <> 1
       or (select count(*) from audit_events where idempotency_reference=new.id
             and event_type='ProjectRoleGrantIssued') <> 1 then
      raise exception 'project role issue evidence pair required' using errcode='23514';
    end if;
    select * into qualification_row from audit_events where idempotency_reference=new.id
      and event_type='ProjectRoleQualificationSnapshotCaptured';
    select * into success_row from audit_events where idempotency_reference=new.id
      and event_type='ProjectRoleGrantIssued';
    select * into grant_row from project_role_grants where id=success_row.resource_id::uuid;
    select * into snapshot_row from project_role_qualification_snapshots
      where id=qualification_row.resource_id::uuid;
    if not found or grant_row.id is null or snapshot_row.id is null
       or grant_row.qualification_snapshot_id <> snapshot_row.id
       or grant_row.project_id <> snapshot_row.project_id
       or grant_row.actor_profile_id <> snapshot_row.actor_profile_id
       or grant_row.role <> snapshot_row.requested_role
       or qualification_row.project_id is distinct from grant_row.project_id
       or success_row.project_id is distinct from grant_row.project_id
       or qualification_row.target_actor_ref is distinct from grant_row.actor_profile_id
       or success_row.target_actor_ref is distinct from grant_row.actor_profile_id
       or qualification_row.request_id is distinct from success_row.request_id
       or qualification_row.correlation_id is distinct from success_row.correlation_id
       or qualification_row.actor_ref_kind is distinct from success_row.actor_ref_kind
       or qualification_row.actor_id is distinct from success_row.actor_id
       or qualification_row.permission_id is distinct from success_row.permission_id
       or qualification_row.matched_grant_id is distinct from success_row.matched_grant_id then
      raise exception 'project role issue evidence mismatch' using errcode='23514';
    end if;
  else
    if success_count <> 1 or invalidation_count <> 1 then
      raise exception 'authority evidence pair required' using errcode='23514';
    end if;
    select * into success_row from audit_events where id=success_id;
  end if;
  if success_row.resource_type <> new.response_resource_type
     or success_row.resource_id <> new.response_resource_id::text then
    raise exception 'authority response does not match evidence' using errcode='23514';
  end if;
  new.committed_at := statement_timestamp(); return new;
end $$
"""


def _definition(name: str) -> str:
    return op.get_bind().execute(
        sa.text("select pg_get_functiondef(cast(:name as regproc))"), {"name": name}
    ).scalar_one()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _assert_triggers() -> None:
    expected = {
        "authority_idempotency_guard": (
            "authority_idempotency_records", "guard_authority_idempotency_record"
        ),
        "audit_events_validate_idempotency": ("audit_events", "validate_linked_authority_event"),
    }
    rows = op.get_bind().execute(sa.text("""
        select t.tgname,c.relname,p.proname,t.tgenabled,t.tgdeferrable,t.tginitdeferred,
               pg_get_triggerdef(t.oid,true) definition
        from pg_trigger t join pg_class c on c.oid=t.tgrelid
        join pg_proc p on p.oid=t.tgfoid where t.tgname in
          ('authority_idempotency_guard','audit_events_validate_idempotency')
    """)).mappings().all()
    if len(rows) != 2:
        raise RuntimeError("unexpected authority evidence trigger inventory")
    for row in rows:
        table, function = expected[row["tgname"]]
        if (
            row["relname"] != table
            or row["proname"] != function
            or row["tgenabled"] not in ("O", b"O")
            or row["tgdeferrable"] not in (False, "f")
            or row["tginitdeferred"] not in (False, "f")
            or _digest(row["definition"]) != _TRIGGER_SHA256[row["tgname"]]
        ):
            raise RuntimeError(f"unexpected authority evidence trigger binding: {dict(row)!r}")


def _assert_fact_constraint() -> None:
    row = op.get_bind().execute(sa.text("""
        select c.relname table_name,q.convalidated,pg_get_constraintdef(q.oid) definition
        from pg_constraint q join pg_class c on c.oid=q.conrelid
        where q.conname='ck_audit_events_fact_bounds'
    """)).mappings().one_or_none()
    if (
        row is None
        or row["table_name"] != "audit_events"
        or not row["convalidated"]
        or _digest(row["definition"]) != _FACT_CONSTRAINT_SHA256
    ):
        raise RuntimeError("unexpected authority fact constraint")


def _privacy(*, add: bool) -> None:
    bind = op.get_bind()
    definition = bind.execute(sa.text("""
        select pg_get_constraintdef(oid) from pg_constraint
        where conrelid='audit_events'::regclass
          and conname='ck_audit_events_authority_privacy_bounds'
    """)).scalar_one()
    expected = _PREDECESSOR_PRIVACY_SHA256 if add else _FORWARD_PRIVACY_SHA256
    if _digest(definition) != expected:
        raise RuntimeError("unexpected authority privacy constraint")
    matches = [(old, new) for old, new in _RESOURCE_MARKERS if (new if not add else old) in definition]
    if add:
        matches = [(old, new) for old, new in matches if new not in definition]
    if not matches:
        raise RuntimeError("unexpected authority privacy constraint")
    old, new = max(matches, key=lambda item: len(item[1]))
    source, target = (old, new) if add else (new, old)
    if definition.count(source) != 1:
        raise RuntimeError("unexpected authority privacy constraint")
    definition = definition.replace(source, target)
    if not add:
        # Rebuild the predecessor through its original IN/NOT IN expression form.
        # Re-executing pg_get_constraintdef() directly produces a semantically equal
        # but structurally different ANY/ALL tree and would not restore 0033 exactly.
        definition = re.sub(
            r"\('([^']+)'::character varying\)::text",
            r"'\1'",
            definition,
        )
        definition = re.sub(
            r"\(\((\w+)\)::text = ANY \(ARRAY\[([^]]+)\]\)\)",
            r"\1 in (\2)",
            definition,
        )
        definition = re.sub(
            r"\(\((\w+)\)::text <> ALL \(ARRAY\[([^]]+)\]\)\)",
            r"\1 not in (\2)",
            definition,
        )
    op.execute(
        "alter table audit_events drop constraint "
        "ck_audit_events_authority_privacy_bounds"
    )
    op.execute(f"alter table audit_events add constraint ck_audit_events_authority_privacy_bounds {definition}")
    installed = bind.execute(sa.text("""
        select pg_get_constraintdef(oid) from pg_constraint
        where conrelid='audit_events'::regclass
          and conname='ck_audit_events_authority_privacy_bounds'
    """)).scalar_one()
    installed_expected = _FORWARD_PRIVACY_SHA256 if add else _PREDECESSOR_PRIVACY_SHA256
    if _digest(installed) != installed_expected:
        raise RuntimeError("unexpected installed authority privacy constraint")


def _linked(*, add: bool) -> None:
    linked = _definition("validate_linked_authority_event")
    if add:
        if linked.count(_LINKED_VALID_MARKER) != 1 or linked.count(_LINKED_BRANCH_MARKER) != 1:
            raise RuntimeError("unexpected linked authority validator definition")
        linked = linked.replace(_LINKED_VALID_MARKER, _LINKED_VALID_FORWARD)
        linked = linked.replace(_LINKED_BRANCH_MARKER, _LINKED_ISSUE_BRANCH)
    else:
        if linked.count(_LINKED_VALID_FORWARD) != 1 or linked.count(_LINKED_ISSUE_BRANCH) != 1:
            raise RuntimeError("unexpected linked authority validator definition")
        linked = linked.replace(_LINKED_VALID_FORWARD, _LINKED_VALID_MARKER)
        linked = linked.replace(_LINKED_ISSUE_BRANCH, _LINKED_BRANCH_MARKER)
    op.execute(linked)


def _facts(*, add: bool) -> None:
    facts = _definition("authority_event_facts_are_safe")
    old_top, new_top = (_FACTS_TOP, _FACTS_TOP_FORWARD) if add else (_FACTS_TOP_FORWARD, _FACTS_TOP)
    old_branch, new_branch = (
        (_FACTS_BRANCH, _FACTS_BRANCH_FORWARD)
        if add
        else (_FACTS_BRANCH_FORWARD, _FACTS_BRANCH)
    )
    if facts.count(old_top) != 1 or facts.count(old_branch) != 1:
        raise RuntimeError("unexpected authority fact validator definition")
    op.execute(facts.replace(old_top, new_top).replace(old_branch, new_branch))


def _refuse_incompatible(*, downgrade: bool) -> None:
    bind = op.get_bind()
    if downgrade:
        query = """select exists(
          select 1 from authority_idempotency_records r
          where r.operation='project_role_grant.issue' and
            (r.status<>'pending' or r.response_resource_type is not null
             or r.response_resource_id is not null or r.response_resource_version is not null
             or r.response_http_status is not null or r.committed_at is not null
             or exists(select 1 from audit_events e where e.idempotency_reference=r.id))
          union all select 1 from audit_events
          where event_type='ProjectRoleQualificationSnapshotCaptured'
             or (idempotency_reference is not null and event_type='ProjectRoleGrantIssued')
             or (event_type='AuthorityInvalidationRequested' and
                 (before_facts::jsonb ? 'future_obligation'
                  or after_facts::jsonb ? 'future_obligation')))"""
    else:
        query = """select exists(
          select 1 from authority_idempotency_records r
          where r.operation='project_role_grant.issue' and
            (r.status<>'pending' or r.response_resource_type is not null
             or r.response_resource_id is not null or r.response_resource_version is not null
             or r.response_http_status is not null or r.committed_at is not null
             or exists(select 1 from audit_events e where e.idempotency_reference=r.id))
          union all select 1 from audit_events e where
            e.event_type='ProjectRoleQualificationSnapshotCaptured'
            or (e.idempotency_reference is not null and e.event_type='ProjectRoleGrantIssued'
                and not exists(select 1 from authority_idempotency_records r
                  where r.id=e.idempotency_reference and r.operation='project_role_grant.issue')))"""
    if bind.execute(sa.text(query)).scalar_one():
        raise RuntimeError("incompatible project-role issue evidence")


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("lock table authority_idempotency_records in access exclusive mode"))
    bind.execute(sa.text("lock table audit_events in access exclusive mode"))
    _assert_triggers()
    _assert_fact_constraint()
    # Frozen hashes make definition drift a hard failure; marker checks below remain a
    # readable diagnostic across PostgreSQL formatting versions.
    guard, linked = _definition("guard_authority_idempotency_record"), _definition("validate_linked_authority_event")
    facts = _definition("authority_event_facts_are_safe")
    if (_digest(guard) != _PREDECESSOR_GUARD_SHA256
        or _digest(linked) != _PREDECESSOR_LINKED_SHA256
        or _digest(facts) != _PREDECESSOR_FACTS_SHA256):
        raise RuntimeError("unexpected predecessor authority evidence definition")
    _refuse_incompatible(downgrade=False)
    _privacy(add=True)
    op.execute(_FORWARD_GUARD)
    _linked(add=True)
    _facts(add=True)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("lock table authority_idempotency_records in access exclusive mode"))
    bind.execute(sa.text("lock table audit_events in access exclusive mode"))
    _assert_triggers()
    _assert_fact_constraint()
    guard = _definition("guard_authority_idempotency_record")
    linked = _definition("validate_linked_authority_event")
    facts = _definition("authority_event_facts_are_safe")
    if (
        _digest(guard) != _FORWARD_GUARD_SHA256
        or _digest(linked) != _FORWARD_LINKED_SHA256
        or _digest(facts) != _FORWARD_FACTS_SHA256
    ):
        raise RuntimeError("unexpected forward authority evidence definition")
    _refuse_incompatible(downgrade=True)
    _linked(add=False)
    _facts(add=False)
    op.execute(_PREDECESSOR_GUARD)
    _privacy(add=False)
