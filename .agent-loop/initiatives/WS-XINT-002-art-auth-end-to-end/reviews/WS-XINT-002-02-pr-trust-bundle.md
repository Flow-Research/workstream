# WS-XINT-002-02 PR Trust Bundle

## Chunk

`WS-XINT-002-02` — Prepared Operation Boundaries (L1).

## Goal and human-approved intent

Close the reusable PREP-to-ART interface without activating any planned ART
action. Prevent the stale status wording that previously reached `main`.

## What changed and why

- Durable ART mutation requests now carry a process-local opaque
  `PreparedAuthorizationHandle`, not raw request authentication context.
- The obsolete upload-session port was removed with no compatibility alias.
- Guide, submission, and checker-output binding use distinct request types and
  typed methods, preventing action and resource confusion.
- Static guards reject prepared handles in routes, schemas, async payloads,
  provider/public interfaces, and unauthorized method signatures.
- PREP tests prove every planned ART action issues no handle/evidence, a wrong
  fixed service denies before availability, and all rollback/cancellation
  classes burn the handle without kernel or evidence reentry.
- Initiative status now records durable merged facts only and never duplicates
  transient active, merge-pending, or next-chunk state.

## Design and alternatives

Chosen: one existing PREP capability protocol plus closed operation-specific
requests. Exact feature row composers, locks, and resource contexts remain in
their evidence-backed activation chunks.

Rejected: generic binding requests, caller-selected actions/facts, raw
`AuthorizationContext` mutation authority, a second capability protocol,
premature feature truth, and compatibility upload-session aliases.

## Scope and product behavior

No action activation, catalogue/migration, evaluator, kernel, repository,
route, provider I/O, durable write, or lifecycle change. Operator read/recovery
remains on its existing bounded path. Review packet/evidence work remains
deferred to `WS-XINT-002-07`.

## Acceptance proof and checks

- Isolated PostgreSQL authorization/architecture run: 364 passed.
- PREP coverage: 98.32 percent, above the 90 percent changed-subsystem floor.
- Final isolated PostgreSQL rollback atomicity regression: passed.
- Artifact architecture: 11 passed.
- Full Ruff, markdown links, stale authorization docs, stale artifact
  contracts, stale Workstream wording, and `git diff --check`: passed.
- No CI/config/dependency changes, skips, xfails, bypasses, or lowered gates.
- GitHub `Backend / test` and `Agent Gates / agent-gates` remain required for
  full exact-head coverage.

## Reviewer results

Senior, architecture, QA, security, product/ops, CI integrity, docs, and test
delta: PASS. Reuse/dedup: PASS WITH LOW RISK for one intentionally retained
focused test overlapping the new exhaustive regression.

## External review

Pending GitHub Actions and CodeRabbit on the exact PR head.

## Remaining risks and follow-up

This chunk intentionally activates nothing. Chunks 03-07 and 05A-D must supply
their exact non-forgeable feature proofs, lock order, stale/race tests, and
activation evidence. Full repository coverage is delegated to GitHub Actions.

## Human review focus and merge ownership

Confirm no raw authentication context or generic resource/action selector can
enter durable ART mutation ports, no planned action issues a handle, and the
status file cannot become stale at merge. The user retains merge approval for
this specific PR.
