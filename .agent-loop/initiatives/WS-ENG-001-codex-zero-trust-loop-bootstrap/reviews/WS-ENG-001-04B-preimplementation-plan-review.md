# WS-ENG-001-04B Preimplementation Plan Review

## Reviewed scope

Planning artifacts and chunk contract for `WS-ENG-001-04B`, reviewed against
current protected-main state during 2026-07-20. All tracks reviewed exact
planning SHA `7ffaa59bcb61baa287a125ee9c01c08c0ff29cf5`.

## Risk routing

- Risk class: L1
- SLA: P1
- Work type: architecture, CI/workflow, signed authority, audit ledger,
  documentation, and tests
- Required reviewers: senior engineering, QA/test, security/auth, product/ops,
  architecture, CI integrity, docs, reuse/dedup, and test delta
- Human gate: required before implementation, protected-environment deployment,
  PR review, and merge
- Budget posture: proof-heavy; start authority, state signatures, and workflow
  credentials require complete fail-closed evidence
- Why: this chunk changes the authenticated engineering-loop state machine and
  adds a write-capable workflow that uses an environment-scoped signing secret.

## Reviewer tracks

| Track | Result | Remaining blocker |
|---|---|---|
| Senior engineering | Pass after repair | None |
| QA/test | Pass after repair | None |
| Security/auth | Pass after repair | None |
| Product/ops | Pass after repair | None |
| Architecture | Pass after repair | None |
| CI integrity | Pass after repair | None |
| Docs | Pass after repair | None |
| Reuse/dedup | Pass after repair | None |
| Test delta | Pass after repair | None |

## First-pass findings repaired

- Replaced the unbounded legacy merge-only path with a signed cutover containing
  an exact, one-use initiative/chunk exemption inventory.
- Defined environment approval by a reviewer distinct from the dispatcher as
  authorization, dispatcher identity as attribution, and both as signed event
  evidence. Required settings disable self-review and administrator bypass.
- Required merge catch-up through expected main before event application and a
  second protected-main freshness check after environment approval immediately
  before signing and push.
- Bound event ID/time to immutable GitHub run metadata, added closed input
  validation, secret hygiene, failure atomicity, and fresh-dispatch recovery.
- Added the missing updater/checker test files to allowed scope, an enforceable
  combined branch-coverage command, exact parsed-workflow assertions, and
  external environment-configuration evidence.
- Prohibited a parallel start-specific state path; 04B must extend the existing
  reconciliation, renderer, signer, manifest, exact-tree, and fast-forward
  machinery.
- Tightened coverage to an independent 90 percent branch floor for each changed
  loop-memory script, connected it to the required Agent Gates PR job with
  hash-pinned dependencies, and fixed workflow permissions to exactly
  `actions: read` plus `contents: write`.
- Required repository and organization secret inventories to prove the
  environment-only signing secret has no same-name fallback.

## Gate

Planning review passes with no open blocker. No reviewer session remains needed
for planning. Implementation requires explicit human approval and a fresh
exact-SHA implementation review across all nine tracks.
