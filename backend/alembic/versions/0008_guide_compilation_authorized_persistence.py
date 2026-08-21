"""Install authorized project-guide compilation request custody."""

from alembic import op
import sqlalchemy as sa

revision = "0008_guide_compilation_authorized_persistence"
down_revision = "0007_contribution_policy_publication_custody"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_compilation_attempt_exact_request",
        "project_guide_compilation_attempts",
        [
            "id",
            "project_id",
            "guide_id",
            "source_snapshot_id",
            "setup_run_id",
            "setup_generation",
        ],
    )
    op.create_table(
        "project_guide_compilation_request_operations",
        sa.Column("operation_id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("actor_profile_id", sa.String(36), nullable=False),
        sa.Column("identity_link_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("guide_id", sa.String(36), nullable=False),
        sa.Column("source_snapshot_id", sa.String(36), nullable=False),
        sa.Column("setup_run_id", sa.String(36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("expected_predecessor_compilation_id", sa.Uuid()),
        sa.Column("request_facts_digest", sa.String(71), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_decision_event_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["actor_profile_id"],
            ["actor_profiles.id"],
            name="fk_compilation_request_actor",
        ),
        sa.ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
            name="fk_compilation_request_actor_link",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_compilation_request_project"
        ),
        sa.ForeignKeyConstraint(
            ["guide_id"], ["project_guides.id"], name="fk_compilation_request_guide"
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id", "project_id", "guide_id"],
            [
                "guide_source_snapshots.id",
                "guide_source_snapshots.project_id",
                "guide_source_snapshots.guide_id",
            ],
            name="fk_compilation_request_snapshot",
        ),
        sa.ForeignKeyConstraint(
            [
                "setup_run_id",
                "project_id",
                "guide_id",
                "source_snapshot_id",
                "setup_generation",
            ],
            [
                "project_setup_runs.id",
                "project_setup_runs.project_id",
                "project_setup_runs.guide_id",
                "project_setup_runs.source_snapshot_id",
                "project_setup_runs.setup_generation",
            ],
            name="fk_compilation_request_setup",
        ),
        sa.ForeignKeyConstraint(
            [
                "attempt_id",
                "project_id",
                "guide_id",
                "source_snapshot_id",
                "setup_run_id",
                "setup_generation",
            ],
            [
                "project_guide_compilation_attempts.id",
                "project_guide_compilation_attempts.project_id",
                "project_guide_compilation_attempts.guide_id",
                "project_guide_compilation_attempts.source_snapshot_id",
                "project_guide_compilation_attempts.setup_run_id",
                "project_guide_compilation_attempts.setup_generation",
            ],
            name="fk_compilation_request_exact_attempt",
        ),
        sa.ForeignKeyConstraint(
            ["expected_predecessor_compilation_id", "project_id", "guide_id"],
            [
                "project_guide_compilations.id",
                "project_guide_compilations.project_id",
                "project_guide_compilations.guide_id",
            ],
            name="fk_compilation_request_predecessor",
        ),
        sa.ForeignKeyConstraint(
            ["authorization_decision_event_id"],
            ["audit_events.id"],
            name="fk_compilation_request_authorization_event",
        ),
        sa.UniqueConstraint(
            "actor_profile_id",
            "request_id",
            name="uq_compilation_request_actor_request",
        ),
        sa.UniqueConstraint(
            "actor_profile_id",
            "idempotency_key",
            name="uq_compilation_request_actor_key",
        ),
        sa.UniqueConstraint("attempt_id", name="uq_compilation_request_attempt"),
        sa.UniqueConstraint(
            "authorization_decision_event_id",
            name="uq_compilation_request_authorization_event",
        ),
        sa.CheckConstraint(
            "setup_generation > 0", name="ck_compilation_request_generation"
        ),
        sa.CheckConstraint(
            "request_facts_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_compilation_request_facts_digest",
        ),
    )
    _install_digest_functions()
    _install_custody_guards()


def _install_digest_functions() -> None:
    op.execute(
        r"""
        create function project_guide_compilation_request_facts_digest(
          op project_guide_compilation_request_operations,
          attempt project_guide_compilation_attempts
        ) returns text immutable strict language sql as $$
          select 'sha256:' || encode(sha256(convert_to(
            '{"domain":"workstream.project_guide_compilation.facts.v1","facts":{' ||
            '"agent_identity":' || to_json(attempt.agent_identity)::text || ',' ||
            '"agent_version":' || to_json(attempt.agent_version)::text || ',' ||
            '"canonical_input_hash":' || to_json(attempt.canonical_input_hash)::text || ',' ||
            '"expected_predecessor_compilation_id":' ||
              coalesce(to_json(op.expected_predecessor_compilation_id::text)::text, 'null') || ',' ||
            '"guide_id":' || to_json(op.guide_id)::text || ',' ||
            '"guide_material_hash":' || to_json(attempt.guide_material_hash)::text || ',' ||
            '"guide_version":' || to_json(attempt.guide_version)::text || ',' ||
            '"idempotency_key":' || to_json(op.idempotency_key::text)::text || ',' ||
            '"instruction_version":' || to_json(attempt.instruction_version)::text || ',' ||
            '"operation_id":' || to_json(op.operation_id::text)::text || ',' ||
            '"post_catalogue_id":' || to_json(attempt.post_catalogue_id)::text || ',' ||
            '"post_catalogue_manifest_hash":' || to_json(attempt.post_catalogue_manifest_hash)::text || ',' ||
            '"post_catalogue_schema_version":' || to_json(attempt.post_catalogue_schema_version)::text || ',' ||
            '"post_catalogue_version":' || to_json(attempt.post_catalogue_version)::text || ',' ||
            '"pre_catalogue_id":' || to_json(attempt.pre_catalogue_id)::text || ',' ||
            '"pre_catalogue_manifest_hash":' || to_json(attempt.pre_catalogue_manifest_hash)::text || ',' ||
            '"pre_catalogue_schema_version":' || to_json(attempt.pre_catalogue_schema_version)::text || ',' ||
            '"pre_catalogue_version":' || to_json(attempt.pre_catalogue_version)::text || ',' ||
            '"project_id":' || to_json(op.project_id)::text || ',' ||
            '"request_id":' || to_json(op.request_id::text)::text || ',' ||
            '"setup_generation":' || op.setup_generation::text || ',' ||
            '"setup_run_id":' || to_json(op.setup_run_id)::text || ',' ||
            '"source_snapshot_hash":' || to_json(attempt.source_snapshot_hash)::text || ',' ||
            '"source_snapshot_id":' || to_json(op.source_snapshot_id)::text || '}}',
            'UTF8')), 'hex')
        $$
        """
    )
    op.execute(
        r"""
        create function project_guide_compilation_request_authority_digest(
          op project_guide_compilation_request_operations,
          grant_row admin_role_grants
        ) returns text immutable strict language sql as $$
          select 'sha256:' || encode(sha256(convert_to(
            '{"action_id":"project.guide_compilation.request",' ||
            '"actor_profile_id":' || to_json(op.actor_profile_id)::text || ',' ||
            '"identity_link_id":' || to_json(op.identity_link_id)::text || ',' ||
            '"permission_id":"project.guide_compilation.request",' ||
            '"project_manager_grant_id":' || to_json(grant_row.id::text)::text || ',' ||
            '"request_facts_digest":' || to_json(op.request_facts_digest)::text || ',' ||
            '"resource_id":' || to_json(op.operation_id::text)::text || ',' ||
            '"resource_type":"project_guide_compilation_request",' ||
            '"scope_project_id":' || to_json(op.project_id)::text || '}',
            'UTF8')), 'hex')
        $$
        """
    )


def _install_custody_guards() -> None:
    op.execute(
        """
        create function guard_project_guide_compilation_request_operation()
        returns trigger language plpgsql as $$
        declare
          attempt project_guide_compilation_attempts%rowtype;
          event audit_events%rowtype;
          grant_row admin_role_grants%rowtype;
        begin
          select * into attempt from project_guide_compilation_attempts
            where id=new.attempt_id;
          select * into event from audit_events
            where id=new.authorization_decision_event_id;
          select * into grant_row from admin_role_grants
            where id=event.matched_grant_id::uuid;
          if attempt.id is null or event.id is null or grant_row.id is null then
            raise exception 'guide compilation request references are invalid'
              using errcode='23514';
          end if;
          if new.request_facts_digest is distinct from
                project_guide_compilation_request_facts_digest(new, attempt) then
            raise exception 'guide compilation request facts digest is invalid'
              using errcode='23514';
          end if;
          if event.event_domain is distinct from 'authority'
             or event.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or event.action_id is distinct from 'project.guide_compilation.request'
             or event.permission_id is distinct from 'project.guide_compilation.request'
             or event.resource_type is distinct from 'project_guide_compilation_request'
             or event.resource_id is distinct from new.operation_id::text
             or event.project_id is distinct from new.project_id
             or event.actor_id is distinct from new.actor_profile_id
             or event.actor_ref_kind is distinct from 'actor_profile'
             or event.after_facts->>'allowed' is distinct from 'true' then
            raise exception 'guide compilation request audit event is invalid'
              using errcode='23514';
          end if;
          if grant_row.target_actor_profile_id is distinct from new.actor_profile_id
             or grant_row.role is distinct from 'project_manager'
             or grant_row.status is distinct from 'active'
             or grant_row.scope_type is distinct from 'project'
             or grant_row.scope_project_id is distinct from new.project_id then
            raise exception 'guide compilation request grant is invalid'
              using errcode='23514';
          end if;
          if event.after_facts->>'resource_context_digest' is distinct from
                project_guide_compilation_request_authority_digest(new, grant_row) then
            raise exception 'guide compilation request authority digest is invalid'
              using errcode='23514';
          end if;
          return new;
        end;
        $$
        """
    )
    op.execute(
        """
        create function reject_project_guide_compilation_request_change()
        returns trigger language plpgsql as $$
        begin
          raise exception 'guide compilation request custody is immutable'
            using errcode='55000';
        end;
        $$
        """
    )
    op.execute(
        "create trigger guide_compilation_request_insert_guard before insert on "
        "project_guide_compilation_request_operations for each row execute function "
        "guard_project_guide_compilation_request_operation()"
    )
    op.execute(
        "create trigger guide_compilation_request_change_guard before update or delete on "
        "project_guide_compilation_request_operations for each row execute function "
        "reject_project_guide_compilation_request_change()"
    )
    op.execute(
        "create trigger guide_compilation_request_truncate_guard before truncate on "
        "project_guide_compilation_request_operations execute function "
        "reject_project_guide_compilation_request_change()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    protected = connection.execute(
        sa.text(
            "select exists(select 1 from project_guide_compilation_request_operations) "
            "or exists(select 1 from project_guide_compilation_attempts) "
            "or exists(select 1 from project_guide_compilations) "
            "or exists(select 1 from audit_events where action_id in "
            "('project.guide_compilation.request','project.guide_compilation.execute'))"
        )
    ).scalar_one()
    if protected:
        raise RuntimeError("guide compilation custody is non-empty; downgrade refused")
    op.execute("drop trigger guide_compilation_request_insert_guard on project_guide_compilation_request_operations")
    op.execute("drop trigger guide_compilation_request_change_guard on project_guide_compilation_request_operations")
    op.execute("drop trigger guide_compilation_request_truncate_guard on project_guide_compilation_request_operations")
    op.execute("drop function project_guide_compilation_request_authority_digest")
    op.execute("drop function project_guide_compilation_request_facts_digest")
    op.execute("drop function reject_project_guide_compilation_request_change")
    op.execute("drop function guard_project_guide_compilation_request_operation")
    op.drop_table("project_guide_compilation_request_operations")
    op.drop_constraint(
        "uq_compilation_attempt_exact_request",
        "project_guide_compilation_attempts",
        type_="unique",
    )
