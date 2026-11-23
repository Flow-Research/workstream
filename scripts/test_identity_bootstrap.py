"""Operator bootstrap refuses live identity nodes and keeps temporary secrets scoped."""
from __future__ import annotations

from contextlib import ExitStack
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HOSTED = Path(__file__).resolve().parents[1] / "deploy/hosted"
sys.path.insert(0, str(HOSTED))
SPEC = importlib.util.spec_from_file_location("identity_bootstrap", HOSTED / "bootstrap-identity.py")
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class IdentityBootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.password = self.root / "bootstrap"
        self.password.write_text("synthetic-temporary-bootstrap-password")
        self.password.chmod(0o400)
        self.values = {"FLOW_IDENTITY_IMAGE": "example.invalid/identity@sha256:" + "a" * 64}
        for key in bootstrap.IDENTITY_FILE_KEYS:
            file = self.root / key
            file.write_text("fixture")
            self.values[key] = str(file)
        self.config = {"name": "owned-fixture", "services": {"identity": {
            "image": self.values["FLOW_IDENTITY_IMAGE"], "ports": ["127.0.0.1:18443:8443"],
            "restart": "on-failure:5", "environment": {"KC_DB": "postgres"},
            "volumes": [], "read_only": True, "user": "1000:1000", "mem_limit": "1536m",
        }}}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name in ("validate_environment", "validate_compose", "validate_identity_host_inputs", "_private_metadata"):
            self.stack.enter_context(patch.object(bootstrap, name))
        self.stack.enter_context(patch.object(bootstrap, "parse_environment", return_value=self.values))
        self.stack.enter_context(patch.object(bootstrap, "render_compose", return_value=self.config))
        self.stack.enter_context(patch.object(bootstrap, "compose_environment", return_value={"PATH": "/usr/bin"}))

    def test_running_node_denies_before_bootstrap(self):
        with patch.object(bootstrap.subprocess, "run", return_value=SimpleNamespace(stdout="running-id\n")) as run:
            with self.assertRaisesRegex(bootstrap.PreflightError, "stop the hosted identity"):
                bootstrap.bootstrap(self.root / "release.env", self.password)
        self.assertEqual(run.call_count, 1)
        self.assertIn("label=com.docker.compose.service=identity", run.call_args.args[0])

    def test_one_off_container_gets_only_scoped_bootstrap_secret(self):
        self.config["services"].update({
            "worker": {"image": "example.invalid/worker", "depends_on": ["model-proxy"]},
            "model-proxy": {"image": "example.invalid/proxy", "profiles": ["model-proxy"]},
        })
        self.config["networks"] = {"default": {"name": "owned-fixture_default"}}
        original = copy.deepcopy(self.config)
        commands = []

        def execute(command, **kwargs):
            commands.append(command)
            if command[1] == "compose":
                config = json.loads(Path(command[command.index("--file") + 1]).read_text())
                self.assertEqual(set(config["services"]), {"identity"})
                self.assertEqual(config["networks"], original["networks"])
                identity = config["services"]["identity"]
                self.assertEqual(identity["ports"], [])
                self.assertEqual(identity["restart"], "no")
                self.assertEqual(identity["environment"]["KC_BOOTSTRAP_ADMIN_PASSWORD_FILE"],
                                 "/run/identity/bootstrap-password")
                self.assertEqual(identity["volumes"][-1]["source"], str(self.password))
                self.assertTrue(identity["volumes"][-1]["read_only"])
                self.assertTrue(identity["read_only"])
                self.assertEqual(identity["user"], "1000:1000")
                self.assertEqual(identity["mem_limit"], "1536m")
                self.assertNotIn(self.password.read_text(), json.dumps(config))
                self.assertNotIn(self.password.read_text(), str(command))
            return SimpleNamespace(stdout="", returncode=0)

        with patch.object(bootstrap.subprocess, "run", side_effect=execute):
            bootstrap.bootstrap(self.root / "release.env", self.password)
        self.assertEqual(self.config, original)
        self.assertIn("--optimized", commands[1])
        self.assertIn("--no-deps", commands[1])
        self.assertEqual(commands[2][1:3], ["rm", "-fv"])
        self.assertEqual(commands[2][-1], commands[1][commands[1].index("--name") + 1])

    def test_timeout_removes_only_the_owned_container(self):
        calls = []

        def execute(command, **kwargs):
            calls.append(command)
            if command[1] == "compose":
                raise subprocess.TimeoutExpired("docker", 390)
            return SimpleNamespace(stdout="", returncode=0)

        with patch.object(bootstrap.subprocess, "run", side_effect=execute):
            with self.assertRaises(subprocess.TimeoutExpired):
                bootstrap.bootstrap(self.root / "release.env", self.password)
        self.assertEqual(calls[-1][1:3], ["rm", "-fv"])
        self.assertEqual(calls[-1][-1], calls[1][calls[1].index("--name") + 1])

    def test_reusing_runtime_secret_is_rejected(self):
        with patch.object(bootstrap.subprocess, "run") as run:
            with self.assertRaisesRegex(bootstrap.PreflightError, "must not reuse"):
                bootstrap.bootstrap(self.root / "release.env", Path(self.values[bootstrap.IDENTITY_FILE_KEYS[0]]))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
