# Internal Plan Review Log: WS-REV-001

## CON Reconciliation Addendum - 2026-07-15

REV's joint integration evidence was refreshed against CON planning commit
`42cf11f`. Its content-level reviews closed the former compensation-context
removal, AUTH service-only outbox/callback authority, ART capability/recovery,
adapter composition, disclosure, provenance, and REV-13 joint activation.
CON runtime publication remains a dependency-owned gate; this planning chunk
does not treat sibling uncommitted changes as merged contracts.
Remaining runtime gates are the immutable reviewed-submission digest/context
contract, unsafe canonical-row downgrade refusal, merged dependency SHAs, and
the normal human start gate.

Current post-CON delta review:

| Track | Agent | Result | Disposition |
|---|---|---|---|
| Security/auth + senior engineering | `/root/rev_con_security` | PASS AFTER FIXES | Trust-state wording corrected; dependency-owned CON publication remains gated; merge intent added |
| Product/ops + QA/test | `/root/rev_con_product` | PASS AFTER FIXES | Merge intent scoped; missing CON-05A REV-02 gate recorded as an owning-CON blocker |
| Architecture + docs | `/root/rev_con_arch` | PASS AFTER FIXES | Stale untracked/reviewed wording corrected; original archival deletions excluded from publication |


## Scope

Reviewed the initiative intent, discovery, decisions, risks, plan, conformance
matrix, chunk map, and every chunk contract. These are planning reviews only;
each implementation chunk still requires its own zero-trust reviewer fanout.

## Final results

| Track | Agent | Final result | Material repairs verified |
|---|---|---|---|
| Senior engineering | `/root/rev_plan_senior` | PASS | Submission lineage constraints, admitted-only backfill, chunk split, outbox gate, lock/race proof |
| QA/test | `/root/rev_plan_qa` | PASS | Fresh isolated Postgres coverage, conformance matrix, live drill order, WS-CON rollback/replay matrix |
| Security/auth | `/root/rev_plan_security` | PASS | Transaction-aware AUTH links, eligibility/self-review, evidence authorization, replay disclosure, bounded privacy, closed rollout |
| Product/ops | `/root/rev_plan_product` | PASS | Final coherent cutover, existing-row activation, D6 effects, invalidations, metrics/notifications, no non-review CON effects |
| Architecture | `/root/rev_plan_architecture` | PASS | AUTH/ART/CON ownership, shared audit/outbox, lock hierarchy, one-way ports, composition and activation sequence |
| Docs/spec adoption | `/root/rev_plan_docs` | PASS | Immutable archival provenance, active contract, scanner scope, migration/job docs, generated/checksum proof |
| Reuse/dedup | `/root/rev_plan_reuse` | PASS | Existing Submission/task/checker/audit/outbox/idempotency/Celery reuse and single canonical submission path |

## Initial failures and disposition

Initial reviews failed or imposed conditions around early public activation,
dependency-owned wildcard scope, duplicate outbox/audit/idempotency mechanics,
submission/checker transaction ownership, indiscriminate historical queueing,
revision chunk size, archival replacement, stale coverage evidence, incomplete
live proof, and underspecified authorization/privacy races. Every valid finding
was incorporated into the plan and explicitly re-reviewed to PASS.

## Residual human gates

Internal PASS does not approve implementation. The decisions in `INTENT.md`
remain human-owned, especially D6 limit/deadline behavior. Chunk 01 remains
inactive until explicit approval, and every later dependency gate is refreshed
from trusted `main` when that chunk is activated.

## Post-clarification final review - 2026-07-15

Human clarification confirmed the one-Project-Guide ADR 0010 flow, ART-backed
current packet, immutable Submission/Review history, and WS-CON creation matrix.
The plan was then repaired and re-reviewed across the following tracks.

The later D5 clarification confirmed that an exact match between the prior
Submission's stamped guide identity/activation sequence and the project's
currently active guide keeps context. Any different internally consistent active
pair is authoritative for forward or backward rebase; an internally inconsistent
pair or missing, incomplete, or unsafe active context blocks for manager repair.

| Track | Final result | Final scope verified |
|---|---|---|
| Senior engineering | PASS | Submission/CheckerRun rebase constraints, guide activation sequence, preparation/reconciliation identity, legacy cutover, admin persistence |
| QA/test | PASS | Migration/direct-SQL proof, race permutations, ART authority races, contribution lineage, duplicate reconciliation, recurrence, rollback |
| Security/auth | PASS | Relationship-scoped history, active-lease content, two-phase ART intake, 22-action AUTH gate, typed PM/Operator resources, replay/denial guards |
| Product/ops | PASS | Frozen Task Context, PM successor repair, Operator legacy closure, reviewer/submitter history, exact CON effects, operable routes |
| Architecture | PASS | Task-owned guide/revision participants, Submission-bound checker context, canonical lock order, AUTH/ART/CON ownership, admin schema ownership |
| Docs/spec adoption | PASS | Impacted-doc scope, 22-action AUTH gate, exact routes, admin/reconciliation schema, status, and review evidence |
| Reuse/dedup | PASS | Existing Submission/ProjectGuide/CheckerRun/task participants reused; justified decision/admin idempotency and reconciliation evidence aggregates |

Material repairs included:

- activated-guide-only ordering and deterministic revision preparation;
- non-branching Review-rooted preparation episodes and a non-forgeable legacy
  revision cutover;
- immutable exact checker admission, active-packet ART disclosure, and two-phase
  evidence authorization;
- exact Submission-to-TaskAssignment and WS-CON actor/lease/policy/hash lineage;
- Project Manager successor repair and evidence-linked Operator legacy closure;
- AUTH-owned repair/closure ActionIds mapped to existing PermissionIds; and
- canonical reconciliation fingerprints, one unresolved generation, atomic
  resolution, duplicate-scan reload, and controlled post-resolution recurrence.
- corrected source provenance for the current revised Markdown hash/counts and
  its section 4.6 divergence from the unchanged PDF companion.

## Post-Main Release-Control Final Review - 2026-07-15

