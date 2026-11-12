#!/usr/bin/env python3
"""Initialize fresh local backing-service credentials; never reset existing state."""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import stat


def postgres_initialization_sql(database_password: str, identity_password: str | None = None) -> str:
    """Build the fresh databases' exact role boundaries using generated credentials."""
    passwords = (database_password,) if identity_password is None else (database_password, identity_password)
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in passwords):
        raise ValueError("database initialization requires generated hexadecimal credentials")
    sql = (
        "CREATE ROLE workstream LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        f"NOREPLICATION NOBYPASSRLS PASSWORD '{database_password}';\n"
        "ALTER DATABASE workstream OWNER TO workstream;\n"
        "REVOKE ALL ON DATABASE workstream FROM PUBLIC;\n"
        "GRANT CONNECT ON DATABASE workstream TO workstream;\n"
    )
    if identity_password is not None:
        sql += (
            "CREATE ROLE flow_identity LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            f"NOREPLICATION NOBYPASSRLS PASSWORD '{identity_password}';\n"
            "CREATE DATABASE flow_identity OWNER flow_identity;\n"
            "REVOKE ALL ON DATABASE flow_identity FROM PUBLIC;\n"
            "GRANT CONNECT ON DATABASE flow_identity TO flow_identity;\n"
        )
    return sql


def initialize(
    root: Path, runtime_uid: int, runtime_gid: int, *, with_keycloak: bool = False,
) -> dict[str, str]:
    if os.geteuid() != 0 or runtime_uid <= 0 or runtime_gid <= 0:
        raise ValueError("initialization requires root and a non-root runtime identity")
    if (not root.is_absolute() or root != root.resolve(strict=False)
            or root == Path("/") or any(c.isspace() or c in ":," for c in str(root))):
        raise ValueError("state root must be a canonical absolute path")
    for parent in root.parents:
        metadata = parent.lstat()
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) & 0o022):
            raise ValueError("state ancestors must be root-owned and not group/world writable")
    # An existing root, including partially initialized state, requires explicit
    # operator investigation. Never rotate credentials or delete data on retry.
    root.mkdir(mode=0o711)
    os.chmod(root, 0o711)
    for name in ("postgres", "redis"):
        directory = root / name
        directory.mkdir(mode=0o700)
        os.chown(directory, 999, 999)

    database_password = secrets.token_hex(32)
    database_admin_password = secrets.token_hex(32)
    broker_password = secrets.token_hex(32)
    identity_password = secrets.token_hex(32) if with_keycloak else None
    contents = {
        "postgres_password": (database_admin_password + "\n", 999, 999),
        "postgres_init.sql": (
            postgres_initialization_sql(database_password, identity_password), 999, 999,
        ),
        "redis_config": (
            "bind 0.0.0.0\nprotected-mode yes\nport 6379\ndir /data\n"
            "appendonly yes\nappendfsync everysec\nmaxmemory 128mb\n"
            "maxmemory-policy noeviction\nlogfile \"\"\n"
            f"requirepass {broker_password}\n", 999, 999,
        ),
        "database_url": (
            f"postgresql+asyncpg://workstream:{database_password}@postgres:5432/workstream\n",
            runtime_uid, runtime_gid,
        ),
        "celery_broker_url": (
            f"redis://:{broker_password}@redis:6379/0\n", runtime_uid, runtime_gid,
        ),
    }
    if identity_password is not None:
        contents["identity_database_password"] = (identity_password + "\n", 1000, 1000)
    for name, (content, uid, gid) in contents.items():
        descriptor = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fchown(stream.fileno(), uid, gid)
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    paths = {
        "WORKSTREAM_POSTGRES_DATA_DIR": str(root / "postgres"),
        "WORKSTREAM_REDIS_DATA_DIR": str(root / "redis"),
        "WORKSTREAM_POSTGRES_PASSWORD_FILE": str(root / "postgres_password"),
        "WORKSTREAM_POSTGRES_INIT_SQL_FILE": str(root / "postgres_init.sql"),
        "WORKSTREAM_REDIS_CONFIG_FILE": str(root / "redis_config"),
        "WORKSTREAM_DATABASE_URL_FILE": str(root / "database_url"),
        "WORKSTREAM_CELERY_BROKER_URL_FILE": str(root / "celery_broker_url"),
    }
    if with_keycloak:
        paths["FLOW_IDENTITY_DATABASE_PASSWORD_FILE"] = str(root / "identity_database_password")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/var/lib/workstream-local-data"))
    parser.add_argument("--runtime-uid", type=int, default=10001)
    parser.add_argument("--runtime-gid", type=int, default=10001)
    parser.add_argument("--with-keycloak", action="store_true",
                        help="Provision the separately owned Flow Identity database")
    args = parser.parse_args()
    try:
        paths = initialize(args.root, args.runtime_uid, args.runtime_gid,
                           with_keycloak=args.with_keycloak)
    except (OSError, ValueError):
        print("Local data initialization refused or incomplete; inspect the private state directory. No existing state was reset.")
        return 1
    print(json.dumps(paths, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
