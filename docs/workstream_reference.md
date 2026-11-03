# Workstream Technical Reference

This document holds the detailed product, lifecycle and implementation notes that
were previously in the README. Read the [README](../README.md) first for a short
introduction. The [v0.1 Roadmap And Capability Status](roadmap_status.md) is the
current capability ledger.

## Definition

Workstream defines a shared protocol for governed work and provides the
software that implements it. It coordinates, verifies, and records work
performed by humans, AI agents, or both. It transforms
project-defined tasks, immutable submissions, policy-governed checks, and
policy-governed acceptance into trusted `ContributionRecord` facts that applications,
organizations, and economic systems can consume.

The protocol defines valid lifecycle actions and records; the software
enforces those rules. A standalone versioned protocol specification and
conformance suite remain formalization work, not delivered interoperability
claims. See [Protocol And Implementation](protocol-and-implementation.md).

Workstream governs the work lifecycle; it does not need to own the system that
requested the work, the tools used to complete it, the identity provider, or
the consequence applied afterward. A project defines the rules, an authorized
contributor performs the work, Workstream binds the exact submitted artifact to
those rules and its verification evidence, and records the authorized outcome
under the project's locked acceptance rules. The resulting immutable contribution lineage establishes who did
what, under which rules, using which artifact, and with what verified result.

## End-To-End Lifecycle

The complete Workstream model is:

```text
Project Guide
-> Versioned Policies
-> Task Assignment Or Claim
-> Artifact Preparation And Pre-Submission Intake Checks
-> Immutable Submission
-> Post-Submission Work Evaluation
-> Policy-Governed Acceptance (Human Review When Required)
-> Accept / Needs Revision / Reject
-> Revision And Resubmission When Required
-> Immutable ContributionRecords
-> Optional Project-Specific Consequences
```

The current submission contract normally receives one outer ZIP containing the
complete work. Workstream computes canonical content identity, stores the bytes
through its artifact boundary, verifies stored content before trusted use, and
runs configured checks against the submitted package and its bounded recursive
contents. After Submission creation, the contributor's submitted work,
post-submission checkers, reviewers, and downstream projections are tied to the
same immutable Submission lineage. Before creation, intake evidence refers to
the prepared artifact and locked intake context, not an existing Submission.

Pre-submission and post-submission checking are different stages:

- **Pre-submission intake checks** assess whether the prepared package is fit
  to submit: required outputs, packaging, evidence integrity, and configured
  intake-quality rules. Blocking failures return feedback before a Submission
  is created. Passing intake does not establish that the task was done correctly.
- **Post-submission work evaluation** assesses the immutable submitted work
  against the locked task/project requirements. Durable results determine
  review eligibility, not final acceptance. Task-specific evaluation may use
  deterministic rules or, when supported and registered, model/agent-based
  evaluators such as a quality judge. These are not the setup agent that
  proposes checker policies. Raw checker results are not acceptance authority;
  when human review is required they do not replace that Review.

The v0.1 project setting `human_review_required` defaults to `true` in the
existing locked ReviewPolicy. After required post-submit checks pass, true
requires human review; false uses an authorized automated FinalAcceptance and
submitter ContributionRecord, with no reviewer contribution.
The separate `requires_second_review` policy field is [fixed to `false`](../.commitrail/changes/enforce-requires-second-review-false.md)
at input, immutable lineage, and database boundaries; second-review and
adjudication behavior remain deferred.
The automated-acceptance branch is implemented in the selected backend
composition: supported false-policy guides can activate, and selected completion
routing uses the shared FinalAcceptance/TASK/CON operation. New false/pass effects
require an Operator-authorized live REV generation whose immutable transition
binds the current reviewed manifest. An older live authorization cannot enable
expanded scope; a typed pre-effect refusal rolls back and uses bounded OUTBOX
retry. The bounded local public API and Celery service drill starts from public guide
inputs with recorded inference;
this is not a deployment claim. Adjudication is excluded.

