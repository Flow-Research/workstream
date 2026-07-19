# Architecture Lockdown

Last updated: 2026-07-14

## Purpose

This note locks the Workstream v0.1 architecture around source-agnostic intake,
project guide discipline, task contracts, human accountability for agent-assisted
work, contribution records, conditional compensation awards and fulfillment,
and reputation consequences.

The ADR files under `docs/decision_*.md` are the decision record for this lockdown. When a locked rule changes, update or add an ADR before changing implementation specs.

The canonical v0.1 scope remains narrower:

```text
Project guide
-> submission artifact policy
-> task screening
-> task queue
-> pre-submit checker policy
-> submission packet
-> automated checks
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
exact-project submitter/reviewer/adjudicator grants, registered permissions,
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

Blocking pre-submit failures prevent submission creation. Preflight failures
return `PreSubmitCheckResponse(status="failed", eligible_to_submit=false,
results=[...])`. Blocked submission-create attempts return
`pre_submission_checker_failed` with structured pass/fail/warning details and
create no submission row, no submission version, no task transition to
`submitted`, and no submission-created audit event. Workstream still writes a
task audit event named `pre_submission_check_failed` with the structured checker
result for project operators; this is audit evidence, not a product review
decision.

Tasks lock to the active guide version at creation or screening time before entering `READY`. Material guide changes require a new guide version.

For guide and context resolution, TaskAssignment contributes only its `task_id`;
it still retains required contributor, assignment, status, and frozen submitter
contribution-policy attribution. Each immutable Submission stamps the exact
Project Guide identity, version, and activation sequence used by that attempt.
After a human `needs_revision` Review, exact stamped identity and
activation-sequence match with the currently active guide keeps context. Any
different valid active pair prepares a forward or backward rebase; incomplete,
inconsistent, revoked, or unsafe context blocks for manager repair. Task Context
returns the frozen preparation. No guide rebase occurs during review; the
reviewer uses the context stamped on the leased Submission.

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

Compensation is not task-guide context. TaskAssignment freezes the active
published submitter `ContributionPolicyVersion`; ReviewLease independently
freezes the reviewer version. Either rule may be explicitly unpaid and therefore
create no award.

### Human Accountability

Workstream allows agent-assisted work, but the contributor or owner is accountable for the submitted packet.

In v0.1, this is enforced through:

- assignment ownership
- contributor attestation
- immutable submission versions
- checker results bound to artifact hashes
- human review before acceptance
- immutable Review, finding, response, and resolution history

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

### Contribution Records

Every valid recorded human Review creates an immutable reviewer
`completed_review` contribution record, regardless of whether the decision is
`accept`, `needs_revision`, or `reject`. REV creates one immutable
FinalAcceptance only for `accept`; that fact, not direct inspection of
`Review.decision`, sources one submitter `accepted_submission` contribution
record. `needs_revision`, `reject`, and automated checker outcomes create no
FinalAcceptance or submitter contribution.

Contribution records are separate from compensation status. Each record freezes
its exact review, submission, actor, policy, and artifact-hash lineage.
Compensation awards may attach to a contribution record but do not replace it.
Reputation projection is deferred.

FinalAcceptance is internal and REV-owned. It has no independent API/action,
uses canonical `Submission.id` because each Submission row is already a
version, and is unique per task, source Review, and Submission. V0.1 contains
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
