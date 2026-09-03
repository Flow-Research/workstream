# WS-ART-001-03B2 External Review Response

## Comments addressed

- Aligned migration filename and documented revision identity.
- Corrected the canonical materialization-port description.
- Made the return-only prepared-inspector type covariant.
- Added deterministic JPEG standalone-marker handling and proof.
- Added a fixed per-entry nested-archive byte ceiling and exact boundary proof
  before any nested member is buffered.
- Added database-backed proof that conflicting immutable classification evidence
  is rejected without replacing the stored row.

## Comments deferred

- None.

## Human decisions needed

- None. All code comments were low-severity and in scope.
- CodeRabbit's generic docstring-coverage warning is not actionable: the hosted
  repository docstring gate passed on the reviewed head and remains the
  canonical configured check.

## Commands rerun

- Focused Ruff over changed backend files.
- Focused guide-format and preparation tests.
- Focused database-backed guide-materialization tests.
- Repository stale-contract, Markdown-link, lightweight-agent-gate, and diff
  checks.
- Exact PR head `1381d371`: Backend passed in 12m47s and Agent Gates passed in
  19s. A later review-request Agent Gates run also passed in 21s.

## Remaining risks

- Format classification remains syntactic by design; semantic extraction belongs
  to WS-ART-001-03B3A.
- Live guide-reader authorization remains planned and unavailable until
  AUTH WS-XINT-002-04B.
