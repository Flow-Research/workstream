"""Standalone POST image request/result framing tests."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from entrypoint import EntrypointError, decode_request, evaluate  # noqa: E402
from model_transport import CompletedModelCall, ModelCallUnavailable  # noqa: E402


CHECK = "solver_brief_and_extension_disclosure"


def request(check: str = CHECK) -> dict[str, object]:
    return {
        "request_digest": "sha256:" + "1" * 64,
        "registry": {
            "registry_entry_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001",
            "entry_digest": "sha256:" + "2" * 64,
            "resources": {"deadline_ms": 30_000},
        },
        "identity": {"phase": "post_submit"},
        "configuration": {"check": check},
        "input": {"requirement_id": check},
    }


class FakeSession:
    def __init__(self, *, unavailable: bool = False, **_kwargs: object) -> None:
        self.unavailable = unavailable
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def call(self, prompt: str, *, required_receipt_handles=()):
        self.calls += 1
        if self.unavailable:
            raise ModelCallUnavailable("model_budget_unavailable")
        value = json.loads(prompt)
        evidence_id = value["untrusted_evidence_data"]["evidence"][0]["evidence_id"]
        output = {
            "schema_version": "terminal_systems.model_assessment.v1",
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
        return CompletedModelCall(
            call_index=0,
            output=json.dumps(output),
            receipt_digest="sha256:" + "3" * 64,
            session_exhausted=True,
        )


class EntrypointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "instruction.md").write_text("Run tool.\n", encoding="utf-8")
        (self.root / "task.toml").write_text("format_version = 1\n", encoding="utf-8")
        (self.root / "AUTHOR_NOTES.md").write_text("Notes.\n", encoding="utf-8")
        (self.root / "workspace").mkdir()
        (self.root / "tests").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_strict_request_decoder_rejects_duplicates_constants_and_oversize(self):
        valid = json.dumps(request()).encode()
        duplicate = valid.replace(
            b'"configuration":', b'"configuration":{},"configuration":', 1
        )
        constant = valid.replace(b"30000", b"NaN", 1)
        for raw in (duplicate, constant, b"x" * (2 * 1024 * 1024 + 1)):
            with (
                self.subTest(raw=raw[:50]),
                self.assertRaisesRegex(EntrypointError, "invalid_request"),
            ):
                decode_request(raw)

    def test_static_model_member_emits_bound_pass_only_after_assessment(self):
        sessions = []

        def factory(**kwargs):
            value = FakeSession(**kwargs)
            sessions.append(value)
            return value

        result = evaluate(
            request(), material_root=self.root, model_session_factory=factory
        )
        self.assertEqual(
            (result["outcome"], result["verdict"]), ("completed", "passed")
        )
        self.assertEqual(sessions[0].calls, 1)
        self.assertEqual(result["request_digest"], request()["request_digest"])

    def test_model_unavailability_and_unknown_member_never_pass(self):
        unavailable = evaluate(
            request(),
            material_root=self.root,
            model_session_factory=lambda **kwargs: FakeSession(
                unavailable=True, **kwargs
            ),
        )
        self.assertEqual(unavailable["outcome"], "infrastructure_failed")
        self.assertEqual(unavailable["findings"], [])

        unknown = evaluate(
            request("unknown_check"),
            material_root=self.root,
            model_session_factory=FakeSession,
        )
        self.assertEqual(unknown["outcome"], "infrastructure_failed")
        self.assertEqual(unknown["infrastructure_failure_code"], "invalid_output")

    def test_wrong_typed_deadline_fails_closed(self):
        selected = request()
        selected["registry"]["resources"]["deadline_ms"] = True
        result = evaluate(
            selected,
            material_root=self.root,
            model_session_factory=FakeSession,
        )
        self.assertEqual(result["outcome"], "infrastructure_failed")
        self.assertEqual(result["infrastructure_failure_code"], "invalid_output")


if __name__ == "__main__":
    unittest.main()