`git pull --no-rebase origin main` merged trusted main `e9d72a1` into REV HEAD
`3e09e99` without conflict. AUTH-07A became merged foundation rather than
unmerged discovery evidence. The later amended AUTH-08 contract supersedes the
old catalogue arithmetic: after AUTH-08's prospective 57 actions (9 active, 48
planned), the four REV additions require 57-to-61 typed catalogue, owner, and
PostgreSQL audit parity, producing 9 active and 52 planned.

The first fresh review failed because shutdown persistence had no executable
owner. Chunk 12A was added, then repaired through repeated zero-trust review:
exact cutover/shutdown phases, generation-aware reactivation, fresh Operator
authority, command-class mapping, typed review/CON drain ports, mandatory
dispatch/callback hooks, durable provider-I/O handoff, and complete race proof.

| Track | Agent | Final result | Final scope verified |
|---|---|---|---|
| Senior engineering | `/root/rev_repair_senior` | PASS | Executable graph, command mapping, remote-I/O handoff, operable drill |
| QA/test | `/root/con_contract_review` | PASS | Phase/class matrix, races, crash/retry, migration, coverage gates |
| Security/auth | `/root/con_code_boundary` | PASS | Actor kind, fresh authority, exact action parity, fences, no lock-held I/O |
| Product/ops | `/root/con_contract_review` | PASS | Legacy continuity, revision/CON behavior, drain, reactivation |
| Architecture | `/root/rev_repair_senior` | PASS | Port ownership, composition, repository isolation, ADR 0014 |
| Docs/spec adoption | `/root/con_code_boundary` | PASS | Provenance, dependency status, terminology, proof ownership |
| Reuse/dedup | `/root/rev_repair_senior` | PASS | Shared hashing/idempotency/audit/outbox/job execution/adapters reused |

All valid findings are closed. The human approved D6, reviewer-current
precedence, coherent activation, the sequence, and planning publication on
2026-07-15. Dependency merges, planning merge, and the successor's separate
post-merge start gate still prevent runtime implementation.

## AUTH-07B Dependency Refresh - 2026-07-15

Trusted main `90eca12` merges AUTH-07B. REV reviewed the merged runtime before
updating its dependency snapshot. The kernel shape, canonical actor boundary,
deny-by-default action handling, exact two active self actions, update lock
order, and bounded denial evidence are compatible with the planned boundary.

The dependency is not yet safe for REV consumption:

- High: `get_authorization_service` commits any open request-session transaction
  during generic successful teardown, so future feature work could be committed
  without its owning service or route doing so.
- Medium: SQL failure while `AuthorizationService.require` stages decision
  evidence can escape the dependency as an unstructured 500 on self-read.
- Medium: the actor-self cutover returns existing actors without advancing
  `ActorProfile.last_seen_at` or `ActorIdentityLink.last_verified_at`.

REV owns no repair in AUTH code. PLAN, DECISIONS, RISKS, CHUNK_MAP, chunk 01,
the first AUTH-consuming chunk 05, and final chunk 13 now fail closed on
AUTH-owned repair and regression proof. The catalogue snapshot is corrected to
74 PermissionIds and 50 ActionIds split into 2 active actor-self actions and 48
planned actions; every one of the 24 REV action dependencies remains inactive.

Review tracks: senior engineering/architecture/reuse found the generic commit
and error mapping defects; QA/product confirmed the error and timestamp
regressions; security/auth found no separate canonical identity, action parity,
or denial privacy defect. Ruff and 24 focused authorization tests passed
locally; merged PR #130's Backend, Agent Gates, and CodeRabbit checks passed.
Database integration was not rerun locally because the isolated test database
URL was not configured.

At this 2026-07-15 refresh, PR #128 was parked and its local main merge was not
pushed. ART PR #129 was conflict-blocked despite approval and green checks; it
still needed to refresh from main and merge before the final dependency refresh,
reviewer pass, SHA binding, and PR update.

The human also corrected the reference-file ownership decision: the revised
supplied Markdown/PDF contents belong at the canonical WS-REV filenames. The
temporary `(2)` paths were removed, canonical hashes were refreshed in the
reference README/SHA256SUMS, and no second archival generation remains in the
active plan.

## AUTH-08 Dependency Refresh - 2026-07-16

`git pull origin main` rebased the four local REV planning commits without
conflict onto trusted main `aa0fdcd6912e66609e39a2fbd7b65f67be6c62f3`.
That merge commit is AUTH-08 PR #131; its final branch head is
`0832358a0262805f553d05b50b0d778e6e6ad995`.

REV reviewed the merged runtime, migration, tests, AUTH evidence, and external
review response. AUTH-08 resolves all three AUTH-07B consumption findings:

- dependency teardown rolls back rather than committing an open caller-owned
  transaction;
- typed authorization-evidence persistence failure maps once to retryable
  `503 service_unavailable`; and
- successful existing-actor GET/PATCH routes advance both canonical
  verification timestamps in the route-owned transaction while denial or
  persistence failure rolls them back.

The merged catalogue now contains 74 PermissionIds and 57 ActionIds: 9 active
and 48 planned. All 20 existing revised-spec submission/review actions remain
planned, the four later REV additions remain absent, and all 24 REV dependencies
remain inactive. The later AUTH-owned migration is therefore exactly 57-to-61,
producing 9 active and 52 planned without activating an action early.

AUTH evidence records 275 focused behavior tests at 90.17 percent branch-aware
focused coverage, 17 isolated Alembic tests, final Backend run `29481047118`,
PR-head Agent Gates runs `29481047119` and `29481057005`, final-head Agent Gates
run `29482246184`, and successful CodeRabbit.
The three former blockers are retained as regression invariants at every REV
consumer rather than unresolved AUTH work.

At this AUTH-08 refresh, ART PR #129 was open and conflict-blocked at
`a7432c87719e694038dae5b386b7c9b3ecf9e9b4` despite green checks. PR #128 was
parked and unpushed. Final PLAN publication review and exact-SHA evidence binding
were deferred until ART merged and its contracts were reconciled from trusted
main.

## ART-02A2 Dependency Refresh - 2026-07-16

