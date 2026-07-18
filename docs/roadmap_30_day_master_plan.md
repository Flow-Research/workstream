# 30-Day Master Plan

## Review Lifecycle Status

The schedule is planning guidance, not a claim that review/revision routes are
live. Those surfaces remain unavailable until their approved WS-REV chunks,
exact AUTH activation, and REV-13 joint release complete.

## Goal

Build the first serious version of Workstream: Flow's configurable task
evaluation and contribution infrastructure that can run real internal projects
from guide to contribution record, review decision, and compensation status.

The output of the 30 days is not a demo-only UI. It is usable infrastructure
with durable contribution records, project templates, automated checks, human
review, revision replay, and compensation award/fulfillment records. Reputation
is a separately approved later consumer.

## Scope

In scope:

- project guide management
- task queue and task records
- submission packets
- checker framework
- human review workflow
- revision loop
- evidence storage
- contribution records
- compensation award and fulfillment ledger
- dashboards for current status
- pilot with real tasks

Out of scope for the first 30 days:

- on-chain settlement
- autonomous agent execution runtime
- full public marketplace
- advanced source adapters
- complex dispute court
- external client billing automation

Future settlement rails such as ERC-8004, ERC-8183, x402, and OmniClaw remain architecture-compatible but are not first-version dependencies.

## Operating Rule

Every feature must support the core lifecycle:

```text
DRAFT -> SCREENING -> READY -> CLAIMED -> IN_PROGRESS -> SUBMITTED -> EVALUATION_PENDING -> REVIEW_PENDING -> needs_revision | accepted work | rejected work
```

`pre_review_gate` is the checker/audit phase that runs while the persisted task status is `evaluation_pending`.

Payment status is separate:

```text
NONE -> PENDING -> PAYOUT_SUBMITTED -> PAID
```

If a feature does not improve lifecycle correctness, review quality, evidence,
or compensation tracking, defer it. Reputation is already deferred.

## Week 1: Foundation

Objective: define the product contract and implement the backend foundation for the core records.

Deliverables:

- project schema
- project guide schema
- queue policy schema
- task schema
- status state machine
- worker profile
- reviewer profile
- roles and permissions matrix
- submission record
- evidence record
- contribution and compensation policy context
- backend API smoke paths for project, task, assignment, and submission records
- workspace/packet convention for the first project
- modular monolith structure with clean router, service, repository, interface, and adapter boundaries
- external Flow authentication verification boundary

Day 1:

- finalize product principles
- finalize lifecycle states
- finalize first database schema
- create first internal project template
- define default queue lanes and packet convention
- lock the per-chunk specification and conditions-of-satisfaction protocol

Day 2:

- build project and guide records
- create project guide editor or markdown-backed guide import
- define checker, review, revision, and payment policy fields, including base amount, currency, and payment rule fields
- use backend records/API first; frontend editor is deferred until the backend contract is stable

Day 3:

- build task creation
- build queue states
- build task detail API response
- enforce task belongs to project

Day 4:

- build worker and reviewer profiles
- add assignment and claim logic

Day 5:

- build submission packet upload/record flow
- add evidence attachment model
- run first dry task through DRAFT to SUBMITTED manually

Week 1 acceptance bar:

- a project can be created with a versioned guide plus checker, review, revision, and payment policy context
- a task can be created, screened, claimed, submitted, and tracked
- every task status transition is recorded
- no task exists outside a project
- the backend runs as a modular monolith with clear boundaries
- Flow authentication is represented as token verification, not Workstream-owned login
- frontend implementation is not required for Week 1 acceptance

## Day-7 Thin Slice

By the end of day 7, one narrow workflow must work end to end:

```text
Project -> Guide -> Task -> Screening -> Ready -> Claim -> Submit -> Checker Result -> Review Decision
```

Minimum scope:

- one project
- one guide
- one task
- one worker
- one reviewer
- one checker
- one review decision

This thin slice is the first proof that Workstream can measure and certify useful work, not just store records. If this does not work, pause feature expansion and fix the lifecycle.

## Week 2: Checker Framework

Objective: prevent worker-fixable submission failures and locked task setup defects from reaching human review.

Week 2 is backend/checker-framework work. Checker results must be available through backend APIs, backend contract drills, and operational debug output. Product frontend pages, reviewer queue UI, and review decision screens stay in Week 3 or later.

Deliverables:

- pre-submit static checker path
- post-submit internal auto-check path
- checker runner
- checker result schema
- project checker policy
- high/medium/low severity
- blocking versus warning checks
- evidence log per checker run
- review gate enforcement
- API-readable checker output for the exact submission version and artifact hash manifest

Required first checkers:

- `check_acceptance_criteria_present`
- `check_policy_context_present`
- `check_submission_packet`
- `check_evidence_present`
- `check_evidence_integrity`
- `check_required_files`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- `check_low_quality_generated_artifacts`

Task lifecycle transitions and revision closure are enforced as lifecycle guards until they have registered checker contracts.

