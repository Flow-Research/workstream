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
from subprocess import TimeoutExpired
import sys
import time
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
HEARTBEAT_SECONDS = 60.0
MINIO_ENDPOINT_ENV = "WORKSTREAM_TEST_MINIO_ENDPOINT"
MINIO_ACCESS_KEY = "workstream-minio"
MINIO_SECRET_KEY = "workstream-minio-secret-key"
S3_TRAFFIC_LANE = "shared_foundations"
S3_TRAFFIC_BUCKET = "workstream-artifacts"
LANE_RE = re.compile(r"[a-z][a-z0-9_]{0,62}")
BUCKET_RE = re.compile(r"[a-z0-9](?:[a-z0-9.-]{1,61}[a-z0-9])?")


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
        database_exists = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = $1)", name
        )
        role_exists = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", role
        )
        if database_exists or role_exists:
            raise RunnerError("cleanup_verification_failed")
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


def _child_env(
    target_url: str, *, minio_bucket: str = "", minio_prefix: str = ""
) -> dict[str, str]:
    env = os.environ.copy()
    env.pop(ADMIN_ENV, None)
    env.pop(OVERRIDE_ENV, None)
    env["WORKSTREAM_TEST_DATABASE_URL"] = target_url
    env["WORKSTREAM_DATABASE_URL"] = target_url
    if minio_bucket:
        env["WORKSTREAM_TEST_MINIO_BUCKET"] = minio_bucket
        env["WORKSTREAM_TEST_MINIO_PREFIX"] = minio_prefix
    return env


def _tree_sha() -> str:
    """Return the immutable commit checked out under the runner's exact tree."""
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.SubprocessError as exc:
        raise RunnerError("invalid_tree_sha") from exc
    if re.fullmatch(r"[a-f0-9]{40}", value) is None:
        raise RunnerError("invalid_tree_sha")
    return value


def _minio_namespace(lane: str, suffix: str) -> tuple[str, str]:
    """Return a lane-bound bucket and prefix without accepting arbitrary names."""
    if LANE_RE.fullmatch(lane) is None or re.fullmatch(r"[a-f0-9]{12}", suffix) is None:
        raise RunnerError("invalid_lane")
    lane_component = lane.replace("_", "-")
    bucket = (
        S3_TRAFFIC_BUCKET
        if lane == S3_TRAFFIC_LANE
        else f"workstream-ci-{lane_component}-{suffix}"
    )
    if len(bucket) > 63 or BUCKET_RE.fullmatch(bucket) is None:
        raise RunnerError("invalid_minio_namespace")
    return bucket, f"ci/{lane}/{suffix}"


def _minio_client(endpoint: str):
    parsed = urlsplit(endpoint)
    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise RunnerError("unsafe_minio_endpoint") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in LOOPBACK
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed_port is None
    ):
        raise RunnerError("unsafe_minio_endpoint")
    from aiobotocore.config import AioConfig
    from aiobotocore.session import AioSession

    session = AioSession()
    session.set_credentials(MINIO_ACCESS_KEY, MINIO_SECRET_KEY)
    return session.create_client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        config=AioConfig(s3={"addressing_style": "path"}),
    )


async def _create_minio(endpoint: str, bucket: str, prefix: str) -> None:
    """Claim and probe one fresh runner-owned MinIO namespace."""
    async with _minio_client(endpoint) as client:
        try:
            await client.create_bucket(Bucket=bucket)
        except Exception as exc:
            raise RunnerError("minio_namespace_collision") from exc
        try:
            key = f"{prefix}/runner-probe"
            await client.put_object(Bucket=bucket, Key=key, Body=b"workstream-ci-probe")
            response = await client.get_object(Bucket=bucket, Key=key)
            async with response["Body"] as body:
                if await body.read() != b"workstream-ci-probe":
                    raise RunnerError("minio_probe_failed")
            await client.delete_object(Bucket=bucket, Key=key)
        except BaseException as exc:
            try:
                await client.delete_object(Bucket=bucket, Key=f"{prefix}/runner-probe")
                await client.delete_bucket(Bucket=bucket)
            except BaseException as cleanup_error:
                if not isinstance(cleanup_error, Exception):
                    raise
                raise RunnerError("minio_provisioning_cleanup_failed") from cleanup_error
            if not isinstance(exc, Exception) or isinstance(exc, RunnerError):
                raise
            raise RunnerError("minio_probe_failed") from exc


async def _drop_minio(endpoint: str, bucket: str, prefix: str) -> None:
    """Delete every object in the exact owned bucket, then prove its removal."""
    async with _minio_client(endpoint) as client:
        continuation = None
        while True:
            request = {"Bucket": bucket}
            if continuation:
                request["ContinuationToken"] = continuation
            response = await client.list_objects_v2(**request)
            objects = response.get("Contents", [])
            if objects:
                await client.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": item["Key"]} for item in objects]},
                )
            if not response.get("IsTruncated"):
                break
            continuation = response.get("NextContinuationToken")
            if not continuation:
                raise RunnerError("minio_cleanup_failed")
        await client.delete_bucket(Bucket=bucket)
        buckets = await client.list_buckets()
        if bucket in {item["Name"] for item in buckets.get("Buckets", [])}:
            raise RunnerError("minio_cleanup_failed")


