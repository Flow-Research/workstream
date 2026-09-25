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

The automated-acceptance branch is a **planned** v0.1
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

Identity, authorization, guide ingestion, automatic unified compilation and
public manager proposal/approval operations are implemented. Terminal guide
activation is implemented internally but not publicly exposed. Task policy
lineage, contributor artifact preparation and immutable Submission creation have
tested foundations; their complete public integration remains unfinished.

Exact assignment-invalidation authority, atomic originating publication and
production delivery with enforced prefork topology are implemented. Manager task
create/screen/release now use exact project authority, atomic evidence and durable
replay. ARCH-03C4 adds the three exact-authorized public task queues. Next is
remaining task-read integration. Guide activation/intake integration and
durable post-submit evaluation follow the owner contracts. Required success
then branches on the locked ReviewPolicy: true routes to human `allow_review`;
false invokes shared authorized acceptance without a human Review. Both routing
integrations remain planned. Human review/revision, contribution and conditional
compensation effects, operations and release proof complete v0.1.

The [independent MCP package](../mcp_server/README.md) implements one profile
tool. It is not a deployed service or the complete proposed tool catalogue.

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
| Identity and actor resolution | **Live foundation** | Flow-token verification; canonical ActorProfile and ActorIdentityLink; human/service separation; lifecycle controls; canonical `/actors/me` self-read with duplicate `/auth/me` removed; suspension denies both self-read and self-update | Final end-to-end operational and conformance proof |
| Authorization kernel | **Live foundation** | Closed action/permission catalogues; deny-by-default evaluation; grants; fixed services; rate controls; opaque transaction-bound PREP; atomic decision evidence | Activate only the remaining owner-proven TASK, checker, REV, and CON boundaries; remove obsolete authority after replacement paths are live |
| Project Guide source custody | **Live foundation** | Guide creation declares documents and task examples; public document upload; immutable internal metadata snapshots; exact run-scoped reads; S3-backed originals and isolated agent document inspection; exact document generation through separate manager approvals and internally authorized CP07 activation | Public activation wiring; prove each enabled document reader |
| Unified Project Guide compilation | **Live setup and manager proposal operations** | Committed original-document readiness dispatches one immutable attempt through Celery; complete result and crash/recovery custody; distinct pre/post proposals; deterministic sufficiency and submission-artifact-policy projections; immutable authorized setup finalization; public exact manager review, pre-submit approval and manual correction dispatch; automatic deterministic post-policy derivation, public complete policy read, separate approval and shared correction custody | Public activation wiring and remaining task-read authority |
| Contribution policy administration | **Hidden and proven** | Finance Authority adapter-binding lifecycle; ContributionPolicy read/create/update/publish/retire with exact Finance Authority; immutable operation and event history; internal exact selected-version validation; CP07 binding with live exact-project manager authority of the selected published version to the active guide generation | Public activation wiring; remaining task-read authority |
| Task readiness and claim | **Foundation with grant-backed manager and contributor commands** | Task records, assignments and locked work context; guide-bound ContributionPolicyVersion locked before `READY` and copied to TaskAssignment; detached project/guide display; public project-scoped ready, management and operational queues with distinct current grant authority and signed bounded live pagination; hidden contributor/management detail with exact project and assignment visibility; separate current live work-context projections with exact receipt-selected review/revision/ContributionPolicy identities and no obsolete economic fields; explicit management/operational/audit locked-context projections using one historical resolver, with operational/audit reads internal; immutable contributor/management requirements using one historical translator, with hidden exact contributor visibility and management read; bounded internal Audit Authority lifecycle evidence with atomic project/task scoping and exact transition references; public manager create/screen/release use exact covered Project Manager authority, atomic audit and replay; claim/start/contributor context use exact-project Submitter grants; separate manager context and system-Operator start; durable claim/start retry receipts with fresh authority and exact assignment checks; hidden exact-assignment invalidation with committed cause verification, delivery fencing, exact fixed-service authority and decision-bound immutable release evidence; atomic authority-loss publication and registered prefork delivery | Remaining task-detail/requirements/locked-context authority, Audit Authority public evidence access |
| Contributor artifact preparation | **Hidden and proven** | One outer ZIP; bounded scratch inspection; canonical manifest; platform and project prechecks; unchanged-work rejection; durable put intent; verification; capacity-charged ready admission | Connect only the active unified guide/checker lineage and complete the later public admission-only cutover |
| Pre-submission intake checking | **Hidden and proven; unified-guide integration remains** | Separate versioned pre-submission catalogue, locked effective-plan compilation, platform/project checks during continuous preparation, blocking feedback before Submission creation, and one internal phase command covering execution/replay with the JSON precheck removed | Connect approved unified-guide pre-submit policy lineage through task/assignment preparation and complete the canonical public cutover; passing intake must never substitute for post-submit evaluation |
| Immutable Submission creation | **Hidden foundation; public packet creation retired** | Contributor preparation authority; durable pre-submit reservation and exact completed-evidence recovery without rerunning checks; atomic admission consumption; TASK-owned admission-backed creation with exact assignment ContributionPolicyVersion and locked policy lineage; fixed-service artifact binding; replay/concurrency/rollback proof | Finish downstream evaluation and the canonical public integration. The retained submission-list GET is not a usable creation POST |
| Post-submission evaluation and `allow_review` | **Planned; immediate integration milestone** | One canonical CHECKER post-submit catalogue/compiler used by existing consumers, internal phase service with explicitly unavailable post execution, hidden value contracts and structural-handler conformance; existing pre-review and materialization foundations | Connect the unavailable phase port to durable execution; evaluate the exact Submission against its locked policy; persist one durable current superseding result; activate fixed services; automatically dispatch it and publish the canonical `allow_review` manifest |
| Review queue and lease | **Hidden persistence foundation** | Queue/admission idempotency and ReviewLease/preference persistence; complete unavailable REV action/principal catalogue and typed AUTH contracts | Packet-membership contract and manifest; Review schema; canonical admission from `allow_review`; claim/lease/packet authority; lease copies the Submission-stamped policy version with no CON lookup |
| Review decision and revision | **Planned** | Review/revision policy identities and mutation authority; approved same-task revision-rebase semantics | Immutable findings and decisions; `accept`, `needs_revision`, and `reject`; complete-context revision preparation; finding responses; replacement contributor rules; replay and recovery |
| Contribution and compensation truth | **Schema foundations plus hidden policy behavior** | ContributionPolicyVersion persistence; lifecycle-audit participant; adapter bindings; hidden policy administration | Persist ContributionRecord/CompensationAward and one shared FinalAcceptance/submitter operation for human accept or authorized false/pass routing. Only actual Reviews create reviewer records. Evaluate frozen actor rules into zero, one or two awards |
| Fulfillment, reconciliation, and audit | **Planned** | Shared audit foundations, provider-neutral adapter convention, AUTH-OUTBOX-02 live dispatcher authority, retained phase audit decisions, Celery delivery/recovery scans and CON-02B custody | Feature-specific handlers and authority, conditional award fulfillment, callbacks, idempotent recovery, reconciliation, bounded operational reads, and release controls |
| Frontend and pilot | **Planned after stable backend contracts** | React + Vite + TypeScript stack decision | Implement only stable backed surfaces, run the real internal pilot, repair findings, and complete release drills |

