# PR Trust Bundle: WS-ART-001-02A3

## Chunk

`WS-ART-001-02A3` - ArtifactStore v2 Local Clean Cut

Merge intent: `.agent-loop/merge-intents/WS-ART-001-02A3.json`

## Goal

Replace ArtifactStore v1 atomically with the byte-only v2 contract, migrate
LocalStorage and the empty pre-production schema, install an immutable storage
namespace fence, and activate bounded scratch cleanup without compatibility
paths or later product behavior.

## Human-Approved Intent

- Initiative: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/INTENT.md`
- Chunk contract: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks/WS-ART-001-02A3-artifact-store-v2-local-clean-cut.md`

LocalStorage is development/test only. AWS S3 through a later S3-compatible
adapter is the v0.1 hosted direction. Flow Node is separately deferred.

## What Changed

- Reduced ArtifactStore to `put`, `observe_put_result`, `open`, and `head`.
- Rebuilt LocalStorage with content-derived paths, exact replay, bounded reads,
  exclusive crash-safe publication, private no-follow I/O, and sanitized errors.
- Added a deployment storage-namespace singleton and provider-replica binding.
- Made concurrent exact-replay finalization converge on one immutable replica
  while recording a receipt for each upload item.
- Guaranteed cleanup always attempts digest-lock release after temp cleanup
  failures without masking caller cancellation or sanitized provider errors.
- Removed provider retention/receipt semantics, v1 helpers, dormant Flow Node
  configuration, and invented service identity.
- Added startup and Celery Beat stale-scratch cleanup without activating product
  ingestion, verification, recovery, S3, review, or authorization actions.

## Why It Changed

The prior interface mixed byte storage with lifecycle and retention semantics
that Workstream must own. The clean cut makes external storage a narrow
immutable-byte capability and leaves PostgreSQL authoritative for Workstream
state, receipts, verification, and later recovery.

## Design Chosen

`CommittedArtifactSource` binds server-computed SHA-256, exact size, media type,
and second-pass bytes. LocalStorage publishes to a deterministic private path.
PostgreSQL transaction A fences the namespace and reserved upload item, provider
I/O runs outside the transaction, and transaction B atomically stores or reuses
content and replica facts, appends the item receipt, and records
`stored_pending_verification`.

## Alternatives Rejected

- Compatibility aliases or dual v1/v2 factories: rejected for this empty
  pre-production clean cut.
- Provider-owned verify/retain/release receipts: rejected because they mix
  Workstream lifecycle authority into the byte adapter.
- A fabricated artifact service principal: rejected because AUTH alone owns
  service identities and action activation.
- S3, admission, verification, recovery, or product routes in this chunk:
  rejected as separately owned follow-up work.

## Scope Control

The change stays within the approved artifact interface, adapter, schema,
orchestrator, cleanup wiring, tests, CI gates, and related loop/docs files. It
adds no S3 SDK, public route, Operator route, verification job, recovery attempt,
guide/task/submission cutover, product review decision, or authorization action.

## Product Behavior

- [x] No contributor, reviewer, contribution, compensation, reputation, or product review behavior is activated.
- [x] Provider acknowledgement remains non-bindable pending verification.

## Acceptance Criteria Proof

- [x] Four-operation provider-neutral v2 port and one typed factory path.
- [x] Immutable local publication, exact replay, range reads, bounded I/O, and sanitized errors.
- [x] V1 retention/provider-receipt/configuration paths removed without fallback.
- [x] Namespace singleton checked before provider I/O and finalization.
- [x] Conflicting concurrent first writers prove one provider winner and one
  zero-provider-call loser after the namespace transaction commits.
- [x] Concurrent exact replay produces one replica and independent receipts.
- [x] Migration refuses existing and concurrently inserted v1 facts before DDL.
- [x] Populated v2 namespace state prevents destructive downgrade.
- [x] Cancellation persists `replay_required` without premature durable facts.
- [x] Startup and named periodic scratch cleanup are wired.
- [x] Changed subsystems meet the 90 percent coverage requirement.

## Tests And Checks

```text
268 prior complete ART-focused tests PASS
73 final filesystem/architecture/wiring tests PASS
59 final LocalStorage/conformance tests PASS
9 final critical real PostgreSQL orchestration cases PASS
5 migration-chain tests PASS, including 4 ArtifactStore v2 safety tests
ART changed scope coverage 93.31%
Configuration coverage 96.92%
app/main.py coverage 90.35%
Ruff PASS
Docstring coverage 92.0%
80 agent-gate tests PASS
Stale artifact/authorization/Workstream wording, Markdown links, and diff PASS
```

GitHub Backend CI remains authoritative for the isolated full suite, the 78
percent repository floor, cumulative scoped 90 percent gates, and real API drill.

## Test Delta

V1 operation/retention vectors were replaced by v2 contract, LocalStorage,
orchestration, migration, cancellation, concurrency, architecture, cleanup, and
configuration tests. No tests were skipped or weakened.

## CI Integrity

- [x] Repository 78 percent floor retained.
- [x] Existing cumulative 90 percent scoped gates retained.
- [x] Worker and FastAPI startup gates remain fail closed.
- [x] No `continue-on-error`, conditional bypass, or package-script weakening.

## Internal Reviewer Results

Reviewed code SHA: `c8eccaafb6b4f0615b1b37049edfcb0368dd6fb2`

All nine required tracks passed the exact repaired SHA with no remaining
finding. Earlier valid findings covered incomplete test-helper consolidation,
cross-initiative migration custody, and provider-operation ordering proof. All
were repaired, every review session was closed, and the final exact-SHA fanout
passed. Reviewer IDs and final results are recorded in the internal review
evidence.

## External Review

| Source | Status | Notes |
|---|---:|---|
| GitHub Actions | Pending | Full isolated suite and coverage run after publication. |
| CodeRabbit | Pending | External review begins after publication. |
| Human review | Pending | Only the user may approve merge. |

## Remaining Risks

- The migration intentionally refuses any populated v1 artifact table.
- LocalStorage is not a hosted production provider.
- Acknowledged bytes remain unusable until later verification/publication work.

## Follow-Up Work

`WS-ART-001-02B1` adds the S3-compatible adapter, MinIO proof, and AWS profile
only after this PR merges and the user explicitly starts it.

## Human Review Focus

- Is the provider boundary byte-only and provider-neutral?
- Does LocalStorage fail closed while always releasing owned resources?
- Do concurrent exact replays converge without losing per-item receipts?
- Does migration refuse every existing or concurrent v1 fact before DDL?
- Does acknowledgement remain non-bindable and free of invented AUTH identity?
- Did the chunk avoid product ingest and future-chunk activation?

## Human Merge Ownership

- [ ] I can explain what changed and why.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] GitHub CI and external review pass.
- [ ] The user explicitly approved this specific PR for merge.
