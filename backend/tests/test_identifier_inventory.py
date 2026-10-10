from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.identifier_inventory import (
    FORMAT,
    _string_uuid_references,
    _key,
    _sql_created_table,
    build_inventory,
    parse_orm_models,
    parse_schema,
    render_text,
    scan_generation_sites,
)


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_current_repository_inventory_has_no_unowned_or_mismatched_keys() -> None:
    report = build_inventory(Path(__file__).resolve().parents[1])
    assert report["unresolved"] == []
    assert report["string_uuid_references"] == []
    assert all(
        site["classification"] != "unclassified" and site["reason"]
        for site in report["generation_sites"]
    )


@pytest.mark.parametrize("constraint", ["sa.PrimaryKeyConstraint", "PrimaryKeyConstraint"])
def test_alembic_table_primary_keys_retain_order_and_native_types(tmp_path: Path, constraint: str) -> None:
    backend = tmp_path / "backend"
    _write(backend / "alembic/baseline/v01_baseline_manifest.json", json.dumps({
        "tables": [], "columns": [], "constraints": [],
    }))
    _write(backend / "alembic/versions/0001_records.py", f'''
from alembic import op
import sqlalchemy as sa
from sqlalchemy import PrimaryKeyConstraint

def upgrade():
    op.create_table("records",
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        {constraint}("id", "generation", name="pk_records"),
    )
''')
    table = parse_schema(backend)["records"]
    assert table["primary_key"] == ["id", "generation"]
    assert {column["name"]: column["storage_kind"] for column in table["columns"]} == {
        "id": "native_uuid", "generation": "integer",
    }


def test_orm_ast_inventory_captures_multiline_and_table_level_foreign_keys(
    tmp_path: Path,
) -> None:
    backend = tmp_path / "backend"
    model_path = backend / "app/modules/example/models.py"
    _write(
        model_path,
        """
from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

class Parent:
    __tablename__ = "parents"
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)

class Child:
    __tablename__ = "children"
    __table_args__ = (
        ForeignKeyConstraint(
            ["parent_id", "tenant_id"],
            ["parents.id", "tenants.id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_id: Mapped[str] = mapped_column(
        ForeignKey(
            "parents.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
""",
    )

    tables = parse_orm_models(backend / "app", backend)

    child = tables["children"]
    assert child["primary_key"] == ["id"]
    columns = {column["name"]: column for column in child["columns"]}
    assert columns["parent_id"]["foreign_keys"] == ["parents.id"]
    assert columns["parent_id"]["storage_kind"] == "native_uuid"
    assert columns["parent_id"]["storage_inferred_from_foreign_key"] is True
    assert columns["tenant_id"]["foreign_keys"] == ["tenants.id"]
    assert tables["parents"]["columns"][0]["storage_kind"] == "native_uuid"


def test_sql_inventory_reuses_quote_aware_baseline_statement_splitting() -> None:
    source = """
CREATE FUNCTION ignored() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 'a;still-in-function';
END $$;
CREATE TABLE public.delivery_attempts (
  event_id uuid REFERENCES public.outbox_events(event_id),
  claim_generation bigint NOT NULL,
  note character varying(36),
  CONSTRAINT pk_delivery PRIMARY KEY (event_id, claim_generation)
);
"""

    table = _sql_created_table(source, "migration.py")["delivery_attempts"]

    assert table["primary_key"] == ["event_id", "claim_generation"]
    columns = {column["name"]: column for column in table["columns"]}
    assert columns["event_id"]["storage_kind"] == "native_uuid"
    assert columns["event_id"]["foreign_keys"] == []


def test_semantic_uuid_reference_includes_task_assignee_without_id_suffix() -> None:
    references = _string_uuid_references(
        [
            {
                "name": "actor_profiles",
                "columns": [
                    {
                        "name": "id",
                        "storage_type": "Uuid(as_uuid=False)",
                        "storage_kind": "native_uuid",
                        "foreign_keys": [],
                    }
                ],
            },
            {
                "name": "workstream_tasks",
                "columns": [
                    {
                        "name": "assigned_to",
                        "storage_type": "String(100)",
                        "storage_kind": "string",
                        "foreign_keys": [],
                    }
                ],
            },
        ]
    )

    assert references == [
        {
            "table": "workstream_tasks",
            "column": "assigned_to",
            "target": "actor_profiles.id",
            "current_storage": "String(100)",
            "candidate": "convert relationship to native UUID",
        }
    ]


