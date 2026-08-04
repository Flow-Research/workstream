# Joint ART/AUTH/REV/CON Release Handoff

> Historical PLAN4 release snapshot. Live 03A implementation state is in
> `STATUS.md`, `SOURCE_MANIFEST.md`, and the `WS-CON-001-03A` contract.

## Ownership

- ART owns immutable artifact admission, submission evidence, guide-source
  processing, and the future typed packet-membership contract.
- AUTH owns identities, permissions, evaluators, prepared authorization,
  availability, and activation.
- REV owns review policy, queue, lease, Review, FinalAcceptance, review/task
  effects, cross-domain composition, and the single decision-route commit.
- CON owns ContributionPolicy, adapter bindings, ContributionRecord,
  CompensationAward, fulfillment truth, and CON projections.

The core review transaction performs no ART provider I/O. It consumes only
already-persisted canonical identities and stabilized hashes supplied by the
owner contracts.

## Current cross-initiative state

At current `main` (`2feaf47d`), AUTH readiness, ART guide foundations and v2
guide-source cutover, and REV PLAN4 are merged, but the live REV lifecycle and
CON runtime are not implemented. ART PR #249 and migration `0050` are current
runtime evidence. REV PR #258 is merged planning evidence, not runtime
behavior. Re-read the current migration head before implementation and refresh
each REV child contract against its exact gate.

## Correct dependency sequence

```text
CON 03A adapter-binding persistence
-> CON 03B ContributionPolicy persistence
   -> enables REV 03A2 lease/policy-freeze persistence

CON 02C lifecycle audit participant
-> REV 04B FinalAcceptance/audit/outbox transaction foundation
-> CON 03C ContributionRecord/CompensationAward persistence
-> CON 03D delivery/receipt/status and ordinal persistence

REV lease schema/caller facts + CON 04B policy service
-> CON 06 claim-time policy lookup/freeze participant

stable REV revision lineage + CON 03C/03D + CON 05A + CON 06
-> CON 07 mandatory review-decision participant
-> REV 10 hidden contribution composition

AUTH dispatcher registration/admission contract
-> CON 02B hidden outbox dispatcher
-> later fulfillment/projection executor work
```

REV `03A1` queue/admission may proceed independently. REV owns
ReviewLease/preference; CON never owns or duplicates it. REV `03B` depends on
an ART-owned typed packet-membership contract, not on ART provider calls.

## Decision transaction

```text
AUTH prepares exact review.decision authority
-> REV locks ReviewLease, Submission, Task, assignment, and policy facts
-> AUTH evaluates once and stages decision evidence
-> REV stages Review and task/lease effects
-> CON stages completed_review contribution inputs
-> on accept, REV creates immutable FinalAcceptance and completes task/assignment
-> CON stages accepted_submission contribution and conditional awards
-> shared audit and outbox participants flush in the same session
-> REV route commits once
```

`needs_revision` creates no FinalAcceptance and keeps the assignment active.
`reject` creates no FinalAcceptance and blocks only the same-task assignment
with the source Review. Stored decisions remain exactly `accept`,
`needs_revision`, and `reject`. There is no adjudication, appeal, replacement
acceptance, no-op CON participant, post-commit repair, or second ledger.

## Release gates

- ContributionPolicy and adapter-binding schemas and hidden services are
  merged; tasks and review leases freeze the exact policy version.
- REV FinalAcceptance persistence is merged with exact Review, Submission,
  Task, submitter, reviewer, and locked ReviewPolicy lineage.
- Shared audit and outbox append participants are mandatory and flush-only.
- CON review participants are mandatory, typed, and rollback-safe.
- AUTH exact evaluators and activations occur only after hidden behavior.
- Each protected executor/callback has independent fixed-service authority; it
  cannot borrow `outbox.dispatch`.
- ART packet facts cross via typed ports; review/contribution code imports no
  ART repositories and performs no provider I/O.
- One integrated PostgreSQL proof covers all three review decisions,
  uniqueness, frozen-policy behavior, no-self-review, rollback, retry/replay,
  and negative authority cases.

## Stop

This handoff is dependency documentation only. It starts no ART, AUTH, REV, or
CON implementation and does not treat an open PR as merged evidence.
