"""Bind exact non-secret runtime configuration to each new guide attempt."""

from alembic import op
import sqlalchemy as sa

revision = "0015_guide_runtime_configuration"
down_revision = "0014_project_role_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve retained evidence while requiring immutable configuration for new attempts."""
    op.add_column(
        "project_guide_compilation_attempts",
        sa.Column("runtime_configuration", sa.JSON(), nullable=True),
    )
    op.add_column(
        "project_guide_compilation_attempts",
        sa.Column("runtime_configuration_hash", sa.String(71), nullable=True),
    )
    op.execute("""
      create function guard_project_guide_runtime_configuration() returns trigger language plpgsql as $$
      declare config jsonb;
      begin
        if TG_OP = 'UPDATE' then
          if new.runtime_configuration::jsonb is distinct from old.runtime_configuration::jsonb
             or new.runtime_configuration_hash is distinct from old.runtime_configuration_hash then
            raise exception 'compilation runtime configuration is immutable' using errcode='23514';
          end if;
          if old.runtime_configuration is null and new.status is distinct from old.status then
            raise exception 'compilation runtime configuration unavailable' using errcode='23514';
          end if;
          return new;
        end if;
        config := new.runtime_configuration::jsonb;
        if config is null or jsonb_typeof(config) is distinct from 'object'
           or octet_length(config::text) > 75000 then
          raise exception 'compilation runtime configuration is invalid' using errcode='23514';
        end if;
        if not (config ?& array['capability_key','runtime_key','model_provider','model',
             'model_api','model_endpoint','instruction_id','instruction_version','instructions',
             'instructions_sha256','timeout_seconds','maximum_prompt_bytes'])
           or config - array['capability_key','runtime_key','model_provider','model',
             'model_api','model_endpoint','instruction_id','instruction_version','instructions',
             'instructions_sha256','timeout_seconds','maximum_prompt_bytes'] <> '{}'::jsonb
           or config->>'capability_key' is distinct from 'project_guide_compilation'
           or jsonb_typeof(config->'runtime_key') is distinct from 'string'
           or not (config->>'runtime_key' ~ '^[a-z][a-z0-9_]{0,63}$')
           or jsonb_typeof(config->'model_provider') is distinct from 'string'
           or config->>'model_provider' not in ('openai','openai_compatible')
           or jsonb_typeof(config->'model') is distinct from 'string'
           or length(config->>'model') not between 1 and 200
           or not (config->>'model' ~ '^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$')
           or jsonb_typeof(config->'model_api') is distinct from 'string'
           or config->>'model_api' not in ('responses','chat_completions')
           or config->>'instruction_id' is distinct from 'project_guide_compilation'
           or jsonb_typeof(config->'instruction_version') is distinct from 'string'
           or length(config->>'instruction_version') not between 1 and 100
           or config->>'instruction_version' is distinct from new.instruction_version
           or jsonb_typeof(config->'instructions') is distinct from 'string'
           or length(config->>'instructions') not between 1 and 16000
           or jsonb_typeof(config->'timeout_seconds') is distinct from 'number'
           or not (config->>'timeout_seconds' ~ '^[0-9]+$')
           or (config->>'timeout_seconds')::numeric not between 1 and 7200
           or jsonb_typeof(config->'maximum_prompt_bytes') is distinct from 'number'
           or not (config->>'maximum_prompt_bytes' ~ '^[0-9]+$')
           or (config->>'maximum_prompt_bytes')::numeric not between 1024 and 16777216 then
          raise exception 'compilation runtime configuration is invalid' using errcode='23514';
        end if;
        if (config->>'model_provider' = 'openai' and config->'model_endpoint' <> 'null'::jsonb)
          or (config->>'model_provider' = 'openai_compatible' and (
            jsonb_typeof(config->'model_endpoint') is distinct from 'string'
            or length(config->>'model_endpoint') > 500
            or not (config->>'model_endpoint' ~ '^https://[a-zA-Z0-9.-]+(:[0-9]{1,5})?(/[^?#@[:space:]]*)?$')
          )) then
          raise exception 'compilation model endpoint is invalid' using errcode='23514';
        end if;
        if config->>'instructions_sha256' is distinct from
             ('sha256:' || encode(sha256(convert_to(config->>'instructions','UTF8')),'hex'))
          or new.runtime_configuration_hash is distinct from
             ('sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(config),'UTF8')),'hex')) then
          raise exception 'compilation runtime configuration hash mismatch' using errcode='23514';
        end if;
        return new;
      end $$;
    """)
    op.execute("""
      create trigger project_guide_runtime_configuration_guard
      before insert or update on project_guide_compilation_attempts
      for each row execute function guard_project_guide_runtime_configuration();
    """)

    _reconcile_service_links(reverse=False)


def downgrade() -> None:
    """Refuse to discard retained configuration evidence during downgrade."""
    op.execute("""
      do $$ begin
        if exists (select 1 from project_guide_compilation_attempts where runtime_configuration is not null) then
          raise exception 'cannot remove retained compilation runtime configuration' using errcode='23514';
        end if;
      end $$;
    """)
    op.execute("""
      drop trigger project_guide_runtime_configuration_guard on project_guide_compilation_attempts;
    """)
    op.execute("""
      drop function guard_project_guide_runtime_configuration();
    """)
    _reconcile_service_links(reverse=True)
    op.drop_column("project_guide_compilation_attempts", "runtime_configuration_hash")
    op.drop_column("project_guide_compilation_attempts", "runtime_configuration")


def _reconcile_service_links(*, reverse: bool) -> None:
    """Use exact controlled-provisioning custody in the two existing SQL guards."""
    replacements = {
        "guard_project_guide_compilation_insert": (
            (
                "              and link.issuer='workstream-internal'\n              and link.subject='workstream.project.setup'",
                "              and event.actor_ref_kind='actor_profile'",
            ),
        ),
        "guard_project_guide_setup_finalization": (
            (
                "and link.subject_kind='service' and link.subject='workstream.project.setup'",
                "and link.subject_kind='service' and actor.status='active' and link.status='active'",
            ),
        ),
    }
    connection = op.get_bind()
    for name, substitutions in replacements.items():
        definition = connection.scalar(
            sa.text("select pg_get_functiondef(cast(:name as regprocedure))"), {"name": name + "()"}
        )
        for before, after in substitutions:
            source, target = (after, before) if reverse else (before, after)
            if definition.count(source) != 1:
                raise RuntimeError("compilation service guard shape changed")
            definition = definition.replace(source, target)
        op.execute(definition)