`git pull origin main` rebased the five local REV planning commits without
conflict onto trusted main `9a04434e2f23c5dec8939dadb943bba4d85110c0`.
That merge commit is ART-02A2 PR #129; its final branch head is
`32aab89262a3944f305e9e5dc4c65a2d31e2e144`.

REV reviewed the merged ART contract, implementation, tests, internal evidence,
external response, and downstream ART chunk gates. ART-02A2 establishes only an
inactive committed-source/private-scratch preparation boundary. It changes no
active ArtifactStore v1 interface, provider selection, schema, product route,
action, permission, reviewer packet read, or evidence-intake behavior.

The boundary is compatible with REV only by remaining behind ART-owned future
capabilities. REV never imports `ArtifactScratchManager`, `PreparedArtifact`, or
`CommittedArtifactSource`; stores scratch paths, ledger reservations, or source
descriptors; or creates an alternate preparation manager. Later ART v2,
MinIO/AWS S3, admission, verification/publication, read/intake/retention,
recovery, checker, projection, and live-proof chunks remain hard runtime gates.

ART evidence records 154 focused tests at 94.40 percent scoped coverage, 38
isolated artifact PostgreSQL tests, 207 isolated AUTH/authentication/Alembic
tests, final Backend run `29487194049`, Agent Gates runs `29487194116` and
`29487194180`, and successful CodeRabbit. PR #129 is merged, so the planning
publication dependency is resolved. PR #128 still requires current-snapshot
internal review, exact reviewed-SHA evidence binding, branch update, and fresh
external checks before human merge.

## PR #128 External Review Response - 2026-07-16

The refreshed PR passed Backend, Agent Gates, and CodeRabbit status checks, but
a thread-aware audit found eight unresolved actionable CodeRabbit comments.
Every comment was valid and in scope. The plan was repaired to:

- add the exact WS-IMP archival pair to REV-01 allowed scope;
- clarify the merged WS-CON compensation-policy prerequisite for REV-03;
- require TaskService route, checker-execution, and composition-path proof in
  REV-05 and correct `later-admitted` wording;
- define submitter chain ownership through the canonical contributor on the
  exact Submission-associated TaskAssignment;
- add explicit API-contract/OpenAPI absence proof to REV-07 and REV-09A; and
- expand REV-13 final conformance tests and lifecycle-control package coverage.

No comment is deferred. The detailed thread mapping is recorded in
`reviews/WS-REV-001-PLAN-external-review-response.md`. Because these are
non-evidence planning-contract changes after the prior reviewed SHA, required
internal reviewer tracks and exact-SHA evidence binding must run again before
the branch is republished.

## WS-XINT-001 Boundary Reconciliation - 2026-07-17

The branch rebased without conflict onto trusted main
`5d353b6d3f8a36b9b9ffdc1959487a150ac25fd1`, merge commit for WS-XINT-001 PR
`#139`. Its ADR 0015 and AUTH/REV, AUTH role/service, ART/REV, and REV/CON handoffs
supersede conflicting active REV planning wording. The archival WS-REV Markdown
and PDF remain provenance inputs, not authority over merged boundary decisions.

Three read-only discovery reviews failed the pre-reconciliation plan and found
the same material drift:

| Review | Result before repair | Required correction |
|---|---|---|
| Architecture | FAIL | AUTH-only activation custody; prepared mutation order; ART v2 ports; no CON or ART repository ownership |
| Security/auth + product/ops | FAIL | Independent exact reviewer grant; role-specific invalidation; fixed AUTH-09E services; canonical task effects |
| ART + CON integration | FAIL | REV-owned packet/evidence relations; two-phase binding; mandatory flush-only CON participant; stable artifact lineage |

The reconciled plan now requires registration -> hidden behavior -> AUTH
activation -> REV product release, derives future action totals from trusted
main, and keeps the four proposed REV actions separate from ART's proposed
`artifact.review_evidence.binding.create` action. It uses request-scoped AUTH
for reads and the AUTH-first prepared protocol for mutations.

ART v2 is the only future provider boundary. REV owns
`ReviewPacketManifest` and `ReviewEvidenceArtifact` while ART owns bytes,
bindings, candidates, finalization, and providers. The currently merged ART
plan does not schedule `WS-ART-001-REV-EVIDENCE`; REV-07 is blocked until ART
adds, approves, and merges that owner chunk.

Review authority requires one exact active `reviewer` grant. Reviewer
invalidation changes only review preference, lease, and queue state. Six
protected review jobs use separate fixed AUTH-09E identities for preference
expiry, lease expiry, authority-invalidation reconciliation, general review
reconciliation, artifact-reference reconciliation, and projection. Human
Operator authority is never borrowed as a job identity.

REV-08 now freezes the decision contract without committing a canonical
Review. REV-10 creates the first canonical Review transaction only after the
CON flush-only participant is merged. At that historical snapshot, every Review
created a reviewer ContributionRecord and the submitter record was triggered
directly by `accept`; the later FinalAcceptance amendment below supersedes that
trigger. CON performs no ART call. The plan interprets the handoff's versioned Submission lineage as
the repository's existing immutable versioned `Submission`, requiring the ART
cutover to stabilize server-derived `Submission.artifact_hash` before CON copies
it to `ContributionRecord.artifact_hash`. Optional contribution-evidence
projection is outside the core transaction and release gate.

Human reject moves the task to canonical `rejected`; approved administrative
limit/deadline or unrecoverable-legacy closure moves it to `cancelled` with an
exact reason. No `closed/review_rejected` status is introduced. REV-13 exposes
only REV-owned surfaces after AUTH activation and CON-owned readiness; it does
not edit or register CON routers.

All earlier exact-SHA PLAN review evidence is historical after this material
change. Fresh senior engineering, QA/test, security/auth, product/ops,
architecture, docs, reuse/dedup, test-delta, and CI-integrity review plus a new
snapshot binding are required before PR #128 is republished.

## WS-XINT Final Review Repair Cycle - 2026-07-17

Final review of immutable snapshot `a916692` failed senior engineering,
architecture, QA/test, product/ops, security/auth, and docs while passing
reuse/dedup, test-delta, and CI integrity. Every substantive failure was valid:

