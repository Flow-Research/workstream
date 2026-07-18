from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import asyncpg
import pytest

RUNNER = Path(__file__).resolve().parents[1] / "scripts/run_isolated_tests.py"
ADMIN_ENV = "WORKSTREAM_TEST_ADMIN_DATABASE_URL"
SPEC = importlib.util.spec_from_file_location("isolated_runner_test", RUNNER)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


async def _names(admin_url: str) -> set[str]:
    connection = await asyncpg.connect("postgresql" + admin_url.removeprefix("postgresql+asyncpg"))
    try:
        rows = await connection.fetch("SELECT datname FROM pg_database WHERE datname LIKE 'workstream_test_%'")
        return {row["datname"] for row in rows}
    finally:
        await connection.close()


async def _roles(admin_url: str) -> set[str]:
    connection = await asyncpg.connect("postgresql" + admin_url.removeprefix("postgresql+asyncpg"))
    try:
        rows = await connection.fetch("SELECT rolname FROM pg_roles WHERE rolname LIKE 'workstream_role_%'")
        return {row["rolname"] for row in rows}
    finally:
        await connection.close()


def _run(tmp_path: Path, code: str, *, timeout: float | None = None) -> subprocess.CompletedProcess:
    command = [sys.executable, str(RUNNER), "--metadata-json", str(tmp_path / "database.json")]
    if timeout is not None:
        command += ["--timeout-seconds", str(timeout)]
    command += ["--", sys.executable, "-c", code]
    return subprocess.run(command, text=True, capture_output=True, env=os.environ.copy())


def _mock_successful_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drop) -> None:
    async def noop(*_): return None
    async def observed(*_): return "0015"
    calls = iter([(0, b"", b""), (0, b"", b"")])
    monkeypatch.setenv(ADMIN_ENV, "postgresql+asyncpg://local@localhost/postgres")
    monkeypatch.setattr(runner, "_urls", lambda _: ("workstream_test_012345abcdef", "workstream_role_012345abcdef", "password", "target"))
    monkeypatch.setattr(runner, "_create", noop)
    monkeypatch.setattr(runner, "_observed_head", observed)
    monkeypatch.setattr(runner, "_drop", drop)
    monkeypatch.setattr(runner, "_run", lambda *_: next(calls))
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *_args, **_kwargs: "1" * 40)
    monkeypatch.setattr(sys, "argv", [str(RUNNER), "--metadata-json", str(tmp_path / "db.json"), "--", "child"])


def test_runner_rejects_nonlocal_admin_without_exposing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provisioning credentials cannot authorize a remote destructive target."""
    secret = "postgresql+asyncpg://admin:secret@db.example.com/postgres"
    monkeypatch.setenv(ADMIN_ENV, secret)
    result = _run(tmp_path, "pass")
    assert result.returncode == 2
    assert secret not in result.stderr
    assert "unsafe_admin_database" in result.stderr


@pytest.mark.parametrize(("code", "expected"), [("raise SystemExit(7)", 7), ("import time; time.sleep(2)", 124)])
def test_runner_propagates_failure_and_always_drops_owned_database(
    tmp_path: Path, code: str, expected: int
) -> None:
    """Child failure and timeout remain visible without leaving database state."""
    admin = os.environ[ADMIN_ENV]
    before = asyncio.run(_names(admin))
    roles = asyncio.run(_roles(admin))
    result = _run(tmp_path, code, timeout=0.1 if expected == 124 else None)
    assert result.returncode == expected
    assert asyncio.run(_names(admin)) == before
    assert asyncio.run(_roles(admin)) == roles


def test_runner_strips_parent_secrets_migrates_and_redacts_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The child sees only its target while metadata proves migration and cleanup."""
    admin = os.environ[ADMIN_ENV]
    monkeypatch.setenv("WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE", "unsafe")
    code = "\n".join([
        "import asyncio, asyncpg, os",
        "assert 'WORKSTREAM_TEST_ADMIN_DATABASE_URL' not in os.environ",
        "assert 'WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE' not in os.environ",
        "url = os.environ['WORKSTREAM_DATABASE_URL']",
        "async def check():",
        " c = await asyncpg.connect('postgresql' + url.removeprefix('postgresql+asyncpg'))",
        " row = await c.fetchrow('select current_database(), rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls from pg_roles where rolname=current_user')",
        " await c.close()",
        " assert row[0].startswith('workstream_test_') and not any(row[1:])",
        "asyncio.run(check())",
        "print(url)",
    ])
    before = asyncio.run(_names(admin))
    roles = asyncio.run(_roles(admin))
    result = _run(tmp_path, code)
    metadata = json.loads((tmp_path / "database.json").read_text(encoding="utf-8"))
    assert result.returncode == 0
    assert "[REDACTED_DATABASE_URL]" in result.stdout
    assert admin not in result.stdout + result.stderr
    assert metadata["database_name"].startswith("workstream_test_")
    assert metadata["alembic_head"]
    assert asyncio.run(_names(admin)) == before
    assert asyncio.run(_roles(admin)) == roles


