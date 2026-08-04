# WS-ART-001-04A1 PR Trust Bundle

## Chunk

`WS-ART-001-04A1 — Legacy Contributor Intake Removal` (L1)

## Goal and approved intent

Remove the inactive multi-step contributor upload-session/item path before the
one-outer-ZIP submission pipeline is built. Preserve historical evidence by
refusing populated deployments; do not translate, detach, delete, or fabricate
legacy lineage.

## What changed and why

- Removed legacy upload session/item ORM records, contributor admission request
  and dispatch, repository lookups, and shared mutation branches.
- Narrowed put-attempt and receipt constraints to current guide/checker
  producers only.
- Added migration `0051_legacy_intake_removal`: exclusive-lock preflight,
  atomic populated refusal, safe-empty removal, and exact empty downgrade.
- Replaced useful generic contributor-fixture coverage with guide and
  task-scoped checker-output proofs.
- Updated current specification, glossary, decisions, and operator deployment
  guidance.

## Design and rejected alternatives

Chosen: a complete safe-empty clean cut. Rejected: detached compatibility
columns, inferred backfill, automatic deletion, dual runtime paths, and adding
the replacement submission route in this chunk.

## Scope and product behavior

No public contributor intake is added. Existing guide and checker storage,
verification, and recovery behavior remains available. A deployment with any
legacy intake evidence remains on `0050_guide_source_v2` and requires separately
approved maintenance work.

## Acceptance proof

- Empty `0050 -> 0051 -> 0050 -> 0051` round trip passed with exact physical
  schema comparison.
- All six populated preflight predicates refused atomically.
- Direct contributor producer and v1 receipt mutations were rejected.
- OpenAPI contains neither retired routes nor the future submission-bundle
  surface.
- Guide/checker put, missing, mismatch, verification, stale-race, retry,
  concurrency, and recovery lineage tests passed.

## CI and test integrity

No CI, threshold, dependency, or package-script changes. Ruff, stale scans,
Markdown links, and diff checks pass. Contributor-specific tests were removed;
their surviving generic guarantees were re-established on current producers.

## Reviewer results and external review

Architecture, security, QA, product/operations, senior engineering,
documentation, reuse, and test-delta reviews pass. CodeRabbit completed without
actionable comments. The first hosted Backend run exposed one stale test request
that omitted the replacement checker's canonical submission lineage; the test
was corrected without changing production guards, and the complete operator and
recovery pair passes 15 tests. A subsequent schema-contract shard exposed one
remaining broad assertion that required the intentionally retired tables; it now
asserts those table columns are discarded, and the exact schema test passes.
All shards subsequently passed, but aggregate ART coverage was 89.52%. Current
checker-output observation tests now replace the removed contributor coverage
for mismatch, provider conflict, and verified-replica collision; all pass and
project 90.01% against the authenticated hosted coverage baseline. Fresh hosted
Backend/Agent Gates are required on the final correction commit.

## Remaining risks and follow-up

- Populated deployments intentionally cannot apply 0051 without separately
  approved maintenance/audit work.
- The replacement one-ZIP preparation begins only in the next approved ART
  chunk; 04A1 creates no submission behavior.

## Human review focus and merge ownership

Confirm the preflight predicates, exact downgrade shape, absence of a
replacement route, and the replacement checker/guide coverage. Human approval
is required for merge; the agent will not merge this PR.
