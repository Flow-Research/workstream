"""Executable checker-core tests; provider callbacks remain test-only."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from checker import ModelCallUnavailable, execute


def request(check: str) -> dict:
    return {
        "request_digest": "sha256:" + "1" * 64,
        "registry": {
            "registry_entry_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001",
            "entry_digest": "sha256:" + "2" * 64,
        },
        "identity": {"phase": "post_submit"},
        "configuration": {"check": check},
        "input": {"requirement_id": check},
    }


class CheckerCoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "instruction.md").write_text("Run check.\n", encoding="utf-8")
        (self.root / "task.toml").write_text("format_version = 1\n", encoding="utf-8")
        (self.root / "AUTHOR_NOTES.md").write_text("No extension.\n", encoding="utf-8")
        (self.root / "workspace").mkdir()
        (self.root / "tests").mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def passing_assessment(self, prompt: str) -> str:
        value = json.loads(prompt)
        evidence_id = value["untrusted_evidence_data"]["evidence"][0]["evidence_id"]
        return json.dumps(
            {
                "schema_version": value["output_contract"]["schema_version"],
                "requirement_id": value["rubric"]["requirement_id"],
                "material_digest": value["untrusted_evidence_data"]["material_digest"],
                "conditions": [
                    {
                        "condition_number": item["condition_number"],
                        "status": "satisfied",
                        "evidence_ids": [evidence_id],
                        "finding_numbers": [],
                    }
                    for item in value["rubric"]["pass_conditions"]
                ],
                "findings": [],
            }
        )

    def test_actual_assessed_evidence_is_required_for_pass(self):
        result = execute(
            request("solver_brief_and_extension_disclosure"),
            self.root,
            self.passing_assessment,
        )
        self.assertEqual(
            (result["outcome"], result["verdict"]), ("completed", "passed")
        )

    def test_schema_only_or_unavailable_model_never_passes(self):
        selected = request("solver_brief_and_extension_disclosure")
        malformed = execute(selected, self.root, lambda _prompt: "{}")
        self.assertEqual(malformed["outcome"], "infrastructure_failed")
        self.assertEqual(malformed["infrastructure_failure_code"], "invalid_output")

        def unavailable(_prompt):
            raise ModelCallUnavailable("model_call_unavailable")

        missing = execute(selected, self.root, unavailable)
        self.assertEqual(missing["outcome"], "infrastructure_failed")
        self.assertEqual(missing["findings"], [])

    def test_request_binding_and_agent_only_checks_fail_closed_in_static_core(self):
        selected = request("solver_brief_and_extension_disclosure")
        selected["input"]["requirement_id"] = "difficulty_claim_evidence"
        invalid = execute(selected, self.root, self.passing_assessment)
        self.assertEqual(invalid["infrastructure_failure_code"], "invalid_output")

        delegated = execute(
            request("author_evidence_accuracy"), self.root, self.passing_assessment
        )
        self.assertEqual(delegated["infrastructure_failure_code"], "invalid_output")


if __name__ == "__main__":
    unittest.main()