@pytest.mark.parametrize("child_drops_database", [False, True])
def test_cleanup_terminates_only_owned_sessions_and_drops_role(child_drops_database: bool) -> None:
    """Cleanup terminates exact owned sessions while an unrelated session survives."""
    admin = os.environ[ADMIN_ENV]
    async def exercise() -> None:
        name, role, password, target = runner._urls(admin)
        await runner._create(admin, name, role, password)
        spectator = await asyncpg.connect(runner._asyncpg_url(admin))
        owned = await asyncpg.connect(runner._asyncpg_url(target))
        if child_drops_database:
            controller = await asyncpg.connect(runner._asyncpg_url(target).rsplit("/", 1)[0] + "/postgres")
            await controller.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await runner._drop(admin, name, role)
        with pytest.raises((asyncpg.PostgresError, asyncpg.InterfaceError, ConnectionResetError)):
            await owned.fetchval("SELECT 1")
        if child_drops_database:
            with pytest.raises((asyncpg.PostgresError, asyncpg.InterfaceError, ConnectionResetError)):
                await controller.fetchval("SELECT 1")
        assert await spectator.fetchval("SELECT 1") == 1
        await spectator.close()
        assert name not in await _names(admin) and role not in await _roles(admin)
    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("name", "role"),
    [("workstream_test_bad", "workstream_role_012345abcdef"), ("workstream_test_012345abcdef", "admin")],
)
def test_destructive_boundaries_revalidate_identifiers(name: str, role: str) -> None:
    """Direct destructive helper use rejects every noncanonical identifier."""
    for operation in (
        lambda: runner._create(os.environ[ADMIN_ENV], name, role, "password"),
        lambda: runner._drop(os.environ[ADMIN_ENV], name, role),
    ):
        with pytest.raises(runner.RunnerError, match="unsafe_database_identifier"):
            asyncio.run(operation())


def test_runner_concurrency_is_unique_and_interrupt_cleanup_is_exact(tmp_path: Path) -> None:
    """Concurrent owned DBs are observable, unique, and removed on interruption."""
    admin = os.environ[ADMIN_ENV]
    before = asyncio.run(_names(admin))
    roles = asyncio.run(_roles(admin))
    processes = []
    for index in range(2):
        marker = tmp_path / f"child-{index}"
        ignored = "import signal; signal.signal(signal.SIGTERM, signal.SIG_IGN); " if index == 0 else ""
        code = ignored + f"import os,time,urllib.parse,pathlib; pathlib.Path({str(marker)!r}).write_text(urllib.parse.urlsplit(os.environ['WORKSTREAM_DATABASE_URL']).path[1:]); time.sleep(30)"
        command = [sys.executable, str(RUNNER), "--metadata-json", str(tmp_path / f"db-{index}.json"), "--", sys.executable, "-c", code]
        processes.append((subprocess.Popen(command, env=os.environ.copy()), marker))
    try:
        deadline = time.monotonic() + 120
        while not all(marker.exists() for _, marker in processes) and time.monotonic() < deadline:
            time.sleep(0.1)
        names = {marker.read_text() for _, marker in processes}
        assert len(names) == 2 and names <= asyncio.run(_names(admin))
    finally:
        for index, (process, _) in enumerate(processes):
            process.send_signal(signal.SIGTERM if index == 0 else signal.SIGINT)
            assert process.wait(timeout=15) == 130
    assert asyncio.run(_names(admin)) == before
    assert asyncio.run(_roles(admin)) == roles