def test_build_inventory_reports_cutover_candidates_and_unresolved_schema_objects(
    tmp_path: Path,
) -> None:
    backend = tmp_path / "backend"
    _write(
        backend / "app/modules/example/models.py",
        """
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

class Widget:
    __tablename__ = "widgets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

class WidgetUse:
    __tablename__ = "widget_uses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    widget_id: Mapped[str] = mapped_column(
        ForeignKey(
            "widgets.id",
        ),
        nullable=False,
    )
""",
    )
    _write(
        backend / "app/writers.py",
        """
from uuid import uuid4

def persist_widget(session):
    session.add(Widget(id=str(uuid4())))
""",
    )
    _write(
        backend / "scripts/drill.py",
        """
import uuid as identifier_source
request_id = identifier_source.uuid5(identifier_source.NAMESPACE_URL, "drill")
""",
    )
    _write(
        backend / "alembic/baseline/v01_baseline_manifest.json",
        json.dumps(
            {
                "tables": [
                    {"name": "widgets"},
                    {"name": "widget_uses"},
                    {"name": "migration_state"},
                ],
                "columns": [
                    {"table_name": "widgets", "name": "id", "data_type": "varchar(36)"},
                    {"table_name": "widget_uses", "name": "id", "data_type": "varchar(36)"},
                    {
                        "table_name": "widget_uses",
                        "name": "widget_id",
                        "data_type": "varchar(36)",
                    },
                    {"table_name": "migration_state", "name": "id", "data_type": "integer"},
                ],
                "constraints": [
                    {
                        "kind": "p",
                        "table_name": table,
                        "definition": "PRIMARY KEY (id)",
                    }
                    for table in ("widgets", "widget_uses", "migration_state")
                ],
            }
        ),
    )
    _write(
        backend / "alembic/versions/0002_delayed.py",
        """
from alembic import op
import sqlalchemy as sa
def upgrade():
    op.create_table(
        "delayed_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
    )
""",
    )

    report = build_inventory(backend)

    assert report["format"] == FORMAT
    assert report["summary"] == {
        "orm_tables": 2,
        "schema_tables": 4,
        "tables": 4,
        "key_classifications": {"generated_surrogate": 2, "unresolved": 2},
        "string_uuid_reference_candidates": 1,
        "generation_sites": {"uuid4": 1, "uuid5": 1},
        "unresolved": 4,
    }
    assert report["string_uuid_references"] == [
        {
            "table": "widget_uses",
            "column": "widget_id",
            "target": "widgets.id",
            "current_storage": "inferred",
            "candidate": "convert relationship to native UUID",
        }
    ]
    assert {item["table"] for item in report["unresolved"] if "table" in item} == {
        "delayed_records",
        "migration_state",
    }
    assert {site["classification"] for site in report["generation_sites"]} == {
        "unclassified"
    }
    generation_issues = [
        item for item in report["unresolved"] if item["kind"] == "generation_site"
    ]
    assert {item["path"] for item in generation_issues} == {
        "app/writers.py",
        "scripts/drill.py",
    }
    row_writer = next(
        site for site in report["generation_sites"] if site["path"] == "app/writers.py"
    )
    assert row_writer["owner"] == "persist_widget"
    assert "Widget(id=str(uuid4()))" in row_writer["expression"]
    assert json.loads(json.dumps(report))["summary"] == report["summary"]
    text = render_text(report)
    assert "widget_uses.widget_id -> widgets.id" in text
    assert "migration_state: schema table has no ORM owner" in text

    # A manifest that silently loses a model or changes its key must not be
    # treated as a complete inventory just because the remaining types match.
    manifest_path = backend / "alembic/baseline/v01_baseline_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["tables"] = [row for row in manifest["tables"] if row["name"] != "widget_uses"]
    manifest["columns"] = [row for row in manifest["columns"] if row["table_name"] != "widget_uses"]
    manifest["constraints"] = [row for row in manifest["constraints"] if row["table_name"] != "widget_uses"]
    manifest["constraints"][0]["definition"] = "PRIMARY KEY (different_key)"
    _write(manifest_path, json.dumps(manifest))
    unresolved = {
        (row["kind"], row["table"])
        for row in build_inventory(backend)["unresolved"]
        if "table" in row
    }
    assert ("missing_schema_table", "widget_uses") in unresolved
    assert ("primary_key_shape_mismatch", "widgets") in unresolved


