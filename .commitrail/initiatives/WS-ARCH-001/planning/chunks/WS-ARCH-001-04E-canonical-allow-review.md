# Chunk Contract: WS-ARCH-001-04E Canonical Allow-Review Manifest

Disposition: Planned. Coordination contract with owner-sized boundaries
below, not one mixed implementation PR. Risk: L1. Outcome: the hidden admission-backed
Submission automatically dispatches post-submit checking and exposes one
durable current routing fact; an exact `allow_review` manifest becomes the REV
entry dependency.

Allowed: TASK owner-local dispatch/projection code and public API, delivery
composition, focused cross-module integration tests, boundary ledgers,
capability/status docs and exact evidence. Not allowed: REV queue writes,
reviewer behavior, CON behavior, public 02I route cutover, legacy-path claims,
or TASK-owned checker decisions. These restrictions apply to the TASK children;
the separately named AUTH child owns only its authorization changes.

## Current bounded sequence

AUTH-19A delivers inert source commitments and planned router registration.
Split preparation from consequences within the existing TASK and AUTH owners:

1. **ARCH-04E1B-A — Complete: TASK request/source-identity reservation.**
   [The bounded record](../../WS-ARCH-001-04E1BA.md) reserves a distinct
   route operation/digest and future manifest ID for the exact latest submitted
   Submission and current completed `allow_review` evaluation. Caller-owned
   staging/replay does not insert a manifest, publish a current pointer, issue
   an AUTH receipt or apply any acceptance effect. Full source projection and
   exact receipt verification remain composition work at 04E1B-B/04E2-B.
2. **ARCH-04E2-A — Complete: hidden AUTH preparation and nominal receipt
   projection.** The existing planned `task.post_submit.route` action/permission
   retains sole fixed identity `workstream.task.post_submit_router`. Its strict
   resource/request/consequence matcher and nominal adapter use canonical PREP.
   The action remains planned/unavailable and denial occurs before handle issuance,
   so no allow, receipt, source publication or effect exists. Mandatory
   source/FinalAcceptance receipt guards and their
   positive SQL proof follow at 04E2-B, not before CON-07. Keep standalone invocation,
   live workers and consequence activation unavailable. This phase requires no
   acceptance-consuming handler and cannot commit an allow independently.
3. **CON-07 and shared acceptance composition** consume the exact prepared
   contracts. CON-07 is a caller-owned flush-only participant; its isolated
   storage controls prove contribution/award behavior, not acceptance authority.
   Do not require a fabricated AUTH allow to make those controls reachable.
   At 04E2-B, install mandatory receipt custody and prove the first genuine allow
   atomically with source publication, FinalAcceptance, TASK and contribution/
   award effects, plus required audit/outbox records. Refuse retained
   pre-authority sources before any production composition or consumer. Pre-CON
   proof covers exact preparation, unavailable execution and rollback, not a
   durable allowed operation.
4. **ARCH-04E1B-B / 04E2-B / 04E3** complete hidden handlers, exact consequence
   activation and live composition as detailed below. True admission uses the
   same preparation/issuer phases but does not require CON/shared acceptance;
   its receipt commits with its own full admission consequence.

Human acceptance later uses the existing `review.decision` issuer and the same
shared acceptance participant. Its genuine source receipt and Review effects
must commit together; AUTH-19A's human contract supplies no executable issuer.
These phases split existing work; they introduce no additional action, service
identity, source table or acceptance operation. Before implementation, each
phase gets its bounded current-main record and exact owner proof.

