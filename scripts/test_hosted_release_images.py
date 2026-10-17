"""Counterexamples for the release-image evidence verifier."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from scripts import verify_hosted_release_images as proof


class ReleaseImageProofTests(unittest.TestCase):
    def setUp(self):
        self.source = {"app/main.py": "a" * 64, "uv.lock": "b" * 64}
        self.packages = {"openai-agents": "0.22.2", "jsonschema": "4.26.0"}
        self.loader = "c" * 64
        self.backend = {
            "source": self.source,
            "packages": self.packages,
            "loader": self.loader,
        }
        self.checker = {
            "status": 1,
            "stdout": "",
            "stderr": proof.CHECKER_ERROR,
            "docker": "Docker version 29.1.3, build proof\n",
            "binary": "d" * 64,
        }

    def test_valid_backend_allows_production_dev_overlap(self):
        proof.verify_backend(self.backend, self.source, self.packages, self.loader)

    def test_source_lock_loader_and_extra_file_substitutions_reject(self):
        for key in ("app/main.py", "uv.lock", "app/extra.py"):
            with self.subTest(key=key):
                altered = copy.deepcopy(self.backend)
                altered["source"][key] = "f" * 64
                with self.assertRaisesRegex(ValueError, "source inventory"):
                    proof.verify_backend(
                        altered, self.source, self.packages, self.loader
                    )
        altered = copy.deepcopy(self.backend)
        altered["loader"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "secret loader"):
            proof.verify_backend(altered, self.source, self.packages, self.loader)

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
                proof.verify_backend(altered, self.source, self.packages, self.loader)

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

    def test_loader_must_have_the_exact_nonwritable_executable_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            loader = Path(directory) / "loader"
            loader.write_text("loader")
            with (
                patch.object(proof, "LOADER", str(loader)),
                patch.object(proof.os, "getuid", return_value=10001),
                patch.object(proof, "checked", return_value=b""),
                patch.object(proof, "source_inventory", return_value={}),
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
            )
        }
        evidence.update(
            source_sha="b" * 40,
            tree_sha="c" * 40,
            backend_image_id="sha256:" + "d" * 64,
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


if __name__ == "__main__":
    unittest.main()
