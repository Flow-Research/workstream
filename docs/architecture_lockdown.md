# Architecture Lockdown

Last updated: 2026-08-11

## Purpose

This note locks the Workstream v0.1 architecture around a source-agnostic,
governed contribution core: project guide discipline, task contracts, human
accountability for agent-assisted work, immutable artifact custody,
policy-governed checks, authorized review, contribution records, conditional
compensation awards and fulfillment, and future reputation consequences.

Pre-submission intake checks and post-submission work evaluation are distinct
lifecycle boundaries, not one generic deterministic-check stage. Intake blocks
Submission creation when required checks fail; post-submit results govern
review eligibility. Deterministic compilation and routing do not guarantee
deterministic judgments from a model-based evaluator. The
[checker framework](architecture_checker_framework.md) retains the supported
implementation boundary; this distinction activates no new runtime evaluator.

Workstream's durable product output is trusted contribution lineage. External
sources may request work and downstream systems may apply payment, points,
reputation, reporting, dataset, or other consequences, but neither side creates
or revises Workstream identity, authority, submission, Review, or
`ContributionRecord` truth. Flow Identity remains the current v0.1 external
authentication adapter, not the product boundary.

The backend is a modular monolith governed by the canonical module map and
public-API dependency rules in
[`engineering/repository_architecture_boundaries.md`](engineering/repository_architecture_boundaries.md).
Cross-module runtime imports use only the target module's typed `api` package.
Concrete implementations are wired only by the application composition root or
the exact same-owner adapter root `backend/app/adapters/<owner>/__init__.py`.
That narrow adapter-root rule permits construction of the owner's public ports;
it does not permit nested adapter files or any adapter to import another
module's private implementation.

The TASKS public boundary exposes immutable task, assignment, immediate
Submission predecessor, and locked project-context reference selectors through
`app.modules.tasks.api`. It exposes no TASK ORM row, repository, session,
mutable policy body, or PROJECT/CHECKER/ACTOR persistence. Those locked
references are inputs to their owning public capabilities; they do not transfer
policy or identity ownership into TASKS.

The PROJECTS public boundary resolves exact task-locked guide, source-snapshot,
effective-policy, and pre-submit-policy lineage through
`app.modules.projects.api`. Historical rows remain valid after canonical
`superseded` transitions when every exact selector and recomputed hash still
matches; current successors are never substituted. Policy bodies cross this
boundary only as canonical immutable JSON, never as ORM rows, sessions,
repositories, mutable mappings, or a public mutable projection helper.

The ADR files under `docs/decision_*.md` are the decision record for this lockdown. When a locked rule changes, update or add an ADR before changing implementation specs.

Repository changes use the Repository-Native Human-Agent SDLC documented in
`README.md` and `CONTRIBUTING.md`: intent, a proportionate plan, a bounded
change, evidence, review, a pull request, and an explicit human merge decision.
GitHub permissions and branch protection govern repository authority. That
repository process is separate from every product lifecycle below.