def test_collision_never_claims_or_drops_existing_database() -> None:
    """A create collision leaves the pre-existing database and sessions untouched."""
    admin = os.environ[ADMIN_ENV]
    async def exercise() -> None:
        suffix = os.urandom(6).hex()
        name, role = f"workstream_test_{suffix}", f"workstream_role_{suffix}"
        password = os.urandom(16).hex()
        await runner._create(admin, name, role, password)
        target = "postgresql" + admin.removeprefix("postgresql+asyncpg").rsplit("/", 1)[0] + f"/{name}"
        session = await asyncpg.connect(target)
        try:
            with pytest.raises(runner.RunnerError, match="database_collision"):
                await runner._create(admin, name, "workstream_role_abcdef012345", password)
            assert name in await _names(admin)
            assert await session.fetchval("SELECT 1") == 1
            assert "workstream_role_abcdef012345" not in await _roles(admin)
        finally:
            await session.close()
            await runner._drop(admin, name, role)
    asyncio.run(exercise())


@pytest.mark.parametrize("trigger", ["CREATE ROLE", "CREATE DATABASE"])
def test_interruption_after_partial_create_compensates_real_resources(
    monkeypatch: pytest.MonkeyPatch, trigger: str
) -> None:
    """Interruption after either provisioning DDL leaves no role or database."""
    admin = os.environ[ADMIN_ENV]
    before, roles = asyncio.run(_names(admin)), asyncio.run(_roles(admin))
    real_connect = asyncpg.connect
    class InterruptingConnection:
        def __init__(self, connection):
            self.connection, self.triggered = connection, False
        async def execute(self, query, *args):
            result = await self.connection.execute(query, *args)
            if query.startswith(trigger) and not self.triggered:
                self.triggered = True
                raise KeyboardInterrupt
            return result
        def __getattr__(self, name):
            return getattr(self.connection, name)
    async def connect(url):
        return InterruptingConnection(await real_connect(url))
    fake = SimpleNamespace(
        connect=connect,
        DuplicateDatabaseError=asyncpg.DuplicateDatabaseError,
        DuplicateObjectError=asyncpg.DuplicateObjectError,
    )
    monkeypatch.setattr(runner, "asyncpg", fake)
    name, role, password, _ = runner._urls(admin)
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(runner._create(admin, name, role, password))
    assert asyncio.run(_names(admin)) == before
    assert asyncio.run(_roles(admin)) == roles


@pytest.mark.parametrize(("migration_code", "interrupted", "expected"), [(9, False, 2), (130, True, 130)])
def test_migration_failure_or_interrupt_cleans_without_starting_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, migration_code: int,
    interrupted: bool, expected: int,
) -> None:
    """Migration failure or interruption cleans before any child can run."""
    events = []
    async def record(event, *_):
        events.append(event)
    monkeypatch.setenv(ADMIN_ENV, "postgresql+asyncpg://local@localhost/postgres")
    monkeypatch.setattr(runner, "_urls", lambda _: ("workstream_test_012345abcdef", "workstream_role_012345abcdef", "password", "target"))
    monkeypatch.setattr(runner, "_create", lambda *_: record("create"))
    monkeypatch.setattr(runner, "_drop", lambda *_: record("drop"))
    def migration(*_):
        runner.INTERRUPTED = interrupted
        return migration_code, b"", b""
    monkeypatch.setattr(runner, "_run", migration)
    monkeypatch.setattr(sys, "argv", [str(RUNNER), "--metadata-json", str(tmp_path / "db.json"), "--", "child"])
    assert runner.main() == expected
    assert events == ["create", "drop"]


def test_cleanup_failure_overrides_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful child cannot hide failure to destroy owned database state."""
    async def fail_drop(*_):
        raise RuntimeError("secret detail")
    _mock_successful_main(tmp_path, monkeypatch, fail_drop)
    assert runner.main() == 2


def test_cleanup_defers_repeated_signals_and_preserves_child_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repeated SIGINT/SIGTERM cannot interrupt owned cleanup or rewrite success."""
    async def signalled_drop(*_):
        os.kill(os.getpid(), signal.SIGINT)
        os.kill(os.getpid(), signal.SIGTERM)
    _mock_successful_main(tmp_path, monkeypatch, signalled_drop)
    assert runner.main() == 0
