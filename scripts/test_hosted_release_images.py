"""Counterexamples for the release-image evidence verifier."""

import ast
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from scripts import verify_hosted_release_images as proof


class ReleaseImageProofTests(unittest.TestCase):
    def test_exported_shared_dependency_requires_exact_locked_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            (root / "backend/pyproject.toml").write_text('[project]\nname="workstream-backend"\nversion="0.1.0"\n')
            package = root / "packages/external-services"
            package.mkdir(parents=True)
            (package / "pyproject.toml").write_text('[project]\nname="workstream-external-services"\nversion="0.1.0"\n')
            lock = root / "backend/uv.lock"
            lock.write_text('[[package]]\nname="workstream-external-services"\nversion="0.1.0"\nsource={directory="../packages/external-services"}\n')
            with patch.object(proof, "checked", return_value=b"../packages/external-services ; python_version >= '3.11'\n"):
                self.assertEqual(proof.expected_packages(root, "agents"), {
                    "workstream-backend": "0.1.0", "workstream-external-services": "0.1.0",
                })
                lock.write_text(lock.read_text().replace('version="0.1.0"', 'version="0.2.0"'))
                with self.assertRaisesRegex(ValueError, "shared adapter lock differs"):
                    proof.expected_packages(root, "agents")
            with patch.object(proof, "checked", return_value=b"../packages/unapproved\n"):
                with self.assertRaises(ValueError):
                    proof.expected_packages(root, "agents")

    def test_installed_shared_adapter_bytes_remain_part_of_source_custody(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend, shared = root / "backend", root / "shared"
            (backend / "app").mkdir(parents=True)
            shared.mkdir()
            (backend / "app/main.py").write_text("# application\n")
            module = shared / "__init__.py"
            module.write_text("# shared adapter\n")
            with patch.object(proof, "SOURCE_PATHS", ("app",)):
                expected = proof.source_inventory(backend, shared)
                self.assertIn("shared-adapter/__init__.py", expected)
                actual = self.backend | {"source": expected}
                proof.verify_backend(actual, expected, self.packages, self.loader, "agents")
                mode = module.stat().st_mode
                module.write_text("# substituted adapter\n")
                self.assertEqual(module.stat().st_mode, mode)
                changed = self.backend | {"source": proof.source_inventory(backend, shared)}
                with self.assertRaisesRegex(ValueError, "source inventory differs"):
                    proof.verify_backend(changed, expected, self.packages, self.loader, "agents")

    def test_release_workflow_builds_and_verifies_both_sdk_environments(self):
        workflow = Path(".github/workflows/release-images.yml").read_text(
            encoding="utf-8"
        )
        built_backend_tags = set(
            re.findall(
                r"--file docker/backend/Dockerfile\.release "
                r"--tag (workstream-backend-[a-z]+-proof)",
                workflow,
            )
        )
        self.assertEqual(
            built_backend_tags,
            {
                "workstream-backend-agents-proof",
                "workstream-backend-omnicore-proof",
            },
        )
        for environment in ("agents", "omnicore"):
            self.assertEqual(
                workflow.count(
                    "--build-arg "
                    f"WORKSTREAM_PROJECT_AGENT_SDK_ENVIRONMENT={environment}"
                ),
                1,
            )
            self.assertEqual(
                workflow.count(f"--backend-{environment}-image"),
                1,
            )
        parser_image = re.search(
            r"scripts/verify_guide_parser_isolation\.py[\s\\]+"
            r"--expected-head \"\$SOURCE_SHA\"[\s\\]+"
            r"--backend-image ([a-z-]+)",
            workflow,
        )
        self.assertIsNotNone(parser_image)
        self.assertIn(parser_image.group(1), built_backend_tags)

    def test_helper_pins_match_runtime_download_and_image_verification(self):
        root = Path(__file__).resolve().parents[1]
        runtime = ast.parse(
            (root / "backend/app/adapters/artifacts/aws_roles_anywhere.py").read_text()
        )
        pins = [
            ast.literal_eval(node.value)
            for node in runtime.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "_AWS_SIGNING_HELPER_SHA256_BY_MACHINE"
                for target in node.targets
            )
        ]
        self.assertEqual(pins, [proof.ROLES_ANYWHERE_HELPER_SHA256])
        dockerfile = (root / "docker/backend/Dockerfile.release").read_text()
        self.assertIn("ARG WORKSTREAM_PROJECT_AGENT_SDK_ENVIRONMENT", dockerfile)
        self.assertIn(
            '--extra "${WORKSTREAM_PROJECT_AGENT_SDK_ENVIRONMENT}"', dockerfile
        )
        self.assertIn("/etc/workstream/project-agent-sdk-environment", dockerfile)
        downloads = re.findall(
            r"ADD --checksum=sha256:([0-9a-f]{64})\s+\\\n\s+"
            r"https://rolesanywhere\.amazonaws\.com/releases/[^/]+/"
            r"(X86_64|Aarch64)/Linux/Amzn2023/aws_signing_helper",
            dockerfile,
        )
        self.assertEqual(len(downloads), 2)
        machines = {"X86_64": "x86_64", "Aarch64": "aarch64"}
        self.assertEqual(
            {machines[architecture]: digest for digest, architecture in downloads},
            proof.ROLES_ANYWHERE_HELPER_SHA256,
        )

    def setUp(self):
        self.source = {"app/main.py": "a" * 64, "uv.lock": "b" * 64}
        self.packages = {"openai-agents": "0.22.2", "jsonschema": "4.26.0"}
        self.loader = "c" * 64
        self.backend = {
            "source": self.source,
            "packages": self.packages,
            "loader": self.loader,
            "roles_anywhere_helper": next(
                iter(proof.ROLES_ANYWHERE_HELPER_SHA256.values())
            ),
            "proof_command_timeout": True,
            "sdk_environment": "agents",
        }
        self.checker = {
            "status": 1,
            "stdout": "",
            "stderr": proof.CHECKER_ERROR,
            "docker": "Docker version 29.1.3, build proof\n",
            "binary": "d" * 64,
        }

    def test_valid_backend_allows_production_dev_overlap(self):
        proof.verify_backend(
            self.backend, self.source, self.packages, self.loader, "agents"
        )
        with self.assertRaisesRegex(ValueError, "SDK environment marker"):
            proof.verify_backend(
                self.backend, self.source, self.packages, self.loader, "omnicore"
            )

    def test_source_lock_loader_and_extra_file_substitutions_reject(self):
        for key in ("app/main.py", "uv.lock", "app/extra.py"):
            with self.subTest(key=key):
                altered = copy.deepcopy(self.backend)
                altered["source"][key] = "f" * 64
                with self.assertRaisesRegex(ValueError, "source inventory"):
                    proof.verify_backend(
                        altered, self.source, self.packages, self.loader, "agents"
                    )
        altered = copy.deepcopy(self.backend)
        altered["loader"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "secret loader"):
            proof.verify_backend(
                altered, self.source, self.packages, self.loader, "agents"
            )
        altered = copy.deepcopy(self.backend)
        altered["roles_anywhere_helper"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Roles Anywhere helper"):
            proof.verify_backend(
                altered, self.source, self.packages, self.loader, "agents"
            )
        altered = copy.deepcopy(self.backend)
        altered["proof_command_timeout"] = False
        with self.assertRaisesRegex(ValueError, "proof timeout command"):
            proof.verify_backend(
                altered, self.source, self.packages, self.loader, "agents"
            )

    def test_missing_agent_or_added_dev_only_package_rejects(self):
        for extra in (False, True):
            altered = copy.deepcopy(self.backend)
            if extra:
                altered["packages"]["pytest"] = "9.0.3"
            else:
                del altered["packages"]["openai-agents"]
            with (
                self.subTest(extra=extra),
                self.assertRaisesRegex(ValueError, "package closure"),
            ):
                proof.verify_backend(
                    altered, self.source, self.packages, self.loader, "agents"
                )

    def test_image_failure_diagnostics_never_expose_arbitrary_output(self):
        for stderr, expected in (
            (b"trace\nValueError: proof command failed\n", "dependency check failed"),
            (
                b"ValueError: duplicate canonical distribution\n",
                "duplicate package metadata",
            ),
            (b"ValueError: private sentinel", "unclassified failure"),
        ):
            result = SimpleNamespace(
                returncode=1, stdout=b"private sentinel", stderr=stderr
            )
            with (
                self.subTest(stderr=stderr),
                patch.object(proof, "run", return_value=result),
                patch.object(proof, "checked") as cleanup,
            ):
                with self.assertRaises(ValueError) as failure:
                    proof.inspect_image("fixture", "backend", "123-1")
                self.assertIn(expected, str(failure.exception))
                self.assertNotIn("private sentinel", str(failure.exception))
                self.assertEqual(
                    cleanup.call_args.args[0][:3], ["docker", "rm", "--force"]
                )

    def test_duplicate_distribution_and_canonical_alias_reject(self):
        for name in ("openai-agents", "openai_agents", "OpenAI.Agents"):
            distributions = [
                SimpleNamespace(metadata={"Name": "openai-agents"}, version="0.0.0"),
                SimpleNamespace(metadata={"Name": name}, version="0.22.2"),
            ]
            with (
                self.subTest(name=name),
                patch.object(
                    proof.importlib.metadata,
                    "distributions",
                    return_value=distributions,
                ),
                self.assertRaisesRegex(ValueError, "duplicate canonical"),
            ):
                proof.installed_packages()
        with patch.object(
            proof.importlib.metadata, "distributions", return_value=distributions[:1]
        ):
            self.assertEqual(proof.installed_packages(), {"openai-agents": "0.0.0"})

    def test_cleanup_is_owner_qualified_and_requires_absence(self):
        container = "a" * 64
        with patch.object(
            proof, "checked", side_effect=[(container + "\n").encode(), b"", b""]
        ) as commands:
            proof.cleanup_containers("123-1")
        self.assertEqual(
            commands.call_args_list[0].args[0][-1],
            "label=workstream.release-proof=123-1",
        )
        self.assertEqual(
            commands.call_args_list[1].args[0], ["docker", "rm", "--force", container]
        )
        self.assertEqual(commands.call_args_list[0], commands.call_args_list[2])
        with (
            patch.object(proof, "checked", side_effect=[b"", b"still present"]),
            self.assertRaisesRegex(ValueError, "remain"),
        ):
            proof.cleanup_containers("123-1")
        with (
            patch.object(proof, "checked") as commands,
            self.assertRaisesRegex(ValueError, "invalid proof owner"),
        ):
            proof.cleanup_containers("")
        commands.assert_not_called()

    def test_backend_entrypoint_accepts_neutral_parser_and_rejects_wrong_sdk(self):
        parser = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        mismatch = SimpleNamespace(
            returncode=1,
            stdout=b"",
            stderr=(
                b"project agent runtime does not match the installed SDK environment\n"
            ),
        )
        for sdk_environment, wrong_runtime in (
            ("agents", "omnicore_agent"),
            ("omnicore", "openai_agents_sdk"),
        ):
            with (
                self.subTest(sdk_environment=sdk_environment),
                patch.object(proof, "run", side_effect=[parser, mismatch]) as runs,
                patch.object(proof, "checked", return_value=b"") as cleanup,
            ):
                proof.verify_backend_entrypoint(
                    "sha256:" + "a" * 64, sdk_environment, "123-1"
                )
            parser_command = runs.call_args_list[0].args[0]
            mismatch_command = runs.call_args_list[1].args[0]
            self.assertIn("WORKSTREAM_RELEASE_ROLE=parser", parser_command)
            self.assertFalse(
                any(
                    value.startswith("WORKSTREAM_PROJECT_AGENT_RUNTIME=")
                    for value in parser_command
                )
            )
            self.assertIn("WORKSTREAM_RELEASE_ROLE=worker", mismatch_command)
            self.assertIn(
                f"WORKSTREAM_PROJECT_AGENT_RUNTIME={wrong_runtime}",
                mismatch_command,
            )
            self.assertEqual(cleanup.call_count, 2)

    def test_backend_entrypoint_smoke_rejects_changed_outcomes(self):
        failures = (
            SimpleNamespace(returncode=1, stdout=b"", stderr=b"private"),
            SimpleNamespace(returncode=0, stdout=b"private", stderr=b""),
        )
        for failure in failures:
            with (
                self.subTest(failure=failure),
                patch.object(proof, "run", return_value=failure),
                patch.object(proof, "checked", return_value=b""),
                self.assertRaisesRegex(ValueError, "entrypoint behavior differs"),
            ):
                proof.verify_backend_entrypoint("fixture", "agents", "123-1")

    def test_loader_must_have_the_exact_nonwritable_executable_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            loader = Path(directory) / "loader"
            loader.write_text("loader")
            with (
                patch.object(proof, "LOADER", str(loader)),
                patch.object(proof, "ROLES_ANYWHERE_HELPER", str(loader)),
                patch.object(proof.platform, "machine", return_value="x86_64"),
                patch.dict(
                    proof.ROLES_ANYWHERE_HELPER_SHA256,
                    {"x86_64": proof.file_hash(loader)},
                    clear=True,
                ),
                patch.object(proof.os, "getuid", return_value=10001),
                patch.object(proof, "checked", return_value=b""),
                patch.object(proof, "source_inventory", return_value={}),
                patch.object(
                    proof, "read_sdk_environment_marker", return_value="agents"
                ),
                patch.object(
                    proof.importlib.metadata, "distributions", return_value=[]
                ),
            ):
                loader.chmod(0o555)
                self.assertEqual(
                    proof.inside_backend()["loader"], proof.file_hash(loader)
                )
                for mode in (0o755, 0o444):
                    loader.chmod(mode)
                    with (
                        self.subTest(mode=mode),
                        self.assertRaisesRegex(ValueError, "loader mode"),
                    ):
                        proof.inside_backend()

    def test_helper_must_have_pinned_identity_and_nonwritable_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loader = root / "loader"
            helper = root / "aws_signing_helper"
            loader.write_bytes(b"loader")
            helper.write_bytes(b"helper")
            loader.chmod(0o555)
            helper.chmod(0o555)
            digest = proof.file_hash(helper)
            with (
                patch.object(proof, "LOADER", str(loader)),
                patch.object(proof, "ROLES_ANYWHERE_HELPER", str(helper)),
                patch.object(proof.platform, "machine", return_value="x86_64"),
                patch.dict(
                    proof.ROLES_ANYWHERE_HELPER_SHA256,
                    {"x86_64": digest},
                    clear=True,
                ),
                patch.object(proof.os, "getuid", return_value=10001),
                patch.object(proof, "checked", return_value=b""),
                patch.object(proof, "source_inventory", return_value={}),
                patch.object(
                    proof, "read_sdk_environment_marker", return_value="agents"
                ),
                patch.object(
                    proof.importlib.metadata, "distributions", return_value=[]
                ),
            ):
                self.assertEqual(
                    proof.inside_backend()["roles_anywhere_helper"], digest
                )
                helper.chmod(0o755)
                with self.assertRaisesRegex(ValueError, "helper mode"):
                    proof.inside_backend()
                helper.chmod(0o555)
                replacement = root / "replacement"
                replacement.write_bytes(b"HELPER")
                replacement.chmod(helper.stat().st_mode & 0o777)
                replacement.replace(helper)
                self.assertEqual(helper.stat().st_mode & 0o777, 0o555)
                self.assertNotEqual(proof.file_hash(helper), digest)
                with self.assertRaisesRegex(ValueError, "^helper identity changed$"):
                    proof.inside_backend()

    def test_backend_manifest_requires_the_proof_timeout_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loader = root / "loader"
            helper = root / "aws_signing_helper"
            loader.write_bytes(b"loader")
            helper.write_bytes(b"helper")
            loader.chmod(0o555)
            helper.chmod(0o555)
            with (
                patch.object(proof, "LOADER", str(loader)),
                patch.object(proof, "ROLES_ANYWHERE_HELPER", str(helper)),
                patch.object(proof, "PROOF_COMMAND_TIMEOUT", str(root / "missing")),
                patch.object(proof.platform, "machine", return_value="x86_64"),
                patch.dict(
                    proof.ROLES_ANYWHERE_HELPER_SHA256,
                    {"x86_64": proof.file_hash(helper)},
                    clear=True,
                ),
                patch.object(proof.os, "getuid", return_value=10001),
                self.assertRaisesRegex(ValueError, "proof timeout command"),
            ):
                proof.inside_backend()

    def test_checker_failure_must_be_exact_not_timeout_or_arbitrary_error(self):
        proof.verify_checker(self.checker)
        for key, value in (
            ("status", 124),
            ("status", 0),
            ("stderr", "loader failed\n"),
            ("stdout", "unexpected"),
            ("docker", "Docker version 1.0"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                proof.verify_checker({**self.checker, key: value})

    def test_metadata_cannot_substitute_user_or_entrypoint(self):
        info = {
            "Os": "linux",
            "Architecture": "amd64",
            "Id": "sha256:" + "a" * 64,
            "Config": {
                "User": "workstream",
                "Entrypoint": [proof.CHECKER],
                "Cmd": ["/etc/workstream/checker-service.json"],
            },
        }
        for role in ("checker", "backend"):
            if role == "backend":
                info["Config"].update(
                    Entrypoint=[proof.LOADER],
                    Cmd=[
                        "python",
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "8000",
                    ],
                )
            with patch.object(
                proof, "checked", return_value=json.dumps([info]).encode()
            ):
                self.assertEqual(proof.image_metadata("fixture", role), info["Id"])
            for key, value in (
                ("User", "root"),
                ("Entrypoint", ["/bin/true"]),
                ("Cmd", []),
            ):
                altered = copy.deepcopy(info)
                altered["Config"][key] = value
                with (
                    self.subTest(role=role, key=key),
                    patch.object(
                        proof, "checked", return_value=json.dumps([altered]).encode()
                    ),
                    self.assertRaises(ValueError),
                ):
                    proof.image_metadata("fixture", role)

    def test_inventory_rejects_links_and_detects_extra_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in proof.SOURCE_PATHS:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text("source")
            original = proof.source_inventory(root)
            (root / "scripts/schema_baseline_sql.py").write_text(
                "changed migration helper"
            )
            self.assertNotEqual(proof.source_inventory(root), original)
            (root / "app").unlink()
            (root / "app").mkdir()
            (root / "app/extra.py").write_text("extra")
            self.assertNotEqual(proof.source_inventory(root), original)
            (root / "app/link").symlink_to(root / "uv.lock")
            with self.assertRaisesRegex(ValueError, "symlink"):
                proof.source_inventory(root)

    def test_evidence_is_closed_and_never_overwrites_a_symlink_target(self):
        evidence = {
            key: "a" * 64
            for key in (
                "backend_source_sha256",
                "backend_lock_sha256",
                "checker_lock_sha256",
                "loader_sha256",
                "checker_binary_sha256",
                "roles_anywhere_helper_sha256",
            )
        }
        evidence.update(
            proof_scope="all-release-images",
            source_sha="b" * 40,
            tree_sha="c" * 40,
            backend_agents_image_id="sha256:" + "d" * 64,
            backend_omnicore_image_id="sha256:" + "f" * 64,
            checker_image_id="sha256:" + "e" * 64,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "evidence.json"
            proof.write_evidence(output, evidence)
            self.assertEqual(json.loads(output.read_text()), evidence)
            with self.assertRaisesRegex(ValueError, "shape"):
                proof.write_evidence(
                    root / "bad.json", {**evidence, "raw_log": "private"}
                )
            linked = root / "linked.json"
            linked.symlink_to(output)
            with self.assertRaises(OSError):
                proof.write_evidence(linked, evidence)
            self.assertEqual(json.loads(output.read_text()), evidence)

    def test_native_hosted_proves_both_backends_without_controller_image(self):
        head = "a" * 40
        for checker_image in (False, True):
            arguments = [
                "verify_hosted_release_images.py",
                "--scope",
                "native-hosted",
                "--expected-head",
                head,
                "--container-owner",
                "123-1",
                "--backend-agents-image",
                "agents",
                "--backend-omnicore-image",
                "omnicore",
                "--evidence",
                "/unused/evidence.json",
            ]
            if checker_image:
                arguments.extend(["--checker-image", "controller"])

            def checked(command):
                if command[:3] == ["git", "status", "--porcelain"]:
                    return b""
                return (head + "\n").encode()

            omnicore = self.backend | {"sdk_environment": "omnicore"}
            with (
                self.subTest(checker_image=checker_image),
                patch.object(sys, "argv", arguments),
                patch.object(proof, "checked", side_effect=checked),
                patch.object(proof, "source_inventory", return_value=self.source),
                patch.object(proof, "expected_packages", return_value=self.packages),
                patch.object(proof, "file_hash", return_value=self.loader),
                patch.object(
                    proof, "image_metadata", side_effect=lambda image, role: image
                ) as metadata,
                patch.object(
                    proof, "inspect_image", side_effect=[self.backend, omnicore]
                ) as inspect,
                patch.object(proof, "verify_backend_entrypoint") as entrypoint,
                patch.object(proof, "verify_checker") as checker,
                patch.object(proof, "write_evidence") as write,
            ):
                if checker_image:
                    with self.assertRaisesRegex(ValueError, "checker image"):
                        proof.main()
                    metadata.assert_not_called()
                    write.assert_not_called()
                    continue
                proof.main()
                self.assertEqual(metadata.call_args_list[0].args, ("agents", "backend"))
                self.assertEqual(
                    metadata.call_args_list[1].args, ("omnicore", "backend")
                )
                self.assertEqual(inspect.call_count, 2)
                self.assertEqual(entrypoint.call_count, 2)
                checker.assert_not_called()
                evidence = write.call_args.args[1]
                self.assertEqual(evidence["proof_scope"], "native-hosted")
                self.assertFalse(any(key.startswith("checker_") for key in evidence))

    def test_native_hosted_evidence_cannot_claim_controller_or_node_attestation(self):
        evidence = {
            "proof_scope": "native-hosted",
            "source_sha": "a" * 40,
            "tree_sha": "b" * 40,
            "backend_agents_image_id": "sha256:" + "c" * 64,
            "backend_omnicore_image_id": "sha256:" + "d" * 64,
            **{
                key: "e" * 64
                for key in (
                    "backend_source_sha256",
                    "backend_lock_sha256",
                    "loader_sha256",
                    "roles_anywhere_helper_sha256",
                )
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            proof.write_evidence(path, evidence)
            self.assertEqual(json.loads(path.read_text()), evidence)
            for key in ("checker_image_id", "native_service_sha256", "guest_sha256"):
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, "shape"):
                    proof.write_evidence(
                        Path(directory) / "bad.json", evidence | {key: "f" * 64}
                    )


if __name__ == "__main__":
    unittest.main()
