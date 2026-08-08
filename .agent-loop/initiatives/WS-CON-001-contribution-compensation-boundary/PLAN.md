# Plan: WS-CON-001 Contribution And Compensation

Current dependency note: CON consumes accepted REV outcomes whose Submission
lineage already binds the exact WS-POL-003 unified compilation and compiled
checker plan. CON does not compile guides, project policies, or checker plans
and does not invoke checker services.

> Historical PLAN4 plan. Live 03A implementation state is in `STATUS.md`,
> `SOURCE_MANIFEST.md`, and the `WS-CON-001-03A` contract.

## Strategy

Build the canonical PostgreSQL truth first, then integrate it into REV's
caller-owned transaction, and only afterward expose asynchronous fulfillment,
operations, and release surfaces. Do not let the missing dispatcher block
independent policy persistence needed by REV.

## Ownership model

| Owner | Owns | CON receives | CON never takes |
|---|---|---|---|
| AUTH | actors, grants, catalogue, typed contexts, PREP, service identities/matrices, evaluators, activation | authorized decisions/capabilities and exact resource facts | catalogue, grants, provisioning, evaluator, activation |
| ART | bytes, bindings, verified content, provider access, accepted artifact identity | stable accepted Submission/binding/hash lineage | provider I/O, credentials, scratch, byte custody |
| REV | queue, ReviewLease, Review, findings, revisions, FinalAcceptance, lifecycle effects, orchestration, single commit | caller session and locked Review/lease/FinalAcceptance facts | lease/decision/FinalAcceptance ownership or commit |
| CON | policy, contribution, award, fulfillment truth and narrow participants | — | review judgment, artifact custody, settlement truth |

## Corrected delivery order

### Phase A — current planning and independent schema foundations

1. `PLAN4` reconciles current main, merged ART #249 plus remaining ART gates,
   merged REV PLAN4, boundaries, and chunk order. It changes no runtime.
2. `03A` persists project compensation adapter-binding identity/lifecycle with
   no provider behavior or credentials.
3. `03B` persists ContributionPolicy, immutable versions/rules/definitions,
   and the project selector. This is the required FK target for REV-03A2.
4. `02C` adds the generic caller-transaction lifecycle-audit participant before
   REV-04B. It no longer waits for dispatcher mechanics.

REV-03A1 may proceed concurrently after merged REV PLAN4. REV-03A2 waits for
CON-03B, while later REV-04B waits for CON-02C.

### Phase B — hidden policy behavior and legacy clean cut

5. `04A` adds hidden adapter-binding service behavior after AUTH registers the
   exact binding actions/contexts and keeps them unavailable until hidden proof.
6. `04B` adds hidden contribution-policy behavior under the same
   registration-before-behavior-before-activation sequence.
7. `05A` removes semantic use of retired guide-bound economic terms, initially
   freezes the submitter ContributionPolicyVersion on TaskAssignment, and
   supplies the guarded update boundary later consumed by human revision
   preparation for complete next-attempt rebase.
8. `05B` removes the now-unreachable legacy economic schema after an approved
   deterministic row classification and zero-consumer proof.

### Phase C — REV integration foundations

9. `06` supplies only claim-time reviewer policy lookup/freeze facts. REV owns
   the ReviewLease row and lifecycle.
10. REV proceeds through its queue/lease/packet/Review persistence sequence.
11. After REV-04B supplies stable Review, ReviewLease, and FinalAcceptance FK
    targets, `03C` persists immutable ContributionRecord and CompensationAward.
12. `03D` persists delivery, receipt, status, ordinal, and generation truth.
13. After REV revision lineage is stable, `07` supplies the mandatory two-step
    flush-only participant for reviewer work and accept-only submitter work.
14. REV-10 owns the atomic Review/FinalAcceptance/TASK/CON/audit/outbox commit.

### Phase D — dispatcher and fulfillment

15. AUTH registers `outbox.dispatch`, `workstream.outbox.dispatcher`, exact
    static membership, typed event context, and fixed-service prepared claim
    support. Registration remains unavailable until hidden behavior exists.
16. `02B` implements generic claim/invoke/finalize, retry, dead-letter, replay,
    retention, registry, and drain mechanics. It grants no handler authority.
17. AUTH activates only dispatcher mechanics after reviewing merged 02B.
18. `08A` adds outbound compensation delivery under an independent delivery
    identity/action; `08R` adds callback rate control; `08B` adds authenticated
    inbound fulfillment reporting. None inherits dispatcher authority.

### Phase E — reads, operations, and release

19. `10A` exposes bounded PostgreSQL contribution/award reads after exact AUTH
    read actions and concealment rules.
20. `10B` adds operations requests/reads and same-session drain observation.
21. `10C` adds independently authorized reconciliation and projection
    executors.
22. `11` proves dependency, cutoff/drain, service provisioning, activation,
    failure, and recovery readiness before public release.

Optional evidence projection `09A/09B` remains outside this core order and
requires a fresh ART/AUTH disclosure plan if ever selected.

## Canonical review transaction

```text
AUTH prepares review.decision
-> REV locks/recomposes canonical Review/Submission/lease facts
-> AUTH consumes/evaluates once
-> REV appends Review/findings/resolutions and closes lease/queue
-> CON reviewer operation stages completed_review and applicable awards
-> branch:
   accept -> REV creates FinalAcceptance + task/assignment effects
           -> CON submitter operation stages accepted_submission and awards
   needs_revision -> REV applies revision effects; no submitter contribution
   reject -> REV applies bounded rejection effects; no submitter contribution
-> REV stages shared audit/outbox
-> REV commits once
```

CON copies the stable artifact hash/identity supplied by REV. It neither loads
bytes nor calls ART.

## Authorization sequence

For each protected CON surface:

```text
feature manifest
-> AUTH registers exact action/context/principal while unavailable
-> CON merges hidden behavior and negative proof
-> AUTH integrates evaluator and activates exact action
-> later composition/release consumes it
```

No catch-all CON service, dynamic plugin registry, generic service locator,
compatibility alias, or dispatcher-authority inheritance is permitted.

## Migration strategy

- Never reserve migration numbers in planning.
- Each implementation refreshes `main` immediately before editing and uses the
  then-current single head.
- Every migration proves fresh install, PostgreSQL upgrade, guarded downgrade,
  and exact constraint parity.
- Legacy economic rows are never guessed or silently backfilled.

## Verification strategy

Every runtime chunk must run its focused tests, Ruff/type checks as applicable,
PostgreSQL migration proof, changed-subsystem coverage at least 90%, and the
repository-wide 78% floor in hosted CI. High-risk auth/payment/architecture
chunks require senior, QA, security, product/ops, architecture, docs,
reuse/dedup, test-delta, and CI-integrity review as applicable.

## Alternatives rejected

- Waiting for the dispatcher before creating policy tables: blocks REV for no
  technical reason.
- Letting REV own ContributionPolicyVersion or ReviewLease policy selection:
  crosses product ownership.
- Letting CON create ReviewLease or FinalAcceptance: transfers judgment state.
- Calling ART/provider services in the review transaction: creates availability
  coupling and breaks atomicity.
- Treating plans/open PRs as implemented behavior: contradicts the current
  capability ledger.

## Stop

PLAN4 is planning only. Do not begin 03A, 03B, 02C, or any runtime chunk in
this planning change.