Policy-switch integration dependency: these handlers consume the merged
ReviewPolicy boolean schema and immutable lineage behavior specified in the
[product-builder handoff](../../../../changes/pre-review-plan-reconciliation.md#product-builder-handoff-implement-the-setting-next).
Read `human_review_required` from the Submission's locked ReviewPolicy, never
the current project policy. Successful checks with true emit human admission;
false uses the same shared FinalAcceptance/CON operation as human accept, not
enqueue human review or treat `allow_review` as acceptance authority. The
current TASK children do not implement REV/CON internals: consume the
[canonical shared participants and authority contract](../../../../../docs/spec_review_lifecycle.md#finalacceptance).
04E1A's TASK manifest schema/detached facts and narrow accepted-effects Protocol
are delivered after 04C, without REV dependency, runtime participant or handlers.
REV-04B now references that schema after its source prerequisites:
[ART-07A1 packet types](../../../WS-ART-001/WS-ART-001-07A1.md) are delivered;
REV-03B normalized packets and REV-04A immutable Review source storage are delivered; REV-04B shared FinalAcceptance storage is delivered; CON-03C contribution/award storage and REV-12A1 disabled controller/fence are delivered; hidden AUTH preparation is delivered before CON-07; mandatory persisted custody accompanies the first authorized atomic consequence at 04E2-B.
CON-07/shared acceptance prerequisites, using the delivered exact AUTH preparation and
REV-12A1 disabled controller/fence, are hard dependencies of false handler composition, not of this
early schema or true admission. Both branches use the delivered preparation phase
above before hidden 04E1B-B, canonical activation 04E2-B and live 04E3. True proceeds with its own prerequisites;
false additionally requires shared acceptance and scoped lifecycle activation,
with 04F remediation before false guide activation. This breaks the source-FK dependency cycle.
False guide activation stays unavailable until that path is proven. Avoid
making automated acceptance depend on live human queues or leases.

The existing success-manifest, `review_pending` transition and corresponding
tests below describe only `human_review_required=true`. They must not run for
false. Before its acceptance participant is implemented and activated, false
has no live success route; an unexpected false attempt fails closed without
creating human admission, acceptance or contribution effects.

1. **[ARCH-04E1A — TASK source foundation](../../WS-ARCH-001-04E1A.md) — Complete.**
   One route-neutral immutable source schema and detached internal facts, plus
   source-neutral accepted-effects types, follow 04C/04D2. There is no runtime
   writer/reader/composition, current pointer, routing allow or accepted effects.
   Source evidence alone never admits a human or authorizes acceptance.
   The current true-policy graph supplies real SQL proof; false is value-shape
   transport only because guide activation still rejects it. Before publication,
   04E2-B must harden this same table with mandatory exact route and
   owner-receipt custody and refuse every retained pre-authority source row,
   without backfill, mutation, deletion or a parallel table.
2. **ARCH-04E1B-B — hidden TASK handlers.** After 04E1B-A/04E2-A and
   CON-02B's handler/claim contract (plus shared acceptance foundations for
   false), TASK implements unavailable request/event
   production for its own evaluation-request event and the TASK consumer of
   04C's already-defined final-result notification, exact public facts, currentness protocol
   and transaction proof described below. No live worker or action activation.
   Initial checker evaluation-request reservation is a bounded atomic consequence of the existing
   exact `submission.create` command, not an authority token sent to the worker.
3. **ARCH-04E2-B — AUTH routing activation.** After 04E1B-B hidden proof, AUTH
   also consumes scoped XINT-003-08B lifecycle-control activation for the false
   consequence; true routing and the early source schema do not depend on it.
   AUTH
   activates the already-registered fixed identity
   `workstream.task.post_submit_router` with sole action/permission
   `task.post_submit.route`. Its context binds committed completion event/claim,
   immutable Submission, request/generation, exact CHECKERS result/fence and
   TASK pre-review state, locked ReviewPolicy and chosen derived effects.
   Bind exact Task/Assignment, equal assignment/Submission contribution-policy
   version, stabilized artifact hash, manifest identity, allocated acceptance
   identity, actor, project, request/idempotency and transaction as well.
   False/pass includes the shared acceptance consequence after its hidden
   proof; true permits only human admission. Allow only AUTH adapters/catalogue/parity/composition
   and focused proof; no TASK state-machine implementation. It cannot execute
   checker, ART, dispatcher, human review or generic contribution actions.
   Derived submitter/award writes occur only through the shared participant,
   exactly as they do inside human `review.decision`.
4. **ARCH-04E3 — live composition and end-to-end proof.** After 04E2-B, 04D and
   AUTH-OUTBOX-02, wire the proven handlers and canonical Submission route to
   the existing shared dispatcher. TASK owns this narrow live integration and
   legacy-call reachability cutover, not another implementation of 04E1B.

If the shared acceptance foundation lands later than true routing, keep false
activation unavailable and integrate it into this same handler after the named
predecessors; do not add another dispatcher, success event or acceptance engine.
If true routing is already active, false requires exact successor AUTH resource,
evaluator and parity/activation proof under the same ActionId; a handler-only
change cannot silently widen its permitted effects.
Enabling false requires both successful end-to-end acceptance and ARCH-04F's
usable failure/remediation path, exact AUTH authority and PROJECTS readiness
proof, plus a valid authorized generation through the existing controller's
scoped XINT-003-08B activation. Human review/revision activation is not a
dependency of this branch.

Each child uses a separate implementation record/PR at start with exact files
and relevant reviewers. The graph does not require live routing to authorize
its own hidden handler. No extra planning-only approval PR is implied.

The remaining sections specify the final publication boundary after 04E1A;
its source-only schema does not claim these effects or receipt guarantees.
04E1B/04E2 must propagate and retain exact decision IDs from `submission.create`,
ART admission/binding and post-submit materialization owners before publication.
Current contracts discard those IDs; reverse audit-log search or borrowing a
checker receipt is prohibited. Execute/finalize IDs already have durable custody.
For the current zero-output catalogue, the output-binding tuple is empty and no
output write/bind allows can be required. A future registered output producer
must implement and authorize those operations before using their evidence.

TASKS owns one evaluation-request/dispatch record and a current routing projection;
the shared outbox owns its event rows, uniqueness and delivery. CHECKERS
owns the result and recommendation. The success manifest references the exact
persisted AUTH allow events for admission consumption/binding, post-submit
materialization and final-result persistence, including their action/resource
and operation/correlation identities. Do not reuse one action's receipt for
another or treat a routing projection as authorization. Final emission
rechecks run/currentness and locked lineage in the TASK-owned transaction.

Bind distinct persisted allows for `checker.post_submit.execute`, every
required `artifact.checker_output.write` and
`artifact.checker_output.binding.create` operation,
`checker.post_submit.finalize` and `task.post_submit.route`, as well as input
materialization and original Submission/admission binding. Each reference
identifies its exact action/resource/request, not one interchangeable service
receipt. TASK stages its routing allow and manifest/state in the same commit.

Reuse CON-02B's explicit typed handler registry and claim validation. Register
the TASK request -> CHECKERS execution handler and CHECKERS completion -> TASK
routing handler with their independent feature-authority manifests. The
dispatcher has mechanics-only authority; event payloads confer no permissions.
No private TASK outbox consumer, dynamic handler loading or second worker
registry belongs here.

The obsolete direct checker scheduling and TASK-mutation paths have already
been removed. Use the existing shared durable event/handler route when wiring
canonical Submission composition; do not recreate those removed paths. Public
intake remains the later 02I boundary.

## Distinct idempotency and uniqueness custody

Define the canonical input envelope from the locked project/task/assignment,
immutable Submission version, admission/binding/content identity, digest/size,
guide/policy/catalogue lineage and compiled post-plan hash below. Hash it using
the existing canonical hashing convention; matching a key with a different
envelope is a conflict, never a replay. No caller supplies trusted hashes.

| Identity | Deterministic key and database uniqueness owner |
|---|---|
| Dispatch | TASKS owns a unique `(project_id, submission_id, post_plan_hash, evaluation_request_generation)` reservation. Initial submission uses the initial server-owned generation; delivery replay or unfinished recovery never increments it. An authorized terminal retry or genuinely new evaluation requires a new generation allocated under the TASK lock, not a timeout fallback. No new public reevaluation command is introduced here. |
| Outbox delivery | TASKS owns one domain event identity derived from the dispatch reservation plus event kind; use the existing shared outbox unique-event contract. Delivery retries retain that identity and dispatch reference. |
| Checker attempt | CHECKERS/04C owns one unique `(evaluation_request_id, phase)` attempt bound to 04A's exact envelope. TASK persists/delivers that same request identity; it does not define a new CHECKERS key here. Provider/member recovery identities derive from this attempt, never from a delivery timestamp. |
| Routing manifest | TASKS owns one immutable manifest per `(submission_id, checker_run_id, final_result_hash)` and one current routing pointer per Submission. It stamps the locked `human_review_required` value: true is human admission; false/pass is the shared acceptance source, not a second manifest type. Replays reuse it; only nonterminal work may replace the current pointer after CHECKERS currentness and locked-lineage validation. |

Use one lock order: TASK Submission/current routing pointer, then CHECKERS
currentness fence through its public caller-session participant. A new
authorized evaluation initializes/advances that fence, invalidates the TASK
current routing pointer, reserves the request with the returned generation,
and appends the shared outbox event in one transaction. CHECKERS finalization
locks only its own fence/result and cannot reverse this lock order or advance
the generation autonomously. No TASK foreign key is imposed on CHECKERS.

The initial dispatch reservation and outbox event commit atomically. That
initial work must also share the successful admission-consumption, immutable
Submission/binding and TASK `evaluation_pending` transaction. A commit followed
by an unrecorded Celery enqueue can strand a Submission and is not sufficient.
The final routing transaction atomically publishes the immutable manifest,
current routing pointer and exact TASK `review_pending` transition; an outbox
notification alone is not the routing result. Unique
conflict losers roll back the failed statement/savepoint, lock/read the winning
row and compare its envelope; an exact match reuses it, otherwise deny. Never
publish a message before commit or duplicate the CHECKERS attempt in TASKS.
That transition is the true branch only. On false/pass, the same transaction
stages the manifest and shared acceptance effects instead of `review_pending`.
After acceptance, new evaluation generations or remediation must deny rather
than invalidating accepted history. The races below apply to nonterminal work;
acceptance-versus-supersession obeys the shared acceptance contract.
Final routing locks the Submission/current pointer and consumes CHECKERS public
current-result facts under the same transaction/serialization contract, so a
concurrent supersession cannot publish an obsolete result as current. If
routing commits first, the subsequent new generation invalidates its pointer;
if generation advance commits first, old finalization/routing denies. Prove
both orders for finalization-versus-generation and routing-versus-generation.
Recovery of an unfinished request reuses its identity; a terminal failure
requires a separately authorized Operator retry and new superseding generation,
not automatic timeout recycling. This contract supplies the coordination
participant but introduces no public retry/reevaluation command.
The implementation must prove independent-session winners/losers and crash recovery
at each of these four uniqueness boundaries, including outbox redelivery.

Acceptance: one end-to-end test proves approved guide -> authorized assignment
-> verified admission -> immutable Submission/binding -> final current checker
result -> `allow_review`. The manifest explicitly binds the task in its exact
pre-review/evaluation state; immutable Submission id/version; assignment,
contributor and predecessor; admission id; ART binding, content, replica,
digest and byte count; evaluation-request ID and generation; compiled post-plan
hash; CHECKER phase/attempt ID and final result digest; final completed current
CheckerRun whose currentness fence matches that generation; no unresolved
blocking failure under the locked post-submit policy; and
`routing_recommendation = allow_review`. It also carries the exact
`WorkstreamTask.locked_contribution_policy_version_id`, the exactly equal
`TaskAssignment.submitter_contribution_policy_version_id`, immutable
`Submission.contribution_policy_version_id`, and locked review/revision policy
lineage needed by later REV and CON consumers. The Submission version was
stamped before any later revision rebase. The initial version was the
same-project, published, complete, binding-valid immutable
version selected at guide activation and locked before task claimability; the
manifest never reselects it and later policy publication cannot alter this
Submission attempt or its downstream lease. Here stale policy means a mismatch
with the attempt's exact locked lineage, not a newer global publication or
later retirement; do not reselect policy or invalidate the stamped version.

Mismatched replay, revocation, stale guide/policy generation, stale assignment, replaced
binding, non-current run, cross-project/resource, wrong service, wrong session,
wrong transaction all deny. Exact replay and concurrent duplicate dispatch
converge on the same stored identity without duplicate effects. Every denial
proves zero unauthorized provider reads, checker mutations, TASK routing transitions, REV
admissions, and duplicate Submission, binding, dispatch, run, or routing rows.
Failures discovered before I/O prove zero provider reads. A late revocation or
stale result after authorized I/O instead proves no final-current result or
routing write; prior authorized I/O cannot be retroactively undone. Reuse the
canonical AUTH error/audit and owner outbox contracts, not a new denial-only
schema. A denied operation emits no allowed-decision fact or product mutation. No
REV admission occurs in this chunk. Verify real
API/database/Celery/MinIO integration, recovery
and concurrency tests, all boundary validators, Ruff and hosted coverage.
Required reviews: architecture, authorization security, product/ops, QA,
senior, reuse, CI, docs and test delta. Human focus: whether this exact merged
manifest is sufficient to let REV-05A begin.

The checker success recommendation `allow_review` remains evidence, not a
permission or instruction to enqueue a human. Only the locked true branch
publishes human admission; false consumes that successful evidence through the
shared operation. Other checker outcomes fail closed for success routing.
Before public 02I or enabling false, ARCH-04F must install
contributor-readable checker-remediation lineage for final needs-revision
checker results without creating Review, ReviewFinding, or
RevisionContextPreparation records.

This is a coordination contract. Each remaining child record, beginning with
delivered request reservation 04E1B-A, supplies its current-main
exact files, commands, migration head and reviewers before implementation.
Shared acceptance foundations additionally gate false composition; they do not
gate true admission. Both branches retain the preparation, issuer, handler, activation and live
composition phases above; only false handlers add shared acceptance.

## Merge state

- Outcome on merge: `planned`
