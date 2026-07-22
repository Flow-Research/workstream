# Review Log: WS-ART-001 Immutable Artifact Storage

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
- Second review on `80c6f4f5` cleared the original blockers and found four
  remaining gaps: malformed receipt cursors, caller-asserted admission project
  scope, advertised-but-unsupported review lookup, and insufficient terminal
  retry authority/zero-fact proof.
- Final repair locks the canonical Project, removes and documents deferred
  review lookup, maps malformed receipt cursors to `422`, and performs a second
  exact actor/link/AUTH decision at the terminal transaction boundary. Focused
  HTTP and recovery rollback tests pass.
- Final exact-SHA review on `584a0626`: circuit breaker PASS WITH EXCEPTION;
  senior engineering, architecture, QA/test, security/auth, product/ops, and
  reuse/dedup PASS WITH LOW RISKS; CI integrity PASS; test delta PASS WITH LOW
  RISKS; docs PASS. No blocking findings or open reviewer sessions remain.

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
