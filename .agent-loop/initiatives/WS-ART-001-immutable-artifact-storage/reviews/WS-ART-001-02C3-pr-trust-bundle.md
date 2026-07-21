# PR Trust Bundle: WS-ART-001-02C3

## Chunk

`WS-ART-001-02C3` — Recovery Attempt And Idempotency Chain (L1)

## Goal And Human-Approved Intent

Add the durable, read-only provider-observation recovery envelope and exact
source-job to retry-job chain. The signed loop-memory start authorized this ART
chunk to run concurrently with AUTH; it does not activate Operator routes.

## What Changed And Why

- added migration `0032` for recovery envelopes and immutable verification
  lineage;
- added nullable task context so the same chain supports guide and task-backed
  artifacts;
- added exact replay, lifetime source ownership, concurrent winner recovery,
  linear retry ancestry, and atomic terminal finalization;
- added a typed Operator authority seam whose production-safe implementation
  denies until the later AUTH-owned activation;
- required fresh actor and exact authority revalidation on creation and every
  replay, with bounded authorization evidence in the initiation audit;
- added focused migration, concurrency, guide, authorization, fencing, and
  terminal-outcome tests.

## Design And Alternatives

The verification job remains the sole executable lease owner. Recovery is an
envelope, not a second worker lease. PostgreSQL uniqueness and custody triggers
enforce one lifetime source owner and immediate-parent chaining. Provider
mutation replay and a task-only recovery abstraction were rejected because
both violate the initiative contract.

## Scope And Product Behavior

No routes, provider mutation, guide/task/submission lifecycle transitions,
review decisions, payment, reputation, dependencies, CI workflow changes, or
coverage reductions are included. Recovery remains infrastructure state and
does not introduce product decisions beyond `accept`, `needs_revision`, and
`reject`.

## Acceptance Evidence

- exact and concurrent replay preserve one envelope, retry job, and initiation
  audit;
- changed/lifetime reuse conflicts without new recovery ownership;
- only exhausted terminal `provider_unavailable` work is recoverable;
- taskless guide recovery is representable and replayable;
- denied creation and denied replay return no identifiers and add no rows;
- success and every failed terminal outcome finalize envelope and audit under
  the verification transaction;
- terminal authority drift writes no terminal recovery facts;
- exhausted retries form only the next linear chain link.

## Tests And CI Integrity

Local focused evidence:

- `ruff check app tests alembic/versions/0032_artifact_recovery_attempts.py`;
- focused recovery tests, including all original five, guide/deny replay,
  authority drift, and sampled failed outcome;
- migration upgrade/downgrade and recovery-schema tests;
- `python3 scripts/check_stale_artifact_contracts.py`;
- `python3 scripts/test_agent_gates.py` — 89 passed;
- `git diff --check`.

The expensive full backend suite, remaining parameter combinations, global
78% coverage, and cumulative artifact 90% coverage are intentionally delegated
to the existing sharded GitHub Actions. No CI or package-script file changed.
No tests were removed, skipped, or weakened.

## Reviewer Results

- senior engineering: PASS WITH LOW RISKS;
- architecture: PASS WITH LOW RISKS;
- QA/test: PASS;
- security/auth: PASS WITH LOW RISKS;
- product/ops: PASS WITH LOW RISKS;
- reuse/dedup: PASS WITH LOW RISKS;
- CI integrity: PASS;
- test delta: PASS;
- docs: PASS.

External review and hosted CI are pending publication of the PR.

The first complete hosted run passed agent gates, preflight, API E2E, and
shards 3-4. Shards 1-2 found an over-broad lineage trigger and an incomplete
integrity-mismatch item transition; both were repaired and their three exact
failing tests pass locally. A full hosted rerun remains required.

## Remaining Risks And Follow-Up

Low risks: legacy terminal audit metadata describes the verifier imperfectly,
the audit builder has private cross-class ownership, and human-proof validation
has small domain-specific duplication. The later typed Operator audit surface
may clean these up. Successor `WS-ART-001-02D` owns Operator routes and real AUTH
activation; it must not start automatically before this chunk merges and the
signed successor event is approved.

## Human Review Focus And Merge Ownership

Verify that no source can own two recoveries, no replay can bypass fresh
authority, and recovery stays separate from provider mutation and product
lifecycle state. A human owns the merge decision; Codex must not merge without
explicit approval for this PR.
