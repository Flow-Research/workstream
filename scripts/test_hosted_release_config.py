"""Focused regressions for the hosted release configuration."""

from __future__ import annotations

from contextlib import redirect_stderr
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = ROOT / "deploy" / "hosted" / "preflight.py"
ENTRYPOINT_PATH = ROOT / "docker" / "backend" / "release-entrypoint.sh"
ENV_EXAMPLE = ROOT / "deploy" / "hosted" / "release.env.example"

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
        self.checker_path.write_text("obsolete local checker sentinel", encoding="utf-8")
        self.direct_user_credentials = self.root / "aws-access-key.json"
        self.direct_user_credentials.write_text(
            json.dumps(
                {
                    "access_key_id": "AKIAEXAMPLE123456789",
                    "secret_access_key": "synthetic-test-secret-key",
                }
            ),
            encoding="utf-8",
        )
        self.direct_user_credentials.chmod(0o400)
        self.cleanup_user_credentials = self.root / "cleanup-aws-access-key.json"
        self.cleanup_user_credentials.write_text(
            json.dumps(
                {
                    "access_key_id": "AKIAEXAMPLE987654321",
                    "secret_access_key": "synthetic-cleanup-test-secret-key",
                }
            ),
            encoding="utf-8",
        )
        self.cleanup_user_credentials.chmod(0o400)
        execution_profile = {
            "capacity": {"maximum_total_bytes": 1_000_000},
            "runtime": {
                "profile_id": "hosted-test-only",
                "platform_root_sha256": "sha256:" + "3" * 64,
                "cpu_millis": 2000,
                "memory_bytes": 2 * 1024**3,
                "temporary_disk_bytes": 4 * 1024**3,
                "maximum_processes": 64,
                "maximum_output_bytes": 1024 * 1024,
                "maximum_log_bytes": 1024 * 1024,
                "aggregate_deadline_ms": 120_000,
                "archive_limits": {
                    "maximum_entries": 2_000,
                    "maximum_path_bytes": 1024,
                    "maximum_path_depth": 32,
                    "maximum_central_directory_bytes": 8 * 1024 * 1024,
                    "maximum_entry_bytes": 128 * 1024 * 1024,
                    "maximum_expanded_bytes": 512 * 1024 * 1024,
                    "maximum_compression_ratio": 100,
                    "maximum_inspection_seconds": 60.0,
                },
            },
            "upload_total_seconds": 300.0,
            "upload_idle_seconds": 10.0,
            "foreground_lease_seconds": 60.0,
            "heartbeat_seconds": 10.0,
            "replay_total_seconds": 30.0,
            "part_bytes": 5 * 1024**2,
        }
        cleanup_profile = {
            "maximum_candidates": 10,
            "run_seconds": 60,
            "lease_seconds": 30,
            "upload_principal": (
                "arn:aws:iam::123456789012:user/workstream-artifact-runtime"
            ),
        }
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
                "/etc/workstream/aws/direct-user-credentials.json",
                str(self.direct_user_credentials),
            )
            .replace(
                "/etc/workstream/aws/source-cleanup-user-credentials.json",
                str(self.cleanup_user_credentials),
            )
            .replace(
                "REPLACE_WITH_APPROVED_SUBMISSION_EXECUTION_PROFILE_JSON",
                json.dumps(execution_profile, separators=(",", ":")),
            )
            .replace(
                "REPLACE_WITH_APPROVED_SUBMISSION_SOURCE_CLEANUP_PROFILE_JSON",
                json.dumps(cleanup_profile, separators=(",", ":")),
            )
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

    def app_environment(self):
        values = self.environment | {preflight.HOSTED_PROFILE_KEY: "app"}
        self.environment_path.write_text(
            "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
            encoding="utf-8",
        )
        return values

    def test_app_profile_keeps_inference_and_rejects_native_runtime_custody(self):
        values = self.app_environment()
        preflight.validate_environment(values)
        rendered = preflight.render_compose(self.environment_path, values)
        preflight.validate_compose(rendered, values)
        services = rendered["services"]
        self.assertIn("model-proxy", services)
        self.assertIn("guide-document-parser", services["worker"]["depends_on"])
        self.assertIn("model-proxy", services["worker"]["depends_on"])
        self.assertEqual(services["outbox-worker"]["depends_on"]["model-proxy"],
                         {"condition": "service_healthy", "required": True})
        paths = preflight.deployment_paths(values)
        self.assertEqual(
            services["worker"]["environment"]["WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET"],
            str(paths.model_socket),
        )
        self.assertEqual(
            services["model-proxy"]["environment"]["WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET"],
            str(paths.model_socket),
        )
        self.assertNotIn(
            "WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET", services["api"]["environment"]
        )
        worker_model_mount = preflight._service_mounts(services["worker"])[
            str(paths.model_socket.parent)
        ]
        self.assertEqual(worker_model_mount["source"], str(paths.model_socket.parent))
        self.assertTrue(worker_model_mount["read_only"])
        self.assertEqual(
            services["outbox-worker"]["environment"]["WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET"],
            str(paths.model_socket),
        )
        self.assertTrue(preflight._service_mounts(services["outbox-worker"])[
            str(paths.model_socket.parent)]["read_only"])
        changed = copy.deepcopy(rendered)
        del changed["services"]["outbox-worker"]["depends_on"]["model-proxy"]
        with self.assertRaisesRegex(preflight.PreflightError, "outbox worker must wait"):
            preflight.validate_compose(changed, values)
        for role in ("api", "worker"):
            self.assertFalse(
                {
                    "WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET",
                    "WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET",
                }
                & services[role]["environment"].keys()
            )
            self.assertNotIn(str(paths.socket_root), preflight._service_mounts(services[role]))
        for role in ("api", "worker", "model-proxy"):
            mounts = preflight._service_mounts(services[role])
            self.assertEqual(
                services[role]["environment"][
                    preflight.DIRECT_USER_CREDENTIAL_FILE_KEY
                ],
                str(preflight.DIRECT_USER_CREDENTIAL_TARGET),
            )
            self.assertEqual(
                mounts[str(preflight.DIRECT_USER_CREDENTIAL_TARGET)]["source"],
                str(self.direct_user_credentials),
            )
            self.assertTrue(
                mounts[str(preflight.DIRECT_USER_CREDENTIAL_TARGET)]["read_only"]
            )
        for role in ("beat", "guide-document-parser", "mcp"):
            if role not in services:
                continue
            self.assertNotIn(
                preflight.DIRECT_USER_CREDENTIAL_FILE_KEY,
                services[role].get("environment", {}),
            )
            self.assertNotIn(
                str(preflight.DIRECT_USER_CREDENTIAL_TARGET),
                preflight._service_mounts(services[role]),
            )
        services["worker"]["environment"]["WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET"] = str(paths.socket)
        with self.assertRaisesRegex(preflight.PreflightError, "environment"):
            preflight.validate_compose(rendered, values)
        with self.assertRaisesRegex(preflight.PreflightError, "unsupported key"):
            preflight.validate_environment(values | {"WORKSTREAM_CHECKER_CONFIG_FILE": str(self.checker_path)})
        with self.assertRaisesRegex(preflight.PreflightError, "requires the trusted model proxy"):
            preflight.validate_environment(values | {"WORKSTREAM_MODEL_PROXY_ENABLED": "false"})

    def test_app_profile_starts_and_resumes_without_native_readiness(self):
        values = self.app_environment()
        self.checker_path.unlink()
        with (
            patch.object(compose, "validate_private_host_inputs") as private,
            patch.object(compose, "validate_typed_submission_profiles") as profiles,
            patch.object(compose, "run_compose", return_value=0) as run,
        ):
            result, error = self._compose_main("up", "--detach")
            self.assertEqual((result, error), (0, ""))
            private.assert_called_once_with(values)
            self.assertEqual(compose.resume_release(self.environment_path, values), 0)
        self.assertEqual(profiles.call_count, 2)
        self.assertEqual(run.call_args_list[-2].args[2][-1], "model-proxy")
        self.assertEqual(run.call_args_list[-1].args[2], ["up", "--detach", "--wait", "--wait-timeout", "120"])

    def test_submission_profiles_are_required_and_bound_to_distinct_cleanup_identity(self):
        preflight.validate_environment(self.environment)
        for key in preflight.SUBMISSION_PROFILE_KEYS:
            for value in (None, "", "not-json", "[]"):
                changed = dict(self.environment)
                if value is None:
                    changed.pop(key)
                else:
                    changed[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(
                    preflight.PreflightError
                ):
                    preflight.validate_environment(changed)
        cleanup = json.loads(
            self.environment["WORKSTREAM_SUBMISSION_SOURCE_CLEANUP_PROFILE"]
        )
        cleanup["upload_principal"] = self.environment[
            preflight.CLEANUP_USER_ARN_KEY
        ]
        with self.assertRaisesRegex(
            preflight.PreflightError, "runtime upload principal"
        ):
            preflight.validate_environment(
                self.environment
                | {
                    "WORKSTREAM_SUBMISSION_SOURCE_CLEANUP_PROFILE": json.dumps(
                        cleanup
                    )
                }
            )
        with self.assertRaisesRegex(preflight.PreflightError, "distinct IAM user"):
            preflight.validate_environment(
                self.environment
                | {
                    preflight.CLEANUP_USER_ARN_KEY: self.environment[
                        "WORKSTREAM_ARTIFACT_S3_RUNTIME_USER_ARN"
                    ]
                }
            )

    def test_exclusive_submission_workers_have_one_queue_and_separate_credentials(self):
        values = self.app_environment()
        rendered = preflight.render_compose(self.environment_path, values)
        preflight.validate_compose(rendered, values)
        services = rendered["services"]
        expected = {
            "submission-finalization-worker": (
                "--queues=workstream.submission_finalization",
                str(self.direct_user_credentials),
            ),
            "submission-source-cleanup-worker": (
                "--queues=workstream.source_cleanup",
                str(self.cleanup_user_credentials),
            ),
        }
        for name, (queue, credential) in expected.items():
            service = services[name]
            self.assertIn(queue, service["command"])
            self.assertEqual(
                preflight._service_mounts(service)[
                    str(preflight.DIRECT_USER_CREDENTIAL_TARGET)
                ]["source"],
                credential,
            )
            self.assertEqual(
                {secret["source"] for secret in service["secrets"]},
                {"database_url", "celery_broker_url"},
            )
            self.assertFalse(
                set(preflight.REMOTE_RUNNER_ENVIRONMENT_KEYS)
                & set(service["environment"])
            )
        for name, service in services.items():
            mounts = preflight._service_mounts(service)
            if name != "submission-source-cleanup-worker":
                self.assertNotIn(
                    str(self.cleanup_user_credentials),
                    {str(mount.get("source")) for mount in mounts.values()},
                )
        changed = copy.deepcopy(rendered)
        changed["services"]["submission-finalization-worker"]["command"].append(
            "--queues=celery"
        )
        with self.assertRaisesRegex(preflight.PreflightError, "exclusive worker"):
            preflight.validate_compose(changed, values)

    def test_feedback_email_overlay_restricts_key_and_queue_to_its_worker(self):
        disabled = self.app_environment()
        rendered = preflight.render_compose(self.environment_path, disabled)
        worker = preflight.FEEDBACK_EMAIL_WORKER
        self.assertNotIn(worker, rendered["services"])
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_environment(disabled | {preflight.FEEDBACK_EMAIL_ENABLED_KEY: "true"})
        values = disabled | {
            preflight.FEEDBACK_EMAIL_ENABLED_KEY: "true",
            preflight.RESEND_KEY_FILE: str(self.root / "resend-api-key"),
        }
        self.environment_path.write_text(
            "\n".join(f"{name}={value}" for name, value in values.items()) + "\n", encoding="utf-8",
        )
        preflight.validate_environment(values)
        rendered = preflight.render_compose(self.environment_path, values)
        preflight.validate_compose(rendered, values)
        services = rendered["services"]
        self.assertEqual(
            [name for name, item in services.items()
             if any(secret.get("source") == "resend_api_key" for secret in item.get("secrets", []))],
            [worker],
        )
        self.assertIn("--queues=workstream.submission_feedback_email", services[worker]["command"])
        changed = copy.deepcopy(rendered)
        changed["services"][worker]["command"].append("--queues=workstream.outbox")
        with self.assertRaisesRegex(preflight.PreflightError, "exclusive worker"):
            preflight.validate_compose(changed, values)
        changed = copy.deepcopy(rendered)
        changed["services"]["outbox-scan-worker"]["environment"][preflight.RESEND_KEY_FILE] = "/run/secrets/resend_api_key"
        with self.assertRaisesRegex(preflight.PreflightError, "unrelated secret selector"):
            preflight.validate_compose(changed, values)

    def test_image_owned_profile_validation_is_fixed_and_fail_closed(self):
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(preflight.subprocess, "run", return_value=completed) as run:
            preflight.validate_typed_submission_profiles(
                self.environment_path, self.environment, cached_images=True
            )
        command = run.call_args.args[0]
        self.assertIn("--pull", command)
        self.assertIn("never", command)
        self.assertIn("SubmissionExecutionProfile.model_validate", command[-1])
        self.assertIn("SubmissionSourceCleanupProfile.model_validate", command[-1])
        self.assertIs(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(run.call_args.kwargs["stderr"], subprocess.DEVNULL)
        with patch.object(
            preflight.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 20),
        ), self.assertRaisesRegex(preflight.PreflightError, "execution profile failed"):
            preflight.validate_typed_submission_profiles(
                self.environment_path, self.environment
            )

    def test_local_data_shutdown_preserves_dependencies_until_consumers_stop(self):
        values = self.local_data_environment()
        with patch.object(preflight.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(preflight.run_shutdown(self.environment_path, values), 0)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[-1][-5:], ["stop", "--timeout", "60", "redis", "postgres"])
        self.assertTrue(any(command[-7:] == ["stop", "--timeout", "7320", "worker",
            "project-control-worker", "artifact-worker", "outbox-worker"] for command in commands[:-1]))
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

    def test_local_postgres_readiness_rejects_temporary_unix_server(self):
        values = self.local_data_environment()
        rendered = preflight.render_compose(self.environment_path, values)
        for probe in (
            ["CMD", "pg_isready", "-U", "postgres", "-d", "workstream"],
            ["CMD", "pg_isready", "-h", "/var/run/postgresql", "-U", "postgres", "-d", "workstream"],
        ):
            with self.subTest(probe=probe):
                changed = copy.deepcopy(rendered)
                changed["services"]["postgres"]["healthcheck"]["test"] = probe
                with self.assertRaisesRegex(preflight.PreflightError, "final TCP server"):
                    preflight.validate_compose(changed, values)

    def test_local_data_bootstrap_does_not_start_application_or_replace_mcp(self):
        values = self.mcp_environment() | self.local_data_environment()
        with patch.object(preflight.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(preflight.run_compose(self.environment_path, values, ["start", "local-data"]), 0)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][-8:], ["up", "--detach", "--no-deps", "--wait", "--wait-timeout", "120", "postgres", "redis"])
        self.assertEqual(run.call_args.kwargs["timeout"], 150)

    def test_mcp_overlay_is_private_and_has_only_its_exchange_credential(self):
        values = self.mcp_environment()
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
                with self.assertRaisesRegex(preflight.PreflightError, "MCP isolation|mcp bind mount"):
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
        values = self.mcp_environment()
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
        self.assertEqual(calls[1][-3:], ["--detach", "--no-deps", "api"])
        self.assertIn("--wait", calls[1])
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

    def test_targeted_worker_up_keeps_mcp_coupled_to_api_dependency(self):
        values = self.mcp_environment()
        for service in ("project-control-worker", "artifact-worker", "outbox-scan-worker",
                        "outbox-worker", "submission-finalization-worker",
                        "submission-source-cleanup-worker"):
            calls = []
            def run(command, **_kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0)
            with self.subTest(service=service), patch.object(
                preflight.subprocess, "run", side_effect=run
            ), patch.object(preflight, "validate_running_mcp_namespace"):
                self.assertEqual(preflight.run_compose(
                    self.environment_path, values, ["up", "--detach", service]
                ), 0)
            self.assertEqual(calls[0][-2:], ["stop", "mcp"])
            self.assertIn(service, calls[1])
            self.assertIn("--force-recreate", calls[2])
            self.assertEqual(calls[2][-1], "mcp")

    def test_full_launch_waits_for_api_before_starting_stale_mcp(self):
        values = self.mcp_environment()
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            # A rebooted MCP would be unhealthy until recreated. The API phase
            # must not include it, or --wait fails before repair can run.
            if "up" in command and "--force-recreate" not in command:
                self.assertNotIn("mcp", command)
                self.assertIn("api", command)
                self.assertIn("--wait", command)
            return subprocess.CompletedProcess(command, 0)
        with (
            patch.object(preflight.subprocess, "run", side_effect=run),
            patch.object(preflight, "validate_running_mcp_namespace") as namespace,
        ):
            self.assertEqual(preflight.run_compose(
                self.environment_path, values, ["up", "--detach", "--wait"],
                cached_images=True,
            ), 0)
        self.assertEqual(len(calls), 3)
        self.assertIn("--force-recreate", calls[2])
        self.assertEqual(calls[2][-1], "mcp")
        for command in calls[1:]:
            self.assertEqual(command[command.index("--pull") + 1], "never")
        namespace.assert_called_once()

    def test_isolated_bootstrap_does_not_start_or_stop_mcp(self):
        values = self.mcp_environment()
        for service in ("model-proxy", "identity", "guide-document-parser"):
            with self.subTest(service=service), patch.object(
                preflight.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
            ) as run:
                self.assertEqual(preflight.run_compose(self.environment_path, values,
                                 ["up", "-d", service]), 0)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][-3:], ["up", "-d", service])

    def test_failed_api_replacement_does_not_restart_mcp(self):
        values = self.mcp_environment()
        with patch.object(preflight.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 1),
        ]) as run:
            self.assertEqual(preflight.run_compose(self.environment_path, values,
                             ["up", "--detach", "--no-deps", "api"]), 1)
        self.assertEqual(run.call_count, 2)

    def mcp_environment(self):
        return self.environment | {
            "WORKSTREAM_MCP_IMAGE": "example.test/mcp@sha256:" + "b" * 64,
            "WORKSTREAM_MCP_RESOURCE_URL": "https://workstream.example.test/mcp",
            "WORKSTREAM_MCP_EXCHANGE_SECRET_FILE": str(self.root / "mcp-exchange-secret"),
        }

    def identity_values(self):
        return self.local_data_environment() | {
            "FLOW_IDENTITY_IMAGE": "example.test/identity@sha256:" + "a" * 64,
            "FLOW_IDENTITY_HOSTNAME": "identity.example.test",
            "FLOW_IDENTITY_DATABASE_PASSWORD_FILE": str(self.root / "identity-db-password"),
            "FLOW_IDENTITY_TLS_CERT_FILE": str(self.root / "identity-cert.pem"),
            "FLOW_IDENTITY_TLS_KEY_FILE": str(self.root / "identity-tls-key.pem"),
            "FLOW_IDENTITY_PROXY_ADDRESS": "172.18.0.1",
            "WORKSTREAM_TOKEN_ISSUER": "https://identity.example.test/realms/flow",
            "WORKSTREAM_TOKEN_AUDIENCE": "workstream-api",
            "WORKSTREAM_TOKEN_JWKS_URL": "https://identity.example.test/realms/flow/protocol/openid-connect/certs",
        }

    def test_identity_resolution_has_no_host_alias_override(self):
        rendered = preflight.render_compose(self.environment_path, self.environment)
        preflight.validate_compose(rendered, self.environment)
        rendered["services"]["api"]["extra_hosts"] = ["identity.example.test=host-gateway"]
        with self.assertRaisesRegex(preflight.PreflightError, "public DNS"):
            preflight.validate_compose(rendered, self.environment)

    def test_identity_overlay_bounds_process_storage_and_exposure(self):
        self.assertNotIn(str(preflight.IDENTITY_COMPOSE_PATH), preflight._compose_file_arguments(self.environment))
        values = self.identity_values()
        preflight.validate_environment(values)
        rendered = preflight.render_compose(self.environment_path, values)
        preflight.validate_compose(rendered, values)
        issuer = rendered["services"]["identity"]
        self.assertEqual(issuer["networks"], {"default": None})
        self.assertEqual(issuer["environment"]["KC_DB_USERNAME"], "flow_identity")
        self.assertEqual(issuer["environment"]["KC_HOSTNAME"], "https://" + values["FLOW_IDENTITY_HOSTNAME"])
        self.assertNotIn("KC_HOSTNAME_ADMIN", issuer["environment"])
        changed = copy.deepcopy(rendered)
        changed["services"]["identity"]["environment"]["KC_HOSTNAME_ADMIN"] = "https://identity-admin.localhost:19443"
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_compose(changed, values)
        self.assertFalse(any("BOOTSTRAP" in name for name in issuer["environment"]))
        self.assertEqual(len(issuer["volumes"]), 3)
        for key, value in (
            ("user", "10001:10001"), ("mem_limit", 0), ("command", ["start-dev"]),
            ("environment", {"WORKSTREAM_DATABASE_URL": "forbidden"}),
            ("networks", {"foreign": None}), ("tmpfs", []),
        ):
            with self.subTest(field=key):
                changed = copy.deepcopy(rendered)
                changed["services"]["identity"][key] = value
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_compose(changed, values)
        for field, value in (("internal", True), ("driver", "host"), ("external", True),
                              ("ipam", {"driver": "custom"}), ("driver_opts", {"x": "y"})):
            changed = copy.deepcopy(rendered)
            changed["networks"]["default"][field] = value
            with self.subTest(network=field), self.assertRaises(preflight.PreflightError):
                preflight.validate_compose(changed, values)
        changed = copy.deepcopy(rendered)
        changed["services"]["identity"]["ports"][0]["host_ip"] = "0.0.0.0"
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_compose(changed, values)
        changed = copy.deepcopy(rendered)
        changed["services"]["identity"]["volumes"][0]["source"] = str(self.root)
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_compose(changed, values)
        changed = copy.deepcopy(rendered)
        changed["services"]["identity"]["healthcheck"]["test"] = ["CMD", "true"]
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_compose(changed, values)

    def test_identity_configuration_rejects_partial_unpinned_and_unbounded_trust(self):
        values = self.identity_values()
        for key, value in (
            ("FLOW_IDENTITY_IMAGE", "identity:latest"),
            ("FLOW_IDENTITY_HOSTNAME", "wrong.example.test"),
            ("WORKSTREAM_TOKEN_AUDIENCE", "foreign"),
            ("WORKSTREAM_TOKEN_JWKS_URL", "https://foreign.example.test/jwks.json"),
            ("FLOW_IDENTITY_PROXY_ADDRESS", "172.16.0.0/12"),
            ("FLOW_IDENTITY_TLS_KEY_FILE", "relative/key.pem"),
        ):
            with self.subTest(key=key), self.assertRaises(preflight.PreflightError):
                preflight.validate_environment(values | {key: value})
        del values["FLOW_IDENTITY_DATABASE_PASSWORD_FILE"]
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_environment(values)

    def test_identity_host_custody_rejects_missing_and_reused_private_files(self):
        values = self.identity_values()
        with (patch.object(preflight, "_private_metadata") as metadata,
              patch.object(Path, "stat", return_value=type("Metadata", (), {"st_ino": 1, "st_dev": 1})())):
            with self.assertRaisesRegex(preflight.PreflightError, "reuse"):
                preflight.validate_identity_host_inputs(values)
            self.assertEqual(metadata.call_args_list[0].kwargs,
                             {"kind": "file", "uid": 1000, "gid": 1000, "mode": 0o400})
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_identity_host_inputs(values)
        values["FLOW_IDENTITY_DATABASE_PASSWORD_FILE"] = str(preflight.deployment_paths(values).scratch / "identity")
        with self.assertRaisesRegex(preflight.PreflightError, "outside processing roots"):
            preflight.validate_environment(values)

    def test_identity_startup_checks_only_issuer_inputs_and_waits(self):
        values = self.identity_values()
        with (
            patch.object(
                compose,
                "parse_args",
                return_value=type(
                    "Args",
                    (),
                    {
                        "env_file": self.environment_path,
                        "compose_arguments": ["start", "identity"],
                    },
                )(),
            ),
            patch.object(compose, "parse_environment", return_value=values),
            patch.object(compose, "render_compose", return_value={}),
            patch.object(compose, "validate_compose"),
            patch.object(
                compose, "validate_identity_host_inputs"
            ) as issuer_inputs,
            patch.object(compose, "validate_private_host_inputs") as backend_inputs,
            patch.object(compose, "run_compose", return_value=0),
        ):
            self.assertEqual(compose.main(), 0)
            issuer_inputs.assert_called_once_with(values)
            backend_inputs.assert_not_called()
        with patch.object(
            preflight.subprocess,
            "run",
            return_value=type("Result", (), {"returncode": 0})(),
        ) as run:
            self.assertEqual(
                preflight.run_compose(
                    self.environment_path, values, ["start", "identity"]
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
                    "360",
                    "identity",
                ],
            )
            self.assertEqual(run.call_args.kwargs["timeout"], 390)

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

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_worker_cannot_consume_finalization_or_omit_its_queue_selection(self) -> None:
        rendered = preflight.render_compose(self.environment_path, self.environment)
        for selection in (None, "--queues=celery", "-Qworkstream.submission_finalization",
                          "--queues=workstream.project_setup,workstream.outbox"):
            with self.subTest(selection=selection):
                changed = copy.deepcopy(rendered)
                command = changed["services"]["worker"]["command"]
                command.remove("--queues=workstream.project_setup")
                if selection:
                    command.append(selection)
                with self.assertRaisesRegex(preflight.PreflightError, "worker delivery profile"):
                    preflight.validate_compose(changed, self.environment)


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

    def test_actual_render_rejects_config_backed_by_direct_user_credentials(self) -> None:
        compose_text = preflight.COMPOSE_PATH.read_text(encoding="utf-8").replace(
            "  beat:\n    <<: *backend-runtime\n",
            "  beat:\n    <<: *backend-runtime\n"
            "    configs:\n"
            "      - source: direct_user_credentials\n"
            "        target: /run/unrelated/key.pem\n",
            1,
        )
        compose_text += (
            "\nconfigs:\n"
            "  direct_user_credentials:\n"
            "    file: "
            "${WORKSTREAM_ARTIFACT_S3_DIRECT_USER_CREDENTIAL_HOST_FILE}\n"
        )
        rendered = self._render_modified_compose(compose_text)

        self.assertEqual(
            rendered["services"]["beat"]["configs"][0]["target"],
            "/run/unrelated/key.pem",
        )
        self.assertEqual(
            rendered["configs"]["direct_user_credentials"]["file"],
            str(self.direct_user_credentials),
        )
        with self.assertRaisesRegex(preflight.PreflightError, "Compose configs"):
            preflight.validate_compose(rendered, self.environment)

    def test_actual_render_rejects_extra_direct_credential_binds(self) -> None:
        compose_text = preflight.COMPOSE_PATH.read_text(encoding="utf-8")
        cases = (
            (
                "API duplicate credential",
                "    restart: on-failure:5\n    stop_grace_period: 30s\n    healthcheck:\n      test: [CMD, python, -c,",
                "/run/unrelated/api-credential.json",
            ),
        )
        for label, marker, target in cases:
            with self.subTest(label=label):
                extra_bind = (
                    "      - type: bind\n"
                    "        source: ${WORKSTREAM_ARTIFACT_S3_DIRECT_USER_CREDENTIAL_HOST_FILE}\n"
                    f"        target: {target}\n"
                    "        read_only: true\n"
                )
                rendered = self._render_modified_compose(
                    compose_text.replace(marker, extra_bind + marker, 1)
                )
                service_name = "api"
                rendered_mounts = preflight._service_mounts(
                    rendered["services"][service_name]
                )
                self.assertEqual(
                    rendered_mounts[target]["source"],
                    str(self.direct_user_credentials),
                )
                with self.assertRaisesRegex(
                    preflight.PreflightError,
                    f"{service_name} bind mounts differ",
                ):
                    preflight.validate_compose(rendered, self.environment)

    def test_actual_render_rejects_parser_hardlink_identity_bind(self) -> None:
        private_key_alias = self.root / "direct-key-parser-alias.json"
        os.link(self.direct_user_credentials, private_key_alias)
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
            "${WORKSTREAM_ARTIFACT_S3_DIRECT_USER_CREDENTIAL_HOST_FILE}",
            1,
        )
        rendered = self._render_modified_compose(compose_text)

        self.assertEqual(
            rendered["secrets"]["database_url"]["file"],
            str(self.direct_user_credentials),
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
            operation_environment["WORKSTREAM_ARTIFACT_S3_RUNTIME_USER_ARN"],
            self.environment["WORKSTREAM_ARTIFACT_S3_RUNTIME_USER_ARN"],
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
        self.assertEqual(commands[1][-7:], ["stop", "--timeout", "7320", "worker",
            "project-control-worker", "artifact-worker", "outbox-worker"])
        self.assertEqual(
            commands[2][-5:],
            [
                "stop",
                "--timeout",
                "420",
                "submission-finalization-worker",
                "submission-source-cleanup-worker",
            ],
        )
        self.assertEqual(
            commands[3][-4:],
            ["stop", "--timeout", "120", "outbox-scan-worker"],
        )
        self.assertEqual(
            commands[4][-4:],
            ["stop", "--timeout", "7320", "model-proxy"],
        )
        self.assertEqual(
            commands[5][-2:],
            ["stop", "guide-document-parser"],
        )

    def test_shutdown_failure_keeps_later_dependencies_running(self) -> None:
        for failed_phase in (0, 1, 2, 3, 4):
            with self.subTest(failed_phase=failed_phase):
                results = [
                    subprocess.CompletedProcess([], 17 if index == failed_phase else 0)
                    for index in range(6)
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

    def test_removed_proof_command_is_rejected(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                ["compose.py", "--env-file", str(self.environment_path), "proof"],
            ),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(compose.main(), 1)

    def test_artifact_preparation_deadline_is_required_bounded_and_shared(self):
        key = "WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS"
        for deadline in ("360", "3400"):
            values = self.environment | {key: deadline}
            with self.subTest(deadline=deadline):
                preflight.validate_environment(values)
                rendered = preflight.render_compose(self.environment_path, values)
                preflight.validate_compose(rendered, values)
                for role in preflight.ROLE_SECRET_FILE_KEYS:
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
            "relative direct credential": (
                "WORKSTREAM_ARTIFACT_S3_DIRECT_USER_CREDENTIAL_HOST_FILE",
                "aws-access-key.json",
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

    def test_environment_requires_every_aws_s3_identity_setting(self) -> None:
        for key in preflight.AWS_S3_IDENTITY_KEYS:
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
        for key in preflight.TRIAL_KEYS:
            changed = dict(self.environment)
            del changed[key]
            with self.assertRaises(preflight.PreflightError):
                preflight.validate_environment(changed)
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
        writable_model_socket = copy.deepcopy(rendered)
        for mount in writable_model_socket["services"]["worker"]["volumes"]:
            if mount["target"] == str(
                preflight.deployment_paths(self.environment).model_socket.parent
            ):
                mount["read_only"] = False
        cases.append(("worker writable model callback socket", writable_model_socket))
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
            if mount["target"] == str(preflight.DIRECT_USER_CREDENTIAL_TARGET):
                mount["read_only"] = False
        cases.append(("writable direct credential", writable_identity))
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
        private_key_alias = self.root / "direct-user-credential-alias.json"
        os.link(self.direct_user_credentials, private_key_alias)
        hardlink_beat_identity["services"]["beat"]["volumes"] = [
            {
                "type": "bind",
                "source": str(private_key_alias),
                "target": "/run/unrelated/key.pem",
                "read_only": True,
            }
        ]
        cases.append(("hardlink direct credential exposed to Beat", hardlink_beat_identity))
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
        beat_direct_selector = copy.deepcopy(rendered)
        beat_direct_selector["services"]["beat"]["environment"][
            preflight.DIRECT_USER_CREDENTIAL_FILE_KEY
        ] = str(preflight.DIRECT_USER_CREDENTIAL_TARGET)
        cases.append(("direct credential selector exposed to Beat", beat_direct_selector))
        parser_direct_selector = copy.deepcopy(rendered)
        parser_direct_selector["services"]["guide-document-parser"]["environment"][
            preflight.DIRECT_USER_CREDENTIAL_FILE_KEY
        ] = str(preflight.DIRECT_USER_CREDENTIAL_TARGET)
        cases.append(("direct credential selector exposed to parser", parser_direct_selector))
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


    def test_trusted_intake_requires_pins_without_shared_runner_mounts(self) -> None:
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
            environment = rendered["services"][role]["environment"]
            for key in preflight.INTAKE_DIGEST_KEYS:
                self.assertEqual(environment[key], self.environment[key])
            self.assertNotIn("WORKSTREAM_ARTIFACT_INTAKE_SERVICE_SOCKET", environment)
            self.assertNotIn(
                str(preflight.deployment_paths(self.environment).socket_root),
                preflight._service_mounts(rendered["services"][role]),
            )

    def test_runner_endpoints_match_the_closed_release_contract(self) -> None:
        key = preflight.REMOTE_RUNNER_ENDPOINTS_KEY
        endpoint = json.loads(self.environment[key])[0]
        for invalid in (
            [],
            [endpoint | {"host": "a..b"}],
            [endpoint | {"server_name": "*.test"}],
            [endpoint | {"config_sha256": "newest"}],
            [endpoint, endpoint | {"port": endpoint["port"] + 1}],
        ):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(preflight.PreflightError, "external runner endpoint"):
                preflight.validate_environment(self.environment | {key: json.dumps(invalid)})



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
