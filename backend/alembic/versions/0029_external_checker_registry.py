"""Publish immutable authorized digest-pinned external checker registrations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0029_external_checker_registry"
down_revision = "0028_lifecycle_transitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("set local search_path = pg_catalog, public, pg_temp")
    op.execute("lock table public.audit_events in access exclusive mode")
    _extend_audit_constraints()
    _create_registry_canonical_json_function()
    op.create_table(
        "external_checker_registry_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("registration_operation_id", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("capability_id", sa.String(100), nullable=False),
        sa.Column("capability_version", sa.String(50), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("image_digest", sa.String(71), nullable=False),
        sa.Column("configuration_schema_id", sa.String(100), nullable=False),
        sa.Column("configuration_schema_version", sa.String(50), nullable=False),
        sa.Column("configuration_schema_sha256", sa.String(71), nullable=False),
        sa.Column("configuration_schema_document", JSONB(), nullable=False),
        sa.Column("input_schema_id", sa.String(100), nullable=False),
        sa.Column("input_schema_version", sa.String(50), nullable=False),
        sa.Column("input_schema_sha256", sa.String(71), nullable=False),
        sa.Column("input_schema_document", JSONB(), nullable=False),
        sa.Column("output_schema_id", sa.String(100), nullable=False),
        sa.Column("output_schema_version", sa.String(50), nullable=False),
        sa.Column("output_schema_sha256", sa.String(71), nullable=False),
        sa.Column("output_schema_document", JSONB(), nullable=False),
        sa.Column("cpu_millis", sa.Integer(), nullable=False),
        sa.Column("memory_bytes", sa.BigInteger(), nullable=False),
        sa.Column("deadline_ms", sa.Integer(), nullable=False),
        sa.Column("maximum_output_bytes", sa.Integer(), nullable=False),
        sa.Column("entry_digest", sa.String(71), nullable=False),
        sa.Column(
            "registered_by_actor_profile_id",
            sa.Uuid(),
            sa.ForeignKey(
                "public.actor_profiles.id",
                ondelete="RESTRICT",
                deferrable=True,
                initially="DEFERRED",
            ),
            nullable=False,
        ),
        sa.Column(
            "authorization_decision_event_id",
            sa.Uuid(),
            sa.ForeignKey("public.audit_events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "registration_operation_id",
            name="registry_operation",
        ),
        sa.UniqueConstraint(
            "capability_id",
            "capability_version",
            "phase",
            name="registry_identity",
        ),
        sa.UniqueConstraint(
            "entry_digest",
            name="registry_digest",
        ),
        sa.UniqueConstraint(
            "authorization_decision_event_id",
            name="registry_authority",
        ),
        sa.CheckConstraint(
            "(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128",
            name="id_uuid7",
        ),
        sa.CheckConstraint(
            "capability_id ~ '^[a-z][a-z0-9_.-]{0,99}$' and "
            "capability_version ~ '^[a-z0-9][a-z0-9_.-]{0,49}$'",
            name="identifiers",
        ),
        sa.CheckConstraint("phase in ('pre_submit','post_submit')", name="phase"),
        sa.CheckConstraint(
            "image_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "configuration_schema_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "input_schema_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "output_schema_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "entry_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="sha256_shapes",
        ),
        sa.CheckConstraint(
            "configuration_schema_id ~ '^[a-z][a-z0-9_.-]{0,99}$' and "
            "configuration_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,49}$' and "
            "input_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,49}$' and "
            "output_schema_version ~ '^[a-z0-9][a-z0-9_.-]{0,49}$'",
            name="schema_identifiers",
        ),
        sa.CheckConstraint(
            "(phase='pre_submit' and input_schema_id='external_checker_pre_submit_input') "
            "or (phase='post_submit' and input_schema_id='external_checker_post_submit_input')",
            name="input_schema_phase",
        ),
        sa.CheckConstraint(
            "output_schema_id='external_checker_result'",
            name="output_schema",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(configuration_schema_document)='object' and "
            "jsonb_typeof(input_schema_document)='object' and "
            "jsonb_typeof(output_schema_document)='object' and "
            "octet_length(convert_to(public.external_checker_registry_canonical_json("
            "configuration_schema_document),'UTF8'))<=65536 and "
            "octet_length(convert_to(public.external_checker_registry_canonical_json("
            "input_schema_document),'UTF8'))<=65536 and "
            "octet_length(convert_to(public.external_checker_registry_canonical_json("
            "output_schema_document),'UTF8'))<=65536",
            name="schema_documents",
        ),
        sa.CheckConstraint(
            "cpu_millis between 100 and 64000 and "
            "memory_bytes between 16777216 and 68719476736 and "
            "deadline_ms between 100 and 3600000 and "
            "maximum_output_bytes between 256 and 65536",
            name="resource_limits",
        ),
        schema="public",
    )
    _create_registry_functions()
    op.execute("""
