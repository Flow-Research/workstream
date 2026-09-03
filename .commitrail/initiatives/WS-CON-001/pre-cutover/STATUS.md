# Status: WS-CON-001 Contribution And Compensation

## Durable state on `main`

- The active Alembic graph begins at `0001_v01_baseline`; historical migration
  identifiers below describe the original merge sequence, not the current root.
- CON-01, CON-02A, and CON-03A are merged; 03A merged in PR #267.
- PLAN5 is merged in PR #270 and preserves the human-confirmed complete-context
  `needs_revision` rebase rule on the continuing TaskAssignment. Its old
  independent reviewer-selection wording is historical and superseded by the
  current canonical inheritance rule recorded by WS-ARCH-001 PLAN2.
- Runtime on main contains shared outbox persistence, the schema-only
  compensation binding foundation, contribution-policy persistence, and the
  02C shared lifecycle-audit participant merged through PR #277. Contribution-record,
  dispatcher, fulfillment, operations, and CON API behavior remain absent.

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
6. CP01-CP05 register, implement, and activate binding/policy behavior in exact
   pairs.
7. CP06 validation, CP07 guide binding, and CP08 task-attempt persistence
   precede ARCH-03A/03B replacement behavior and WS-ARCH-001-03C activation; CP09 then
   removes the retired path.
8. Contribution/award persistence follows stable REV Review, ReviewLease and
   FinalAcceptance FK targets, but precedes live review decisions.
9. Review claim copies the admitted Submission's immutable attempt version;
   Task/Assignment lineage is only an equality check, and CON-06 is a planned
   retirement of the former lookup and must not implement runtime behavior.
10. The atomic REV/CON participant must merge before the first canonical Review
    decision; it creates a reviewer ContributionRecord for every final decision
    and, on accept only, a submitter ContributionRecord from FinalAcceptance.
    Frozen rules may create zero, one or two CompensationAwards per record.
11. Dispatcher and fulfillment follow exact AUTH service registration.

## PLAN3 correction

The former 04A/04B/05A/05B path is not executable as written. PLAN3 separates
AUTH registration, hidden CON behavior, AUTH activation, CON validation,
PROJECT guide binding, TASK attempt lineage, and clean legacy removal as
CP01-CP09. The consolidated v0.1 baseline removes any presumption of deployed
historical-row backfill or compatibility behavior.

## Current blockers

- CON-02B: missing `outbox.dispatch`, `workstream.outbox.dispatcher`, exact
  matrix/context/PREP support, and AUTH activation plan.
- CP01A and CP01B are merged with four exact adapter-binding and five
  exact ContributionPolicy actions registered but unavailable. CP01C is
  merged with corrected binding identity and lifecycle-generation
  facts. Callback/fulfillment authority stays separate.
- CP02 is merged with hidden, route-unreachable adapter-binding behavior and
  immutable lifecycle history while all four AUTH actions remain unavailable.
  CP03A is merged through PR #340 with target identity and owner eligibility while
  actions remain unavailable. CP03B completes Finance Authority activation.
  CP04 is a non-executable split parent; CP04A hidden policy draft behavior is
  complete and CP04B completes hidden publication/retirement behavior.
  CP05 is the next non-executable activation skeleton.
- CP06-CP09: validation, owner schema lineage, and clean legacy removal wait for
  the preceding public behavior. No historical-row classification is required
  unless current-main discovery proves real deployed data exists.
- The retained CON-06 contract is superseded/non-executable historical evidence;
  CP06/CP07/CP08 are its only current replacement path.
- The retained CON-08A contract is non-executable because it names superseded
  CON-04A/04B prerequisites. Delivery requires a fresh current-main contract
  against CP02/CP04 and its other exact gates.
- CON-03C: REV Review and FinalAcceptance tables are not implemented.
- CON-07: the corresponding REV decision caller contract is future. CON-06 is
  a planned retirement with no runtime dependency.
- CON-03A creation behavior: AUTH has not approved a compensation-adapter
  service identity/capability; existing ART/REV identities cannot substitute.

CON is not downstream of REV acceptance. It validates the one policy version
at guide activation and participates in every final review-decision commit.
TASK carries that lineage into each immutable Submission, and REV copies the
Submission stamp without a claim-time CON lookup.
Only fulfillment, reconciliation and product reads remain downstream of the
canonical decision transaction.

CP06 validation plus CP07/CP08 owner persistence replace former CON-05A as the
prerequisite for task readiness. WS-CON-001-06 is a planned retirement;
ReviewLease copies the admitted Submission's immutable attempt version and
verifies upstream Task/Assignment equality only.
CP09 replaces historical CON-05B and follows WS-ARCH-001-03C activation of the
CP08/ARCH-03B replacement path.

## Immediate next action

CON-02C merged through PR #277. REV-04B may consume its shared lifecycle-audit
participant after REV's earlier gates merge. CP04A hidden ContributionPolicy
read/create/update-draft and hidden publish/retire behavior are complete. All
five policy actions remain unavailable; prepare CP05 activation next.
Open pull requests determine transient CON work.
