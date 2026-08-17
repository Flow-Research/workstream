"""Install ContributionPolicy publication and retirement custody."""

from alembic import op
import sqlalchemy as sa

revision = "0007_contribution_policy_publication_custody"
down_revision = "0006_contribution_policy_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contribution_policy_transition_custody",
        sa.Column("operation_id", sa.Uuid(), primary_key=True),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("actor_profile_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("contribution_policy_id", sa.Uuid(), nullable=False),
        sa.Column("contribution_policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("prior_current_version_id", sa.Uuid()),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_profile_id"], ["actor_profiles.id"],
            name="fk_contribution_policy_custody_actor",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_contribution_policy_custody_project",
        ),
        sa.ForeignKeyConstraint(
            ["contribution_policy_id", "project_id"],
            ["contribution_policies.id", "contribution_policies.project_id"],
            name="fk_contribution_policy_custody_policy",
        ),
        sa.ForeignKeyConstraint(
            ["contribution_policy_version_id", "contribution_policy_id", "project_id"],
            [
                "contribution_policy_versions.id",
                "contribution_policy_versions.contribution_policy_id",
                "contribution_policy_versions.project_id",
            ],
            name="fk_contribution_policy_custody_version",
        ),
        sa.ForeignKeyConstraint(
            ["prior_current_version_id", "contribution_policy_id", "project_id"],
            [
                "contribution_policy_versions.id",
                "contribution_policy_versions.contribution_policy_id",
                "contribution_policy_versions.project_id",
            ],
            name="fk_contribution_policy_custody_prior_version",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_contribution_policy_custody_digest",
        ),
        sa.CheckConstraint(
            "event_type in ('published','retired')",
            name="ck_contribution_policy_custody_event_type",
        ),
    )
    for table, constraint in (
        ("contribution_policies", "fk_contribution_policy_transition_custody"),
        (
            "contribution_policy_versions",
            "fk_contribution_policy_version_transition_custody",
        ),
    ):
        op.add_column(table, sa.Column("last_transition_operation_id", sa.Uuid()))
        op.create_foreign_key(
            constraint,
            table,
            "contribution_policy_transition_custody",
            ["last_transition_operation_id"],
            ["operation_id"],
            deferrable=True,
            initially="DEFERRED",
        )
    op.add_column(
        "contribution_policy_lifecycle_events",
        sa.Column("publication_custody_operation_id", sa.Uuid()),
    )
    op.create_unique_constraint(
        "uq_contribution_policy_event_publication_custody",
        "contribution_policy_lifecycle_events",
        ["publication_custody_operation_id"],
    )
    op.create_foreign_key(
        "fk_contribution_policy_event_publication_custody",
        "contribution_policy_lifecycle_events",
        "contribution_policy_transition_custody",
        ["publication_custody_operation_id"],
        ["operation_id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_check_constraint(
        "ck_contribution_policy_event_custody_shape",
        "contribution_policy_lifecycle_events",
        "(event_type in ('draft_created','draft_updated') and "
        "publication_custody_operation_id is null) or "
        "(event_type in ('published','retired') and "
        "publication_custody_operation_id=operation_id)",
    )
    _install_custody_guards()
    _replace_event_guard()
    _install_graph_guards()


def _install_custody_guards() -> None:
    op.execute(
        """
        create function guard_contribution_policy_transition_custody()
        returns trigger language plpgsql as $$
        declare
          policy contribution_policies%rowtype;
          target contribution_policy_versions%rowtype;
          prior contribution_policy_versions%rowtype;
          event_count integer;
          accepted_count integer;
          review_count integer;
          invalid_rule_count integer;
        begin
          select * into policy from contribution_policies
            where id=new.contribution_policy_id;
          select * into target from contribution_policy_versions
            where id=new.contribution_policy_version_id;
          select count(*) into event_count
            from contribution_policy_lifecycle_events e
            where e.publication_custody_operation_id=new.operation_id
              and e.operation_id=new.operation_id
              and e.request_digest=new.request_digest
              and e.event_type=new.event_type
              and e.actor_profile_id=new.actor_profile_id
              and e.project_id=new.project_id
              and e.contribution_policy_id=new.contribution_policy_id
              and e.contribution_policy_version_id=new.contribution_policy_version_id
              and e.prior_current_version_id is not distinct from new.prior_current_version_id
              and e.occurred_at=new.occurred_at;
          if event_count <> 1
             or policy.last_transition_operation_id is distinct from new.operation_id
             or target.last_transition_operation_id is distinct from new.operation_id then
            raise exception 'invalid contribution policy transition custody'
              using errcode='23514';
          end if;
          if new.event_type='published' then
            if policy.status is distinct from 'active'
               or policy.current_published_version_id is distinct from target.id
               or target.status is distinct from 'published'
               or target.published_by is distinct from new.actor_profile_id
               or target.published_at is distinct from new.occurred_at then
              raise exception 'invalid contribution policy publication custody'
                using errcode='23514';
            end if;
            select count(*) filter (where contribution_type='accepted_submission'),
                   count(*) filter (where contribution_type='completed_review')
              into accepted_count, review_count from contribution_rules
              where contribution_policy_version_id=target.id;
            if accepted_count <> 1 or review_count <> 1 then
              raise exception 'incomplete contribution policy graph'
                using errcode='23514';
            end if;
            select count(*) into invalid_rule_count from contribution_rules r
              where r.contribution_policy_version_id=target.id and (
                (r.compensation_mode='unpaid' and exists (
                  select 1 from contribution_award_definitions d
                  where d.contribution_rule_id=r.id))
                or (r.compensation_mode='compensated' and (
                  select count(*) from contribution_award_definitions d
                  where d.contribution_rule_id=r.id) not between 1 and 2));
            if invalid_rule_count <> 0 then
              raise exception 'incomplete contribution policy definitions'
                using errcode='23514';
            end if;
            if new.prior_current_version_id is not null then
              select * into prior from contribution_policy_versions
                where id=new.prior_current_version_id;
              if prior.status is distinct from 'retired'
                 or prior.last_transition_operation_id is distinct from new.operation_id
                 or prior.retired_by is distinct from new.actor_profile_id
                 or prior.retired_at is distinct from new.occurred_at then
                raise exception 'invalid replacement publication custody'
                  using errcode='23514';
              end if;
            end if;
          else
            if policy.status is distinct from 'retired'
               or policy.current_published_version_id is distinct from target.id
               or policy.retired_by is distinct from new.actor_profile_id
               or policy.retired_at is distinct from new.occurred_at
               or target.status is distinct from 'retired'
               or target.retired_by is distinct from new.actor_profile_id
               or target.retired_at is distinct from new.occurred_at then
              raise exception 'invalid contribution policy retirement custody'
                using errcode='23514';
            end if;
          end if;
          return null;
        end;
        $$
        """
    )


def _replace_event_guard() -> None:
    op.execute(
        """
        create or replace function guard_contribution_policy_event_insert()
        returns trigger language plpgsql as $$
        declare
          policy contribution_policies%rowtype;
          version contribution_policy_versions%rowtype;
          prior_version_number integer;
          custody contribution_policy_transition_custody%rowtype;
        begin
          select * into policy from contribution_policies where id=new.contribution_policy_id;
          select * into version from contribution_policy_versions
            where id=new.contribution_policy_version_id;
          if policy.id is null or version.id is null
             or policy.project_id is distinct from new.project_id
             or version.project_id is distinct from new.project_id
             or version.contribution_policy_id is distinct from new.contribution_policy_id
             or version.version_number is distinct from new.version_number
             or version.status is distinct from new.to_version_status
             or policy.status is distinct from new.to_policy_status then
            raise exception 'invalid contribution policy lifecycle event' using errcode='23514';
          end if;
          if new.prior_current_version_id is not null then
            select version_number into prior_version_number from contribution_policy_versions
              where id=new.prior_current_version_id;
          end if;
          if new.prior_current_version_number is distinct from prior_version_number then
            raise exception 'contribution policy event prior version mismatch'
              using errcode='23514';
          end if;
          if new.event_type in ('draft_created','draft_updated') then
            if new.prior_current_version_id is distinct from policy.current_published_version_id
               or (new.event_type='draft_created' and version.version_number=1
                   and (new.from_policy_status is not null or policy.status <> 'draft'))
               or (new.event_type='draft_created' and version.version_number>1
                   and (new.from_policy_status <> 'active' or policy.status <> 'active'))
               or (new.event_type='draft_updated'
                   and new.from_policy_status is distinct from policy.status) then
              raise exception 'contribution policy event prior state mismatch'
                using errcode='23514';
            end if;
            new.occurred_at := clock_timestamp();
          else
            select * into custody from contribution_policy_transition_custody
              where operation_id=new.publication_custody_operation_id;
            if custody.operation_id is null
               or custody.operation_id is distinct from new.operation_id
               or custody.event_type is distinct from new.event_type then
              raise exception 'contribution policy event custody mismatch'
                using errcode='23514';
            end if;
            new.occurred_at := custody.occurred_at;
          end if;
          if (new.event_type='draft_created'
                 and version.created_by is distinct from new.actor_profile_id)
             or (new.event_type='draft_updated'
                 and version.last_updated_by is distinct from new.actor_profile_id)
             or (new.event_type='published'
                 and version.published_by is distinct from new.actor_profile_id)
             or (new.event_type='retired'
                 and version.retired_by is distinct from new.actor_profile_id) then
            raise exception 'contribution policy event attribution mismatch'
              using errcode='23514';
          end if;
          return new;
        end;
        $$
        """
    )
    op.execute(
        "create constraint trigger contribution_policy_custody_guard "
        "after insert on contribution_policy_transition_custody "
        "deferrable initially deferred for each row execute function "
        "guard_contribution_policy_transition_custody()"
    )
    op.execute(
        "create trigger contribution_policy_custody_change_guard "
        "before update or delete on contribution_policy_transition_custody "
        "for each row execute function reject_contribution_policy_event_change()"
    )
    op.execute(
        "create trigger contribution_policy_custody_truncate_guard "
        "before truncate on contribution_policy_transition_custody execute function "
        "reject_contribution_policy_event_change()"
    )


def _install_graph_guards() -> None:
    op.execute(
        """
        create function guard_published_contribution_policy_graph()
        returns trigger language plpgsql as $$
        declare version_status text;
        begin
          if TG_OP='DELETE' then
            select status into version_status from contribution_policy_versions
              where id=old.contribution_policy_version_id;
          else
            select status into version_status from contribution_policy_versions
              where id=new.contribution_policy_version_id;
          end if;
          if version_status in ('published','retired') then
            raise exception 'published contribution policy graph is immutable'
              using errcode='55000';
          end if;
          if TG_OP='DELETE' then
            return old;
          end if;
          return new;
        end;
        $$
        """
    )
    for table in ("contribution_rules", "contribution_award_definitions"):
        op.execute(
            f"create trigger {table}_published_graph_guard "
            f"before insert or update or delete on {table} for each row execute function "
            "guard_published_contribution_policy_graph()"
        )


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
