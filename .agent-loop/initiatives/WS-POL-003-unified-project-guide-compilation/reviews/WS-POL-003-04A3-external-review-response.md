# WS-POL-003-04A3 External Review Response

## Comments addressed

- The projection-operation insert guard recomputes the canonical digest from
  the referenced sufficiency report or submission-artifact policy. A
  self-consistent operation cannot seal product content that does not match its
  recorded output digest.
- Source-usage insertion is rejected after a sufficiency report receives
  projection custody. The shared update/delete guard returns `NEW` for an
  unprotected update, so unrelated legacy rows remain mutable.
- Required artifact paths pass through the existing PROJECTS canonical policy
  validator. Focused projection tests now prove rejection of whitespace and
  non-NFC values, traversal, absolute paths, empty segments, local separators,
  and storage references without adding another path-validation implementation.
  Paths already rejected by the current proposal schema have separate
  persisted-v1 coverage using model construction only to reach and prove the
  projection-owned legacy-input boundary; invalid objects are not created at
  test collection time.

## Comments deferred

- None.

## Human decisions needed

- None beyond normal approval and merge authority.

## Commands rerun

- Ruff and the focused projection-policy tests.
- Focused PostgreSQL projection migration tests are owned by hosted CI.
- Stale-wording, Markdown-link, chunk-state, and diff checks.

## Remaining risks

- Exact-head hosted PostgreSQL and complete-suite evidence must pass after this
  response and focused proof are pushed.