- REV-10 named a lifecycle fence that did not exist until REV-12A;
- active gates named unmerged sibling CON chunk numbers as though canonical;
- ART packet-read and `Submission.artifact_hash` had no approved owner chunk;
- REV-06/07 omitted their composition-root wiring scope;
- materially changed non-review modules were missing from 90-percent coverage;
- cross-project current-work behavior was ambiguous under global lease capacity;
- claim preflight/finalization order did not fully state AUTH-first preparation;
- cross-scope artifact errors could disclose guessed binding existence;
- current stale wording scanners failed on retired terminology; and
- trust/evidence scope remained bound to the pre-XINT publication.

The repair makes hidden pre-12A claim/evidence/decision services inaccessible
from public/background command entry points and gives them executable AUTH-first
orders without a fence. REV-12A later inserts the fence before REV-13 release.
CON dependencies are capability-and-SHA gates until their owner merges exact
contracts. ART packet-read, review evidence, and server-derived Submission hash
are explicit owner amendments, with REV-07/10 blocked until merge. REV-06/07
wire typed ports only through the existing composition root. Coverage commands
now name every materially changed module, composition path, and runtime job.

Selected-project current work returns `none` without disclosure when global
capacity is occupied in another project. Preliminary artifact preflight is
authority/concealment-gated; the final transaction follows AUTH authority lock,
REV locks/final facts, one AUTH evaluation, participant flush, and one caller
commit. Cross-scope, unauthorized, and nonexistent bindings are
concealment-equivalent; detailed availability/integrity errors require proven
in-scope authority.

The implemented Workstream, AUTH, and ART stale scanners pass after terminology
repair. The future REV scanner remains a REV-01 deliverable and is not claimed
as current proof. The repaired snapshot still requires fresh exact-revision
review and evidence binding before publication.

Second review of `93955f1` confirmed the substantive lifecycle repairs but
rejected split shell tokens used in proof commands to avoid false positives for
literal technical paths/flags. That finding was valid. The commands again use
canonical technical execution-package paths and live-drill flags. The shared
AUTH documentation scanner now has a narrow, tested classifier for those exact
technical forms while continuing to reject human contributor-role vocabulary.
The planning chunk explicitly owns this CI gate change
and requires CI-integrity review. The same pass also found and repaired one
remaining stale lifecycle-fence reference in `CON_INTEGRATION_REVIEW.md`.

Third review of `15c6aa7` passed every product and architecture track but found
that the exact live-drill CLI classifier accepted a suffixed `-beat` near miss.
The matcher now requires end-of-token or whitespace after `-beat`, and negative
regressions reject suffixed variants of both allowed flags. No broader exemption
or test weakening is permitted.

## FinalAcceptance Boundary Amendment - 2026-07-17

After the prior publication snapshot, the human approved a material lifecycle
amendment: every reviewer decision remains an immutable Review, every submitted
finding and later resolution remains immutable, and later rounds append rather
than rewrite. When a Review decision is `accept`, REV additionally creates one
immutable FinalAcceptance. CON creates `accepted_submission` only from that
fact; `completed_review` remains directly sourced from every Review.

The human also clarified transaction ownership: the review request owns the
single transaction, CON is a flush-only contribution and award participant, and
REV stages shared audit and outbox rows. Later AUTH reconciliation made the
mechanical owner explicit: the request route or service command owns the caller
`AsyncSession` and sole commit. No ART or provider call is allowed in the
transaction. Adjudication remains disabled for v0.1;
dormant interface compatibility does not authorize adjudication behavior or
readiness.

Initial amendment wording used the phrase "accept-only immutable
FinalAcceptance." The human correctly rejected it as ambiguous because it could
suggest that only accepted Reviews are immutable. The plan now states the two
independent rules explicitly throughout: every Review, submitted finding, and
later resolution is immutable, while FinalAcceptance is an additional immutable
record created only when the new Review decision is `accept`. The lock
choreography was also corrected: FinalAcceptance is appended after the Review;
it is not an existing row in the pre-write lock set.

This material change invalidates the prior exact-SHA publication evidence.
Fresh deterministic gates and all required internal reviewer tracks must pass on
a new immutable snapshot before PR #128 is refreshed.

### First amendment review of `8e4d376`

Senior engineering and architecture failed the snapshot because normative flow
text applied the decision branch before creating and evaluating the mandatory
reviewer `completed_review`. QA/test also required the final live drill to prove
the full positive and negative contribution-source matrix for all three
decisions. Product/ops rejected remaining `Review/FinalAcceptance` shorthand
because it could imply that every Review creates FinalAcceptance. Reuse/dedup,
test-delta, security/auth, docs, and CI integrity passed.

The repair keeps one injected CON participant but gives its two operations
explicit purposes and a fixed order in the caller-owned transaction. The
reviewer operation creates `completed_review` and evaluates the reviewer policy
after immutable review history is appended and the lease and queue entry are
closed. REV then applies the decision branch. Only `accept` appends
FinalAcceptance and invokes the submitter operation, which creates
`accepted_submission` and evaluates the submitter policy. REV stages audit and
outbox records after the branch and commits once. REV-13 now proves all three
contribution source shapes, negative cardinalities, Task and TaskAssignment
outcomes, the exact write order, and rollback after the reviewer operation or
any later stage.

### Second amendment review of `370fb54`

Senior engineering, architecture, security/auth, docs, QA/test, and product/ops
rejected one remaining omnibus-input paragraph in `DECISIONS.md`. It still
carried nullable FinalAcceptance and one unspecified frozen policy context,
which contradicted the ordered reviewer and submitter operations. Reuse/dedup,
test-delta, and CI integrity passed. QA/test and product/ops also found that the
reviewer contribution shape did not explicitly require
`source_task_assignment_id` to be null.

The repair defines two non-interchangeable typed inputs. The reviewer operation
always receives Review and ReviewLease lineage plus the lease-frozen reviewer
policy and never receives FinalAcceptance or submitter policy facts. The
submitter operation exists only after `accept` creates FinalAcceptance and
receives FinalAcceptance and TaskAssignment lineage plus the assignment-frozen
submitter policy. The canonical checks and final drill now require both
acceptance-source fields to be null on reviewer contributions and both direct
review-source fields to be null on submitter contributions.

