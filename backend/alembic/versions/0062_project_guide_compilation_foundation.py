"""Install hidden unified guide-compilation persistence.

Revision ID: 0062_guide_compilation
Revises: 0061_submission_admission
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0062_guide_compilation"
down_revision = "0061_submission_admission"
branch_labels = depends_on = None

_HASH = r"^sha256:[0-9a-f]{64}$"
_ACTION = "project.guide_compilation.execute"
_PERMISSION = "project.guide_compilation.execute"
_RESOURCE_MARKER = (
    "('project_submission_artifact_policy_mutation'::character varying)::text"
)
_RESOURCE_ADDITION = (
    ", ('project_guide_compilation_attempt'::character varying)::text"
)
_PERMISSION_MARKER = "('review.queue.override'::character varying)::text"
_PERMISSION_ADDITION = (
    ", ('project.guide_compilation.execute'::character varying)::text"
)


def _rewrite_permission_registry(*, add: bool) -> None:
    connection = op.get_bind()
    definition = connection.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_registries'"
        )
    ).scalar_one()
    expanded = _PERMISSION_MARKER + _PERMISSION_ADDITION
    source, target = (
        (_PERMISSION_MARKER, expanded)
        if add
        else (expanded, _PERMISSION_MARKER)
    )
    if definition.count(source) != 1 or (add and expanded in definition):
        raise RuntimeError("unexpected compilation permission registry")
    op.drop_constraint("authority_registries", "audit_events", type_="check")
    op.execute(
        "alter table audit_events add constraint "
        f"ck_audit_events_authority_registries {definition.replace(source, target, 1)}"
    )


def _rewrite_audit_resource(*, add: bool) -> None:
    connection = op.get_bind()
    definition = connection.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_privacy_bounds'"
        )
    ).scalar_one()
    expanded = _RESOURCE_MARKER + _RESOURCE_ADDITION
    source, target = (
        (_RESOURCE_MARKER, expanded)
        if add
        else (expanded, _RESOURCE_MARKER)
    )
    if definition.count(source) != 1 or (add and expanded in definition):
        raise RuntimeError("unexpected compilation audit-resource registry")
    op.drop_constraint("authority_privacy_bounds", "audit_events", type_="check")
    op.execute(
        "alter table audit_events add constraint "
        f"ck_audit_events_authority_privacy_bounds {definition.replace(source, target, 1)}"
    )


def _action_pair_token() -> str:
    return (
        f"(((action_id)::text = '{_ACTION}'::text) AND "
        f"((permission_id)::text = '{_PERMISSION}'::text))"
    )


def _rewrite_action_evidence(*, add: bool) -> None:
    connection = op.get_bind()
    definition = connection.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authorization_action_evidence'"
        )
    ).scalar_one()
    marker = (
        "(((action_id)::text = 'project.guide_sufficiency.run'::text) AND "
        "((permission_id)::text = 'project.guide.manage'::text))"
    )
    addition = " OR " + _action_pair_token()
    if add:
        if definition.count(marker) != 2 or _action_pair_token() in definition:
            raise RuntimeError("unexpected compilation action-evidence registry")
        definition = definition.replace(marker, marker + addition)
    else:
        if definition.count(addition) != 2:
            raise RuntimeError("unexpected compilation action-evidence registry")
        definition = definition.replace(addition, "")
    op.drop_constraint("authorization_action_evidence", "audit_events", type_="check")
    op.execute(
        "alter table audit_events add constraint "
        f"ck_audit_events_authorization_action_evidence {definition}"
    )


def upgrade() -> None:
    """Create the attempt fence and append-only compilation graph."""
    op.execute("lock table audit_events in access exclusive mode")
    _rewrite_audit_resource(add=True)
    _rewrite_permission_registry(add=True)
    _rewrite_action_evidence(add=True)
    op.create_table(
        "project_guide_compilation_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("guide_id", sa.String(36), nullable=False),
        sa.Column("guide_version", sa.String(50), nullable=False),
        sa.Column("source_snapshot_id", sa.String(36), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(71), nullable=False),
        sa.Column("setup_run_id", sa.String(36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("canonical_input_hash", sa.String(71), nullable=False),
        sa.Column("guide_material_hash", sa.String(71), nullable=False),
        sa.Column("pre_catalogue_id", sa.String(160), nullable=False),
        sa.Column("pre_catalogue_version", sa.String(100), nullable=False),
        sa.Column("pre_catalogue_schema_version", sa.String(160), nullable=False),
        sa.Column("pre_catalogue_manifest_hash", sa.String(71), nullable=False),
        sa.Column("post_catalogue_id", sa.String(160), nullable=False),
        sa.Column("post_catalogue_version", sa.String(100), nullable=False),
        sa.Column("post_catalogue_schema_version", sa.String(160), nullable=False),
        sa.Column("post_catalogue_manifest_hash", sa.String(71), nullable=False),
        sa.Column("agent_identity", sa.String(100), nullable=False),
        sa.Column("agent_version", sa.String(100), nullable=False),
        sa.Column("instruction_version", sa.String(100), nullable=False),
        sa.Column("provider_idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("canonical_result", sa.JSON()),
        sa.Column("result_hash", sa.String(71)),
        sa.Column("component_hashes", sa.JSON()),
        sa.Column("failure_code", sa.String(100)),
        sa.Column("persisted_compilation_id", sa.Uuid()),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("provider_uncertain_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.Column("persisted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["guide_id"], ["project_guides.id"]),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_compilation_attempt_snapshot_hash",
        ),
        sa.ForeignKeyConstraint(
            ["setup_run_id", "project_id", "guide_id", "source_snapshot_id", "setup_generation"],
            ["project_setup_runs.id", "project_setup_runs.project_id", "project_setup_runs.guide_id", "project_setup_runs.source_snapshot_id", "project_setup_runs.setup_generation"],
            name="fk_compilation_attempt_exact_setup",
        ),
        sa.UniqueConstraint("setup_run_id", "setup_generation", name="uq_compilation_attempt_setup_generation"),
        sa.UniqueConstraint("provider_idempotency_key", name="uq_compilation_attempt_provider_key"),
        sa.CheckConstraint("setup_generation > 0", name="ck_compilation_attempt_generation"),
        sa.CheckConstraint(
            "status in ('reserved','provider_uncertain','accepted','invalid_terminal','persisted')",
            name="ck_compilation_attempt_status",
        ),
        sa.CheckConstraint(
            f"source_snapshot_hash ~ '{_HASH}' and canonical_input_hash ~ '{_HASH}' and guide_material_hash ~ '{_HASH}' and "
            f"pre_catalogue_manifest_hash ~ '{_HASH}' and post_catalogue_manifest_hash ~ '{_HASH}'",
            name="ck_compilation_attempt_identity_hashes",
        ),
        sa.CheckConstraint(f"result_hash is null or result_hash ~ '{_HASH}'", name="ck_compilation_attempt_result_hash"),
        sa.CheckConstraint("canonical_result is null or octet_length(canonical_result::text) <= 4194304", name="ck_compilation_attempt_result_size"),
        sa.CheckConstraint(
            "component_hashes is null or (json_typeof(component_hashes)='object' and "
            "component_hashes::jsonb=jsonb_build_object("
            "'sufficiency_hash',component_hashes->>'sufficiency_hash',"
            "'artifact_policy_hash',component_hashes->>'artifact_policy_hash',"
            "'requirement_inventory_hash',component_hashes->>'requirement_inventory_hash',"
            "'pre_submit_hash',component_hashes->>'pre_submit_hash',"
            "'post_submit_hash',component_hashes->>'post_submit_hash',"
            "'capability_suggestions_hash',component_hashes->>'capability_suggestions_hash',"
            "'setup_notes_hash',component_hashes->>'setup_notes_hash') and "
            + " and ".join(
                f"coalesce((component_hashes->>'{name}') ~ '{_HASH}',false)"
                for name in (
                    "sufficiency_hash", "artifact_policy_hash", "requirement_inventory_hash",
                    "pre_submit_hash", "post_submit_hash", "capability_suggestions_hash",
                    "setup_notes_hash",
                )
            )
            + ")",
            name="ck_compilation_attempt_component_hashes",
        ),
        sa.CheckConstraint(
            "(status='reserved' and provider_uncertain_at is null and accepted_at is null and terminal_at is null and persisted_at is null and canonical_result is null and result_hash is null and component_hashes is null and failure_code is null and persisted_compilation_id is null) or "
            "(status='provider_uncertain' and provider_uncertain_at is not null and accepted_at is null and terminal_at is null and persisted_at is null and canonical_result is null and result_hash is null and component_hashes is null and failure_code is null and persisted_compilation_id is null) or "
            "(status='accepted' and accepted_at is not null and terminal_at is null and persisted_at is null and canonical_result is not null and result_hash is not null and component_hashes is not null and failure_code is null and persisted_compilation_id is null) or "
            "(status='persisted' and accepted_at is not null and persisted_at is not null and terminal_at is null and canonical_result is not null and result_hash is not null and component_hashes is not null and failure_code is null and persisted_compilation_id is not null) or "
            "(status='invalid_terminal' and terminal_at is not null and accepted_at is null and persisted_at is null and canonical_result is null and result_hash is null and component_hashes is null and persisted_compilation_id is null and failure_code in ('schema_invalid','unsafe_text','hash_mismatch','context_mismatch'))",
            name="ck_compilation_attempt_state_shape",
        ),
    )
    for column in ("project_id", "guide_id", "source_snapshot_id", "setup_run_id"):
        op.create_index(f"ix_project_guide_compilation_attempts_{column}", "project_guide_compilation_attempts", [column])

    op.create_table(
        "project_guide_compilations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("guide_id", sa.String(36), nullable=False),
        sa.Column("guide_version", sa.String(50), nullable=False),
        sa.Column("source_snapshot_id", sa.String(36), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(71), nullable=False),
        sa.Column("setup_run_id", sa.String(36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("canonical_input_hash", sa.String(71), nullable=False),
        sa.Column("guide_material_hash", sa.String(71), nullable=False),
        sa.Column("pre_catalogue_manifest_hash", sa.String(71), nullable=False),
        sa.Column("post_catalogue_manifest_hash", sa.String(71), nullable=False),
        sa.Column("agent_identity", sa.String(100), nullable=False),
        sa.Column("agent_version", sa.String(100), nullable=False),
        sa.Column("instruction_version", sa.String(100), nullable=False),
        sa.Column("canonical_result", sa.JSON(), nullable=False),
        sa.Column("result_hash", sa.String(71), nullable=False),
        sa.Column("component_hashes", sa.JSON(), nullable=False),
        sa.Column("supersedes_compilation_id", sa.Uuid()),
        sa.Column("created_by_actor_profile_id", sa.String(36), nullable=False),
        sa.Column("created_via_identity_link_id", sa.String(36), nullable=False),
        sa.Column("created_by_service_identity", sa.String(160), nullable=False),
        sa.Column("creation_action_id", sa.String(160), nullable=False),
        sa.Column("authorization_decision_event_id", sa.String(36), nullable=False),
        sa.Column("authorization_resource_context_digest", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["attempt_id"], ["project_guide_compilation_attempts.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["guide_id"], ["project_guides.id"]),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["guide_source_snapshots.id"]),
        sa.ForeignKeyConstraint(["setup_run_id"], ["project_setup_runs.id"]),
        sa.ForeignKeyConstraint(["created_by_actor_profile_id"], ["actor_profiles.id"]),
        sa.ForeignKeyConstraint(["created_via_identity_link_id"], ["actor_identity_links.id"]),
        sa.ForeignKeyConstraint(["authorization_decision_event_id"], ["audit_events.id"]),
        sa.UniqueConstraint("attempt_id", name="uq_project_guide_compilation_attempt"),
        sa.UniqueConstraint("id", "attempt_id", name="uq_project_guide_compilation_id_attempt"),
        sa.UniqueConstraint("supersedes_compilation_id", name="uq_project_guide_compilation_predecessor"),
        sa.UniqueConstraint("id", "project_id", "guide_id", name="uq_project_guide_compilation_scope"),
        sa.ForeignKeyConstraint(
            ["supersedes_compilation_id", "project_id", "guide_id"],
            ["project_guide_compilations.id", "project_guide_compilations.project_id", "project_guide_compilations.guide_id"],
            name="fk_project_guide_compilation_predecessor",
        ),
        sa.CheckConstraint(
            f"source_snapshot_hash ~ '{_HASH}' and canonical_input_hash ~ '{_HASH}' and guide_material_hash ~ '{_HASH}' and pre_catalogue_manifest_hash ~ '{_HASH}' and post_catalogue_manifest_hash ~ '{_HASH}' and result_hash ~ '{_HASH}'",
            name="ck_project_guide_compilation_hashes",
        ),
        sa.CheckConstraint(
            "octet_length(canonical_result::text) <= 4194304 and "
            "json_typeof(component_hashes)='object' and "
            "component_hashes::jsonb=jsonb_build_object("
            "'sufficiency_hash',component_hashes->>'sufficiency_hash',"
            "'artifact_policy_hash',component_hashes->>'artifact_policy_hash',"
            "'requirement_inventory_hash',component_hashes->>'requirement_inventory_hash',"
            "'pre_submit_hash',component_hashes->>'pre_submit_hash',"
            "'post_submit_hash',component_hashes->>'post_submit_hash',"
            "'capability_suggestions_hash',component_hashes->>'capability_suggestions_hash',"
            "'setup_notes_hash',component_hashes->>'setup_notes_hash') and "
            + " and ".join(
                f"coalesce((component_hashes->>'{name}') ~ '{_HASH}',false)"
                for name in (
                    "sufficiency_hash", "artifact_policy_hash", "requirement_inventory_hash",
                    "pre_submit_hash", "post_submit_hash", "capability_suggestions_hash",
                    "setup_notes_hash",
                )
            ),
            name="ck_project_guide_compilation_result_shape",
        ),
        sa.CheckConstraint(
            "setup_generation > 0 and created_by_service_identity='workstream.project.setup' and creation_action_id='project.guide_compilation.execute'",
            name="ck_project_guide_compilation_custody",
        ),
        sa.CheckConstraint(
            f"authorization_resource_context_digest ~ '{_HASH}'",
            name="ck_project_guide_compilation_authorization_digest",
        ),
    )
    op.create_index(
        "uq_project_guide_compilation_root",
        "project_guide_compilations",
        ["project_id", "guide_id"],
        unique=True,
        postgresql_where=sa.text("supersedes_compilation_id is null"),
    )
    for column in ("project_id", "guide_id", "source_snapshot_id", "setup_run_id"):
        op.create_index(f"ix_project_guide_compilations_{column}", "project_guide_compilations", [column])
    op.create_foreign_key(
        "fk_compilation_attempt_exact_persisted_compilation",
        "project_guide_compilation_attempts",
        "project_guide_compilations",
        ["persisted_compilation_id", "id"],
        ["id", "attempt_id"],
    )
    _install_guards()


def _install_guards() -> None:
    statements = (
        """
        create function guard_project_guide_compilation_attempt_update()
        returns trigger language plpgsql as $$
        begin
          if row(new.project_id,new.guide_id,new.guide_version,new.source_snapshot_id,
            new.source_snapshot_hash,new.setup_run_id,new.setup_generation,
            new.canonical_input_hash,new.guide_material_hash,new.pre_catalogue_id,
            new.pre_catalogue_version,new.pre_catalogue_schema_version,
            new.pre_catalogue_manifest_hash,new.post_catalogue_id,new.post_catalogue_version,
            new.post_catalogue_schema_version,new.post_catalogue_manifest_hash,
            new.agent_identity,new.agent_version,new.instruction_version,
            new.provider_idempotency_key)
          is distinct from row(old.project_id,old.guide_id,old.guide_version,old.source_snapshot_id,
            old.source_snapshot_hash,old.setup_run_id,old.setup_generation,
            old.canonical_input_hash,old.guide_material_hash,old.pre_catalogue_id,
            old.pre_catalogue_version,old.pre_catalogue_schema_version,
            old.pre_catalogue_manifest_hash,old.post_catalogue_id,old.post_catalogue_version,
            old.post_catalogue_schema_version,old.post_catalogue_manifest_hash,
            old.agent_identity,old.agent_version,old.instruction_version,
            old.provider_idempotency_key) then raise exception 'compilation attempt identity is immutable'; end if;
          if old.status in ('persisted','invalid_terminal') then raise exception 'terminal compilation attempt is immutable'; end if;
          if new.reserved_at is distinct from old.reserved_at then
            raise exception 'compilation reservation timestamp is immutable';
          end if;
          if new.provider_uncertain_at is distinct from old.provider_uncertain_at and
            not (old.status='reserved' and new.status='provider_uncertain') then
            raise exception 'provider uncertainty timestamp is immutable';
          end if;
          if new.accepted_at is distinct from old.accepted_at and
            not (old.status in ('reserved','provider_uncertain') and new.status='accepted') then
            raise exception 'accepted timestamp is immutable';
          end if;
          if new.terminal_at is distinct from old.terminal_at and
            not (old.status in ('reserved','provider_uncertain') and new.status='invalid_terminal') then
            raise exception 'terminal timestamp is immutable';
          end if;
          if row(new.persisted_at,new.persisted_compilation_id) is distinct from
            row(old.persisted_at,old.persisted_compilation_id) and
            not (old.status='accepted' and new.status='persisted') then
            raise exception 'persisted custody is immutable';
          end if;
          if old.status='accepted' and row(new.canonical_result::jsonb,new.result_hash,new.component_hashes::jsonb,new.accepted_at)
            is distinct from row(old.canonical_result::jsonb,old.result_hash,old.component_hashes::jsonb,old.accepted_at) then
            raise exception 'accepted compilation result is immutable';
          end if;
          if not ((old.status='reserved' and new.status in ('provider_uncertain','accepted','invalid_terminal')) or
                  (old.status='provider_uncertain' and new.status in ('accepted','invalid_terminal')) or
                  (old.status='accepted' and new.status='persisted')) then
            raise exception 'invalid compilation attempt transition';
          end if;
          return new;
        end $$
        """,
        """
        create trigger trg_compilation_attempt_update before update on project_guide_compilation_attempts
          for each row execute function guard_project_guide_compilation_attempt_update()
        """,
        """
        create function reject_project_guide_compilation_mutation()
        returns trigger language plpgsql as $$ begin raise exception 'compilation custody is append-only'; end $$
        """,
        """
        create trigger trg_compilation_attempt_delete before delete or truncate on project_guide_compilation_attempts
          for each statement execute function reject_project_guide_compilation_mutation()
        """,
        """
        create function guard_project_guide_compilation_insert()
        returns trigger language plpgsql as $$
        declare predecessor_generation bigint;
        declare source_attempt project_guide_compilation_attempts%rowtype;
        begin
          select * into source_attempt from project_guide_compilation_attempts
            where id=new.attempt_id for update;
          if source_attempt.id is null or source_attempt.status <> 'accepted' or
            row(new.project_id,new.guide_id,new.guide_version,new.source_snapshot_id,
              new.source_snapshot_hash,new.setup_run_id,new.setup_generation,
              new.canonical_input_hash,new.guide_material_hash,
              new.pre_catalogue_manifest_hash,new.post_catalogue_manifest_hash,
              new.agent_identity,new.agent_version,new.instruction_version,
              new.canonical_result::jsonb,new.result_hash,new.component_hashes::jsonb)
            is distinct from
            row(source_attempt.project_id,source_attempt.guide_id,
              source_attempt.guide_version,source_attempt.source_snapshot_id,
              source_attempt.source_snapshot_hash,source_attempt.setup_run_id,
              source_attempt.setup_generation,source_attempt.canonical_input_hash,
              source_attempt.guide_material_hash,source_attempt.pre_catalogue_manifest_hash,
              source_attempt.post_catalogue_manifest_hash,source_attempt.agent_identity,
              source_attempt.agent_version,source_attempt.instruction_version,
              source_attempt.canonical_result::jsonb,source_attempt.result_hash,
              source_attempt.component_hashes::jsonb) then
            raise exception 'compilation does not match its accepted attempt';
          end if;
          if not exists(
            select 1 from audit_events event
            join actor_profiles profile on profile.id=new.created_by_actor_profile_id
            join actor_identity_links link on link.id=new.created_via_identity_link_id
              and link.actor_profile_id=profile.id
            where event.id=new.authorization_decision_event_id
              and event.event_domain='authority'
              and event.event_type='SensitiveAuthorizationAllowed'
              and event.denial_code is null
              and event.actor_id=new.created_by_actor_profile_id
              and event.permission_id='project.guide_compilation.execute'
              and event.action_id='project.guide_compilation.execute'
              and event.project_id=new.project_id
              and event.resource_type='project_guide_compilation_attempt'
              and event.resource_id=new.attempt_id::text
              and event.after_facts->>'allowed'='true'
              and event.after_facts->>'resource_context_digest'=
                new.authorization_resource_context_digest
              and profile.actor_kind='service' and profile.status='active'
              and profile.service_identity='workstream.project.setup'
              and link.subject_kind='service' and link.status='active'
              and link.issuer='workstream-internal'
              and link.subject='workstream.project.setup'
          ) then
            raise exception 'compilation authorization evidence is invalid';
          end if;
          if new.supersedes_compilation_id is null then return new; end if;
          select setup_generation into predecessor_generation
            from project_guide_compilations
            where id=new.supersedes_compilation_id
              and project_id=new.project_id and guide_id=new.guide_id;
          if predecessor_generation is null or predecessor_generation >= new.setup_generation then
            raise exception 'compilation generation must strictly advance';
          end if;
          return new;
        end $$
        """,
        """
        create trigger trg_compilation_insert before insert on project_guide_compilations
          for each row execute function guard_project_guide_compilation_insert()
        """,
        """
        create trigger trg_compilation_mutation before update or delete or truncate on project_guide_compilations
          for each statement execute function reject_project_guide_compilation_mutation()
        """
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    """Remove only the hidden compilation foundation."""
    connection = op.get_bind()
    connection.execute(sa.text("lock table audit_events in access exclusive mode"))
    retained = connection.execute(
        sa.text(
            "select exists(select 1 from project_guide_compilation_attempts) or "
            "exists(select 1 from project_guide_compilations) or "
            "exists(select 1 from audit_events where action_id=:action)"
        ),
        {"action": _ACTION},
    ).scalar_one()
    if retained:
        raise RuntimeError("cannot downgrade non-empty guide-compilation custody")
    op.execute("drop trigger if exists trg_compilation_mutation on project_guide_compilations")
    op.execute("drop trigger if exists trg_compilation_insert on project_guide_compilations")
    op.execute("drop trigger if exists trg_compilation_attempt_delete on project_guide_compilation_attempts")
    op.execute("drop trigger if exists trg_compilation_attempt_update on project_guide_compilation_attempts")
    op.execute("drop function if exists reject_project_guide_compilation_mutation()")
    op.execute("drop function if exists guard_project_guide_compilation_insert()")
    op.execute("drop function if exists guard_project_guide_compilation_attempt_update()")
    op.drop_constraint("fk_compilation_attempt_exact_persisted_compilation", "project_guide_compilation_attempts", type_="foreignkey")
    op.drop_table("project_guide_compilations")
    op.drop_table("project_guide_compilation_attempts")
    _rewrite_action_evidence(add=False)
    _rewrite_permission_registry(add=False)
    _rewrite_audit_resource(add=False)
