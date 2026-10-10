"""Retain authorized project-bound task-import source bytes in ART custody."""

from alembic import op
import sqlalchemy as sa


revision = "0030_task_import_source"
down_revision = "0029_external_checker_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Install one immutable source declaration and its exact ART lineage."""
    op.execute("set local search_path = pg_catalog, public, pg_temp")
    op.execute(
        "lock table public.actor_identity_links, public.actor_profiles, "
        "public.artifact_operation_receipts, public.artifact_put_attempts, "
        "public.audit_events, public.projects in access exclusive mode"
    )
    _extend_audit_constraints()
    _create_source_table()
    _extend_put_attempts()
    _extend_operation_receipts()
    _create_source_custody()


def _definition(table: str, name: str) -> str:
    return (
        op.get_bind()
        .execute(
            sa.text(
                "select pg_get_constraintdef(oid) from pg_catalog.pg_constraint "
                "where conrelid=cast(:table as regclass) and conname=:name"
            ),
            {"table": f"public.{table}", "name": name},
        )
        .scalar_one()
    )


def _replace_constraint(table: str, name: str, definition: str) -> None:
    op.execute(f"alter table public.{table} drop constraint {name}")
    op.execute(f"alter table public.{table} add constraint {name} {definition}")


def _extend_audit_constraints() -> None:
    name = "ck_audit_events_authorization_action_evidence"
    definition = _definition("audit_events", name)
    anchor = (
        "(((action_id)::text = 'project.task.create'::text) AND "
        "((permission_id)::text = 'project.task.manage'::text))"
    )
    additions = " OR ".join(
        "(((action_id)::text = "
        f"'{action}'::text) AND ((permission_id)::text = "
        "'project.task.manage'::text))"
        for action in (
            "artifact.task_import_source.declare",
            "artifact.task_import_source.upload",
            "artifact.task_import_source.read",
        )
    )
    if definition.count(anchor) != 2 or "artifact.task_import_source.declare" in definition:
        raise RuntimeError("task import source audit action constraint shape changed")
    _replace_constraint(
        "audit_events",
        name,
        definition.replace(anchor, anchor + " OR " + additions),
    )

    name = "ck_audit_events_authority_privacy_bounds"
    definition = _definition("audit_events", name)
    if "'task_import_source'::character varying" in definition:
        raise RuntimeError("task import source audit privacy constraint already changed")
    resource_start = definition.index("resource_type IS NULL")
    target_start = definition.index("target_ref_kind IS NULL")
    addition = "('task_import_source'::character varying)::text, "
    for start in sorted((resource_start, target_start), reverse=True):
        index = definition.index("ARRAY[", start) + len("ARRAY[")
        definition = definition[:index] + addition + definition[index:]
    _replace_constraint("audit_events", name, definition)


