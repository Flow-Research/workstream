# Internal Review: WS-XINT-002-01

## Scope reviewed

Closed ART authority catalogue reconciliation, migration `0036`, fixed-service
matrix, deterministic stale proof, live custody documentation, and merge intent.

## Initial findings and resolution

- Senior, QA, CI, and product review rejected the first draft because linked
  idempotency evidence was only implicit and refusal coverage was aggregate.
  Migration `0036` now uses a write-excluding idempotency lock, explicitly joins
  linked evidence, and tests every direct, permission-registry, invalidation,
  and linked predicate independently with unchanged-state snapshots.
- Architecture/docs review found live 25-row and historical count wording.
  Current docs now state 71 permissions, 78 actions, 22 active, 56 planned,
  seven fixed-service identities, twelve memberships, and 22 planned ART rows.
- Test-delta review found missing post-head invalidation rejection and an
  ambiguous historical handoff allowlist. Current SQL rejection covers every
  removed pair, target reference, and invalidation reference; the old handoff
  is explicitly marked immutable historical provenance.
- Corrective security review found that narrowing the direct audit scan to null
  idempotency references could miss orphaned historical evidence. The direct
  predicate now covers every audit row, the linked scan remains additive, and
  an orphaned non-null reference independently proves refusal without mutation.
## Final reviewer results

- Senior engineering: PASS WITH LOW RISKS.
- QA/test: PASS WITH LOW RISKS; later isolated predicate proof was added.
- Security/auth: PASS after the corrective orphan-evidence finding was fixed.
- Product/ops: PASS WITH LOW RISKS; wording note resolved.
- Architecture: PASS.
- CI integrity: PASS WITH LOW RISKS.
- Docs: PASS.
- Reuse/dedup: PASS WITH LOW RISKS.
- Test delta: PASS WITH LOW RISKS.

No blocking finding remains.
