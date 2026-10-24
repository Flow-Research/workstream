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
            str(preflight.SOCKET_ROOT), "/var/lib/workstream/checker-runtime"
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
                "guide-document-parser",
                "checker-service",
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
            "guide-document-parser",
            "checker-service",
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
        for name in ("api", "worker", "beat", *preflight.PROOF_SERVICES):
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
            for name in ("api", "worker", "beat", "checker-service")
        }
        self.assertIn("/api/v1/health", health_commands["api"])
        self.assertIn("/tmp/celery-worker.pid", health_commands["worker"])
        self.assertIn("/tmp/celerybeat.pid", health_commands["beat"])
        self.assertIn(".Runtimes.runsc", health_commands["checker-service"])
        self.assertEqual(services["api"]["stop_grace_period"], "30s")
        self.assertIn(services["worker"]["stop_grace_period"], {"7320s", "2h2m0s"})
        self.assertEqual(services["beat"]["stop_grace_period"], "30s")
        self.assertEqual(services["guide-document-parser"]["stop_grace_period"], "30s")
        self.assertEqual(services["api"]["ports"][0]["host_ip"], "127.0.0.1")
        expected_secrets = {
            target[0] for target in preflight.SECRET_FILE_TARGETS.values()
        }
        self.assertEqual(set(rendered["secrets"]), expected_secrets)
        for key, (secret_name, _target) in preflight.SECRET_FILE_TARGETS.items():
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
        self.assertNotIn("secrets", services["checker-service"])
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
                    preflight.GUIDE_SOCKET_PATH
                ),
            },
        )
        self.assertEqual(parser["mem_limit"], "536870912")
        self.assertEqual(parser["memswap_limit"], "536870912")
        self.assertEqual(parser["cpus"], 1)
        self.assertEqual(parser["pids_limit"], 64)
        self.assertFalse(
            preflight._service_mounts(parser)[str(preflight.GUIDE_SOCKET_ROOT)].get(
                "read_only", False
            )
        )
        worker_mounts = preflight._service_mounts(services["worker"])
        self.assertTrue(worker_mounts[str(preflight.GUIDE_SOCKET_ROOT)]["read_only"])
        for name in (
            "api",
            "beat",
            "checker-service",
            *preflight.PROOF_SERVICES,
        ):
            self.assertNotIn(
                str(preflight.GUIDE_SOCKET_ROOT),
                preflight._service_mounts(services[name]),
            )
        for name in ("api", "worker"):
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
        checker_mounts = preflight._service_mounts(services["checker-service"])
        self.assertNotIn(
            str(preflight.ROLES_ANYWHERE_CERTIFICATE_TARGET), checker_mounts
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
                "    depends_on:\n      checker-service:\n",
                "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_READINESS_PRIVATE_KEY_HOST_FILE",
                "/run/unrelated/readiness-key.pem",
            ),
            (
                "API negative key",
                "    depends_on:\n      checker-service:\n",
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

    def test_actual_render_rejects_checker_hardlink_identity_bind(self) -> None:
        private_key_alias = self.root / "runtime-key-checker-alias.pem"
        os.link(self.runtime_private_key, private_key_alias)
        marker = (
            "    healthcheck:\n"
            '      test: [CMD-SHELL, "test -S /var/lib/workstream/checker-runtime/checker.sock'
        )
        extra_bind = (
            "      - type: bind\n"
            f"        source: {private_key_alias}\n"
            "        target: /run/unrelated/key.pem\n"
            "        read_only: true\n"
        )
        compose_text = preflight.COMPOSE_PATH.read_text(encoding="utf-8").replace(
            marker,
            extra_bind + marker,
            1,
        )
        rendered = self._render_modified_compose(compose_text)

        checker_mounts = preflight._service_mounts(
            rendered["services"]["checker-service"]
        )
        self.assertEqual(
            checker_mounts["/run/unrelated/key.pem"]["source"],
            str(private_key_alias),
        )
        with self.assertRaisesRegex(preflight.PreflightError, "checker-service bind"):
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

    def _compose_main(self, operation: str) -> tuple[int, str]:
        errors = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                ["compose.py", "--env-file", str(self.environment_path), operation],
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
            patch.object(preflight, "validate_docker_runtime"),
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
                    patch.object(compose, "validate_docker_runtime") as runtime,
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
                        compose, "validate_docker_runtime", side_effect=runtime_check
                    ),
                    patch.object(compose, "validate_trusted_intake", side_effect=intake_check),
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
                        {"private": ["private"], "runtime": ["private", "runtime"],
                         "intake": ["private", "runtime", "intake"]}[failure],
                    )
                    run.assert_not_called()

    def test_stop_remains_available_with_invalid_checker_configuration(self) -> None:
        self.checker_path.write_text("invalid json", encoding="utf-8")
        with (
            patch.object(compose, "load_checker_config") as load,
            patch.object(compose, "validate_private_host_inputs") as private,
            patch.object(compose, "validate_docker_runtime") as runtime,
            patch.object(compose, "run_shutdown", return_value=0) as shutdown,
        ):
            self.assertEqual(self._compose_main("stop"), (0, ""))
        load.assert_not_called()
        private.assert_not_called()
        runtime.assert_not_called()
        shutdown.assert_called_once_with(self.environment_path, self.environment)

    def test_shutdown_stops_producers_then_worker_then_parser_and_checker(self) -> None:
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(preflight.subprocess, "run", return_value=completed) as run:
            self.assertEqual(
                preflight.run_shutdown(self.environment_path, self.environment), 0
            )
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][-3:], ["stop", "beat", "api"])
        self.assertEqual(commands[1][-4:], ["stop", "--timeout", "7320", "worker"])
        self.assertEqual(
            commands[2][-3:],
            ["stop", "guide-document-parser", "checker-service"],
        )

    def test_shutdown_failure_keeps_later_dependencies_running(self) -> None:
        for failed_phase in (0, 1):
            with self.subTest(failed_phase=failed_phase):
                results = [
                    subprocess.CompletedProcess([], 17 if index == failed_phase else 0)
                    for index in range(3)
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
                ],
            ),
            patch.object(compose, "run_shutdown") as shutdown,
            redirect_stderr(errors),
        ):
            self.assertEqual(compose.main(), 1)
        shutdown.assert_not_called()
        self.assertIn(
            "fixed producer, worker, parser/checker sequence", errors.getvalue()
        )

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
            patch.object(compose, "validate_private_host_inputs"),
            patch.object(compose, "validate_docker_runtime"),
            patch.object(compose, "validate_trusted_intake"),
            patch.object(compose, "run_proof_group", return_value=0) as proof_group,
        ):
            self.assertEqual(compose.main(), 0)
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
        }
        manager.pop("WORKSTREAM_PROJECT_AGENT_API_KEY_FILE")
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
        }
        for old, new in replacements.items():
            manager_text = manager_text.replace(old, new)
        manager_text = (
            "\n".join(
                line
                for line in manager_text.splitlines()
                if not line.startswith("WORKSTREAM_PROJECT_AGENT_API_KEY_FILE=")
            )
            + "\n"
        )
        manager_path = self.root / "manager.env"
        manager_path.write_text(manager_text, encoding="utf-8")
        manager = preflight.parse_environment(manager_path)

        preflight.validate_environment(manager)
        rendered = preflight.render_compose(manager_path, manager)
        preflight.validate_compose(rendered, manager)

        self.assertNotIn("project_agent_api_key", rendered.get("secrets", {}))
        worker = rendered["services"]["worker"]
        self.assertNotIn("WORKSTREAM_PROJECT_AGENT_API_KEY_FILE", worker["environment"])
        self.assertNotIn(
            "project_agent_api_key",
            {item["source"] for item in worker["secrets"]},
        )

        selected = manager | {
            "WORKSTREAM_PROJECT_AGENT_API_KEY_FILE": str(self.root / "provider")
        }
        with self.assertRaisesRegex(
            preflight.PreflightError, "cannot select a provider credential"
        ):
            preflight.validate_environment(selected)

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
        networked = copy.deepcopy(rendered)
        networked["services"]["checker-service"]["network_mode"] = "default"
        cases.append(("networked checker", networked))
        privileged = copy.deepcopy(rendered)
        privileged["services"]["checker-service"]["cap_drop"] = []
        cases.append(("checker capabilities", privileged))
        writable_material = copy.deepcopy(rendered)
        for mount in writable_material["services"]["checker-service"]["volumes"]:
            if mount["target"] == str(preflight.SCRATCH_ROOT):
                mount["read_only"] = False
        cases.append(("writable checker material", writable_material))
        volatile_owner = copy.deepcopy(rendered)
        for mount in volatile_owner["services"]["checker-service"]["volumes"]:
            if mount["target"] == str(preflight.SOCKET_ROOT):
                mount["source"] = "/run/workstream-checker"
        cases.append(("boot-volatile checker custody", volatile_owner))
        for role in ("api", "worker"):
            writable_owner = copy.deepcopy(rendered)
            for mount in writable_owner["services"][role]["volumes"]:
                if mount["target"] == str(preflight.SOCKET_ROOT):
                    mount["read_only"] = False
            cases.append((f"{role} writable checker custody", writable_owner))
        root_controller = copy.deepcopy(rendered)
        root_controller["services"]["checker-service"]["user"] = "0:0"
        cases.append(("root checker controller", root_controller))
        extra_group = copy.deepcopy(rendered)
        extra_group["services"]["checker-service"]["group_add"].append("10002")
        cases.append(("extra checker group", extra_group))
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
            "WORKSTREAM_PROJECT_AGENT_API_KEY_FILE"
        ] = "/run/secrets/project_agent_api_key"
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
        checker_identity = copy.deepcopy(rendered)
        checker_identity["services"]["checker-service"]["volumes"].append(
            copy.deepcopy(rendered["services"]["api"]["volumes"][-1])
        )
        cases.append(("runtime identity exposed to checker", checker_identity))
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
        ] = str(preflight.GUIDE_SOCKET_PATH)
        cases.append(("guide parser socket exposed to proof", proof_parser_socket))
        proof_provider_selector = copy.deepcopy(rendered)
        proof_provider_selector["services"]["aws-proof-coordinate"]["environment"][
            "WORKSTREAM_PROJECT_AGENT_API_KEY_FILE"
        ] = "/run/secrets/project_agent_api_key"
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

    def test_private_host_inputs_check_exact_socket_group_without_reading_secrets(
        self,
    ) -> None:
        scratch = self.root / "scratch"
        socket_root = self.root / "socket"
        guide_socket_root = self.root / "guide-socket"
        intake_root = self.root / "intake"
        intake_root.mkdir(mode=0o700)
        intake_path = intake_root / "checker.sock"
        intake_listener = socket.socket(socket.AF_UNIX)
        intake_listener.bind(str(intake_path))
        intake_path.chmod(0o600)
        self.addCleanup(intake_listener.close)
        for field, value in (("INTAKE_SOCKET_ROOT", intake_root), ("INTAKE_SOCKET_PATH", intake_path)):
            owned_patch = patch.object(preflight, field, value)
            owned_patch.start()
            self.addCleanup(owned_patch.stop)
        scratch.mkdir(mode=0o700)
        socket_root.mkdir(mode=0o700)
        guide_socket_root.mkdir(mode=0o750)
        host_uid = os.getuid()
        host_gid = os.getgid()
        environment = dict(self.environment)
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
            environment["WORKSTREAM_DOCKER_SOCKET_GID"] = str(
                docker_socket.stat().st_gid
            )
            with (
                patch.object(preflight, "SCRATCH_ROOT", scratch),
                patch.object(preflight, "SOCKET_ROOT", socket_root),
                patch.object(preflight, "GUIDE_SOCKET_ROOT", guide_socket_root),
                patch.object(
                    preflight,
                    "GUIDE_SOCKET_PATH",
                    guide_socket_root / "guide.sock",
                ),
                patch.object(preflight, "GUIDE_PARSER_UID", host_uid),
                patch.object(preflight, "GUIDE_PARSER_GID", host_gid),
                patch.object(preflight, "DOCKER_SOCKET", docker_socket),
            ):
                preflight.validate_private_host_inputs(environment)
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
                environment["WORKSTREAM_DOCKER_SOCKET_GID"] = str(
                    docker_socket.stat().st_gid + 1
                )
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_private_host_inputs(environment)
            environment["WORKSTREAM_DOCKER_SOCKET_GID"] = str(
                docker_socket.stat().st_gid
            )
            scratch_secret = scratch / "project-agent-secret"
            scratch_secret.write_text("private", encoding="utf-8")
            scratch_secret.chmod(0o400)
            scratch_alias = self.root / "scratch-alias"
            scratch_alias.symlink_to(scratch, target_is_directory=True)
            environment["WORKSTREAM_PROJECT_AGENT_API_KEY_FILE"] = str(
                scratch_alias / scratch_secret.name
            )
            with (
                patch.object(preflight, "SCRATCH_ROOT", scratch),
                patch.object(preflight, "SOCKET_ROOT", socket_root),
                patch.object(preflight, "GUIDE_SOCKET_ROOT", guide_socket_root),
                patch.object(
                    preflight,
                    "GUIDE_SOCKET_PATH",
                    guide_socket_root / "guide.sock",
                ),
                patch.object(preflight, "GUIDE_PARSER_UID", host_uid),
                patch.object(preflight, "GUIDE_PARSER_GID", host_gid),
                patch.object(preflight, "DOCKER_SOCKET", docker_socket),
                self.assertRaisesRegex(
                    preflight.PreflightError, "outside shared roots"
                ),
            ):
                preflight.validate_private_host_inputs(environment)
            environment["WORKSTREAM_PROJECT_AGENT_API_KEY_FILE"] = str(secret_paths[-1])
            socket_identity = socket_root / "negative-key.pem"
            socket_identity.write_text("private", encoding="utf-8")
            socket_identity.chmod(0o400)
            negative_key = (
                "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_NEGATIVE_PRIVATE_KEY_HOST_FILE"
            )
            original_negative_key = environment[negative_key]
            environment[negative_key] = str(socket_identity)
            with (
                patch.object(preflight, "SCRATCH_ROOT", scratch),
                patch.object(preflight, "SOCKET_ROOT", socket_root),
                patch.object(preflight, "GUIDE_SOCKET_ROOT", guide_socket_root),
                patch.object(
                    preflight,
                    "GUIDE_SOCKET_PATH",
                    guide_socket_root / "guide.sock",
                ),
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
                patch.object(preflight, "SCRATCH_ROOT", scratch),
                patch.object(preflight, "SOCKET_ROOT", socket_root),
                patch.object(preflight, "GUIDE_SOCKET_ROOT", guide_socket_root),
                patch.object(
                    preflight,
                    "GUIDE_SOCKET_PATH",
                    guide_socket_root / "guide.sock",
                ),
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
                patch.object(preflight, "SCRATCH_ROOT", scratch),
                patch.object(preflight, "SOCKET_ROOT", socket_root),
                patch.object(preflight, "GUIDE_SOCKET_ROOT", guide_socket_root),
                patch.object(
                    preflight,
                    "GUIDE_SOCKET_PATH",
                    guide_socket_root / "guide.sock",
                ),
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
                patch.object(preflight, "SCRATCH_ROOT", scratch),
                patch.object(preflight, "SOCKET_ROOT", socket_root),
                patch.object(preflight, "GUIDE_SOCKET_ROOT", guide_socket_root),
                patch.object(
                    preflight,
                    "GUIDE_SOCKET_PATH",
                    guide_socket_root / "guide.sock",
                ),
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
                with self.subTest(key=key, value=value), self.assertRaises(preflight.PreflightError):
                    preflight.validate_environment(changed)
        rendered = preflight.render_compose(self.environment_path, self.environment)
        for role in ("api", "worker"):
            changed = copy.deepcopy(rendered)
            for mount in changed["services"][role]["volumes"]:
                if mount["target"] == str(preflight.INTAKE_SOCKET_ROOT):
                    mount["read_only"] = False
            with self.subTest(role=role), self.assertRaises(preflight.PreflightError):
                preflight.validate_compose(changed, self.environment)

    def test_trusted_intake_health_uses_typed_factory_without_credentials(self) -> None:
        health = {"runtime": "smolvm", "isolation_mode": "smol-microvm",
                  "image_digest": self.environment[preflight.INTAKE_DIGEST_KEYS[0]],
                  "config_digest": self.environment[preflight.INTAKE_DIGEST_KEYS[1]]}
        with patch.object(preflight, "_run_json", return_value=health) as run:
            preflight.validate_trusted_intake(self.environment)
        command = run.call_args.args[0]
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
        "WORKSTREAM_DATABASE_URL_FILE": "WORKSTREAM_DATABASE_URL",
        "WORKSTREAM_CELERY_BROKER_URL_FILE": "WORKSTREAM_CELERY_BROKER_URL",
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE": (
            "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET"
        ),
        "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE": (
            "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET"
        ),
        "WORKSTREAM_PROJECT_AGENT_API_KEY_FILE": "OPENROUTER_API_KEY",
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
            "WORKSTREAM_PROJECT_AGENT_API_KEY_FILE",
        ),
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
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        file_names = {
            "WORKSTREAM_DATABASE_URL_FILE": "database",
            "WORKSTREAM_CELERY_BROKER_URL_FILE": "broker",
            "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE": "rate",
            "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE": "cursor",
            "WORKSTREAM_PROJECT_AGENT_API_KEY_FILE": "project-agent",
        }
        for variable, name in file_names.items():
            path = root / name
            if path.exists():
                path.chmod(0o600)
            path.write_text(content, encoding="utf-8")
            path.chmod(0o400)
            environment[variable] = str(path)
        if runtime == "manager_authored":
            environment.pop("WORKSTREAM_PROJECT_AGENT_API_KEY_FILE", None)
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
        expected = {self.FILE_TO_SECRET[key] for key in self.ROLE_FILES.get(role, ())}
        if role == "worker" and runtime == "manager_authored":
            expected.remove("OPENROUTER_API_KEY")
        if role == "worker" and provider == "openai":
            expected.remove("OPENROUTER_API_KEY")
            expected.add("OPENAI_API_KEY")
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
            ["/bin/sh", str(loader), sys.executable, "-c", program],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

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
                    if self.ROLE_FILES[role]:
                        missing = self._run_loader(
                            root,
                            role=role,
                            unset_selector=self.ROLE_FILES[role][0],
                        )
                        self.assertNotEqual(missing.returncode, 0)
                        self.assertIn(
                            "required secret file is unavailable", missing.stderr
                        )
            openai = self._run_loader(root, provider="openai")
            self.assertEqual(openai.returncode, 0, openai.stderr)
            unsupported = self._run_loader(root, provider="unknown")
            self.assertNotEqual(unsupported.returncode, 0)
            self.assertIn("model provider", unsupported.stderr)
            unknown = self._run_loader(root, role="unknown")
            self.assertNotEqual(unknown.returncode, 0)
            self.assertEqual(unknown.stdout, "")
            self.assertIn("release role is unavailable or unsupported", unknown.stderr)

    def test_loader_binds_runtime_to_sdk_marker_before_provider_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            omni = self._run_loader(
                root,
                runtime="omnicore_agent",
                sdk_environment="omnicore",
            )
            self.assertEqual(omni.returncode, 0, omni.stderr)
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
