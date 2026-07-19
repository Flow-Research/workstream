# Plan: WS-REV-001 Review And Revision Lifecycle

## Planning authority

This plan is reconciled from trusted main
`44f2467cedc266d2efe261119cfff436ac6b7715`, which additionally contains ART
admission foundation PR #154 after REV PLAN2 PR #150, AUTH-09D-B PR #152, and
the AUTH contributor foundation PR #153. Worktree branches, unmerged PRs, and
proposed owner changes are discovery evidence only.
They are not runtime dependencies until their exact owner chunk, PR, merge SHA,
schema head, typed contract, and tests exist on trusted main.

Current merged facts are:

- the single Alembic head is `0028_artifact_admission`;
- TaskAssignment and Submission attribution use canonical `contributor_id`
  ActorProfile foreign keys and database-enforced human lineage;
- the AUTH catalogue contains 74 PermissionIds and 65 ActionIds, with 15 active
  and 50 planned;
- all 24 REV lifecycle action dependencies remain unavailable;
- ART admission and prepared put-attempt foundation is merged through PR #154,
  but provider execution/publication, review packet reads, review-evidence
  candidate/finalize, and server-derived stabilized Submission artifact lineage
  do not have merged owner contracts;
- CON has merged its canonical specification, but its outbox, audit,
  contribution-policy, contribution/award, freeze, and atomic participant
  runtime chunks remain proposed.

AUTH-09D-A is merged through PR #148 at
`99ae4c963e53f317175dcb308b9e47c93ccf19ed` and supplies database-backed
ActorProfile lifecycle status/provenance in migration `0026`. The separate
`WS-AUTH-001-CONTRIBUTOR-FOUNDATION` merged through PR #153 at `8d5eb15b` from
reviewed head `6a70b33f`; migration `0027_contributor_foundation` clean-cuts
both task-subsystem owner fields, adds canonical-human constraints, and exposes
transaction-local active-human revalidation without changing authorization
availability. That external runtime gate is satisfied. Each REV migration still
allocates only the then-current next revision at its own explicit start.
ART PR #154 later advanced the sole head to `0028_artifact_admission` without
changing a Project/setup writer. It creates no REV migration conflict; every
future REV child still refreshes from then-current trusted main.

## Shipping boundary

The v0.1 product path is:

```text
project guide -> task -> submission -> checkers -> review/revision
-> FinalAcceptance on accept -> ContributionRecord
-> CompensationAward where frozen policy permits
-> asynchronous external fulfillment
```

Review decisions stored by the product are only `accept`, `needs_revision`, and
`reject`. Every valid Review, every submitted finding, and every later finding
resolution is immutable. A later round appends new records.

Adjudication is disabled and unimplemented. This initiative adds no
adjudication action, state, queue, lease, policy, decision, contribution, or
readiness dependency. Stable origin and lineage interfaces may accept a new
future origin kind only through a separately approved migration and lifecycle;
that future compatibility does not implement adjudication now.

## Canonical decision transaction

The review request or service command owns the only transaction and commit.
AUTH, task, REV, CON, audit, and outbox collaborators are session-bound,
flush-only participants.

```text
compute canonical request key/digest without a database lock
-> AUTH prepare and authority lock
-> reserve/lock ReviewDecisionRequest
-> lock the review lifecycle fence
-> lock ReviewLease
-> lock ReviewQueueEntry
-> lock WorkstreamTask
-> lock the exact Submission.task_assignment_id row
-> lock the exact Submission
-> lock predecessor Review/finding/resolution/evidence rows in stable ID order
-> recompose final facts and consume/evaluate AUTH handle once
-> append immutable Review and submitted findings/resolutions
-> consume ReviewLease and close ReviewQueueEntry
-> CON reviewer operation creates completed_review and evaluates reviewer freeze
-> apply decision branch
-> stage shared audit/outbox rows
-> commit once
```

The user-confirmed ReviewLease-before-queue order controls this command. Other
commands must publish their own order and may not refer vaguely to a universal
canonical order. Cross-domain rows of the same type lock by ascending primary
key. Database time is read after the relevant locks. No remote ART or external
fulfillment call occurs in the transaction.

Decision branches are exact:

