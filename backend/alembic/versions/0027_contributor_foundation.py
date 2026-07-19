"""clean-cut contributor attribution to canonical human actors

Revision ID: 0027_contributor_foundation
Revises: 0026_actor_profile_lifecycle
Create Date: 2026-07-19
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "0027_contributor_foundation"
down_revision = "0026_actor_profile_lifecycle"
branch_labels = depends_on = None

UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
FUNCTION_NAME = "require_human_actor_profile_reference"
LINEAGE_OBJECTS = (
    (
        "task_assignments",
        "task_assignments_contributor_human",
        "fk_task_assignments_contributor_id_actor_profiles",
    ),
    (
        "submissions",
        "submissions_contributor_human",
        "fk_submissions_contributor_id_actor_profiles",
    ),
)


def _preflight() -> None:
    """Reject source rows that cannot become canonical human references."""
    bind = op.get_bind()
    failures: dict[str, dict[str, dict[str, object]]] = {}
    for table in ("task_assignments", "submissions"):
        rows = bind.execute(
            sa.text(
                f"""
                select source.id as row_id, source.worker_id as actor_profile_id,
                       case
                         when source.worker_id !~ :uuid_pattern then 'malformed'
                         when profile.id is null then 'missing'
                         when profile.actor_kind <> 'human' then 'service'
                       end as failure_class
                from {table} source
                left join actor_profiles profile on profile.id = source.worker_id
                where source.worker_id !~ :uuid_pattern
                   or profile.id is null
                   or profile.actor_kind <> 'human'
                order by failure_class, source.id, source.worker_id
                """
            ),
            {"uuid_pattern": UUID_PATTERN},
        ).mappings()
        table_failures: dict[str, dict[str, object]] = {}
        for row in rows:
            failure_class = str(row["failure_class"])
            bucket = table_failures.setdefault(
                failure_class,
                {"total": 0, "rows": []},
            )
            bucket["total"] = int(bucket["total"]) + 1
            bounded_rows = bucket["rows"]
            if isinstance(bounded_rows, list) and len(bounded_rows) < 20:
                actor_profile_id = (
                    "<redacted-malformed>"
                    if failure_class == "malformed"
                    else str(row["actor_profile_id"])
                )
                bounded_rows.append(
                    [str(row["row_id"]), actor_profile_id]
                )
        if table_failures:
            failures[table] = table_failures
    if failures:
        raise RuntimeError(
            "contributor foundation preflight failed: "
            + json.dumps(failures, sort_keys=True, separators=(",", ":"))
        )


def _create_lineage_function() -> None:
    op.execute(
        f"""
        create function public.{FUNCTION_NAME}() returns trigger
        language plpgsql security invoker as $$
        declare referenced_id text; referenced_kind text;
        begin
          if tg_nargs <> 1 or tg_argv[0] is null
             or not (to_jsonb(new) ? tg_argv[0]) then
            raise exception 'human actor reference trigger is misconfigured'
              using errcode='55000';
          end if;
          referenced_id := to_jsonb(new) ->> tg_argv[0];
          if referenced_id is null then return new; end if;
          select profile.actor_kind into referenced_kind
          from public.actor_profiles profile where profile.id=referenced_id;
          if not found then return new; end if;
          if referenced_kind <> 'human' then
            raise exception 'actor reference must identify a human profile'
              using errcode='23514', constraint='{FUNCTION_NAME}';
          end if;
          return new;
        end $$
        """
    )


def _downstream_dependencies() -> tuple[int, tuple[str, ...]]:
    """Return bounded descriptions of dependencies beyond this migration's triggers."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            f"""
            with owned_triggers as (
              select trigger_row.oid
              from pg_trigger trigger_row
              join pg_class table_row on table_row.oid=trigger_row.tgrelid
              join pg_namespace namespace_row on namespace_row.oid=table_row.relnamespace
              where namespace_row.nspname='public'
                and (table_row.relname,trigger_row.tgname) in (
                  ('task_assignments','task_assignments_contributor_human'),
                  ('submissions','submissions_contributor_human')
                )
            )
            select description, total
            from (
              select
                pg_describe_object(
                  dependency.classid,
                  dependency.objid,
                  dependency.objsubid
                ) as description,
                count(*) over () as total
              from pg_depend dependency
              where dependency.refclassid='pg_proc'::regclass
                and dependency.refobjid='public.{FUNCTION_NAME}()'::regprocedure
                and not (
                  dependency.classid='pg_trigger'::regclass
                  and dependency.objid in (select oid from owned_triggers)
                )
            ) dependencies
            order by description
            limit 20
            """
        )
    ).all()
    if not rows:
        return 0, ()
    return int(rows[0].total), tuple(str(row.description) for row in rows)


def upgrade() -> None:
    """Install canonical-human contributor attribution without guessing data."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table actor_profiles, task_assignments, submissions "
            "in access exclusive mode"
        )
    )
    _preflight()

    op.alter_column(
        "task_assignments",
        "worker_id",
        new_column_name="contributor_id",
        existing_type=sa.String(100),
        existing_nullable=False,
    )
    op.alter_column(
        "task_assignments",
        "contributor_id",
        type_=sa.String(36),
        existing_type=sa.String(100),
        existing_nullable=False,
    )
    op.execute(
        "alter index ix_task_assignments_worker_id "
        "rename to ix_task_assignments_contributor_id"
    )
    op.alter_column(
        "submissions",
        "worker_id",
        new_column_name="contributor_id",
        existing_type=sa.String(100),
        existing_nullable=False,
    )
    op.alter_column(
        "submissions",
        "contributor_id",
        type_=sa.String(36),
        existing_type=sa.String(100),
        existing_nullable=False,
    )
    op.execute(
        "alter index ix_submissions_worker_id rename to ix_submissions_contributor_id"
    )

    for table, _, foreign_key in LINEAGE_OBJECTS:
        op.create_foreign_key(
            foreign_key,
            table,
            "actor_profiles",
            ["contributor_id"],
            ["id"],
        )
    _create_lineage_function()
    for table, trigger, _ in LINEAGE_OBJECTS:
        op.execute(
            f"create trigger {trigger} before insert or update of contributor_id "
            f"on {table} for each row execute function "
            f"public.{FUNCTION_NAME}('contributor_id')"
        )


