#!/usr/bin/env python3
"""Run a command against one owned, temporary local Postgres database."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
from urllib.parse import quote, urlsplit, urlunsplit

import asyncpg
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
NAME_RE = re.compile(r"workstream_test_[a-f0-9]{12}")
ROLE_RE = re.compile(r"workstream_role_[a-f0-9]{12}")
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
ADMIN_ENV = "WORKSTREAM_TEST_ADMIN_DATABASE_URL"
OVERRIDE_ENV = "WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE"
INTERRUPTED = False
TERMINATION_GRACE_SECONDS = 2.0


class RunnerError(RuntimeError):
    """A stable, non-secret isolation failure."""


def _urls(admin_url: str) -> tuple[str, str, str, str]:
    parsed = urlsplit(admin_url)
    if parsed.scheme != "postgresql+asyncpg" or parsed.hostname not in LOOPBACK:
        raise RunnerError("unsafe_admin_database")
    if not parsed.path.strip("/") or parsed.query or parsed.fragment:
        raise RunnerError("unsafe_admin_database")
    suffix = hashlib.sha256(
        f"{ROOT.resolve()}:{secrets.token_hex(16)}".encode()
    ).hexdigest()[:12]
    name, role, password = f"workstream_test_{suffix}", f"workstream_role_{suffix}", secrets.token_hex(24)
    _identifiers(name, role)
    try:
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError as exc:
        raise RunnerError("unsafe_admin_database") from exc
    netloc = f"{quote(role)}:{quote(password)}@{host}{port}"
    return name, role, password, urlunsplit((parsed.scheme, netloc, f"/{name}", "", ""))


def _identifiers(name: str, role: str) -> None:
    if NAME_RE.fullmatch(name) is None or ROLE_RE.fullmatch(role) is None:
        raise RunnerError("unsafe_database_identifier")


def _asyncpg_url(url: str) -> str:
    return "postgresql" + url.removeprefix("postgresql+asyncpg")


def _head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RunnerError("ambiguous_alembic_head")
    return heads[0]


async def _create(admin_url: str, name: str, role: str, password: str) -> None:
    _identifiers(name, role)
    connection = await asyncpg.connect(_asyncpg_url(admin_url))
    role_created = False
    try:
        password_literal = await connection.fetchval("SELECT quote_literal($1)", password)
        await connection.execute(
            f'CREATE ROLE "{role}" LOGIN PASSWORD {password_literal} '
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
        role_created = True
        await connection.execute(f'CREATE DATABASE "{name}" OWNER "{role}"')
    except (asyncpg.DuplicateDatabaseError, asyncpg.DuplicateObjectError) as exc:
        if role_created:
            await connection.execute(f'DROP ROLE "{role}"')
        raise RunnerError("database_collision") from exc
    except BaseException:
        try:
            owner = await connection.fetchval(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = $1", name
            )
            if owner == role:
                await connection.fetch(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = $1 AND pid <> pg_backend_pid()",
                    name,
                )
                await connection.execute(f'DROP DATABASE "{name}"')
            role_exists = await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", role
            )
            if role_exists:
                await connection.execute(f'DROP ROLE "{role}"')
        except Exception as cleanup_error:
            raise RunnerError("provisioning_cleanup_failed") from cleanup_error
        raise
    finally:
        await connection.close()


async def _drop(admin_url: str, name: str, role: str) -> None:
    _identifiers(name, role)
    connection = await asyncpg.connect(_asyncpg_url(admin_url))
    try:
        owner = await connection.fetchval(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = $1", name
        )
        if owner not in (None, role):
            raise RunnerError("cleanup_ownership_mismatch")
        await connection.fetch(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE (datname = $1 OR usename = $2) AND pid <> pg_backend_pid()",
            name, role,
        )
        if owner:
            await connection.execute(f'DROP DATABASE "{name}"')
        if await connection.fetchval("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", role):
            await connection.execute(f'DROP ROLE "{role}"')
    finally:
        await connection.close()


async def _observed_head(target_url: str) -> str:
    connection = await asyncpg.connect(_asyncpg_url(target_url))
    try:
        rows = await connection.fetch("SELECT version_num FROM alembic_version")
    finally:
        await connection.close()
    expected = _head()
    if [row["version_num"] for row in rows] != [expected]:
        raise RunnerError("alembic_head_mismatch")
    return expected


def _child_env(target_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop(ADMIN_ENV, None)
    env.pop(OVERRIDE_ENV, None)
    env["WORKSTREAM_TEST_DATABASE_URL"] = target_url
    env["WORKSTREAM_DATABASE_URL"] = target_url
    return env


def _emit(data: bytes, stream, secrets_to_hide: tuple[str, ...]) -> None:
    for value in secrets_to_hide:
        data = data.replace(value.encode(), b"[REDACTED_DATABASE_URL]")
    stream.buffer.write(data)
    stream.flush()


def _run(
    command: list[str], env: dict[str, str], timeout: float | None
) -> tuple[int, bytes, bytes]:
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        _signal_group(process, signal.SIGKILL)
        stdout, stderr = process.communicate()
        return 124, stdout, stderr
    except KeyboardInterrupt:
        _signal_group(process, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _signal_group(process, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return 130, stdout, stderr


def _signal_group(process: subprocess.Popen, value: int) -> None:
    try:
        os.killpg(process.pid, value)
    except ProcessLookupError:
        pass


def _interrupt(_signum, _frame) -> None:
    global INTERRUPTED
    INTERRUPTED = True
    raise KeyboardInterrupt


def _defer_interrupt(_signum, _frame) -> None:
    global INTERRUPTED
    INTERRUPTED = True


def main() -> int:
    """Provision, migrate, run, redact, and clean up one database."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-json", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    global INTERRUPTED
    INTERRUPTED = False
    admin_url = os.environ.pop(ADMIN_ENV, "")
    owned = False
    result = 2
    previous_sigint = signal.signal(signal.SIGINT, _defer_interrupt)
    previous_sigterm = signal.signal(signal.SIGTERM, _defer_interrupt)
    try:
        if (
            not command
            or args.metadata_json.exists()
            or args.metadata_json.is_symlink()
            or not args.metadata_json.parent.is_dir()
        ):
            raise RunnerError("invalid_runner_arguments")
        name, role, password, target_url = _urls(admin_url)
        asyncio.run(_create(admin_url, name, role, password))
        owned = True
        signal.signal(signal.SIGINT, _interrupt)
        signal.signal(signal.SIGTERM, _interrupt)
        if INTERRUPTED:
            raise KeyboardInterrupt
        migration = _run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], _child_env(target_url), None
        )
        _emit(migration[1], sys.stdout, (admin_url, target_url))
        _emit(migration[2], sys.stderr, (admin_url, target_url))
        if migration[0] == 130 and INTERRUPTED:
            raise KeyboardInterrupt
        if migration[0] != 0:
            raise RunnerError("migration_failed")
        head = asyncio.run(_observed_head(target_url))
        metadata = {
            "alembic_head": head,
            "database_name": name,
            "schema_version": 1,
            "tree_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
        }
        args.metadata_json.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        code, stdout, stderr = _run(command, _child_env(target_url), args.timeout_seconds)
        _emit(stdout, sys.stdout, (admin_url, target_url))
        _emit(stderr, sys.stderr, (admin_url, target_url))
        result = code
    except (RunnerError, OSError, asyncpg.PostgresError) as exc:
        code = exc.args[0] if isinstance(exc, RunnerError) else "database_operation_failed"
        print(f"isolated-test runner failed: {code}", file=sys.stderr)
    except KeyboardInterrupt:
        print("isolated-test runner interrupted", file=sys.stderr)
        result = 130
    finally:
        signal.signal(signal.SIGINT, _defer_interrupt)
        signal.signal(signal.SIGTERM, _defer_interrupt)
        if owned:
            try:
                asyncio.run(_drop(admin_url, name, role))
            except BaseException:
                print("isolated-test runner failed: cleanup_failed", file=sys.stderr)
                result = 2
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