- `accept`: append `FinalAcceptance`, set Task `accepted`, complete the exact
  reviewed TaskAssignment, invoke CON submitter operation from
  `FinalAcceptance`, then stage shared audit/outbox.
- `needs_revision`: invoke the task-owned preparation participant, append the
  human-Review-rooted initial preparation, set Task
  `needs_revision`, keep the assignment active, and create no FinalAcceptance or
  submitter contribution.
- `reject`: block the exact immutable `Submission.task_assignment_id`, set Task
  `rejected`, and create no FinalAcceptance or submitter contribution.

Every branch creates the reviewer `completed_review` ContributionRecord. CON
failure rolls back the Review and all lifecycle effects. External award/points
delivery is post-commit outbox work and cannot roll back acceptance.

## FinalAcceptance

`FinalAcceptance` is an immutable internal derived fact created only by the
successful accept branch. It has no public/manual create API and no separate
authorization action. It records project, task, exact Submission, source Review,
accepted submitter, database acceptance time, recording reviewer, and frozen
ReviewPolicy context. PostgreSQL enforces unique task, source Review, and
Submission plus exact same-chain actor/policy lineage.

Submitter `accepted_submission` contribution consumes FinalAcceptance and never
infers acceptance from `Review.decision`. Reviewer `completed_review`
contribution consumes Review and ReviewLease directly.

## One Project Guide pipeline

Project Guide is the single task and review authority. Task stamps one immutable
guide identity triplet when leaving draft. Submission copies the exact task or
prepared-revision context used for that attempt. The reviewer reads the context
stamped on the exact leased Submission and never performs a separate rebase.

Project Guide activation receives an immutable per-project positive
`activation_sequence`. Version strings are never ordered. A superseded guide
retains its original sequence and provenance if intentionally reactivated.

Publication and task screening both lock Project first. Publication then locks
candidate/current guide and every exact generation input in a declared stable
type/ID order. Task screening locks Project, Task, and the selected active guide
before stamping. This prevents activation from changing the active generation
between task context selection and commit.

02A1 first makes every current setup writer share one Project-first fence.
02A3 then adds chronology, freezes the complete activated guide row except exact
lifecycle transitions, and explicitly introduces a no-write idempotent repeat
for the sole active candidate; current runtime rejects that repeat, so this is
additive behavior rather than a claimed preservation. Draft first activation
remains allowed and a superseded candidate remains denied. 02A4 finally stamps
the exact Task triplet. After the pure REV contracts and AUTH-PREP/custody merge,
02A2 adds the hidden prepared-authorized reactivation branch while
`project.guide.activate` remains unavailable. Its reviewed resource manifest
then gates AUTH-12 evaluator/cutover/activation. The bodyless command requires `If-Match` for
the exact current active guide ETag; missing precondition fails with 428 and a
stale/mismatched precondition fails with 412. Therefore a delayed retry cannot
silently replace a newer guide.

Task guide ID, version, and activation sequence are nullable only together while
draft and complete thereafter. PostgreSQL validates that the triplet names one
same-project guide and rejects every valid-to-valid mutation after allocation.

## Human Review revision preparation

Controlled Project Guide rebase is rooted only in an immutable
`Review(needs_revision)` and its exact prior Submission. Checker-caused
`needs_revision` remains a distinct supported upstream remediation path anchored
to its final CheckerRun. It keeps the Task's existing locked context, creates no
Review/ReviewFinding/reviewer contribution, consumes no human ReviewPolicy
revision round/deadline, and does not use D6 close or human finding replay.
Corrected N+1 persists the unique server-derived
`remediation_source_checker_run_id` for that exact predecessor CheckerRun.

`RevisionContextPreparation` is task-owned and directly references the exact
Review and prior Submission. It forms an immutable non-branching root/successor
chain with one head. The task participant owns guide resolution, Task Context,
and N+1 validation; REV invokes it through typed human-review facts without
importing task/project repositories.

```text
Review(needs_revision) after reviewer CON operation
-> append the Review-rooted initial preparation
-> Task needs_revision -> REV audit/outbox -> review transaction commits once
```

No contributor-readable human-review-caused `needs_revision` state may exist
without one preparation head. Unsafe context creates a blocked head rather than
a missing root.

Preparation compares the prior Submission guide identity/sequence to the
currently active guide:

