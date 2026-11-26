"""Reject false evidence in the drill; these tests do not certify product APIs."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.pilot04_external_checker_runtime.guide_evidence import verify_source_commitment
from experiments.pilot04_external_checker_runtime import guide_polling


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.examples = [{"content": "Repair the worker", "title": None, "labels": []},
                         {"content": "Inspect another fault", "title": "Example", "labels": ["python"]}]
        self.expected = dict(examples=self.examples, examples_hash="sha256:" + "a" * 64,
                             source_hash="sha256:" + "b" * 64)
        self.source = dict(task_examples=deepcopy(self.examples),
                           task_examples_hash=self.expected["examples_hash"],
                           manifest_json={"task_examples_hash": self.expected["examples_hash"],
                                          "task_examples_count": 2},
                           bundle_hash=self.expected["source_hash"])
        self.expected.update(source_id="source-1", original_sha256="sha256:" + "e" * 64,
                             accesses=[{"source_snapshot_id": "source-1", "sha256": "sha256:" + "e" * 64,
                                        "manifest_sha256": "sha256:" + "f" * 64,
                                        "access_method": "trusted_parser", "operation": "read"}])
        self.attempt = {"canonical_input_hash": "sha256:" + "c" * 64,
                        "compiled_input_hash": "sha256:" + "c" * 64,
                        "source_snapshot_hash": self.expected["source_hash"],
                        "source_snapshot_id": "source-1", "guide_material_hash": "sha256:" + "f" * 64,
                        "status": "compilation_persisted"}

    def test_control_and_each_independent_source_substitution(self):
        verify_source_commitment(self.source, self.attempt, **self.expected)
        for field, value in (("task_examples", list(reversed(self.examples))),
                             ("task_examples_hash", "sha256:" + "d" * 64),
                             ("bundle_hash", "sha256:" + "d" * 64)):
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, "source commitment"):
                verify_source_commitment(self.source | {field: value}, self.attempt, **self.expected)
        for field, value in (("task_examples_hash", "sha256:" + "d" * 64),
                             ("task_examples_count", 1)):
            changed = deepcopy(self.source)
            changed["manifest_json"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, "source commitment"):
                verify_source_commitment(changed, self.attempt, **self.expected)

    def test_correct_storage_cannot_hide_different_worker_inputs(self):
        for field in ("canonical_input_hash", "compiled_input_hash", "source_snapshot_hash",
                      "source_snapshot_id", "status"):
            changed = self.attempt | {field: "foreign"}
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, "worker input"):
                verify_source_commitment(self.source, changed, **self.expected)
        for field in ("source_snapshot_id", "sha256", "manifest_sha256", "access_method", "operation"):
            changed = deepcopy(self.expected)
            changed["accesses"][0][field] = "foreign"
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, "original-read"):
                verify_source_commitment(self.source, self.attempt, **changed)
        with self.assertRaisesRegex(AssertionError, "original-read"):
            verify_source_commitment(self.source, self.attempt, **(self.expected | {"accesses": []}))


class SetupPollingTests(unittest.IsolatedAsyncioTestCase):
    async def read(self, call):
        with patch.object(guide_polling.asyncio, "sleep", new_callable=AsyncMock):
            return await guide_polling.wait_for_guide_read(
                None, "/same-setup", "local-token", lambda value: value["status"] == "policy_draft_ready", call,
            )

    async def test_inflight_unresolved_is_observed_without_retry_or_success(self):
        ready = {"status": "policy_draft_ready", "error_code": None}
        call = AsyncMock(side_effect=[
            {"status": "dispatch_pending", "error_code": "provider_outcome_unresolved"}, ready,
        ])
        self.assertEqual(await self.read(call), ready)
        self.assertEqual(call.await_count, 2)
        self.assertTrue(all(item.args == (None, "GET", "/same-setup", "local-token", 200)
                            for item in call.await_args_list))

    async def test_uncertainty_never_becomes_success_at_deadline(self):
        call = AsyncMock(return_value={"status": "dispatch_pending", "current_step": "queued",
                                       "error_code": "provider_outcome_unresolved", "setup_generation": 2,
                                       "error_summary": "private guide contents"})
        with self.assertRaisesRegex(AssertionError, "did not reach.*dispatch_pending.*generation=2") as fault:
            await self.read(call)
        self.assertNotIn("private guide contents", str(fault.exception))
        self.assertEqual(call.await_count, 120)

    async def test_terminal_errors_and_http_failure_are_not_hidden(self):
        call = AsyncMock(return_value={"status": "failed", "error_code": "schema_invalid"})
        with self.assertRaisesRegex(AssertionError, "schema_invalid"):
            await self.read(call)
        self.assertEqual(call.await_count, 1)
        unavailable = AsyncMock(side_effect=RuntimeError("503/service_unavailable"))
        with self.assertRaisesRegex(RuntimeError, "503/service_unavailable"):
            await self.read(unavailable)
        self.assertEqual(unavailable.await_count, 1)


if __name__ == "__main__":
    unittest.main()