## What Has Been Completed

### Security and platform foundations

- FastAPI, SQLAlchemy 2.x async, PostgreSQL, Alembic, Celery, and Redis form the
  locked backend execution stack.
- The schema has one fresh `0001_uuid7_v01` Alembic baseline. Generated record
  identities use UUIDv7 and native PostgreSQL UUID relationships; meaningful
  natural keys and external request tokens retain their semantics. Old stamped
  development databases require explicitly scoped recreation, not conversion or
  compatibility stamping. Local Compose uses a separate UUIDv7 database volume.
- AWS S3 is the hosted artifact target, MinIO proves the storage protocol in
  development and CI, and all storage access stays behind `ArtifactStore`.
  Development/CI MinIO uses a shared pinned-source build; existing artifact
  volumes and real S3-protocol tests remain unchanged.
- Private extraction scratch is bounded by `ArtifactScratchManager`; it is not
  durable artifact storage.
- Cross-module behavior is moving through explicit public ports under the
  modular-monolith boundary. New private edges are prohibited and touched debt
  is reduced incrementally.
- GitHub CI distributes the backend suite across semantic lanes, rejects
  skipped/deselected tests, preserves global coverage, and requires at least
  90 percent coverage for new or materially changed backend subsystems.
  Its eight-lane allocation uses three project lanes, two task lanes, two
  shared-foundation lanes and one schema lane. Database resets batch trigger
  commands within the existing transaction while retaining full schema checks;
  authorization preflight runs alongside lanes and remains mandatory at fan-in.
  Ordinary CI databases use bounded private RAM-backed storage with write
  settings verified; schema-contract and aggregate databases stay disk-backed.
  Hosted runtime remains measured rather than guaranteed.

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
  separate value/predicate/shape/request evidence. The
  [fixed 29-operation matrix](engineering/external-api-drill.md#fixed-29-operation-acceptance-matrix)
  records the completed client-contract scope and its field/authority/replay
  checks for the MCP handoff, across the documented frozen executions. New
  provider-dependent operations require their own evidence;
  they do not repeatedly reopen this original selection. Route discovery alone
  is not readiness.
  The [MCP initiative](../.commitrail/initiatives/WS-MCP-002/OVERVIEW.md)
  now fixes the caller-token design: the adapter forwards each caller's Flow
  bearer unchanged and Workstream verifies it. The
  [local one-tool experiment](../experiments/mcp_caller_token/README.md) passed
  15 real-process checks and 24 focused tests, including first admission and
  caller isolation. Independent packaging and the three bounded self-service
  tools are delivered through WS-MCP-002-02: profile read, profile update and
  exact-project authorization context. Twenty-four proposed tools remain;
  WS-MCP-002-03 administrative reads are next. This remains a custom
  authentication adapter, not a public deployment or a 27-tool release.
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
  Closure probes include exact persisted administrator-history fields, all
  lifecycle reason/key partitions and conflict codes, document declaration
  limits/order/labels/media types, service exclusion from human discovery,
  ineligible grant targets and stored cross-project grant substitution. Local
  bootstrap/count-guard evidence remains distinct from HTTP API observations.
  [API-DRILL-007](engineering/external-api-drill-findings.md#api-drill-007-embedded-nul-in-canonical-profile-fields-becomes-503)
  records the reproduced self-profile NUL defect and its repair: both editable
  fields reject the unsupported character at request validation with 422 rather
  than passing it to storage. The drill retains unchanged-business-state controls.
  [API-DRILL-008](engineering/external-api-drill-findings.md#api-drill-008-nul-project-selector-becomes-503)
  records the matching authorization-context selector repair: NUL is rejected
  with 422 while project-ID lookup and project concealment remain intact.
  [API-DRILL-009](engineering/external-api-drill-findings.md#api-drill-009-project-and-guide-text-nul-becomes-503)
  records the project/guide text repair: the original eight inputs rejected NUL
  at request validation instead of returning a storage failure; the guide
  document cutover removes inline-content inputs and retains validation on
  surviving fields. Dedicated
  regressions check selected stored-state preservation, same-key recovery and
  replay. This does not certify the unfinished all-field external-client handoff.
  API-DRILL-006 is repaired with a bounded project-role issuance envelope that
  accommodates the existing public qualification maxima; other authority
  mutations retain their original limit. Full-max parser/PostgreSQL regressions
  cover both roles, persistence, replay, conflict and unauthorized rollback.
  The resumed real guide-upload drill reproduced
  [API-DRILL-010](engineering/external-api-drill-findings.md#api-drill-010-successful-guide-document-replay-returns-stale):
  an exact retry of a successfully stored document returned `stale`. The repair
  returns the authorized terminal result without another provider operation.
  The related inactive-resolver denial now returns concealed 404 and retains
  its canonical audit rather than escaping as 500. Local real PostgreSQL/MinIO
  regression and genuine-document replay passed; this does not establish
  complete field-level client readiness.
  [API-DRILL-012](engineering/external-api-drill-findings.md#api-drill-012-administrative-grant-reasons-containing-nul-return-503)
  closes the same validation gap in administrative grant issue/revoke reasons:
  NUL rejects before storage, while valid Unicode and same-key recovery remain
  supported. This does not change authority or retained grant history.
  [API-DRILL-013](engineering/external-api-drill-findings.md#api-drill-013-service-provisioning-subject-containing-nul-returns-503)
  applies the same early rejection to service provisioning subjects, preserving
  exact Unicode identity and same-key recovery without changing service authority.
- Guide ingestion and exact document reads, artifact verification/recovery,
  contributor preparation, Submission consumption/binding, unified compilation
  request/execute, and deterministic projection authority are implemented at
  their current hidden or live boundaries.

### Project Guide and artifact pipeline

- Project Managers can authorize guide-source ingestion for projects they are
  permitted to manage.
- Guide originals remain immutable in ArtifactStore; PostgreSQL holds metadata,
  versions, custody and the required task-example list. Guide creation requires
  at least one nonblank example and the complete nonempty document list. The
  response supplies document IDs for the public binary upload route; no separate
  source-snapshot creation call remains. A starting idea is sufficient and optional
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
  covered projects need no suggestions. POL-05B exposes the complete POL-05A review package;
  AUTH-12F4 supplies exact manager authority; suggestions cannot register or activate a checker. Runtime, model/provider and instructions are independently
  configured and bound to the attempt. The agent opens assigned files on demand
  in an isolated workspace and assesses them with every supplied task example;
  exact grants exclude other projects and runs. Known
  invalid output ends terminally, and replay never starts a second inference.
  The model-facing mandatory archive-entry capability explicitly names existing
  encryption, symbolic-link and special-file rejection. The existing package-size
  rule enforces verified expanded bytes, now explicit in the proposal schema.
  The optional `maximum_archive_entries` policy adds a compiled, blocking normalized
  outer-ZIP tree entry limit, including implied parent directories, preserving tighter default
  limits and ART safety ceilings. This does not expose public submission intake.
  The separate optional `maximum_archive_size_bytes` rule enforces the entire
  compressed ZIP's verified byte count, including archive metadata, independently
  of expanded content size; the same default-floor and locked-plan controls apply.
  The [post-POL-05B genuine-guide replay](engineering/external-api-drill-findings.md#post-pol-05b-replay-nested-archive-capability-gap)
  exposed an unrequested nested-archive restriction in the assistant's drill
  guide. The human removed that fixture requirement: members may have any file
  type, including nested archives, subject to existing safety/resource checks.
  No nested-archive detector is required by this decision. The corrected guide's
  replay reached draft readiness with 34 expected HTTP checks and independently
  verified stored limits; the old failed run remains historical evidence.
  Transient pre-send retries use bounded backoff and a circuit breaker; the
  default request timeout is 300 seconds, separate from the whole-run timeout.
  POL-05B exposes review, pre-submission approval and correction successors
  using POL-05A custody. Approval requires selected pre-submit checks to appear
  in the plan compiled from the actual policy; complete-proposal access requires
  Project Manager guide-management authority. Public manager review and manual
  dispatch use AUTH-12F4 authority. Committed manager requests enter the same
  Celery execution pipeline with atomic queue intent and no second attempt.
  The authorized latest-setup read exposes saved correction/predecessor identifiers
  so a replacement manager can discover and explicitly dispatch a pending correction
  after the creator is revoked, without the original creation receipt.
  Superseded post-submit setup/approval/correction routes are removed. POL-06A
  implements hidden deterministic projection of the saved post-submit proposal,
  complete draft read, separate approval and correction through the existing
  unified successor. Immutable operation receipts replace role-string authority
  in affected readers. AUTH-12G supplies live fixed-service and exact-project manager adapters. POL-06B exposes the complete post-policy read, separate approval and correction, with automatic deterministic derivation and approval-driven recovery. Real Terra runs through API upload,
  MinIO, the Celery handler and PostgreSQL proved both blocked findings and ready
  draft policy outcomes, with exact replay and provider cleanup. Broker delivery
  was scripted in these drills; live Celery transport and broad semantic accuracy
  are not established by them. A later public-client diagnostic used an isolated
  Redis broker and actual Celery delivery with two original shareable PDFs;
  it reached a persisted `sufficiency_blocked` report and verified both stored
  originals. The subsequent clean `869a1d71` public-client run passed 36 cases,
  including repaired replay, findings-to-setup lineage, and inactive-resolver
  denial with unchanged setup and stored originals. Its real model identified
  unsupported archive/content intake checks and post-submit audit evaluation
  required by that project. This does not establish broad semantic accuracy,
  manager approval or active project policy.
  Earlier probes omitted task examples and establish
  execution mechanics only. A subsequent real Terra run with assigned private documents
  and two task examples proved exact example delivery, original access, persisted
  findings, cleanup and replay. It correctly stopped for absent project-wide
  file/archive size limits, without demanding one selected paper. This proves
  that bounded blocked-result flow; it does not establish a ready policy for
  those inputs or broad semantic accuracy. CP07 now supplies hidden complete-guide
  activation and immutable ContributionPolicy binding. It requires both exact
  approvals and current complete review/revision inputs, supersedes the selected
  prior guide and promotes a draft Project atomically. Active-guide reads require
  the committed binding. AUTH-12H supplies live exact-project manager authority;
  CP08 locks and carries exact policy lineage through Task, TaskAssignment and
  Submission. Public activation wiring and remaining task-read authority remain pending.
- Contributor ZIP preparation uses one verified byte lineage from scratch
  inspection through durable admission and eventual Submission binding.

### Contribution and review foundations

- Finance Authority can manage compensation adapter bindings through the
  hidden, authorized boundary. CP07A aligns policy/binding mutations with AUTH
  by locking authority before product resources, and reconciles the database
  audit vocabulary for the existing binding actions. CP07 complete hidden guide
  activation/binding and AUTH-12H live exact-project manager authority are delivered.
- Complete hidden ContributionPolicy draft/publication/retirement behavior is
  persisted with immutable lifecycle history. All five actions have exact human
  Finance Authority through explicit AUTH composition; default composition denies
  access and public policy routes remain unavailable.
- CP06 supplies internal caller-transaction validation of the exact selected
  ContributionPolicy version and its complete graph/resources. New guide binding
  requires the active current published selector. Controlled revision validates
  the caller’s exact guide-bound version, not a newer global selector; downstream
  guide custody and revision integration remain pending.
- REV queue/admission and lease/preference persistence foundations are merged.
- The governing rule is fixed: one ContributionPolicyVersion contains both the
  `accepted_submission` and `completed_review` rules. It is bound before task
  readiness and carried as immutable attempt lineage.

## Current Work And Immediate Order

Only open pull requests describe transient work. Use the repository's
[open pull-request view](https://github.com/Flow-Research/workstream/pulls) to
see whether any item below is already under review.

Delivered capabilities are summarized in the [scoreboard](#end-to-end-lifecycle-scoreboard);
their evidence is linked under [completed work](#what-has-been-completed).
The [dependency and ownership plan](../.commitrail/initiatives/WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
owns implementation sequencing. The existing checker phase service supports
hidden pre-submit execution/replay, but production post-submit execution remains
unavailable. Live setup does not wait for downstream task/checker execution.

The next dependency-safe product sequence is:

1. **Integrate the delivered guide/task foundations.** CP08 lineage and
   ARCH-03B1–03B9 owner operations are delivered at the exposure boundaries
   listed above. ARCH-03C1 supplies exact reconciler authority and decision-bound
   receipts. ARCH-03C2 supplies atomic originating publication and production
   delivery with enforced prefork topology. ARCH-03C3 supplies exact-authorized
   manager task create/screen/release; ARCH-03C4 supplies the three public queues. Remaining read authority
   and exposure remain separately bounded. Public guide activation remains pending and is not implied by an
   internal public port. Guide activation requires exact
   current compilation, sufficiency, separate pre/post approvals, review/revision
   inputs and an explicitly selected published ContributionPolicyVersion.
   Registered checker implementations and configuration are checked without a
   Task, Submission, completed checker run or live REV implementation.
   The hidden operation replaces superseded economic readiness. Retained economic
   data and downstream TASK consumers remain until their scoped cutover;
   deleting retained data is not authorized by code cleanup.
2. **Complete public intake and admission integration for claimable work.**
   CP08 already locks the complete guide and policy context before `READY`.
   Claim copies it to TaskAssignment without selecting another ContributionPolicy;
   hidden admission-backed Submission creation already copies that exact lineage.
   Remaining work connects continuous preparation to the approved unified-guide
   intake plan and completes the canonical public cutover. Preparation returns
   correction feedback for blocking intake failures and publishes ready admission
   only after the required preparation/custody checks; the existing TASK creation
   operation consumes that admission with the assignment's locked lineage.
3. **Produce current post-submit evidence and policy-governed routing.** Materialize the exact immutable
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
4. **Start the live REV path.** Complete packet, Review, and FinalAcceptance
   persistence; admit only canonical `allow_review`; claim a bounded lease and
   exact packet using the Submission-stamped ContributionPolicyVersion.
5. **Make human review decisions economically complete.** Before the first live
   Review commit, add the reviewer CON operation and reuse the shared acceptance
   operation already needed by the false branch. Every final decision records
   reviewer work; accept additionally records accepted submitter work. Do not
   duplicate the common persistence or submitter participant.
6. **Complete revision and operations.** Preserve old attempts immutably;
   rebase a continuing TaskAssignment only at the controlled human-revision
   boundary when the complete governed context changed. Finish recovery,
   fulfillment, reconciliation, audit, release controls, and legacy cleanup.
7. **Release proof.** Expose stable APIs and frontend surfaces, exercise the
    complete path through real database, durable-job, storage, security, failure,
    and recovery tests, then run the internal pilot.

## Engineering Quality Alongside Product Work

The [behavior-first audit](../.commitrail/initiatives/WS-QUAL-003/OVERVIEW.md)
has delivered focused PROJECT proof repairs, fixture separation, real
rollback checks, a shared AUTH concurrency-observer repair, and a rebalance of
the hosted CI lanes. The audit also corrected concrete sufficiency and
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
Delivered foundations (not a claim of full public integration)
  automatic unified setup + separate manager pre/post approvals
  ContributionPolicy validation + internal guide activation/binding
  task/assignment/Submission lineage + hidden intake/creation
  shared dispatcher + exact-authorized hidden assignment invalidation
  ARCH-03C2 invalidation producer + first handler registration
  ARCH-03C3 exact manager task create/screen/release + replay
  ARCH-03C4 exact-authorized public task queues
    |
    v
Remaining integration
  bounded ARCH-03C remaining task-read authority
  -> public guide activation + approved-guide intake integration
  -> immutable admitted Submission through the public path
  -> durable current post-submit result + required checks pass
       |
       +-- locked true -> allow_review -> human Review
       |                                    | accept
       |                                    v
       +-- locked false -> authorized ----> shared FinalAcceptance
                           automated        + submitter ContributionRecord
                           trigger          + applicable awards (atomic)
                                               |
                                               v
                         fulfillment, reconciliation and release proof
```

Human `needs_revision` follows controlled revision; `reject` records a rejected
outcome. Every final human decision records reviewer work and any applicable
reviewer award atomically; the false branch creates neither. Both acceptance
triggers use the same operation. Shared acceptance persistence
and CON participation must exist before false/pass routing is activated; human
queues and leases are not prerequisites for that branch. The diagram shows the
successful evaluation branches; failure/remediation and recovery remain required
by the sequence and release gates below. Neither branch is live end to end yet.

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

- Unified guide: POL-04B1/04B/04B2, POL-05A/AUTH-12F4/POL-05B,
  POL-06A/AUTH-12G/POL-06B, POL-07A/07B, AUTH-12H and ARCH-03A are delivered.
  The complete internal guide context and `CP08` exact task/assignment/Submission
  contribution-policy stamps and ARCH-03B1 detached display are available; ARCH-03B2 ready and ARCH-03B3 management/operational queue facts and ARCH-03B4 hidden task detail and ARCH-03B5 current live work context and ARCH-03B6 locked-context and ARCH-03B7 requirements projections are delivered.
  ARCH-03B8 hidden task audit evidence and ARCH-03B9 hidden assignment invalidation
  are complete. ARCH-03C1 real feature authority and exact decision receipts are
  complete; ARCH-03C2 supplies atomic producer wiring and registration;
  [ARCH-03C3](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03C3.md) supplies
  exact-authorized manager create/screen/release.
  [ARCH-03C4](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03C4.md) exposes the
  three queues with distinct grants and signed pagination. ARCH-04A supplies registered-capability
  contracts; activation does not require a Task, Submission or completed run.
- Contribution lineage: CP05 authorization, CP06 validation and hidden `CP07` activation
  and `AUTH-12H` live manager authority are complete. `ARCH-03A` has completed
  the existing internal guide-context port. `CP08` delivers lineage fields
  and minimal Task/Assignment/Submission writers together without superseded economic
  readiness. Atomic assignment-invalidation publication and delivery are complete
  in `ARCH-03C2`, following real authority in `ARCH-03C1` and
  `ARCH-03B1` metadata and ARCH-03B2/03B3 hidden queues and ARCH-03B4 hidden detail and ARCH-03B5 current work context, ARCH-03B6 locked-context and ARCH-03B7 requirements and ARCH-03B8 hidden audit evidence and ARCH-03B9 hidden assignment invalidation, and authorization/public cutover in `ARCH-03C`. `CP09` physical cleanup waits for all remaining
  legacy consumers to be replaced; it is outside the `allow_review` critical path.
  Shared dispatch authority is delivered by AUTH-OUTBOX-02. Live assignment
  invalidation has atomic producer fan-out and registered delivery in ARCH-03C2.
  Manager readiness commands are public with exact authority in ARCH-03C3;
  ARCH-03C4 exposes ready, management and Operator-status queues;
  remaining task-read authority/exposure is pending. Current authority is checked
  on every request.
- Post-submit admission: after delivered `POL-07B` and remaining `ARCH-03C`, `ARCH-04B -> 04C ->
  04D -> 04E` supplies materialization, durable results, authority and routing.
  An ART-owned output/log custody child precedes `04C` final completion.
  AUTH-OUTBOX-02 delivers shared live authority, phase audit custody and Celery
  delivery/recovery scans over CON-02B. Delivery termination is bounded by a
  300-second hard limit under prefork.
  ARCH-03C2 enforces a dedicated non-eager prefork delivery queue.
  Automatic `04E` delivery still needs its
  separately authorized checker-routing handler; the installed assignment handler
  does not supply that authority. These foundations do not require REV or fulfillment.
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
