"""Focused regressions for the hosted release configuration."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = ROOT / "deploy" / "hosted" / "preflight.py"
ENTRYPOINT_PATH = ROOT / "docker" / "backend" / "release-entrypoint.sh"
ENV_EXAMPLE = ROOT / "deploy" / "hosted" / "release.env.example"
CHECKER_EXAMPLE = ROOT / "deploy" / "hosted" / "checker-service.example.json"
ROLES_ANYWHERE_GUIDE = ROOT / "docs" / "operations_aws_roles_anywhere.md"

SPEC = importlib.util.spec_from_file_location(
    "hosted_release_preflight", PREFLIGHT_PATH
)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
SPEC.loader.exec_module(preflight)

COMPOSE_SPEC = importlib.util.spec_from_file_location(
    "hosted_release_compose", ROOT / "deploy" / "hosted" / "compose.py"
)
assert COMPOSE_SPEC is not None and COMPOSE_SPEC.loader is not None
compose = importlib.util.module_from_spec(COMPOSE_SPEC)
with patch.dict(sys.modules, {"preflight": preflight}):
    COMPOSE_SPEC.loader.exec_module(compose)


class HostedReleaseConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runtime_uid = 10001
        self.runtime_gid = 10001
        self.checker_path = self.root / "checker.json"
        self.checker = json.loads(CHECKER_EXAMPLE.read_text(encoding="utf-8"))
        self.checker["sandbox_uid"] = self.runtime_uid
        self.checker["sandbox_gid"] = self.runtime_gid
        # Synthetic test qualification, never an operational sizing recommendation.
        self.checker["trusted_intake"]["storage_envelope"].update(
            overhead_bytes=128 * 1024**2, maximum_storage_gib=2,
        )
        self.checker_path.write_text(json.dumps(self.checker), encoding="utf-8")
        self.identity_files = {
            name: self.root / f"{name.replace('_', '-')}.pem"
            for name in (
                "runtime-certificate",
                "runtime-private-key",
                "readiness-certificate",
                "readiness-private-key",
                "negative-certificate",
                "negative-private-key",
            )
        }
        for name, path in self.identity_files.items():
            content = f"test {name}"
            path.write_text(content, encoding="utf-8")
            path.chmod(0o400)
        self.runtime_certificate = self.identity_files["runtime-certificate"]
        self.runtime_private_key = self.identity_files["runtime-private-key"]
        environment_text = ENV_EXAMPLE.read_text(encoding="utf-8")
        environment_text = (
            environment_text.replace(
                "WORKSTREAM_RUNTIME_UID=10001",
                f"WORKSTREAM_RUNTIME_UID={self.runtime_uid}",
            )
            .replace(
                "WORKSTREAM_RUNTIME_GID=10001",
                f"WORKSTREAM_RUNTIME_GID={self.runtime_gid}",
            )
            .replace(
                "WORKSTREAM_CHECKER_CONFIG_FILE=/etc/workstream/checker-service.json",
                f"WORKSTREAM_CHECKER_CONFIG_FILE={self.checker_path}",
            )
            .replace(
                "/etc/workstream/roles-anywhere/runtime-certificate.pem",
                str(self.runtime_certificate),
            )
            .replace(
                "/etc/workstream/roles-anywhere/runtime-private-key.pem",
                str(self.runtime_private_key),
            )
        )
        for name in (
            "readiness-certificate",
            "readiness-private-key",
            "negative-certificate",
            "negative-private-key",
        ):
            environment_text = environment_text.replace(
                f"/etc/workstream/roles-anywhere/{name}.pem",
                str(self.identity_files[name]),
            )
        self.environment_path = self.root / "release.env"
        self.environment_path.write_text(environment_text, encoding="utf-8")
        self.environment = preflight.parse_environment(self.environment_path)

    def local_data_environment(self):
        return self.environment | {
            "WORKSTREAM_POSTGRES_IMAGE": "postgres@sha256:" + "1" * 64,
            "WORKSTREAM_REDIS_IMAGE": "redis@sha256:" + "2" * 64,
            "WORKSTREAM_POSTGRES_DATA_DIR": str(self.root / "postgres"),
            "WORKSTREAM_REDIS_DATA_DIR": str(self.root / "redis"),
            "WORKSTREAM_POSTGRES_PASSWORD_FILE": str(self.root / "pg-password"),
            "WORKSTREAM_POSTGRES_INIT_SQL_FILE": str(self.root / "pg-init.sql"),
            "WORKSTREAM_REDIS_CONFIG_FILE": str(self.root / "redis.conf"),
        }

    def test_local_data_shutdown_preserves_dependencies_until_consumers_stop(self):
        values = self.local_data_environment()
        with patch.object(preflight.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(preflight.run_shutdown(self.environment_path, values), 0)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[-1][-5:], ["stop", "--timeout", "60", "redis", "postgres"])
        self.assertTrue(any(command[-4:] == ["stop", "--timeout", "7320", "worker"] for command in commands[:-1]))
        with patch.object(preflight.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 17),
        ]) as run:
            self.assertEqual(preflight.run_shutdown(self.environment_path, values), 17)
        self.assertFalse(any("postgres" in call.args[0] for call in run.call_args_list))

    def test_local_data_requires_complete_pinned_separate_inputs(self):
        values = self.local_data_environment()
        preflight.validate_environment(values)
        for key in preflight.LOCAL_DATA_KEYS:
            with self.subTest(missing=key), self.assertRaises(preflight.PreflightError):
                preflight.validate_environment(values | {key: ""})
        for key, value in (
            ("WORKSTREAM_POSTGRES_IMAGE", "postgres:16"),
            ("WORKSTREAM_REDIS_DATA_DIR", values["WORKSTREAM_POSTGRES_DATA_DIR"]),
            ("WORKSTREAM_POSTGRES_PASSWORD_FILE", values["WORKSTREAM_POSTGRES_DATA_DIR"] + "/secret"),
            ("WORKSTREAM_REDIS_DATA_DIR", "/var/lib/workstream/scratch/redis"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(preflight.PreflightError):
                preflight.validate_environment(values | {key: value})

    def test_local_data_render_has_no_public_ports_or_cross_mounted_credentials(self):
        values = self.local_data_environment()
        rendered = preflight.render_compose(self.environment_path, values)
        preflight.validate_compose(rendered, values)
        for role in ("api", "worker", "beat", "model-proxy", "guide-document-parser"):
            sources = {entry["source"] for entry in rendered["services"][role].get("secrets", [])}
            self.assertFalse(sources & {"postgres_password", "redis_config"})
        for role in ("postgres", "redis"):
            for field, value in (
                ("ports", [{"target": 5432, "published": "5432", "host_ip": "0.0.0.0"}]),
                ("network_mode", "host"), ("user", "0:0"),
                ("image", "postgres:latest"), ("privileged", True),
                ("volumes", []), ("secrets", []),
            ):
                changed = copy.deepcopy(rendered)
                changed["services"][role][field] = value
                with self.subTest(role=role, field=field), self.assertRaises(preflight.PreflightError):
                    preflight.validate_compose(changed, values)

    def test_local_data_bootstrap_does_not_start_application_or_replace_mcp(self):
        values = self.local_data_environment() | {"WORKSTREAM_MCP_IMAGE": "mcp@sha256:" + "3" * 64}
        with patch.object(preflight.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(preflight.run_compose(self.environment_path, values, ["start", "local-data"]), 0)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][-8:], ["up", "--detach", "--no-deps", "--wait", "--wait-timeout", "120", "postgres", "redis"])
        self.assertEqual(run.call_args.kwargs["timeout"], 150)

    def test_mcp_overlay_is_private_and_has_no_server_credentials(self):
        values = dict(self.environment, WORKSTREAM_MCP_IMAGE="example.test/mcp@sha256:" + "b" * 64)
        preflight.validate_environment(values)
        rendered = preflight.render_compose(self.environment_path, values)
        preflight.validate_compose(rendered, values)
        self.assertEqual(rendered["services"]["mcp"]["network_mode"], "service:api")
        for key, value in (
            ("network_mode", "host"), ("networks", {"default": None}),
            ("volumes", [{"type": "bind", "source": "/private", "target": "/private"}]),
            ("secrets", [{"source": "database_url"}]), ("user", "0:0"),
            ("privileged", True), ("entrypoint", ["sh"]),
            ("environment", {"WORKSTREAM_API_URL": "https://foreign.example"}),
        ):
            with self.subTest(field=key):
                changed = copy.deepcopy(rendered)
                changed["services"]["mcp"][key] = value
                with self.assertRaisesRegex(preflight.PreflightError, "MCP isolation"):
                    preflight.validate_compose(changed, values)
        changed = copy.deepcopy(rendered)
        next(p for p in changed["services"]["api"]["ports"] if p["target"] == 8080)["host_ip"] = "0.0.0.0"
        with self.assertRaisesRegex(preflight.PreflightError, "private API"):
            preflight.validate_compose(changed, values)
        changed = copy.deepcopy(rendered)
        changed["services"]["api"]["network_mode"] = "host"
        changed["services"]["api"].pop("networks", None)
        with self.assertRaisesRegex(preflight.PreflightError, "parent API"):
            preflight.validate_compose(changed, values)
        for network in ({"driver": "host"}, {"external": True}, {"driver_opts": {"anything": "yes"}}):
            changed = copy.deepcopy(rendered)
            changed["networks"]["default"] = network
            with self.assertRaisesRegex(preflight.PreflightError, "parent API"):
                preflight.validate_compose(changed, values)
        for image in ("mcp:latest", "", "mcp@sha256:bad"):
            with self.assertRaisesRegex(preflight.PreflightError, "digest-qualified"):
                preflight.validate_environment(dict(values, WORKSTREAM_MCP_IMAGE=image))

    def test_api_replacement_stops_then_recreates_mcp_and_binds_current_namespace(self):
        values = dict(self.environment, WORKSTREAM_MCP_IMAGE="example.test/mcp@sha256:" + "b" * 64)
        api_id, mcp_id = "a" * 64, "b" * 64
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            output = ""
            if command[-3:] == ["ps", "--quiet", "api"]:
                output = api_id
            elif command[-3:] == ["ps", "--quiet", "mcp"]:
                output = mcp_id
            elif command[:2] == ["docker", "inspect"]:
                output = "container:" + api_id
            return subprocess.CompletedProcess(command, 0, stdout=output)
        with patch.object(preflight.subprocess, "run", side_effect=run):
            self.assertEqual(preflight.run_compose(self.environment_path, values,
                             ["up", "--detach", "--no-deps", "api"]), 0)
        self.assertEqual(calls[0][-2:], ["stop", "mcp"])
        self.assertEqual(calls[1][-4:], ["up", "--detach", "--no-deps", "api"])
        self.assertIn("--force-recreate", calls[2])
        self.assertEqual(calls[2][-1], "mcp")
        self.assertEqual(calls[-1][-1], mcp_id)
        with patch.object(preflight.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0, stdout=api_id),
            subprocess.CompletedProcess([], 0, stdout=mcp_id),
            subprocess.CompletedProcess([], 0, stdout="container:" + "c" * 64),
        ]):
            with self.assertRaisesRegex(preflight.PreflightError, "different API namespace"):
                preflight.validate_running_mcp_namespace(["docker", "compose"], values)

    def test_isolated_bootstrap_does_not_start_or_stop_mcp(self):
        values = dict(self.environment, WORKSTREAM_MCP_IMAGE="example.test/mcp@sha256:" + "b" * 64)
        for service in ("model-proxy", "demo-identity", "guide-document-parser"):
            with self.subTest(service=service), patch.object(
                preflight.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
            ) as run:
                self.assertEqual(preflight.run_compose(self.environment_path, values,
                                 ["up", "-d", service]), 0)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][-3:], ["up", "-d", service])

    def test_failed_api_replacement_does_not_restart_mcp(self):
        values = dict(self.environment, WORKSTREAM_MCP_IMAGE="example.test/mcp@sha256:" + "b" * 64)
        with patch.object(preflight.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 1),
        ]) as run:
            self.assertEqual(preflight.run_compose(self.environment_path, values,
                             ["up", "--detach", "--no-deps", "api"]), 1)
        self.assertEqual(run.call_count, 2)

    def demo_identity_values(self):
        values = dict(self.environment)
        values.update(
            {
                "DEMO_IDENTITY_IMAGE": "example.test/issuer@sha256:" + "a" * 64,
                "DEMO_IDENTITY_ISSUER": "https://identity.example.test",
                "DEMO_IDENTITY_AUDIENCE": values["WORKSTREAM_TOKEN_AUDIENCE"],
                "DEMO_IDENTITY_HOSTNAME": "identity.example.test",
                "DEMO_IDENTITY_DATA_DIR": str(self.root / "issuer-data"),
                "DEMO_IDENTITY_TLS_CERT_FILE": str(self.root / "issuer-cert.pem"),
                "DEMO_IDENTITY_TLS_KEY_FILE": str(self.root / "issuer-tls-key.pem"),
                "WORKSTREAM_TOKEN_ISSUER": "https://identity.example.test",
                "WORKSTREAM_TOKEN_JWKS_URL": "https://identity.example.test/jwks.json",
            }
        )
        return values

    def test_issuer_host_mapping_is_absent_without_issuer_profile(self):
        rendered = preflight.render_compose(self.environment_path, self.environment)
        preflight.validate_compose(rendered, self.environment)
        rendered["services"]["api"]["extra_hosts"] = ["identity.example.test=host-gateway"]
        with self.assertRaisesRegex(preflight.PreflightError, "host mapping"):
            preflight.validate_compose(rendered, self.environment)

    def test_demo_identity_overlay_preserves_default_and_bounds_authority(self):
        self.assertNotIn(
            str(preflight.DEMO_IDENTITY_COMPOSE_PATH),
            preflight._compose_file_arguments(self.environment),
        )
        values = self.demo_identity_values()
        preflight.validate_environment(values)
        rendered = preflight.render_compose(self.environment_path, values)
        preflight.validate_compose(rendered, values)
        self.assertEqual(
            rendered["services"]["demo-identity"]["networks"], {"demo_identity": None}
        )
        self.assertEqual(rendered["services"]["api"]["networks"], {"default": None})
        self.assertEqual(
            rendered["services"]["api"]["extra_hosts"],
            [values["DEMO_IDENTITY_HOSTNAME"] + "=host-gateway"],
        )
        self.assertEqual(rendered["networks"]["demo_identity"]["driver"], "bridge")
        self.assertFalse(rendered["networks"]["demo_identity"].get("internal", False))
        mutations = []
        for hosts in ([], [values["DEMO_IDENTITY_HOSTNAME"] + "=127.0.0.1"],
                      ["other.example.test=host-gateway"],
                      [values["DEMO_IDENTITY_HOSTNAME"] + "=host-gateway", "extra.test=host-gateway"]):
            changed = copy.deepcopy(rendered)
            changed["services"]["api"]["extra_hosts"] = hosts
            mutations.append(changed)
        changed = copy.deepcopy(rendered)
        changed["services"]["worker"]["extra_hosts"] = {values["DEMO_IDENTITY_HOSTNAME"]: "host-gateway"}
        mutations.append(changed)
        for key, value in (
            ("user", "10001:10001"),
            ("mem_limit", 0),
            ("command", ["init", "/data", "admin@example.test"]),
            ("environment", {"WORKSTREAM_DATABASE_URL": "forbidden"}),
        ):
            changed = copy.deepcopy(rendered)
            changed["services"]["demo-identity"][key] = value
            mutations.append(changed)
        for role in ("api", "worker", "beat"):
            changed = copy.deepcopy(rendered)
            changed["services"][role]["networks"] = {"demo_identity": None}
            mutations.append(changed)
        # The reproduced live failure: an internal bridge reports healthy but
        # does not expose the requested loopback host port to the ingress proxy.
        for key, value in (
            ("internal", True),
            ("driver", "host"),
            ("external", True),
            ("ipam", {"driver": "custom"}),
            ("driver_opts", {"com.docker.network.bridge.gateway_mode_ipv4": "isolated"}),
        ):
            changed = copy.deepcopy(rendered)
            changed["networks"]["demo_identity"][key] = value
            mutations.append(changed)
        changed = copy.deepcopy(rendered)
        changed["services"]["demo-identity"]["networks"]["default"] = None
        mutations.append(changed)
        changed = copy.deepcopy(rendered)
        changed["services"]["demo-identity"]["ports"][0]["host_ip"] = "0.0.0.0"
        mutations.append(changed)
        changed = copy.deepcopy(rendered)
        changed["services"]["demo-identity"]["volumes"][0]["source"] = str(self.root)
        mutations.append(changed)
        changed = copy.deepcopy(rendered)
        changed["services"]["demo-identity"]["healthcheck"]["test"].append("--insecure")
        mutations.append(changed)
        for changed in mutations:
            with self.subTest(changed=changed["services"]["demo-identity"]):
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_compose(changed, values)

    def test_demo_identity_configuration_rejects_partial_unpinned_and_public_settings(
        self,
    ):
        values = self.demo_identity_values()
        for key, value in (
            ("DEMO_IDENTITY_IMAGE", "issuer:latest"),
            ("DEMO_IDENTITY_HOSTNAME", "wrong.example.test"),
            ("WORKSTREAM_TOKEN_AUDIENCE", "foreign"),
            ("WORKSTREAM_TOKEN_JWKS_URL", "https://foreign.example.test/jwks.json"),
            ("DEMO_IDENTITY_PUBLISHED_BIND", "0.0.0.0"),
            ("DEMO_IDENTITY_ISSUER", "https://identity.example.test/path"),
            ("DEMO_IDENTITY_TLS_KEY_FILE", "relative/key.pem"),
        ):
            with self.subTest(key=key):
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_environment({**values, key: value})
        del values["DEMO_IDENTITY_DATA_DIR"]
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_environment(values)

    def test_demo_identity_host_custody_is_separate_and_rejects_missing_state(self):
        values = self.demo_identity_values()
        with (
            patch.object(preflight, "_private_metadata") as metadata,
            patch.object(
                Path,
                "stat",
                return_value=type("Metadata", (), {"st_ino": 1, "st_dev": 1})(),
            ),
        ):
            with self.assertRaisesRegex(preflight.PreflightError, "distinct"):
                preflight.validate_demo_identity_host_inputs(values)
            self.assertEqual(
                metadata.call_args_list[0].kwargs,
                {"kind": "directory", "uid": 12001, "gid": 12001, "mode": 0o700},
            )
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_demo_identity_host_inputs(values)
        values["DEMO_IDENTITY_DATA_DIR"] = str(
            preflight.deployment_paths(values).scratch / "issuer"
        )
        with self.assertRaisesRegex(preflight.PreflightError, "shared runtime roots"):
            preflight.validate_environment(values)

    def test_demo_identity_bootstrap_checks_only_issuer_inputs_and_waits(self):
        values = self.demo_identity_values()
        with (
            patch.object(
                compose,
                "parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "env_file": self.environment_path,
                        "compose_arguments": ["start", "demo-identity"],
                    },
                )(),
            ),
            patch.object(compose, "parse_environment", return_value=values),
            patch.object(compose, "render_compose", return_value={}),
            patch.object(compose, "validate_compose"),
            patch.object(
                compose, "validate_demo_identity_host_inputs"
            ) as issuer_inputs,
            patch.object(compose, "validate_private_host_inputs") as backend_inputs,
            patch.object(compose, "load_checker_config") as checker_inputs,
            patch.object(compose, "run_compose", return_value=0),
        ):
            self.assertEqual(compose.main(), 0)
            issuer_inputs.assert_called_once_with(values)
            backend_inputs.assert_not_called()
            checker_inputs.assert_not_called()
        with patch.object(
            preflight.subprocess,
            "run",
            return_value=type("Result", (), {"returncode": 0})(),
        ) as run:
            self.assertEqual(
                preflight.run_compose(
                    self.environment_path, values, ["start", "demo-identity"]
                ),
                0,
            )
            command = run.call_args.args[0]
            self.assertEqual(
                command[-7:],
                [
                    "up",
                    "--detach",
                    "--no-deps",
                    "--wait",
                    "--wait-timeout",
                    "60",
                    "demo-identity",
                ],
            )
            self.assertEqual(run.call_args.kwargs["timeout"], 120)

    def test_optional_github_app_render_is_worker_only(self) -> None:
        values = dict(self.environment)
        values.update({
            "WORKSTREAM_GITHUB_APP_ID": "123",
            "WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE": str(self.root / "github.pem"),
            "WORKSTREAM_GITHUB_APP_INSTALLATION_ID": "456",
        })
        preflight.validate_environment(values)
        rendered = preflight.render_compose(self.environment_path, values)
        preflight.validate_compose(rendered, values)
        self.assertIn("github_app_private_key", rendered["secrets"])
        self.assertIn(preflight.GITHUB_COMPOSE_PATH.as_posix(), preflight._compose_file_arguments(values))
        for role, service in rendered["services"].items():
            environment = service.get("environment", {})
            mounted = {item["source"] for item in service.get("secrets", [])}
            if role == "worker":
                self.assertEqual(environment["WORKSTREAM_GITHUB_APP_ID"], "123")
                self.assertEqual(environment["WORKSTREAM_GITHUB_APP_INSTALLATION_ID"], "456")
                self.assertIn("github_app_private_key", mounted)
            else:
                self.assertTrue(set(preflight.GITHUB_APP_KEYS).isdisjoint(environment))
                self.assertNotIn("github_app_private_key", mounted)
            with self.subTest(injected_role=role):
                altered = copy.deepcopy(rendered)
                altered["services"][role]["environment"]["WORKSTREAM_GITHUB_APP_PRIVATE_KEY"] = "synthetic-private-value"
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_compose(altered, values)
            if role != "worker":
                altered = copy.deepcopy(rendered)
                altered["services"][role]["environment"]["WORKSTREAM_GITHUB_APP_ID"] = "123"
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_compose(altered, values)
        baseline = preflight.render_compose(self.environment_path, self.environment)
        preflight.validate_compose(baseline, self.environment)
        self.assertNotIn("github_app_private_key", baseline["secrets"])
        self.assertNotIn(str(preflight.GITHUB_COMPOSE_PATH), preflight._compose_file_arguments(self.environment))
        self.assertIn("WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE", preflight._secret_file_keys(values))
        self.assertNotIn("WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE", preflight._secret_file_keys(self.environment))

    def test_github_app_requires_safe_paired_configuration(self) -> None:
        valid = dict(self.environment, WORKSTREAM_GITHUB_APP_ID="123",
                     WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE=str(self.root / "github.pem"))
        preflight.validate_environment(valid)
        cases = [
            {"WORKSTREAM_GITHUB_APP_ID": ""},
            {"WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE": ""},
            {"WORKSTREAM_GITHUB_APP_ID": "0"},
            {"WORKSTREAM_GITHUB_APP_ID": "-1"},
            {"WORKSTREAM_GITHUB_APP_ID": "１２３"},
            {"WORKSTREAM_GITHUB_APP_INSTALLATION_ID": "0"},
            {"WORKSTREAM_GITHUB_APP_INSTALLATION_ID": "not-an-id"},
            {"WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE": "relative.pem"},
            {"WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE": str(self.root / ".." / "github.pem")},
            {"WORKSTREAM_GITHUB_APP_PRIVATE_KEY": "synthetic-private-value"},
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(preflight.PreflightError):
                preflight.validate_environment(valid | changes)
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_environment(self.environment | {"WORKSTREAM_GITHUB_APP_INSTALLATION_ID": "456"})

    def _render_modified_compose(self, compose_text: str) -> dict[str, object]:
        compose_path = self.root / "compose.yml"
        compose_path.write_text(compose_text, encoding="utf-8")
        with patch.object(preflight, "COMPOSE_PATH", compose_path):
            return preflight.render_compose(self.environment_path, self.environment)

    def test_roles_anywhere_timer_is_bounded_and_five_minute(self) -> None:
        guide = ROLES_ANYWHERE_GUIDE.read_text(encoding="utf-8")
        self.assertIn("OnCalendar=*-*-* *:0/5:00", guide)
        self.assertIn("AccuracySec=5s", guide)
        self.assertIn("RandomizedDelaySec=10s", guide)
        self.assertIn("TimeoutStartSec=120s", guide)
        self.assertNotIn("OnCalendar=daily", guide)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_valid_configuration_and_rendered_topology(self) -> None:
        self.assertEqual(
            str(preflight.deployment_paths(self.environment).socket_root),
            "/var/lib/workstream/checker-runtime",
        )
        preflight.validate_environment(self.environment)
        preflight.validate_checker_config(self.checker, self.environment)
        rendered = preflight.render_compose(self.environment_path, self.environment)
        preflight.validate_compose(rendered, self.environment)
        self.assertEqual(
            set(rendered["services"]),
            {
                "api",
                "worker",
                "beat",
                "model-proxy",
                "guide-document-parser",
                *preflight.PROOF_SERVICES,
            },
        )
        self.assertNotIn("build", rendered["services"]["api"])
        services = rendered["services"]
        evidence = {
            key: self.environment[key] for key in preflight.AWS_S3_EVIDENCE_KEYS
        }
        for name in (
            "api",
            "worker",
            "beat",
            "model-proxy",
            "guide-document-parser",
        ):
            service = services[name]
            self.assertEqual(service["pull_policy"], "always")
            self.assertTrue(service["init"])
            self.assertEqual(service["restart"], "on-failure:5")
            self.assertTrue(service["healthcheck"]["test"])
        for name in preflight.PROOF_SERVICES:
            self.assertEqual(services[name]["pull_policy"], "never")
            self.assertEqual(services[name]["profiles"], ["aws-proof"])
            self.assertEqual(services[name]["command"], ["/bin/false"])
        for name in preflight.ROLE_SECRET_FILE_KEYS:
            service_environment = services[name]["environment"]
            self.assertEqual(
                {
                    key: service_environment[key]
                    for key in preflight.AWS_S3_EVIDENCE_KEYS
                },
                evidence,
            )
        project_agent_configuration = {
            key: self.environment[key]
            for key in preflight.PROJECT_AGENT_CONFIGURATION_KEYS
        }
        for name in (
            "api",
            "worker",
            "beat",
            "model-proxy",
            *preflight.PROOF_SERVICES,
        ):
            self.assertEqual(
                {
                    key: services[name]["environment"][key]
                    for key in preflight.PROJECT_AGENT_CONFIGURATION_KEYS
                },
                project_agent_configuration,
            )
        api_command = " ".join(services["api"]["command"])
        worker_command = " ".join(services["worker"]["command"])
        self.assertIn("alembic upgrade head", api_command)
        self.assertNotIn("--reload", api_command)
        self.assertIn("--pool=prefork", worker_command)
        health_commands = {
            name: " ".join(services[name]["healthcheck"]["test"])
            for name in (
                "api",
                "worker",
                "beat",
                "model-proxy",
            )
        }
        self.assertIn("/api/v1/health", health_commands["api"])
        self.assertIn("/tmp/celery-worker.pid", health_commands["worker"])
        self.assertIn("/tmp/celerybeat.pid", health_commands["beat"])
        self.assertIn(
            "/var/lib/workstream/model-runtime/model.sock",
            health_commands["model-proxy"],
        )
        self.assertNotIn("checker-service", services)
        for service in services.values():
            self.assertNotIn("/var/run/docker.sock", preflight._service_mounts(service))
        self.assertEqual(services["api"]["stop_grace_period"], "30s")
        self.assertIn(services["worker"]["stop_grace_period"], {"7320s", "2h2m0s"})
        self.assertIn(services["model-proxy"]["stop_grace_period"], {"7320s", "2h2m0s"})
        self.assertEqual(services["beat"]["stop_grace_period"], "30s")
        self.assertEqual(services["guide-document-parser"]["stop_grace_period"], "30s")
        self.assertEqual(services["api"]["ports"][0]["host_ip"], "127.0.0.1")
        expected_secrets = {
            preflight.SECRET_FILE_TARGETS[key][0]
            for key in preflight._secret_file_keys(self.environment)
        }
        self.assertEqual(set(rendered["secrets"]), expected_secrets)
        for key in preflight._secret_file_keys(self.environment):
            secret_name, _target = preflight.SECRET_FILE_TARGETS[key]
            self.assertEqual(
                rendered["secrets"][secret_name]["file"],
                self.environment[key],
            )
        for service in services.values():
            self.assertNotIn("volumes_from", service)
            self.assertNotIn("configs", service)
        for name in preflight.ROLE_SECRET_FILE_KEYS:
            file_keys = preflight._role_secret_file_keys(name, self.environment)
            self.assertEqual(
                services[name]["environment"]["WORKSTREAM_RELEASE_ROLE"], name
            )
            mounted = services[name]["secrets"]
            expected_role_secrets = {
                preflight.SECRET_FILE_TARGETS[key][0] for key in file_keys
            }
            self.assertEqual(
                {item["source"] for item in mounted}, expected_role_secrets
            )
            self.assertTrue(all(item["mode"] in (0o400, "0400") for item in mounted))
            for key in preflight.SECRET_FILE_KEYS:
                if key in file_keys:
                    self.assertEqual(
                        services[name]["environment"][key],
                        preflight.SECRET_FILE_TARGETS[key][1],
                    )
                else:
                    self.assertNotIn(key, services[name]["environment"])
        parser = services["guide-document-parser"]
        self.assertEqual(parser["image"], services["api"]["image"])
        self.assertEqual(parser["user"], "0:0")
        self.assertEqual(parser["cap_drop"], ["ALL"])
        self.assertEqual(parser["cap_add"], ["KILL", "SETGID", "SETUID"])
        self.assertEqual(parser["network_mode"], "none")
        self.assertNotIn("secrets", parser)
        self.assertEqual(
            parser["environment"],
            {
                "WORKSTREAM_RELEASE_ROLE": "parser",
                "WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET": str(
                    preflight.deployment_paths(self.environment).guide_socket
                ),
            },
        )
        self.assertEqual(parser["mem_limit"], "536870912")
        self.assertEqual(parser["memswap_limit"], "536870912")
        self.assertEqual(parser["cpus"], 1)
        self.assertEqual(parser["pids_limit"], 64)
        self.assertFalse(
            preflight._service_mounts(parser)[
                str(preflight.deployment_paths(self.environment).guide_root)
            ].get("read_only", False)
        )
        worker_mounts = preflight._service_mounts(services["worker"])
        self.assertTrue(
            worker_mounts[str(preflight.deployment_paths(self.environment).guide_root)][
                "read_only"
            ]
        )
        for name in (
            "api",
            "beat",
            *preflight.PROOF_SERVICES,
        ):
            self.assertNotIn(
                str(preflight.deployment_paths(self.environment).guide_root),
                preflight._service_mounts(services[name]),
            )
        for name in ("api", "worker", "model-proxy"):
            mounts = preflight._service_mounts(services[name])
            self.assertEqual(
                mounts[str(preflight.ROLES_ANYWHERE_CERTIFICATE_TARGET)]["source"],
                str(self.runtime_certificate),
            )
            self.assertTrue(
                mounts[str(preflight.ROLES_ANYWHERE_PRIVATE_KEY_TARGET)]["read_only"]
            )
        beat_mounts = preflight._service_mounts(services["beat"])
        self.assertEqual(beat_mounts, {})
        model_socket_root = str(preflight.deployment_paths(self.environment).model_root)
        self.assertTrue(worker_mounts[model_socket_root]["read_only"])
        self.assertFalse(
            preflight._service_mounts(services["model-proxy"])[model_socket_root].get(
                "read_only", False
            )
        )
        for name in ("api", "beat", *preflight.PROOF_SERVICES):
            self.assertNotIn(
                model_socket_root,
                preflight._service_mounts(services[name]),
            )
        relay_root = str(preflight.deployment_paths(self.environment).model_relays)
        for name, service in services.items():
            self.assertNotIn(relay_root, preflight._service_mounts(service))
        for role in ("api", "worker"):
            self.assertEqual(
                services[role]["environment"][
                    "WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET"
                ],
                str(preflight.deployment_paths(self.environment).socket),
            )
            self.assertEqual(
                services[role]["environment"][
                    "WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET"
                ],
                str(preflight.deployment_paths(self.environment).socket),
            )

    def test_actual_render_rejects_beat_inheriting_api_volumes(self) -> None:
        compose_text = preflight.COMPOSE_PATH.read_text(encoding="utf-8").replace(
            "  beat:\n    <<: *backend-runtime\n",
            "  beat:\n    <<: *backend-runtime\n    volumes_from:\n      - api:ro\n",
            1,
        )
        rendered = self._render_modified_compose(compose_text)

        self.assertEqual(rendered["services"]["beat"]["volumes_from"], ["api:ro"])
        with self.assertRaisesRegex(preflight.PreflightError, "inherit"):
            preflight.validate_compose(rendered, self.environment)

    def test_actual_render_rejects_config_backed_by_runtime_private_key(self) -> None:
        compose_text = preflight.COMPOSE_PATH.read_text(encoding="utf-8").replace(
            "  beat:\n    <<: *backend-runtime\n",
            "  beat:\n    <<: *backend-runtime\n"
            "    configs:\n"
            "      - source: runtime_private_key\n"
            "        target: /run/unrelated/key.pem\n",
            1,
        )
        compose_text += (
            "\nconfigs:\n"
            "  runtime_private_key:\n"
            "    file: "
            "${WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_RUNTIME_PRIVATE_KEY_HOST_FILE}\n"
        )
        rendered = self._render_modified_compose(compose_text)

        self.assertEqual(
            rendered["services"]["beat"]["configs"][0]["target"],
            "/run/unrelated/key.pem",
        )
        self.assertEqual(
            rendered["configs"]["runtime_private_key"]["file"],
            str(self.runtime_private_key),
        )
        with self.assertRaisesRegex(preflight.PreflightError, "Compose configs"):
            preflight.validate_compose(rendered, self.environment)

    def test_actual_render_rejects_extra_backend_identity_binds(self) -> None:
        compose_text = preflight.COMPOSE_PATH.read_text(encoding="utf-8")
        cases = (
            (
                "API readiness key",
                "    restart: on-failure:5\n    stop_grace_period: 30s\n    healthcheck:\n      test: [CMD, python, -c,",
                "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_READINESS_PRIVATE_KEY_HOST_FILE",
                "/run/unrelated/readiness-key.pem",
            ),
            (
                "API negative key",
                "    restart: on-failure:5\n    stop_grace_period: 30s\n    healthcheck:\n      test: [CMD, python, -c,",
                "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_NEGATIVE_PRIVATE_KEY_HOST_FILE",
                "/run/unrelated/negative-key.pem",
            ),
            (
                "worker readiness certificate",
                "    depends_on:\n      api:\n",
                "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_READINESS_CERTIFICATE_HOST_FILE",
                "/run/unrelated/readiness-certificate.pem",
            ),
        )
        for label, marker, source_key, target in cases:
            with self.subTest(label=label):
                extra_bind = (
                    "      - type: bind\n"
                    f"        source: ${{{source_key}}}\n"
                    f"        target: {target}\n"
                    "        read_only: true\n"
                )
                rendered = self._render_modified_compose(
                    compose_text.replace(marker, extra_bind + marker, 1)
                )
                service_name = "worker" if label.startswith("worker") else "api"
                rendered_mounts = preflight._service_mounts(
                    rendered["services"][service_name]
                )
                self.assertEqual(
                    rendered_mounts[target]["source"],
                    self.environment[source_key],
                )
                with self.assertRaisesRegex(
                    preflight.PreflightError,
                    f"{service_name} bind mounts differ",
                ):
                    preflight.validate_compose(rendered, self.environment)

    def test_actual_render_rejects_parser_hardlink_identity_bind(self) -> None:
        private_key_alias = self.root / "runtime-key-parser-alias.pem"
        os.link(self.runtime_private_key, private_key_alias)
        marker = "    healthcheck:\n      test: [CMD, python, -m, app.adapters.guide_document_tools.service"
        extra_bind = (
            "      - type: bind\n"
            f"        source: {private_key_alias}\n"
            "        target: /run/unrelated/key.pem\n        read_only: true\n"
        )
        compose_text = preflight.COMPOSE_PATH.read_text(encoding="utf-8").replace(
            marker, extra_bind + marker, 1
        )
        rendered = self._render_modified_compose(compose_text)
        parser_mounts = preflight._service_mounts(
            rendered["services"]["guide-document-parser"]
        )
        self.assertEqual(
            parser_mounts["/run/unrelated/key.pem"]["source"], str(private_key_alias)
        )
        with self.assertRaisesRegex(
            preflight.PreflightError, "guide-document-parser bind"
        ):
            preflight.validate_compose(rendered, self.environment)

    def test_actual_render_rejects_secret_file_substitution(self) -> None:
        compose_text = preflight.COMPOSE_PATH.read_text(encoding="utf-8").replace(
            "${WORKSTREAM_DATABASE_URL_FILE:?set the private database URL file}",
            "${WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_RUNTIME_PRIVATE_KEY_HOST_FILE}",
            1,
        )
        rendered = self._render_modified_compose(compose_text)

        self.assertEqual(
            rendered["secrets"]["database_url"]["file"],
            str(self.runtime_private_key),
        )
        self.assertEqual(
            {item["source"] for item in rendered["services"]["beat"]["secrets"]},
            {"database_url", "celery_broker_url"},
        )
        with self.assertRaisesRegex(preflight.PreflightError, "database_url"):
            preflight.validate_compose(rendered, self.environment)

    def test_compose_secret_mode_encodings_preserve_owner_only_read(self) -> None:
        rendered = preflight.render_compose(self.environment_path, self.environment)
        for mode in (0o400, "0400"):
            candidate = copy.deepcopy(rendered)
            for role in preflight.ROLE_SECRET_FILE_KEYS:
                for secret in candidate["services"][role]["secrets"]:
                    secret["mode"] = mode
            with self.subTest(valid_mode=mode):
                preflight.validate_compose(candidate, self.environment)
        for mode in (400, 256.0, "400", "0444", 0o444, "0600", 0o600, True, None):
            candidate = copy.deepcopy(rendered)
            candidate["services"]["api"]["secrets"][0]["mode"] = mode
            with (
                self.subTest(invalid_mode=mode),
                self.assertRaisesRegex(preflight.PreflightError, "mounted secrets"),
            ):
                preflight.validate_compose(candidate, self.environment)

    def test_render_and_compose_operation_ignore_hostile_ambient_environment(
        self,
    ) -> None:
        hostile = {
            "WORKSTREAM_TOKEN_JWKS_URL": "https://attacker.invalid/jwks",
            "WORKSTREAM_DATABASE_URL_FILE": "/tmp/attacker-database",
            "WORKSTREAM_BACKEND_IMAGE": "attacker.invalid/backend:latest",
            "COMPOSE_FILE": "/tmp/attacker-compose.yml",
            "DOCKER_HOST": "tcp://attacker.invalid:2375",
            "AWS_ACCESS_KEY_ID": "ambient-secret",
        }
        with patch.dict(os.environ, hostile):
            rendered = preflight.render_compose(self.environment_path, self.environment)
            self.assertEqual(
                rendered["services"]["api"]["environment"]["WORKSTREAM_TOKEN_JWKS_URL"],
                self.environment["WORKSTREAM_TOKEN_JWKS_URL"],
            )
            self.assertEqual(
                rendered["secrets"]["database_url"]["file"],
                self.environment["WORKSTREAM_DATABASE_URL_FILE"],
            )
            with patch.object(preflight.subprocess, "run") as run:
                run.return_value.returncode = 0
                self.assertEqual(
                    preflight.run_compose(
                        self.environment_path,
                        self.environment,
                        ["up", "--detach", "--wait"],
                    ),
                    0,
                )
        operation_environment = run.call_args.kwargs["env"]
        self.assertEqual(
            operation_environment["WORKSTREAM_TOKEN_JWKS_URL"],
            self.environment["WORKSTREAM_TOKEN_JWKS_URL"],
        )
        self.assertEqual(
            operation_environment["WORKSTREAM_ARTIFACT_S3_RUNTIME_ROLE_ARN"],
            self.environment["WORKSTREAM_ARTIFACT_S3_RUNTIME_ROLE_ARN"],
        )
        self.assertEqual(
            operation_environment["DOCKER_HOST"], "unix:///var/run/docker.sock"
        )
        for key in ("COMPOSE_FILE", "AWS_ACCESS_KEY_ID"):
            self.assertNotIn(key, operation_environment)
        self.assertIn(
            "deploy/hosted/compose.py", (ROOT / "deploy/hosted/README.md").read_text()
        )

    def _compose_main(self, *arguments: str) -> tuple[int, str]:
        errors = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                ["compose.py", "--env-file", str(self.environment_path), *arguments],
            ),
            redirect_stderr(errors),
        ):
            result = compose.main()
        return result, errors.getvalue()

    def test_launch_rechecks_checker_selectors_after_preflight(self) -> None:
        with (
            patch.object(
                sys, "argv", ["preflight.py", "--env-file", str(self.environment_path)]
            ),
            patch.object(preflight, "validate_private_host_inputs"),
            patch.object(preflight, "validate_smol_runtime"),
            patch.object(preflight, "validate_trusted_intake"),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(preflight.main(), 0)
        for field, unsafe in (("runtime", "runc"), ("isolation_mode", "docker-dev")):
            with self.subTest(field=field):
                self.checker_path.write_text(
                    json.dumps(self.checker | {field: unsafe}), encoding="utf-8"
                )
                with (
                    patch.object(compose, "validate_private_host_inputs") as private,
                    patch.object(compose, "validate_smol_runtime") as runtime,
                    patch.object(compose, "run_compose") as run,
                ):
                    result, error = self._compose_main("up")
                self.assertEqual(result, 1)
                self.assertIn(f"unsafe release value: {field}", error)
                private.assert_not_called()
                runtime.assert_not_called()
                run.assert_not_called()

    def test_launch_checks_host_and_runtime_before_starting(self) -> None:
        for failure in (None, "private", "runtime", "intake"):
            with self.subTest(failure=failure):
                order = []

                def private_check(values):
                    self.assertEqual(values, self.environment)
                    order.append("private")
                    if failure == "private":
                        raise preflight.PreflightError("private host rejected")

                def runtime_check(config, values):
                    self.assertEqual(config, self.checker)
                    self.assertEqual(values, self.environment)
                    order.append("runtime")
                    if failure == "runtime":
                        raise preflight.PreflightError("Docker runtime rejected")

                def intake_check(values):
                    self.assertEqual(values, self.environment)
                    order.append("intake")
                    if failure == "intake":
                        raise preflight.PreflightError("trusted intake rejected")

                def launch(path, values, arguments):
                    self.assertEqual(path, self.environment_path)
                    self.assertEqual(values, self.environment)
                    self.assertEqual(arguments, ["up"])
                    order.append("launch")
                    return 0

                with (
                    patch.object(
                        compose,
                        "validate_private_host_inputs",
                        side_effect=private_check,
                    ),
                    patch.object(
                        compose, "validate_smol_runtime", side_effect=runtime_check
                    ),
                    patch.object(
                        compose, "validate_trusted_intake", side_effect=intake_check
                    ),
                    patch.object(compose, "run_compose", side_effect=launch) as run,
                ):
                    result, error = self._compose_main("up")
                if failure is None:
                    self.assertEqual((result, error), (0, ""))
                    self.assertEqual(order, ["private", "runtime", "intake", "launch"])
                    run.assert_called_once()
                else:
                    self.assertEqual(result, 1)
                    self.assertIn("rejected", error)
                    self.assertEqual(
                        order,
                        {
                            "private": ["private"],
                            "runtime": ["private", "runtime"],
                            "intake": ["private", "runtime", "intake"],
                        }[failure],
                    )
                    run.assert_not_called()

    def test_stop_remains_available_with_invalid_checker_configuration(self) -> None:
        self.checker_path.write_text("invalid json", encoding="utf-8")
        with (
            patch.object(compose, "load_checker_config") as load,
            patch.object(compose, "validate_private_host_inputs") as private,
            patch.object(compose, "validate_smol_runtime") as runtime,
            patch.object(compose, "run_shutdown", return_value=0) as shutdown,
        ):
            self.assertEqual(self._compose_main("stop"), (0, ""))
        load.assert_not_called()
        private.assert_not_called()
        runtime.assert_not_called()
        shutdown.assert_called_once_with(self.environment_path, self.environment)

    def test_shutdown_drains_producers_worker_and_proxy_without_stopping_native_node(
        self,
    ) -> None:
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(preflight.subprocess, "run", return_value=completed) as run:
            self.assertEqual(
                preflight.run_shutdown(self.environment_path, self.environment), 0
            )
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][-3:], ["stop", "beat", "api"])
        self.assertEqual(commands[1][-4:], ["stop", "--timeout", "7320", "worker"])
        self.assertEqual(
            commands[2][-4:],
            ["stop", "--timeout", "7320", "model-proxy"],
        )
        self.assertEqual(
            commands[3][-2:],
            ["stop", "guide-document-parser"],
        )

    def test_shutdown_failure_keeps_later_dependencies_running(self) -> None:
        for failed_phase in (0, 1, 2):
            with self.subTest(failed_phase=failed_phase):
                results = [
                    subprocess.CompletedProcess([], 17 if index == failed_phase else 0)
                    for index in range(4)
                ]
                with patch.object(
                    preflight.subprocess, "run", side_effect=results
                ) as run:
                    self.assertEqual(
                        preflight.run_shutdown(
                            self.environment_path,
                            self.environment,
                        ),
                        17,
                    )
                self.assertEqual(run.call_count, failed_phase + 1)

    def test_stop_rejects_caller_selected_service_order(self) -> None:
        errors = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "compose.py",
                    "--env-file",
                    str(self.environment_path),
                    "stop",
                    "worker",
                    "api",
                ],
            ),
            patch.object(compose, "run_shutdown") as shutdown,
            redirect_stderr(errors),
        ):
            self.assertEqual(compose.main(), 1)
        shutdown.assert_not_called()
        self.assertIn(
            "fixed shutdown sequence or exactly one worker", errors.getvalue()
        )

    def test_exact_worker_stop_preserves_dependencies_and_start_rechecks_native(self):
        self.checker_path.write_text("invalid json", encoding="utf-8")
        with (
            patch.object(compose, "load_checker_config") as load,
            patch.object(compose, "run_compose", return_value=0) as run,
        ):
            self.assertEqual(self._compose_main("stop", "worker"), (0, ""))
        load.assert_not_called()
        run.assert_called_once_with(
            self.environment_path, self.environment, ["stop", "worker"]
        )
        self.checker_path.write_text(json.dumps(self.checker), encoding="utf-8")
        for failure in (None, "private", "native", "intake"):
            with (
                self.subTest(failure=failure),
                patch.object(
                    compose,
                    "validate_private_host_inputs",
                    side_effect=preflight.PreflightError("private")
                    if failure == "private"
                    else None,
                ) as private,
                patch.object(
                    compose,
                    "validate_smol_runtime",
                    side_effect=preflight.PreflightError("native")
                    if failure == "native"
                    else None,
                ) as native,
                patch.object(
                    compose,
                    "validate_trusted_intake",
                    side_effect=preflight.PreflightError("intake")
                    if failure == "intake"
                    else None,
                ) as intake,
                patch.object(compose, "run_compose", return_value=0) as run,
            ):
                result, _ = self._compose_main("start", "worker")
                self.assertEqual(result, 0 if failure is None else 1)
                if failure is None:
                    private.assert_called_once_with(self.environment)
                    native.assert_called_once_with(self.checker, self.environment)
                    intake.assert_called_once_with(self.environment)
                    run.assert_called_once_with(
                        self.environment_path, self.environment, ["start", "worker"]
                    )
                else:
                    run.assert_not_called()

    def test_worker_operations_have_fixed_grace_readiness_and_management_bounds(self):
        cases = (
            (["stop", "worker"], ["stop", "--timeout", "7320", "worker"], 7380),
            (
                ["start", "worker"],
                [
                    "up",
                    "--detach",
                    "--no-deps",
                    "--wait",
                    "--wait-timeout",
                    "60",
                    "worker",
                ],
                120,
            ),
        )
        for arguments, expected, timeout in cases:
            with (
                self.subTest(arguments=arguments),
                patch.object(
                    preflight.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0),
                ) as run,
            ):
                self.assertEqual(
                    preflight.run_compose(
                        self.environment_path, self.environment, arguments
                    ),
                    0,
                )
                self.assertEqual(run.call_args.args[0][-len(expected) :], expected)
                self.assertEqual(run.call_args.kwargs["timeout"], timeout)
                self.assertEqual(
                    run.call_args.kwargs["env"]["DOCKER_HOST"],
                    "unix:///var/run/docker.sock",
                )
            with patch.object(
                preflight.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("docker", timeout),
            ):
                with self.assertRaisesRegex(
                    preflight.PreflightError, "management deadline"
                ):
                    preflight.run_compose(
                        self.environment_path, self.environment, arguments
                    )
        for arguments in (
            ["start", "api"],
            ["restart", "worker"],
            ["stop", "--timeout", "0", "worker"],
            ["start", "worker", "api"],
        ):
            with (
                self.subTest(arguments=arguments),
                patch.object(preflight.subprocess, "run") as run,
            ):
                with self.assertRaises(preflight.PreflightError):
                    preflight.run_compose(
                        self.environment_path, self.environment, arguments
                    )
                run.assert_not_called()

    def test_proof_wrapper_runs_only_the_fixed_identity_sequence(self) -> None:
        nonce = "0199f68b-5dc2-7000-8000-000000000001"
        with (
            patch.object(
                sys,
                "argv",
                [
                    "compose.py",
                    "--env-file",
                    str(self.environment_path),
                    "proof",
                    "--group-nonce",
                    nonce,
                ],
            ),
            patch.object(compose, "load_checker_config", return_value=self.checker),
            patch.object(compose, "validate_private_host_inputs") as private,
            patch.object(compose, "validate_smol_runtime") as native,
            patch.object(compose, "validate_trusted_intake") as intake,
            patch.object(compose, "run_proof_group", return_value=0) as proof_group,
        ):
            self.assertEqual(compose.main(), 0)
        private.assert_called_once_with(self.environment, require_node=False)
        native.assert_not_called()
        intake.assert_not_called()
        self.assertEqual(str(proof_group.call_args.args[2]), nonce)
        for invalid in (["proof"], ["proof", "--group-nonce", "not-a-uuid"]):
            with (
                self.subTest(invalid=invalid),
                patch.object(
                    sys,
                    "argv",
                    ["compose.py", "--env-file", str(self.environment_path), *invalid],
                ),
                redirect_stderr(io.StringIO()),
                patch.object(compose, "run_proof_group") as run,
            ):
                self.assertEqual(compose.main(), 1)
                run.assert_not_called()

    def test_proof_group_runs_identities_then_credential_free_coordinator(self) -> None:
        nonce = preflight.UUID("0199f68b-5dc2-7000-8000-000000000001")
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(preflight.subprocess, "run", return_value=completed) as run:
            self.assertEqual(
                preflight.run_proof_group(
                    self.environment_path, self.environment, nonce
                ),
                0,
            )
        commands = [
            call.args[0]
            for call in run.call_args_list
            if call.args[0][:2] == ["docker", "compose"]
        ]
        cleanup = [
            call.args[0]
            for call in run.call_args_list
            if call.args[0][:3] == ["docker", "rm", "--force"]
        ]
        self.assertEqual(
            [command[command.index("--name") + 2] for command in commands],
            list(preflight.PROOF_SERVICES),
        )
        self.assertEqual(
            [
                command[command.index("scripts.aws_artifact_provider_proof") + 1]
                for command in commands
            ],
            list(preflight.PROOF_SERVICES.values()),
        )
        self.assertTrue(all("--rm" in command for command in commands))
        self.assertTrue(
            all(
                command[command.index(service) + 1 : command.index(service) + 5]
                == [
                    "/usr/bin/timeout",
                    "--signal=TERM",
                    f"--kill-after={preflight.PROOF_INNER_KILL_AFTER_SECONDS}s",
                    next(
                        value
                        for value in command
                        if value.endswith("s") and value[:-1].isdigit()
                    ),
                ]
                for command, service in zip(commands, preflight.PROOF_SERVICES)
            )
        )
        expected_names = [
            f"workstream-proof-{nonce.hex}-{service}"
            for service in preflight.PROOF_SERVICES
        ]
        self.assertEqual(
            [command[command.index("--name") + 1] for command in commands],
            expected_names,
        )
        self.assertEqual([command[-1] for command in cleanup], expected_names)
        self.assertTrue(
            all(call.kwargs.get("timeout", 0) > 0 for call in run.call_args_list)
        )

    def test_proof_services_reject_registry_dependent_pull_policies(self) -> None:
        rendered = preflight.render_compose(self.environment_path, self.environment)
        for name in preflight.PROOF_SERVICES:
            for policy in (None, "always", "missing"):
                with self.subTest(service=name, policy=policy):
                    altered = copy.deepcopy(rendered)
                    if policy is None:
                        altered["services"][name].pop("pull_policy")
                    else:
                        altered["services"][name]["pull_policy"] = policy
                    with self.assertRaisesRegex(
                        preflight.PreflightError, "cached release image without pulling"
                    ):
                        preflight.validate_compose(altered, self.environment)

    def test_missing_cached_proof_image_stops_before_later_identities(self) -> None:
        nonce = preflight.UUID("0199f68b-5dc2-7000-8000-000000000001")
        calls: list[list[str]] = []

        def missing_image_then_cleanup(command, **kwargs):
            calls.append(command)
            if command[:2] == ["docker", "compose"]:
                return subprocess.CompletedProcess(command, 1)
            return subprocess.CompletedProcess(command, 0)

        with patch.object(
            preflight.subprocess, "run", side_effect=missing_image_then_cleanup
        ):
            self.assertEqual(
                preflight.run_proof_group(
                    self.environment_path, self.environment, nonce
                ),
                1,
            )
        name = f"workstream-proof-{nonce.hex}-aws-proof-runtime"
        self.assertEqual(len(calls), 2)
        self.assertIn("aws-proof-runtime", calls[0])
        self.assertEqual(calls[1], ["docker", "rm", "--force", name])
        self.assertFalse(any("aws-proof-coordinate" in command for command in calls))

    def test_proof_group_timeout_cleans_exact_container_and_stops_sequence(
        self,
    ) -> None:
        nonce = preflight.UUID("0199f68b-5dc2-7000-8000-000000000001")
        calls: list[list[str]] = []

        def timeout_then_cleanup(command, **kwargs):
            calls.append(command)
            if command[:2] == ["docker", "compose"]:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return subprocess.CompletedProcess(command, 0)

        with patch.object(
            preflight.subprocess, "run", side_effect=timeout_then_cleanup
        ):
            self.assertEqual(
                preflight.run_proof_group(
                    self.environment_path, self.environment, nonce
                ),
                preflight.PROOF_TIMEOUT_RETURN_CODE,
            )
        name = f"workstream-proof-{nonce.hex}-aws-proof-runtime"
        self.assertEqual(
            [command[:2] for command in calls],
            [["docker", "compose"], ["docker", "rm"]],
        )
        self.assertEqual(calls[1], ["docker", "rm", "--force", name])
        self.assertFalse(any("aws-proof-coordinate" in command for command in calls))

    def test_artifact_preparation_deadline_is_required_bounded_and_shared(self):
        key = "WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS"
        for deadline in ("360", "3400"):
            values = self.environment | {key: deadline}
            with self.subTest(deadline=deadline):
                preflight.validate_environment(values)
                rendered = preflight.render_compose(self.environment_path, values)
                preflight.validate_compose(rendered, values)
                for role in (
                    *preflight.ROLE_SECRET_FILE_KEYS,
                    *preflight.PROOF_SERVICES,
                ):
                    self.assertEqual(
                        rendered["services"][role]["environment"][key], deadline
                    )
                for mutation in ("missing", "different"):
                    changed = copy.deepcopy(rendered)
                    if mutation == "missing":
                        del changed["services"]["worker"]["environment"][key]
                    else:
                        changed["services"]["worker"]["environment"][key] = "600"
                    with (
                        self.subTest(mutation=mutation),
                        self.assertRaises(preflight.PreflightError),
                    ):
                        preflight.validate_compose(changed, values)
                changed = copy.deepcopy(rendered)
                del changed["services"]["aws-proof-runtime"]["environment"][key]
                with self.assertRaisesRegex(
                    preflight.PreflightError, "preparation deadline"
                ):
                    preflight.validate_compose(changed, values)
                changed = copy.deepcopy(rendered)
                for role in preflight.ROLE_SECRET_FILE_KEYS:
                    changed["services"][role]["environment"][key] = "600"
                with self.assertRaisesRegex(preflight.PreflightError, key):
                    preflight.validate_compose(changed, values)
        for deadline in (
            "",
            "NaN",
            "Infinity",
            "-Infinity",
            "300",
            "3600",
            "0",
            "-1",
            "true",
        ):
            with (
                self.subTest(deadline=deadline),
                self.assertRaises(preflight.PreflightError),
            ):
                preflight.validate_environment(self.environment | {key: deadline})
        missing = dict(self.environment)
        del missing[key]
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_environment(missing)

    def test_environment_rejects_mutable_or_development_settings(self) -> None:
        cases = {
            "mutable image": (
                "WORKSTREAM_BACKEND_IMAGE",
                "registry.example/backend:latest",
            ),
            "local HMAC": ("WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET", "private"),
            "static AWS key": ("WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID", "private"),
            "ambient static AWS key": ("AWS_ACCESS_KEY_ID", "private"),
            "web identity token": ("AWS_WEB_IDENTITY_TOKEN_FILE", "/run/token"),
            "debug override": ("WORKSTREAM_DEBUG", "true"),
            "non-finite timeout": (
                "WORKSTREAM_ARTIFACT_S3_OPERATION_TOTAL_TIMEOUT_SECONDS",
                "NaN",
            ),
            "insecure issuer": (
                "WORKSTREAM_TOKEN_ISSUER",
                "http://identity.example/flow",
            ),
            "insecure collector": (
                "WORKSTREAM_OBSERVABILITY_OTLP_ENDPOINT",
                "http://collector",
            ),
            "introspection expansion": (
                "WORKSTREAM_TOKEN_INTROSPECTION_MODE",
                "required",
            ),
            "unsupported identity transport": (
                "WORKSTREAM_ARTIFACT_S3_AWS_WORKLOAD_IDENTITY_METHOD",
                "iam-role",
            ),
            "relative certificate": (
                "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_RUNTIME_CERTIFICATE_HOST_FILE",
                "runtime-certificate.pem",
            ),
            "wrong backend UID": ("WORKSTREAM_RUNTIME_UID", "10003"),
            "unsupported runtime": (
                "WORKSTREAM_PROJECT_AGENT_RUNTIME",
                "unregistered_runtime",
            ),
            "unsupported provider": (
                "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER",
                "unregistered_provider",
            ),
            "OpenRouter responses mismatch": (
                "WORKSTREAM_PROJECT_AGENT_MODEL_API",
                "responses",
            ),
            "provider endpoint override": (
                "WORKSTREAM_PROJECT_AGENT_BASE_URL",
                "https://attacker.invalid/v1",
            ),
            "provider key value": ("OPENROUTER_API_KEY", "private"),
            "runtime endpoint option": (
                "WORKSTREAM_PROJECT_AGENT_RUNTIME_OPTIONS",
                '{"base_url":"https://attacker.invalid/v1"}',
            ),
            "runtime options list": (
                "WORKSTREAM_PROJECT_AGENT_RUNTIME_OPTIONS",
                "[]",
            ),
        }
        for label, (key, value) in cases.items():
            with self.subTest(label=label):
                changed = self.environment | {key: value}
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_environment(changed)

    def test_environment_requires_every_aws_s3_evidence_setting(self) -> None:
        for key in preflight.AWS_S3_EVIDENCE_KEYS:
            with self.subTest(key=key):
                changed = dict(self.environment)
                del changed[key]
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_environment(changed)

    def test_environment_accepts_only_registered_runtime_provider_tuples(self) -> None:
        omni = self.environment | {
            "WORKSTREAM_PROJECT_AGENT_RUNTIME": "omnicore_agent",
            "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER": "openrouter",
            "WORKSTREAM_PROJECT_AGENT_MODEL_API": "chat_completions",
            "WORKSTREAM_PROJECT_AGENT_RUNTIME_OPTIONS": "{}",
        }
        preflight.validate_environment(omni)
        manager = self.environment | {
            "WORKSTREAM_PROJECT_AGENT_RUNTIME": "manager_authored",
            "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER": "none",
            "WORKSTREAM_PROJECT_AGENT_MODEL_API": "none",
            "WORKSTREAM_PROJECT_AGENT_MODEL": "none",
            "WORKSTREAM_PROJECT_AGENT_RUNTIME_OPTIONS": "{}",
            "WORKSTREAM_MODEL_PROXY_ENABLED": "false",
        }
        for key in preflight.MODEL_PROXY_SECRET_FILE_KEYS:
            manager.pop(key)
        preflight.validate_environment(manager)
        for changed in (
            omni | {"WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER": "openai"},
            omni | {"WORKSTREAM_PROJECT_AGENT_MODEL": "openai/gpt-5.6-terra:online"},
            omni | {"WORKSTREAM_PROJECT_AGENT_MODEL": "OpenRouter/auto"},
            manager | {"WORKSTREAM_PROJECT_AGENT_MODEL": "configured"},
        ):
            with self.assertRaises(preflight.PreflightError):
                preflight.validate_environment(changed)

    def test_manager_authored_render_has_no_provider_credential_surface(self) -> None:
        manager_text = self.environment_path.read_text(encoding="utf-8")
        replacements = {
            "WORKSTREAM_PROJECT_AGENT_RUNTIME=openai_agents_sdk": (
                "WORKSTREAM_PROJECT_AGENT_RUNTIME=manager_authored"
            ),
            "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER=openrouter": (
                "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER=none"
            ),
            "WORKSTREAM_PROJECT_AGENT_MODEL=openai/gpt-5.6-terra": (
                "WORKSTREAM_PROJECT_AGENT_MODEL=none"
            ),
            "WORKSTREAM_PROJECT_AGENT_MODEL_API=chat_completions": (
                "WORKSTREAM_PROJECT_AGENT_MODEL_API=none"
            ),
            "WORKSTREAM_MODEL_PROXY_ENABLED=true": (
                "WORKSTREAM_MODEL_PROXY_ENABLED=false"
            ),
        }
        for old, new in replacements.items():
            manager_text = manager_text.replace(old, new)
        manager_text = (
            "\n".join(
                line
                for line in manager_text.splitlines()
                if not line.startswith("WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE=")
                and not line.startswith(
                    "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE="
                )
            )
            + "\n"
        )
        manager_path = self.root / "manager.env"
        manager_path.write_text(manager_text, encoding="utf-8")
        manager = preflight.parse_environment(manager_path)

        preflight.validate_environment(manager)
        rendered = preflight.render_compose(manager_path, manager)
        preflight.validate_compose(rendered, manager)

        self.assertNotIn("model_proxy_openai_api_key", rendered.get("secrets", {}))
        self.assertNotIn("model_proxy_openrouter_api_key", rendered.get("secrets", {}))
        worker = rendered["services"]["worker"]
        for key in preflight.MODEL_PROXY_SECRET_FILE_KEYS:
            self.assertNotIn(key, worker["environment"])
        self.assertNotIn(
            "model_proxy_openai_api_key",
            {item["source"] for item in worker["secrets"]},
        )
        self.assertNotIn(
            "model_proxy_openrouter_api_key",
            {item["source"] for item in worker["secrets"]},
        )

        selected = manager | {
            "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE": str(self.root / "provider")
        }
        with self.assertRaisesRegex(preflight.PreflightError, "disabled model proxy"):
            preflight.validate_environment(selected)

    def test_manager_setup_can_enable_post_proxy_with_both_provider_credentials(
        self,
    ) -> None:
        manager_text = self.environment_path.read_text(encoding="utf-8")
        for old, new in {
            "WORKSTREAM_PROJECT_AGENT_RUNTIME=openai_agents_sdk": (
                "WORKSTREAM_PROJECT_AGENT_RUNTIME=manager_authored"
            ),
            "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER=openrouter": (
                "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER=none"
            ),
            "WORKSTREAM_PROJECT_AGENT_MODEL=openai/gpt-5.6-terra": (
                "WORKSTREAM_PROJECT_AGENT_MODEL=none"
            ),
            "WORKSTREAM_PROJECT_AGENT_MODEL_API=chat_completions": (
                "WORKSTREAM_PROJECT_AGENT_MODEL_API=none"
            ),
        }.items():
            manager_text = manager_text.replace(old, new)
        manager_text = manager_text.replace(
            "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE=\n",
            "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE="
            "/etc/workstream/secrets/model_proxy_openai_api_key\n",
        )
        manager_path = self.root / "manager-with-post-proxy.env"
        manager_path.write_text(manager_text, encoding="utf-8")
        manager = preflight.parse_environment(manager_path)

        preflight.validate_environment(manager)
        rendered = preflight.render_compose(manager_path, manager)
        preflight.validate_compose(rendered, manager)

        self.assertIn("model-proxy", rendered["services"])
        self.assertEqual(
            {item["source"] for item in rendered["services"]["model-proxy"]["secrets"]},
            {
                "database_url",
                "model_proxy_openai_api_key",
                "model_proxy_openrouter_api_key",
            },
        )
        worker_environment = rendered["services"]["worker"]["environment"]
        for key in preflight.MODEL_PROXY_SECRET_FILE_KEYS:
            self.assertNotIn(key, worker_environment)

    def test_openrouter_only_render_omits_openai_credential(self) -> None:
        self.assertEqual(
            self.environment["WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER"], "openrouter"
        )
        rendered = preflight.render_compose(self.environment_path, self.environment)
        preflight.validate_compose(rendered, self.environment)

        proxy = rendered["services"]["model-proxy"]
        self.assertEqual(
            {
                item["source"]
                for item in proxy["secrets"]
                if item["source"] != "database_url"
            },
            {"model_proxy_openrouter_api_key"},
        )
        self.assertNotIn(
            "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE", proxy["environment"]
        )
        for key in preflight.MODEL_PROXY_SECRET_FILE_KEYS:
            self.assertNotIn(key, rendered["services"]["worker"]["environment"])

    def test_openai_only_render_omits_openrouter_credential(self) -> None:
        environment_text = self.environment_path.read_text(encoding="utf-8")
        environment_text = environment_text.replace(
            "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER=openrouter",
            "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER=openai",
        ).replace(
            "WORKSTREAM_PROJECT_AGENT_MODEL_API=chat_completions",
            "WORKSTREAM_PROJECT_AGENT_MODEL_API=responses",
        )
        environment_text = environment_text.replace(
            "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE=\n",
            "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE="
            "/etc/workstream/secrets/model_proxy_openai_api_key\n",
        ).replace(
            "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE="
            "/etc/workstream/secrets/model_proxy_openrouter_api_key",
            "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE=",
        )
        environment_path = self.root / "openai-only.env"
        environment_path.write_text(environment_text, encoding="utf-8")
        environment = preflight.parse_environment(environment_path)

        preflight.validate_environment(environment)
        rendered = preflight.render_compose(environment_path, environment)
        preflight.validate_compose(rendered, environment)

        proxy = rendered["services"]["model-proxy"]
        self.assertEqual(
            {
                item["source"]
                for item in proxy["secrets"]
                if item["source"] != "database_url"
            },
            {"model_proxy_openai_api_key"},
        )
        self.assertNotIn(
            "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE", proxy["environment"]
        )

    def test_enabled_setup_rejects_missing_selected_provider_credential(self) -> None:
        missing_openrouter = dict(self.environment)
        missing_openrouter["WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE"] = ""
        with self.assertRaisesRegex(preflight.PreflightError, "selected provider"):
            preflight.validate_environment(missing_openrouter)

        manager = missing_openrouter | {
            "WORKSTREAM_PROJECT_AGENT_RUNTIME": "manager_authored",
            "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER": "none",
            "WORKSTREAM_PROJECT_AGENT_MODEL_API": "none",
            "WORKSTREAM_PROJECT_AGENT_MODEL": "none",
        }
        with self.assertRaisesRegex(preflight.PreflightError, "at least one"):
            preflight.validate_environment(manager)

    def test_checker_config_rejects_non_hosted_or_substituted_identity(self) -> None:
        cases = {
            "runc": ("runtime", "runc"),
            "development isolation": ("isolation_mode", "docker-dev"),
            "wrong material root": ("material_root", "/tmp/material"),
            "root sandbox": ("sandbox_uid", 0),
            "empty cache": ("cache", []),
        }
        for label, (key, value) in cases.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(self.checker)
                changed[key] = value
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_checker_config(changed, self.environment)
        changed = copy.deepcopy(self.checker)
        changed["cache"][0]["config_image_id"] = "sha256:" + "A" * 64
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_checker_config(changed, self.environment)

    def test_intake_storage_qualification_must_match_pins_and_have_real_bounds(self):
        preflight.validate_checker_config(self.checker, self.environment)
        for key in (
            "archive_sha256",
            "config_image_id",
            "smol_binary_sha256",
            "guest_sha256",
        ):
            with self.subTest(identity=key):
                changed = copy.deepcopy(self.checker)
                changed["trusted_intake"]["storage_envelope"][key] = (
                    "sha256:" + "f" * 64
                )
                with self.assertRaisesRegex(
                    preflight.PreflightError, "storage qualification"
                ):
                    preflight.validate_checker_config(changed, self.environment)
        for key in (
            "overhead_bytes",
            "maximum_storage_gib",
            "maximum_entries",
            "maximum_path_bytes",
            "maximum_path_depth",
        ):
            for value in (0, True, -1, 2**64):
                with self.subTest(bound=key, value=value):
                    changed = copy.deepcopy(self.checker)
                    changed["trusted_intake"]["storage_envelope"][key] = value
                    with self.assertRaisesRegex(
                        preflight.PreflightError, "storage qualification"
                    ):
                        preflight.validate_checker_config(changed, self.environment)
        changed = copy.deepcopy(self.checker)
        changed["smol"]["maximum_storage_bytes"] = 2 * 1024**3
        with self.assertRaisesRegex(preflight.PreflightError, "storage qualification"):
            preflight.validate_checker_config(changed, self.environment)

    def test_intake_storage_qualification_covers_configured_inspection_limits(self):
        for setting in ("MAXIMUM_ENTRIES", "MAXIMUM_PATH_BYTES", "MAXIMUM_PATH_DEPTH"):
            values = self.environment | {"WORKSTREAM_ARTIFACT_SUBMISSION_ZIP_" + setting: "100001"}
            with self.subTest(setting=setting):
                with self.assertRaisesRegex(preflight.PreflightError, "exceeds storage qualification"):
                    preflight.validate_checker_config(self.checker, values)

    def test_intake_storage_qualification_covers_largest_supported_zip(self):
        changed = copy.deepcopy(self.checker)
        envelope = changed["trusted_intake"]["storage_envelope"]
        envelope["maximum_storage_gib"] = 1
        with self.assertRaisesRegex(preflight.PreflightError, "cannot cover supported ZIPs"):
            preflight.validate_checker_config(changed, self.environment)
        envelope.update(maximum_storage_gib=2, overhead_bytes=1024**3)
        preflight.validate_checker_config(changed, self.environment)
        envelope["overhead_bytes"] += 1
        with self.assertRaisesRegex(preflight.PreflightError, "cannot cover supported ZIPs"):
            preflight.validate_checker_config(changed, self.environment)
        envelope["overhead_bytes"] = 2**64 - 1
        with self.assertRaisesRegex(preflight.PreflightError, "cannot cover supported ZIPs"):
            preflight.validate_checker_config(changed, self.environment)

    def test_custom_deployment_root_preserves_paths_and_refuses_unsafe_custody(
        self,
    ) -> None:
        root = self.root / "owned-data"
        root.mkdir(mode=0o700)
        values = self.environment | {"WORKSTREAM_DEPLOYMENT_ROOT": str(root)}
        paths = preflight.deployment_paths(values)
        config = copy.deepcopy(self.checker)
        config.update(
            socket_path=str(paths.socket),
            material_root=str(paths.scratch),
            model_proxy_socket=str(paths.model_socket),
            model_relay_root=str(paths.model_relays),
        )
        preflight.validate_environment(values)
        preflight.validate_checker_config(config, values)
        rendered = preflight.render_compose(self.environment_path, values)
        preflight.validate_compose(rendered, values)
        for role in ("api", "worker"):
            environment = rendered["services"][role]["environment"]
            self.assertEqual(
                environment["WORKSTREAM_ARTIFACT_SCRATCH_ROOT"], str(paths.scratch)
            )
            self.assertEqual(
                environment["WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET"],
                str(paths.socket),
            )
            self.assertEqual(
                environment["WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET"],
                str(paths.socket),
            )
            mounts = preflight._service_mounts(rendered["services"][role])
            self.assertEqual(mounts[str(paths.scratch)]["source"], str(paths.scratch))
            self.assertTrue(mounts[str(paths.socket_root)]["read_only"])
        proxy_mounts = preflight._service_mounts(rendered["services"]["model-proxy"])
        self.assertEqual(
            proxy_mounts[str(paths.model_root)]["source"], str(paths.model_root)
        )
        preflight._private_metadata(
            root, kind="directory", uid=os.getuid(), gid=os.getgid(), mode=0o700
        )
        with self.assertRaisesRegex(preflight.PreflightError, "owner"):
            preflight._private_metadata(
                root, kind="directory", uid=os.getuid() + 1, gid=os.getgid(), mode=0o700
            )
        alias = self.root / "root-alias"
        alias.symlink_to(root, target_is_directory=True)
        for unsafe in ("/", str(alias), str(root / ".." / "owned-data")):
            with self.subTest(root=unsafe), self.assertRaises(preflight.PreflightError):
                preflight.validate_environment(
                    values | {"WORKSTREAM_DEPLOYMENT_ROOT": unsafe}
                )
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_environment(
                values | {"WORKSTREAM_CHECKER_SERVICE_BINARY": str(root / "service")}
            )
        for field, path in (
            ("guest_binary", root / "guest"),
            ("binary", root / "engine"),
        ):
            changed = copy.deepcopy(config)
            changed["smol"][field] = str(path)
            with self.assertRaisesRegex(preflight.PreflightError, "outside deployment"):
                preflight.validate_checker_config(changed, values)
        credential_values = values | {
            "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE": str(root / "credential")
        }
        with self.assertRaisesRegex(preflight.PreflightError, "outside deployment"):
            preflight.validate_checker_config(config, credential_values)
        self.assertTrue(root.is_dir())

    def test_native_socket_rejects_foreign_identity_permissions_and_links(self) -> None:
        path = self.root / "native.sock"
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(path))
        self.addCleanup(listener.close)
        path.chmod(0o600)
        with self.subTest(path=path):
            preflight._validate_native_socket(path, os.getuid(), os.getgid())
            for uid, gid in (
                (os.getuid() + 1, os.getgid()),
                (os.getuid(), os.getgid() + 1),
            ):
                with self.assertRaisesRegex(preflight.PreflightError, "identity"):
                    preflight._validate_native_socket(path, uid, gid)
            path.chmod(0o660)
            with self.assertRaises(preflight.PreflightError):
                preflight._validate_native_socket(path, os.getuid(), os.getgid())
            path.chmod(0o600)
            alias = self.root / "native-alias"
            os.link(path, alias)
            with self.assertRaises(preflight.PreflightError):
                preflight._validate_native_socket(path, os.getuid(), os.getgid())
            alias.unlink()
            preflight._validate_native_socket(path, os.getuid(), os.getgid())

    def test_trial_manifest_is_paired_shared_and_confined_to_the_proxy(self) -> None:
        manifest = self.root / "trial-authority.json"
        manifest.write_text("fixture pinned authority", encoding="utf-8")
        manifest.chmod(0o400)
        self.environment.update(
            {
                preflight.TRIAL_KEYS[0]: str(manifest),
                preflight.TRIAL_KEYS[1]: "sha256:"
                + hashlib.sha256(manifest.read_bytes()).hexdigest(),
            }
        )
        preflight.validate_environment(self.environment)
        rendered = preflight.render_compose(self.environment_path, self.environment)
        preflight.validate_compose(rendered, self.environment)
        self.assertEqual(
            preflight._service_mounts(rendered["services"]["model-proxy"])[
                str(preflight.TRIAL_MANIFEST_TARGET)
            ]["source"],
            str(manifest),
        )
        for role in ("api", "worker", "beat"):
            self.assertFalse(
                set(preflight.TRIAL_KEYS)
                & set(rendered["services"][role]["environment"])
            )
        for mutation in ("writable", "foreign-source", "worker-selector"):
            changed = copy.deepcopy(rendered)
            mount = next(
                item
                for item in changed["services"]["model-proxy"]["volumes"]
                if item["target"] == str(preflight.TRIAL_MANIFEST_TARGET)
            )
            if mutation == "writable":
                mount["read_only"] = False
            elif mutation == "foreign-source":
                mount["source"] = "/tmp/foreign-manifest"
            else:
                changed["services"]["worker"]["environment"][
                    preflight.TRIAL_KEYS[0]
                ] = str(preflight.TRIAL_MANIFEST_TARGET)
            with self.assertRaises(preflight.PreflightError):
                preflight.validate_compose(changed, self.environment)
        native = copy.deepcopy(self.checker)
        native.update(
            trial_authority_manifest_path=str(manifest),
            trial_authority_manifest_digest=self.environment[preflight.TRIAL_KEYS[1]],
        )
        native["trial_runtime"] = {
            **{
                key: str(self.root / key)
                for key in (
                    "relay_root",
                    "scratch_root",
                    "child_home_root",
                    "offline_cache_root",
                    "trusted_launcher_path",
                    "filesystem_tool_path",
                )
            },
            **{
                key: "sha256:" + "f" * 64
                for key in (
                    "outer_runtime_config_digest",
                    "trusted_launcher_digest",
                    "filesystem_tool_digest",
                )
            },
            "builder_image_id": native["cache"][0]["config_image_id"],
            "deployment_owner": "hosted-native",
            "maximum_candidate_archive_bytes": 1024,
        }
        native["trial_runtime"]["child_home_root"] = self.enterContext(
            tempfile.TemporaryDirectory(prefix="ws", dir="/tmp")
        )
        preflight.validate_checker_config(native, self.environment)
        for root, valid in (
            ("/" + "a" * 17, True),
            ("/" + "é" * 8 + "a", True),
            ("/" + "a" * 18, False),
            ("/" + "é" * 9, False),
        ):
            changed = copy.deepcopy(native)
            changed["trial_runtime"]["child_home_root"] = root
            with self.subTest(child_home_root=root):
                if valid:
                    preflight.validate_checker_config(changed, self.environment)
                else:
                    with self.assertRaisesRegex(preflight.PreflightError, "18-byte"):
                        preflight.validate_checker_config(changed, self.environment)
        substituted = native | {"trial_authority_manifest_digest": "sha256:" + "0" * 64}
        with self.assertRaisesRegex(preflight.PreflightError, "trial authority"):
            preflight.validate_checker_config(substituted, self.environment)
        for key in preflight.TRIAL_KEYS:
            changed = dict(self.environment)
            del changed[key]
            with self.assertRaises(preflight.PreflightError):
                preflight.validate_environment(changed)
        with self.assertRaisesRegex(preflight.PreflightError, "trial authority"):
            preflight.validate_checker_config(self.checker, self.environment)

    def test_smol_home_socket_budget_counts_filesystem_bytes(self):
        for root, valid in (
            ("/" + "a" * 58, True),
            ("/" + "é" * 29, True),
            ("/" + "a" * 59, False),
            ("/" + "é" * 30, False),
        ):
            changed = copy.deepcopy(self.checker)
            changed["smol"]["home"] = root
            with self.subTest(home=root):
                if valid:
                    preflight.validate_checker_config(changed, self.environment)
                else:
                    with self.assertRaisesRegex(preflight.PreflightError, "59-byte"):
                        preflight.validate_checker_config(changed, self.environment)

    def _native_inputs(self):
        config = copy.deepcopy(self.checker)
        values = self.environment | {
            "WORKSTREAM_RUNTIME_UID": str(os.getuid()),
            "WORKSTREAM_RUNTIME_GID": str(os.getgid()),
        }
        smol = config["smol"]
        home = self.root / "native-home"
        home.mkdir(mode=0o700)
        group = self.root / "delegated"
        group.mkdir(mode=0o700)
        (group / "controller").mkdir(mode=0o700)
        for key in ("cgroup.controllers", "cgroup.subtree_control"):
            (group / key).write_text("cpu memory pids", encoding="ascii")
        smol.update(home=str(home), cgroup_root=str(group))
        for key, digest_key in (
            ("binary", "binary_sha256"),
            ("guest_binary", "guest_sha256"),
        ):
            path = self.root / key
            raw = key.encode()
            path.write_bytes(raw)
            path.chmod(0o400)
            smol[key] = str(path)
            smol[digest_key] = "sha256:" + hashlib.sha256(raw).hexdigest()
        for index, entry in enumerate(config["cache"]):
            for key, digest_key in (
                ("archive", "archive_sha256"),
                ("image_config", "config_image_id"),
            ):
                path = self.root / f"cache-{index}-{key}"
                raw = f"static native custody fixture {index} {key}".encode()
                path.write_bytes(raw)
                path.chmod(0o400)
                entry["smol"][key] = str(path)
                target = entry["smol"] if key == "archive" else entry
                target[digest_key] = "sha256:" + hashlib.sha256(raw).hexdigest()
        values[preflight.INTAKE_DIGEST_KEYS[1]] = config["cache"][1]["config_image_id"]
        service = self.root / "service-binary"
        service.write_bytes(b"pinned installed native service")
        service.chmod(0o400)
        values["WORKSTREAM_CHECKER_SERVICE_BINARY"] = str(service)
        values["WORKSTREAM_CHECKER_SERVICE_BINARY_SHA256"] = (
            "sha256:" + hashlib.sha256(service.read_bytes()).hexdigest()
        )
        health = {
            "runtime": "smolvm",
            "isolation_mode": "smol-microvm",
            "operating_system": "linux",
            "architecture": "amd64",
            "sandbox_uid": os.getuid(),
            "sandbox_gid": os.getgid(),
            "cached_platform_manifests": len(config["cache"]),
        }
        return config, values, service, health

    def test_native_asset_refusals_preserve_operator_diagnostics(self) -> None:
        for failure, reason in (
            ("path", "path is not canonical"),
            ("custody", "custody is unsafe"),
            ("deadline", "verification deadline exceeded"),
            ("digest", "digest or identity differs"),
            ("missing", "is unavailable"),
        ):
            with self.subTest(failure=failure):
                asset = self.root / f"asset-{failure}"
                asset.write_bytes(b"pinned asset")
                asset.chmod(0o400)
                expected = "sha256:" + hashlib.sha256(asset.read_bytes()).hexdigest()
                deadline = float("inf")
                if failure == "path":
                    alias = self.root / "asset-alias"
                    alias.symlink_to(asset)
                    asset = alias
                elif failure == "custody":
                    asset.chmod(0o620)
                elif failure == "deadline":
                    deadline = 0
                elif failure == "digest":
                    expected = "sha256:" + "0" * 64
                else:
                    asset.unlink()
                with self.assertRaisesRegex(
                    preflight.PreflightError, f"^native Smol asset {reason}$"
                ):
                    preflight._verify_smol_asset(asset, expected, os.getuid(), deadline)

    def test_native_readiness_binds_static_assets_delegation_and_typed_health(
        self,
    ) -> None:
        config, values, service, health = self._native_inputs()
        with (
            patch.object(preflight, "_run_json", return_value=health) as run,
        ):
            preflight.validate_smol_runtime(config, values)
        command = run.call_args.args[0]
        self.assertIn("configured_external_checker_execution(s).health()", command[-1])
        self.assertIn("--network", command)
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertIn("readonly", command[command.index("--mount") + 1])
        self.assertNotIn("--env", command)
        self.assertNotIn("--env-file", command)
        self.assertNotIn("/var/run/docker.sock", " ".join(command))
        for changed_health in (
            health | {"runtime": "runsc"},
            health | {"sandbox_uid": os.getuid() + 1},
            health | {"cached_platform_manifests": 1},
        ):
            with (
                patch.object(preflight, "_run_json", return_value=changed_health),
            ):
                with self.assertRaisesRegex(
                    preflight.PreflightError, "readiness identity"
                ):
                    preflight.validate_smol_runtime(config, values)
        for mutate in ("cache", "binary", "delegation"):
            changed = copy.deepcopy(config)
            if mutate == "cache":
                changed["cache"][0]["smol"]["archive_sha256"] = "sha256:" + "f" * 64
            elif mutate == "binary":
                changed["smol"]["guest_sha256"] = "sha256:" + "f" * 64
            else:
                Path(changed["smol"]["cgroup_root"]).joinpath(
                    "cgroup.subtree_control"
                ).write_text("cpu memory", encoding="ascii")
            with (
                patch.object(preflight, "_run_json") as run,
            ):
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_smol_runtime(changed, values)
                run.assert_not_called()

    def test_cold_start_prerequisites_never_release_application_or_require_node(
        self,
    ) -> None:
        for arguments in (("migrate",), ("up", "-d", "model-proxy")):
            with (
                self.subTest(arguments=arguments),
                patch.object(compose, "validate_private_host_inputs") as private,
                patch.object(compose, "validate_smol_runtime") as native,
                patch.object(compose, "validate_trusted_intake") as intake,
                patch.object(compose, "run_compose", return_value=0) as run,
            ):
                self.assertEqual(self._compose_main(*arguments), (0, ""))
                private.assert_called_once_with(self.environment, require_node=False)
                native.assert_not_called()
                intake.assert_not_called()
                run.assert_called_once_with(
                    self.environment_path, self.environment, list(arguments)
                )
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(preflight.subprocess, "run", return_value=completed) as run:
            self.assertEqual(
                preflight.run_compose(
                    self.environment_path, self.environment, ["migrate"]
                ),
                0,
            )
        self.assertEqual(
            run.call_args.args[0][-9:],
            [
                "run",
                "--rm",
                "--no-deps",
                "api",
                "python",
                "-m",
                "alembic",
                "upgrade",
                "head",
            ],
        )

    def _points_inputs(self):
        token = self.root / "finance-token"
        token.write_text("private-finance-bearer", encoding="ascii")
        token.chmod(0o400)
        values = self.environment | {
            "WORKSTREAM_RUNTIME_UID": str(os.getuid()),
            "WORKSTREAM_RUNTIME_GID": str(os.getgid()),
        }
        arguments = [
            "provision-project-points",
            "--project-id", "00000000-0000-4000-8000-000000000001",
            "--adapter-actor-id", "00000000-0000-4000-8000-000000000002",
            "--unit-code", "FLOW", "--route-key", "flow_points.recording",
            "--finance-token-file", str(token),
        ]
        return values, arguments, token

    def test_points_operator_uses_only_fixed_image_owned_command_and_private_mount(self):
        values, arguments, token = self._points_inputs()
        with patch.object(preflight.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(preflight.run_compose(self.environment_path, values, arguments), 0)
        command = run.call_args.args[0]
        name = command[command.index("--name") + 1]
        self.assertRegex(name, r"^workstream-points-[0-9a-f]{32}$")
        self.assertEqual(command[command.index("run"):], [
            "run", "--rm", "--no-deps", "-T", "--pull", "never", "--name", name,
            "--volume", f"{token}:/run/secrets/points_finance_token:ro", "api",
            "/usr/bin/timeout", "--signal=TERM", "--kill-after=5s", "120s",
            "python", "scripts/provision_project_points.py",
            *arguments[1:9], "--finance-token-file", "/run/secrets/points_finance_token",
        ])
        self.assertEqual(run.call_args.kwargs["env"], preflight.compose_environment(values))
        self.assertEqual(run.call_args.kwargs["timeout"], 150)
        self.assertNotIn("private-finance-bearer", repr(run.call_args))
        self.assertNotIn("--entrypoint", command)
        self.assertNotIn("--service-ports", command)

    def test_points_operator_rejects_extra_or_malformed_selectors_before_launch(self):
        values, original, _ = self._points_inputs()
        cases = [original[:-2], original + ["--entrypoint", "sh"], ["run", "api", "sh"]]
        for index, value in ((1, "--entrypoint"), (3, "--project-id"), (2, "invalid"),
                             (4, "invalid"), (6, "--help"), (8, "../route"), (8, "--help")):
            changed = list(original)
            changed[index] = value
            cases.append(changed)
        for arguments in cases:
            with self.subTest(arguments=arguments), patch.object(preflight.subprocess, "run") as run:
                with self.assertRaises(preflight.PreflightError):
                    preflight.run_compose(self.environment_path, values, arguments)
                run.assert_not_called()

    def test_points_operator_rejects_unsafe_token_mounts(self):
        for unsafe in ("symlink", "parent-link", "hardlink", "public", "directory",
                       "empty", "oversized", "owner", "group", "delimiter"):
            with self.subTest(unsafe=unsafe):
                values, arguments, token = self._points_inputs()
                if unsafe == "symlink":
                    token = self.root / "token-link"
                    token.symlink_to(arguments[-1])
                elif unsafe == "parent-link":
                    parent = self.root / "parent-link"
                    parent.symlink_to(self.root, target_is_directory=True)
                    token = parent / token.name
                elif unsafe == "hardlink":
                    os.link(token, self.root / "hardlink")
                elif unsafe == "public":
                    token.chmod(0o644)
                elif unsafe == "directory":
                    token = self.root
                elif unsafe in {"empty", "oversized"}:
                    token.chmod(0o600)
                    token.write_text("" if unsafe == "empty" else "x" * 16_385)
                elif unsafe in {"owner", "group"}:
                    key = "WORKSTREAM_RUNTIME_UID" if unsafe == "owner" else "WORKSTREAM_RUNTIME_GID"
                    values[key] = str(int(values[key]) + 1)
                else:
                    token = self.root / "token:mount"
                    token.write_text("private-finance-bearer")
                    token.chmod(0o400)
                arguments[-1] = str(token)
                with patch.object(preflight.subprocess, "run") as run:
                    with self.assertRaises(preflight.PreflightError):
                        preflight.run_compose(self.environment_path, values, arguments)
                    run.assert_not_called()
                # Restore the shared token before the next independent subcase.
                (self.root / "finance-token").chmod(0o600)
                if unsafe == "hardlink":
                    (self.root / "hardlink").unlink()

    def test_points_operator_timeout_and_start_failure_clean_only_owned_container(self):
        values, arguments, _ = self._points_inputs()
        for error in (subprocess.TimeoutExpired([], 150), OSError("private-provider-detail")):
            for cleanup_ok in (True, False):
                errors = io.StringIO()
                cleanup = subprocess.CompletedProcess([], 0 if cleanup_ok else 1)
                with (
                    self.subTest(error=type(error), cleanup_ok=cleanup_ok),
                    patch.object(preflight.subprocess, "run", side_effect=[error, cleanup]) as run,
                    redirect_stderr(errors),
                ):
                    with self.assertRaisesRegex(preflight.PreflightError, "no automatic retry"):
                        preflight.run_compose(self.environment_path, values, arguments)
                launch, removal = run.call_args_list
                name = launch.args[0][launch.args[0].index("--name") + 1]
                self.assertEqual(removal.args[0], ["docker", "rm", "--force", name])
                self.assertEqual(removal.kwargs["timeout"], 10)
                self.assertEqual(removal.kwargs["env"], preflight.compose_environment(values))
                self.assertNotIn("private-provider-detail", errors.getvalue())
                self.assertEqual(bool(errors.getvalue()), not cleanup_ok)
                if not cleanup_ok:
                    self.assertIn(name, errors.getvalue())

    def test_points_operator_preflight_requires_static_inputs_without_checker_execution(self):
        _, arguments, _ = self._points_inputs()
        with (
            patch.object(compose, "validate_private_host_inputs") as private,
            patch.object(compose, "validate_smol_runtime") as native,
            patch.object(compose, "validate_trusted_intake") as intake,
            patch.object(compose, "run_compose", return_value=0) as run,
        ):
            self.assertEqual(self._compose_main(*arguments), (0, ""))
            private.assert_called_once_with(self.environment, require_node=False)
            native.assert_not_called()
            intake.assert_not_called()
            run.assert_called_once_with(self.environment_path, self.environment, arguments)

    def test_checker_model_paths_require_enabled_exact_proxy_topology(self) -> None:
        for key in ("model_proxy_socket", "model_relay_root"):
            for replacement in (None, "/tmp/substituted"):
                with self.subTest(key=key, replacement=replacement):
                    changed = copy.deepcopy(self.checker)
                    changed[key] = replacement
                    with self.assertRaises(preflight.PreflightError):
                        preflight.validate_checker_config(changed, self.environment)
        disabled = self.environment | {"WORKSTREAM_MODEL_PROXY_ENABLED": "false"}
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_checker_config(self.checker, disabled)
        ordinary = copy.deepcopy(self.checker)
        del ordinary["model_proxy_socket"]
        del ordinary["model_relay_root"]
        preflight.validate_checker_config(ordinary, disabled)

    def test_rendered_topology_rejects_a_second_checker_controller(self) -> None:
        rendered = preflight.render_compose(self.environment_path, self.environment)
        changed = copy.deepcopy(rendered)
        changed["services"]["checker-service"] = copy.deepcopy(
            rendered["services"]["worker"]
        )
        with self.assertRaisesRegex(preflight.PreflightError, "bounded topology"):
            preflight.validate_compose(changed, self.environment)

    def test_rendered_topology_rejects_privilege_and_path_drift(self) -> None:
        rendered = preflight.render_compose(self.environment_path, self.environment)
        cases = []
        mutable = copy.deepcopy(rendered)
        mutable["services"]["worker"]["image"] = (
            "registry.example/workstream/backend:latest"
        )
        cases.append(("mutable worker image", mutable))
        different_parser_image = copy.deepcopy(rendered)
        different_parser_image["services"]["guide-document-parser"]["image"] = (
            "registry.example/workstream/backend@sha256:" + "9" * 64
        )
        cases.append(("different guide parser image", different_parser_image))
        for role in ("api", "worker"):
            writable_owner = copy.deepcopy(rendered)
            for mount in writable_owner["services"][role]["volumes"]:
                if mount["target"] == str(
                    preflight.deployment_paths(self.environment).socket_root
                ):
                    mount["read_only"] = False
            cases.append((f"{role} writable checker custody", writable_owner))
        expanded_worker = copy.deepcopy(rendered)
        expanded_worker["services"]["worker"]["environment"]["UNREVIEWED"] = "true"
        cases.append(("worker environment drift", expanded_worker))
        unknown_role = copy.deepcopy(rendered)
        unknown_role["services"]["worker"]["environment"]["WORKSTREAM_RELEASE_ROLE"] = (
            "setup"
        )
        cases.append(("unknown backend role", unknown_role))
        missing_role_secret = copy.deepcopy(rendered)
        del missing_role_secret["services"]["api"]["environment"][
            "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE"
        ]
        cases.append(("missing role secret selector", missing_role_secret))
        unrelated_role_secret = copy.deepcopy(rendered)
        unrelated_role_secret["services"]["beat"]["environment"][
            "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE"
        ] = "/run/secrets/model_proxy_openai_api_key"
        cases.append(("unrelated role secret selector", unrelated_role_secret))
        unrelated_role_mount = copy.deepcopy(rendered)
        unrelated_role_mount["services"]["beat"]["secrets"].append(
            copy.deepcopy(rendered["services"]["worker"]["secrets"][-1])
        )
        cases.append(("unrelated role secret mount", unrelated_role_mount))
        writable_identity = copy.deepcopy(rendered)
        for mount in writable_identity["services"]["worker"]["volumes"]:
            if mount["target"] == str(preflight.ROLES_ANYWHERE_PRIVATE_KEY_TARGET):
                mount["read_only"] = False
        cases.append(("writable runtime identity", writable_identity))
        beat_identity = copy.deepcopy(rendered)
        beat_identity["services"]["beat"]["volumes"] = [
            copy.deepcopy(rendered["services"]["api"]["volumes"][-1])
        ]
        cases.append(("runtime identity exposed to Beat", beat_identity))
        relocated_beat_identity = copy.deepcopy(rendered)
        relocated_mount = copy.deepcopy(rendered["services"]["api"]["volumes"][-1])
        relocated_mount["target"] = "/run/unrelated/private.pem"
        relocated_beat_identity["services"]["beat"]["volumes"] = [relocated_mount]
        cases.append(("runtime identity relocated into Beat", relocated_beat_identity))
        arbitrary_beat_volume = copy.deepcopy(rendered)
        unrelated_file = self.root / "unrelated-volume"
        unrelated_file.write_text("unrelated", encoding="utf-8")
        arbitrary_beat_volume["services"]["beat"]["volumes"] = [
            {
                "type": "bind",
                "source": str(unrelated_file),
                "target": "/run/unrelated/value",
                "read_only": True,
            }
        ]
        cases.append(("arbitrary Beat volume", arbitrary_beat_volume))
        hardlink_beat_identity = copy.deepcopy(rendered)
        private_key_alias = self.root / "runtime-private-key-alias.pem"
        os.link(self.runtime_private_key, private_key_alias)
        hardlink_beat_identity["services"]["beat"]["volumes"] = [
            {
                "type": "bind",
                "source": str(private_key_alias),
                "target": "/run/unrelated/key.pem",
                "read_only": True,
            }
        ]
        cases.append(
            ("hardlink runtime identity exposed to Beat", hardlink_beat_identity)
        )
        parser_secret = copy.deepcopy(rendered)
        parser_secret["services"]["guide-document-parser"]["secrets"] = [
            copy.deepcopy(rendered["services"]["worker"]["secrets"][-1])
        ]
        cases.append(("provider secret exposed to parser", parser_secret))
        parser_network = copy.deepcopy(rendered)
        parser_network["services"]["guide-document-parser"]["network_mode"] = "default"
        cases.append(("networked guide parser", parser_network))
        parser_identity = copy.deepcopy(rendered)
        parser_identity["services"]["guide-document-parser"]["user"] = "10001:10001"
        cases.append(("guide parser shares worker identity", parser_identity))
        parser_resources = copy.deepcopy(rendered)
        parser_resources["services"]["guide-document-parser"]["pids_limit"] = 65
        cases.append(("guide parser PID limit drift", parser_resources))
        privileged_parser = copy.deepcopy(rendered)
        privileged_parser["services"]["guide-document-parser"]["privileged"] = True
        cases.append(("privileged guide parser", privileged_parser))
        missing_parser_capability = copy.deepcopy(rendered)
        missing_parser_capability["services"]["guide-document-parser"]["cap_add"] = [
            "KILL",
            "SETGID",
        ]
        cases.append(
            ("guide parser missing required capability", missing_parser_capability)
        )
        extra_parser_capability = copy.deepcopy(rendered)
        extra_parser_capability["services"]["guide-document-parser"]["cap_add"].append(
            "SYS_ADMIN"
        )
        cases.append(("guide parser added capability", extra_parser_capability))
        missing_parser_cap_drop = copy.deepcopy(rendered)
        missing_parser_cap_drop["services"]["guide-document-parser"]["cap_drop"] = []
        cases.append(
            ("guide parser did not drop default capabilities", missing_parser_cap_drop)
        )
        parser_device = copy.deepcopy(rendered)
        parser_device["services"]["guide-document-parser"]["devices"] = [
            "/dev/null:/dev/foreign"
        ]
        cases.append(("guide parser device", parser_device))
        parser_entrypoint = copy.deepcopy(rendered)
        parser_entrypoint["services"]["guide-document-parser"]["entrypoint"] = [
            "python"
        ]
        cases.append(("guide parser bypasses release entrypoint", parser_entrypoint))
        worker_entrypoint = copy.deepcopy(rendered)
        worker_entrypoint["services"]["worker"]["entrypoint"] = ["python"]
        cases.append(("worker bypasses secret loader", worker_entrypoint))
        parser_credential_environment = copy.deepcopy(rendered)
        parser_credential_environment["services"]["guide-document-parser"][
            "environment"
        ]["OPENROUTER_API_KEY"] = "private"
        cases.append(
            (
                "provider credential interpolated into parser",
                parser_credential_environment,
            )
        )
        missing_parser_dependency = copy.deepcopy(rendered)
        del missing_parser_dependency["services"]["worker"]["depends_on"][
            "guide-document-parser"
        ]
        cases.append(("worker does not wait for parser", missing_parser_dependency))
        proof_runtime_drift = copy.deepcopy(rendered)
        proof_runtime_drift["services"]["aws-proof-coordinate"]["environment"][
            "WORKSTREAM_PROJECT_AGENT_MODEL"
        ] = "different-model"
        cases.append(("proof project agent snapshot drift", proof_runtime_drift))
        proof_parser_socket = copy.deepcopy(rendered)
        proof_parser_socket["services"]["aws-proof-coordinate"]["environment"][
            "WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET"
        ] = str(preflight.deployment_paths(self.environment).guide_socket)
        cases.append(("guide parser socket exposed to proof", proof_parser_socket))
        proof_provider_selector = copy.deepcopy(rendered)
        proof_provider_selector["services"]["aws-proof-coordinate"]["environment"][
            "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE"
        ] = "/run/secrets/model_proxy_openai_api_key"
        cases.append(("provider selector exposed to proof", proof_provider_selector))
        worker_provider_value = copy.deepcopy(rendered)
        worker_provider_value["services"]["worker"]["environment"][
            "OPENROUTER_API_KEY"
        ] = "private"
        cases.append(("provider value interpolated into worker", worker_provider_value))
        api_parser_mount = copy.deepcopy(rendered)
        api_parser_mount["services"]["api"]["volumes"].append(
            copy.deepcopy(rendered["services"]["worker"]["volumes"][2])
        )
        cases.append(("guide parser socket exposed to API", api_parser_mount))
        for label, changed in cases:
            with self.subTest(label=label), self.assertRaises(preflight.PreflightError):
                preflight.validate_compose(changed, self.environment)

    def test_private_metadata_rejects_empty_broad_and_linked_files(self) -> None:
        private_file = self.root / "secret"
        private_file.write_text("value", encoding="utf-8")
        private_file.chmod(0o400)
        preflight._private_metadata(
            private_file,
            kind="file",
            uid=os.getuid(),
            gid=os.getgid(),
            mode=0o400,
        )
        with self.assertRaises(preflight.PreflightError):
            preflight._private_metadata(
                private_file,
                kind="file",
                uid=os.getuid() + 1,
                gid=os.getgid(),
                mode=0o400,
            )
        private_file.chmod(0o440)
        with self.assertRaises(preflight.PreflightError):
            preflight._private_metadata(
                private_file,
                kind="file",
                uid=os.getuid(),
                gid=os.getgid(),
                mode=0o400,
            )
        private_file.chmod(0o600)
        private_file.write_text("", encoding="utf-8")
        private_file.chmod(0o400)
        with self.assertRaises(preflight.PreflightError):
            preflight._private_metadata(
                private_file,
                kind="file",
                uid=os.getuid(),
                gid=os.getgid(),
                mode=0o400,
            )
        target = self.root / "target"
        target.write_text("value", encoding="utf-8")
        link = self.root / "link"
        link.symlink_to(target)
        with self.assertRaises(preflight.PreflightError):
            preflight._private_metadata(
                link,
                kind="file",
                uid=os.getuid(),
                gid=os.getgid(),
                mode=0o400,
            )

    def test_private_host_inputs_check_socket_identity_without_reading_secrets(
        self,
    ) -> None:
        scratch = self.root / "scratch"
        socket_root = self.root / "checker-runtime"
        model_socket_root = self.root / "model-runtime"
        model_relay_root = self.root / "model-relays"
        guide_socket_root = self.root / "guide-runtime"
        intake_root = self.root / "checker-runtime"
        intake_root.mkdir(mode=0o700)
        intake_path = intake_root / "checker.sock"
        intake_listener = socket.socket(socket.AF_UNIX)
        intake_listener.bind(str(intake_path))
        intake_path.chmod(0o600)
        self.addCleanup(intake_listener.close)
        scratch.mkdir(mode=0o700)
        socket_root.mkdir(mode=0o700, exist_ok=True)
        model_socket_root.mkdir(mode=0o700, exist_ok=True)
        model_relay_root.mkdir(mode=0o700)
        guide_socket_root.mkdir(mode=0o750)
        host_uid = os.getuid()
        host_gid = os.getgid()
        environment = dict(self.environment)
        environment["WORKSTREAM_GITHUB_APP_ID"] = "123"
        environment["WORKSTREAM_DEPLOYMENT_ROOT"] = str(self.root)
        environment["WORKSTREAM_RUNTIME_UID"] = str(host_uid)
        environment["WORKSTREAM_RUNTIME_GID"] = str(host_gid)
        checker = self.root / "private-checker.json"
        checker.write_text("{}", encoding="utf-8")
        checker.chmod(0o400)
        secret_paths = []
        environment["WORKSTREAM_CHECKER_CONFIG_FILE"] = str(checker)
        for index, key in enumerate(preflight.SECRET_FILE_KEYS):
            secret = self.root / f"secret-{index}"
            secret.write_text(f"private-{index}", encoding="utf-8")
            secret.chmod(0o400)
            environment[key] = str(secret)
            secret_paths.append(secret)
        docker_socket = self.root / "docker.sock"
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(docker_socket))
        try:
            with (
                patch.object(preflight, "GUIDE_PARSER_UID", host_uid),
                patch.object(preflight, "GUIDE_PARSER_GID", host_gid),
                patch.object(preflight, "DOCKER_SOCKET", docker_socket),
            ):
                preflight.validate_private_host_inputs(environment)
                model_relay_root.chmod(0o755)
                with self.assertRaisesRegex(preflight.PreflightError, "wrong mode"):
                    preflight.validate_private_host_inputs(environment)
                model_relay_root.chmod(0o700)
                guide_listener = socket.socket(socket.AF_UNIX)
                guide_listener.bind(str(guide_socket_root / "guide.sock"))
                (guide_socket_root / "guide.sock").chmod(0o660)
                try:
                    preflight.validate_private_host_inputs(environment)
                    guide_socket_alias = self.root / "guide-socket-alias"
                    os.link(guide_socket_root / "guide.sock", guide_socket_alias)
                    try:
                        with self.assertRaisesRegex(
                            preflight.PreflightError,
                            "unsafe retained state",
                        ):
                            preflight.validate_private_host_inputs(environment)
                    finally:
                        guide_socket_alias.unlink()
                finally:
                    guide_listener.close()
                    (guide_socket_root / "guide.sock").unlink()
                (guide_socket_root / "guide.sock").write_text(
                    "foreign", encoding="utf-8"
                )
                with self.assertRaisesRegex(
                    preflight.PreflightError, "unsafe retained state"
                ):
                    preflight.validate_private_host_inputs(environment)
                (guide_socket_root / "guide.sock").unlink()
                guide_socket_root.chmod(0o700)
                with self.assertRaisesRegex(preflight.PreflightError, "wrong mode"):
                    preflight.validate_private_host_inputs(environment)
                guide_socket_root.chmod(0o750)
            scratch_secret = scratch / "project-agent-secret"
            scratch_secret.write_text("private", encoding="utf-8")
            scratch_secret.chmod(0o400)
            scratch_alias = self.root / "scratch-alias"
            scratch_alias.symlink_to(scratch, target_is_directory=True)
            environment["WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE"] = str(
                scratch_alias / scratch_secret.name
            )
            with (
                patch.object(preflight, "GUIDE_PARSER_UID", host_uid),
                patch.object(preflight, "GUIDE_PARSER_GID", host_gid),
                patch.object(preflight, "DOCKER_SOCKET", docker_socket),
                self.assertRaisesRegex(
                    preflight.PreflightError, "outside shared roots"
                ),
            ):
                preflight.validate_private_host_inputs(environment)
            environment["WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE"] = str(
                secret_paths[-1]
            )
            socket_identity = socket_root / "negative-key.pem"
            socket_identity.write_text("private", encoding="utf-8")
            socket_identity.chmod(0o400)
            negative_key = (
                "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_NEGATIVE_PRIVATE_KEY_HOST_FILE"
            )
            original_negative_key = environment[negative_key]
            environment[negative_key] = str(socket_identity)
            with (
                patch.object(preflight, "GUIDE_PARSER_UID", host_uid),
                patch.object(preflight, "GUIDE_PARSER_GID", host_gid),
                patch.object(preflight, "DOCKER_SOCKET", docker_socket),
                self.assertRaisesRegex(
                    preflight.PreflightError, "outside shared roots"
                ),
            ):
                preflight.validate_private_host_inputs(environment)
            environment[negative_key] = original_negative_key
            runtime_key = (
                "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_RUNTIME_PRIVATE_KEY_HOST_FILE"
            )
            original_runtime_key = environment[runtime_key]
            secret_alias = self.root / "project-agent-secret-runtime-key-alias"
            os.link(secret_paths[-1], secret_alias)
            environment[runtime_key] = str(secret_alias)
            with (
                patch.object(preflight, "GUIDE_PARSER_UID", host_uid),
                patch.object(preflight, "GUIDE_PARSER_GID", host_gid),
                patch.object(preflight, "DOCKER_SOCKET", docker_socket),
                self.assertRaisesRegex(preflight.PreflightError, "distinct files"),
            ):
                preflight.validate_private_host_inputs(environment)
            environment[runtime_key] = original_runtime_key
            checker_alias = self.root / "checker-negative-key-alias"
            os.link(checker, checker_alias)
            environment[negative_key] = str(checker_alias)
            with (
                patch.object(preflight, "GUIDE_PARSER_UID", host_uid),
                patch.object(preflight, "GUIDE_PARSER_GID", host_gid),
                patch.object(preflight, "DOCKER_SOCKET", docker_socket),
                self.assertRaisesRegex(preflight.PreflightError, "distinct files"),
            ):
                preflight.validate_private_host_inputs(environment)
            environment[negative_key] = original_negative_key
            same_identity = self.root / "same-identity"
            same_identity.write_text("private", encoding="utf-8")
            same_identity.chmod(0o400)
            environment.update(
                {
                    key: str(same_identity)
                    for key in preflight.ROLES_ANYWHERE_HOST_FILE_KEYS
                }
            )
            with (
                patch.object(preflight, "GUIDE_PARSER_UID", host_uid),
                patch.object(preflight, "GUIDE_PARSER_GID", host_gid),
                patch.object(preflight, "DOCKER_SOCKET", docker_socket),
                self.assertRaisesRegex(preflight.PreflightError, "distinct files"),
            ):
                preflight.validate_private_host_inputs(environment)
        finally:
            listener.close()

    def test_trusted_intake_requires_pinned_settings_and_readonly_mounts(self) -> None:
        for key in preflight.INTAKE_DIGEST_KEYS:
            for value in (None, "latest"):
                changed = dict(self.environment)
                if value is None:
                    del changed[key]
                else:
                    changed[key] = value
                with (
                    self.subTest(key=key, value=value),
                    self.assertRaises(preflight.PreflightError),
                ):
                    preflight.validate_environment(changed)
        rendered = preflight.render_compose(self.environment_path, self.environment)
        for role in ("api", "worker"):
            changed = copy.deepcopy(rendered)
            for mount in changed["services"][role]["volumes"]:
                if mount["target"] == str(
                    preflight.deployment_paths(self.environment).socket_root
                ):
                    mount["read_only"] = False
            with self.subTest(role=role), self.assertRaises(preflight.PreflightError):
                preflight.validate_compose(changed, self.environment)

    def test_trusted_intake_health_uses_typed_factory_without_credentials(self) -> None:
        health = {
            "runtime": "smolvm",
            "isolation_mode": "smol-microvm",
            "image_digest": self.environment[preflight.INTAKE_DIGEST_KEYS[0]],
            "config_digest": self.environment[preflight.INTAKE_DIGEST_KEYS[1]],
        }
        with patch.object(preflight, "_run_json", return_value=health) as run:
            preflight.validate_trusted_intake(self.environment)
        command = run.call_args.args[0]
        self.assertIn("--pull=never", command)
        self.assertIn("trusted_submission_intake(s).health()", command[-1])
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertEqual(command.count("--mount"), 1)
        self.assertIn("readonly", command[command.index("--mount") + 1])
        self.assertNotIn("--env-file", command)
        self.assertNotIn("--env", command)
        for mutation in ({"runtime": "runsc"}, {"image_digest": "sha256:" + "f" * 64}):
            with patch.object(preflight, "_run_json", return_value=health | mutation):
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_trusted_intake(self.environment)


class ReleaseSecretLoaderTests(unittest.TestCase):
    FILE_TO_SECRET = {
        "WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE": "WORKSTREAM_GITHUB_APP_PRIVATE_KEY",
        "WORKSTREAM_DATABASE_URL_FILE": "WORKSTREAM_DATABASE_URL",
        "WORKSTREAM_CELERY_BROKER_URL_FILE": "WORKSTREAM_CELERY_BROKER_URL",
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE": (
            "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET"
        ),
        "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE": (
            "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET"
        ),
        "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE": "OPENAI_API_KEY",
        "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE": "OPENROUTER_API_KEY",
    }
    ROLE_FILES = {
        "api": (
            "WORKSTREAM_DATABASE_URL_FILE",
            "WORKSTREAM_CELERY_BROKER_URL_FILE",
            "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE",
            "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE",
        ),
        "worker": (
            "WORKSTREAM_DATABASE_URL_FILE",
            "WORKSTREAM_CELERY_BROKER_URL_FILE",
        ),
        "model-proxy": ("WORKSTREAM_DATABASE_URL_FILE",),
        "beat": (
            "WORKSTREAM_DATABASE_URL_FILE",
            "WORKSTREAM_CELERY_BROKER_URL_FILE",
        ),
        "proof": ("WORKSTREAM_DATABASE_URL_FILE",),
        "parser": (),
    }

    def _run_loader(
        self,
        root: Path,
        *,
        role: str = "worker",
        content: str = "safe-value",
        override: tuple[str, Path] | None = None,
        unset_selector: str | None = None,
        provider: str = "openrouter",
        runtime: str = "openai_agents_sdk",
        sdk_environment: str = "agents",
        include_runtime_configuration: bool = True,
        provider_files: tuple[str, ...] = ("openrouter",),
        github: bool = False,
        github_settings: dict[str, str] | None = None,
        check_github_settings: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        for variable in preflight.GITHUB_APP_KEYS:
            environment.pop(variable, None)
        file_names = {
            "WORKSTREAM_DATABASE_URL_FILE": "database",
            "WORKSTREAM_CELERY_BROKER_URL_FILE": "broker",
            "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE": "rate",
            "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE": "cursor",
            "WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE": "model-proxy-openai",
            "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE": (
                "model-proxy-openrouter"
            ),
        }
        configured_provider_variables = {
            f"WORKSTREAM_MODEL_PROXY_{name.upper()}_API_KEY_FILE"
            for name in provider_files
        }
        if github:
            file_names["WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE"] = "github-private-key"
            environment["WORKSTREAM_GITHUB_APP_ID"] = "123"
            environment["WORKSTREAM_GITHUB_APP_INSTALLATION_ID"] = "456"
        for variable, name in file_names.items():
            if (
                variable in preflight.MODEL_PROXY_SECRET_FILE_KEYS
                and variable not in configured_provider_variables
            ):
                environment.pop(variable, None)
                continue
            path = root / name
            if path.exists():
                path.chmod(0o600)
            path.write_text(content, encoding="utf-8")
            path.chmod(0o400)
            environment[variable] = str(path)
        for secret_name in {
            *self.FILE_TO_SECRET.values(),
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "WORKSTREAM_PROJECT_AGENT_API_KEY",
            "WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID",
            "WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY",
            "WORKSTREAM_ARTIFACT_S3_SESSION_TOKEN",
            "WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET",
            "WORKSTREAM_DEV_AUTH_TOKEN",
            "WORKSTREAM_TOKEN_INTROSPECTION_CLIENT_SECRET",
        }:
            environment[secret_name] = "ambient-value-must-not-survive"
        if override is not None:
            environment[override[0]] = str(override[1])
        if unset_selector is not None:
            environment.pop(unset_selector, None)
        if github_settings:
            environment.update(github_settings)
        environment["WORKSTREAM_RELEASE_ROLE"] = role
        runtime_variables = {
            "WORKSTREAM_PROJECT_AGENT_RUNTIME": runtime,
            "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER": provider,
            "WORKSTREAM_PROJECT_AGENT_MODEL_API": (
                "none" if runtime == "manager_authored" else "chat_completions"
            ),
            "WORKSTREAM_PROJECT_AGENT_MODEL": (
                "none" if runtime == "manager_authored" else "openai/gpt-5.6-terra"
            ),
        }
        for variable, value in runtime_variables.items():
            if include_runtime_configuration:
                environment[variable] = value
            else:
                environment.pop(variable, None)
        environment["WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_CERTIFICATE_FILE"] = (
            "/run/private/certificate.pem"
        )
        environment["WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_PRIVATE_KEY_FILE"] = (
            "/run/private/private-key.pem"
        )
        environment["EXPECT_PARSER_SELECTOR_SCRUB"] = "1" if role == "parser" else "0"
        role_files = self.ROLE_FILES.get(role, ())
        if role == "model-proxy":
            role_files = (*role_files, *sorted(configured_provider_variables))
        if github and role == "worker":
            role_files = (*role_files, "WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE")
        expected = {self.FILE_TO_SECRET[key] for key in role_files}
        environment["EXPECTED_SECRET_NAMES"] = ",".join(sorted(expected))
        environment["EXPECTED_SECRET_SHA256"] = hashlib.sha256(
            content.encode()
        ).hexdigest()
        program = (
            "import hashlib,os;"
            "expected=set(filter(None,os.environ['EXPECTED_SECRET_NAMES'].split(',')));"
            "all_names={'WORKSTREAM_DATABASE_URL','WORKSTREAM_CELERY_BROKER_URL',"
            "'WORKSTREAM_API_RATE_LIMIT_KEY_SECRET',"
            "'WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET','OPENAI_API_KEY',"
            "'OPENROUTER_API_KEY','WORKSTREAM_PROJECT_AGENT_API_KEY',"
            "'WORKSTREAM_GITHUB_APP_PRIVATE_KEY',"
            "'WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID',"
            "'WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY',"
            "'WORKSTREAM_ARTIFACT_S3_SESSION_TOKEN',"
            "'WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET','WORKSTREAM_DEV_AUTH_TOKEN',"
            "'WORKSTREAM_TOKEN_INTROSPECTION_CLIENT_SECRET'};"
            "assert all((hashlib.sha256(os.environ[name].encode()).hexdigest()"
            "==os.environ['EXPECTED_SECRET_SHA256']) for name in expected);"
            "assert all(name not in os.environ for name in all_names-expected);"
            f"assert all(name not in os.environ for name in {set(self.FILE_TO_SECRET) | {'OPENAI_API_KEY_FILE'}!r});"
            "assert os.environ['EXPECT_PARSER_SELECTOR_SCRUB']=='0' or all("
            "name not in os.environ for name in {"
            "'WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_CERTIFICATE_FILE',"
            "'WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_PRIVATE_KEY_FILE'});"
            "assert 'WORKSTREAM_RELEASE_ROLE' not in os.environ;"
            "print('loader-ok')"
        )
        if check_github_settings:
            program += (
                ";import sys;"
                f"sys.path.insert(0,{str(ROOT / 'backend')!r});"
                "selected={key:value for key,value in os.environ.items() "
                "if key.startswith('WORKSTREAM_GITHUB_APP_')};"
                "os.environ.clear();os.environ.update(selected);"
                "from app.core.config import Settings;"
                "settings=Settings(_env_file=None,environment='test');"
                "assert settings.github_app_installation_id is None;"
                "assert (settings.github_app_id is not None)=="
                "('WORKSTREAM_GITHUB_APP_PRIVATE_KEY' in selected)"
            )
        marker = root / "project-agent-sdk-environment"
        if marker.exists():
            marker.chmod(0o600)
        marker.write_text(f"{sdk_environment}\n", encoding="utf-8")
        marker.chmod(0o444)
        loader = root / "release-entrypoint.sh"
        if loader.exists():
            loader.chmod(0o700)
        loader.write_text(
            ENTRYPOINT_PATH.read_text(encoding="utf-8")
            .replace(
                "sdk_marker=/etc/workstream/project-agent-sdk-environment",
                f"sdk_marker={marker}",
            )
            .replace("0:0:444", f"{os.getuid()}:{os.getgid()}:444"),
            encoding="utf-8",
        )
        loader.chmod(0o555)
        return subprocess.run(
            ["/bin/sh", str(loader),
             str(ROOT / "backend/.venv/bin/python") if check_github_settings else sys.executable,
             "-c", program],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_github_key_loader_is_worker_only_and_preserves_multiline_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = "-----BEGIN PRIVATE KEY-----\nsynthetic $(touch ignored) `false`\n-----END PRIVATE KEY-----"
            completed = self._run_loader(root, github=True, content=content)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "loader-ok\n")
            self.assertEqual(completed.stderr, "")
            self.assertFalse((ROOT / "ignored").exists())
            for role in self.ROLE_FILES:
                if role == "worker":
                    continue
                with self.subTest(role=role):
                    refused = self._run_loader(root, role=role, github=True, content=content)
                    self.assertNotEqual(refused.returncode, 0)
                    self.assertIn("worker release role", refused.stderr)
                    self.assertNotIn(content, refused.stdout + refused.stderr)

            for settings in (
                {"WORKSTREAM_GITHUB_APP_ID": ""},
                {"WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE": ""},
                {"WORKSTREAM_GITHUB_APP_ID": "0"},
                {"WORKSTREAM_GITHUB_APP_ID": "-1"},
                {"WORKSTREAM_GITHUB_APP_INSTALLATION_ID": "bad"},
                {"WORKSTREAM_GITHUB_APP_INSTALLATION_ID": "000"},
            ):
                with self.subTest(settings=settings):
                    refused = self._run_loader(root, github=True, github_settings=settings)
                    self.assertNotEqual(refused.returncode, 0)
                    self.assertNotIn(content, refused.stdout + refused.stderr)
            missing = root / "missing-github-key"
            symlink = root / "linked-github-key"
            symlink.symlink_to(root / "github-private-key")
            broad = root / "broad-github-key"
            broad.write_text(content)
            broad.chmod(0o440)
            for invalid in (missing, symlink, broad):
                with self.subTest(invalid=invalid):
                    refused = self._run_loader(root, github=True, override=("WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE", invalid))
                    self.assertNotEqual(refused.returncode, 0)
                    self.assertNotIn(content, refused.stdout + refused.stderr)

    def test_github_optional_installation_and_absent_app_parse_real_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for github in (False, True):
                with self.subTest(github=github):
                    completed = self._run_loader(
                        root, github=github,
                        content="-----BEGIN PRIVATE KEY-----\nsynthetic\n-----END PRIVATE KEY-----",
                        github_settings={"WORKSTREAM_GITHUB_APP_INSTALLATION_ID": ""},
                        check_github_settings=True,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stdout, "loader-ok\n")

    def test_loader_does_not_evaluate_or_log_secret_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "evaluated"
            content = f"$(touch {marker}) `touch {marker}` ; private"
            completed = self._run_loader(root, content=content)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "loader-ok\n")
            self.assertEqual(completed.stderr, "")
            self.assertFalse(marker.exists())
            self.assertNotIn(content, completed.stdout + completed.stderr)

    def test_loader_loads_only_role_secrets_and_rejects_missing_or_unknown_role(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for role in self.ROLE_FILES:
                with self.subTest(role=role):
                    completed = self._run_loader(root, role=role)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stdout, "loader-ok\n")
                    self.assertEqual(completed.stderr, "")
                    required_files = self.ROLE_FILES[role]
                    if role == "model-proxy":
                        required_files = (
                            *required_files,
                            "WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE",
                        )
                    if required_files:
                        missing = self._run_loader(
                            root,
                            role=role,
                            unset_selector=required_files[0],
                        )
                        self.assertNotEqual(missing.returncode, 0)
                        self.assertIn(
                            "required secret file is unavailable", missing.stderr
                        )
            openai = self._run_loader(
                root,
                role="model-proxy",
                provider="openai",
                provider_files=("openai",),
            )
            self.assertEqual(openai.returncode, 0, openai.stderr)
            both = self._run_loader(
                root,
                role="model-proxy",
                provider="openrouter",
                provider_files=("openai", "openrouter"),
            )
            self.assertEqual(both.returncode, 0, both.stderr)
            missing_selected = self._run_loader(
                root,
                role="model-proxy",
                provider="openrouter",
                provider_files=("openai",),
            )
            self.assertNotEqual(missing_selected.returncode, 0)
            self.assertIn("selected provider credential", missing_selected.stderr)
            unsupported = self._run_loader(root, role="model-proxy", provider="unknown")
            self.assertNotEqual(unsupported.returncode, 0)
            self.assertIn("provider is unsupported", unsupported.stderr)
            unknown = self._run_loader(root, role="unknown")
            self.assertNotEqual(unknown.returncode, 0)
            self.assertEqual(unknown.stdout, "")
            self.assertIn("release role is unavailable or unsupported", unknown.stderr)

    def test_api_entrypoint_executes_without_node_proxy_or_model_credentials(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing_socket = root / "not-started.sock"
            with patch.dict(
                os.environ,
                {
                    "WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET": str(missing_socket),
                    "WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET": str(missing_socket),
                    "WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET": str(missing_socket),
                },
            ):
                completed = self._run_loader(root, role="api", provider_files=())
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "loader-ok\n")
            self.assertEqual(completed.stderr, "")
            self.assertFalse(missing_socket.exists())

    def test_loader_binds_runtime_to_sdk_marker_before_provider_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            omni = self._run_loader(
                root,
                runtime="omnicore_agent",
                sdk_environment="omnicore",
            )
            self.assertEqual(omni.returncode, 0, omni.stderr)
            omni_proxy = self._run_loader(
                root,
                role="model-proxy",
                runtime="omnicore_agent",
                sdk_environment="agents",
            )
            self.assertEqual(omni_proxy.returncode, 0, omni_proxy.stderr)
            manager_proxy = self._run_loader(
                root,
                role="model-proxy",
                runtime="manager_authored",
                provider="none",
                sdk_environment="agents",
            )
            self.assertEqual(manager_proxy.returncode, 0, manager_proxy.stderr)
            manager_without_provider = self._run_loader(
                root,
                role="model-proxy",
                runtime="manager_authored",
                provider="none",
                sdk_environment="agents",
                provider_files=(),
            )
            self.assertNotEqual(manager_without_provider.returncode, 0)
            self.assertIn(
                "at least one provider credential", manager_without_provider.stderr
            )
            for sdk_environment in ("agents", "omnicore"):
                with self.subTest(
                    runtime="manager_authored", sdk_environment=sdk_environment
                ):
                    manager = self._run_loader(
                        root,
                        runtime="manager_authored",
                        provider="none",
                        sdk_environment=sdk_environment,
                    )
                    self.assertEqual(manager.returncode, 0, manager.stderr)
            mismatch = self._run_loader(
                root,
                runtime="omnicore_agent",
                sdk_environment="agents",
                content="provider-secret-must-not-load",
            )
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("does not match", mismatch.stderr)
            self.assertNotIn("provider-secret-must-not-load", mismatch.stderr)

    def test_parser_without_runtime_configuration_is_sdk_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for sdk_environment in ("agents", "omnicore"):
                with self.subTest(sdk_environment=sdk_environment):
                    completed = self._run_loader(
                        root,
                        role="parser",
                        sdk_environment=sdk_environment,
                        include_runtime_configuration=False,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stdout, "loader-ok\n")
                    self.assertEqual(completed.stderr, "")

    def test_loader_rejects_empty_missing_directory_and_symlink_without_disclosure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases: list[tuple[str, Path]] = []
            empty = root / "empty"
            empty.touch()
            cases.append(("empty", empty))
            cases.append(("missing", root / "missing"))
            directory = root / "directory"
            directory.mkdir()
            cases.append(("directory", directory))
            target = root / "target"
            target.write_text("do-not-print", encoding="utf-8")
            symlink = root / "symlink"
            symlink.symlink_to(target)
            cases.append(("symlink", symlink))
            broad = root / "broad"
            broad.write_text("do-not-print", encoding="utf-8")
            broad.chmod(0o440)
            cases.append(("broad mode", broad))
            for label, invalid in cases:
                with self.subTest(label=label):
                    completed = self._run_loader(
                        root,
                        override=("WORKSTREAM_DATABASE_URL_FILE", invalid),
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertEqual(completed.stdout, "")
                    self.assertIn("WORKSTREAM_DATABASE_URL", completed.stderr)
                    self.assertNotIn("do-not-print", completed.stderr)


if __name__ == "__main__":
    unittest.main()
