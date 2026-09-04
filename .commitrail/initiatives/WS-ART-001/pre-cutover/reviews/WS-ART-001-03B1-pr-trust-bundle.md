# PR Trust Bundle: WS-ART-001-03B1

## Chunk

`WS-ART-001-03B1` — Guide Binding And Setup Generation (L1)

## Goal And Intent

Bind exact verified guide bytes to the exact project, draft guide, source
snapshot/item, setup run, and monotonic setup generation without activating
AUTH, reading provider bytes, parsing content, or continuing Celery setup.

## What Changed

- Added positive guide-local setup generations and deterministic migration
  backfill.
- Added immutable guide-source artifact bindings with composite lineage and
  verified replica/content constraints.
- Added a hidden binding service that consumes canonical repository facts,
  immutable verification receipts, and transaction-local prepared authority.
- Kept production authority deny-only until AUTH `WS-XINT-002-04B`.
- Added exact replay, concurrency, supersession, stale-lineage, denial,
  migration, downgrade, architecture, and documentation evidence.

## Scope Control

No provider read, materialization, classification, extraction, agent input,
Celery continuation, legacy cutover, submission behavior, or AUTH availability
was added. ART-03B2 and later chunks retain those responsibilities.

## Tests And CI Integrity

No CI threshold or workflow was weakened. The new test module belongs to the
canonical shared-foundations lane. Hosted failures were used as evidence to
repair the exact schema fingerprint, closed-contract result inventory, API E2E
seed, and FK fixture ordering. The exact final head must pass Backend and Agent
Gates before this draft becomes ready for external review.

## Internal Review

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs all pass after valid findings
were repaired. Review details are recorded in the paired internal-review
evidence.

## Remaining Boundary And Next Gate

Guide binding remains unavailable in production. After this PR merges, AUTH
`WS-XINT-002-04B` may activate only the fixed artifact-binding and guide-reader
service actions. ART-03B2 does not start automatically.

## Human Review Focus

Confirm immutable receipt-backed identity, exact setup-generation fencing,
canonical lineage reuse, one-effect concurrency, explicit supersession, and
the deny-only pre-AUTH boundary. The user retains merge approval for this PR.
