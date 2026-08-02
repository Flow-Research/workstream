"""activate authorized review and revision policy mutation

Revision ID: 0048_policy_authority
Revises: 0047_policy_identity_lineage
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0048_policy_authority"
down_revision = "0047_policy_identity_lineage"
branch_labels = depends_on = None


_PROVENANCE_COLUMNS = (
    ("predecessor_policy_hash", sa.String(71)),
    ("created_by_actor_profile_id", sa.String(36)),
    ("created_via_identity_link_id", sa.String(36)),
    ("created_by_admin_role_grant_id", sa.Uuid()),
    ("creation_scope_type", sa.String(16)),
    ("creation_scope_project_id", sa.String(36)),
    ("creation_action_id", sa.String(160)),
    ("authorization_decision_event_id", sa.String(36)),
)


def _add_policy_authority(table: str, kind: str) -> None:
    for name, type_ in _PROVENANCE_COLUMNS:
        op.add_column(table, sa.Column(name, type_))
    op.create_foreign_key(
        f"fk_{table}_actor_profile",
        table,
        "actor_profiles",
        ["created_by_actor_profile_id"],
        ["id"],
    )
    op.create_foreign_key(
        f"fk_{table}_identity_link",
        table,
        "actor_identity_links",
        ["created_via_identity_link_id"],
        ["id"],
    )
    op.create_foreign_key(
        f"fk_{table}_admin_grant",
        table,
        "admin_role_grants",
        ["created_by_admin_role_grant_id"],
        ["id"],
    )
    op.create_foreign_key(
        f"fk_{table}_decision_event",
        table,
        "audit_events",
        ["authorization_decision_event_id"],
        ["id"],
    )
    op.create_check_constraint(
        f"{kind}_policy_predecessor_shape",
        table,
        "(supersedes_policy_id is null and predecessor_policy_hash is null and "
        "policy_generation = 1) or (supersedes_policy_id is not null and "
        "predecessor_policy_hash ~ '^sha256:[0-9a-f]{64}$' and policy_generation > 1) "
        "or semantics_status='legacy_incomplete'",
    )
    op.create_check_constraint(
        f"{kind}_policy_authority_shape",
        table,
        "semantics_status='legacy_incomplete' or "
        "(created_by_actor_profile_id is not null and "
        "created_via_identity_link_id is not null and "
        "created_by_admin_role_grant_id is not null and "
        "creation_scope_type in ('system','project') and "
        f"creation_action_id='project.{kind}_policy.update' and "
        "authorization_decision_event_id is not null)",
    )


def upgrade() -> None:
    """Install one replay ledger and complete policy mutation provenance."""
    op.drop_constraint("policy_selection_shape", "project_guides", type_="check")
    op.create_check_constraint(
        "policy_selection_shape",
        "project_guides",
        "((selected_review_policy_id is null and "
        "selected_review_policy_generation is null and selected_review_policy_hash is null) or "
        "(selected_review_policy_id is not null and "
        "selected_review_policy_generation is not null and "
        "selected_review_policy_hash is not null)) and "
        "((selected_revision_policy_id is null and "
        "selected_revision_policy_generation is null and "
        "selected_revision_policy_hash is null) or "
        "(selected_revision_policy_id is not null and "
        "selected_revision_policy_generation is not null and "
        "selected_revision_policy_hash is not null))",
    )
    _add_policy_authority("review_policies", "review")
    _add_policy_authority("revision_policies", "revision")
    op.create_table(
        "policy_mutation_idempotency_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "actor_profile_id", sa.String(36), sa.ForeignKey("actor_profiles.id"), nullable=False
        ),
        sa.Column(
            "identity_link_id",
            sa.String(36),
            sa.ForeignKey("actor_identity_links.id"),
            nullable=False,
        ),
        sa.Column("action_id", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("policy_hash", sa.String(71), nullable=False),
        sa.Column("resource_context_digest", sa.String(71), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("guide_id", sa.String(36), sa.ForeignKey("project_guides.id"), nullable=False),
        sa.Column("policy_id", sa.String(36), nullable=False),
        sa.Column("policy_generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response_json", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "actor_profile_id",
            "action_id",
            "idempotency_key",
            name="uq_policy_mutation_replay_namespace",
        ),
        sa.UniqueConstraint("operation_id", name="uq_policy_mutation_operation_identity"),
        sa.CheckConstraint(
            "action_id in ('project.review_policy.update','project.revision_policy.update')",
            name="ck_policy_mutation_action",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "policy_hash ~ '^sha256:[0-9a-f]{64}$' and "
            "resource_context_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_policy_mutation_digests",
        ),
        sa.CheckConstraint("policy_generation > 0", name="ck_policy_mutation_generation"),
        sa.CheckConstraint("status in ('pending','committed')", name="ck_policy_mutation_status"),
        sa.CheckConstraint(
            "(status='pending' and response_json is null and committed_at is null) or "
            "(status='committed' and response_json is not null and committed_at is not null)",
            name="ck_policy_mutation_state_shape",
        ),
    )
    op.execute(
        """
        create function guard_policy_mutation_replay() returns trigger language plpgsql as $$
        begin
          if tg_op='INSERT' then
            if new.status<>'pending' then
              raise exception 'policy mutation must begin pending' using errcode='23514';
            end if;
            return new;
          elsif tg_op='DELETE' then
            raise exception 'policy mutation replay is immutable' using errcode='55000';
          elsif new is not distinct from old then
            return new;
          elsif old.status='pending' and new.status='committed'
             and (new.id,new.actor_profile_id,new.identity_link_id,new.action_id,
                  new.idempotency_key,new.request_digest,new.policy_hash,
                  new.resource_context_digest,
                  new.operation_id,new.project_id,new.guide_id,new.policy_id,
                  new.policy_generation)
                 is not distinct from
                 (old.id,old.actor_profile_id,old.identity_link_id,old.action_id,
                  old.idempotency_key,old.request_digest,old.policy_hash,
                  old.resource_context_digest,
                  old.operation_id,old.project_id,old.guide_id,old.policy_id,
                  old.policy_generation) then
            return new;
          end if;
          raise exception 'policy mutation replay is immutable' using errcode='23514';
        end $$
        """
    )
    op.execute(
        "create trigger policy_mutation_replay_immutable before insert or update or delete "
        "on policy_mutation_idempotency_records for each row "
        "execute function guard_policy_mutation_replay()"
    )
    op.execute(
        """
        create function reject_policy_mutation_replay_truncate() returns trigger
        language plpgsql as $$ begin
          raise exception 'policy mutation replay is immutable' using errcode='55000';
        end $$
        """
    )
    op.execute(
        "create trigger policy_mutation_replay_reject_truncate before truncate "
        "on policy_mutation_idempotency_records "
        "execute function reject_policy_mutation_replay_truncate()"
    )
    op.execute(
        """
        create function validate_policy_mutation_custody() returns trigger language plpgsql as $$
        declare reservation policy_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
                actor_id text; link_id text; grant_id uuid; action_value text;
                scope_type text; scope_project text; decision_id text;
                product_project text; product_guide text; product_id text;
                product_generation integer;
                product_hash text; predecessor_id text; predecessor_hash text;
                selector_id text; selector_generation integer; selector_hash text;
                predecessor_valid boolean;
        begin
          if tg_table_name='policy_mutation_idempotency_records' then
            select * into reservation from policy_mutation_idempotency_records where id=new.id;
            if reservation.status<>'committed' then
              raise exception 'pending policy mutation custody cannot commit' using errcode='23514';
            end if;
            if reservation.action_id='project.review_policy.update' then
              select created_by_actor_profile_id,created_via_identity_link_id,
                     created_by_admin_role_grant_id,creation_action_id,
                     creation_scope_type,creation_scope_project_id,
                     authorization_decision_event_id,p.project_id,g.id,p.id,
                     p.policy_generation,p.policy_hash,p.supersedes_policy_id,
                     p.predecessor_policy_hash,g.selected_review_policy_id,
                     g.selected_review_policy_generation,g.selected_review_policy_hash
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_guide,product_id,product_generation,
                     product_hash,predecessor_id,predecessor_hash,selector_id,
                     selector_generation,selector_hash
                from review_policies p join project_guides g
                  on g.project_id=p.project_id and g.version=p.guide_version
                where p.id=reservation.policy_id and g.id=reservation.guide_id;
            else
              select created_by_actor_profile_id,created_via_identity_link_id,
                     created_by_admin_role_grant_id,creation_action_id,
                     creation_scope_type,creation_scope_project_id,
                     authorization_decision_event_id,p.project_id,g.id,p.id,
                     p.policy_generation,p.policy_hash,p.supersedes_policy_id,
                     p.predecessor_policy_hash,g.selected_revision_policy_id,
                     g.selected_revision_policy_generation,g.selected_revision_policy_hash
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_guide,product_id,product_generation,
                     product_hash,predecessor_id,predecessor_hash,selector_id,
                     selector_generation,selector_hash
                from revision_policies p join project_guides g
                  on g.project_id=p.project_id and g.version=p.guide_version
                where p.id=reservation.policy_id and g.id=reservation.guide_id;
            end if;
          else
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            action_value:=new.creation_action_id;
            scope_type:=new.creation_scope_type;
            scope_project:=new.creation_scope_project_id;
            decision_id:=new.authorization_decision_event_id;
            product_project:=new.project_id; product_id:=new.id;
            product_generation:=new.policy_generation; product_hash:=new.policy_hash;
            predecessor_id:=new.supersedes_policy_id;
            predecessor_hash:=new.predecessor_policy_hash;
            if tg_table_name='review_policies' then
              select g.id,g.selected_review_policy_id,g.selected_review_policy_generation,
                     g.selected_review_policy_hash
                into product_guide,selector_id,selector_generation,selector_hash
                from project_guides g
                where g.project_id=new.project_id and g.version=new.guide_version;
            else
              select g.id,g.selected_revision_policy_id,g.selected_revision_policy_generation,
                     g.selected_revision_policy_hash
                into product_guide,selector_id,selector_generation,selector_hash
                from project_guides g
                where g.project_id=new.project_id and g.version=new.guide_version;
            end if;
            select r.* into reservation from policy_mutation_idempotency_records r
              where r.policy_id=new.id and r.action_id=new.creation_action_id
                and r.policy_generation=new.policy_generation and r.status='committed';
          end if;
          if reservation.id is null or product_id is null
             or reservation.actor_profile_id is distinct from actor_id
             or reservation.identity_link_id is distinct from link_id
             or reservation.action_id is distinct from action_value
             or reservation.project_id is distinct from product_project
             or reservation.guide_id is distinct from product_guide
             or reservation.policy_id is distinct from product_id
             or reservation.policy_generation is distinct from product_generation
             or reservation.policy_hash is distinct from product_hash
             or selector_id is distinct from product_id
             or selector_generation is distinct from product_generation
             or selector_hash is distinct from product_hash
             or scope_type not in ('system','project')
             or (scope_type='project' and scope_project is distinct from product_project)
             or (scope_type='system' and scope_project is not null) then
            raise exception 'policy mutation custody mismatch' using errcode='23514';
          end if;
          if product_generation=1 then
            predecessor_valid:=predecessor_id is null and predecessor_hash is null;
          elsif reservation.action_id='project.review_policy.update' then
            select exists(select 1 from review_policies prior
              where prior.id=predecessor_id and prior.project_id=product_project
                and prior.guide_version=(select version from project_guides where id=product_guide)
                and prior.policy_generation=product_generation-1
                and prior.policy_hash=predecessor_hash) into predecessor_valid;
          else
            select exists(select 1 from revision_policies prior
              where prior.id=predecessor_id and prior.project_id=product_project
                and prior.guide_version=(select version from project_guides where id=product_guide)
                and prior.policy_generation=product_generation-1
                and prior.policy_hash=predecessor_hash) into predecessor_valid;
          end if;
          if predecessor_valid is not true then
            raise exception 'policy mutation lineage mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=decision_id;
          if evidence.id is null or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from actor_id
             or evidence.matched_grant_id is distinct from grant_id::text
             or evidence.permission_id is distinct from 'project.review_policy.manage'
             or evidence.action_id is distinct from action_value
             or evidence.resource_type is distinct from 'project'
             or evidence.resource_id is distinct from product_project
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from product_project
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'policy mutation evidence mismatch' using errcode='23514';
          end if;
          return null;
        end $$
        """
    )
    for name, table in (
        ("review_policy_mutation_custody", "review_policies"),
        ("revision_policy_mutation_custody", "revision_policies"),
        ("policy_mutation_replay_custody", "policy_mutation_idempotency_records"),
    ):
        op.execute(
            f"create constraint trigger {name} after insert or update on {table} "
            "deferrable initially deferred for each row "
            "execute function validate_policy_mutation_custody()"
        )


def downgrade() -> None:
    """Remove 02B authority state while preserving 02A policy lineage."""
    bind = op.get_bind()
    has_custody = bool(
        bind.scalar(
            sa.text(
                "select exists(select 1 from policy_mutation_idempotency_records) or "
                "exists(select 1 from review_policies where creation_action_id="
                "'project.review_policy.update') or exists(select 1 from revision_policies "
                "where creation_action_id='project.revision_policy.update')"
            )
        )
    )
    if has_custody:
        raise RuntimeError("cannot downgrade populated policy mutation authority")
    for name, table in (
        ("review_policy_mutation_custody", "review_policies"),
        ("revision_policy_mutation_custody", "revision_policies"),
        ("policy_mutation_replay_custody", "policy_mutation_idempotency_records"),
    ):
        op.execute(f"drop trigger {name} on {table}")
    op.execute("drop function validate_policy_mutation_custody()")
    op.execute(
        "drop trigger policy_mutation_replay_reject_truncate on policy_mutation_idempotency_records"
    )
    op.execute("drop function reject_policy_mutation_replay_truncate()")
    op.execute(
        "drop trigger policy_mutation_replay_immutable on policy_mutation_idempotency_records"
    )
    op.execute("drop function guard_policy_mutation_replay()")
    op.drop_table("policy_mutation_idempotency_records")
    for table, kind in (("revision_policies", "revision"), ("review_policies", "review")):
        op.drop_constraint(f"{kind}_policy_authority_shape", table, type_="check")
        op.drop_constraint(f"{kind}_policy_predecessor_shape", table, type_="check")
        for suffix in ("decision_event", "admin_grant", "identity_link", "actor_profile"):
            op.drop_constraint(f"fk_{table}_{suffix}", table, type_="foreignkey")
        for name, _type in reversed(_PROVENANCE_COLUMNS):
            op.drop_column(table, name)
    op.drop_constraint("policy_selection_shape", "project_guides", type_="check")
    op.create_check_constraint(
        "policy_selection_shape",
        "project_guides",
        "(selected_review_policy_id is null and selected_review_policy_generation is null "
        "and selected_review_policy_hash is null and selected_revision_policy_id is null "
        "and selected_revision_policy_generation is null and "
        "selected_revision_policy_hash is null) or (selected_review_policy_id is not null "
        "and selected_review_policy_generation is not null and "
        "selected_review_policy_hash is not null and selected_revision_policy_id is not null "
        "and selected_revision_policy_generation is not null and "
        "selected_revision_policy_hash is not null)",
    )
