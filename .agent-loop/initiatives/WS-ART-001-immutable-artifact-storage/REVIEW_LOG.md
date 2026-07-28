# Review Log: WS-ART-001 Immutable Artifact Storage

## WS-ART-001-03A

- Reconciled on 2026-07-28 with trusted `main` `13d9d5d1`, after merged
  WS-XINT-002-01 through 04 planning and internal-service activation.
- Preimplementation reconciliation review rejected the preserved raw
  `AuthorizationContext`, custom evidence, and callback revalidation seam. The
  repair uses only the merged opaque `PreparedAuthorizationHandle` operation
  contract and one request-local PREP adapter lifecycle.
- The route-facing command performs Project Manager preflight before body read,
  scratch construction, or provider runtime. Production remains deny-only
  while `artifact.guide_source.ingest` is planned.
- Transaction A locks canonical project/guide/snapshot/item lineage, consumes
  the issuer-local handle against server-computed digest, byte count, and media
  type, stages non-authoritative `GuideSourceArtifactIngest`, reserves capacity,
  and creates put intent atomically. Provider I/O remains after commit.
- Migration `0038_guide_source_ingest` follows the merged `0037`
  authorization evidence head. Binding, reads, setup activation,
  materialization, and action availability remain outside 03A.
- Final internal review: senior engineering PASS WITH LOW RISKS; architecture
  PASS WITH LOW RISKS; QA PASS WITH LOW RISKS; security/auth PASS WITH LOW
  RISKS; product/ops PASS; reuse/dedup PASS WITH LOW RISKS; CI integrity PASS
  WITH LOW RISKS; test delta PASS; docs PASS. All blocking findings were
  repaired before PR creation.
- Repairs include commit-before-provider execution, activated fixed-service
  put-resolver composition, confirmed-missing replay with capacity
  reacquisition, concealed request-metadata validation, populated downgrade
  refusal, and the exact hosted projects coverage gate.

## WS-ART-001-02D

- Signed explicit start verified on 2026-07-22 against trusted main
  `92b8a7aa`.
- L1 preimplementation plan review: PASS WITH CONDITIONS. The accepted design
  uses an artifact-owned typed activation seam with deny-only production
  wiring, exact ActionId/PermissionId evidence validation, canonical resource
  composition, transaction-local retry reauthorization, configuration-only
  readiness, and the existing bounded in-process metrics convention.
- Focused real-HTTP PostgreSQL evidence passes for binding discovery, redacted
  replica and receipt reads, verification diagnosis, reason-bound `202` retry,
  recovery/audit follow-through, admission usage, inactive readiness,
  pagination, and concealed denial. Required implementation reviewer fanout is
  pending on the candidate commit.
- First implementation review on `6f281793`: circuit-breaker PASS with a
  justified single-contract size exception; all nine reviewer tracks FAIL.
  Blocking findings covered canonical product/pre-binding lineage, recovery
  port bypass and authorization ordering, open response dictionaries, receipt
  cursor/audit completeness, project-scoped admission redaction, proactive
  metrics, safe quota reconciliation, CI gate activation, and missing
  adversarial HTTP/race proofs.
- Repair replaces page-derived scope with locked product and put-attempt
  lineage, routes retry through `ArtifactOperatorRecoveryPort`, authorizes
  canonical recovery facts before differentiated errors, installs strict
  response models and composite receipt cursors, covers every receipt audit
  lineage, requires project-scoped usage, emits all four pressure scopes from
  admission, reconciles configured limits under locked CAS guards, activates
  the exact API-router CI gate, and expands HTTP replay/race/concealment and
  pagination proof.
- Final internal review cleared every blocker. The first hosted PR #177 run
  passed Agent Gates, preflight, API E2E, and shards 1, 2, and 4. Shard 3 found
  one stale exact OpenAPI inventory assertion after the nine intended protected
  Operator routes were composed. Commit `536213ff` updates the exact total and
  protected counts/hashes; its single regression passes and all reviewer tracks
  reapproved the repair. The rerun passed all four shards, then the unchanged
  90 percent artifact foundation gate reported 89.50 percent. Commit
  `f1b9480c` adds meaningful resolver/page helper tests without changing the
  threshold or production code; 26 focused tests and all reviewer tracks pass.
  The next hosted run improved the unchanged gate to 89.70 percent. Commit
  `45725a85` adds exact audit-resource composition and missing-lineage tests,
  covering 14 additional Operator statements for the remaining roughly
  13-statement gap; 28 focused tests and all reviewer tracks pass. A final
  binding projection/missing-resource proof closes the last statement without
  changing production code or the threshold. Final Backend run `29894507010`
  passes preflight, API E2E, all four shards, repository coverage, every scoped
  coverage gate, and artifact foundation coverage at exactly 90.00 percent.

## WS-ART-001-02C3

- Signed explicit start verified on 2026-07-21 against trusted main `f2aa57a4`.
- L1 preimplementation plan review: PASS WITH CONDITIONS.
- Required conditions cover verification-job lineage, database recovery
  invariants, concurrency-safe replay, AUTH separation, atomic audits, terminal
  fencing, and cumulative coverage gates.
- First internal review batch returned blocking findings: taskless guide
  recovery was not representable, the Operator mutation seam was not yet
  fail-closed, and required fencing/terminal/migration proofs were incomplete.
- Repair in progress: recovery task context is nullable, the exact Operator
  authority seam defaults to deny until AUTH-owned activation, authorization
  evidence is retained in the initiation audit, and focused guide/authority
  drift tests were added. No publication claim is recorded yet.
- Re-review cleared taskless-guide and architecture blockers, then identified
  an authorization-ordering bypass on exact replay. Every normal and
  concurrent-winner replay now revalidates the persisted human identity and
  exact recovery authority before returning identifiers; denied replay is
  covered with zero-write assertions.
- Final internal review results on `841f2a38`: senior engineering PASS WITH
  LOW RISKS; architecture PASS WITH LOW RISKS; QA PASS; security PASS WITH LOW
  RISKS; product/ops PASS WITH LOW RISKS; reuse/dedup PASS WITH LOW RISKS; CI
  integrity PASS; test delta PASS; docs PASS.
- Accepted low risks are limited to legacy terminal-audit top-level metadata,
  private audit-builder ownership coupling, and duplicated human-proof shape;
  none changes authorization, recovery custody, or product lifecycle state.
- GitHub Actions run `29851665477` found two valid integration issues: an
  over-broad lineage trigger and an incomplete integrity-mismatch upload-item
  transition. Both received bounded repairs and their three failing tests pass
  locally; final internal re-review and hosted rerun remain.
