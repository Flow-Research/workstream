"""Emit the deterministic v0.1 PostgreSQL schema manifest."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import asyncpg

REFERENCE_TABLES = (
    "actor_profile_migration_state",
    "authority_control",
    "iso_4217_currency_codes",
)
APPLICATION_ACL_PRINCIPALS: dict[str, str] = {}
_SPACE = re.compile(r"\s+")
_ARRAY_EXPRESSION = re.compile(r"ARRAY\[(.*?)\](?:::(?:text|character varying)\[\])?", re.S)


def _asyncpg_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "postgresql+asyncpg":
        raise ValueError("database URL must use postgresql+asyncpg")
    return urlunsplit(("postgresql", parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _normalize_definition(value: str | None) -> str:
    """Normalize insignificant formatting while preserving expression structure."""
    compact = _SPACE.sub(" ", value or "").strip()

    def normalize_array(match: re.Match[str]) -> str:
        body = re.sub(r"::(?:character varying|text)", "", match.group(1))
        body = re.sub(r"\(('(?:[^']|'')*')\)", r"\1", body)
        return f"ARRAY[{body}]"

    normalized = _ARRAY_EXPRESSION.sub(normalize_array, compact)
    return re.sub(r"\((ARRAY\[.*?\])\)::text\[\]", r"\1", normalized)


async def _records(connection: asyncpg.Connection, query: str) -> list[dict[str, Any]]:
    return [
        {key: _json_value(value) for key, value in record.items()}
        for record in await connection.fetch(query)
    ]


def canonical_acl_principal(grantee: str, owner: str) -> str:
    """Return the stable manifest principal or reject an unconfigured role."""
    if grantee == owner:
        return "owner"
    if grantee == "PUBLIC":
        return "PUBLIC"
    if grantee in APPLICATION_ACL_PRINCIPALS:
        return grantee
    raise RuntimeError(f"unknown ACL principal: {grantee}")


async def _acl_manifest(connection: asyncpg.Connection) -> list[dict[str, str]]:
    rows = await connection.fetch(
        "with objects(kind,name,owner_oid,acl,default_kind) as ("
        "select case when c.relkind='S' then 'sequence' else 'relation' end, "
        "c.relname,c.relowner,c.relacl,case when c.relkind='S' then 'S'::\"char\" else 'r'::\"char\" end "
        "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='public' and c.relname <> 'alembic_version' "
        "and c.relkind in ('r','p','S','v','m','f') union all "
        "select 'routine',p.proname||'('||pg_get_function_identity_arguments(p.oid)||')',"
        "p.proowner,p.proacl,'f'::\"char\" from pg_proc p join pg_namespace n "
        "on n.oid=p.pronamespace where n.nspname='public' union all "
        "select 'type',t.typname,t.typowner,t.typacl,'T'::\"char\" from pg_type t "
        "join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' "
        "and t.typrelid=0 and t.typcategory <> 'A') "
        "select o.kind,o.name,owner.rolname owner_name,coalesce(grantee.rolname,'PUBLIC') grantee_name,"
        "x.privilege_type,x.is_grantable from objects o join pg_roles owner "
        "on owner.oid=o.owner_oid cross join lateral aclexplode("
        "coalesce(o.acl,acldefault(o.default_kind,o.owner_oid))) x "
        "left join pg_roles grantee on grantee.oid=x.grantee order by 1,2,5,4"
    )
    result: list[dict[str, str]] = []
    for row in rows:
        principal = canonical_acl_principal(row["grantee_name"], row["owner_name"])
        result.append(
            {
                "kind": row["kind"],
                "name": row["name"],
                "principal": principal,
                "privilege": row["privilege_type"],
                "grantable": str(row["is_grantable"]).lower(),
            }
        )
    return result


async def build_manifest(database_url: str) -> dict[str, Any]:
    """Collect the closed v0.1 schema and reference-data inventory."""
    connection = await asyncpg.connect(_asyncpg_url(database_url))
    try:
        tables = await _records(
            connection,
            "select c.relname name,c.relkind::text kind,c.relpersistence::text persistence,"
            "c.relrowsecurity row_security,c.relforcerowsecurity force_row_security "
            "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='public' and c.relkind in ('r','p','v','m','f') "
            "and c.relname <> 'alembic_version' order by c.relname",
        )
        columns = await _records(
            connection,
            "select c.relname table_name,row_number() over (partition by c.oid order by a.attnum) ordinal,a.attname name,"
            "format_type(a.atttypid,a.atttypmod) data_type,a.attnotnull not_null,"
            "a.attidentity identity_kind,a.attgenerated generated_kind,"
            "coalesce(pg_get_expr(d.adbin,d.adrelid),'') default_expression "
            "from pg_attribute a join pg_class c on c.oid=a.attrelid "
            "join pg_namespace n on n.oid=c.relnamespace left join pg_attrdef d "
            "on d.adrelid=a.attrelid and d.adnum=a.attnum where n.nspname='public' "
            "and c.relname <> 'alembic_version' and c.relkind in ('r','p','v','m','f') "
            "and a.attnum>0 and not a.attisdropped order by c.relname,a.attnum",
        )
        constraints = await _records(
            connection,
            "select coalesce(c.relname,'') table_name,q.conname name,q.contype::text kind,"
            "pg_get_constraintdef(q.oid,true) definition from pg_constraint q "
            "left join pg_class c on c.oid=q.conrelid join pg_namespace n "
            "on n.oid=q.connamespace where n.nspname='public' "
            "and coalesce(c.relname,'') <> 'alembic_version' order by 1,2",
        )
        indexes = await _records(
            connection,
            "select tablename table_name,indexname name,indexdef definition "
            "from pg_indexes where schemaname='public' and tablename <> 'alembic_version' "
            "order by tablename,indexname",
        )
        sequences = await _records(
            connection,
            "select s.sequencename name,s.data_type,s.start_value,s.min_value,s.max_value,"
            "s.increment_by,s.cycle,s.cache_size,s.last_value "
            "from pg_sequences s where s.schemaname='public' "
            "order by s.sequencename",
        )
        for sequence in sequences:
            identifier = str(sequence["name"]).replace('"', '""')
            state = await connection.fetchrow(
                f'SELECT last_value,is_called FROM public."{identifier}"'
            )
            sequence["last_value"] = state["last_value"]
            sequence["is_called"] = state["is_called"]
        types = await _records(
            connection,
            "select t.typname name,t.typtype::text kind,coalesce(array_to_json(array_agg(e.enumlabel "
            "order by e.enumsortorder) filter (where e.enumlabel is not null))::text,'[]') labels "
            "from pg_type t join pg_namespace n on n.oid=t.typnamespace left join pg_enum e "
            "on e.enumtypid=t.oid where n.nspname='public' and t.typrelid=0 "
            "and t.typcategory <> 'A' group by t.typname,t.typtype order by t.typname",
        )
        routines = await _records(
            connection,
            "select p.proname name,pg_get_function_identity_arguments(p.oid) arguments,"
            "pg_get_functiondef(p.oid) definition from pg_proc p join pg_namespace n "
            "on n.oid=p.pronamespace where n.nspname='public' order by p.proname,arguments",
        )
        triggers = await _records(
            connection,
            "select c.relname table_name,t.tgname name,t.tgenabled::text enabled,"
            "pg_get_triggerdef(t.oid,true) definition from pg_trigger t join pg_class c "
            "on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='public' and not t.tgisinternal order by c.relname,t.tgname",
        )
        policies = await _records(
            connection,
            "select c.relname table_name,p.polname name,p.polpermissive permissive,p.polcmd command,"
            "p.polroles::text roles,coalesce(pg_get_expr(p.polqual,p.polrelid),'') using_expression,"
            "coalesce(pg_get_expr(p.polwithcheck,p.polrelid),'') check_expression "
            "from pg_policy p join pg_class c on c.oid=p.polrelid join pg_namespace n "
            "on n.oid=c.relnamespace where n.nspname='public' order by c.relname,p.polname",
        )
        auxiliary = await _records(
            connection,
            "select kind,name,definition from ("
            "select 'extension' kind,e.extname name,e.extversion definition from pg_extension e "
            "join pg_namespace n on n.oid=e.extnamespace where n.nspname='public' union all "
            "select 'domain',t.typname,format_type(t.typbasetype,t.typtypmod) from pg_type t "
            "join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and t.typtype='d' "
            "union all select 'collation',c.collname,coalesce(c.collversion,'') from pg_collation c "
            "join pg_namespace n on n.oid=c.collnamespace where n.nspname='public' union all "
            "select 'operator_class',o.opcname,a.amname from pg_opclass o join pg_namespace n "
            "on n.oid=o.opcnamespace join pg_am a on a.oid=o.opcmethod where n.nspname='public') x "
            "order by kind,name",
        )
        reference_rows: dict[str, list[dict[str, Any]]] = {}
        for table in REFERENCE_TABLES:
            records = await connection.fetch(f'SELECT * FROM public."{table}" ORDER BY 1')
            reference_rows[table] = [
                {key: _json_value(value) for key, value in row.items()} for row in records
            ]
        for collection in (columns, constraints, indexes, routines, triggers, policies):
            for row in collection:
                for key in tuple(row):
                    if "definition" in key or "expression" in key:
                        row[key] = _normalize_definition(str(row[key]))
        return {
            "format": "workstream-v01-schema-manifest-1",
            "tables": tables,
            "columns": columns,
            "constraints": constraints,
            "indexes": indexes,
            "sequences": sequences,
            "types": types,
            "routines": routines,
            "triggers": triggers,
            "policies": policies,
            "auxiliary_objects": auxiliary,
            "acl": await _acl_manifest(connection),
            "reference_rows": reference_rows,
        }
    finally:
        await connection.close()


def canonical_bytes(manifest: dict[str, Any]) -> bytes:
    """Serialize a manifest deterministically."""
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


async def _run(args: argparse.Namespace) -> None:
    manifest = await build_manifest(args.database_url)
    payload = canonical_bytes(manifest)
    if args.compare:
        expected = args.compare.read_bytes()
        if payload != expected:
            raise RuntimeError(
                "schema manifest mismatch: "
                f"expected={hashlib.sha256(expected).hexdigest()} "
                f"actual={hashlib.sha256(payload).hexdigest()}"
            )
    if args.output:
        args.output.write_bytes(payload)
    elif not args.compare:
        print(payload.decode(), end="")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url", default=os.environ.get("WORKSTREAM_DATABASE_URL"), required=False
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or WORKSTREAM_DATABASE_URL is required")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
