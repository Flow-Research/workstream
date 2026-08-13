# Plan: WS-REV-001 Review And Revision Lifecycle

## Current authority

REV owns review/revision lifecycle behavior only. Eligible Submissions and
packets must carry the exact WS-POL-003 compilation/component/catalogue/plan
lineage admitted by ART/AUTH/XINT; REV neither compiles guides nor selects or
invokes checkers.

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

### Wave 1 — REV persistence with explicit owner gates

1. `03A1` adds queue/admission-idempotency persistence only.
2. `03A2` adds the entirely REV-owned lease/preference persistence. Its
   migration follows CON-03B only so the lease can store its required non-null
   FK to the already-existing canonical `ContributionPolicyVersion`.
3. `03B` adds normalized immutable ReviewPacketManifest persistence after the
   ART membership contract is exact.
4. `04A` adds immutable Review/finding/resolution and decision-request
   persistence.
5. `04B` adds FinalAcceptance plus shared audit/outbox linkage persistence.

These chunks expose no routes, activate no actions, and perform no ART or CON
operation. After AUTH 02D, 03A1 can proceed independently. REV still owns every
03A2 lease row, constraint, timestamp, and transition; only its migration order
waits for CON-03B's FK target. 03B waits for the exact ART packet-membership
identifier contract. These are reference-order gates, not foreign ownership of
REV behavior.

### Wave 2 — Admission and server-selected work

6. `05A` composes final `allow_review` admission using owner-supplied
   Submission, CheckerRun, and verified ART facts. It creates exactly one open
   queue entry and transitions only through typed TASK/CHECKER participants.
7. `05B` implements concealed current-work selection: active lease, one
   server-selected offer, or none. It never exposes the backlog.

AUTH action activation remains separate in XINT-003-03A and does not release a
product router. Before activation, REV proves its hidden feature rules and the
AUTH-unavailable denial path separately; the positive integrated authorization
path belongs to the matching XINT activation after the REV behavior merges.

### Wave 3 — Claim, lease, and packet

8. `06A` implements atomic claim, one-active-lease capacity, REV's lease policy-
   version inheritance from the admitted task lock, and packet-
   manifest freeze with ART-owned membership.
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

### Cross-initiative consume/produce contract

| Subsystem | It owns | It gives REV | It receives from REV | It never owns in this lifecycle |
|---|---|---|---|---|
| AUTH/XINT | ActorProfile/grants, action catalogue and availability, request-scoped evaluation/PREP, decision evidence, fixed service principals, activation | Closed typed REV action contracts and later authorized evaluation/consume results | Canonical REV resource composers, hidden behavior/manifests, and integration fixtures needed for matching XINT activation | Queue, lease, packet, Review, revision, FinalAcceptance, contribution, or product-router release |
| TASK/CHECKER | Project/Task/TaskAssignment/Submission and CheckerRun state, final current `allow_review`, typed task/submission transitions | Existing immutable Submission, final current CheckerRun facts, stamped policy/context lineage, typed caller-transaction participants | Admission/decision/revision commands containing exact locked REV facts | Review queue, reviewer routing/lease, Review judgment, findings, or contribution records |
| ART/XINT | Artifact bytes, verified binding/hash/membership identifiers, provider access, scratch/materialization, packet-byte authorization and delivery | Exact verified Submission binding facts, a contract-only membership port, and later lease-scoped packet materialization | Active REV lease and normalized immutable ReviewPacketManifest identifying what may be materialized | Admission meaning, queue/lease lifecycle, reviewer notes/findings, decisions, revisions, or contributions |
| REV | Queue/admission idempotency, routing/preference, ReviewLease, normalized packet-manifest semantics, immutable Review/findings/resolutions, human revision history, FinalAcceptance, orchestration and the single commit | N/A | N/A | AUTH grants/activation, artifact custody/provider I/O, upstream Submission/checker creation, ContributionRecord/award/fulfillment persistence |
| CON | ContributionPolicy/versions, ContributionRecord, award and fulfillment state, guide-activation policy validation, flush-only decision participant, shared dispatcher/release hooks | Existing canonical policy-version FK target and decision-time contribution/award staging | REV-owned lease reference facts; immutable Review source for reviewer work; accept-only FinalAcceptance source for submitter work; caller session/locked facts | ReviewLease persistence/transitions, reviewer selection, claim-time policy selection, review decision, FinalAcceptance creation, task transition, authorization, or transaction commit |
| Future adjudication | Future policy and adjudication behavior under separate intent | Nothing in v0.1 | Traversable immutable Submission/Review/finding/response/resolution/FinalAcceptance lineage | Any v0.1 REV behavior |

### Exact ownership flows

