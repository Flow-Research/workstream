# Architecture Lockdown

Last updated: 2026-06-06

## Purpose

This note locks the Workstream v0.1 architecture around source-agnostic intake, project guide discipline, task contracts, human accountability for agent-assisted work, contribution records, payment records, and reputation consequences.

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
-> contribution record
-> payment record
-> reputation event
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

- submission artifact policy
- generated pre-submit checker policy
- post-submit checker policy
- review policy
- revision policy
- payment policy

The guide may summarize or link to those policies, but the policies are the enforcement source.

`SubmissionArtifactPolicy` defines what a worker must submit. Workstream combines it with the non-bypassable Workstream default submission artifact policy to create the effective submission artifact policy. Workstream generates `PreSubmitCheckerPolicy` from that effective policy.

Blocking pre-submit failures prevent submission creation. They return worker-safe fixes and create no submission row, no submission version, no task transition to `submitted`, and no submission-created audit event.

Tasks lock to the active guide version at creation or screening time before entering `READY`. Material guide changes require a new guide version.

### Task Contract

Every task must carry enough information to make claiming, checking, reviewing, and payment auditable:

- project id
- locked guide version
- title
- description
- task type
- required output
- acceptance criteria
- required artifacts and evidence references derived from the effective submission artifact policy
- difficulty
- skill tags
- estimated time when known
- base amount
- currency
- payout type
- deadline or SLA when applicable
- source type and source reference when imported

### Human Accountability

Workstream allows agent-assisted work, but the human worker or owner is accountable for the submitted packet.

In v0.1, this is enforced through:

- assignment ownership
- worker attestation
- immutable submission versions
- checker results bound to artifact hashes
- human review before acceptance
- reputation events tied to outcomes

An explicit owner-agent execution workspace is later work.

### Contribution Records

Accepted work must create a durable contribution record separate from payment status.

The contribution record is the evidence-backed certification that a worker completed accepted work under a locked project guide. Payment records and reputation events attach to this contribution record, but do not replace it.

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

## Canonical Names

Use these names consistently:

- `check_acceptance_criteria_present`
- `ContributionRecord`
- `SubmissionArtifactPolicy`
- `EffectiveSubmissionArtifactPolicy`
- `PreSubmitCheckerPolicy`
- `PostSubmitCheckerPolicy`
- `Project activation gate`
- `Task screening gate`
- `Submission quality gate`
- `worker_claim_status`
- `reviewer_closure_status`

Revision replay worker claim statuses:

- `fixed`
- `disputed`
- `not_applicable`

Revision replay reviewer closure statuses:

- `closed_fixed`
- `closed_rebutted`
- `partially_closed`
- `still_open`
- `obsolete`