- exact pair: `kept`;
- any different internally consistent active pair: `rebased` with `forward` or
  `backward` direction;
- missing, incomplete, revoked, inconsistent, or unsafe pair: `blocked`.

It freezes guide/source/task-execution policy context, not contribution policy.
Task Context returns the exact head. Submission N+1 acknowledges the head ID and
digest; a later guide activation does not silently change it.

Human revision requires one immutable response for every unresolved blocking
ReviewFinding and later resolution during review, and returns prefer the prior
reviewer. Checker remediation shows contributor-safe checker messages/fixes,
creates no fake ReviewFinding response/resolution, preserves current guide/task
context, and returns to ordinary open routing after corrected checker admission.

## Revision limits and deadlines

The exact human Review revision-round counting source, deadline anchor, and
boundary remain a human-owned product decision before 09A1. They are not
inferred from checker retries, task SLA, current time, or archival examples.
Whatever values are approved freeze on the Review-rooted episode and use
database time. At exhaustion, Task remains `needs_revision` and assignment
active; context repair cannot bypass exhaustion, and only exact D6 close may
terminate the human revision episode. No synthetic reject is created.

An exact final CheckerRun proves a checker-remediation task is not a rootless
human revision. Only state that claims human Review revision but has no
unambiguous originating Review/preparation is
`legacy_revision_context_unrecoverable`; migration never fabricates a Review.

## Artifact boundary

REV consumes typed ART capabilities only. It never receives ArtifactStore,
provider adapters/references, scratch paths, or raw repository access.

- Queue admission uses stabilized submission/checker facts from exact ART-owned
  cutover contracts.
- Claim creates a normalized immutable ReviewPacketManifest and item rows only
  after ART defines exact packet membership relations. JSON/opaque ID sets are
  prohibited.
- Context content reads require an active exact lease for the exact Submission.
  History is metadata-only; prior, sibling, later, expired, and consumed leases
  grant no byte access.
- Reviewer finding evidence uses an ART-owned candidate/finalize port and an
  exact binding service action. Revision response evidence is owned only by the
  human Review revision chunk.
- Core Review/CON transactions copy stabilized digest lineage and make no ART
  call.

ART currently has no scheduled owner chunks for packet read, review evidence,
or server-derived Submission artifact digest. Those are hard blockers. REV may
record required capability shapes but must not invent ART chunk IDs or start ART
work.

## Contribution and outbox boundary

CON owns ContributionPolicyVersion persistence, TaskAssignment/ReviewLease
freezes, ContributionRecord and award persistence, delivery records, and the
two-operation flush-only decision participant. REV owns Review,
FinalAcceptance, lifecycle orchestration, shared audit/outbox staging, and the
single commit.

Exact merged CON gates are consumed by chunk ID, PR, SHA, migration head, typed
symbol, and tests. `WS-CON-001-03B` precedes the ReviewLease policy FK;
`WS-CON-001-02A` and `02C` precede Review/FinalAcceptance shared outbox/audit
persistence; `WS-CON-001-06` precedes claim freeze; `WS-CON-001-03C` and `07`
precede the first canonical decision commit. Proposed status is not readiness.

## Authorization boundary

Reads use request-scoped AUTH `require`; protected mutations use AUTH's exact
merged prepared protocol. REV does not query grants, register actions, provision
service identities, integrate evaluators, or change availability.

Every external AUTH edge must name the owner chunk and prove merged PR/SHA,
typed actor/action/resource contracts, static service rows where applicable,
and denial/race tests. Placeholder names remain fail-closed planning labels,
not executable dependencies. All actions remain unavailable until AUTH merges
the matching feature-gated activation after hidden behavior.

## Persistence and immutability

`Submission` remains the only versioned submission entity. Submission and
Review predecessor chains are exact N-1 and non-branching. Human identity fields
use canonical human ActorProfile IDs after the AUTH foundation. Service/system
actors remain explicitly typed and cannot occupy contributor/reviewer fields.

Evidence binding identity and scope are immutable. Pre-decision evidence uses
an immutable slot/binding relation; attachment to a finding/response is a
separately appended immutable relation in the Review or submission transaction.
No row described as immutable is later updated set-once.

