"""Unit proof for the administrator drill's evidence checks, not API proof."""

import importlib.util
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
import httpx
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

DIRECTORY = Path(__file__).resolve().parents[1] / "backend/scripts"
sys.path.insert(0, str(DIRECTORY))
SPEC = importlib.util.spec_from_file_location("admin_api_drill", DIRECTORY / "admin_api_drill.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
guard_probe = __import__("admin_guard_probe")


def count_boundary(count):
    return count <= 1


def ambiguous_boundary(count):
    return count <= 1 or count <= 1


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    def test_grant_row_and_replay_proof_reject_field_and_timestamp_mutants(self):
        expected = {"grant_id": "known", "status": "active", "revoked_at": None}
        row = expected | {"granted_at": "2026-01-01T00:00:00+00:00"}
        self.assertTrue(module.one_grant_matches([row], expected))
        for rows in ([], [row, row], [row | {"unexpected": True}], [row | {"status": "revoked"}],
                     [{key: value for key, value in row.items() if key != "status"}]):
            self.assertFalse(module.one_grant_matches(rows, expected))
        from external_api_drill import verify_response
        history = {"items": [row | {"revoked_at": "2026-01-02T00:00:00+00:00"}], "total": 1, "next_cursor": None}
        verify_response(httpx.Response(200, json=history), 200, history)
        for field in ("granted_at", "revoked_at"):
            changed = deepcopy(history)
            changed["items"][0][field] = "2026-01-03T00:00:00+00:00"
            with self.subTest(field=field), self.assertRaises(module.ProbeFailure):
                verify_response(httpx.Response(200, json=changed), 200, history)

    def test_duplicate_setup_grant_cannot_shrink_expected_pagination_truth(self):
        instance = module.AuthorityDrill(SimpleNamespace(results=[]), None, {})
        rows = {}
        key = str(module.uuid4())
        instance.remember_grant("first", rows, key, {"role": "submitter"})
        for bad in (key, "not-a-uuid", None):
            with self.subTest(key=bad), self.assertRaises(module.ProbeFailure):
                instance.remember_grant("duplicate", rows, bad, {"role": "reviewer"})
            self.assertEqual(rows, {key: {"role": "submitter"}})
            self.assertEqual(instance.drill.results[-1]["result"], "failed")

    def test_guard_failure_report_preserves_only_allowlisted_codes(self):
        cases = [(ValueError(code), code) for code in guard_probe.FAILURE_CODES]
        cases += [(module.ProbeFailure("isolation_required"), "isolation_required"),
                  (ValueError("password=private-secret"), "guard_probe_failed"),
                  (RuntimeError("password=private-secret"), "guard_probe_failed")]
        for exc, expected in cases:
            async def fail(args):
                raise exc
            output = io.StringIO()
            with self.subTest(expected=expected, kind=type(exc).__name__), \
                 patch.object(guard_probe.argparse.ArgumentParser, "parse_args", return_value=SimpleNamespace()), \
                 patch.object(guard_probe, "probe", fail), redirect_stdout(output):
                self.assertEqual(guard_probe.main(), 1)
            self.assertEqual(json.loads(output.getvalue()), {
                "result": "infrastructure_failure", "error_kind": type(exc).__name__,
                "error_code": expected})
            self.assertNotIn("private-secret", output.getvalue())

    def test_guard_mutant_changes_only_one_boundary_without_changing_original(self):
        mutant = guard_probe.boundary_mutant(count_boundary)
        self.assertTrue(count_boundary(1))
        self.assertFalse(mutant(1))
        self.assertTrue(mutant(0))
        self.assertFalse(mutant(2))
        with self.assertRaisesRegex(ValueError, "mutation_target_not_unique"):
            guard_probe.boundary_mutant(ambiguous_boundary)

    def test_roster_has_twenty_distinct_actors(self):
        self.assertEqual(len(module.ROSTER), 20)
        self.assertEqual(len(set(module.ROSTER)), 20)
        self.assertIn("submitter_a", module.ROSTER)
        self.assertIn("reviewer_b", module.ROSTER)

    def test_two_winners_or_no_winner_cannot_pass_bootstrap(self):
        self.assertTrue(module.one_winner([0, 3]))
        self.assertTrue(module.one_winner([3, 0]))
        for outcomes in ([0, 0], [3, 3], [0, 1], [0], [0, 3, 3]):
            self.assertFalse(module.one_winner(outcomes))

    def test_duplicate_role_cannot_hide_behind_exact_set(self):
        items = [{"role": role} for role in module.ROLES]
        self.assertTrue(module.exact_role_list(items))
        self.assertFalse(module.exact_role_list(items + items[:1]))
        self.assertFalse(module.exact_role_list(items[:-1]))

    def test_failed_state_assertion_is_retained(self):
        drill = SimpleNamespace(results=[])
        instance = module.AuthorityDrill(drill, None, {})
        with self.assertRaises(module.ProbeFailure):
            instance.proof("forbidden_change", False)
        self.assertEqual(drill.results[0]["result"], "failed")

    async def test_denied_status_does_not_hide_changed_state(self):
        instance = module.AuthorityDrill(SimpleNamespace(results=[]), None, {})
        instance.call = AsyncMock(return_value={"error": {"code": "denied"}})
        instance.snapshot = AsyncMock(side_effect=[{"grants": []}, {"grants": ["unauthorized"]}])
        with self.assertRaises(module.ProbeFailure):
            await instance.deny("denied_but_wrote", "POST", "/example", "actor")
        self.assertEqual(instance.drill.results[-1]["result"], "failed")

    async def test_wrong_response_still_checks_state(self):
        instance = module.AuthorityDrill(SimpleNamespace(results=[]), None, {})
        instance.call = AsyncMock(side_effect=module.ProbeFailure("bad_status"))
        instance.snapshot = AsyncMock(return_value={"grants": []})
        with self.assertRaisesRegex(module.ProbeFailure, "bad_status"):
            await instance.deny("wrong_status", "POST", "/example", "actor")
        self.assertEqual(instance.snapshot.await_count, 2)


if __name__ == "__main__":
    unittest.main()
