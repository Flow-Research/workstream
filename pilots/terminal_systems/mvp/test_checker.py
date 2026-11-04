"""Behavior and failure boundaries of the standalone incident summary checker."""

from pathlib import Path
import hashlib
import importlib.util
import shutil
import tempfile
import unittest

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("mvp_checker", ROOT / "checker.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def request(phase):
    check = checker.CHECKS[phase]
    return {
        "schema_version": "external_checker_request.v1",
        "request_digest": "sha256:" + "0" * 64,
        "registry": {
            "registry_entry_id": "019a14ee-5f61-7f21-8dd8-11d4d41a0001",
            "entry_digest": "sha256:" + "1" * 64,
        },
        "identity": {"phase": phase},
        "configuration": {"check": check},
        "input": {
            "requirement_id": "terminal."
            + ("pre" if phase == "pre_submit" else "post")
            + "."
            + check
        },
    }


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copyfile(ROOT / "events.jsonl", self.root / "events.jsonl")

    def summary(self, kind):
        shutil.copyfile(
            ROOT / "fixtures" / kind / "summary.json", self.root / "summary.json"
        )

    def test_missing_summary_is_pre_failure(self):
        result = checker.evaluate(request("pre_submit"), self.root)
        self.assertEqual(
            (result["phase"], result["outcome"], result["verdict"]),
            ("pre_submit", "completed", "failed"),
        )
        self.assertEqual([x["code"] for x in result["findings"]], ["summary_missing"])

    def test_malformed_required_files_fail_pre(self):
        for name, code in (("events.jsonl", "events_invalid"), ("summary.json", "summary_invalid")):
            with self.subTest(name=name):
                shutil.copyfile(ROOT / "events.jsonl", self.root / "events.jsonl")
                self.summary("correct")
                (self.root / name).write_text("{not valid JSON}")
                result = checker.evaluate(request("pre_submit"), self.root)
                self.assertEqual((result["outcome"], result["verdict"]), ("completed", "failed"))
                self.assertEqual([x["code"] for x in result["findings"]], [code])

    def test_structurally_valid_wrong_summary_fails_only_post(self):
        self.summary("incorrect")
        self.assertEqual(
            checker.evaluate(request("pre_submit"), self.root)["verdict"], "passed"
        )
        post = checker.evaluate(request("post_submit"), self.root)
        self.assertEqual(post["verdict"], "failed")
        self.assertEqual([x["code"] for x in post["findings"]], ["counts_incorrect"])

    def test_corrected_summary_passes(self):
        self.summary("correct")
        post = checker.evaluate(request("post_submit"), self.root)
        self.assertEqual(post["verdict"], "passed")
        self.assertEqual(post["findings"], [])
        body = {k: v for k, v in post.items() if k != "result_digest"}
        self.assertEqual(
            post["result_digest"],
            "sha256:" + hashlib.sha256(checker.canonical(body).encode()).hexdigest(),
        )

    def test_tampered_but_well_formed_input_fails_post(self):
        self.summary("correct")
        (self.root / "events.jsonl").write_text(
            (ROOT / "events.jsonl")
            .read_text()
            .replace('"worker","status":"error"', '"worker","status":"ok"', 1)
        )
        self.assertEqual(
            checker.evaluate(request("pre_submit"), self.root)["verdict"], "passed"
        )
        self.assertEqual(
            [
                x["code"]
                for x in checker.evaluate(request("post_submit"), self.root)["findings"]
            ],
            ["events_changed"],
        )

    def test_unsafe_path_and_malformed_request_fail_closed(self):
        self.summary("correct")
        (self.root / "summary.json").unlink()
        (self.root / "summary.json").symlink_to(ROOT / "fixtures/correct/summary.json")
        result = checker.evaluate(request("post_submit"), self.root)
        self.assertEqual(
            (
                result["outcome"],
                result["verdict"],
                result["infrastructure_failure_code"],
            ),
            ("infrastructure_failed", None, "material_unavailable"),
        )
        bad = request("post_submit")
        bad["configuration"] = {"check": "../summary.json"}
        with self.assertRaises(checker.InvalidRequest):
            checker.evaluate(bad, self.root)
        with self.assertRaises(ValueError):
            checker.decode(b'{"x":1,"x":2}')
        bad_digest = request("post_submit")
        bad_digest["request_digest"] = "sha256:" + "z" * 64
        with self.assertRaises(checker.InvalidRequest):
            checker.evaluate(bad_digest, self.root)
        bad_registry = request("post_submit")
        bad_registry["registry"]["entry_digest"] = "sha256:" + "z" * 64
        with self.assertRaises(checker.InvalidRequest):
            checker.evaluate(bad_registry, self.root)


if __name__ == "__main__":
    unittest.main()