PostgreSQL owns uniqueness, XOR, same-chain, actor-kind, status/provenance,
immutability, and deferred cross-row integrity. Services validate for useful
errors but do not substitute for database enforcement.

## Chunk strategy

Merged parent references remain as non-executable split records. Parent 02A is
the active planning-only split repair after its L1 preimplementation review
failed; 02A1, 02A3, and 02A4 are the only executable children it declares.
Each child still requires its own current-main refresh, risk routing, plan
review, explicit start, and exact owner evidence before code.

The detailed order is maintained in `CHUNK_MAP.md`. The important boundaries
are:

- 02A1 establishes the shared Project/setup fence; 02A3 adds guide chronology;
  02A4 adds Task triplet screening. 02A2 remains later after 08 and adds hidden
  prepared-authorized, stale-retry-safe reactivation before AUTH-12 activation.
- 03A queue/lease base schema; 03B normalized packet manifest after ART contract.
- 04A immutable review-chain persistence; 04B FinalAcceptance/task linkage and
  shared audit/outbox persistence primitives.
- 05A online checker admission; 05B server-selected reviewer/admin reads.
  Historical admission classification/scan belongs to 11C reconciliation.
- 06A claim/freeze; 06B release/decline/preferences; 06C expiry/lazy recovery.
- 07A lease-bounded context; 07B reviewer finding evidence only.
- 08 pure decision schemas, validation, and typed participant inputs only.
- 09A1 Review-rooted preparation schema; 09A2 preparation resolver and Task
  Context; 09A3 human response evidence; 09A4 internal prepared human N+1 plus
  the exact source XOR that retains 02C's immutable checker-remediation
  `remediation_source_checker_run_id`;
  09A5 replacement-assignment transfer; 09B replay/resolution/return routing.
- 10 first hidden canonical Review/FinalAcceptance/CON transaction.
- 11A privileged queue/lease commands; 11B PM repair/D6 close; 11C
  reconciliation persistence/jobs; 11D true-legacy close and ART delegation.
- 12P1 projection; 12P2 projection/artifact reconciliation jobs; 12P3 reads,
  notifications, metrics, and drain observation.
- 12A1-12A4 separately build hidden release controller, REV fences, CON fences,
  and Operator transition/drain recovery.
- 13A preflight/manifests/drill harness; 13B pre-release docs/generated preparation;
  13C sole product router registration and final HTTP proof.

## Release control

Persisted lifecycle phase controls whether already-registered commands may
execute. It does not dynamically unregister FastAPI routes or rewrite AUTH
action/static-service catalogues. Scheduler shutdown is an operational action;
database fences remain the correctness boundary.

Product reads and mutation classes are defined separately. A disabled phase may
allow bounded readiness/administrative reads while denying product mutations.
Forward reactivation reuses static router registration and AUTH mappings after
phase, drain, service, and dependency checks pass.

Checker needs-revision routing is one server-derived checker-completion class:
it is allowed with checker completion through `revision_cutover_fenced` and
denied from `admission_fenced`. It creates only CheckerRun-rooted task state,
audit, and outbox under the existing locked task context. Human Review
preparation is an internal consequence of leased `review.decision` and shares
that completion class; it is never an independently phase-enabled command.

Chunk 13C is the only product router-registration and active-release-document
point. Earlier chunks keep routes absent, build hidden composition, add reusable
drill scenarios, and may update only planned/pre-release documentation.

## Verification strategy

Every runtime chunk must run focused tests, Ruff, real-PostgreSQL isolated full
suite at the repository 78 percent floor, and at least 90 percent coverage for
materially changed backend subsystems. Migration chunks additionally prove one
head, preflight, upgrade, downgrade/re-upgrade where safe, protected-row refusal,
transactional failure behavior, and direct-SQL constraints.

Every chunk runs stale Workstream/AUTH/ART/REV wording scans applicable on
current main, Markdown links, `git diff --check`, merge-intent validation through
agent gates, and required internal reviewer fanout. Test changes may not weaken,
skip, or rewrite existing checker-caused revision coverage.

## Stop rule

`WS-REV-001-02A` now changes planning/specification only because its L1
preimplementation review rejected the oversized runtime contract. After this
split merges, automated memory names `WS-REV-001-02A1` with an explicit-start
gate. No runtime child or successor starts automatically.