create trigger external_checker_registry_immutable
before update or delete on public.external_checker_registry_entries
for each row execute function public.deny_external_checker_registry_mutation()
""")
    op.execute("""
create trigger external_checker_registry_no_truncate
before truncate on public.external_checker_registry_entries
for each statement execute function public.deny_external_checker_registry_mutation()
""")
    op.execute("""
create constraint trigger external_checker_registry_authority_closure
after insert on public.external_checker_registry_entries
deferrable initially deferred for each row
execute function public.guard_external_checker_registry_entry()
""")


def _definition(name: str) -> str:
    return op.get_bind().execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_catalog.pg_constraint "
            "where conrelid='public.audit_events'::regclass and conname=:name"
        ),
        {"name": name},
    ).scalar_one()


def _replace_constraint(name: str, definition: str) -> None:
    op.execute(f"alter table public.audit_events drop constraint {name}")
    op.execute(f"alter table public.audit_events add constraint {name} {definition}")


def _extend_audit_constraints() -> None:
    name = "ck_audit_events_authorization_action_evidence"
    definition = _definition(name)
    anchor = (
        "(((action_id)::text = 'project.task.create'::text) AND "
        "((permission_id)::text = 'project.task.manage'::text))"
    )
    addition = (
        "(((action_id)::text = 'checker.registry.register'::text) AND "
        "((permission_id)::text = 'operations.reconcile.run'::text))"
    )
    if definition.count(anchor) != 2 or addition in definition:
        raise RuntimeError("checker registry audit action constraint shape changed")
    _replace_constraint(name, definition.replace(anchor, anchor + " OR " + addition))

    name = "ck_audit_events_authority_privacy_bounds"
    definition = _definition(name)
    resource_start = definition.index("resource_type IS NULL")
    target_start = definition.index("target_ref_kind IS NULL")
    addition = "('external_checker_registry_entry'::character varying)::text, "
    for start in sorted((resource_start, target_start), reverse=True):
        index = definition.index("ARRAY[", start) + len("ARRAY[")
        definition = definition[:index] + addition + definition[index:]
    _replace_constraint(name, definition)


def _create_registry_canonical_json_function() -> None:
    op.execute("""
create function public.external_checker_registry_canonical_json(value jsonb)
returns text language plpgsql immutable strict
set search_path=pg_catalog,public,pg_temp as $$
declare encoded text;
begin
 case pg_catalog.jsonb_typeof(value)
  when 'object' then
   select '{' || coalesce(pg_catalog.string_agg(
    pg_catalog.to_json(item_key)::text || ':' ||
     public.external_checker_registry_canonical_json(item_value),
    ',' order by item_key collate "C"), '') || '}' into encoded
   from pg_catalog.jsonb_each(value) as items(item_key,item_value);
   return encoded;
  when 'array' then
   select '[' || coalesce(pg_catalog.string_agg(
    public.external_checker_registry_canonical_json(item_value),
    ',' order by item_order), '') || ']' into encoded
   from pg_catalog.jsonb_array_elements(value) with ordinality
    as items(item_value,item_order);
   return encoded;
  else return value::text;
 end case;
end
$$
""")


def _create_registry_functions() -> None:
    op.execute("""
