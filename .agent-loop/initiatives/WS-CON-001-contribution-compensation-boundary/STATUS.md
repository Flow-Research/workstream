# Status: WS-CON-001 Contribution And Compensation

## Current baseline

- Reconciled main: `9865456b3fb1f6048f4c7b7aef4dac71fbf3323e`.
- Alembic head on main: `0056_review_lease_preference`.
- CON-01, CON-02A, and CON-03A are merged; 03A merged in PR #267.
- PLAN5 is merged in PR #270 and preserves the human-confirmed complete-context
  `needs_revision` rebase rule.
- Runtime on main contains shared outbox persistence, the schema-only
  compensation binding foundation, and contribution-policy persistence. 02C
  implementation, deterministic proof, internal review, and external checks
  are complete; human approval and merge remain pending. Contribution-record,
  dispatcher, fulfillment, operations, and CON API behavior remain absent.
- The pre-existing local deletion of the archival reference PDF is user-owned
  and excluded from this runtime change.

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

REV planning evidence remains aligned with CON ownership. REV-03A2 lease and
preference persistence is merged in PR #280 on top of the merged CON-03B policy
FK prerequisite; Review and FinalAcceptance behavior remain future REV work.

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
- CON-03C: REV Review and FinalAcceptance tables are not implemented.
- CON-06/07: corresponding REV lease/decision caller contracts are future.
- CON-03A creation behavior: AUTH has not approved a compensation-adapter
  service identity/capability; existing ART/REV identities cannot substitute.

## Immediate next action

Move CON-02C through external review and human approval now that implementation,
deterministic proof, and required internal review are complete. REV-03A2 may
proceed against the merged contribution-policy version FK, and REV-04B may
proceed in parallel against the 02C contract but must merge after 02C.
Binding creation remains deferred to 04A after AUTH approves the exact adapter
identity/capability contract.