def _create_source_table() -> None:
    op.create_table(
        "artifact_task_import_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("actor_profile_id", sa.Uuid(), nullable=False),
        sa.Column("identity_link_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_decision_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(71), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("operation_identity", sa.String(71), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_artifact_task_import_sources"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["public.projects.id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["actor_profile_id"],
            ["public.actor_profiles.id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["public.actor_identity_links.id", "public.actor_identity_links.actor_profile_id"],
            name="fk_artifact_task_import_source_actor_link",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["authorization_decision_id"],
            ["public.audit_events.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_artifact_task_import_source_namespace",
        ),
        sa.UniqueConstraint(
            "operation_identity",
            name="uq_artifact_task_import_source_operation",
        ),
        sa.UniqueConstraint(
            "id",
            "project_id",
            "sha256",
            "byte_count",
            "media_type",
            name="uq_artifact_task_import_source_custody",
        ),
        sa.CheckConstraint(
            "(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128",
            name="ck_artifact_task_import_sources_id_uuid7",
        ),
        sa.CheckConstraint(
            "sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_artifact_task_import_sources_sha256_shape",
        ),
        sa.CheckConstraint(
            "operation_identity ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_artifact_task_import_sources_operation_identity_shape",
        ),
        sa.CheckConstraint(
            "byte_count between 1 and 8388608",
            name="ck_artifact_task_import_sources_byte_count_bound",
        ),
        sa.CheckConstraint(
            "media_type='application/json'",
            name="ck_artifact_task_import_sources_media_type",
        ),
        schema="public",
    )


def _extend_put_attempts() -> None:
    op.add_column(
        "artifact_put_attempts",
        sa.Column("task_import_source_id", sa.Uuid(), nullable=True),
        schema="public",
    )
    _replace_constraint(
        "artifact_put_attempts",
        "ck_artifact_put_attempts_producer_request_type",
        "check (producer_request_type in "
        "('guide','checker_output','submission_bundle','task_import_source'))",
    )
    _replace_constraint(
        "artifact_put_attempts",
        "ck_artifact_put_attempts_producer_identity",
        "check ((producer_request_type in ('guide','task_import_source') "
        "and producer_type='actor_profile' "
        "and producer_ref ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-"
        "[89ab][0-9a-f]{3}-[0-9a-f]{12}$') or "
        "(producer_request_type='checker_output' "
        "and producer_type='service_identity' "
        "and producer_ref='workstream.artifact.checker_output') or "
        "(producer_request_type='submission_bundle' "
        "and producer_type='actor_profile' "
        "and producer_ref ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-"
        "[89ab][0-9a-f]{3}-[0-9a-f]{12}$'))",
    )
    _replace_constraint(
        "artifact_put_attempts",
        "ck_artifact_put_attempts_producer_reference",
        "check ((producer_request_type='guide' and task_import_source_id is null "
        "and guide_source_item_id is not null and checker_run_id is null "
        "and task_id is null and submission_id is null and submission_version is null "
        "and logical_role is null) or "
        "(producer_request_type='checker_output' and task_import_source_id is null "
        "and guide_source_item_id is null and checker_run_id is not null "
        "and task_id is not null and submission_id is not null "
        "and submission_version is not null "
        "and octet_length(logical_role) between 1 and 100) or "
        "(producer_request_type='submission_bundle' and task_import_source_id is null "
        "and guide_source_item_id is null and checker_run_id is null "
        "and task_id is not null and submission_id is null "
        "and submission_version is null and logical_role is null) or "
        "(producer_request_type='task_import_source' "
        "and task_import_source_id is not null and guide_source_item_id is null "
        "and checker_run_id is null and task_id is null and submission_id is null "
        "and submission_version is null and logical_role='task_import_source'))",
    )
    op.create_unique_constraint(
        "uq_artifact_put_attempt_import_source",
        "artifact_put_attempts",
        ["task_import_source_id"],
        schema="public",
    )
    op.create_foreign_key(
        "fk_artifact_put_attempt_import_source_custody",
        "artifact_put_attempts",
        "artifact_task_import_sources",
        ["task_import_source_id", "project_id", "sha256", "byte_count", "media_type"],
        ["id", "project_id", "sha256", "byte_count", "media_type"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )


def _extend_operation_receipts() -> None:
    _replace_constraint(
        "artifact_operation_receipts",
        "ck_artifact_operation_receipts_contract_producer_reference",
        "check (contract_version=2 and put_attempt_id is not null and "
        "((guide_source_item_id is not null and checker_run_id is null "
        "and logical_role is null) or "
        "(guide_source_item_id is null and checker_run_id is not null "
        "and octet_length(logical_role) between 1 and 100) or "
        "(guide_source_item_id is null and checker_run_id is null "
        "and (logical_role is null or logical_role='task_import_source'))))",
    )
    op.execute(
        """
create or replace function public.guard_artifact_receipt_producer_reference()
returns trigger language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare request_type text;
begin
 select producer_request_type into request_type
 from public.artifact_put_attempts where id=new.put_attempt_id;
 if request_type is null
    or (request_type='guide' and not (
      new.guide_source_item_id is not null and new.checker_run_id is null
      and new.logical_role is null))
    or (request_type='checker_output' and not (
      new.guide_source_item_id is null and new.checker_run_id is not null
      and octet_length(new.logical_role) between 1 and 100))
    or (request_type='submission_bundle' and not (
      new.guide_source_item_id is null and new.checker_run_id is null
      and new.logical_role is null))
    or (request_type='task_import_source' and not (
      new.guide_source_item_id is null and new.checker_run_id is null
      and new.logical_role='task_import_source'))
    or request_type not in (
      'guide','checker_output','submission_bundle','task_import_source') then
  raise exception 'artifact receipt producer reference mismatch' using errcode='23514';
 end if;
 return new;
end
$$
"""
    )


def _create_source_custody() -> None:
    op.execute(
        """
create function public.task_import_source_resource_digest(
 source public.artifact_task_import_sources
) returns varchar language sql immutable
set search_path=pg_catalog,public,pg_temp as $$
 select public.external_checker_registry_digest(pg_catalog.jsonb_build_object(
  'resource_context',pg_catalog.jsonb_build_object(
   'resource_type','task_import_source','resource_id',source.id,
   'scope_project_id',source.project_id,
   'actor_profile_id',source.actor_profile_id,
   'identity_link_id',source.identity_link_id,
   'sha256',source.sha256,'byte_count',source.byte_count,
   'media_type',source.media_type,
   'operation_identity',source.operation_identity,
   'idempotency_key',source.idempotency_key)))
$$
"""
    )
    op.execute(
        """
create function public.guard_artifact_task_import_source() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare authority public.audit_events%rowtype;
begin
 select event.* into authority from public.audit_events event
 where event.id=new.authorization_decision_id;
 if not found
    or authority.event_domain<>'authority'
    or authority.event_type<>'SensitiveAuthorizationAllowed'
    or authority.actor_ref_kind<>'actor_profile'
    or authority.actor_id<>new.actor_profile_id::text
    or authority.project_id is distinct from new.project_id
    or authority.action_id<>'artifact.task_import_source.declare'
    or authority.permission_id<>'project.task.manage'
    or authority.resource_type<>'task_import_source'
    or authority.resource_id<>new.id::text
    or authority.target_ref_kind<>'task_import_source'
    or authority.target_ref_id<>new.id::text
    or authority.denial_code is not null
    or authority.after_facts::jsonb is distinct from pg_catalog.jsonb_build_object(
      'allowed',true,'resource_context_digest',
      public.task_import_source_resource_digest(new))
    or new.operation_identity is distinct from
      public.external_checker_registry_digest(pg_catalog.jsonb_build_object(
       'request_type','task_import_source','source_id',new.id)) then
  raise exception 'task import source authorization custody invalid' using errcode='23514';
 end if;
 return new;
end
$$
"""
    )
    op.execute(
        """
create constraint trigger artifact_task_import_source_authority
after insert on public.artifact_task_import_sources
deferrable initially deferred for each row
execute function public.guard_artifact_task_import_source()
"""
    )
    op.execute(
        """
create function public.reject_artifact_task_import_source_mutation() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
begin
 raise exception 'task import source custody is immutable' using errcode='55000';
end
$$
"""
    )
    op.execute(
        """
create trigger artifact_task_import_source_immutable
before update or delete on public.artifact_task_import_sources
for each row execute function public.reject_artifact_task_import_source_mutation()
"""
    )
    op.execute(
        """
create trigger artifact_task_import_source_no_truncate
before truncate on public.artifact_task_import_sources
for each statement execute function public.reject_artifact_task_import_source_mutation()
"""
    )
    op.execute(
        """
create function public.guard_task_import_source_put_attempt() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare source public.artifact_task_import_sources%rowtype;
begin
 if tg_op='DELETE' then
  if old.producer_request_type='task_import_source' then
   raise exception 'task import source put attempt custody is immutable' using errcode='55000';
  end if;
  return old;
 end if;
 if old.producer_request_type='task_import_source'
    or new.producer_request_type='task_import_source' then
  if tg_op='UPDATE' and row(
      new.id,new.producer_request_type,new.task_import_source_id,
      new.producer_type,new.producer_ref,new.project_id,new.task_id,
      new.guide_source_item_id,new.checker_run_id,new.submission_id,
      new.submission_version,new.logical_role,new.sha256,new.byte_count,
      new.media_type,new.storage_namespace_id,new.namespace_fingerprint,
      new.canonical_target,new.operation_identity,new.request_digest,
      new.checker_request_digest,new.maximum_observations,new.prepared_at,new.created_at
     ) is distinct from row(
      old.id,old.producer_request_type,old.task_import_source_id,
      old.producer_type,old.producer_ref,old.project_id,old.task_id,
      old.guide_source_item_id,old.checker_run_id,old.submission_id,
      old.submission_version,old.logical_role,old.sha256,old.byte_count,
      old.media_type,old.storage_namespace_id,old.namespace_fingerprint,
      old.canonical_target,old.operation_identity,old.request_digest,
      old.checker_request_digest,old.maximum_observations,old.prepared_at,old.created_at
     ) then
   raise exception 'task import source put attempt custody is immutable' using errcode='55000';
  end if;
  select value.* into source from public.artifact_task_import_sources value
  where value.id=new.task_import_source_id for key share;
  if not found
     or source.project_id is distinct from new.project_id
     or source.actor_profile_id::text is distinct from new.producer_ref
     or source.sha256 is distinct from new.sha256
     or source.byte_count is distinct from new.byte_count
     or source.media_type is distinct from new.media_type
     or source.operation_identity is distinct from new.operation_identity
     or new.producer_type<>'actor_profile'
     or new.logical_role<>'task_import_source' then
   raise exception 'task import source put attempt custody invalid' using errcode='23514';
  end if;
 end if;
 return new;
end
$$
"""
    )
    op.execute(
        """
create trigger task_import_source_put_attempt_custody
before insert or update or delete on public.artifact_put_attempts
for each row execute function public.guard_task_import_source_put_attempt()
"""
    )


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
