# Day-by-Day Execution Plan

## Purpose

This is the execution calendar for the first 30 days. The master plan explains the strategy; this file defines what happens each day and what must be true before moving on.

The plan assumes a small team:

- 1 product/ops lead
- 1 backend engineer
- 1 frontend engineer
- 1 reviewer/quality lead
- 1 finance/reconciliation owner

If the team is smaller, keep the sequence and reduce scope, not the quality gates.

## Week 1: Backend Foundation

Week 1 is backend-first. The frontend starts after the backend contract, lifecycle guards, and first workflow are stable.

The backend is a modular monolith. Routers stay thin, services own workflow rules, repositories own database queries, interfaces define external boundaries, and adapters implement those boundaries.

Each implementation chunk must have a specification and conditions of satisfaction before code starts. Senior engineering, QA/test, and security/auth verification are required before operator final review.

### Day 1: Freeze Product Contract

Deliver:

- product brief accepted
- lifecycle state machine accepted
- entity list accepted
- first three project templates named
- initial operating principles frozen
- Week 1 backend chunk plan accepted
- modular monolith boundaries accepted
- external Flow auth verification boundary accepted

Exit criteria:

- no task can exist without a project
- no project can exist without a guide
- no accepted task can exist without payment and evidence concepts
- no backend implementation starts without chunk specification and conditions of satisfaction

### Day 2: Project And Guide Records

Deliver:

- `WorkstreamProject`
- `ProjectGuide`
- guide versioning
- guide approval and active-version locking
- checker policy fields
- review policy fields
- revision policy fields
- payment policy fields
- base amount fields
- evidence policy fields
- payment dispute policy fields
- active/inactive project status
- SQLAlchemy 2.x async model shape
- Pydantic request/response schemas

Exit criteria:

- create a project from a markdown guide
- retrieve the active guide version for a task
- edit a draft guide without changing historical task guide versions
- block activation of a guide missing checker, review, revision, payment, or evidence policy
- migrations and model tests define the expected invariants

### Day 3: Task Queue

Deliver:

- `WorkstreamTask`
- queue lanes
- task create/edit
- screening/readiness gate
- task status transition table
- audit event for each status change
- task-owned locked guide and policy context

Exit criteria:

- create task in `DRAFT`
- move task to `SCREENING` only when required fields exist
- move task to `READY` only after screening passes
- view queues by status
- every transition writes an actor-attributed audit event

### Day 4: People And Assignment

Deliver:

- `WorkerProfile`
- `ReviewerProfile`
- `AdminRole`
- assignment/claim flow
- skill tags
- external Flow actor identity mapped into Workstream actor context

Exit criteria:

- assign task to worker
- move `READY -> CLAIMED -> IN_PROGRESS`
- prevent two workers owning the same task unless project policy allows it
- Workstream verifies Flow-issued tokens and does not own passwords or login

### Day 5: Submission Packet

Deliver:

- `Submission`
- `SubmissionArtifact`
- evidence upload/reference
- package hash field
- artifact hash manifest
- worker attestation
- submission versioning
- server-stamped locked guide and policy context from the task

Exit criteria:

- submit v1 packet
- worker does not provide guide, checker policy, review policy, revision policy, or payment policy versions
- task moves to `SUBMITTED`
- package/evidence records are immutable after checker run starts
- replacing any artifact creates v2 instead of mutating v1

## Week 2: Checker System

Week 2 is backend-first checker infrastructure. Checker output is exposed through APIs, dry-run scripts, and demo/debug output. It does not build the product frontend, reviewer queue UI, review decision form, contribution records, payment records, or reputation updates.

The core invariant is:

`Draft packet -> Pre-submit checks -> Submit -> Lock -> Internal CheckerRun -> CheckerResults -> review_pending | needs_revision | internal task_setup_blocked -> trusted checker retry when repaired`

The checker framework does not accept or reject work. It may route worker-fixable checker failures to user-facing `needs_revision`, but that does not create a human review decision. Internally the source is recorded as `auto_checker`.

### Day 6: Checker Interface

Deliver:

- checker result contract
- checker runner
- checker severity model
- `CheckerRun`
- `CheckerResult`

Exit criteria:

- run a checker against a submission
- store `passed`, `warning`, and `failed` results
- expose checker run and result data through backend API responses and dry-run/demo output
- no product frontend task page is added in Week 2
- checker records can distinguish pre-submit feedback from post-submit internal auto checks

### Day 7: Core Structural Checkers

Deliver:

- `check_policy_context_present`
- `check_submission_packet`
- `check_required_files`
- `check_forbidden_files`

Exit criteria:

- worker-fixable submission failures fail before review
- locked checker policy blocking failures block `review_pending`
- checker runs bind to the exact submission id, submission version, package hash, and artifact hash manifest
- worker-fixable checker failures route to user-facing `needs_revision`

### Day 8: Evidence And Acceptance Checkers

Deliver:

- `check_evidence_present`
- `check_evidence_integrity`
- `check_acceptance_criteria_present`
- `check_policy_context_present`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- first version of `check_low_quality_generated_artifacts`

Exit criteria:

- task cannot become review-pending with no evidence
- task cannot become review-pending when checker artifact hashes do not match submission hashes
- task cannot be accepted later without payment policy