def _write_metadata(path: Path, metadata: dict[str, object]) -> None:
    """Create or replace private metadata without following a destination symlink."""
    data = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(data)
        while view:
            view = view[os.write(descriptor, view) :]
    finally:
        os.close(descriptor)


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
    started_at = time.monotonic()
    try:
        while True:
            elapsed = time.monotonic() - started_at
            if timeout is not None and elapsed >= timeout:
                _signal_group(process, signal.SIGTERM)
                try:
                    stdout, stderr = process.communicate(timeout=TERMINATION_GRACE_SECONDS)
                except TimeoutExpired:
                    _signal_group(process, signal.SIGKILL)
                    stdout, stderr = process.communicate()
                return 124, stdout, stderr
            wait_seconds = HEARTBEAT_SECONDS
            if timeout is not None:
                wait_seconds = min(wait_seconds, max(0.001, timeout - elapsed))
            try:
                stdout, stderr = process.communicate(timeout=wait_seconds)
                return process.returncode, stdout, stderr
            except TimeoutExpired:
                print(
                    "isolated-test child active: "
                    f"elapsed_seconds={time.monotonic() - started_at:.0f}",
                    flush=True,
                )
    except KeyboardInterrupt:
        _signal_group(process, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=TERMINATION_GRACE_SECONDS)
        except TimeoutExpired:
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
    parser.add_argument("--lane", default="isolated")
    parser.add_argument("--tree-sha")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    global INTERRUPTED
    INTERRUPTED = False
    admin_url = os.environ.pop(ADMIN_ENV, "")
    owned = False
    minio_owned = False
    name = role = bucket = prefix = ""
    endpoint = os.environ.get(MINIO_ENDPOINT_ENV, "")
    metadata: dict[str, object] | None = None
    result = 2
    previous_sigint = signal.signal(signal.SIGINT, _defer_interrupt)
    previous_sigterm = signal.signal(signal.SIGTERM, _defer_interrupt)
    try:
        if (
            not command
            or args.metadata_json.exists()
            or args.metadata_json.is_symlink()
            or args.metadata_json.parent.is_symlink()
            or not args.metadata_json.parent.is_dir()
        ):
            raise RunnerError("invalid_runner_arguments")
        if args.timeout_seconds is not None and args.timeout_seconds <= 0:
            raise RunnerError("invalid_runner_arguments")
        actual_tree_sha = _tree_sha()
        if args.tree_sha is not None and args.tree_sha != actual_tree_sha:
            raise RunnerError("tree_sha_mismatch")
        name, role, password, target_url = _urls(admin_url)
        asyncio.run(_create(admin_url, name, role, password))
        owned = True
        if endpoint:
            suffix = name.removeprefix("workstream_test_")
            bucket, prefix = _minio_namespace(args.lane, suffix)
            asyncio.run(_create_minio(endpoint, bucket, prefix))
            minio_owned = True
        signal.signal(signal.SIGINT, _interrupt)
        signal.signal(signal.SIGTERM, _interrupt)
        if INTERRUPTED:
            raise KeyboardInterrupt
        migration = _run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            _child_env(target_url, minio_bucket=bucket, minio_prefix=prefix),
            None,
        )
        hidden = (admin_url, target_url, MINIO_ACCESS_KEY, MINIO_SECRET_KEY)
        _emit(migration[1], sys.stdout, hidden)
        _emit(migration[2], sys.stderr, hidden)
        if migration[0] == 130 and INTERRUPTED:
            raise KeyboardInterrupt
        if migration[0] != 0:
            raise RunnerError("migration_failed")
        head = asyncio.run(_observed_head(target_url))
        metadata = {
            "alembic_head": head,
            "database_name": name,
            "database_cleanup_complete": False,
            "database_provisioned": True,
            "database_role": role,
            "lane": args.lane,
            "minio_bucket": bucket or None,
            "minio_prefix": prefix or None,
            "minio_cleanup_complete": False,
            "minio_probe_complete": minio_owned,
            "minio_provisioned": minio_owned,
            "schema_version": 2,
            "tree_sha": actual_tree_sha,
        }
        _write_metadata(args.metadata_json, metadata)
        code, stdout, stderr = _run(
            command,
            _child_env(target_url, minio_bucket=bucket, minio_prefix=prefix),
            args.timeout_seconds,
        )
        _emit(stdout, sys.stdout, hidden)
        _emit(stderr, sys.stderr, hidden)
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
        cleanup_ok = True
        minio_cleanup_ok = not minio_owned
        if minio_owned:
            try:
                asyncio.run(_drop_minio(endpoint, bucket, prefix))
                minio_cleanup_ok = True
            except BaseException:
                print("isolated-test runner failed: minio_cleanup_failed", file=sys.stderr)
                result = 2
                cleanup_ok = False
        database_cleanup_ok = not owned
        if owned:
            try:
                asyncio.run(_drop(admin_url, name, role))
                database_cleanup_ok = True
            except BaseException:
                print("isolated-test runner failed: cleanup_failed", file=sys.stderr)
                result = 2
                cleanup_ok = False
        if metadata is not None:
            metadata["database_cleanup_complete"] = database_cleanup_ok
            metadata["minio_cleanup_complete"] = minio_cleanup_ok
            metadata["cleanup_complete"] = cleanup_ok
            try:
                _write_metadata(args.metadata_json, metadata)
            except OSError:
                print("isolated-test runner failed: metadata_write_failed", file=sys.stderr)
                result = 2
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
