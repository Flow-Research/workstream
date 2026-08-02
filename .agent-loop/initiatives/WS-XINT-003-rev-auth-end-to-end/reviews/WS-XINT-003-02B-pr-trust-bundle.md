# PR Trust Bundle: WS-XINT-003-02B

## Chunk

`WS-XINT-003-02B` — Guide-bound policy mutation activation.

## Goal and human-approved intent

Activate exactly `project.review_policy.update` and
`project.revision_policy.update` so a covered Project Manager can append and
select immutable policy versions for one exact draft guide. Do not activate the
review or revision lifecycle.

## What changed and why

- Added the two guide-bound `PUT` routes and one policy mutation service.
- Added append-only ReviewPolicy/RevisionPolicy provenance and one replay ledger.
- Extended the existing opaque PREP protocol with exact policy lineage facts.
- Added deferred PostgreSQL custody joining the selected successor, real
  predecessor, replay record, authority evidence, actor/link/grant, and digest.
- Replaced remaining live fixture bypasses with the public policy routes and
  retained explicitly historical incomplete fixtures only where required.

This removes direct or embedded policy writes and makes the authorized path the
sole live configuration boundary.

## Design and alternatives rejected

The design uses opaque exact `If-Match` selectors, UUID idempotency keys,
replay classification before PREP, locked selector revalidation, single-use
transaction-bound PREP consumption, append-only rows, and atomic evidence.
Raw AuthorizationContext authority, role-only fallback, mutable policy rows,
digest-only selectors, and a second authorization protocol were rejected.

## Scope and product behavior

Only draft-guide policy configuration changes. Reviewer queues, leases,
findings, decisions, contributor revisions, artifacts, payments, contribution
records, and reputation remain unavailable or unchanged.

## Acceptance proof and tests

- Focused policy/PREP tests: 11 passed.
- New-subsystem coverage: 10 passed, 90.58 percent.
- Artifact architecture: 20 passed.
- Ruff, migration SQL generation, stale authorization/artifact/wording scans,
  Markdown links, and `git diff --check`: passed.
- Full PostgreSQL-isolated and repository coverage gates are delegated to
  GitHub Actions as required; no local full-suite run was performed.

## Test delta and CI integrity

No tests were removed, skipped, or weakened. Live project/task/E2E fixtures now
use the real routes. Historical artifact fixtures remain explicitly
`legacy_incomplete`. No workflow, lane, threshold, or failure behavior changed.

## Reviewer results

Architecture, security, product/operations, docs, and CI integrity passed. QA,
senior engineering, reuse/dedup, and test-delta passed with low non-blocking
risks. Every blocking first-round finding was fixed and re-reviewed.

## External review

GitHub `Backend / test`, `Agent Gates / agent-gates`, and CodeRabbit must pass
on the exact final head. Valid findings must be corrected before human merge.

## Remaining risks and follow-up

The API may later expose the opaque replacement selector as a response ETag.
The next REV/AUTH lifecycle chunk remains separate and requires a new explicit
start after this PR is human-merged.

## Human review focus

Confirm replay-before-PREP ordering, exact successor/predecessor custody,
Project Manager scope, append-only behavior, denial side-effect ordering, and
the absence of review/revision lifecycle activation.

## Human merge ownership

Only the human may merge this PR.