The stage describes the purpose and lifecycle boundary, not a promise that all
checks are deterministic. Deterministic compilation and policy routing do not
make model-based judgments reproducible. Only supported implementations run;
the [roadmap](roadmap_status.md#pre-submission-and-post-submission-checking)
distinguishes existing foundations from remaining integration and does not
claim a live agent judge.

On the human-review branch, every valid Review creates a reviewer `completed_review`
`ContributionRecord`. An `accept` decision also creates `FinalAcceptance` and a
submitter `accepted_submission` `ContributionRecord`. These records cannot be
created or edited directly by a person or downstream adapter. Together they are
the central durable outcome of Workstream.

## How Workstream Establishes Trust

- **Identity is separate from authority.** External identity verification does
  not grant product access. Explicit administrative or project-scoped grants,
  resource ownership, lifecycle guards, and revocation determine authority.
- **Project rules are versioned and locked.** Assignments, submissions,
  Reviews, and contributions retain the guide and policy context that governed
  them instead of silently adopting later rules.
- **Artifacts are immutable and content-addressed.** Workstream derives identity
  from server-computed SHA-256 and byte count, independently verifies stored
  bytes, and binds trusted content facts to that identity.
- **Checks have distinct, attributable evidence.** Pre-submit results refer to
  the prepared artifact and locked intake context before Submission creation.
  Post-submit results refer to the immutable Submission and locked evaluation
  policy. Intake feedback cannot substitute for post-submit review-gate evidence;
  recording an evaluation does not guarantee an identical judgment on rerun.
- **Review is authorized and attributable.** A Review records the authorized
  reviewer, exact artifact lineage, locked rules, findings, and one canonical
  decision: `accept`, `needs_revision`, or `reject`.
- **Separation of duties limits self-dealing.** Submitter and reviewer authority
  are independent, self-review is prohibited, and narrower project conflict
  rules may be enforced.
- **History is preserved.** Submissions, findings, responses, resolutions,
  Reviews, contribution records, awards, receipts, and audit evidence remain
  linked rather than being overwritten.

## Source-Agnostic Core, Bounded v0.1 Intake

Workstream does not require tasks to originate from one marketplace,
application, organization, or industry. AI evaluation programs, government
workforce initiatives, research programs, open-source projects, contractor
pipelines, academic review, data-labeling operations, and legal, medical,
engineering, creative, human-to-agent, or agent-to-agent workflows can use the
same governed lifecycle while retaining their own user experience and operating
model.

Source-agnostic does not mean every source adapter is already implemented.
v0.1 remains manual-first. PILOT-02A provides Project Manager declaration, upload,
inspection and verified download of canonical JSON task-import sources through the
[public ART contract](spec_artifact_storage_service.md#task-import-source-custody).
Its public routes are covered by PostgreSQL/MinIO custody, authority, replay and
recovery tests. PILOT-02B imports one verified JSON source into immutable native
batch membership and 1..500 DRAFT Tasks atomically, with fresh-authority exact-file
replay and batch status through the public TASK contract. Its actual 200-row and
rollback/custody controls pass on PostgreSQL and MinIO. PILOT-02C adds explicit atomic batch screening
and release and CLI source/import/status commands with local CSV conversion. A client-converted CSV retains
its received JSON rather than claiming original CSV custody.
External origin onboarding, external task-routing systems, and execution workspaces remain
later adapters. Revision and reassignment belong to the governed lifecycle;
adjudication remains a separately approved future capability rather than a
claim about current v0.1 behavior.

## Long-Term Intelligent Orchestration Direction

After the governed v0.1 lifecycle is proven, a future orchestration adapter may
propose task dependencies and contributor matches for work distributed across
humans and AI agents. Existing Workstream services would still authorize and
version tasks and assignments, bind artifacts and checks, record Reviews and
revisions, and create contribution facts under the canonical lifecycle.

This is a research hypothesis, not current or planned runtime behavior.
Execution remains in a source application such as Garden or another external
host. See the [Product Brief](product_brief.md#future-research-hypothesis-accountable-orchestration)
for the canonical hypothesis. Current availability is governed only by
[Current v0.1 Status](roadmap_status.md).

## Product Boundary

Workstream determines what governed work occurred and whether the resulting
contribution fact can be trusted. Payments, points, tokens, staking, slashing,
reputation, eligibility, reporting, datasets, and model-training systems may
consume that fact and apply project-specific consequences. They do not create,
revise, or control Workstream identity, authorization, submission, review, or
contribution truth.

That boundary allows one Workstream core to support centralized, sovereign,
federated, and permissionless applications without coupling lifecycle truth to
any one application's business or economic model.

Flow Identity is the current v0.1 external authentication provider. It is an
adapter boundary, not the definition or ownership boundary of Workstream.
Workstream is not an execution workspace and is not blockchain-first.

## Core Invariants

Different projects speak different domain languages, but Workstream preserves
the same governing invariants across them:

- project guides and policies are versioned before they govern work
- tasks, assignments, submissions, checks, and Reviews retain their exact
  project and actor lineage
- invalid submission packets stop before trusted Submission creation
- findings, responses, resolutions, Reviews, and contribution facts append to
  history rather than rewriting it
- `FinalAcceptance` is the sole source of an accepted submitter contribution
- conditional compensation follows contribution truth and never controls it

These invariants turn project-specific operating knowledge into reusable
infrastructure without narrowing the complete v0.1 lifecycle defined above.

## Current v0.1 State

Workstream is under active v0.1 development. Progress is tracked by proven
capabilities, not by calendar weeks or promised dates.

Implemented foundations include external Flow-token verification,
canonical local actors and authorization, project guides and task records,
submission packets, immutable artifact storage, pre-submit intake checks,
and authorized retained submission/checker history. ARCH-04C implements hidden
durable post-submit execution and unfinished-attempt recovery. ARCH-04D2 supplies
exact service authority. ARCH-04E1A adds immutable route-neutral TASK source
storage, detached source facts and accepted-effects contracts. B6 commits each
new hidden Submission with its initial checker reservation and outbox request;
selected production request/completion delivery now runs digest-pinned external
images after the Workstream default checker and approved external PRE checks.
Passing true-policy results reach `review_pending`; eligible false-policy results
invoke shared authorized acceptance atomically after an Operator-authorized LIVE
REV generation. ARCH-02I-B exposes public admission-backed Submission entry,
and ARCH-04E3-B admits complete false-policy guides with supported approved
checks. The bounded local public API and Celery service journey drill starts from public
guide inputs with recorded inference;
the bounded local run passed both policy outcomes, restart/replay, late
authority revocation and cleanup. Recorded inference is not live-model or hosted
deployment proof.
Project-guide ingestion stores original documents,
records immutable metadata and provides authorized exact-file reads to the
unified setup agent. Accepted originals are PDF, DOCX, PPTX and byte-preserved
UTF-8 Markdown (`.md`); HTML and documentation sites are not guide inputs. Guide
metadata in PostgreSQL also holds at least one required task example; the agent
assesses the examples with the uploaded guide documents.

Default-only projects need no external-service configuration. The fixed Rust
provider is resolved only when a required project image executes; missing
configuration for that image produces recoverable infrastructure evidence.
Findings and policy proposals retain document-access evidence.

[ART-07A1](../.commitrail/initiatives/WS-ART-001/WS-ART-001-07A1.md) provides strict
metadata-only reviewer packet types, not a resolver or byte-access capability.
REV-03B persists immutable normalized packets using live guide ingest identities.
REV-04A Review and REV-04B shared FinalAcceptance storage foundations are delivered; CON-03C contribution/award storage, REV-12A1's disabled controller/transaction
fence, exact hidden AUTH preparation and CON-07 hidden source-neutral submitter
participation with complete frozen award sets are delivered. REV-04C adds one
hidden source-neutral participant that stages FinalAcceptance, TASK
accepted/completed effects and the complete CON submitter outcome in the caller's
transaction. ARCH-04E2-B binds its mandatory actual AUTH decision-event receipt,
database complete-set enforcement, currentness custody and shared audit/outbox
in one hidden authorized outcome operation. REV-12A4A supplies internal
Operator-authorized transitions on the existing lifecycle controller. New
participant effects require a live, nonzero generation; exact terminal replay
remains read-only in stopped phases. The controller itself grants no routing
authority; ARCH-04E2-B consumes the separate exact AUTH action. Payment delivery
stays disabled.
ARCH-04E1B-B1 requires TASK locking before checker reservation, current-result
reads and review admission INSERTs, preserving exact read-only reservation replay
after acceptance. ARCH-04E1B-B3 retains the inspected ZIP file metadata with immutable
ART evidence and returns it on consumption without another storage read. ARCH-04E1B-B6 commits each new Submission, verified binding, exact AUTH receipts,
generation-one evaluation reservation and one shared outbox request atomically.
Fresh-authorized replay returns the original identities without recreating rows. ARCH-04E1B-B4 binds the
Submission summary and attestation to the packet that passed intake, with
service and database enforcement. ARCH-04E1B-B5 rejects evaluation content that
exceeds the locked checker limits before any pre-check attempt or durable upload
intent, using the same content contract required by later dispatch. ARCH-04E1B-B2 prepares exact source proposals from current
CHECKERS custody and historical PROJECTS policy, without inserting a manifest
or granting authority by itself. ARCH-04E2-B consumes this source in the complete
authorized outcome. B8 supplies hidden completion delivery; 04F2 routes verified
contributor-correctable failures to `needs_revision` under either policy mode.
ARCH-04F3 admits a changed full replacement ZIP only for that exact current
authorized checker-remediation source. The existing intake and atomic Submission
writer retain its cause, predecessor and locked policy lineage while creating
the successor evaluation request. This hidden path creates no Review or
contribution on failure. ARCH-04F4 adds hidden reason-bound Operator retry for
known terminal infrastructure failures using the existing CHECKERS coordinator
and request handler, with exact AUTH, audit and outbox custody. Fresh-authorized
replay validates the historical request. The current selected completion classifier has no `task_setup_blocked` path.
A future setup-fault hold must preserve the Submission and locked rules without
contributor penalty; changing or re-screening submitted-task rules remains
deferred. PILOT-04 registers selected production request/completion delivery.
ARCH-02I-B exposes public initial and checker-remediation intake, and
ARCH-04E3-B admits supported false-policy guides with exact Python/PostgreSQL
custody. A known pre-effect refusal while REV is non-live retries within the
existing OUTBOX attempt budget; exhaustion dead-letters without automatic
reopen. The bounded local public API and Celery service drill starts from public guide
inputs with recorded inference.

Active work stays on that first contribution path. Live human review/revision,
reviewer participation and fulfillment delivery follow separately.
Contribution evidence remains the input for a separately implemented future
reputation projection. Frontend product work follows stable and tested backend
contracts for the surface it consumes.

The release bar is a verified end-to-end v0.1 lifecycle, not the completion of
an old timeboxed plan. See the [v0.1 Roadmap And Capability Status](roadmap_status.md)
for the lifecycle scoreboard, current critical path, and complete release gates;
reading internal engineering records is not required to understand product
progress.


## Authorization Baseline

Workstream verifies externally issued Flow authentication tokens and owns its
product authorization. Token role claims, email, display name, skills,
reputation, and typed workflow profiles are not product authority. Canonical
authority comes from local actor identity links, administrative grants,
exact-project contributor grants, registered permissions, resource/lifecycle
guards, revocation, and append-only evidence.

All public API documentation uses `/api/v1`. Imported reference specifications
are immutable archival inputs. ADR 0012 and the canonical authorization service
specification control authorization; ADR 0016 and the canonical contribution
and compensation specification control contribution recognition, award
eligibility, and fulfillment boundaries. Older chunk specifications remain
implementation history until their owning migrations replace the runtime.

## Terminal Client

The independent [Go CLI](../cli/README.md) provides `workstream whoami` and
`workstream project access PROJECT_ID`, plus `workstream profile update` for
caller-owned human display fields, through the currently public REST API.
`workstream project show PROJECT_ID` inspects the project fields returned for
the caller's current authority, preserving contributor-minimal disclosure.
`workstream project tasks PROJECT_ID` and `project task PROJECT_ID TASK_ID`
provide a paginated manager list-to-detail journey through public reads.
`workstream task ready PROJECT_ID` and `task show TASK_ID` provide contributor
discovery and instructions, with live Submitter authority and no task claim.
`workstream task claim TASK_ID --idempotency-key UUID` assigns and starts work
atomically through existing public APIs, with server-owned authority,
explicit caller retry keys and uncertain-outcome reporting without automatic retries.
`workstream task context TASK_ID` and `task requirements TASK_ID` inspect the
governing guide/policy selectors, server action hints and locked intake rules.
Hints do not grant authority; these CLI reads do not invoke the separate public
submission upload and creation operations.
`workstream task prepare` streams the contributor ZIP once with an explicit
caller key; `task submit` separately consumes its ready admission and exact
packet. Preparation never creates a Submission or automatically polls/retries.
`task submissions`, `submission show` and `submission findings` read bounded
public history and contributor checker evidence, not inferred acceptance.
See the [submission command contract](../cli/README.md#prepare-submit-and-inspect-contributor-work)
for replay, packet-header restrictions and proof boundaries.
`workstream task guide TASK_ID [--download DIR]` lists or downloads the original
documents of the task's locked guide for its currently authorized assignee.
Downloaded bytes are verified against their retained hash and size; task examples
remain private, and newer guide activation does not change existing task locks.
`workstream project create --name TEXT --slug TEXT --idempotency-key UUID`
creates a draft project shell through the public API, with explicit manual
replay and uncertain-outcome handling; it does not approve or activate a guide.
`workstream project guide create PROJECT_ID --input FILE --idempotency-key UUID`
declares a draft guide, task examples and document upload targets. It does not
upload documents or approve the guide; returned setup waits for those documents.
`workstream project guide upload PROJECT_ID GUIDE_ID DOCUMENT_ID --file FILE
--media-type MIME --idempotency-key UUID` uploads a declared original. The CLI
streams its bytes and validates the storage receipt against their hash and size.
An upload receipt is not setup completion, policy approval or guide activation.
`workstream project guide setup PROJECT_ID GUIDE_ID` reads the latest public
setup status and compilation lineage. A successful diagnostic read is not
approval or activation; there is no polling or setup execution in the CLI.
`workstream project guide proposal PROJECT_ID GUIDE_ID COMPILATION_ID` reads
the exact finalized proposal, findings, artifact policy and PRE/POST suggestions
with their check specifications and target. It never substitutes the latest
compilation or approves a policy.
`workstream project guide approve-pre PROJECT_ID GUIDE_ID COMPILATION_ID --input
FILE --idempotency-key UUID` submits the deliberately prepared public intake
approval request. It preserves the exact target, ordered warning acknowledgments
and prior-approval selectors, plus the explicit human PRE/POST image attachment
lists, with explicit manual replay. The backend owns fresh
authority, currentness and policy validation; the receipt proves intake approval,
not post-policy approval, post-policy job delivery or guide activation.
`workstream project guide post-policy PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID`
reads the exact derived evaluation policy, upstream proposal/findings, activation
selectors and saved correction through one public GET. Compiled, approved and
superseded packages remain observations, not approval or activation.
`workstream project guide approve-post PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID
--input FILE --idempotency-key UUID` separately approves the inspected evaluation
policy. It preserves the caller's exact target and retry key, validates the
complete returned target, and never activates a guide or retries automatically.
`workstream project guide correct-post PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID
--input FILE --idempotency-key UUID` requests a unified setup successor for the
inspected policy and supplied feedback. Its saved correction receipt does not
dispatch setup, replace policy content or activate a guide.
`workstream project guide correct PROJECT_ID GUIDE_ID COMPILATION_ID --input
FILE --idempotency-key UUID` saves correction feedback for the exact finalized
proposal. `workstream project guide dispatch-correction PROJECT_ID GUIDE_ID
COMPILATION_ID --input FILE` explicitly dispatches the successor identified by
that saved correction receipt (or the `correction` member from `correct-post`).
It reports the backend's diagnostic status, not completed processing or activation;
uncertain writes are never automatically retried.
`workstream project guide activate PROJECT_ID GUIDE_ID --input FILE
--idempotency-key UUID` separately activates exactly selected, approved policies
through the public manager API. It validates the immutable activation receipt;
Workstream retains readiness, contribution-policy binding and supersession
authority. It does not approve policies or bypass activation readiness: supported
false-review guides use the same backend-owned activation checks.
`workstream project task create PROJECT_ID --input FILE --idempotency-key UUID`
creates a draft; separate `project task screen PROJECT_ID TASK_ID` and
`project task release PROJECT_ID TASK_ID --reason TEXT` commands each require
their own retry key. Workstream owns guide/policy locking and readiness; no
command automatically prepares or releases work after another command.
PILOT-02's `workstream project task-batch` commands add local CSV conversion,
source declaration/upload/status, atomic import and separate whole-batch
screen/release through public APIs. They share the same CLI; they neither
replace individual-task commands nor form a prerequisite for evidence export.
`workstream project role-grant issue PROJECT_ID --input FILE --idempotency-key UUID`
and `project role-grant revoke PROJECT_ID GRANT_ID --input FILE --idempotency-key UUID`
send deliberate Submitter/Reviewer decisions with explicit qualification evidence
and reasons. AUTH retains exact-project manager authority, qualification capture
and fresh-authorized replay; receipts are observations, not cached permission.
`project role-grant list PROJECT_ID` reads one optionally filtered, count-free
page; `project role-grant show PROJECT_ID GRANT_ID` inspects complete public
qualification/provenance and revocation history. Pagination is explicit and
fresh authority is backend-owned; a read never authorizes a later write.
`project role-grant candidates PROJECT_ID [--limit N] [--cursor TOKEN]` reads
only the backend's two-field, exact-project candidate page for a covered Project
Manager. Its opaque continuation is explicit; discovery neither qualifies an
actor nor issues a grant or exposes a global actor directory.
`project contribution-policy current PROJECT_ID` discovers the published and
open-draft selectors; `project contribution-policy show PROJECT_ID POLICY_ID
[--version UUID]` inspects backend-selected or exact historical policy versions,
including complete rules and exact quantities. These read commands require
current Finance Authority, not PM-only permission; they do not edit, publish,
retire or pay.
The `create`, `update`, `publish` and `retire` commands in that same group expose
separate Finance decisions with explicit idempotency keys and exact version
selectors. They return immutable event receipts; guide activation stays separate.
All support human-readable and JSON output, using the caller's Flow token.
`workstream contributions [--project UUID]` reads the caller's contribution
evidence; `workstream project contributions PROJECT_ID` exports one authorized
project. Both support recorded-time/type filters and `--csv FILE` for the exact
server export, saved privately without overwrite. The backing REST reads use
signed fixed-membership cursors for selections up to 100,000 contributions,
freshly authorize every page, and expose continuation in JSON or the CSV
response header. The CLI follows continuation internally with the same filters,
retains its existing complete JSON output shape, and publishes CSV only after
every page validates. A later-page denial or malformed response leaves no
partial stdout result or destination file. Earned awards are not proof of
payment; these reads do not activate unfinished lifecycle writers.
The first source package is buildable; further workflow commands and published
binaries remain planned.

## Repository-Native Human-Agent SDLC

Workstream uses a Repository-Native Human-Agent SDLC. Plans, tests, review, and
durable decisions live with the code so humans and agents can collaborate
without depending on chat history. GitHub permissions and branch protection
remain the repository authority; process notes never create a second permission
system.

```text
Intent
-> Plan
-> Bounded Change
-> Evidence
-> Review
-> PR
-> Human Merge
```

Codex-discoverable skills live in `.agents/skills/`. Codex custom reviewer
agents live in `.codex/agents/`. The smallest useful durable engineering
records live in `.commitrail/`; start with its `README.md` and `INDEX.md`.

This engineering loop is separate from Workstream product state. It governs how
the repository is changed; it does not define runtime task or review records.
Independent initiatives and branches may proceed concurrently. Start with
[CONTRIBUTING.md](../CONTRIBUTING.md) before proposing repository work.

The shared outbox dispatcher uses the fixed service identity and phase-specific
AUTH/PREP decisions for claim, invocation and finalization. AUTH-OUTBOX-02 binds
those decisions to immutable delivery receipts and supplies Celery delivery and
bounded recovery scans. ARCH-03C2 registers exact assignment invalidation,
with atomic publication from supported authority mutations and separate fixed
feature authority. The selected checker request and completion handlers are
registered in production composition. ARCH-02I-B exposes ZIP preparation and
admission-backed Submission creation for initial work and checker remediation
through public backend APIs. Registration does not establish deployed sandbox readiness.
Delivery consumes `workstream.outbox` only under a validated non-eager prefork
Celery process; other queues can use their appropriate execution pool.


## Implementation Notes: Guide Setup, Policies And Task Context

Verified guide-source readiness automatically delivers one compilation. A ready
result records both policy proposals and stops at a draft; an insufficient guide
stops with findings. Automatic compilation ends without approving the proposals.
POL-05B exposes exact Project Manager proposal review, pre-submission approval,
setup-wide correction and explicit manual dispatch using POL-05A operations and
AUTH-12F4 authorization. The setup response supplies `finalized_compilation_id`
for opening the exact complete proposal, plus `correction_operation_id` and
`predecessor_compilation_id` for recovering a saved correction after manager
handoff or a lost creation response. See the
[manager proposal flow](operations_project_operating_manual.md#review-approve-or-correct-a-guide-proposal).
POL-06B connects deterministic post-submission policy derivation to committed
pre-submission approval. The fixed setup service derives from the saved result;
project managers discover its `post_submit_policy_id` through the proposal read,
inspect its complete body, and separately approve it or request a unified
correction. Both correction origins use the same explicit manual dispatch.
Derivation, reads, approval and correction creation do not invoke inference or
post-submit evaluators. A periodic scan recovers publication failures from
committed approvals; duplicate delivery retains one policy and receipt.
Hidden post-submission execution and completion custody are implemented.
ARCH-04D2 supplies exact service authority and ARCH-04E1A supplies source-only
facts/types. PILOT-04 registers selected production request/completion routing;
ARCH-04E3-B activates supported false-policy guides. The bounded local public
durable-runtime drill starts from public guide inputs with recorded inference.
The public submission-bundle preparation flow reserves an exact pre-submit
attempt before invoking checks. Completed retries recover the original evidence
without rerunning checks or issuing a new upload capability. An uncertain attempt
cannot execute again under the same key. POL-07B connects the internal
checker phase service and removes the standalone JSON precheck. Both fresh
pre-submit execution and completed replay use that service, with ART retaining
canonical evidence ownership. The obsolete checker worker, manual execution and
submission-finalize repair routes are removed. `evaluate_post_submission` now
uses hidden durable execution with exact ARCH-04D2 service authority. ARCH-04E1A
retains route-neutral source evidence. REV-04C uses its bounded exact-source
verifier and shared FinalAcceptance/TASK/CON participant. The authorized TASK
outcome owner publishes exact routing sources under CHECKERS current-run custody.
B7 implements hidden
request delivery with invocation fencing. B8 adds hidden completion routing with commit-before-ACK. Production
request/completion registration is supplied by the selected PILOT-04 composition;
ARCH-02I-B exposes the existing admission-backed writer through the public
Submission POST for initial work and checker remediation.
Submission and checker history use live exact-project Submitter authority for the
original contributor. Separate `/projects/{project_id}` reads require a covering
Project Manager grant and expose fixed management fields. Token roles confer no
authority and authentication returns only the verified identity contract.
Finance Authority can publicly discover, create, update, publish,
read and retire a project's ContributionPolicy under
`/api/v1/projects/{project_id}/contribution-policies`. The current-policy read
recovers a draft selector, a published selector, or both for another authorized
Finance actor.
Each mutation requires one UUID `Idempotency-Key`. AUTH owns the authorization
decision for the authenticated actor; the CON caller transaction atomically commits
policy effects, AUTH evidence and immutable replay custody. Both contribution
types must explicitly declare compensated or unpaid rules. Unpaid publication
needs no compensation binding; compensated rules retain verified binding checks.
Project Managers do not acquire Finance powers. Public compensation-binding
administration remains pending.

CON provides internal exact selected-policy validation: a
new guide binding must match the active policy’s current published version;
the revision-adoption purpose validates an explicitly supplied historical version
without reselection. Both validate complete rules and current unit/binding
eligibility in the caller transaction. CP07 supplies the canonical activation operation:
exact separate pre/post approvals, review/revision selections and the published
ContributionPolicyVersion become one immutable guide binding. It atomically
supersedes the explicitly selected prior guide and activates a draft Project.
Replay preserves the original binding after supersession or policy retirement;
active-guide reads require that custody. Activation no longer uses the superseded economic readiness guard.
AUTH-12H supplies explicit live authority for an active Project Manager scoped to
that exact project. Shared prepared authorization locks current identity and grant
before product resources, binds the complete activation digest and rechecks live
authority on replay. Composition without an authority adapter still denies.
AUTH-18 exposes `POST /api/v1/projects/{project_id}/guides/{guide_id}/activate`.
The draft post-policy review package supplies `activation_context`: exact guide,
review/revision, predecessor, separately approved post-policy and published CON
selectors. Missing selectors remain explicit; the context does not promise readiness.
Managers obtain those selectors without Finance privileges, then submit the exact
selection with one UUID `Idempotency-Key`. Save the body and key for receipt replay;
the draft context is not an active-guide replay endpoint. Response validation,
authority evidence and activation effects commit together. ARCH-03D connects the
intake handoff to the exact activated guide. ARCH-02I-B exposes public initial
and checker-remediation intake; controlled human-review revision remains separate.

ARCH-03A completes the existing internal PROJECTS context port. New work selects
one active activated guide; existing work resolves its exact frozen guide and
policy selectors, including after a successor or contribution-policy retirement.
The result includes the saved activation receipt, both checker-policy bodies,
artifact/effective policy, review/revision semantics and exact approved external
image bindings. Retained earlier contexts preserve their immutable identities. It never substitutes current policies or reruns inference. CP08 uses
that port in the existing TASK writers: screening stamps the activated contribution
policy, claim copies it to the assignment, and hidden Submission creation copies
the assignment's exact stamp. PostgreSQL rejects mismatched or replaced stamps.
New work requires no superseded economic configuration. ARCH-03B1 removes
TaskService's private PROJECTS reads: the existing port now returns detached
project descriptions and exact historical guide display facts. Draft task creation
requires project existence, not an activated guide. ARCH-03B2 adds hidden,
project-scoped ready queue facts with bounded live pagination; it exposes no
queue endpoint or authority. ARCH-03B3 adds hidden all-state management queues
with planning fields and operational queues with IDs/status/timestamps only.
ARCH-03B4 adds hidden contributor and management task detail with fixed
fields and project/assignment visibility, now exposed through ARCH-03C5 exact
Contributor and Manager authority. ARCH-03B5 replaces the existing contributor/manager work-context
responses with distinct fixed task facts and exact historical policy identities,
without obsolete payment fields or submission flags. ARCH-03B6 supplies distinct
locked-context projections through the same historical resolver: management
includes the bounded checker summary; operational and audit reads expose only
exact policy references. ARCH-03C6 exposes all three through distinct
exact-authorized routes and removes the old task-only management route. ARCH-03B7 supplies immutable contributor and
management requirements through one historical translator. Its hidden contributor
read reuses exact assignment visibility after locking TASK; the retained requirements
route and separate Manager route use ARCH-03C5 live exact authority. ARCH-03B8 supplies bounded task evidence, publicly authorized by ARCH-03C7;
ARCH-03B9 supplies hidden exact-assignment invalidation with committed cause
verification and a same-transaction delivery fence. ARCH-03C1 supplies real
fixed-service authority and exact decision receipts; ARCH-03C2 supplies atomic
AUTH event publication and production handler registration. ARCH-03C3 replaces
the create/screen/release role-only path with exact Project Manager authority,
atomic audit evidence and durable replay. ARCH-03C4 exposes separate contributor-ready,
manager-planning and Operator-status queues with current scoped grants and signed
pagination. ARCH-03C5 exposes separate Contributor/Manager detail and requirements,
removing their old role/creator wrappers. PILOT-14 adds the task-locked
ContributionPolicyVersion compensation block to ready summaries and Contributor
detail for active exact-project Submitters or Reviewers. It exposes only unpaid
or instrument/unit/exact-quantity terms, never Finance binding or route facts;
claim authority remains Submitter-only. ARCH-03C6 exposes separate manager, system-Operator and Audit Authority
locked-context reads with exact current grants. ARCH-03C7 exposes bounded task
history only to covered Audit Authority and removes the old payload-bearing
task-only audit route. AUTH-18 delivers public manager guide activation;
ARCH-03D connects hidden intake through final durable intent to canonical TASK/PROJECTS
ports, preserving historical guide selection. ARCH-02I-B exposes public ZIP
preparation and canonical admission-backed Submission creation. ARCH-04B supplies
hidden exact verified Submission
input with scoped async file access and cleanup. ARCH-04B2 adds hidden typed
checker-output storage, byte-free recovery and flush-only verified binding over
the generic ART put/verification path. ARCH-04C supplies hidden durable execution,
exact request/execution-lease custody, immutable member results and atomic completion events.
Selected image execution retains normalized bounded JSON results. Checker file
output write/bind authority remains unavailable; neither executable catalogue
remains in the live flow. ARCH-04D1 validates retained terminal material against canonical
ART lineage. ARCH-04D2 supplies fixed-service input, execute and finalize authority,
with PostgreSQL enforcement of exact execution/finalization receipts. ARCH-04E1A
adds immutable source storage and detached contracts. PILOT-04 composes selected
hidden dispatch and production routing; ARCH-02I-B exposes public intake and
ARCH-04E3-B admits complete false-policy guides with supported approved
requirements. The hidden
[ARCH-04E2-B operation](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E2B.md)
consumes canonical fixed-router authorization and commits the actual receipt
with its exact source and complete consequence. Locked true moves TASK to
`review_pending` without a REV queue or CON dependency. Locked false invokes
the shared acceptance participant and atomically stages FinalAcceptance,
accepted TASK/completed assignment, submitter ContributionRecord, applicable
awards and shared audit/outbox evidence. It creates no Review or reviewer
contribution. Database closure rejects partial effects; exact replay verifies
the original tuple with fresh authority instead of repairing it.

B6 supplies atomic Submission/dispatch, B7 hidden request delivery and B8 hidden
completion handling with commit-before-ACK. 04F2 supplies the hidden remediation
handoff without Review, acceptance, contribution or award effects. 04F3 supplies
hidden exact-cause replacement intake through the canonical Submission writer;
it neither creates failure economics nor activates human revision. 04F4 adds
hidden Operator retry for known terminal infrastructure failures with immutable
source evidence. PILOT-04 registers selected production request/completion handlers.
ARCH-02I-B exposes public admission-backed entry; ARCH-04E3-B activates
supported false-policy guides, with new acceptance effects still gated on a
LIVE REV generation bound to the current reviewed manifest. A known pre-effect
refusal retries only within
the existing OUTBOX budget; exhausted delivery dead-letters without automatic
reopen. The connected public-guide API and Celery drill passed with recorded inference. A future setup-fault hold must
retain the Submission and locked rules without contributor penalty; changing
submitted-work rules remains deferred.
Real manager activation now supplies the false-policy lineage when the approved
requirements are supported; a `human_review` disposition still blocks that mode.
Conditional awards stay atomic; payment delivery and fulfillment-root machinery
remain deferred until fulfillment is enabled.


## v0.1 Success Standard

Workstream v0.1 succeeds only when the complete lifecycle defined in
[End-To-End Lifecycle](#end-to-end-lifecycle) runs as a real internal task cycle with real people. The cycle must
prevent invalid work from reaching review, preserve exact evidence and
authority, support revision without rewriting history, produce trusted
contribution facts, and carry payable contributions through conditional award
and fulfillment. Runtime reputation projection is not part of this release
bar.

## Operating Standard

Workstream is built as durable operational infrastructure. Project rules live
in versioned guides and policies rather than chat memory. Each active attempt
keeps its locked governing context. The task's locked project RevisionPolicy
requires an explicit nonnegative revision cap: N=2 permits submissions 0, 1 and
2; N=0 permits only the initial Submission. A final-attempt failure immediately
records rejection, closes its assignment and returns the task to ready, without
another preparation or deadline. Timeout also returns the task to ready. Anyone
eligible may claim a new assignment at round 0, including a previous claimant;
there is no contributor-count limit or repeated-failure hold.

When a revision remains, contributor-fixable failure freezes the complete
next-attempt context and change summary. Revision reruns intake and acknowledges
that exact preparation. A setup-blocked rebase publishes durable PM attention
and pauses the PostgreSQL-time allowance; repair resumes only its remaining
time. Repair of a running context preserves its deadline. Only committed
immutable resubmission ends a running opportunity. Task state, terminal evidence,
authorization, audit and outbox intent commit atomically. Original Submissions
and findings remain immutable; scans and retries recover after downtime.
Infrastructure/provider/budget failures never spend a contributor attempt.
Checker remediation creates no Review or reviewer contribution. Live human
Review decision composition remains #554 work under the same intended policy.
Timeout and exhaustion create no contribution, award or fulfillment facts.

Lifecycle state is a ledger, not a loose label. Submitted artifacts remain
immutable and hash-bound to their checks; findings, responses, resolutions,
Reviews, and contribution facts remain attributable and auditable. Lessons
become governed guide, policy, template, or checker changes before they affect
future work. Project activation, task screening, submission quality, review,
contribution recognition, and conditional fulfillment remain distinct gates
even though they form one end-to-end v0.1 lifecycle.