The canonical v0.1 scope remains narrower. The sequence below describes the
human-review branch. Project configuration uses one existing
ReviewPolicy boolean, `human_review_required`, default true. False permits
authorized automated FinalAcceptance and submitter contribution after required
post-submit checks pass, without human admission, a synthetic Review or a
reviewer contribution. Its source/authority/CON design is defined in the
[shared acceptance contract](spec_review_lifecycle.md#finalacceptance);
REV-04C supplies its hidden FinalAcceptance/TASK/CON transaction participant,
and ARCH-04E2-B binds actual routing authority, immutable evidence and complete
atomic outcomes under currentness custody. Completion delivery, remediation and
production composition remain before false-guide activation and public intake.
This amendment does not enable raw checker results to create acceptance or
change the existing human branch's implementation contract.
The ReviewPolicy field `requires_second_review` is fixed to `false` in v0.1.
Typed policy contracts and PostgreSQL enforce that invariant; no second-review
or adjudication lifecycle is implied.

```text
Project guide
-> submission artifact policy
-> task screening
-> task queue
-> pre-submit checker policy
-> submission packet
-> pre-submission intake checks
-> immutable Submission
-> post-submission work evaluation
-> pre-review gate
-> human review
-> revision replay
-> review decision: accept / needs_revision / reject
-> FinalAcceptance for accept only
-> contribution record
-> compensation award / fulfillment when payable
-> reputation integration (future, separate initiative)
```

## Locked For v0.1

### Record Identity

Workstream-generated surrogate record keys use the shared UUIDv7 generator and
native PostgreSQL `uuid` storage, with version/variant constraints on generated
keys. Relationships use the same native type. Existing typed owner boundaries
may expose Python UUID values or canonical UUID strings; this does not change
their PostgreSQL storage.

Meaningful natural/composite keys, Flow subjects, request/idempotency tokens and
content hashes are not surrogate record IDs. Retrying an operation recovers its
original stored ID through exact owner-local uniqueness and fresh authorization;
it does not derive a row ID from a token. IDs are not secrets, authority, expiry
clocks, or commit-order evidence. Use explicit lifecycle timestamps and existing
pagination tie-breakers for those purposes. UUIDv7 reveals approximate generation
time; possession of an ID never substitutes for authorization.

### Source-Agnostic, Manual First

Workstream is source-agnostic, but v0.1 does not include external source adapters.

Allowed v0.1 intake:

- manual task creation
- controlled markdown import
- controlled CSV import

Every imported or manually created task still normalizes into the same Workstream task contract.

### Three Gates

Workstream uses three separate quality gates:

1. Project activation gate
2. Task screening gate
3. Submission quality gate

### Authorization Boundary

Workstream verifies external Flow tokens and owns product authorization through
local ActorProfile/ActorIdentityLink records, administrative grants,
exact-project submitter/reviewer grants, registered permissions,
resource and lifecycle guards, revocation, and append-only authority evidence.

The global role catalogue does not define the v0.1 review lifecycle. Shipping
uses submitter and reviewer authority only; no adjudication policy, action,
queue, lease, state, decision, contribution, or readiness dependency exists.

Token roles and typed workflow profiles are not product authority. All public
routes remain under `/api/v1`. ADR 0012 and the canonical authorization service
specification control authorization wording in this lockdown.

External origin qualification and task ingestion map to project activation and task screening in v0.1. External origins remain deferred.

### Project Guide Structure

Every project guide is human-facing. It must explain:

- purpose
- task types
- task instructions
- acceptance criteria
- rejection criteria
- reviewer rubric
- required skills
- difficulty scale
- estimated time policy
- common rejection reasons

Every active guide version must also have approved machine-readable policies:

- immutable guide-source snapshot
- guide sufficiency report
- submission artifact policy
- effective project submission artifact policy hash
- project pre-submit checker bundle hash
- post-submit checker policy
- review policy
- revision policy

The guide may summarize or link to those policies, but the policies are the enforcement source.

Project owners provide open-ended project material and business terms.
Workstream evaluates guide sufficiency, derives
`SubmissionArtifactPolicy` from that material, and an authorized covered
Project Manager approves the internal policy bundle
before guide activation. Project owners do not approve Workstream's internal
submission policy schema.

`SubmissionArtifactPolicy` defines project-level intake rules. Workstream combines it with the non-bypassable Workstream default submission artifact policy to create `EffectiveProjectSubmissionArtifactPolicy`. Workstream then generates, persists, and locks project `PreSubmitCheckerPolicy` with a compiled bundle hash from that effective project submission artifact policy. Tasks lock the applicable guide snapshot, effective project submission artifact policy hash, and pre-submit checker bundle hash before entering the contributor pipeline.

Blocking pre-submit failures prevent submission creation. The current hidden
preparation route returns only `pre_submission_checker_failed`; bounded
structured public feedback remains pending the canonical public intake cutover. Failures create no submission
row, no submission version, no task transition to `submitted`, and no
submission-created audit event. ART constructs a bounded audit-ready projection;
publication as a task event named `pre_submission_check_failed` remains pending.
That event must contain only this closed, path-redacted projection: actor-profile ID, project ID, task ID, preparation
attempt ID, effective-plan hash, terminal status, pass/warning/failure counts,
and a bounded ordered list of catalogue ID/version plus stable outcome code.
It excludes filenames, archive paths, scratch/provider references, credentials,
raw checker output, evidence content, and free-form or unbounded messages. This
is audit evidence, not a product review decision. POL-07B removes the independently invocable
JSON precheck. The internal pre-submit phase command uses ART's existing
execution or completed-evidence recovery after reservation commits. WS-ARCH-001-02I retains the
broader Submission caller migration and its downstream prerequisites.

Hidden ART-04B2 uses XINT-06A's two-stage fixed-materializer PREP. It locks the
service/action and scalar lineage before ZIP inspection, then consumes the same
process-local handle with the server-computed semantic-manifest identity before
workspace reservation or checker execution. It reserves the complete expanded
workspace budget, verifies one canonical sealed tree against the 04A identities,
and runs only platform/default catalogue entries. The callback-scoped tree and
all paths are destroyed before bounded results return. Hidden ART-04B3 extends
that same plan and sealed-tree callback
to the locked project-policy entries, then reloads the exact task context and
persists one immutable platform-plus-project evidence set after scratch cleanup.
It creates no provider object, admission, Submission, or lifecycle effect;
AUTH activation remains XINT-06A. POL-07A commits an ART execution reservation
before invoking checks, then obtains fresh materialization authority; a prepared
AUTH handle never crosses that commit. Completed replay freshly authorizes the
stored original generation and returns evidence without another checker run or
pass capability.

Tasks lock to the active guide version at creation or screening time before entering `READY`. Material guide changes require a new guide version.

For guide and context resolution, TaskAssignment contributes only its `task_id`;
it still retains required contributor, assignment, status, and frozen submitter
contribution-policy attribution. Each immutable Submission stamps the exact
Project Guide identity, version, and activation sequence used by that attempt.
After a human `needs_revision` Review, preparation compares the complete prior
stamped context with all applicable current guide and policy selectors. Exact
component matches keep; every changed valid component rebases together;
incomplete, inconsistent, revoked, or unsafe context blocks for manager repair.
Task Context returns the frozen preparation. No rebase occurs during review;
the reviewer uses the context stamped on the leased Submission.

### Task Contract

Every task must carry enough information to make claiming, checking, and
reviewing auditable:

- project id
- locked guide version
- title
- description
- task type
- required output
- acceptance criteria
- required artifacts and evidence references derived from the locked project pre-submit checker policy
- difficulty
- skill tags
- estimated time when known
- deadline or SLA when applicable
- source type and source reference when imported

Compensation remains an independently owned CON policy, but its selected version
is part of the complete governing work context. Guide activation binds one
`ContributionPolicyVersion`; task readiness locks it before claimability, and
TaskAssignment copies it, Submission stamps the attempt value, and ReviewLease
copies that stamp without claim-time selection.
Publication never silently changes existing work. A human `needs_revision`
may atomically rebase the continuing Task and TaskAssignment for the next
submission attempt while the completed lease and prior history remain
immutable. Either rule may be
explicitly unpaid and therefore create no award.

### Human Accountability

Workstream allows agent-assisted work, but the contributor or owner is accountable for the submitted packet.

In v0.1, this is enforced through:

- assignment ownership
- contributor attestation
- immutable submission versions
- checker results bound to artifact hashes
- human review before acceptance when the locked policy requires it; the
  planned false branch requires separately authorized acceptance evidence
- immutable Review, finding, response, and resolution history on the human branch

An explicit owner-agent execution workspace is later work.

### Immutable Artifact Storage

Workstream stores guide material, submission artifacts, checker inputs, checker
logs, checker outputs, and review evidence through ART v2 typed capabilities.
Product services do not import the raw ArtifactStore, provider, repository, or
scratch interfaces.

```text
LocalStorageAdapter          development and focused tests only
S3CompatibleArtifactStore    AWS S3 in v0.1 production
MinIO                        local and CI S3-compatible integration proof
```

Here, `local and CI` is the non-production eligibility boundary. The
repository-managed MinIO service is published on host loopback; a private
operator-controlled container-network endpoint is also valid in local,
development, or test environments. MinIO is never hosted-production evidence.

AWS S3 is the only v0.1 production provider. Cloudflare R2 and Flow Node are
deferred adapter initiatives. No provider owns product identity, authorization,
lifecycle, bindings, audit, or integrity truth. PostgreSQL owns those facts;
object storage owns private immutable bytes.

Provider acknowledgement, ETag, and provider checksum metadata are not enough
to bind content. Workstream independently reads, hashes, and counts the complete
object before it becomes bindable. Production clients receive no provider
credentials, object references, signed URLs, or direct-upload authority.

v0.1 performs no physical deletion of completed artifacts. R2 and Flow Node are
separate deferred adapter initiatives and are not v0.1 runtime dependencies.

An active ReviewLease authorizes artifact bytes only for its immutable
ReviewPacketManifest and exact Submission. Authorized chain history is bounded
metadata only. Decision and contribution creation perform no ART call.

### Pre-Submission Checker Boundary

CHECKERS owns the single deterministic effective pre-submission plan. The 02C
boundary exposes its public planning port and bounded result facts and migrates
the touched TASK and ART admission call path away from the catalogue, compiler,
and executor internals. ART retains exclusive ownership of byte custody,
storage scheme, evidence persistence, pass capability, and admission attachment.

Public CHECKER results contain the plan identity, eligibility outcome, and
bounded per-definition facts only. They never expose prepared-artifact custody,
scratch state, provider details, or durable evidence identity. Concrete
catalogue and executor implementations remain CHECKER-private and meet callers
only through application composition. Existing ART materialization and evidence
imports that have not yet migrated remain frozen private-edge debt; the next
ART boundary chunk must move those exact consumers to this public surface.

### Contribution Records

On the human branch, every valid recorded human Review creates an immutable reviewer
`completed_review` contribution record, regardless of whether the decision is
`accept`, `needs_revision`, or `reject`. REV creates one immutable
FinalAcceptance only for `accept`; that fact, not direct inspection of
`Review.decision`, sources one submitter `accepted_submission` contribution
record. `needs_revision`, `reject`, and automated checker outcomes create no
FinalAcceptance or submitter contribution by themselves. On the planned false
branch, an authorized automated decision creates FinalAcceptance and the
submitter contribution through the shared atomic participant, never a reviewer
contribution. The [shared acceptance contract](spec_review_lifecycle.md#finalacceptance)
defines both triggers and their source/authority constraints. Runtime proof is
required before activation; it is not a checker-owned write or fabricated Review.

Contribution records are separate from compensation status. Each record freezes
its exact review, submission, actor, policy, and artifact-hash lineage.
Compensation awards may attach to a contribution record but do not replace it.
Reputation projection is deferred.

FinalAcceptance is internal and REV-owned. It has no independent API/action,
uses canonical `Submission.id` because each Submission row is already a
version, and is unique per task, Submission and each non-null exclusive source
(accepting Review or authorized TASK routing manifest). V0.1 contains
no adjudication policy, action, queue, lease, state, decision, contribution
type, branch, readiness check, or adjudication-initiative dependency.

## Deferred

These ideas remain architecture-compatible, but they are not part of the first build:

- external origin onboarding
- webhook drop notifications to external origins
- automated source adapters
- automated task routing
- owner-agent account pairs as first-class runtime objects
- agent identity registry writes
- ERC-8183 settlement
- ERC-8004 reputation writes
- x402 micropayments
- marketplace discovery
- adjudication lifecycle, queues, leases, decisions, and actions

## Canonical Names

Use these names consistently:

- `check_acceptance_criteria_present`
- `ContributionRecord`
- `ContributionPolicyVersion`
- `CompensationAward`
- `CompensationFulfillmentReceipt`
- `CompensationStatusProjection`
- `SubmissionArtifactPolicy`
- `EffectiveProjectSubmissionArtifactPolicy`
- `PreSubmitCheckerPolicy`
- `PostSubmitCheckerPolicy`
- `pre_submission_checker_failed`
- `Project activation gate`
- `Task screening gate`
- `Submission quality gate`
- `ReviewQueueEntry`
- `ReviewLease`
- `ReviewPacketManifest`
- `ReviewFinding`: `blocking | advisory`
- `SubmissionFindingResponse`
- `FindingResolution`: `resolved | unresolved | not_applicable`
- `RevisionContextPreparation`
- `FinalAcceptance`
