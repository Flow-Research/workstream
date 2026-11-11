"""The storage-key example must not exempt noncanonical public API routes."""

import unittest

from scripts.check_stale_authorization_docs import RULES, exempt_match
from scripts.check_stale_review_contracts import scan_text


class SubmissionSpecWordingTests(unittest.TestCase):
    def test_only_the_exact_storage_key_line_is_exempt(self):
        rule = next(item for item in RULES if item.code == "NON_CANONICAL_API_PREFIX")
        key = "submission-source/v1/<operation_uuid>/bundle.zip"
        for path, line, expected in (
            ("docs/spec_submission_execution.md", key, True),
            ("docs/other.md", key, False),
            ("docs/spec_submission_execution.md", "POST /v1/tasks", False),
            ("docs/spec_submission_execution.md", key + " POST /v1/tasks", False),
            ("docs/spec_submission_execution.md", "/v1/submission-source", False),
        ):
            with self.subTest(path=path, line=line):
                matches = list(rule.pattern.finditer(line))
                self.assertTrue(matches)
                for match in matches:
                    self.assertEqual(exempt_match(path, rule, line, match.start()), expected)
                failures = scan_text(path, line)
                self.assertEqual(bool(failures), not expected)


if __name__ == "__main__":
    unittest.main()
