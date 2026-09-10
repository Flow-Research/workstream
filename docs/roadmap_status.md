# Workstream v0.1 Roadmap And Capability Status

This is the public, human-readable source for what Workstream can do on
`main`, what is implemented but intentionally hidden, what we are building
next, and what remains before v0.1 is ready. It uses capability milestones,
not calendar promises.

**v0.1 is Workstream's first usable release: the minimum complete product, not
an expansion beyond an already-working MVP.** Individual backend foundations
are implemented, but Workstream is not yet usable through its complete governed
work lifecycle. The remaining v0.1 release requirements establish that baseline;
they are not optional enhancements to a finished product.

Implementation claims require merged code, migrations, tests, and review
evidence. A plan or open pull request is not implemented behavior. Open pull
requests are the transient view of work currently under review.

## Product Goal

Workstream turns governed work into trusted `ContributionRecord` facts:

```text
Project Guide
-> governed Task
-> artifact preparation and pre-submission intake checks
-> immutable Submission
-> post-submission evaluation against locked requirements
-> policy-governed acceptance: authorized human Review or automated decision
-> controlled Revision when required
-> Contribution Records
-> conditional Compensation Awards and Fulfillment
-> evidence for a future Reputation projection
```

The v0.1 release bar is one secured, observable, recoverable end-to-end path.
Authorization, locked project rules, exact artifact identity, attributable
policy-governed acceptance decisions, and durable contribution facts are necessary for that path to be
trustworthy. Integration and failure-recovery proof are part of making it
function correctly, not a later quality upgrade. This does not require every
future feature, an exhaustive cleanup of the codebase, or proof of unlimited
scale before first use; the release gates below define the bounded requirement.
Attributable human Review is required when the locked project mode requires it;
automated acceptance records its own authorized decision and evidence instead.

Marketplace expansion, blockchain settlement, external source adapters,
automated routing, agent workspaces, and runtime reputation projection remain
outside v0.1.

## Status Vocabulary

