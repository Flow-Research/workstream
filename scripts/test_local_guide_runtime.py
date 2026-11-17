"""Local guide parsing must retain the same isolation boundary as deployment."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import yaml

from scripts import verify_guide_parser_isolation as parser_proof

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters.project_agents import (  # noqa: E402
    build_project_guide_adapter_profile,
    create_project_guide_runtime,
)
from app.core.config import Settings  # noqa: E402
from app.core.project_agents import project_guide_runtime_configuration  # noqa: E402


class ParserProofCheckoutTests(unittest.TestCase):
    def test_read_only_inspection_handles_large_index_and_rejects_dirty_source(self):
        with tempfile.TemporaryDirectory(prefix="ws-parser-checkout-") as directory:
            root = Path(directory)

            def git(*arguments):
                return subprocess.check_output(
                    ["git", "-c", "core.hooksPath=/dev/null", *arguments],
                    cwd=root, stderr=subprocess.DEVNULL,
                ).decode().strip()

            git("init", "--quiet", "--template=")
            for number in range(1200):
                (root / f"{number:04d}-{'x' * 120}").touch()
            git("add", ".")
            git("-c", "user.name=Parser Proof", "-c", "user.email=proof@example.invalid",
                "commit", "--quiet", "-m", "Synthetic source")
            head = git("rev-parse", "HEAD")
            index = root / ".git/index"
            self.assertGreater(index.stat().st_size, parser_proof.OUTPUT_LIMIT)
            before = index.read_bytes()
            source = root / f"0000-{'x' * 120}"
            metadata = source.stat()
            os.utime(source, ns=(metadata.st_atime_ns, metadata.st_mtime_ns - 10**9))
            with chdir(root):
                self.assertEqual(parser_proof._source_checkout(head), head)
                self.assertEqual(index.read_bytes(), before)
                self.assertFalse((root / ".git/index.lock").exists())
                source.write_text("changed")
                with self.assertRaisesRegex(ValueError, "checkout is dirty"):
                    parser_proof._source_checkout(head)


class LocalGuideRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
        self.services = self.compose["services"]

    def test_parser_has_no_secrets_network_or_source_mount(self):
        parser = self.services["guide-document-parser"]
        self.assertEqual(parser["network_mode"], "none")
        self.assertEqual(parser["user"], "0:0")
        self.assertTrue(parser["read_only"])
        self.assertEqual(parser["cap_drop"], ["ALL"])
        self.assertEqual(parser["cap_add"], ["KILL", "SETGID", "SETUID"])
        self.assertEqual(parser["security_opt"], ["no-new-privileges:true"])
        self.assertFalse(parser.get("environment"))
        self.assertFalse(parser.get("secrets"))
        self.assertEqual(parser["volumes"], ["guide_parser_socket:/var/lib/workstream/guide-runtime"])
        self.assertEqual(parser["pids_limit"], 32)
        self.assertEqual(parser["mem_limit"], "512m")
        self.assertEqual(parser["cpus"], 1.0)
        self.assertIn("size=64m", parser["tmpfs"][0])
        self.assertIn("--healthcheck", parser["healthcheck"]["test"])

    def test_only_model_proxy_receives_provider_keys(self):
        for name in ("backend", "worker", "submission-finalizer", "beat", "guide-document-parser"):
            service = self.services[name]
            self.assertFalse(
                {"OPENAI_API_KEY", "OPENROUTER_API_KEY"} & set(service.get("environment", {})),
                name,
            )
            if name in {"backend", "beat"}:
                self.assertFalse(any("guide_parser_socket:" in mount for mount in service["volumes"]))
        proxy = self.services["model-proxy"]
        self.assertEqual(
            {"OPENAI_API_KEY", "OPENROUTER_API_KEY"}
            & set(proxy.get("environment", {})),
            {"OPENAI_API_KEY", "OPENROUTER_API_KEY"},
        )

    def test_worker_receives_readonly_parser_socket(self):
        worker = self.services["worker"]
        self.assertIn("10001", worker["group_add"])
        self.assertIn("guide_parser_socket:/var/lib/workstream/guide-runtime:ro", worker["volumes"])
        self.assertEqual(worker["depends_on"]["guide-document-parser"]["condition"], "service_healthy")

    def test_finalization_consumer_requires_explicit_positive_capacity(self):
        service = self.services["submission-finalizer"]
        self.assertEqual(service["profiles"], ["submission-intake"])
        self.assertIn("--queues=celery,workstream.outbox", self.services["worker"]["command"])
        # Compose turns escaped dollars into shell variables at container launch.
        script = service["command"][2].replace("$$", "$")
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "python"
            executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            executable.chmod(0o700)
            for value in ("", "0", "00", "-1", "1.5", "two", "2"):
                with self.subTest(value=value):
                    result = subprocess.run(["/bin/sh", "-ec", script], text=True, capture_output=True,
                        env={"PATH": directory, "WORKSTREAM_SUBMISSION_FINALIZATION_CONCURRENCY": value})
                    if value != "2":
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(result.stdout, "")
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        arguments = result.stdout.splitlines()
                        self.assertIn("--concurrency=2", arguments)
                        self.assertIn("--pool=prefork", arguments)
                        self.assertIn("--queues=workstream.submission_finalization", arguments)

    def test_images_create_private_directory_without_exposing_local_env(self):
        for name in ("dev", "release"):
            dockerfile = (ROOT / f"docker/backend/Dockerfile.{name}").read_text()
            self.assertIn("install -d -m 0750 -o 10002 -g 10001 /var/lib/workstream/guide-runtime", dockerfile)
        self.assertIn("backend/.env", (ROOT / ".dockerignore").read_text().splitlines())

    def test_rendered_default_model_tuple_constructs_registered_adapter(self):
        environment = os.environ.copy()
        environment.update({
            "COMPOSE_PROJECT_NAME": "guide-runtime-test",
            "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET": "test-only",
            "WORKSTREAM_MINIO_ROOT_USER": "test-only",
            "WORKSTREAM_MINIO_ROOT_PASSWORD": "test-only",
            "WORKSTREAM_DATABASE_URL": "postgresql+asyncpg://user:pass@postgres/test",
            "WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET": "test-only",
            "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET": "test-only",
            "WORKSTREAM_PROJECT_AGENT_RUNTIME_OPTIONS": "{}",
            "WORKSTREAM_POSTGRES_PASSWORD": "test-only",
        })
        for name in (
            "WORKSTREAM_PROJECT_AGENT_RUNTIME",
            "WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER",
            "WORKSTREAM_PROJECT_AGENT_MODEL_API",
            "WORKSTREAM_PROJECT_AGENT_MODEL",
        ):
            environment.pop(name, None)
        rendered = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.yml", "--profile", "backend",
             "config", "--format", "json"],
            cwd=ROOT, env=environment, text=True, capture_output=True, check=True,
        )
        services = json.loads(rendered.stdout)["services"]
        self.assertNotIn("submission-finalizer", services)
        worker = services["worker"]["environment"]
        settings = Settings(
            project_agent_runtime=worker["WORKSTREAM_PROJECT_AGENT_RUNTIME"],
            project_agent_model_provider=worker["WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER"],
            project_agent_model_api=worker["WORKSTREAM_PROJECT_AGENT_MODEL_API"],
            project_agent_model=worker["WORKSTREAM_PROJECT_AGENT_MODEL"],
            project_agent_runtime_options=json.loads(
                worker["WORKSTREAM_PROJECT_AGENT_RUNTIME_OPTIONS"]
            ),
        )
        configuration = project_guide_runtime_configuration(
            settings,
            adapter_profile_builder=lambda options: build_project_guide_adapter_profile(
                settings.project_agent_runtime, options
            ),
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}), patch(
            "app.adapters.project_agents.openai_agent_sdk."
            "require_openai_agents_sdk_adapter_profile",
            return_value=object(),
        ), patch.dict(sys.modules, {"agents": ModuleType("agents"), "openai": ModuleType("openai")}):
            runtime = create_project_guide_runtime(configuration)
        self.assertEqual(
            (configuration.runtime_key, configuration.model_provider,
             configuration.model_api, configuration.model),
            ("openai_agents_sdk", "openrouter", "chat_completions", "openai/gpt-5.6-terra"),
        )
        self.assertEqual(runtime.identity, configuration.adapter_identity)


if __name__ == "__main__":
    unittest.main()
