# Status: WS-CON-001 Contribution And Compensation

## Current baseline

- Reconciled main: `cda59fc32e3a60e1e2c337cae7ebeaa94b95e12b`.
- Alembic head on main: `0053_compensation_bindings`.
- CON-01, CON-02A, and CON-03A are merged; 03A merged in PR #267.
- PLAN5 is the active documentation/specification reconciliation for the
  human-confirmed complete-context `needs_revision` rebase rule.
- Runtime contains shared outbox persistence and the schema-only compensation
  binding foundation; contribution,
  dispatcher, fulfillment, operations, and CON API behavior remain absent.
- The pre-existing local deletion of the archival reference PDF is user-owned
  and excluded from this planning change.

## Current external work inspected

### AUTH/XINT

Merged through PR #257:

- review/revision policy identity and mutations;
- complete planned REV action/principal catalogue;
- typed fail-closed REV resource, PREP, and read contracts.

This is readiness for hidden REV implementation, not a live review lifecycle.
CON dispatcher and protected CON surface identifiers remain unregistered.

### ART

Guide byte ingest, binding, extraction, sufficiency foundations, and the
verified guide-source v2 cutover are merged. AUTH guide binding/read activation
is merged. ART PR #249 and migration `0050_guide_source_v2` are now part
of main; their contracts remain ART-owned inputs rather than CON behavior.

### REV

REV PR #258 is merged planning-only end-to-end evidence. It correctly
preserves CON ownership and identifies CON-03B as
the policy FK prerequisite for REV-03A2.

## Corrected CON priority

The old plan incorrectly made dispatcher work the predecessor of all CON
schema work. Current dependency analysis yields:

1. PLAN4 planning reconciliation.
2. CON-03A adapter-binding persistence.
3. PLAN5 complete-context human revision-rebase reconciliation.
4. CON-03B contribution-policy persistence, unblocking REV-03A2.
5. CON-02C lifecycle-audit participant before REV-04B.
6. Hidden policy/binding behavior and legacy clean cut as AUTH contracts become
   available.
7. Contribution/award persistence after REV provides stable FK targets.
8. Atomic REV/CON participant after both sides' lineage exists.
9. Dispatcher and fulfillment later, after exact AUTH service registration.

## Current blockers

- CON-02B: missing `outbox.dispatch`, `workstream.outbox.dispatcher`, exact
  matrix/context/PREP support, and AUTH activation plan.
- CON-04A/04B and later protected surfaces: exact AUTH manifests are not yet
  registered.
- CON-05A/05B: deterministic legacy-row classification remains a human data
  decision.
- CON-03C: REV Review/ReviewLease/FinalAcceptance tables are not implemented.
- CON-06/07: corresponding REV lease/decision caller contracts are future.
- CON-03A creation behavior: AUTH has not approved a compensation-adapter
  service identity/capability; existing ART/REV identities cannot substitute.

## Immediate next action

Finish PLAN5 canonical reconciliation and stop at its PR checkpoint. It changes
no runtime. After human merge approval, 03B remains the next proposed runtime
chunk; binding creation remains deferred to 04A after AUTH approves the exact
adapter identity/capability contract.
