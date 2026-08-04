# WS-ART-001-04A2 External Review Response

## Comments addressed

- Hosted `shared_foundations` found two guide-OOXML regression failures after
  the neutral ZIP probe move. EOCD per-disk versus total entry-count mismatch
  was being classified as multi-disk before the existing guide layer could
  preserve its stable `ooxml_directory_conflict` and `ooxml_zip64` outcomes.
- The neutral probe now reserves `multi-disk` for non-zero disk identifiers,
  preserves the existing guide classification order, and retains submission
  exact-record validation separately.
- CodeRabbit's completed correction-head review identified three valid small
  fixes: align the ingest activation ledger, enforce inspection deadline below
  the preparation deadline, and make NFC/NFD test literals explicit. All were
  applied. Its hosted-status wording comment was also reconciled here.

## Comments deferred

- The first-head CodeRabbit attempt was rate-limited. The correction-head
  review completed; no comment was deferred.

## Human decisions needed

None. Human approval and merge remain required. The first hosted
`shared_foundations` run completed with the two documented guide failures; the
replacement Backend run and all five shards remain pending on the latest head.

## Commands rerun

```text
ruff check app/modules/artifacts/zip_safety.py tests/test_submission_archive.py tests/test_guide_ooxml.py
pytest -q tests/test_guide_ooxml.py tests/test_submission_archive.py tests/test_guide_formats.py
```

Result: Ruff passed; 119 focused tests passed.

## Remaining risks

The exact correction commit still requires fresh hosted Backend and Agent Gates.