Day 6:

- define checker interface
- define checker result record
- build checker runner
- expose checker run and result reads through backend contracts

Day 7:

- implement schema and required-file checks
- attach check runs to submission records

Day 8:

- implement evidence and rubric/acceptance checks
- block `REVIEW_PENDING` when critical- or high-severity checks fail

Day 9:

- implement project-specific checker policy
- allow each project guide to declare required checkers

Day 10:

- run the expanded internal sample matrix through the checker framework
- document false positives and missing checks

Week 2 acceptance bar:

- every submitted task runs checks
- checker output is stored permanently
- blocking checker policy failures block human review and can route to user-facing `needs_revision` without creating a human review decision
- backend contracts expose the exact checker results before Week 3 reviewer UI work begins

## Week 3: Review And Revision Engine

Objective: make human review auditable, consistent, and useful.

Deliverables:

- reviewer current work with an active lease, one server-selected offer, or none
- review packet
- finding model
- blocking/advisory lifecycle model
- accept / needs_revision / reject decisions
- revision replay
- revision context preparation and guide/policy rebase audit
- offline reviewer quality metrics without product adjudication state

Day 11:

- build review queue
- expose checker results on review page
- create review decision form

Day 12:

- build finding model:
  - lifecycle meaning: blocking or advisory
  - area
  - issue
  - required fix
  - immutable evidence relation to a finalized ART binding

Day 13:

- implement `needs_revision` flow
- store feedback history
- force resubmission to reference prior feedback

Day 14:

- implement revision replay:
  - prior issue
  - fix summary
  - evidence
  - immutable later resolution: `resolved | unresolved | not_applicable`

Day 15:

- create reviewer quality metrics
- run internal reviewer simulation on 5 tasks

Week 3 acceptance bar:

- accept requires acceptance evidence; `needs_revision` requires an unresolved
  blocking finding; reject requires a bounded human reason and findings remain
  optional
- every `needs_revision` has concrete fix requirements
- every resubmission must answer each unresolved blocking finding and preserve
  later immutable resolution
- accept, needs_revision, and reject decisions are auditable

## Week 4: Compensation, Pilot

Objective: run real tasks and harden the operating loop.

Deliverables:

- compensation award and fulfillment ledger
- project dashboard
- worker dashboard
- reviewer dashboard
- pilot report
- day-30 lessons learned

Day 16:

- implement payment records:
  - base amount
  - accepted amount
  - pending payout
  - paid amount
  - payment status

Day 17:

- prove compensation outbox delivery, retry, callback, and immutable receipt
  behavior; keep reputation out of the v0.1 transaction

Day 18:

- build dashboards:
  - tasks by status
  - accepted count
  - needs revision count
  - pending payout
  - paid total

Day 19:

- create first real pilot project guide
- create 10 pilot tasks

Day 20:

- run pilot tasks through assignment and submission
- collect checker and review failures

Day 21:

- process needs-revision tasks
- test revision replay

Day 22:

- accept/reject pilot tasks
- create contribution records
- record compensation outcomes when payable

Day 23:

- run a reviewer audit on accepted and rejected tasks
- identify weak checker coverage

Day 24:

- patch checker gaps
- patch reviewer workflow gaps

Day 25:

- run a second pilot batch of 10 tasks

Day 26:

- create operations manual
- create reviewer checklist
- create task creator checklist

Day 27:

- measure throughput:
  - time to submit
  - time to review
  - revision count
  - acceptance rate
  - payment pending

Day 28:

- harden state transitions
- harden audit logs
- fix dashboard inconsistencies

Day 29:

- write day-30 pilot report
- define next 60-day expansion plan

Day 30:

- final review
- freeze v0.1 operating standard
- start onboarding next operators

Week 4 acceptance bar:

- at least 10 real tasks entered
- at least 5 complete submission cycles
- at least 2 revision cycles
- contribution records and conditional compensation records generated
- one pilot report completed

## Success Metrics

Product:

- 100% of tasks belong to a project guide
- 100% of submissions have checker results
- 100% of accepted tasks have evidence
- 100% of revision requests have concrete findings

Operations:

- at least 10 pilot tasks
- at least 5 completed cycles
- median review turnaround under 24 hours for pilot
- no payable accepted contribution without its CompensationAward
- no accepted task without contribution record

Quality:

- weak submissions blocked before review
- reviewer findings are actionable
- revision replay closes prior feedback
- accepted work can be audited later
- accepted work has FinalAcceptance-sourced contribution records before any
  compensation fulfillment

## Main Risks

Risk: overbuilding the marketplace before the workflow works.

Mitigation: keep the first 30 days internal.

Risk: project rules living in chat instead of system policy.

Mitigation: every project guide must define checker, review, revision, and payment policy.

Risk: reviewers giving vague feedback.

Mitigation: require structured findings and concrete required fixes.

Risk: payment tracking becoming manual chaos.

Mitigation: payment ledger exists from week 4 even before automated payment.
