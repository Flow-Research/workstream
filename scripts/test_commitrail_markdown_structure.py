"""Regression tests for non-live Markdown in current Commitrail structures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_commitrail_records as gate


class CommitrailMarkdownStructureTests(unittest.TestCase):
    RECORD_PATH = ".commitrail/initiatives/WS-EXAMPLE-001/WS-EXAMPLE-001-01.md"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._write(
            ".commitrail/CHANGE_TEMPLATE.md",
            "# <Change ID> — <Outcome>\n\n- [ ] `<observable result>`\n",
        )
        self._write(
            ".commitrail/INDEX.md",
            "| Initiative | Durable disposition | Next |\n"
            "|---|---|---|\n"
            "| [WS-EXAMPLE-001](initiatives/WS-EXAMPLE-001/OVERVIEW.md) "
            "| Planned | Next |\n",
        )
        self._write(
            ".commitrail/initiatives/WS-EXAMPLE-001/OVERVIEW.md",
            "# Example\n\n- Disposition: Planned\n",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    @staticmethod
    def _record(evidence: str = "Observed proof.") -> str:
        return (
            "# WS-EXAMPLE-001-01 — Example\n\n"
            "- Durable disposition: Planned\n"
            "- Intended merge outcome: Example is bounded.\n\n"
            "## Intent\nSmall intent.\n\n"
            "## Bounded change\nSmall scope.\n\n"
            "## Acceptance criteria\n- [ ] Future behavior.\n\n"
            "## Risk and review routing\n- Risk: L1.\n\n"
            f"## Evidence\n{evidence}\n"
        )

    def _validate(self) -> None:
        with patch.object(gate, "tracked_legacy_paths", return_value=[]):
            gate.validate(
                self.root,
                ["backend/app/example.py", self.RECORD_PATH],
            )

    def test_fenced_overview_disposition_does_not_count(self) -> None:
        self._write(
            ".commitrail/initiatives/WS-EXAMPLE-001/OVERVIEW.md",
            "# Example\n\n```markdown\n- Disposition: Planned\n```\n",
        )
        with self.assertRaisesRegex(gate.CommitrailError, "DISPOSITION_INVALID"):
            self._validate()

    def test_commented_record_fields_do_not_count(self) -> None:
        for closing in ("-->", ""):
            with self.subTest(closing=closing):
                self._write(self.RECORD_PATH, f"<!--\n{self._record()}\n{closing}")
                with self.assertRaisesRegex(
                    gate.CommitrailError, "DISPOSITION_INVALID"
                ):
                    self._validate()

    def test_commented_overview_disposition_does_not_count(self) -> None:
        self._write(
            ".commitrail/initiatives/WS-EXAMPLE-001/OVERVIEW.md",
            "# Example\n<!--\n- Disposition: Planned\n-->\n",
        )
        with self.assertRaisesRegex(gate.CommitrailError, "DISPOSITION_INVALID"):
            self._validate()

    def test_commented_index_row_does_not_count(self) -> None:
        index = self.root / ".commitrail/INDEX.md"
        self._write(".commitrail/INDEX.md", f"<!--\n{index.read_text()}\n-->")
        with self.assertRaisesRegex(gate.CommitrailError, "INDEX_ROW_INVALID"):
            self._validate()

    def test_commented_merge_outcome_does_not_count(self) -> None:
        self._write(
            self.RECORD_PATH,
            self._record().replace(
                "- Intended merge outcome: Example is bounded.\n",
                "<!--\n- Intended merge outcome: Example is bounded.\n-->\n",
            ),
        )
        with self.assertRaisesRegex(gate.CommitrailError, "FIELD_MISSING"):
            self._validate()

    def test_commented_required_heading_does_not_count(self) -> None:
        self._write(
            self.RECORD_PATH,
            self._record().replace(
                "## Intent\nSmall intent.", "<!--\n## Intent\nSmall intent.\n-->"
            ),
        )
        with self.assertRaisesRegex(gate.CommitrailError, "FIELD_MISSING"):
            self._validate()

    def test_comment_only_section_body_is_empty(self) -> None:
        self._write(self.RECORD_PATH, self._record("<!-- Not visible evidence. -->"))
        with self.assertRaisesRegex(gate.CommitrailError, "FIELD_EMPTY"):
            self._validate()

    def test_comment_mask_preserves_offsets_and_live_evidence(self) -> None:
        record = self._record("<!-- hidden -->\n```bash\npython verify.py\n```")
        record = "<!--\n## Evidence\n```ignored fence\n-->\n" + record
        structure = gate._markdown_structure(record, self.RECORD_PATH)
        self.assertEqual(len(structure), len(record))
        self.assertEqual(structure.rfind("## Evidence"), record.rfind("## Evidence"))
        self._write(self.RECORD_PATH, record)
        self._validate()

    def test_fenced_index_row_does_not_count(self) -> None:
        self._write(
            ".commitrail/INDEX.md",
            "| Initiative | Durable disposition | Next |\n"
            "|---|---|---|\n"
            "   ~~~~markdown\n"
            "| [WS-EXAMPLE-001](initiatives/WS-EXAMPLE-001/OVERVIEW.md) "
            "| Planned | Next |\n"
            "   ~~~~\n",
        )
        with self.assertRaisesRegex(gate.CommitrailError, "INDEX_ROW_INVALID"):
            self._validate()

    def test_fenced_merge_outcome_does_not_count(self) -> None:
        record = self._record().replace(
            "- Intended merge outcome: Example is bounded.\n",
            "```markdown\n- Intended merge outcome: Impersonated.\n```\n",
        )
        self._write(self.RECORD_PATH, record)
        with self.assertRaisesRegex(gate.CommitrailError, "FIELD_MISSING"):
            self._validate()

    def test_fenced_required_headings_do_not_count(self) -> None:
        record = (
            "# WS-EXAMPLE-001-01 — Example\n\n"
            "- Durable disposition: Planned\n"
            "- Intended merge outcome: Example is bounded.\n\n"
            "```markdown\n"
            "## Intent\nFake.\n"
            "## Bounded change\nFake.\n"
            "## Acceptance criteria\nFake.\n"
            "## Risk and review routing\nFake.\n"
            "## Evidence\nFake.\n"
            "```\n"
        )
        self._write(self.RECORD_PATH, record)
        with self.assertRaisesRegex(gate.CommitrailError, "FIELD_MISSING"):
            self._validate()

    def test_real_evidence_section_accepts_fenced_command_content(self) -> None:
        evidence = (
            "```bash\n"
            "python3 -m unittest scripts.test_example\n"
            "## Intent\n"
            "- Intended merge outcome: This is command output, not structure.\n"
            "- CI: pending\n"
            "`<observable result>`\n"
            "````"
        )
        self._write(self.RECORD_PATH, self._record(evidence))
        self._validate()

    def test_comment_syntax_inside_fence_remains_literal_evidence(self) -> None:
        for literal in (
            "rg '<!--' docs",
            "<div><!-- literal sample\n</div>",
            "<!-- closed -->",
        ):
            with self.subTest(literal=literal):
                evidence = f"```html\n{literal}\n```"
                record = self._record(evidence)
                structure, visible = gate._markdown_views(record, self.RECORD_PATH)
                self.assertEqual(len(structure), len(record))
                self.assertIn(literal, visible)
                self.assertNotIn(literal, structure)
                self._write(self.RECORD_PATH, record)
                self._validate()

    def test_real_comment_after_literal_fence_cannot_supply_outcome(self) -> None:
        record = self._record().replace(
            "- Intended merge outcome: Example is bounded.\n",
            "```html\n<!-- literal\n```\n"
            "<!--\n- Intended merge outcome: Concealed.\n-->\n",
        )
        self._write(self.RECORD_PATH, record)
        with self.assertRaisesRegex(gate.CommitrailError, "FIELD_MISSING"):
            self._validate()

    def test_inline_code_comment_opener_does_not_hide_later_sections(self) -> None:
        for literal in ("`<!--`", "`` ` <!-- ``", "`literal\n<!-- span`", r"\<!--"):
            with self.subTest(literal=literal):
                record = self._record().replace(
                    "Small intent.", f"Document {literal} syntax."
                )
                self._write(self.RECORD_PATH, record)
                self._validate()

    def test_real_comment_after_inline_code_cannot_supply_outcome(self) -> None:
        record = self._record().replace(
            "- Intended merge outcome: Example is bounded.\n",
            "Document `<!--` literally.\n<!--\n"
            "- Intended merge outcome: Concealed.\n-->\n",
        )
        self._write(self.RECORD_PATH, record)
        with self.assertRaisesRegex(gate.CommitrailError, "FIELD_MISSING"):
            self._validate()

    def test_unmatched_backtick_does_not_disable_real_comment(self) -> None:
        record = self._record().replace(
            "- Intended merge outcome: Example is bounded.\n",
            "An unmatched ` delimiter.\n<!--\n"
            "- Intended merge outcome: Concealed.\n-->\n",
        )
        self._write(self.RECORD_PATH, record)
        with self.assertRaisesRegex(gate.CommitrailError, "FIELD_MISSING"):
            self._validate()

    def test_shorter_closing_fence_fails_closed(self) -> None:
        evidence = "````text\ncommand\n```"
        self._write(self.RECORD_PATH, self._record(evidence))
        with self.assertRaisesRegex(gate.CommitrailError, "FENCE_UNCLOSED"):
            self._validate()

    def test_invalid_backtick_fence_info_fails_closed(self) -> None:
        evidence = "```text`malformed\ncommand\n```"
        self._write(self.RECORD_PATH, self._record(evidence))
        with self.assertRaisesRegex(gate.CommitrailError, "FENCE_INVALID"):
            self._validate()


if __name__ == "__main__":
    unittest.main()
