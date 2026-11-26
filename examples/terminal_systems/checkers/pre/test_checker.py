"""Guide-derived intake checks, independent of named tasks or implementation language."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import checker


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name) / "package"
        shutil.copytree(Path(__file__).parent / "samples/valid", self.root)

    def change(self, old, new):
        path = self.root / "task.toml"
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def codes(self):
        return {finding["code"] for finding in checker.metadata(self.root)}

    def request(self, selected="metadata_contract"):
        return {
            "configuration": {"check": selected},
            "identity": {"phase": "pre_submit"},
            "request_digest": "sha256:" + "1" * 64,
            "registry": {
                "registry_entry_id": "00000000-0000-7000-8000-000000000001",
                "entry_digest": "sha256:" + "2" * 64,
            },
        }

    def test_valid_layout_accepts_extra_material(self):
        (self.root / "data").mkdir()
        (self.root / "data/input.csv").write_text("id,value\n1,3\n")
        self.assertEqual(checker.layout(self.root), [])

    def test_missing_and_wrong_type_are_actionable(self):
        (self.root / "instruction.md").unlink()
        findings = checker.layout(self.root)
        self.assertEqual(
            [(f["code"], f["path"]) for f in findings],
            [("layout_missing_required_file", "instruction.md")],
        )
        (self.root / "instruction.md").mkdir()
        self.assertEqual(
            [f["code"] for f in checker.layout(self.root)], ["layout_wrong_entry_type"]
        )

    def test_directory_required_even_without_files(self):
        shutil.rmtree(self.root / "workspace")
        self.assertEqual(
            [f["code"] for f in checker.layout(self.root)],
            ["layout_missing_required_directory"],
        )
        (self.root / "workspace").mkdir()
        self.assertEqual(checker.layout(self.root), [])

    def test_wrapped_archive(self):
        wrapper = self.root.parent / "wrapped"
        wrapper.mkdir()
        shutil.move(str(self.root), wrapper / "anything")
        codes = {f["code"] for f in checker.layout(wrapper)}
        self.assertEqual(
            codes,
            {
                "layout_missing_required_file",
                "layout_missing_required_directory",
                "layout_wrapped_archive",
            },
        )

    def test_dot_root_and_arbitrary_subject_and_linux_platform(self):
        self.assertEqual(checker.metadata(self.root), [])
        self.change('id = "portable-intake-example"', 'id = "new-language-tool-73"')
        self.change('platform = "linux/amd64"', 'platform = "linux/riscv64"')
        with (self.root / "task.toml").open("a") as handle:
            handle.write('\n[extensions]\ncustom_tool = "new-tool"\n')
        self.assertEqual(checker.metadata(self.root), [])

    def test_parent_absolute_and_wrong_type_paths(self):
        for value in ("../package", "/tmp", "C:\\private", "instruction.md"):
            with self.subTest(value=value):
                self.assertFalse(checker.contained_path(self.root, value, "directory"))
        self.assertFalse(checker.contained_path(self.root, ".", "file"))
        self.change(
            'dockerfile = "environment/Dockerfile"', 'dockerfile = "environment"'
        )
        self.assertEqual(self.codes(), {"metadata_unsafe_path"})

    def test_links_do_not_escape_verified_tree(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "Dockerfile").write_text("not submitted")
        (self.root / "outside").symlink_to(outside, target_is_directory=True)
        self.assertFalse(
            checker.contained_path(self.root, "outside/Dockerfile", "file")
        )
        (self.root / "task.toml").unlink()
        (self.root / "task.toml").symlink_to(outside / "Dockerfile")
        self.assertEqual(self.codes(), {"metadata_invalid_format"})

    def test_metadata_rejects_noncanonical_path_aliases(self):
        path = self.root / "task.toml"
        original = path.read_text()
        for alias in (
            "./environment/Dockerfile",
            "environment/./Dockerfile",
            "environment//Dockerfile",
            "environment/Dockerfile/",
        ):
            with self.subTest(alias=alias):
                path.write_text(original.replace("environment/Dockerfile", alias))
                self.assertEqual(self.codes(), {"metadata_unsafe_path"})

    def test_metadata_rejects_undeclared_nested_fields(self):
        path = self.root / "task.toml"
        original = path.read_text()
        for table in ("environment", "reference", "verification", "resources"):
            with self.subTest(table=table):
                path.write_text(
                    original.replace(f"[{table}]", f'[{table}]\nundeclared = "value"')
                )
                self.assertEqual(self.codes(), {"metadata_invalid_format"})
        path.write_text(original + '\n[extensions.custom]\nextra = "allowed"\n')
        self.assertEqual(checker.metadata(self.root), [])

    def test_version_bool_and_zero_resource_are_not_integers(self):
        self.change("format_version = 1", "format_version = true")
        self.change("cpu_millis = 1000", "cpu_millis = 0")
        self.assertEqual(self.codes(), {"metadata_missing_required_value"})

    def test_commands_are_arrays_and_are_never_executed(self):
        marker = self.root / "executed"
        self.change(
            'command = ["sh", "tests/run.sh"]',
            f'command = ["sh", "-c", "touch {marker}"]',
        )
        self.assertEqual(checker.metadata(self.root), [])
        self.assertFalse(marker.exists())
        self.change(
            f'command = ["sh", "-c", "touch {marker}"]', 'command = "sh tests/run.sh"'
        )
        self.assertEqual(self.codes(), {"metadata_invalid_argument_array"})

    def test_empty_argument_is_valid_but_empty_program_is_not(self):
        self.change('command = ["sh", "tests/run.sh"]', 'command = ["tool", ""]')
        self.assertEqual(checker.metadata(self.root), [])
        self.change('command = ["tool", ""]', 'command = [""]')
        self.assertEqual(self.codes(), {"metadata_invalid_argument_array"})

    def test_unknown_top_level_and_scalar_extensions(self):
        self.change(
            "format_version = 1",
            'format_version = 1\nunknown = "not declared"\nextensions = 3',
        )
        self.assertEqual(self.codes(), {"metadata_invalid_format"})

    def test_malformed_and_non_utf8_toml(self):
        for content in (b"[[", b"\xff"):
            (self.root / "task.toml").write_bytes(content)
            self.assertEqual(self.codes(), {"metadata_invalid_format"})

    def test_capacity_is_infrastructure_not_a_size_rule(self):
        with patch.object(checker, "METADATA_READ_CAPACITY", 2):
            result = checker.evaluate(self.request(), self.root)
        self.assertEqual(result["outcome"], "infrastructure_failed")
        self.assertEqual(result["infrastructure_failure_code"], "capacity_exceeded")
        self.assertIsNone(result["verdict"])
        self.assertEqual(result["findings"], [])

    def test_wrong_configuration_and_missing_material_cannot_pass(self):
        for request in (
            self.request("unknown"),
            self.request()
            | {"configuration": {"check": "metadata_contract", "ignore": True}},
        ):
            self.assertEqual(
                checker.evaluate(request, self.root)["outcome"], "infrastructure_failed"
            )
        self.assertEqual(
            checker.evaluate(self.request(), self.root / "absent")[
                "infrastructure_failure_code"
            ],
            "material_unavailable",
        )

    def test_result_hash_and_exact_request_identity(self):
        request = self.request()
        result = checker.evaluate(request, self.root)
        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(result["request_digest"], request["request_digest"])
        self.assertEqual(
            result["registry_entry_id"], request["registry"]["registry_entry_id"]
        )
        body = deepcopy(result)
        digest = body.pop("result_digest")
        encoded = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        self.assertEqual(digest, "sha256:" + hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    unittest.main()
