# WS-ART-001-03B3B2 External Review Response

## Comments addressed

- CodeRabbit Major: valid. `pypdf` may raise `KeyError` or `IndexError` while
  reading malformed internal structures. Both now map to terminal
  `malformed/invalid_pdf` rather than retryable `parser_failure`, with direct
  regression proof.
- CodeRabbit documentation nitpick: valid. The artifact specification now
  records the enforced 100,000-object inspection limit and bounded
  `pdf_object_limit` outcome.

## Comments deferred

None.

## Human decisions needed

None beyond normal PR review and merge ownership.

## Commands rerun

- Focused PDF regression tests.
- Ruff on the changed PDF code/tests.
- Dependency gate, stale-contract scan, Markdown links, and `git diff --check`.
- Hosted Backend and Agent Gates rerun after the repair commit.

## Remaining risks

The parser remains an untrusted-format dependency; existing child resource
limits, seccomp-before-byte-read ordering, bounded errors, and complete process
termination remain required controls.
