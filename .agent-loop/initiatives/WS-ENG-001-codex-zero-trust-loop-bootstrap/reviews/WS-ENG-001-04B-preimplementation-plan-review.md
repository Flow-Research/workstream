# WS-ENG-001-04B Preimplementation Plan Review

## Reviewed scope

Planning artifacts and chunk contract for `WS-ENG-001-04B`, reviewed against
current protected-main state during 2026-07-20.

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
| Senior engineering | Pending | Review required |
| QA/test | Pending | Review required |
| Security/auth | Pending | Review required |
| Product/ops | Pending | Review required |
| Architecture | Pending | Review required |
| CI integrity | Pending | Review required |
| Docs | Pending | Review required |
| Reuse/dedup | Pending | Review required |
| Test delta | Pending | Review required |

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

## Gate

Planning review is in progress. Implementation is not approved.