### Final amendment review of `3ef72b9`

Senior engineering, architecture, reuse/dedup, QA/test, product/ops,
test-delta, security/auth, docs, and CI integrity all passed with no findings.
The reviewers confirmed that the two operation-specific inputs, all-decision
immutability, accept-only FinalAcceptance, mutually exclusive contribution
sources, exact branch effects, guide-context rules, no-ART transaction boundary,
atomic rollback, and dormant adjudication boundary are consistent across the
plan and chunk contracts.

## FinalAcceptance Refresh External Review - 2026-07-17

CodeRabbit thread `PRRT_kwDOSwL_U86Rr721` found that the release controller
required fulfillment work to be zero before entering `delivery_draining`, while
the live drill expected fulfillment work to drain during that phase. The first
repair made the phase reachable by allowing fulfillment dispatch and callbacks
through `delivery_draining` and moving the complete zero-obligation guard to the
transition into `disabled`.

Internal security review then required a durable boundary between eligible
drain work and post-cutoff work. CON now owns a monotonic ordinal for each
immutable fulfillment-obligation root and allocates it only after acquiring the
shared lifecycle fence. The exclusive transition into `commands_draining` waits
for prior writers and stores the CON-derived maximum ordinal as the generation
cutoff. During `delivery_draining`, dispatch and callbacks are completion-only
for same-generation roots at or below that cutoff.

Subsequent internal review added every CON root creation, requeue, successor,
and repair writer to mandatory fence composition and both-order race proof. It
also aligned the exact command-class token and corrected denied already-claimed
dispatch behavior: bounded denial audit is retained, no successor or provider
I/O occurs, and only the shared dispatcher's idempotent same-root
claim-to-retryable recovery may change outbox state. High-level PLAN, DECISIONS,
CON integration, dependency, risk, chunk, and live-drill wording now state the
same contract.

Exact snapshot `615964e16e9f03257fc8631f5af8e35544c01f81` passed senior
engineering, architecture, reuse/dedup, QA/test, product/ops, test-delta,
security/auth, docs, and CI integrity with no findings.

## AUTH PR #140 Reconciliation - 2026-07-17

REV rebased cleanly onto trusted main
`d541521790a0441cfd2193f466e00ef81248ec31`, merge commit for AUTH
reconciliation PR #140. That merge changes planning and authorization
documentation only; runtime remains 74 PermissionIds and 57 ActionIds, with 9
active and 48 planned. The 24 REV dependencies remain non-executable:
`submission.create`, 19 registered review actions, and four approved but
unregistered REV additions. The separate ART evidence-binding proposal is not
part of the 24.

Read-only AUTH/REV, catalogue, and post-rebase audits found seven material
planning gaps: unnamed AUTH custody/registration/activation gates; incomplete
prepared-handle binding and misuse proof; denial wording that could suppress
AUTH's clean denial evidence; ambiguous transaction commit ownership; missing
AUTH-13/14 contributor-field sequencing; generic fixed-service identity
assumptions; and a stale shared REV/CON handoff that still encoded the
pre-FinalAcceptance one-call transaction.

The repair names `WS-AUTH-001-REV-CUSTODY`, `WS-AUTH-001-PREP`,
`WS-AUTH-001-REV-REG`, every exact per-feature REV activation gate, and
`WS-AUTH-001-REV-LIFECYCLE`. The initial repair required exact session, ActionId,
actor-reference kind/ID, idempotency key, and canonical request-digest binding
before feature mutation; the later review below corrected validation and
consumption ownership to AUTH.
Normal denial rolls back feature effects while AUTH may persist only its bounded
unchanged denial evidence through the clean AUTH-owned restaging protocol. The
request route or service command owns the one commit; REV remains lifecycle
orchestrator and stages shared audit/outbox rows. REV-02 waits for AUTH-13/14
schema ownership, and each protected service identity requires a reviewed
identity-to-ActionId manifest before AUTH provisioning.

The planning chunk's scope now includes only the exact shared
`REV_CON_HANDOFF.md` amendment requested by the human. That handoff now records
immutable FinalAcceptance, the ordered reviewer and accept-only submitter CON
operations, canonical versioned `Submission.artifact_hash`, REV audit/outbox
staging, and request-route/service-command commit ownership.

The rebase and these normative edits invalidate pre-rebase exact-SHA evidence.
Fresh deterministic gates and every required internal reviewer track must pass
before PR #128 is force-updated.

### First AUTH reconciliation review of `777468d`

Senior engineering, architecture, QA/test, product/ops, security/auth, and docs
failed the snapshot. Reuse/dedup passed; test-delta and CI integrity passed with
the condition that exact-SHA evidence be rebound after repair.

The reviewers found three executable-graph defects. Full AUTH-13/14 were placed
before REV-02 even though their own contracts require revision/replacement
behavior owned by downstream REV-09A. `WS-AUTH-001-REV-REG` and exact service
identities were prerequisites for chunks that appeared to produce their own
registration/identity manifests. Final release also omitted AUTH-14 activation
of `submission.create`, despite counting it among the 24 REV dependencies.

The repaired graph requires AUTH to split and merge a schema-only
contributor-field foundation before REV-02. REV-09A then publishes hidden
prepared revision/replacement behavior; amended full AUTH-13/14 cutovers and
AUTH-14 `submission.create` activation follow before REV-13. REV-01's merged
active contract is now the immutable four-action registration manifest and the
six exact service identity-to-ActionId manifests, so AUTH may register planned
rows and provision identities before consuming chunks without claiming hidden
behavior exists.

Security review also found that REV-12A consumed PREP before fence/domain locks
and final fact recomposition, and several chunks conflated prepared-handle misuse
with evaluated denial. The repair restores AUTH prepare -> feature locks and final
facts -> AUTH-owned handle validation/consumption/evaluation/evidence stage ->
feature mutation -> participant flush -> request-route/service-command commit.
At that snapshot, protocol misuse was still described too broadly; the later
review below separates rejected pre-consumption substitution from an already-
consumed replay. Evaluated authority/policy denial rolls back
the dirty caller transaction, restages unchanged bounded AUTH denial evidence in
a clean transaction, and commits that evidence once through the request route or
service command. Feature/shared audit/outbox effects remain absent and restaging
failure commits nothing.