def downgrade() -> None:
    """Restore prior names only while no later lineage consumer depends on them."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table actor_profiles, task_assignments, submissions "
            "in access exclusive mode"
        )
    )
    dependency_total, dependencies = _downstream_dependencies()
    if dependency_total:
        raise RuntimeError(
            "cannot downgrade contributor lineage dependencies: "
            + json.dumps(
                {"total": dependency_total, "objects": dependencies},
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    for table, trigger, _ in LINEAGE_OBJECTS:
        op.execute(f"drop trigger {trigger} on {table}")
    for table, _, foreign_key in LINEAGE_OBJECTS:
        op.drop_constraint(foreign_key, table, type_="foreignkey")
    op.execute(f"drop function public.{FUNCTION_NAME}() restrict")

    op.execute(
        "alter index ix_task_assignments_contributor_id "
        "rename to ix_task_assignments_worker_id"
    )
    op.alter_column(
        "task_assignments",
        "contributor_id",
        type_=sa.String(100),
        existing_type=sa.String(36),
        existing_nullable=False,
    )
    op.alter_column(
        "task_assignments",
        "contributor_id",
        new_column_name="worker_id",
        existing_type=sa.String(100),
        existing_nullable=False,
    )
    op.execute(
        "alter index ix_submissions_contributor_id rename to ix_submissions_worker_id"
    )
    op.alter_column(
        "submissions",
        "contributor_id",
        type_=sa.String(100),
        existing_type=sa.String(36),
        existing_nullable=False,
    )
    op.alter_column(
        "submissions",
        "contributor_id",
        new_column_name="worker_id",
        existing_type=sa.String(100),
        existing_nullable=False,
    )
