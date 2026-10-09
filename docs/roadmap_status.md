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
external task-routing systems, agent workspaces, and runtime reputation projection remain
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
`allow_review`. Shared REV source persistence and hidden CON submitter
participation are delivered before ARCH-04E false/pass integration; human
queues/leases are not its prerequisites. REV-12A4A supplies the existing
controller’s internal Operator-authorized phase transitions and current-generation
participant gates. The initial manifest refuses retained pre-authority acceptance
facts before entering live. It enables neither routing nor payment delivery;
conditional award facts remain atomic, while obligation/root/cutoff machinery
belongs to later fulfillment activation.

The setting is configurable through the existing authorized policy writer;
creation defaults true and omitted replacements inherit the predecessor.
Versioned hashing preserves old policy hashes and locks. False remains blocked
by the current activation service. See the [implementation record](../.commitrail/changes/pre-review-plan-reconciliation.md#delivered-policy-setting-implementation). Enabling false follows shared final-acceptance,
TASK effects, exact AUTH/source custody and routing proof, not live human-review infrastructure.
The separate `requires_second_review` field is [fixed to false](../.commitrail/changes/enforce-requires-second-review-false.md)
at typed input, immutable lineage and PostgreSQL boundaries. Retained true facts
refuse upgrade without rewrite; supported false-policy hashes remain unchanged.
The first complete contributor milestone is claim -> upload ZIP -> pre-submit
feedback or immutable Submission -> automatic post-submit checking -> outcome.
For an eligible project with locked `human_review_required=false`, success must
include shared FinalAcceptance, the submitter ContributionRecord and applicable
policy awards. Failure/remediation and public intake belong to that milestone;
reaching hidden checker success alone does not complete it. Deliver this journey
before live human review/revision. Independent review foundations may proceed in
a separate worktree, but cannot add a human-queue or review-lease dependency to
automated acceptance. Human review/revision still belongs to the complete v0.1 release. See the
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
public manager proposal/approval operations and terminal guide activation are
implemented. Managers discover exact activation selections through the authorized
draft post-policy read; Finance publication remains separate. Task policy
lineage, contributor artifact preparation and immutable Submission creation have
tested foundations; their complete public integration remains unfinished. TASK
now reserves and replays exact post-submit routing requests internally. Hidden
AUTH preparation strictly binds those requests to exact source and branch
consequences through canonical PREP, but the action remains planned/unavailable.
No handle, allow, receipt, routing outcome or acceptance is published.

Exact assignment-invalidation authority, atomic originating publication and
production delivery with enforced prefork topology are implemented. Manager task
create/screen/release now use exact project authority, atomic evidence and durable
replay. ARCH-03C4 adds the three exact-authorized public task queues. PILOT-14
adds locked
ContributionPolicyVersion compensation to ready rows and Contributor detail for
active exact-project Submitters or Reviewers, without Finance internals or claim
authority. ARCH-03C5 adds exact-authorized Contributor/Manager
detail and requirements. ARCH-03C6 adds
separate exact-authorized locked-context reads. ARCH-03C7 adds bounded public
Audit Authority history access. PILOT-02A defines project-bound canonical JSON
source declaration, upload, status and verified download using ART custody and
current PM authority. Its ordered source migration and public PostgreSQL/MinIO
proof remain pending. Source storage creates no Tasks; atomic DRAFT import,
explicit batch screen/release and CLI conversion follow in later PILOT-02 work.
ARCH-03D connects hidden intake through durable intent to the activated historical
guide using canonical owner ports. ARCH-04B adds hidden verified Submission input
with scoped async access. ARCH-04B2 adds hidden typed checker-output storage,
byte-free recovery and flush-only verified binding over generic ART
put/verification. ARCH-04C supplies hidden durable evaluation, immutable ordered
results, database-timed execution leases and atomic completion events. ARCH-04D2 supplies exact fixed-service input, execute and finalize authority
and database-bound receipts; output-file authority remains unavailable. ARCH-04D1 enforces canonical
ART material lineage for all terminal results retaining material; public intake remains deferred to
the later cutover prerequisites. ARCH-04E1A adds one immutable route-neutral
TASK source table, detached source facts and source-neutral accepted-effects
contracts. REV-04C uses the bounded exact-source verifier, but there is no
general routing publication writer/reader, handler, current pointer or routing
authority. Required success
then branches on the locked ReviewPolicy: true routes to human `allow_review`;
false invokes shared authorized acceptance without a human Review. Both routing
integrations remain planned; false has metadata and guard-reachability proof only and guide activation
still rejects it. ART-07A1 supplies metadata-only reviewer packet types, with no resolver or byte
authority. REV-03B packets and REV-04A immutable Review source storage are delivered; REV-04B shared acceptance storage, CON-03C contribution/award storage, REV-12A1 disabled controller/fence mechanics and CON-07 hidden source-neutral submitter participation with complete frozen award sets
are delivered. [REV-04C](../.commitrail/initiatives/WS-REV-001/WS-REV-001-04C.md)
adds one hidden source-neutral participant that stages
FinalAcceptance, TASK accepted/completed effects and the complete CON outcome in
the caller's transaction. This mechanical core is not an authorized operation,
routing handler, currentness guarantee or live acceptance path. AUTH-19A supplies inert exact source commitments and a planned router
identity; ARCH-04E2-A supplies hidden source preparation and a nominal receipt
projection only after canonical consumption, which is unreachable while the action
is planned. Durable receipts commit only with the complete consequence. Human review/revision, acceptance authority/evidence closure, conditional
fulfillment, operations and release proof complete v0.1.

The [independent MCP package](../mcp_server/README.md) implements nine self-service
and administrative read tools through WS-MCP-002-03. The
[Go CLI](../cli/README.md) provides caller-profile and exact-project authorization
reads plus human self-profile editing, exact-project inspection and manager
task queue/detail reads, contributor ready-work/instruction reads and public
claim/start commands with caller-supplied retry keys, plus governing work-context
and locked intake-requirement reads, assigned locked-original listing/download,
draft project creation, guide declaration
with illustrative tasks/document selectors, and declared-original upload with
hash/size-bound storage receipts and a local-original recheck before success, using explicit
caller-owned retry keys, with
text/JSON output, plus latest guide-setup diagnostic inspection without polling
or local readiness decisions. Project inspection preserves
server-selected full/minimal fields; no public project-list route is invented.
CLI write uncertainty is explicit and never automatically
retried. These source packages do not claim
hosted deployment, published CLI binaries or the complete proposed workflow catalogue.

Privacy-bounded API and prefork Celery diagnostics are implemented: structured
logs, sampled traces and bounded metrics through one typed export adapter.
Trusted-broker trace linkage depends on restricted broker publisher ACLs and
never supplies product authority. Collector deployment, diagnostic-store access
and finite-retention controls, and an operational end-to-end drill remain
release work; diagnostics do not establish lifecycle truth.

[ARCH-04E1B-B1](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB1.md)
adds required TASK-before-CHECKERS reservation/current-result locking, ordered
review admission INSERTs, exact terminal replay and mechanical race controls.
[ARCH-04E1B-B2](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB2.md)
adds exact hidden source preparation through existing owner ports, without
source publication or authority.
[ARCH-04E1B-B3](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB3.md)
retains verified ZIP member metadata for consumption without another storage read.
[ARCH-04E1B-B4](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB4.md)
binds Submission text to its checked intake packet at consumption and in storage.
[ARCH-04E1B-B5](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB5.md)
rejects unrepresentable evaluation content before durable admission.
[ARCH-04E1B-B6](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB6.md)
commits each new Submission, verified ART binding, exact creation/binding AUTH
receipts, generation-one reservation and shared outbox request together.
Fresh-authorized replay verifies retained owners without creating missing rows.
B7 adds the hidden request handler with exact invocation fencing. Completion routing and complete authorized routing proof are next.

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
| Post-submission evaluation | Does the submitted work meet the configured task/project checks? Evaluate the exact stored work and evidence under the locked requirements. | The Submission-stamped `PostSubmitCheckerPolicy` drives the durable checker registry after immutable Submission creation. Only supported, registered checks execute. | Persist current evidence. The route-neutral TASK source schema and hidden exact AUTH preparation exist, with publication still deferred. Later routing branches on the locked ReviewPolicy: true moves TASK to `review_pending`; false invokes shared acceptance under TASK authority. CHECKERS never writes acceptance itself. Both routes remain planned. |

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
| Project Guide source custody | **Live foundation** | Guide creation declares documents and task examples; public document upload; immutable internal metadata snapshots; exact run-scoped setup reads and assigned-task locked-original reads; S3-backed originals and isolated agent document inspection; exact document generation through separate manager approvals and public exact-authorized CP07 activation | Public activation-to-intake drill after evaluation/remediation prerequisites; prove each enabled document reader |
| Unified Project Guide compilation | **Live setup and manager proposal operations** | Committed original-document readiness dispatches one immutable attempt through Celery; complete result and crash/recovery custody; distinct pre/post proposals; deterministic sufficiency and submission-artifact-policy projections; immutable authorized setup finalization; public exact manager review, pre-submit approval and manual correction dispatch; automatic deterministic post-policy derivation, public complete policy read, separate approval and shared correction custody | Public intake cutover after evaluation/remediation prerequisites |
| Contribution policy administration | **Public Finance policy workflow; binding administration internal** | Internal Finance Authority adapter-binding lifecycle; public ContributionPolicy discovery/read/create/update/publish/retire with exact Finance Authority and recoverable draft selectors; immutable operation and event history; internal exact selected-version validation; CP07 binding with live exact-project manager authority of the selected published version to the active guide generation | Public intake cutover after evaluation/remediation prerequisites |
| Task readiness and claim | **Foundation with grant-backed manager and contributor commands** | Task records, assignments and locked work context; guide-bound ContributionPolicyVersion locked before `READY` and copied to TaskAssignment; detached project/guide display; public project-scoped ready, management and operational queues with distinct current grant authority and signed bounded live pagination; public contributor/management detail with exact project and assignment authority; separate current live work-context projections with exact receipt-selected review/revision/ContributionPolicy identities and no obsolete economic fields; explicit management/operational/audit locked-context projections using one historical resolver, with separate public manager, system-Operator and Audit Authority access; immutable contributor/management requirements using one historical translator, with public exact Contributor and Manager authority; bounded public Audit Authority lifecycle evidence with atomic project/task scoping and exact transition references; public manager create/screen/release use exact covered Project Manager authority, atomic audit and replay; claim/start/contributor context use exact-project Submitter grants; assigned context lists documents only and distinct `task.guide.read` verifies locked originals before delivery; separate manager context and system-Operator start; durable claim/start retry receipts with fresh authority and exact assignment checks; hidden exact-assignment invalidation with committed cause verification, delivery fencing, exact fixed-service authority and decision-bound immutable release evidence; atomic authority-loss publication and registered prefork delivery; PILOT-14 exposes both locked contribution types in ready rows and Contributor detail for active exact-project Submitters or Reviewers as unpaid or exact instrument/unit/quantity awards, without Finance binding facts; claim/start remain Submitter-only | Public intake cutover follows evaluation/remediation prerequisites |
| Bulk task source custody | **Planned source foundation** | PILOT-02A defines covered-PM project-bound declaration, canonical 1..500-row JSON upload with exact SHA/count, fresh-authority replay, source status and independently verified download using existing ART custody; pure contract tests pass | Ordered source migration and public PostgreSQL/MinIO proof; then atomic DRAFT import, separate explicit batch screen/release and CLI conversion |
| Contributor artifact preparation | **Hidden and proven** | One outer ZIP; bounded scratch inspection; canonical manifest; shared evaluation-content capacity and exact locked-policy checks before attempts or durable intent; platform and project prechecks; unchanged-work rejection; durable put intent; verification; capacity-charged ready admission; hidden final handoff validates the exact activated historical guide through owner ports | Complete the later public admission-only cutover |
| Pre-submission intake checking | **Hidden with approved-guide lineage** | Separate versioned pre-submission catalogue, locked effective-plan compilation, platform/project checks during continuous preparation, blocking feedback before Submission creation, and one internal phase command covering execution/replay with the JSON precheck removed; ARCH-03D connects approved-guide lineage through the final durable handoff | Complete the canonical public cutover after evaluation/remediation prerequisites; passing intake must never substitute for post-submit evaluation |
| Immutable Submission creation | **Hidden foundation; public packet creation retired** | Contributor preparation authority; durable pre-submit reservation and exact completed-evidence recovery without rerunning checks; atomic admission consumption; TASK-owned admission-backed creation with exact assignment ContributionPolicyVersion, locked policy lineage and service/database checked-packet custody; fixed-service artifact binding; replay/concurrency/rollback proof | Finish downstream evaluation and the canonical public integration. The retained submission-list GET is not a usable creation POST |
| Post-submission evaluation and `allow_review` | **Hidden exact preparation; routing planned** | One canonical CHECKER post-submit catalogue/compiler used by existing consumers, internal phase service with exact fixed-service post-submit authority, hidden value contracts and structural-handler conformance; ARCH-04B/04B2 input and output custody; ARCH-04C durable execution and current-result custody; ARCH-04D1 canonical ART material custody; ARCH-04D2 exact phase authority and receipts; ARCH-04E1A immutable route-neutral source table and detached facts; AUTH-19A inert source/receipt commitments and planned router identity; ARCH-04E1B-A immutable request/source-identity reservation and exact replay; ARCH-04E2-A strict preparation; REV-04C hidden FinalAcceptance/TASK/CON participant; ARCH-04E1B-B1 required TASK reservation/current-read guard, ordered admission INSERTs and mechanical race controls; ARCH-04E1B-B2 exact source preparation without publication; 04E1B-B3 retains inspected ZIP metadata and B4 binds checked packet text for consumption; B5 rejects unrepresentable evaluation content before durable admission; B6 commits atomic Submission/dispatch with exact receipts and select-only replay | B7 adds hidden request delivery; completion routing 04E1B-B is next. True routing remains independent of shared acceptance. False activation at 04E2-B requires the same strict participant input to carry the mandatory exact AUTH decision-event receipt, database-enforced FinalAcceptance/TASK/CON completeness, shared audit/outbox and the reviewed scoped lifecycle manifest. 04E1B-B1 supplies reservation/current-read and admission INSERT lock ordering; the remaining handlers must prove complete authorized routing/currentness race orders. No handler, current pointer, route, currentness guarantee or acceptance effect is live; 04F remediation still precedes false guide activation |
| Review queue and lease | **Hidden persistence foundation** | Queue/admission idempotency and ReviewLease/preference persistence; complete unavailable REV action/principal catalogue and typed AUTH contracts; ART-07A1 metadata-only packet contract and REV-03B immutable normalized packet persistence with live ingest custody; REV-04A Review/finding/resolution and completed request storage | Future resolver proof; canonical admission from `allow_review`; claim/lease/packet authority; lease copies the Submission-stamped policy version with no CON lookup |
| Review decision and revision | **Hidden acceptance core; runtime planned** | Review/revision policy identities and mutation authority, with `requires_second_review` fixed false through typed and database boundaries; REV-04A immutable Review storage; REV-04B source storage; REV-04C hidden source-neutral FinalAcceptance/TASK/CON participant; approved same-task revision-rebase semantics | Add the mandatory exact AUTH receipt to the same participant input and complete database/audit/outbox closure before either trigger consumes it; then authorize atomic human decisions, revision preparation, replay and recovery |
| Contribution and compensation truth | **Hidden shared participant plus public policy administration** | ContributionPolicyVersion persistence; lifecycle-audit participant; adapter bindings; public Finance policy administration; REV-04B shared acceptance source storage; CON-03C immutable ContributionRecord/CompensationAward storage; obsolete guide-keyed payment storage and task-local payment fields removed; CON-07 source-neutral submitter participant and complete award sets; REV-04C composes it with FinalAcceptance/TASK effects in the caller transaction | Add authority/evidence and complete-set database closure before production consumption. Only actual Reviews create reviewer records. REV-12A4A adds scoped lifecycle control; add audit/outbox and exact acceptance authority before production consumption. Obligation/root/ordinal custody remains deferred until fulfillment activation; no public recognition or fulfillment route is live |
| Fulfillment, reconciliation, and audit | **Planned** | Shared audit foundations, provider-neutral adapter convention, AUTH-OUTBOX-02 live dispatcher authority, retained phase audit decisions, Celery delivery/recovery scans and CON-02B custody | Feature-specific handlers and authority, conditional award fulfillment, callbacks, idempotent recovery, reconciliation, bounded operational reads, and release controls |
| Runtime diagnostics | **Implemented foundation** | Closed structured logging, explicit API/Celery tracing, bounded metrics, safe correlation and optional typed OTLP export | Restrict broker publishers; configure and secure collector/log access, egress, encryption and finite deletion; prove diagnostics during the release drill; no deployed monitoring claim |
| Frontend and pilot | **Local runtime foundation; product pilot planned** | Checkout-isolated Docker Compose API, prefork Celery process, beat, PostgreSQL, Redis and MinIO stack with local Flow-HMAC identities, existing authority bootstrap/grants, configurable loopback ports and project-scoped state; a pinned offline sample image build and separate oracle were proved under gVisor; React + Vite + TypeScript stack decision | Implement the external launcher/checker images and benchmark a representative task before choosing production limits; complete provider-backed guide compilation and activated-guide scoped task-denial proof on the base stack, implement only stable backed frontend surfaces, run the real internal pilot, repair findings, and complete release drills; Docker Desktop/macOS runtime proof remains |

## What Has Been Completed

### Security and platform foundations

- FastAPI, SQLAlchemy 2.x async, PostgreSQL, Alembic, Celery, and Redis form the
  locked backend execution stack.
- [Runtime diagnostics](engineering/observability.md) provide closed structured
  logging, sampled API/prefork Celery traces and bounded metrics through optional
  OTLP export. Public propagation cannot control sampling; sensitive payloads,
  credentials and exception text are excluded. Collector failures do not change
  product outcomes. Durable outbox recovery starts a new trace and retains only
  its existing diagnostic correlation, without new persisted trace fields.
- The schema has one fresh `0001_uuid7_v01` Alembic baseline. Generated record
  identities use UUIDv7 and native PostgreSQL UUID relationships; meaningful
  natural keys and external request tokens retain their semantics. Old stamped
  development databases require explicitly scoped recreation, not conversion or
  compatibility stamping. Local Compose uses a separate UUIDv7 database volume.
- The [local pilot stack](engineering/local-pilot.md) runs API, the existing
  prefork Celery topology, its recovery scheduler, PostgreSQL, Redis and MinIO
  under one explicit Compose project. Every published port is checkout-local;
  containers, network, retained data and bounded scratch are project-scoped.
  Its Flow-HMAC helper creates identity only, while the existing trust-root and
  grant operations remain the sole local authority path.
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
  skipped/deselected tests and requires behavior, boundary and real API proof.
  Coverage is diagnostic only, with no percentage gate or test-count target.
  Redundant coverage-only reruns are removed; their tests remain in full-suite lanes.
  Its nine-lane allocation uses three project lanes, three task lanes, two
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
  exact-project authorization context. WS-MCP-002-03 adds six administrative
  reads for permission/role definitions, grants and actor/identity projections.
  Eighteen proposed tools remain; WS-MCP-002-04 administrative grant mutations
  are next. This remains a custom
  authentication adapter, not a public deployment or a 27-tool release.
  The [CLI foundation](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-01.md)
  provides `whoami` and `project access PROJECT_ID` through those public REST
  contracts. [CLI profile editing](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-02.md)
  adds caller-owned display-field set/clear through public PATCH, with explicit
  uncertain-outcome reporting and no automatic retry.
  [CLI project inspection](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-03.md)
  adds the existing public project read, preserving server-selected full/minimal
  fields and concealed foreign/revoked/suspended denials.
  [PILOT-02A task-import source custody](../.commitrail/changes/pilot02-task-import-source-custody.md)
  defines public covered-PM declaration, exact JSON upload, status and verified
  download with immutable failed/abandoned-source retention and existing ART
  automatic recovery, pending its ordered migration and public PostgreSQL/MinIO
  proof. It creates no Tasks; issue 489 retains atomic DRAFT
  import, explicit batch screen/release and CLI conversion as future boundaries.
  [CLI manager task browsing](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-04.md)
  adds one-page task discovery and exact task detail through existing manager
  reads, with server-owned live authority and opaque continuation.
  [CLI contributor discovery](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-05.md)
  adds ready-task pages and contributor instructions through public reads,
  preserving exact-project contributor scope and assignment visibility without
  claiming work. PILOT-14
  displays the task-locked ContributionPolicyVersion UUID and both unpaid or
  exact award terms in ready rows and task detail to a Submitter or Reviewer,
  while claim/start remain Submitter-only.
  [CLI contributor claim/start](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-06.md)
  adds the existing public writes with explicit retry keys, server-owned
  assignment/lineage, fresh-authority replay and uncertain-outcome handling.
  [CLI contributor context](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-07.md)
  adds the governing guide, exact policy selectors, server hints and locked
  intake requirements through public reads. Hints are not authority; no files
  are fetched, no policy is evaluated locally and hidden submission remains hidden.
  [CLI project creation](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-08.md)
  creates a draft shell through the public POST, with exact 201 response,
  caller-owned replay custody and explicit uncertain outcomes. It does not upload,
  approve or activate a guide. Committed recovery follows the existing project's
  API contract, not task replay authorization semantics.
  [CLI guide declaration](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-09.md)
  creates draft guide metadata, required illustrative tasks and document targets
  through public POST. The API reauthorizes exact replay and setup waits for
  document upload; the declaration command does not upload, approve or activate
  the guide.
  [CLI guide original upload](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-10.md)
  sends one declared document through the public binary POST, with bounded
  streaming, explicit replay custody and SHA-256/size-bound storage receipts.
  Unconfirmed storage is an unknown outcome, not success. Upload does not imply
  setup completion, policy approval or guide activation.
  [CLI setup inspection](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-11.md)
  reads the latest exact-guide setup and compilation lineage through the public
  diagnostic GET. Read success does not establish compilation success, policy
  approval or guide activation; no polling or setup execution is added.
  [PILOT-13 assigned-guide access](../.commitrail/changes/pilot13-assigned-task-guide-documents.md)
  lists exact locked originals in assigned contributor context and streams
  authorized, fully verified ART bytes. `task guide` lists or safely downloads
  them; setup examples remain private. Successor activation does not move a
  task's locks; actual rebase remains PILOT-08 work.
  Built-binary HTTP
  integration and isolated real-API proof accompany
  the package. Further public commands, optional TUI and binary distribution
  remain planned; CLI reads do not complete unfinished product lifecycle work.
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
  binds the exact version's examples. Upload admission accepts PDF, DOCX, PPTX and byte-preserved UTF-8 Markdown (`.md`)
  and checks bounded format, digest and size.
  Committed originals do not bypass the separate verification required for
  submission ZIPs. Embedded document bodies and extractors are removed.
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
  those inputs or broad semantic accuracy. CP07 supplies complete-guide activation and immutable ContributionPolicy
  binding, exposed through AUTH-18 public manager activation. It requires both exact
  approvals and current complete review/revision inputs, supersedes the selected
  prior guide and promotes a draft Project atomically. Active-guide reads require
  the committed binding. AUTH-12H supplies live exact-project manager authority;
  CP08 locks and carries exact policy lineage through Task, TaskAssignment and
  Submission. ARCH-03D completes the hidden final intake handoff through exact
  historical TASK/PROJECTS ports; the public cutover remains pending.
- Contributor ZIP preparation uses one verified byte lineage from scratch
  inspection through durable admission and eventual Submission binding.

### Contribution and review foundations

- Finance Authority can manage compensation adapter bindings through the
  hidden, authorized boundary. CP07A aligns policy/binding mutations with AUTH
  by locking authority before product resources, and reconciles the database
  audit vocabulary for the existing binding actions. CP07 guide activation/binding, AUTH-12H live exact-project manager authority
  and AUTH-18 public manager activation are delivered.
- CP05A exposes ContributionPolicy discovery, read, draft update, publication
  and retirement through exact human Finance Authority, preserving immutable
  lifecycle history and default-denied uncomposed owners. Compensation-binding
  administration remains internal; public manager activation uses exact published
  selectors without granting Finance privileges.
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

[PILOT-15 / PR #514](https://github.com/Flow-Research/workstream/pull/514)
delivers byte-preserved UTF-8 Markdown (`.md`) guide admission, setup-agent reads
and task-locked contributor REST/CLI reads alongside PDF, DOCX and PPTX originals.
This guide-format capability is complete; it adds no downstream intake or
acceptance activation.

Delivered capabilities are summarized in the [scoreboard](#end-to-end-lifecycle-scoreboard);
their evidence is linked under [completed work](#what-has-been-completed).
The [dependency and ownership plan](../.commitrail/initiatives/WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
owns implementation sequencing. The existing checker phase service supports
hidden pre-submit execution/replay and hidden durable post-submit execution.
Exact post-submit service authority and ARCH-04E1A source-only facts/types are
implemented; automatic request delivery, routing and acceptance remain unavailable.
Live setup does not wait for downstream task/checker execution.

The [first complete contributor milestone](../.commitrail/initiatives/WS-ARCH-001/planning/PLAN.md#first-complete-contributor-milestone)
records the delivered checked-input, capacity and atomic Submission/request
steps. Remaining work is hidden completion routing after B7 request delivery, authorized outcomes, remediation,
live activation, public intake and a real end-to-end drill. Human review/revision
runtime follows that milestone. Initial public intake covers initial submissions
and checker remediation; the historical requirement to complete human-review
revisions before any public intake is not adopted. Prove remediation against hidden
handlers before activating false; do not make it depend on an already-live false path.

The broader v0.1 sequence below retains later scope:

1. **Integrate the delivered guide/task foundations.** CP08 lineage and
   ARCH-03B1–03B9 owner operations are delivered at the exposure boundaries
   listed above. ARCH-03C1 supplies exact reconciler authority and decision-bound
   receipts. ARCH-03C2 supplies atomic originating publication and production
   delivery with enforced prefork topology. ARCH-03C3 supplies exact-authorized
   manager task create/screen/release; ARCH-03C4 supplies the three public queues;
   ARCH-03C5 supplies exact-authorized detail and requirements; ARCH-03C6 supplies
   distinct locked-context reads; ARCH-03C7 supplies bounded public Audit Authority
   history access. AUTH-18 exposes manager activation context and the canonical
   guide activation POST. PILOT-02A defines canonical JSON import-source custody
   pending its ordered migration and public PostgreSQL/MinIO proof;
   atomic DRAFT import and explicit batch screen/release remain required for
   bulk task intake. The source prerequisite does not change guide locks or
   create Tasks. Guide activation requires exact
   current compilation, sufficiency, separate pre/post approvals, review/revision
   inputs and an explicitly selected published ContributionPolicyVersion.
   Registered checker implementations and configuration are checked without a
   Task, Submission, completed checker run or live REV implementation.
   The operation replaces superseded economic readiness. Retained economic
   data and downstream TASK consumers remain until their scoped cutover;
   deleting retained data is not authorized by code cleanup.
2. **Produce current post-submit evidence and policy-governed routing.** ARCH-04B's
   hidden exact input materialization and ARCH-04B2's hidden output custody are
   delivered. ARCH-04C executes the locked structural plan internally, supports its
   empty output set and persists one current result with its completion event.
   ARCH-04D1 enforces canonical ART material lineage for every terminal result
   retaining material, with database rejection, rollback and safe-upgrade proof.
   ARCH-04D2 supplies exact input/execute/finalize service authority and durable
   receipt custody. ARCH-04E1A supplies one immutable route-neutral source table,
   detached facts and source-neutral accepted-effects types. CON-03C adds immutable contribution/award storage. REV-12A1 supplies disabled controller/fence mechanics with PostgreSQL-enforced root-transaction checks, including raw-SQL savepoint rejection. CON-07 supplies a hidden source-neutral submitter participant and complete frozen award-set staging/replay under that caller-root fence. REV-04C composes FinalAcceptance, TASK accepted/completed effects and that CON participant in one hidden caller-owned transaction for either source. It adds no AUTH receipt, handler, route, currentness guarantee, audit/outbox consequence, fulfillment root or reviewer participant.
   Both branches have delivered request reservation 04E1B-A and hidden AUTH
   preparation 04E2-A before handlers 04E1B-B, activation 04E2-B and live 04E3.
   True routing may proceed after its own prerequisites to publish the exact TASK
   manifest and move `evaluation_pending -> review_pending` when no blocking
   failure exists; this does not write the REV queue. The delivered shared
   acceptance participant is an additional false-branch dependency; true
   admission has no CON prerequisite.
   CHECKERS owns durable execution/currentness; the shared facade does not
   create a second result store. Work evaluation may be deterministic or use
   an explicitly implemented model judge. A structural presence check cannot
   stand in for a required substantive quality evaluation. Unsupported required
   evaluators block the affected guide until implemented and included in a new
   approved catalogue-bound generation. Infrastructure retries and project
   setup faults are not contributor failures; `allow_review` is not acceptance.
   **For the first false-policy acceptance path:** consume the delivered TASK
   04E1A source facts through the delivered REV-04B source FK; TASK request/source-identity reservation (04E1B-A) and the hidden
   `task.post_submit.route` preparation for `workstream.task.post_submit_router`
   (04E2-A) are delivered. They bind exact `TaskAcceptedEffectsRequest` values
   without a Review. CON-07 now uses the delivered REV-12A1 fence to stage or
   exactly replay the contribution and complete zero/one/two frozen award set;
   paid replay checks its correlation and unpaid replay retains none. REV-04C
   now composes that result with FinalAcceptance and TASK effects. Hidden handlers
   04E1B-B remain after delivered 04E1B-B2 exact source preparation and 04E1B-B3 verified ZIP metadata plus B4 checked-packet custody and B5 shared bounded content. B6 supplies atomic Submission/dispatch using that content, exact creation/binding receipts and fresh-authorized select-only replay. Delivered 04E1B-B1 makes TASK-before-CHECKERS reservation,
   current-read and admission INSERT ordering mandatory, including intermediate
   admission waits and both mechanical race controls; the full
   authorized acceptance/successor race proof remains required. At activation 04E2-B make the
   exact AUTH decision-event receipt mandatory on the same strict input, with no
   optional/default path; add database-enforced FinalAcceptance/TASK/CON
   completeness, shared audit/outbox and prove a genuine allow with all effects
   in that caller transaction. Only then wire live 04E3. Isolated hidden controls
   prove mechanical participation, not acceptance authority. Prove real scoped activation/drain and 04F remediation before
   enabling false. This milestone creates the submitter contribution and
   applicable awards without live human queues/leases/decisions; it neither
   invents a reviewer nor removes the later human branch from v0.1.
   Before production acceptance composition or CON consumption, add mandatory exact AUTH custody
   to the same FinalAcceptance table and refuse retained pre-authority sources and dependent contribution/award rows unchanged; source
   storage alone grants no acceptance authority.
3. **Complete public intake and admission integration for claimable work.**
   CP08 already locks the complete guide and policy context before `READY`.
   Claim copies it to TaskAssignment without selecting another ContributionPolicy;
   hidden admission-backed Submission creation already copies that exact lineage.
   ARCH-03D connects the hidden final handoff to the approved unified-guide
   intake plan. The public cutover remains after evaluation and remediation
   prerequisites. Preparation returns
   correction feedback for blocking intake failures and publishes ready admission
   only after the required preparation/custody checks; the existing TASK creation
   operation consumes that admission with the assignment's locked lineage.
4. **Start the live REV path.** Reuse the packet, Review and FinalAcceptance
   storage completed before the automated path. Admit only canonical
   `allow_review`; claim a bounded lease and
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
7. **Release proof.** The isolated six-service local stack is available; use it
    to expose stable APIs and frontend surfaces, exercise the complete path
    through real database, durable-job, storage, security, failure, and recovery
    tests, then run the internal pilot. Compose health alone is not journey proof.

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
and full hosted behavior/integration checks remain required. Product
implementation is already progressing alongside this audit with separate file
ownership.

Commitrail's contribution-path and reviewer-routing improvements are delivered.
They support this work; they do not complete a product capability or create a
second permission system.

Retained checker ownership is database-immutable; finished outcomes cannot change
or receive additional results. Result insertion serializes with completion.
Detail reads first resolve the authorized parent Submission, then query the exact
run/task/submission.
Retained submission/checker history now uses canonical AUTH with separate
contributor and Project Manager projections. The obsolete token-role dependency,
compatibility identity writer, manual checker execution, finalize repair and
fabricated-actor Celery gate are removed. Retained records are preserved;
ARCH-04C supplies hidden durable execution and unfinished-attempt recovery;
ARCH-04D2 supplies exact service authority; automatic routing remains ARCH-04E work.

ARCH-04B adds hidden exact Submission materialization through TASK's immutable
read port and ART's consumed admission. Local/MinIO input is independently reread,
verified and projected through canonical bounded scratch. ARCH-04D2 supplies exact leased input authority before and after I/O.
Public intake and automatic checker dispatch remain unavailable.

ARCH-04B2 adds hidden typed checker-output `store` and byte-free
`recover(selector)` operations, per-slot preparation caps, generic put and
verification reuse, and flush-only immutable verified binding. Controlled
nonempty slots prove ART mechanics only; the current structural catalogue has
zero slots. ARCH-04C supplies CHECKERS reservation/currentness; ARCH-04D2 supplies
execute/finalize authority. Output write/bind authority remains unavailable. Public intake is not activated.

## Critical Dependency Map

```text
Delivered foundations (not a claim of full public integration)
  privacy-bounded API/Celery diagnostics (collector deployment still required)
  automatic unified setup + separate manager pre/post approvals
  public Finance ContributionPolicy administration + exact selected-version validation
  public manager activation context + exact guide activation/binding
  task/assignment/Submission lineage + hidden intake/creation
  ARCH-03D exact approved historical guide through durable intake handoff
  ARCH-04B hidden verified Submission input
  ARCH-04B2 hidden checker output store/recovery/binding (authority deny-only)
  ARCH-04C hidden durable execution/current results + atomic completion event
  shared dispatcher + exact-authorized hidden assignment invalidation
  ARCH-03C2 invalidation producer + first handler registration
  ARCH-03C3 exact manager task create/screen/release + replay
  ARCH-03C4 exact-authorized public task queues and ARCH-03C5 detail/requirements
  ARCH-03C6 distinct exact-authorized locked-context reads
  ARCH-03C7 bounded exact-authorized Audit Authority task history
  PILOT-13 assigned-task locked originals: document-only context + verified REST/CLI reads
  canonical contributor/manager Submission and checker history; obsolete gate removed
  ARCH-04D1 canonical ART material custody at terminal CHECKERS commit
  ARCH-04D2 exact input/execute/finalize authority + durable receipts
  ARCH-04E1A immutable route-neutral TASK source facts + type-only effects port
  ART-07A1 metadata-only packet membership types (no resolver/byte authority)
  REV-03B normalized immutable lease packets and live guide ingest custody
  REV-04A immutable Review/finding/resolution and completed request storage
    |
    v
  REV-04B immutable shared acceptance source storage (no AUTH custody or production writer)
  CON-03C immutable contribution records and fixed awards
  REV-12A1 disabled generation-zero controller and transaction fence (no authority)
  AUTH-19A exact source/receipt contracts and planned router (no execution or receipt storage)
  ARCH-04E1B-A immutable request and future source-ID reservation (no source publication)
  ARCH-04E2-A strict hidden preparation + nominal PREP adapter (action unavailable)
  CON-07 hidden source-neutral submitter participant + complete frozen award set
  REV-04C hidden FinalAcceptance + TASK effects + CON composition (no authority/route)
  ARCH-04E1B-B1 ordered reservation/current reads + admission INSERTs (no activation)
  ARCH-04E1B-B2 exact source proposal + B3 ZIP metadata + B4 checked packet custody + B5 bounded evaluation content
  ARCH-04E1B-B6 atomic Submission/dispatch + exact AUTH receipts + replay (no delivery/publication authority)
  ARCH-04E1B-B7 hidden request delivery (unregistered)
  REV-12A4A scoped Operator transitions + immutable AUTH/history custody + current-generation gates

Remaining integration
  PILOT-02A ordered source migration -> public PostgreSQL/MinIO custody proof
    -> separately scoped atomic DRAFT import -> explicit batch screen/release
  both branches: hidden completion routing 04E1B-B
    -> authority/consequence proof 04E2-B
  production false path additionally requires remediation before live activation
  true: own routing prerequisites; no CON/shared acceptance prerequisite
  selected false path first: delivered shared participant -> handler
    -> mandatory same-input AUTH receipt + DB complete-set closure
    -> TASK-before-CHECKERS race proof + shared audit/outbox
    -> exact authorized production manifest on delivered REV-12A4A controller
       (conditional awards atomic; payment delivery and obligation roots deferred)
  -> 04F hidden remediation + authorized recovery proof
  -> 04E3 live composition and false-policy readiness
  -> public initial/checker-remediation intake and immutable admitted Submission cutover
  -> automatically consume the durable current result + required checks pass
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
triggers use the same operation. Shared acceptance persistence and hidden CON
participation are separate foundations before false/pass routing activation; human
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

- Prove the public activation-to-intake journey: the public manager activation
  boundary and hidden intake handoff are delivered; public integration must consume its complete approved
  guide and policy identities/hashes, including ContributionPolicyVersion.
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
- Before either route is published, the existing TASK source table gains
  mandatory exact routing and owner-receipt custody and rejects retained
  pre-authority rows; no parallel manifest or permissive backfill is introduced.
- REV-12A4A supplies authorized lifecycle transitions and phase-gated atomic
  participants. Before production shared acceptance, extend its reviewed manifest
  with genuine source-receipt custody and complete authorized consequences.
  Conditional awards remain atomic. Fulfillment obligation/root/ordinal storage
  and real cutoff/drain proof are required when payment fulfillment is enabled,
  not before the first contribution path. No fabricated observation or
  permissive generation can replace a supported manifest.
- A reviewer can claim only that admitted version, access only its bounded
  packet, and record one immutable final decision.
- `needs_revision` safely continues or rebases the same assignment while
  preserving every earlier attempt; `reject` and `accept` have their exact
  distinct effects.
- Every final review atomically creates the reviewer ContributionRecord;
  `accept` additionally creates FinalAcceptance and the submitter record.
- The delivered REV-04C participant composes FinalAcceptance, TASK effects and
  CON-07's zero, one, or two frozen CompensationAwards in one caller transaction
  without controlling Workstream lifecycle truth; isolated hidden participation
  is not release proof.
- Fulfillment and recovery are idempotent, observable, reconcilable, and safe
  under durable-job, provider, transaction, and unknown-commit failures.
- Configure secured diagnostic collection with bounded retention and access,
  and prove API/Celery correlation, privacy and collector-outage behavior in
  the release drill. Implemented instrumentation alone is not deployed monitoring.
- Public APIs and frontend surfaces expose only the canonical paths, obsolete
  authority and legacy routes are removed, and the full security/operations
  drill plus internal pilot passes without weakening safeguards.

## Trace References

The [observability foundation record](../.commitrail/changes/observability-foundation.md)
and [operator guide](engineering/observability.md) define diagnostic scope and
remaining deployment responsibilities.

The [local pilot stack record](../.commitrail/changes/pilot-local-stack.md) and
[runbook](engineering/local-pilot.md) define the checkout-isolated runtime,
authority bootstrap, retained-data boundary and remaining platform/journey
proof.

The [offline gVisor build spike](engineering/pilot00-gvisor-offline-build-spike.md)
selects a sealed-cache Kaniko builder plus a separate gVisor oracle sandbox for
PILOT-04/PILOT-06. It proves only the included small Linux fixture; the external
launcher, representative task sizing, hosted hardening and macOS fallback
evidence remain.

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
  three queues with distinct grants and signed pagination.
  [ARCH-03C5](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03C5.md) exposes
  exact-authorized Contributor/Manager task detail and requirements.
  [ARCH-03C6](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03C6.md) exposes
  distinct manager, system-Operator and Audit Authority locked-context reads.
  [ARCH-03C7](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03C7.md) exposes
  bounded task history under covered Audit Authority. ARCH-04A supplies registered-capability
  contracts; activation does not require a Task, Submission or completed run.
- Contribution lineage: CP05 authorization, CP06 validation, `CP07` activation
  and `AUTH-12H` live manager authority are complete.
  [AUTH-18](../.commitrail/initiatives/WS-AUTH-001/WS-AUTH-001-18.md) exposes
  manager activation selections and the canonical public activation POST. `ARCH-03A` has completed
  the existing internal guide-context port. `CP08` delivers lineage fields
  and minimal Task/Assignment/Submission writers together without superseded economic
  readiness. Atomic assignment-invalidation publication and delivery are complete
  in `ARCH-03C2`, following real authority in `ARCH-03C1` and
  `ARCH-03B1` metadata and ARCH-03B2/03B3 hidden queues and ARCH-03B4 hidden detail and ARCH-03B5 current work context, ARCH-03B6 locked-context and ARCH-03B7 requirements and ARCH-03B8 hidden audit evidence and ARCH-03B9 hidden assignment invalidation, and authorization/public cutover in `ARCH-03C`. The [completed physical cleanup](../backend/alembic/versions/0023_remove_task_payment_policy.py)
  removes unused guide-keyed payment storage and TASK/Submission fields through
  migration 0023, with retained-data refusal. Historical CP09 sequencing is no
  longer a pending removal or an `allow_review` activation dependency.
  Shared dispatch authority is delivered by AUTH-OUTBOX-02. Live assignment
  invalidation has atomic producer fan-out and registered delivery in ARCH-03C2.
  Manager readiness commands are public with exact authority in ARCH-03C3;
  ARCH-03C4 exposes ready, management and Operator-status queues. PILOT-14
  adds contributor-safe
  locked compensation to ready/detail without restoring removed task payment
  fields or exposing Finance bindings. ARCH-03C5 exposes task detail and
  requirements; ARCH-03C6 exposes distinct
  locked-context reads; ARCH-03C7 exposes bounded Audit Authority history. Current authority is checked
  on every request.
- Hidden intake: [ARCH-03D](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03D.md)
  removes the private TASK/PROJECTS lookup at final durable handoff. No public
  preparation or Submission endpoint is activated.
- Post-submit admission: after delivered `POL-07B` and `ARCH-03C`, delivered hidden
  [ARCH-04B input materialization](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04B.md)
  and [ARCH-04B2 output custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04B2.md)
  and [ARCH-04C durable execution](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04C.md)
  and [ARCH-04D2 exact service authority](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04D2.md)
  lead to delivered
  [ARCH-04E1A source facts](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1A.md).
  [ARCH-04E1B-B2](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB2.md) adds exact source preparation without publication or authority.
  Delivered [ART-07A1 packet types](../.commitrail/initiatives/WS-ART-001/WS-ART-001-07A1.md), [REV-03B packet persistence](../.commitrail/initiatives/WS-REV-001/WS-REV-001-03B.md),
  [REV-04A Review source storage](../.commitrail/initiatives/WS-REV-001/WS-REV-001-04A.md)
  and [REV-04B acceptance storage](../.commitrail/initiatives/WS-REV-001/WS-REV-001-04B.md),
  followed by delivered [CON-03C contribution/award storage](../.commitrail/initiatives/WS-CON-001/WS-CON-001-03C.md),
  [REV-12A1 disabled controller/fence](../.commitrail/initiatives/WS-REV-001/WS-REV-001-12A1.md)
  and [CON-07 hidden participation](../.commitrail/initiatives/WS-CON-001/WS-CON-001-07.md),
  plus the REV-04C hidden FinalAcceptance/TASK/CON participant, support the
  additional false-path acceptance-source AUTH custody and activation prerequisites. Both branches have delivered request reservation `04E1B-A` and AUTH preparation `04E2-A`,
  then handlers/activation/live `04E1B-B -> 04E2-B -> 04E3`; true
  routing proceeds after its own prerequisites without shared acceptance; 04F supplies remediation. The mandatory
  [04D1 canonical material custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04D1.md)
  closes the three-field ART database guarantee before authority activation.
  ARCH-04C accepts the exact empty output set from the current structural
  catalogue; nonempty 04B2 test slots do not claim a live evaluator capability.
  AUTH-OUTBOX-02 delivers shared live authority, phase audit custody and Celery
  delivery/recovery scans over CON-02B. Delivery termination is bounded by a
  300-second hard limit under prefork.
  ARCH-03C2 enforces a dedicated non-eager prefork delivery queue.
  ARCH-04E1A proves source storage and detached contracts only; its false scalar
  proof does not make false activation available. Automatic `04E` delivery still needs its
  separately authorized checker-routing handler; the installed assignment handler
  does not supply that authority. These foundations do not require REV or fulfillment.
  TASK request/source-identity reservation `04E1B-A`, hidden AUTH preparation
  `04E2-A`, CON-07 participation and REV-04C hidden FinalAcceptance/TASK/CON
  composition are delivered. The selected automated path next adds hidden
  handlers `04E1B-B`, then mandatory authority/evidence closure and activation
  at `04E2-B`, followed by live integration `04E3`; a dispatcher cannot authorize TASK or CHECKERS mutations.
  Later `04F` owns contributor-correctable remediation and admission-backed
  resubmission before public cutover; it does not block `allow_review` or
  replace human review/revision.
- [CON-03C contribution/award storage](../.commitrail/initiatives/WS-CON-001/WS-CON-001-03C.md)
  supplies immutable source/economic equality. [CON-07 hidden participation](../.commitrail/initiatives/WS-CON-001/WS-CON-001-07.md)
  supplies source replay and complete frozen award sets; REV-04C composes them
  with hidden FinalAcceptance and TASK effects, without live recognition,
  acceptance authority or fulfillment.
- Review/revision: REV packet/schema foundations may proceed independently,
  but live admission starts after `ARCH-04E`; the first live Review commit also
  requires the atomic CON decision participant on the delivered CON-03C storage.

For implementation ownership and exact contracts, contributors can follow
[Commitrail Engineering Index](../.commitrail/INDEX.md). For historical
decisions, use the [Historical Planning Index](historical_planning.md).

AUTH-19A source-contract boundary: [exact commitments and remaining custody](../.commitrail/initiatives/WS-AUTH-001/WS-AUTH-001-19A.md).

ARCH-04E1B-B3 proof: [verified ZIP metadata custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB3.md).

ARCH-04E1B-B6 proof: [atomic Submission, exact receipts and initial request custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB6.md).

ARCH-04E1B-B7 proof: [hidden request delivery and invocation custody](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E1BB7.md). Production registration, completion routing and public intake remain unavailable.

REV-12A4A proof: [scoped lifecycle control and payment-delivery deferral](../.commitrail/initiatives/WS-REV-001/WS-REV-001-12A4A.md). Exact production source receipts and acceptance activation remain required.