Finally, the repair removes remaining REV-owned-commit wording, aligns PLAN risk
to L1, records the now-passing loop-memory gate, and makes registered/planned
status consistent in REV-12A.

### Second AUTH reconciliation review of `4084cd4`

Senior engineering, architecture, QA/test, product/ops, security/auth, and docs
failed the snapshot. Reuse/dedup, test-delta, and CI integrity passed.

The PREP proof incorrectly grouped an already-consumed replay with a rejected
wrong-binding or forged attempt and then promised that every rejected handle
could receive a later first use. The repair now proves three separate outcomes:
pre-consumption substitution/forgery stages no state and preserves the legitimate
handle for one later exact first use; stale, already-consumed, and concurrent
duplicate use stages no new state and never becomes valid again, with exactly one
concurrent winner; evaluated authority/policy denial uses dirty rollback and
clean unchanged AUTH evidence restaging. REV only locks feature rows and
recomposes final facts. AUTH alone validates bindings/current authority, consumes
once, evaluates once, and stages decision evidence.

Architecture review also found that REV-12A/13 still assigned the mandatory
preparation-transfer binding, legacy replacement removal, strict revision
migration, and prepared submission cutover to REV-13 even though amended full
AUTH-13/14 were prerequisites. Those cutovers now own their commands, binding,
migration, and hidden behavior after REV-09A. REV-12A classifies and fences them;
REV-13 verifies the exact merged capabilities and only exposes them through the
joint lifecycle transition. REV-01's last stale commit statement now assigns
orchestration and shared audit/outbox staging to REV while the request route or
service command owns the caller session and sole commit. Ambiguous action-table
and PR #140 status wording is also corrected.

### First re-review of `2146b8c`

QA/test, product/ops, and test-delta passed. Senior engineering, architecture,
security/auth, and docs found one deeper AUTH-14 ownership contradiction in
REV-09A and an unstated ordering assumption in REV-12A; reuse/dedup and CI
integrity remained passing.

The repaired REV-09A contract now lands only nullable/conditional preparation
schema and hidden preparation behavior. Amended AUTH-14 owns the strict
`NOT VALID` guard, legacy submission-branch removal, prepared branch, and their
atomic route/schema cutover while `submission.create` remains unavailable;
REV-13 only verifies and exposes the merged result. Risk R30 states the same
owner split. REV-12A is behavior-neutral about whether its fence foundation or
amended AUTH-13 merges first: it classifies the exact owner-installed command
mode, while active and later generations require prepared mode. REV-11's early
choreography now also names AUTH as the sole binding validator, handle consumer,
evaluator, and evidence stager.

## AUTH-09A PR #132 Reconciliation - 2026-07-17

REV rebased cleanly onto trusted main
`299363af5d9e8a68bcc9b17457188048483caeed`, merge commit for AUTH-09A PR #132.
The merge advances the migration head to `0023`, adds the common fixed-service
enum/schema, closes the current set at seven ART service identities with eleven
exact memberships, and adds eight planned AUTH-09 route actions. The current
catalogue is 74 PermissionIds and 65 ActionIds: 9 active and 56 planned.

This merge does not provision a service ActorProfile/link, admit a service
token, activate an action, or add any REV identity. The 24 REV dependencies
remain unavailable: planned `submission.create`, 19 planned review actions, and
four approved but unregistered additions. REV's six protected job identities
remain separate AUTH extension work driven by the immutable REV-01 manifests;
each needs exact enum/constraint/matrix coverage, AUTH-09B provisioning,
AUTH-09E admission, cross-service denial proof, and the later action-activation
gate. No catch-all service identity is introduced.

The refreshed plan treats AUTH-08's 57/9/48 count as historical and AUTH-09A's
65/9/56 count as current-main evidence, not as a promised later total. It also
updates the discovered migration/test inventory and preserves the previously
reviewed PREP, FinalAcceptance, transaction ownership, revision rebase, and no-
adjudication boundaries. The exact `7a76da2` approval predates this rebase and
must be replaced by fresh exact-SHA review and evidence before publication.

## WS-REV-001-01 Start And Plan Review - 2026-07-17

PR #128 merged as trusted main
`0302bcf854a565d429e232ad6b076a1931ea74e4`, and the user explicitly started
`WS-REV-001-01` from that exact base on branch `codex/ws-rev-001-01`.

The initial L1 plan review passed with conditions. The contract was amended to
name the complete active-document surface, forbid all four archival inputs,
require literal hashes plus exact trusted-base diffs, specify the fail-closed
scanner classifier and fixtures, publish exact four-action and six-service
manifests, reconcile initiative state, and require exact-SHA internal evidence
plus a changed-path audit. The amended contract then passed plan re-review.

Deterministic evidence later exposed random WeasyPrint font-subset bytes. The
render scope was amended to include `render_pdf.sh`, fix the PDF identifier,
and embed full fonts. Plan re-review then found that the renderer rewrote four
unchanged context PNGs outside Chunk 01 scope. The renderer now compares pixels
through temporary outputs and preserves existing target bytes when unchanged;
verification also binds all four paths to trusted base `0302bcf`. Consecutive
renders produced identical lifecycle PDF and PNG hashes without changing a
context image. The repaired L1 contract passed final plan review.

Implementation remains specification and gate work only. No runtime endpoint,
authorization availability, artifact capability, contribution behavior,
adjudication behavior, or reputation mutation is introduced.

## WS-REV-001-01 First Exact-SHA Review - 2026-07-17

Candidate `06548c56e9db63e7f73c581c2c974a3ce798ba2f` passed deterministic
evidence but failed senior engineering, architecture, QA/test, product/ops,
docs, test-delta, and CI-integrity review. Security/auth and reuse/dedup passed.

The valid findings and repairs are:

