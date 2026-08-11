"""Install the clean v0.1 Workstream schema baseline."""

from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

from scripts.schema_baseline_sql import split_sql_statements

revision = "0001_v01_baseline"
down_revision = None
branch_labels = None
depends_on = None

_BASELINE_DIRECTORY = Path(__file__).resolve().parents[1] / "baseline"
_RECREATE_GUIDANCE = (
    "Workstream v0.1 requires a fresh database; recreate this database before "
    "running the 0001_v01_baseline migration"
)


def _public_schema_has_product_objects() -> bool:
    connection = op.get_bind()
    return bool(
        connection.scalar(
            text(
                "select exists ("
                "select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                "where n.nspname='public' and c.relname <> 'alembic_version' "
                "and c.relkind in ('r','p','S','v','m','f') "
                "union all select 1 from pg_proc p join pg_namespace n "
                "on n.oid=p.pronamespace where n.nspname='public' "
                "union all select 1 from pg_type t join pg_namespace n "
                "on n.oid=t.typnamespace where n.nspname='public' and t.typrelid=0 "
                "and t.typcategory <> 'A' "
                "union all select 1 from pg_collation c join pg_namespace n "
                "on n.oid=c.collnamespace where n.nspname='public' "
                "union all select 1 from pg_opclass o join pg_namespace n "
                "on n.oid=o.opcnamespace where n.nspname='public'"
                ")"
            )
        )
    )


def _execute(statements: tuple[str, ...]) -> None:
    if not statements:
        return
    batch_tag = "$workstream_baseline_batch$"
    commands: list[str] = []
    for index, statement in enumerate(statements):
        tag = f"$workstream_statement_{index}$"
        if tag in statement or batch_tag in statement:
            raise RuntimeError("baseline SQL contains a reserved execution delimiter")
        commands.append(f"EXECUTE {tag}{statement}{tag};")
    op.execute(text(f"DO {batch_tag} BEGIN {' '.join(commands)} END {batch_tag}"))


def upgrade() -> None:
    """Install the exact v0.1 schema only into a fresh database."""
    if _public_schema_has_product_objects():
        raise RuntimeError(_RECREATE_GUIDANCE)

    # pg_dump orders functions before tables; some PL/pgSQL declarations use
    # table row types. Limit deferred body validation to this migration
    # transaction and let the completed-schema parity tests validate every body.
    op.execute(text("set local check_function_bodies = false"))

    schema = split_sql_statements(
        (_BASELINE_DIRECTORY / "v01_schema.sql").read_text(encoding="utf-8")
    )
    triggers = tuple(statement for statement in schema if statement.startswith("CREATE TRIGGER "))
    _execute(tuple(statement for statement in schema if statement not in triggers))
    _execute(
        split_sql_statements(
            (_BASELINE_DIRECTORY / "v01_reference_data.sql").read_text(encoding="utf-8")
        )
    )
    _execute(triggers)


def downgrade() -> None:
    """Reject destructive downgrade of the clean v0.1 baseline."""
    raise RuntimeError("0001_v01_baseline cannot be downgraded; recreate the database")