```text
Admission
TASK/CHECKER/ART own and supply:
  immutable Submission + final current CheckerRun allow_review + verified binding facts
REV alone decides admission meaning and persists:
  admission idempotency + ReviewQueueEntry

Claim
AUTH prepares/consumes authority
REV verifies the canonical admission's task-locked ContributionPolicyVersion ID
REV alone persists and manages:
  ReviewLease + policy-version FK + queue/lease transitions + packet freeze
ART and CON perform no claim or lease write

Packet read
REV supplies active lease + normalized ReviewPacketManifest
ART authorizes/materializes/verifies exact bytes
REV exposes the lease-bounded review context

Decision
REV locks and validates the complete lifecycle state
REV appends Review/findings/resolutions and consumes lease/closes queue
CON stages exactly one reviewer contribution from Review
accept only: REV creates FinalAcceptance and TASK acceptance;
             CON stages one submitter contribution from FinalAcceptance
needs_revision/reject: CON stages no submitter contribution
REV-owned caller commits every staged effect exactly once
```

The TASK/CHECKER/ART handoff contains identifiers and verified facts only. REV
owns admission meaning, not checker output or artifact custody. ART's admission
chain through its final checker-output routing and the corresponding XINT
activation must provide the exact current-main manifest before `05A` starts.
REV-03B defines normalized packet semantics without waiting for ART-07A runtime;
ART-07A later consumes the lease/manifest and materializes bytes, and REV-07A
consumes that materialization. This ordering avoids a circular dependency.

### Current cross-plan gates

Owner plans are dependency evidence, not authority for REV to edit their work.
Some AUTH/XINT/CON status prose predates current main, so every consuming child
must recheck the implementation and signed merge history rather than trusting a
stale `Proposed` or `Active` label.

| Required owner output | Producer | Current-main state at PLAN4 | REV consumer |
|---|---|---|---|
| Closed typed REV authorization/PREP schemas, actions unavailable | XINT-003-02D | Merged in PR #257 | Hidden REV services; later positive activation remains XINT-owned |
| Canonical ContributionPolicyVersion persistence target | CON-03B | Merged PR #274; consumed by merged REV-03A2 PR #280 | 03A2 |
| Reviewer-packet membership identifier/port contract, with no REV runtime dependency | ART-owned contract-only precursor to ART-07A | Missing exact published contract; report to ART owner | 03B |
| Shared lifecycle-audit participant | CON-02C | Merged PR #277 | 04B |
| Final Submission/CheckerRun/verified-binding admission manifest | ART checker chain through ART-06B and XINT-06B | Not evidenced complete | 05A |
| Task-locked ContributionPolicyVersion lineage carried by canonical admission and copied to the lease FK | TASK/ARCH manifest; CON-06 lookup superseded | Future live admission gate; no claim-time lookup | 06A |
| Exact reviewer packet materialization | ART-07A, activated by XINT-002-07A | Future after merged REV lease/manifest | 07A |
| Atomic contribution/award decision participant | CON-07 | Future after REV-04B/09B and CON prerequisites | 10 |
| Shared dispatcher/handler registry | CON-02B | Not evidenced merged | 12P1 |
| CON cutoff/drain hooks | CON-03D/08A/08B/10B/11 as refreshed by CON | Future | 12A3 and 13C |

The missing ART contract-only precursor is an ART-owner gap, not a new REV
chunk. REV-03B cannot start until ART publishes it. This explicit precursor
breaks the former ART-07A ↔ REV-03B cycle: ART publishes types first, REV
persists the semantic manifest, then ART-07A materializes it.

### REV to CON

REV invokes ordered typed operations. Every Review gets reviewer
`completed_review`; accept additionally gets submitter `accepted_submission`
from FinalAcceptance. CON owns policy, records, awards, and fulfillment.
REV exclusively owns ReviewLease persistence and lifecycle. The lease stores a
non-null immutable reference to CON's canonical reviewer
ContributionPolicyVersion; it does not duplicate policy fields or own policy
selection. CON never creates, updates, closes, or authorizes a lease. CON-03C
may consume merged REV Review/FinalAcceptance/ReviewLease schema, and REV-10
waits for CON-07's mandatory flush-only participant.

On human `needs_revision`, REV composes the task-owned complete-context
preparation after the reviewer CON operation in the same transaction. The
completed reviewer record keeps its lease-frozen policy. Preparation may keep
the applicable lineage or create a newly prepared task context locked to a
newly active guide-bound version; existing tasks and assignments are not
rewritten. The next assignment and ReviewLease inherit that task lock. REV owns
orchestration and lineage, not CON policy selection.

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

This planning refresh starts no runtime child. PLAN4, 03A1, and 03A2 are
merged. The next REV planning boundary is 03B after ART publishes its exact
contract-only packet-membership port. Replace the 03B skeleton with a
current-main executable contract and obtain human approval before implementation.