- Added active ADR 0003, the Project Guide template, and three README-linked
  roadmaps to Chunk 01. They now remove automatic revision rejection,
  policy-selected latest-context rebase, legacy finding severity/closure,
  direct Review-to-submitter contribution, active reputation, and product
  second-review assumptions.
- Moved `task_assignment_id` from Assignment to immutable Submission, removed
  policy-selected rebase fields, added ReviewEvidenceArtifact, and corrected
  FinalAcceptance, contribution-source, blocking-finding, reputation, and
  adjudication model invariants.
- Made the decision transaction commit before later revision preparation,
  contributor response, replacement Submission, and checker work in both
  sequence sources; regenerated the lifecycle image and architecture PDF.
- Added `NEEDS_REVISION -> CANCELLED`, prohibited direct acceptance from
  revision, required CheckerRun-rooted automated revision, removed pre-submit
  revision-lane wording, and made reject findings optional beside its bounded
  human reason.
- Added planned/unavailable status to queue, first-user-flow, compensation, and
  roadmap surfaces. Initiative state now finishes Chunk 01 and stops before 02.
- Replaced filename-only scanner admission with fail-closed classification for
  every docs file, exact reference/archive handling, local structural
  exceptions only, and adversarial tests for keyword decoys, unrelated
  negation, legacy severity, direct contribution, and unclassified copies.

The repaired scanner passes across the full active docs tree and the expanded
agent-gate suite passes 85 tests. A new exact-SHA review is required; the failed
candidate is historical evidence only.

The roadmap scope amendment also records that neither ignored local roadmap
export existed at start or after repair. The contract fails closed if an XLSX or
CSV appears without its paired export, exact one-sheet name, current Workstream
definition, and ignored/untracked status. No spreadsheet file is committed.
The expanded L1 chunk contract then passed final plan re-review with no
remaining scope or proof blocker.

A later repeat-render proof showed that ImageMagick SVG antialiasing can change
context-diagram pixels across invocations, which also changes the composed PDF.
The renderer default now rebuilds only Chunk 01's lifecycle PNG and PDF; full
context regeneration requires explicit `--all`. The four context images are
restored and remain trusted-base bound.

## WS-REV-001-01 Second Exact-SHA Review And Repair - 2026-07-17

Candidate `0a0be1acd870f769ac5d27661a01d45ce3b402b6` failed the grouped
senior-engineering/architecture, QA/product/test-delta, and
security/docs/CI-integrity reviews. Reuse/dedup remained passing. The failed
candidate is historical evidence only.

The valid findings produced this repair:

- reconciled all three active roadmaps and the Project Guide template to
  immutable finding responses/resolutions, decision-specific evidence, the
  FinalAcceptance contribution matrix, payable-only awards, and deferred
  reputation;
- removed remaining automatic-reject, mandatory second-review, overturned-
  decision, and adjudication-like product semantics from active decision,
  risk, data-model, operations, and diagram surfaces;
- expanded the fail-closed scanner and adversarial fixtures for spaced legacy
  closure, plural automatic rejection, unconditional payment, passive
  reputation, direct-contribution decoys containing FinalAcceptance, and mixed
  reviewer-rebase negation;
- separated concealed `review.queue.read`, `review.claim`, and
  `review.decision` operations, with fresh token verification, AUTH PREP,
  canonical lock/recomposition order, exact handle validation/consumption,
  evaluation, and staged evidence before the first feature mutation; and
- regenerated the two context diagrams whose v0.1 reputation content changed,
  while the Workstream context and future identity/payment/reputation images
  remain byte-bound to trusted base.

The amended L1 contract added the affected active sources and generated files
to allowed scope. Its final plan re-review passed after the renderer was made
portable and deterministic: it requires the repository-standard PlantUML
1.2026.6 jar, verifies SHA-256
`89948f14c93756c7a3fb7b69078ff37e8489fd79dd430c582b931e2f65358690`,
uses that jar unconditionally, fixes `SOURCE_DATE_EPOCH`, strips lifecycle PNG
metadata, and exposes explicit `--review-context` source-to-SVG-to-PNG
rendering. Two complete pinned render passes produced identical SVG, PNG, and
PDF hashes.

The repaired stale-review and stale-workstream gates pass, the expanded agent
gate suite passes all 85 tests, archival literal hashes remain exact, and both
local roadmap exports remain absent. A new committed exact-SHA candidate and
full internal reviewer fanout are still required before PR publication.

## WS-REV-001-01 CON PR #142 Main Reconciliation - 2026-07-17

Candidate `9b2fc11c12e8c0cb19914c9772f95ba4e9814688` later passed all nine
required reviewer tracks and its evidence gate. Before publication, CON planning
PR #142 merged to main at `a947b8693a97bdb94c9dc63202a51e197834d613` from
branch head `4b13c3ee28ecddd7c92be70ad2059c130604f9d1`.

`git pull --no-rebase origin main` exposed conflicts in 15 shared active
documents. The reconciliation retains CON's exact reviewer/submitter operation
shapes, frozen-policy award rules, source constraints, and joint transaction
boundary while preserving REV's blocking/advisory finding model, optional
reject findings, deterministic revision preparation, deferred reputation, and
no-adjudication v0.1 boundary. The newly supplied CON reference Markdown is an
exact historical path in the fail-closed review scanner: it is a noncanonical
working transcription, not an archival or runtime-authority input.

PR #142 contains planning and documentation only. It activates no CON or REV
runtime behavior. Because current-main reconciliation changed review-relevant
files, the earlier exact-SHA PASS is historical and a fresh full reviewer pass
is required on the merge candidate.

## WS-REV-001-01 Current-Main Candidate Repair - 2026-07-17

Exact candidate `1c7c3e75cffbe91a44d5cd10d333a5ec0fcf1fd4` passed the
current-main plan review but failed the first full reviewer fanout. Senior
engineering, architecture, QA, and product/ops found that three active
operational workflows inverted or ambiguously described the canonical reviewer
CON operation, FinalAcceptance, task-effect, and submitter CON operation order.
They also found an optional human simulation inserted into automated checker
admission, an undefined disputed-reject owner, and missing planned/unavailable
review-lifecycle status in the operator workflow.

