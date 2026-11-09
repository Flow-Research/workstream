"""Fresh local backing-service initialization without privileged test execution."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "hosted_local_data_initialization",
    ROOT / "deploy" / "hosted" / "initialize-local-data.py",
)
assert SPEC is not None and SPEC.loader is not None
initializer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(initializer)


class HostedLocalDataInitializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "state"
        self.file_owners: dict[int, tuple[int, int]] = {}
        self.mocks = ExitStack()
        self.addCleanup(self.mocks.close)
        self.mocks.enter_context(patch.object(initializer.os, "geteuid", return_value=0))
        self.chown = self.mocks.enter_context(patch.object(initializer.os, "chown"))
        self.fchown = self.mocks.enter_context(patch.object(
            initializer.os, "fchown", side_effect=self.record_file_owner,
        ))
        # Model approved root-owned ancestors only. Actual file creation, modes,
        # exclusive opens, contents and fsync still exercise the filesystem.
        original_lstat = Path.lstat
        ancestors = set(self.root.parents)

        def ancestor_metadata(path: Path):
            if path in ancestors:
                return SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o755)
            return original_lstat(path)

        self.mocks.enter_context(patch.object(Path, "lstat", ancestor_metadata))

    def record_file_owner(self, descriptor: int, uid: int, gid: int) -> None:
        self.file_owners[os.fstat(descriptor).st_ino] = (uid, gid)

    def test_generated_credentials_match_services_and_separate_database_admin(self) -> None:
        paths = initializer.initialize(self.root, 10001, 10002)
        database_url = urlparse((self.root / "database_url").read_text().strip())
        broker_url = urlparse((self.root / "celery_broker_url").read_text().strip())
        admin_password = (self.root / "postgres_password").read_text().strip()
        sql = (self.root / "postgres_init.sql").read_text()
        redis_config = (self.root / "redis_config").read_text()

        self.assertEqual(database_url.scheme, "postgresql+asyncpg")
        self.assertEqual((database_url.username, database_url.hostname, database_url.port,
                          database_url.path), ("workstream", "postgres", 5432, "/workstream"))
        self.assertEqual((broker_url.scheme, broker_url.hostname, broker_url.port,
                          broker_url.path), ("redis", "redis", 6379, "/0"))
        for credential in (database_url.password, broker_url.password, admin_password):
            self.assertRegex(credential, r"^[0-9a-f]{64}$")
        self.assertEqual(len({database_url.password, broker_url.password, admin_password}), 3)
        self.assertIn(
            "CREATE ROLE workstream LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            f"NOREPLICATION NOBYPASSRLS PASSWORD '{database_url.password}';", sql,
        )
        self.assertIn("ALTER DATABASE workstream OWNER TO workstream;", sql)
        self.assertNotIn(admin_password, sql)
        self.assertIn(f"requirepass {broker_url.password}\n", redis_config)
        self.assertIn("appendonly yes\n", redis_config)
        self.assertEqual(paths, {
            "WORKSTREAM_POSTGRES_DATA_DIR": str(self.root / "postgres"),
            "WORKSTREAM_REDIS_DATA_DIR": str(self.root / "redis"),
            "WORKSTREAM_POSTGRES_PASSWORD_FILE": str(self.root / "postgres_password"),
            "WORKSTREAM_POSTGRES_INIT_SQL_FILE": str(self.root / "postgres_init.sql"),
            "WORKSTREAM_REDIS_CONFIG_FILE": str(self.root / "redis_config"),
            "WORKSTREAM_DATABASE_URL_FILE": str(self.root / "database_url"),
            "WORKSTREAM_CELERY_BROKER_URL_FILE": str(self.root / "celery_broker_url"),
        })
        self.assertFalse(any(secret in str(paths) for secret in (
            database_url.password, broker_url.password, admin_password,
        )))

    def test_private_permissions_and_service_specific_ownership(self) -> None:
        initializer.initialize(self.root, 10001, 10002)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o711)
        for name in ("postgres", "redis"):
            self.assertEqual(stat.S_IMODE((self.root / name).stat().st_mode), 0o700)
        self.assertEqual(self.chown.call_args_list, [
            unittest.mock.call(self.root / "postgres", 999, 999),
            unittest.mock.call(self.root / "redis", 999, 999),
        ])
        for path in self.root.iterdir():
            if path.is_file():
                with self.subTest(file=path.name):
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o400)
                    expected = (10001, 10002) if path.name in {
                        "database_url", "celery_broker_url",
                    } else (999, 999)
                    self.assertEqual(self.file_owners[path.stat().st_ino], expected)
        self.assertEqual(self.fchown.call_count, 5)

    def test_retry_refuses_existing_state_without_changing_any_file(self) -> None:
        initializer.initialize(self.root, 10001, 10002)
        data = self.root / "postgres" / "retained-data"
        data.write_bytes(b"retained database state")
        before = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mode)
                  for p in self.root.rglob("*") if p.is_file()}
        with patch.object(initializer.secrets, "token_hex") as token:
            with self.assertRaises(FileExistsError):
                initializer.initialize(self.root, 10001, 10002)
        token.assert_not_called()
        after = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mode)
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_partial_existing_state_is_never_filled_or_removed(self) -> None:
        self.root.mkdir()
        retained = self.root / "partial"
        retained.write_bytes(b"investigate me")
        with self.assertRaises(FileExistsError):
            initializer.initialize(self.root, 10001, 10002)
        self.assertEqual(list(self.root.iterdir()), [retained])
        self.assertEqual(retained.read_bytes(), b"investigate me")

    def test_invalid_paths_and_runtime_identity_create_no_state(self) -> None:
        invalid_paths = (Path("relative"), Path("/"), self.root / ".." / "state",
                         self.root.with_name("state space"), self.root.with_name("state:port"),
                         self.root.with_name("state,option"))
        for path in invalid_paths:
            with self.subTest(path=path), self.assertRaises(ValueError):
                initializer.initialize(path, 10001, 10002)
        for uid, gid in ((0, 10002), (10001, 0), (-1, 10002), (10001, -1)):
            with self.subTest(uid=uid, gid=gid), self.assertRaises(ValueError):
                initializer.initialize(self.root, uid, gid)
        with patch.object(initializer.os, "geteuid", return_value=10001):
            with self.assertRaises(ValueError):
                initializer.initialize(self.root, 10001, 10002)
        self.assertFalse(self.root.exists())
        self.chown.assert_not_called()
        self.fchown.assert_not_called()

    def test_symlinked_state_path_is_rejected_without_touching_target(self) -> None:
        target = self.root.with_name("target")
        target.mkdir()
        retained = target / "retained"
        retained.write_bytes(b"existing state")
        self.root.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            initializer.initialize(self.root, 10001, 10002)
        self.assertTrue(self.root.is_symlink())
        self.assertEqual(list(target.iterdir()), [retained])
        self.assertEqual(retained.read_bytes(), b"existing state")

    def test_unsafe_ancestor_ownership_or_permissions_refuse_before_creation(self) -> None:
        for mode, uid in ((stat.S_IFDIR | 0o777, 0), (stat.S_IFDIR | 0o775, 0),
                          (stat.S_IFDIR | 0o755, 10001), (stat.S_IFREG | 0o644, 0)):
            with self.subTest(mode=oct(mode), uid=uid):
                with patch.object(Path, "lstat", return_value=SimpleNamespace(
                    st_uid=uid, st_mode=mode,
                )), self.assertRaises(ValueError):
                    initializer.initialize(self.root, 10001, 10002)
                self.assertFalse(self.root.exists())

    def test_cli_reports_refusal_without_echoing_private_exception(self) -> None:
        output = io.StringIO()
        with patch.object(initializer, "initialize", side_effect=OSError("private-password")), \
                patch("sys.argv", [str(SPEC.origin)]), redirect_stdout(output):
            self.assertEqual(initializer.main(), 1)
        self.assertIn("No existing state was reset", output.getvalue())
        self.assertNotIn("private-password", output.getvalue())


if __name__ == "__main__":
    unittest.main()