### Day 9: Project Checker Policy

Deliver:

- `CheckerPolicy`
- project-required checker list
- blocking severity settings
- trusted checker retry with reason after internal setup repair

Exit criteria:

- two projects can require different checkers
- trusted checker retry creates audit record
- project-required checker policy is read from the locked task context, not from mutable worker input

### Day 10: Checker Trial

Deliver:

- expanded sample matrix
- [checker failure catalog](checker_trial_failure_catalog.md)
- false-positive notes
- missing-checker list

Exit criteria:

- at least one worker-fixable submission failure is blocked
- at least one clean submission reaches `REVIEW_PENDING`
- trial output documents project-manager/admin checker API visibility and worker redaction

## Week 3: Review And Revision

### Day 11: Review Queue

Deliver:

- reviewer queue
- review page
- checker result panel
- task guide panel
- submission evidence panel

Exit criteria:

- reviewer sees all context without asking operator in chat

### Day 12: Structured Findings

Deliver:

- `Review`
- `ReviewFinding`
- severity
- area
- issue
- required fix
- evidence reference

Exit criteria:

- `needs_revision` and `reject` require at least one finding
- `accept` requires checklist confirmation
- `accept` requires evidence references, not only a free-text approval

### Day 13: Needs Revision Flow

Deliver:

- `review_pending -> needs_revision`
- feedback history
- task unlock for worker
- resubmission requirements

Exit criteria:

- worker can see every prior finding
- worker cannot resubmit without revision replay

### Day 14: Revision Replay

Deliver:

- `RevisionReplay`
- `RevisionFix`
- closure status
- prior finding mapping

Exit criteria:

- every prior high/medium finding is mapped to a fix or explicit dispute
- reviewer can mark closed/still open

### Day 15: Review Quality Metrics

Deliver:

- reviewer turnaround
- decision distribution
- unclear feedback flag
- overturned decision marker
- second-review marker

Exit criteria:

- reviewer quality can be discussed from data, not memory

## Week 4: Ledger, Dashboard, Pilot

### Day 16: Payment Ledger

Deliver:

- `ContributionRecord`
- `PaymentRecord`
- accepted amount
- pending amount
- paid amount
- payment status
- payment reference
- payment dispute status
- payment adjustment record

Exit criteria:

- accepted work creates a contribution record
- accepted work creates pending payment record
- paid payment status requires payment reference

### Day 17: Reputation Ledger

Deliver:

- `ReputationEvent`
- worker quality events
- reviewer quality events
- skill-tag scoring

Exit criteria:

- accepted, needs revision, rejected, and review-quality events are recorded

### Day 18: Dashboards

Deliver:

- project dashboard
- queue dashboard
- payment dashboard
- reviewer dashboard

Exit criteria:

- dashboard totals reconcile with task and payment records

### Day 19: Pilot Setup

Deliver:

- 3 project guides
- 10 pilot tasks
- 2 reviewers assigned
- payment owner assigned

Exit criteria:

- pilot tasks are real enough to expose workflow problems

### Day 20: Pilot Batch 1

Deliver:

- 5 tasks assigned
- 3 submissions
- checker results

Exit criteria:

- at least one task reaches review
- at least one checker failure is handled correctly

### Day 21: Revision Drill

Deliver:

- at least 2 needs-revision decisions
- revision replay records
- resubmissions

Exit criteria:

- every prior finding is mapped to a fix

### Day 22: Acceptance And Rejection Drill

Deliver:

- accepted decisions
- rejected decision if warranted
- contribution records
- payment records
- reputation events

Exit criteria:

- accepted work has evidence, contribution record, and pending payment

### Day 23: Reviewer Audit

Deliver:

- second-review audit on accepted/rejected tasks
- reviewer findings quality report

Exit criteria:

- vague review feedback is identified and corrected

### Day 24: Patch Workflow Gaps

Deliver:

- update guides
- update checkers
- update templates
- update reviewer workflow

Exit criteria:

- every pilot failure either becomes a guide change, checker change, or policy decision

### Day 25: Pilot Batch 2

Deliver:

- 10 additional tasks
- improved checker/review process

Exit criteria:

- fewer repeated errors than batch 1

### Day 26: Operating Manual

Deliver:

- operator manual
- reviewer manual
- task creator checklist
- payment reconciliation checklist

Exit criteria:

- a new operator can follow docs without private explanation

### Day 27: Metrics Review

Deliver:

- throughput metrics
- review metrics
- payment metrics
- quality metrics

Exit criteria:

- team knows the real bottleneck

### Day 28: Hardening

Deliver:

- transition guards
- audit log cleanup
- dashboard reconciliation fixes
- data export

Exit criteria:

- no silent state changes
- no accepted task missing payment/evidence

### Day 29: Pilot Report

Deliver:

- day-30 pilot report draft
- v0.2 priorities
- unresolved risk list

Exit criteria:

- decisions are based on pilot evidence

### Day 30: Freeze v0.1

Deliver:

- v0.1 operating standard
- final planning package
- next 60-day roadmap outline
- onboarding plan for next operators

Exit criteria:

- Workstream can run a small real project from guide to payment record