The repair aligns every numbered accept workflow to Review and lease/queue
closure -> reviewer CON operation -> FinalAcceptance -> accepted task and
completed assignment -> submitter CON operation. Submitted-work admission is
now a mandatory durable CheckerRun decision; human judgment begins only with an
immutable Review. Terminal-reject sampling is explicitly non-mutating and has
no dispute, reopen, or adjudication path. Focused scanner fixtures and
structural workflow-order tests prevent recurrence. Candidate `1c7c3e75` is
historical failure evidence; a new exact-SHA full reviewer fanout is required.

The first repair candidate `e2797fb1` then failed the repair-cycle plan gate:
the two structural tests were not registered in the custom runner, payment
wording left task effects versus the submitter operation implicit, and a global
accept-order regex rejected valid branch-scoped prose. The follow-up registers
both tests, raises the executed gate count, asserts the complete payment order,
and removes the overbroad regex while retaining exact human-admission and
disputed-reject protections.

Candidate `76ed3c14` passed the repaired plan gate and eight of nine full-review
tracks. The docs track then found two remaining active-flow contradictions:
Flow 4 used severity/no-blocker shorthand instead of exact durable, final,
current `allow_review` admission, and generic Flow 6 applied Review-rooted
revision records to checker-caused remediation. The repair binds Flow 4 and
Flow 5 to the exact admitting CheckerRun, keeps setup/provenance defects on
`evaluation_pending` / `task_setup_blocked`, scopes Flow 6 to immutable
`Review(needs_revision)`, and states that checker remediation has only
CheckerResult lineage and returns through the normal submission/checker spine.
The registered structural test now covers these distinctions.

The follow-up plan gate accepted the active prose and required the regression
to bind Flow 5's verified facts and every checker-forbidden Review record or
reviewer contribution explicitly. The final fixture scopes those assertions to
the checker-remediation `creates no` clause.

## WS-REV-001-01 AUTH-09B Main Reconciliation - 2026-07-18

After candidate `df098f203fae4982806568dcc25a81043d9f7211` passed all nine
tracks, AUTH-09B PR #143 advanced main to
`053242b90d927ace3fab92eeca72da27a61cecec`. The branch pulled that merge
cleanly. Only `scripts/test_agent_gates.py` overlapped, and Git retained both
AUTH's new gates and REV's registered 87-test baseline without conflict.

AUTH-09B activates only `actor.service.provision`, changing the current
catalogue snapshot to 74 PermissionIds and 65 ActionIds split into 10 active and
55 planned. It supplies controlled provisioning for AUTH's existing closed
identity registry but adds none of REV's six future identities, admits no
service token, and activates no review action. All 24 REV action dependencies
remain unavailable. The prior exact-SHA PASS is historical; the reconciled
candidate requires fresh deterministic and full reviewer evidence against
`053242b`.

## WS-REV-001-01 PR #145 Initial External Gate - 2026-07-18

PR #145 opened from head `9ad0420e`. GitHub Agent Gates failed only at the
schema-v2 merge-intent validator because the existing `WS-REV-001-02` contract
heading omitted the successor title declared by the exact REV-01 merge intent.
The repair adds that exact title to the heading without changing successor
scope or starting Chunk 02. CodeRabbit reported a review-limit cooldown and
produced no findings.

## WS-REV-001-01 CON-01 Main Reconciliation - 2026-07-18

While PR #145 replacement Backend was running, CON-01 PR #144 advanced main to
`e118e33afcd89b8ee78ecfc8f0e0d585ae0ee4b9`. The branch pulled it and resolved
one `architecture_data_model.md` conflict by retaining the exact shared
FinalAcceptance fields plus explicit canonical reviewer ActorProfile and
immutable ReviewPolicy foreign-key semantics.

CON-01 now publishes `docs/spec_contribution_compensation.md` and ADR 0016 as
canonical CON authority. It confirms REV's one-commit transaction, ordered
reviewer/accept-only submitter operations, FinalAcceptance-only submitter
trigger, frozen policies, and no ART call. It adds no runtime. The prior PR
candidate and replacement checks are historical; fresh exact-SHA internal and
external gates are required against `e118e33`.

The first CON-01 reconciliation plan gate found one stale central PLAN paragraph
that still called the older WS-XINT handoff current and treated CON as unmerged
sibling evidence. The repair names merged CON-01 `e118e33`, its active
specification, and ADR 0016 as canonical authority while retaining XINT only as
historical supporting context and preserving every downstream runtime gate.

## WS-REV-001-01 Final Scope Verification Repair - 2026-07-18

After ART-02A3 reconciliation and a fresh nine-track PASS, CodeRabbit correctly
reported that the final path listing did not fail on unexpected scope. Candidate
`7742730` added a committed path allowlist and documented why trusted current
main `a10d901` defines PR scope while planning base `0302bcf` remains the
archival byte-integrity anchor.

Internal security/docs/CI review then found that path-only comparison could not
distinguish an approved modification from deleting the same path. Candidate
`7785b832` replaces it with an exact 71-entry
`git diff --name-status --no-renames` A/M manifest. The exact comparison
passes; simulated status change, removal, rename as D+A, and addition each fail.
All deterministic gates and all nine exact-SHA reviewer tracks pass. The proof
is intentionally chunk-specific rather than a permanent global CI rule pinned
to one historical main SHA.

## WS-REV-001-01 AUTH-09C Main Reconciliation - 2026-07-18

AUTH-09C PR #146 advanced main to `0ffdabf3`. The branch merged it and resolved
the sole conflict in `scripts/test_agent_gates.py` by adopting main's current
AUTH-09C and merged ART-02A3 assertions while retaining REV's pre-merge ART
phase checks in their fallback branches. No test or assertion was removed.

AUTH-09C keeps 74 PermissionIds and 65 ActionIds, activating only
`actor.profile.read` and `actor.identity_link.read` and moving the split to
12 active / 53 planned. It adds no REV identity or action; all 24 REV
dependencies remain unavailable. The trusted PR-scope base is now
`0ffdabf3dbb77e4e066683fde1a095d744ff1f43`. Fresh deterministic evidence and
all nine exact-SHA reviewer tracks are required.