The automated-acceptance branch is a newly clarified **planned** v0.1
requirement, not a live capability. The existing versioned ReviewPolicy now
persists the setting: `human_review_required: bool = true`. True requires human
review after required checks pass; false leads to authorized FinalAcceptance
and submitter contribution without a reviewer contribution. It requires explicit locked project policy,
supported acceptance evidence, distinct service decision provenance and shared
atomic contribution effects; checker success alone is not acceptance. The
[canonical shared acceptance contract](spec_review_lifecycle.md#finalacceptance)
defines one FinalAcceptance/submitter-contribution operation with two triggers,
not a separate automated acceptance system. The human branch retains canonical
`allow_review`. Shared REV source persistence and CON participation precede
ARCH-04E false/pass integration; human queues/leases are not its prerequisites.

The setting is configurable through the existing authorized policy writer;
creation defaults true and omitted replacements inherit the predecessor.
Versioned hashing preserves old policy hashes and locks. False remains blocked
by the current activation service. See the [implementation record](../.commitrail/changes/pre-review-plan-reconciliation.md#delivered-policy-setting-implementation). Enabling false follows shared final-acceptance,
CON and exact AUTH integration proof, not live human-review infrastructure.
This allows an automated end-to-end milestone first; human review/revision
still belongs to the complete v0.1 release. See the
[product-builder handoff](../.commitrail/changes/pre-review-plan-reconciliation.md#product-builder-handoff-implement-the-setting-next).

| Status | Meaning |
| --- | --- |
| **Live foundation** | Merged behavior is available to its intended caller. It may still be only one part of a larger product flow. |
| **Hidden and proven** | Merged behavior exists and is tested, but no public production route exposes the complete flow yet. |
| **Next** | The next dependency-safe implementation boundary after current `main`. |
| **Planned** | The design direction is accepted, but its current skeleton must be refreshed into a bounded executable contract before coding. |
| **Deferred** | Deliberately outside the v0.1 runtime. |

## Executive Snapshot

Workstream already has strong backend foundations for identity, authorization,
projects, guide ingestion, immutable artifact storage, tasks, submissions, and
checker execution. The new unified Project Guide compiler and its two
deterministic projections are implemented behind hidden boundaries. The
contributor artifact path can prepare verified bytes, publish a ready
admission, create the immutable Submission, and bind it atomically, but its
public legacy cutover is intentionally deferred.

The current critical path is to finish one complete governed Project Guide
generation, lock its ContributionPolicyVersion into claimable work, and carry
one admitted Submission through a durable current post-submit checker result
with `routing_recommendation = allow_review`. That fact unlocks the live
review/revision path. Review decisions must then create contribution and
conditional compensation facts atomically before v0.1 can be released.

## Pre-Submission And Post-Submission Checking

Both stages enforce quality, but answer different questions and produce
different outcomes. They are not one combined checker phase.

The phase is distinct from the execution method. Intake primitives and policy
compilation can be deterministic without making every task evaluator
deterministic. Post-submit work evaluation may use deterministic rules or a
supported model/agent-based quality judge; recording its inputs and result does
not promise identical judgments on rerun. Such an evaluator needs an explicit
implementation and policy binding and is not claimed live here.

| Stage | Purpose and examples | Policy and execution boundary | Outcome |
| --- | --- | --- | --- |
| Pre-submission intake checks | Is this package acceptable to submit? Check completeness, required/forbidden files, evidence integrity, and configured intake-quality rules. | The locked `PreSubmitCheckerPolicy` and effective artifact policy drive the pre-submission catalogue during continuous artifact preparation, before a Submission exists. | Blocking failures return correction feedback and prevent Submission creation. Passing intake does not prove the task is accepted or ready for review. |
| Post-submission evaluation | Does the submitted work meet the configured task/project checks? Evaluate the exact stored work and evidence under the locked requirements. | The Submission-stamped `PostSubmitCheckerPolicy` drives the durable checker registry after immutable Submission creation. Only supported, registered checks execute. | Persist current evidence. Required success routes by the locked ReviewPolicy: true produces human `allow_review`; false invokes shared acceptance under TASK authority. CHECKERS never writes acceptance itself. Both routes remain planned. |

The unified guide agent proposes both sets of policy bindings in one setup
result. Trusted compilation, validation, and the governing approval path turn
those proposals into separate locked policies; setup inference is not a second
agent run judging a contributor's submission. An agent-based evaluator or quality
judge would require its own supported checker implementation and policy binding;
it is not implied to be live by the unified setup agent or the roadmap.

Authorized reviewers still own `accept`, `needs_revision`, and `reject`.
Only an actual human Review stores those decisions; neither checker stage
impersonates one. With locked false policy, TASK invokes the shared acceptance
operation without a Review. Pre-submission feedback
cannot be reused as post-submission review-gate evidence. See the
[checker architecture](architecture_checker_framework.md) and
[pre-submit versus durable contract](spec_chunk_8_submission_artifact_policy_checkers.md#pre-submit-versus-durable-runs).

## End-To-End Lifecycle Scoreboard

| Lifecycle stage | Status on `main` | What is already proven | What remains before v0.1 |
| --- | --- | --- | --- |
| Identity and actor resolution | **Live foundation** | Flow-token verification; canonical ActorProfile and ActorIdentityLink; human/service separation; lifecycle controls | Final end-to-end operational and conformance proof |
| Authorization kernel | **Live foundation** | Closed action/permission catalogues; deny-by-default evaluation; grants; fixed services; rate controls; opaque transaction-bound PREP; atomic decision evidence | Activate only the remaining owner-proven TASK, checker, REV, and CON boundaries; remove obsolete authority after replacement paths are live |
| Project Guide source custody | **Live foundation** | Project Manager original-document uploads; immutable metadata snapshots; exact run-scoped reads; S3-backed originals and isolated agent document inspection | Carry the same document generation through manager approval and guide activation; prove each enabled document reader |
| Unified Project Guide compilation | **Live automatic draft/findings setup** | Committed original-document readiness dispatches one immutable attempt through Celery; complete result and crash/recovery custody; distinct pre/post proposals; deterministic sufficiency and submission-artifact-policy projections; immutable authorized setup finalization | Add manager proposal review, correction, approval and manual rerun; add deterministic post-submit projection and one checker-service port |
| Contribution policy administration | **Hidden and proven** | Finance Authority adapter-binding lifecycle; ContributionPolicy read/create/update/publish/retire with exact Finance Authority; immutable operation and event history | Expose selected-policy validation, bind one published complete version to the active guide generation |
| Task readiness and claim | **Foundation plus planned replacement** | Task records, lifecycle guards, assignments, locked work context, public owner facts | A task must inherit the guide-bound ContributionPolicyVersion before `READY`; claim copies the prepared task context into TaskAssignment without a current-policy lookup; activate exact task authority |
| Contributor artifact preparation | **Hidden and proven** | One outer ZIP; bounded scratch inspection; canonical manifest; platform and project prechecks; unchanged-work rejection; durable put intent; verification; capacity-charged ready admission | Connect only the active unified guide/checker lineage and complete the later public admission-only cutover |
| Pre-submission intake checking | **Hidden and proven; unified-guide integration remains** | Separate versioned pre-submission catalogue, locked effective-plan compilation, platform/project checks during continuous preparation, and blocking feedback before Submission creation | Connect approved unified-guide pre-submit policy lineage through task/assignment preparation and complete the canonical public cutover; passing intake must never substitute for post-submit evaluation |
| Immutable Submission creation | **Hidden and proven** | Contributor preparation authority; atomic admission consumption; TASK-owned Submission creation; fixed-service artifact binding; replay/concurrency/rollback proof | Stamp the assignment's exact ContributionPolicyVersion and unified policy lineage; remove the legacy Submission path only after remediation and review prerequisites are ready |
| Post-submission evaluation and `allow_review` | **Planned; immediate integration milestone** | One canonical CHECKER post-submit catalogue/compiler used by existing consumers, hidden phase contracts and structural-handler conformance; existing pre-review and materialization foundations | Connect the unavailable phase port to durable execution; evaluate the exact Submission against its locked policy; persist one durable current superseding result; activate fixed services; automatically dispatch it and publish the canonical `allow_review` manifest |
| Review queue and lease | **Hidden persistence foundation** | Queue/admission idempotency and ReviewLease/preference persistence; complete unavailable REV action/principal catalogue and typed AUTH contracts | Packet-membership contract and manifest; Review schema; canonical admission from `allow_review`; claim/lease/packet authority; lease copies the Submission-stamped policy version with no CON lookup |
| Review decision and revision | **Planned** | Review/revision policy identities and mutation authority; approved same-task revision-rebase semantics | Immutable findings and decisions; `accept`, `needs_revision`, and `reject`; complete-context revision preparation; finding responses; replacement contributor rules; replay and recovery |
| Contribution and compensation truth | **Schema foundations plus hidden policy behavior** | ContributionPolicyVersion persistence; lifecycle-audit participant; adapter bindings; hidden policy administration | Persist ContributionRecord/CompensationAward and one shared FinalAcceptance/submitter operation for human accept or authorized false/pass routing. Only actual Reviews create reviewer records. Evaluate frozen actor rules into zero, one or two awards |
| Fulfillment, reconciliation, and audit | **Planned** | Shared audit foundations and provider-neutral adapter convention | Outbox/dispatcher authority, conditional award fulfillment, callbacks, idempotent recovery, reconciliation, bounded operational reads, and release controls |
| Frontend and pilot | **Planned after stable backend contracts** | React + Vite + TypeScript stack decision | Implement only stable backed surfaces, run the real internal pilot, repair findings, and complete release drills |

## What Has Been Completed

### Security and platform foundations

- FastAPI, SQLAlchemy 2.x async, PostgreSQL, Alembic, Celery, and Redis form the
  locked backend execution stack.
- The schema has one clean v0.1 Alembic baseline; later bounded migrations
  extend it without compatibility bridges for discarded pre-v0.1 history.
- AWS S3 is the hosted artifact target, MinIO proves the storage protocol in
  development and CI, and all storage access stays behind `ArtifactStore`.
- Private extraction scratch is bounded by `ArtifactScratchManager`; it is not
  durable artifact storage.
- Cross-module behavior is moving through explicit public ports under the
  modular-monolith boundary. New private edges are prohibited and touched debt
  is reduced incrementally.
- GitHub CI distributes the backend suite across semantic lanes, rejects
  skipped/deselected tests, preserves global coverage, and requires at least
  90 percent coverage for new or materially changed backend subsystems.

### Identity and authorization

- Workstream verifies external Flow identity tokens but owns no login,
  password, or primary authentication session.
- External subject identity resolves through ActorIdentityLink into a stable
  internal ActorProfile.
- Human roles and fixed-service authority remain separate and fail closed.
- Exact-project contributor grants support only `submitter` and `reviewer`.
  Unsupported `adjudicator` inputs are rejected; adjudication remains deferred.
- Project and administrative grants, resource guards, lifecycle revalidation,
  idempotency, rate controls, audit evidence, and opaque prepared authority are
  implemented.
- A reusable [real-HTTP authorization drill](engineering/external-api-drill.md)
  exercises twenty human profiles, the actual local administrator bootstrap,
  all five administrative role definitions and applicable scope boundaries,
  submitter/reviewer grants, self-protection, replay and lifecycle revocation.
  Separate rollback-only probes exercise the four last-effective-administrator
  count guards on stored authority; isolated off-by-one mutants verify that the
  assertions detect those defects. These are local synthetic-Flow checks, not
  deployed identity-provider certification or exhaustive API-field coverage.
- The [five API drill defects](engineering/external-api-drill-findings.md) are
  repaired: project name/slug and guide version enforce existing storage limits,
  guide PATCH now excludes the superseded inline-content field, and
  unsupported project-role input is rejected before mutation. Both original
  drills passed again on merged main after that repair. The extended drill adds
  populated pagination/cursor checks, nested qualification boundary probes and
  separate value/predicate/shape/request evidence. Remaining field combinations
  and provider-dependent flows still need client proof before inclusion in the
  MCP endpoint-and-field handoff; route discovery alone is not readiness.
  The public-client drill targets currently usable APIs only; hidden and
  unfinished lifecycle routes are not completion targets. Draft-guide policy
  probes additionally cover optional fields, conditional headers and exact
  selected-lineage preservation after rejection, including preservation of the
  human-review mode when omitted during replacement.
  Endpoint-by-endpoint probes also check exact health output, full self-profile
  business-state preservation after rejected updates, and contributor context
  actions/revocation with real foreign-project concealment. These strengthen
  evidence within the selected 29 canonical operations, not obsolete routes or
  an exhaustive API-completion claim.
  Catalogue evidence compares every registered permission and the full five-role
  definition matrix. Administrative grant probes compare complete provenance,
  reason and timestamp fields across issue/revoke replay, retaining independent
  stored-state checks. Catalogue membership does not imply action activation.
  Contributor-discovery drill checks enforce the privacy-safe two-field row,
  cursor scope/limit binding and exact candidate membership across existing
  actor/link lifecycle transitions. These checks do not equate discovery with
  contributor authority or certify the entire public API surface.
  Project-role field probes bind issuance and qualification capture to the known
  manager grant and compare complete public state across issue/revoke replay
  and conflicts for both submitter and reviewer roles.
  [API-DRILL-007](engineering/external-api-drill-findings.md#api-drill-007-embedded-nul-in-canonical-profile-fields-becomes-503)
  records the reproduced self-profile NUL defect and its repair: both editable
  fields reject the unsupported character at request validation with 422 rather
  than passing it to storage. The drill retains unchanged-business-state controls.
  [API-DRILL-008](engineering/external-api-drill-findings.md#api-drill-008-nul-project-selector-becomes-503)
  records the matching authorization-context selector repair: NUL is rejected
  with 422 while project-ID lookup and project concealment remain intact.
  [API-DRILL-009](engineering/external-api-drill-findings.md#api-drill-009-project-and-guide-text-nul-becomes-503)
  records the project/guide text repair: eight create/update fields reject NUL
  at request validation instead of returning a storage failure. Dedicated
  regressions check selected stored-state preservation, same-key recovery and
  replay. This does not certify the unfinished all-field external-client handoff.
  API-DRILL-006 is repaired with a bounded project-role issuance envelope that
  accommodates the existing public qualification maxima; other authority
  mutations retain their original limit. Full-max parser/PostgreSQL regressions
  cover both roles, persistence, replay, conflict and unauthorized rollback.
- Guide ingestion and exact document reads, artifact verification/recovery,
  contributor preparation, Submission consumption/binding, unified compilation
  request/execute, and deterministic projection authority are implemented at
  their current hidden or live boundaries.

### Project Guide and artifact pipeline

- Project Managers can authorize guide-source ingestion for projects they are
  permitted to manage.
- Guide originals remain immutable in ArtifactStore; PostgreSQL holds metadata,
  versions, custody and the required task-example list. Guide creation requires
  at least one nonblank example; a starting idea is sufficient and optional
  example fields do not repeat requirements from the guide. Each snapshot/run
  binds the exact version's examples. Upload admission checks bounded format, digest and size.
  Committed originals do not bypass the separate verification required for
  submission ZIPs. Inline markdown setup and extractors are removed.
- Committed original-document readiness automatically runs one unified compilation
  through Celery. It persists sufficiency findings and separate pre-submit and
  post-submit proposals, then projects the sufficiency and artifact-policy
  components and atomically finalizes the setup at draft output. A blocked guide
  ends at sufficiency evidence, with no policy projection. Its canonical result
  retains exact supported catalogue matches and one evidence-linked engineering
  suggestion for each required missing pre-submit or post-submit check. Fully
  covered projects need no suggestions. The manager-facing handoff remains
  part of POL-05; suggestions cannot register or activate a checker. Runtime, model/provider and instructions are independently
  configured and bound to the attempt. The agent opens assigned files on demand
  in an isolated workspace and assesses them with every supplied task example;
  exact grants exclude other projects and runs. Known
  invalid output ends terminally, and replay never starts a second inference.
  Transient pre-send retries use bounded backoff and a circuit breaker; the
  default request timeout is 300 seconds, separate from the whole-run timeout.
  Project Manager proposal review, correction and manual rerun remain POL-05.
  Superseded post-submit setup/approval/correction routes are removed; POL-06
  owns the remaining post-submit projection. Real Terra runs through API upload,
  MinIO, the Celery handler and PostgreSQL proved both blocked findings and ready
  draft policy outcomes, with exact replay and provider cleanup. Broker delivery
  was scripted in these drills; live Celery transport and broad semantic accuracy
  are not established by them. Earlier probes omitted task examples and establish
  execution mechanics only. A subsequent real Terra run with assigned private documents
  and two task examples proved exact example delivery, original access, persisted
  findings, cleanup and replay. It correctly stopped for absent project-wide
  file/archive size limits, without demanding one selected paper. This proves
  that bounded blocked-result flow; it does not establish a ready policy for
  those inputs or broad semantic accuracy. The dormant activation command is removed; active
  guide reads and locked policy consumers remain, with activation deferred to
  AUTH-12H.
- Contributor ZIP preparation uses one verified byte lineage from scratch
  inspection through durable admission and eventual Submission binding.

### Contribution and review foundations

- Finance Authority can manage compensation adapter bindings through the
  hidden, authorized boundary.
- Complete hidden ContributionPolicy draft/publication/retirement behavior is
  persisted with immutable lifecycle history. All five actions have exact human
  Finance Authority through explicit AUTH composition; default composition denies
  access and public policy routes remain unavailable.
- REV queue/admission and lease/preference persistence foundations are merged.
- The governing rule is fixed: one ContributionPolicyVersion contains both the
  `accepted_submission` and `completed_review` rules. It is bound before task
  readiness and carried as immutable attempt lineage.

## Current Work And Immediate Order

Only open pull requests describe transient work. Use the repository's
[open pull-request view](https://github.com/Flow-Research/workstream/pulls) to
see whether any item below is already under review.

Hidden unified-guide setup finalization and its exact authorization gate are
complete. ARCH-04A consolidation supplies one current post-submit catalogue,
compiler/parser and registered implementation per checker ID. Active consumers
validate the canonical policy body and matching stored summaries. Immutable
phase contracts and structural-handler conformance remain distinct from live
phase execution, which is still unavailable. POL-04B1 supplies hidden automatic
request authority and source-operation custody, with current-authority replay
checks for both triggers. POL-04B connects those contracts and unified
finalization to automatic initial setup execution, replacing the separate
inference methods and prompts. Runtime adapter, model and instructions are
independently configured. Compilation stops at findings and draft pre/post
policies. POL-05A is next: hidden complete-proposal review, correction and pre-policy
approval custody, followed by AUTH-12F4 and POL-05B live manager review,
approval and manual rerun through the same compiler. The reconciled
[dependency and ownership plan](../.commitrail/initiatives/WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
permits selected-policy validation independently after completed CP05. The
selected delivery order finishes unified setup, separate pre/post approval and
the POL-07 facade before returning to CP06/CP07 and AUTH-12H guide activation.
This priority adds no dependency on CP06 to live setup. Plans are not
implementation claims.
The sequence below describes product dependencies; production activation still
requires its exact owner-proven prerequisites.

The next dependency-safe product sequence is:

1. **Complete manager proposal review and correction.** Expose the complete
   unified result and preserve its distinct pre-submit and post-submit proposals.
   Authorized manual rerun creates a fresh generation through the same compiler.
2. **Complete guide policy approval.** Project Manager approval consumes the
   already-produced unified result; it does not run another agent. Persist the
   effective pre-submit policy and deterministically compiled post-submit
   policy, activate their narrow AUTH gates, and expose one typed checker-service
   facade. Approval/projection records reference immutable setup finalization;
   they cannot reopen or overwrite it.
3. **Validate and bind the selected ContributionPolicy.** CP05 completes
   authorization for the five hidden policy actions. CP06 supplies selected-policy
   validation; CP07 binds one exact published, complete, binding-valid
   ContributionPolicyVersion to the Project Guide.
4. **Activate the complete guide generation.** AUTH may permit terminal guide
   activation only when compilation, sufficiency, pre-submit policy,
   post-submit policy, review policy, revision policy, and ContributionPolicy
   all belong to the same approved current generation. First prove that each
   selected checker has a supported registered implementation and valid
   configuration. This does not require a Task, Submission, completed checker
   run or live REV implementation—their dependency runs in the other direction.
   The new activation command replaces legacy economic readiness guards;
   physical deletion waits until all old consumers are gone, including checker
   and public Submission cutover. Physical deletion is not a prerequisite for `allow_review`.
5. **Make tasks claimable from that generation.** TASK locks the complete guide
   and policy context before `READY`. Claim copies it to TaskAssignment; it
   performs no ContributionPolicy selection. Submission later copies the
   assignment's attempt version.
   **Complete pre-submission intake integration before creating the Submission:**
   continuous artifact preparation executes the locked intake plan, returns
   correction feedback on blocking failures, and publishes ready admission only
   after the required preparation/custody checks. TASK then consumes that
   admission to create the immutable Submission with the same assignment lineage.
6. **Produce current post-submit evidence and policy-governed routing.** Materialize the exact immutable
   Submission, execute the locked post-submit plan, persist one current result,
   activate only its fixed services, and automatically publish an exact
   human `allow_review` manifest on true when no blocking failure exists.
   CHECKERS owns durable execution/currentness; the shared facade does not
   create a second result store. Work evaluation may be deterministic or use
   an explicitly implemented model judge. A structural presence check cannot
   stand in for a required substantive quality evaluation. Unsupported required
   evaluators block the affected guide until implemented and included in a new
   approved catalogue-bound generation. Infrastructure retries and project
   setup faults are not contributor failures; `allow_review` is not acceptance.
   **For the first false-policy acceptance path:** publish TASK 04E1A source
   facts before REV-04B's source FK; complete CON-03C/07 and the existing shared
   fence/controller slice, then wire one shared acceptance operation through
   04E1B/04E2/04E3. Prove real scoped activation/drain and 04F remediation before
   enabling false. This milestone creates the submitter contribution and
   applicable awards without live human queues/leases/decisions; it neither
   invents a reviewer nor removes the later human branch from v0.1.
7. **Start the live REV path.** Complete packet, Review, and FinalAcceptance
   persistence; admit only canonical `allow_review`; claim a bounded lease and
   exact packet using the Submission-stamped ContributionPolicyVersion.
8. **Make human review decisions economically complete.** Before the first live
   Review commit, add the reviewer CON operation and reuse the shared acceptance
   operation already needed by the false branch. Every final decision records
   reviewer work; accept additionally records accepted submitter work. Do not
   duplicate the common persistence or submitter participant.
9. **Complete revision and operations.** Preserve old attempts immutably;
   rebase a continuing TaskAssignment only at the controlled human-revision
   boundary when the complete governed context changed. Finish recovery,
   fulfillment, reconciliation, audit, release controls, and legacy cleanup.
10. **Release proof.** Expose stable APIs and frontend surfaces, exercise the
    complete path through real database, durable-job, storage, security, failure,
    and recovery tests, then run the internal pilot.

## Engineering Quality Alongside Product Work

The [behavior-first audit](../.commitrail/initiatives/WS-QUAL-003/OVERVIEW.md)
has delivered focused PROJECT proof repairs, fixture separation, real
rollback checks, a shared AUTH concurrency-observer repair, and a rebalance of
the seven hosted CI lanes. The audit also corrected concrete sufficiency and
submission-policy validation defects. These are delivered bounded repairs,
not a claim that every test or subsystem is fully audited.

The selected AUTH projection replay, actor-resolution, and authentication audit
and decomposition are also delivered, including stronger first-access race
proof. The selected bootstrap/admin-access audit also retains signed API
composition, strengthens exact PostgreSQL lock and staged rollback proof, and
maps the replaced mixed assertions to bounded owner tests. That does not complete
the remaining service-actor, profile/link and other AUTH families or the full
suite audit. Remaining work includes those AUTH families and the TASK, CHECKER,
ART, CON, REV, and tooling audit. The audit requires behavioral proof, not only
file splitting or coverage percentages. Real PostgreSQL, concurrency, storage,
and full hosted coverage checks remain required. Product implementation is
already progressing alongside this audit with separate file ownership.

Commitrail's contribution-path and reviewer-routing improvements are delivered.
They support this work; they do not complete a product capability or create a
second permission system.

## Critical Dependency Map

```text
Hidden unified compilation, projections and setup finalization (complete)
  -> AUTH finalization gate (complete)
  -> automatic request authority and replay custody (complete)
  -> live unified compilation cutover
  -> Project Manager approval + effective pre-submit policy
  -> deterministic post-submit policy + single checker port

Hidden ContributionPolicy behavior (complete)
  -> AUTH policy action activation (complete)
  -> CON selected-policy validation
  -> Project Guide policy-version binding

Both chains
  -> terminal Project Guide activation
  -> Task readiness and assignment lineage
  -> artifact preparation + locked pre-submission intake checks
  -> ready admission after intake and custody checks
  -> immutable admitted Submission
  -> durable current post-submit result
  -> canonical allow_review
  -> REV admission, lease, packet, decision and revision
  -> atomic ContributionRecord / CompensationAward effects
  -> fulfillment, reconciliation and release proof
```

No claim-time policy selection exists. A normal task claim copies the version
already locked on the ready task. Review claim copies the version stamped on
the admitted Submission. During `needs_revision`, the continuing assignment
may rebase only after comparing and atomically preparing the complete newer
governed context; earlier Submission, ReviewLease, Review, ContributionRecord,
and award history never changes.

## Remaining Release Gates

v0.1 is not ready until all of the following are true:

- One active Project Guide generation contains a complete approved compilation
  and every required policy identity/hash, including ContributionPolicyVersion.
- A task cannot enter `READY` without that complete locked context.
- A contributor can claim and prepare one ZIP under the locked pre-submit
  policy. Blocking intake failures return feedback and create no Submission;
  successful preparation produces ready admission after the required custody
  checks, without a parallel legacy path.
- TASK consumes that admission to create the immutable Submission with exact
  assignment/policy lineage. Pre-submit feedback is not post-submit proof.
- The immutable Submission automatically reaches exactly one current
  post-submit result. Locked true produces human `allow_review` when eligible;
  locked false with supported requirements invokes the shared atomic acceptance
  operation with no human Review/lease/reviewer contribution.
- A reviewer can claim only that admitted version, access only its bounded
  packet, and record one immutable final decision.
- `needs_revision` safely continues or rebases the same assignment while
  preserving every earlier attempt; `reject` and `accept` have their exact
  distinct effects.
- Every final review atomically creates the reviewer ContributionRecord;
  `accept` additionally creates FinalAcceptance and the submitter record.
- Frozen policy rules produce zero, one, or two CompensationAwards without
  controlling Workstream lifecycle truth.
- Fulfillment and recovery are idempotent, observable, reconcilable, and safe
  under durable-job, provider, transaction, and unknown-commit failures.
- Public APIs and frontend surfaces expose only the canonical paths, obsolete
  authority and legacy routes are removed, and the full security/operations
  drill plus internal pilot passes without weakening safeguards.

## Trace References

Internal chunk identifiers are useful for implementation traceability, but a
reader does not need internal engineering records to understand the roadmap
above. The main
remaining trace sequence is:

- Unified guide: `POL-04B1 -> POL-04B -> POL-05A -> AUTH-12F4 -> POL-05B -> POL-06A
  -> AUTH-12G -> POL-06B -> POL-07 -> AUTH-12H`. `ARCH-04A` catalogue/schema
  reconciliation precedes approval-eligible `POL-04B` generations, and actual
  selected-capability conformance precedes `POL-07`/activation. POL-05 includes
  complete proposal visibility and setup-wide correction before approval.
- Contribution lineage: CP05 authorization is complete; `CP06 -> CP07` remain. Hidden `CP07` is another
  prerequisite of `AUTH-12H`, not a second live activation. `CP08` supplies
  lineage fields after `CP07`; `ARCH-03A` follows both `AUTH-12H` and `CP08`,
  then `ARCH-03B -> ARCH-03C`. `CP09` physical cleanup waits for all remaining
  legacy consumers to be replaced; it is outside the `allow_review` critical path.
  Live assignment invalidation also requires shared dispatch and its exact
  service authority; current authority is still checked on every request.
- Post-submit admission: after `POL-07` and `ARCH-03C`, `ARCH-04B -> 04C ->
  04D -> 04E` supplies materialization, durable results, authority and routing.
  An ART-owned output/log custody child precedes `04C` final completion.
  Automatic `04E` delivery also needs the shared `CON-02B` dispatcher and its
  exact AUTH registration/activation; existing outbox persistence alone does
  not deliver events. These foundations do not require REV or fulfillment.
  `04E` is hidden TASK handler `04E1`, exact AUTH activation `04E2`, then live
  integration `04E3`; a dispatcher cannot authorize TASK or CHECKERS mutations.
  Later `04F` owns contributor-correctable remediation and admission-backed
  resubmission before public cutover; it does not block `allow_review` or
  replace human review/revision.
- Review/revision: REV packet/schema foundations may proceed independently,
  but live admission starts after `ARCH-04E`; the first live Review commit also
  requires CON contribution/award persistence and its atomic decision participant.

For implementation ownership and exact contracts, contributors can follow
[Commitrail Engineering Index](../.commitrail/INDEX.md). For historical
decisions, use the [Historical Planning Index](historical_planning.md).