create function public.external_checker_registry_spec(
 r public.external_checker_registry_entries
) returns jsonb language sql immutable
set search_path=pg_catalog,public,pg_temp as $$
 select pg_catalog.jsonb_build_object(
  'capability_id',r.capability_id,'capability_version',r.capability_version,
  'phase',r.phase,'image_digest',r.image_digest,
  'configuration_schema',pg_catalog.jsonb_build_object(
   'schema_id',r.configuration_schema_id,'schema_version',r.configuration_schema_version,
   'document',r.configuration_schema_document,'schema_sha256',r.configuration_schema_sha256),
  'input_schema',pg_catalog.jsonb_build_object(
   'schema_id',r.input_schema_id,'schema_version',r.input_schema_version,
   'document',r.input_schema_document,'schema_sha256',r.input_schema_sha256),
  'output_schema',pg_catalog.jsonb_build_object(
   'schema_id',r.output_schema_id,'schema_version',r.output_schema_version,
   'document',r.output_schema_document,'schema_sha256',r.output_schema_sha256),
  'resources',pg_catalog.jsonb_build_object(
   'cpu_millis',r.cpu_millis,'memory_bytes',r.memory_bytes,
   'deadline_ms',r.deadline_ms,'maximum_output_bytes',r.maximum_output_bytes))
$$
""")
    op.execute("""
create function public.external_checker_registry_digest(value jsonb)
returns varchar language sql immutable
set search_path=pg_catalog,public,pg_temp as $$
 select 'sha256:' || pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
  public.external_checker_registry_canonical_json(value),'UTF8')),'hex')
$$
""")
    op.execute("""
create function public.external_checker_registry_authority_resource(
 r public.external_checker_registry_entries
) returns jsonb language sql immutable
set search_path=pg_catalog,public,pg_temp as $$
 select pg_catalog.jsonb_build_object(
  'resource_type','external_checker_registry_entry','resource_id',r.id,
  'operation_id',r.registration_operation_id,'request_digest',r.request_digest,
  'entry_digest',r.entry_digest)
$$
""")
    op.execute("""
create function public.external_checker_registry_entry_valid(
 r public.external_checker_registry_entries
) returns boolean language sql stable
set search_path=pg_catalog,public,pg_temp as $$
 select coalesce(
  r.entry_digest=public.external_checker_registry_digest(
   public.external_checker_registry_spec(r))
  and r.configuration_schema_sha256=public.external_checker_registry_digest(
   r.configuration_schema_document)
  and r.input_schema_sha256=public.external_checker_registry_digest(
   r.input_schema_document)
  and r.output_schema_sha256=public.external_checker_registry_digest(
   r.output_schema_document)
  and r.request_digest=public.external_checker_registry_digest(
   pg_catalog.jsonb_build_object(
    'actor_profile_id',r.registered_by_actor_profile_id,
    'operation_id',r.registration_operation_id,'registry_entry_id',r.id,
    'spec',public.external_checker_registry_spec(r)))
  and exists(
   select 1 from public.audit_events a
   join public.actor_profiles p on p.id::text=a.actor_id
   join public.actor_identity_links l on l.actor_profile_id=p.id
   join public.admin_role_grants g on g.id::text=a.matched_grant_id
   where a.id=r.authorization_decision_event_id
    and a.event_domain='authority'
    and a.event_type='SensitiveAuthorizationAllowed'
    and a.actor_ref_kind='actor_profile'
    and p.id=r.registered_by_actor_profile_id
    and p.actor_kind='human' and p.status='active'
    and l.status='active'
    and g.target_actor_profile_id=p.id and g.role='operator'
    and g.status='active' and g.scope_type='system' and g.scope_project_id is null
    and a.action_id='checker.registry.register'
    and a.permission_id='operations.reconcile.run'
    and a.request_id is not null
    and a.correlation_id=r.registration_operation_id
    and a.project_id is null
    and a.resource_type='external_checker_registry_entry'
    and a.resource_id=r.id::text
    and a.target_ref_kind='external_checker_registry_entry'
    and a.target_ref_id=r.id::text
    and a.denial_code is null
    and a.after_facts::jsonb=pg_catalog.jsonb_build_object(
     'allowed',true,'resource_context_digest',
     public.external_checker_registry_digest(pg_catalog.jsonb_build_object(
      'resource_context',public.external_checker_registry_authority_resource(r))))
  ),false)
$$
""")
    op.execute("""
create function public.guard_external_checker_registry_entry() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
begin
 if not public.external_checker_registry_entry_valid(new) then
  raise exception 'external checker registry authority closure invalid'
   using errcode='23514';
 end if;
 return null;
end
$$
""")
    op.execute("""
create function public.deny_external_checker_registry_mutation() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
begin
 raise exception 'external checker registry is immutable' using errcode='23514';
end
$$
""")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
