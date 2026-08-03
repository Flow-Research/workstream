# Plan: WS-REV-001 Review And Revision Lifecycle

## Current authority

This PLAN4 refresh supersedes PLAN2/PLAN3 implementation sequencing while
preserving their boundary correction: REV begins only at a final current
CheckerRun `allow_review`. Historical files remain evidence, not executable
authority. Current implementation must follow this plan, `CHUNK_MAP.md`, the
active `docs/spec_review_lifecycle.md`, and exact refreshed child contracts.

## Architecture

```text
TASK/CHECKER/ART handoff
  immutable Submission + final allow_review + verified binding facts
        |
        v
REV hidden core
  admission -> queue -> offer -> claim -> lease -> packet/context
  -> Review/findings -> revision or FinalAcceptance
        |
        +-> AUTH evaluates exact typed contracts and stages decision evidence
        +-> TASK applies typed lifecycle effects
        +-> ART materializes only authorized packet bytes
        +-> CON stages contribution/award facts
        +-> shared audit/outbox stage in the same caller transaction
```

REV owns lifecycle state and orchestration. It never imports foreign
repositories or repairs foreign facts.

## Delivery strategy

### Wave 1 — Independent REV persistence

1. `03A1` adds queue/admission-idempotency persistence only.
2. `03A2` adds lease/preference persistence only.
3. `03B` adds normalized immutable ReviewPacketManifest persistence after the
   ART membership contract is exact.
4. `04A` adds immutable Review/finding/resolution and decision-request
   persistence.
5. `04B` adds FinalAcceptance plus shared audit/outbox linkage persistence.

These chunks expose no routes, activate no actions, and perform no ART or CON
operation. This wave can proceed in order after AUTH 02D; only 03B waits for an
exact ART packet-membership contract.

### Wave 2 — Admission and server-selected work

6. `05A` composes final `allow_review` admission using owner-supplied
   Submission, CheckerRun, and verified ART facts. It creates exactly one open
   queue entry and transitions only through typed TASK/CHECKER participants.
7. `05B` implements concealed current-work selection: active lease, one
   server-selected offer, or none. It never exposes the backlog.

AUTH action activation remains separate in XINT-003-03A and does not release a
product router.

### Wave 3 — Claim, lease, and packet

8. `06A` implements atomic claim, one-active-lease capacity, reviewer policy
   freeze through CON, and packet-manifest freeze with ART-owned membership.
9. `06B` implements owned release and preferred decline.
10. `06C` implements database-time preference/lease expiry, lazy recovery, and
    fixed-service commands.
11. `07A` implements lease-bounded context and chain reads, consuming ART
    packet materialization without raw storage access.
12. `07B` implements immutable reviewer notes/findings as records only.

### Wave 4 — Decision and human revision core

13. `08` is pure decision validation and effect planning. It commits no Review.
14. `09A1` persists Review-rooted revision episodes/preparation after the human
    approves round/deadline semantics.
15. `09A2` publishes the typed TASK revision participant and context resolver.
16. `09A3` adds immutable contributor finding-response records.
17. `09A4` integrates prepared human N+1 Submission lineage while preserving
    the separate CheckerRun-remediation source.
18. `09A5` handles replacement-assignment preparation successors.
19. `09B` replays findings/resolutions and creates preferred return routing.

Uploaded reviewer/response evidence is excluded from v0.1.

### Wave 5 — Canonical decision commit

20. `10` composes the first canonical decision transaction:

```text
AUTH consume
-> Review/finding/resolution append
-> lease consume + queue close
-> reviewer CON operation
-> decision branch
-> accept only: FinalAcceptance + TASK accept + submitter CON operation
-> needs_revision: TASK state + revision preparation
-> reject: exact assignment block + TASK reject
-> shared audit/outbox
-> one commit
```

Any participant failure rolls back all product effects. ART/provider I/O is
forbidden inside this transaction.

### Wave 6 — Recovery, projection, and lifecycle control

21. `11A` adds queue inspection and privileged queue/lease commands.
22. `11B` adds covered-project revision repair and obligation close.
23. `11C` adds resumable reconciliation and authority-invalidation jobs.
24. `11D` adds true-legacy closure and typed ART recovery delegation.
25. `12P1` adds deterministic review projection handling on shared outbox.
26. `12P2` adds artifact-reference reconciliation and projection rebuild.
27. `12P3` adds notifications, bounded admin reads, metrics, and drain facts.
28. `12A1` persists the single lifecycle release controller.
29. `12A2` composes REV/TASK/CHECKER mutation fences.
30. `12A3` composes CON writer/dispatcher/callback cutoff and drain fences.
31. `12A4` adds Operator transitions and crash-safe forward recovery.

### Wave 7 — Conformance and release

32. `13A` verifies exact merged dependency manifests and builds the drill
    harness.
33. `13B` prepares current documentation and generated evidence without
    exposing routes.
34. `13C` registers the coherent REV product routers and performs final HTTP,
    database, job, storage, authorization, contribution, and recovery proof.

`13C` is the sole product release. Earlier AUTH activations enable hidden
integrated proof only.

## Authorization protocol

Reads use request-scoped AUTH evaluation with the exact frozen contract.
Mutations prepare an opaque handle, lock AUTH authority first, lock REV and
participant facts in the command-specific published order, recompose the final
typed contract, consume once, stage bounded decision evidence, flush all
participants, and commit once at the route/service-command boundary.

Unavailable actions fail closed. REV never changes catalogue availability.

## Data and history invariants

- One queue entry per admitted Submission.
- One active lease per queue entry and one active lease globally per reviewer.
- Immutable queue age; preference and lease timers are independent.
- One Review per Submission; every Review records the exact lease, packet,
  reviewer, policy, checker admission, and artifact lineage.
- Every revised Submission points to its immediate predecessor; every later
  Review points to the prior Review; findings/responses/resolutions append.
- Accept alone creates one FinalAcceptance, unique by Review, Submission, and
  Task.
- Checker remediation and human revision sources are mutually exclusive.

## External intersections

### ART/CHECKER to REV

The handoff contains identifiers and verified facts only. REV owns admission
meaning, not checker output or artifact custody. Until the final handoff merges,
core persistence continues but `05A`, `06A`, and `07A` remain gated.

### REV to CON

REV invokes ordered typed operations. Every Review gets reviewer
`completed_review`; accept additionally gets submitter `accepted_submission`
from FinalAcceptance. CON owns policy, records, awards, and fulfillment.

## Alternatives rejected

- Waiting for all ART/CON work before any REV persistence.
- Building foreign behavior inside REV to unblock integration.
- One giant schema or decision PR.
- Public routes before recovery and lifecycle fences.
- A separate SubmissionVersion, artifact store, authorization protocol, audit
  ledger, outbox, or contribution writer.
- Review evidence uploads in v0.1.

## Verification strategy

Each child freezes exact commands at start. Required proof includes Ruff,
typecheck where configured, focused unit/service/API tests, PostgreSQL migration
and direct-SQL constraints, independent-session race tests, fault injection,
architecture scans, stale wording/link checks, at least 90 percent coverage for
materially changed subsystems, and GitHub-hosted repository coverage at or
above 78 percent. Full local suite runs are not required.

## Stop rule

This planning refresh starts no runtime child. After review and human approval,
start only `WS-REV-001-03A1`. Stop after its PR; do not begin 03A2
automatically.