def test_generation_site_keys_ignore_lines_but_detect_generator_references(
    tmp_path: Path,
) -> None:
    backend = tmp_path / "backend"
    path = backend / "app/defaults.py"
    source = """
from uuid import uuid4
import uuid

def model_column(mapped_column):
    return mapped_column(default=uuid4)

def dataclass_field(field):
    return field(default_factory=uuid.uuid4)
"""
    _write(path, source)
    first = scan_generation_sites((backend / "app",), backend)
    _write(path, "\n\n" + source)
    shifted = scan_generation_sites((backend / "app",), backend)

    assert len(first) == 2
    assert {site["usage"] for site in first} == {"reference"}
    assert {site["classification"] for site in first} == {"unclassified"}
    assert [site["site_key"] for site in first] == [
        site["site_key"] for site in shifted
    ]


def test_routing_operation_key_classification_is_owner_and_shape_scoped() -> None:
    table = {"name": "task_post_submit_routing_requests", "primary_key": ["route_operation_id"]}
    assert _key(table, True)["classification"] == "generated_surrogate"
    assert _key(table, False)["classification"] == "unresolved"
    assert _key(table | {"name": "unowned_requests"}, True)["classification"] == "unresolved"
    assert _key(table | {"primary_key": ["unexpected_id"]}, True)["classification"] == "unresolved"


@pytest.mark.parametrize("migration,unowned", [
    ("def upgrade():\n    op.drop_table('retired')", False),
    ("def upgrade():\n    op.drop_table('retired', schema='public')", False),
    ("def upgrade():\n    op.drop_table('retired')\n    op.create_table('retired', sa.Column('id', sa.Uuid(), primary_key=True))", True),
    ("def upgrade():\n    op.create_table('retired', sa.Column('id', sa.Uuid(), primary_key=True))\n    op.drop_table('retired')", False),
    ("def upgrade():\n    op.drop_table('retired')\ndef downgrade():\n    op.create_table('retired', sa.Column('id', sa.Uuid(), primary_key=True))", False),
    ("def upgrade():\n    op.drop_table('retired')\ndef downgrade():\n    op.execute('CREATE TABLE public.retired (id uuid PRIMARY KEY);')", False),
    ("DDL = 'CREATE TABLE public.retired (id uuid PRIMARY KEY);'\ndef upgrade():\n    op.execute(DDL)", True),
    ("def downgrade():\n    op.drop_table('retired')", True),
    ("def helper():\n    op.drop_table('retired')\ndef upgrade():\n    helper()", True),
    ("def upgrade():\n    if enabled:\n        op.drop_table('retired')", True),
    ("def upgrade():\n    other.drop_table('retired')", True),
    ("def upgrade():\n    op.drop_table('retired', schema='other')", True),
    ("def upgrade():\n    op.drop_table(table_name)", True),
    ("def upgrade():\n    op.drop_table('retired', schema=schema_name)", True),
    ("def upgrade():\n    op.drop_table('retired', **options)", True),
])
def test_inventory_only_retires_explicit_public_upgrade_drops(tmp_path, migration, unowned):
    backend = tmp_path / "backend"
    _write(backend / "alembic/baseline/v01_baseline_manifest.json", json.dumps({
        "tables": [{"name": "retired"}],
        "columns": [{"table_name": "retired", "name": "id", "data_type": "uuid"}],
        "constraints": [{"kind": "p", "table_name": "retired", "definition": "PRIMARY KEY (id)"}],
    }))
    _write(backend / "alembic/versions/0002_retire.py", "from alembic import op\nimport sqlalchemy as sa\n" + migration)
    report = build_inventory(backend)
    assert report["summary"]["schema_tables"] == int(unowned)
    assert report["unresolved"] == ([{
        "kind": "table_key", "table": "retired", "reason": "schema table has no ORM owner",
    }] if unowned else [])

    # Recreation in a later migration must also remain visible to the guard.
    _write(backend / "alembic/versions/0003_recreate.py", """
from alembic import op
import sqlalchemy as sa
def upgrade():
    op.create_table('retired', sa.Column('id', sa.Uuid(), primary_key=True))
""")
    recreated = build_inventory(backend)
    assert recreated["summary"]["schema_tables"] == 1
    assert recreated["unresolved"] == [{
        "kind": "table_key", "table": "retired", "reason": "schema table has no ORM owner",
    }]
