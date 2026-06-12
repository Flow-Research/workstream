# 30-Day Master Plan

## Goal

Build the first serious version of Workstream: Flow's configurable task evaluation and contribution infrastructure that can run real internal projects from guide to contribution record, review decision, payment status, and reputation signal.

The output of the 30 days is not a demo-only UI. It is usable infrastructure with durable contribution records, project templates, automated checks, human review, revision replay, and payment/reputation ledgers.

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
- payment ledger
- reputation ledger
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
DRAFT -> SCREENING -> READY -> CLAIMED -> IN_PROGRESS -> SUBMITTED -> AUTO_CHECKING -> REVIEW_PENDING -> NEEDS_REVISION | ACCEPTED | REJECTED
```

`pre_review_gate` is the checker/audit phase that runs while the persisted task status is `AUTO_CHECKING`.

Payment status is separate:

```text
NONE -> PENDING -> PAYOUT_SUBMITTED -> PAID
```

If a feature does not improve lifecycle correctness, review quality, evidence, payment tracking, or reputation, defer it.

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
- payment policy context
- reputation dimensions
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
- define reputation dimensions
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

Week 2 is backend/checker-framework work. Checker results must be available through backend APIs, dry-run scripts, and demo/debug output. Product frontend pages, reviewer queue UI, and review decision screens stay in Week 3 or later.

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

- `check_task_schema`
- `check_required_files`
- `check_submission_packet`
- `check_evidence_present`
- `check_acceptance_criteria_present`
- `check_status_transition`
- `check_prior_revision_closed`
- `check_policy_context_present`
- `check_forbidden_files`

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
- block `REVIEW_PENDING` when high-severity checks fail

Day 9:

- implement project-specific checker policy
- allow each project guide to declare required checkers

Day 10:

- run five internal sample submissions through the checker framework
- document false positives and missing checks

Week 2 acceptance bar:

- every submitted task runs checks
- checker output is stored permanently
- high-severity failures block human review and can route to user-facing `NEEDS_REVISION` without creating a human review decision
- backend contracts expose the exact checker results before Week 3 reviewer UI work begins

## Week 3: Review And Revision Engine

Objective: make human review auditable, consistent, and useful.

Deliverables:

- review queue
- review packet
- finding model
- severity model
- accept / needs_revision / reject decisions
- revision replay
- revision context preparation and guide/policy rebase audit
- reviewer metrics
- second-review flag

Day 11:

- build review queue
- expose checker results on review page
- create review decision form

Day 12:

- build finding model:
  - severity
  - area
  - issue
  - required fix
  - evidence reference

Day 13:

- implement NEEDS_REVISION flow
- store feedback history
- force resubmission to reference prior feedback

Day 14:

- implement revision replay:
  - prior issue
  - fix summary
  - evidence
  - closed / still open

Day 15:

- create reviewer quality metrics
- run internal reviewer simulation on 5 tasks

Week 3 acceptance bar:

- reviewers cannot issue vague decisions without findings
- every NEEDS_REVISION has concrete fix requirements
- every resubmission must close prior feedback
- accept, needs_revision, and reject decisions are auditable

## Week 4: Payment, Reputation, Pilot

Objective: run real tasks and harden the operating loop.

Deliverables:

- payment ledger
- reputation ledger
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

- implement reputation updates:
  - acceptance rate
  - revision rate
  - rejection rate
  - review quality
  - skill tags

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
- record payment outcomes
- update reputation

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
- payment and reputation records generated
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
- no accepted task without payment record
- no accepted task without contribution record

Quality:

- weak submissions blocked before review
- reviewer findings are actionable
- revision replay closes prior feedback
- accepted work can be audited later
- accepted work has contribution records before payment and reputation updates

## Main Risks

Risk: overbuilding the marketplace before the workflow works.

Mitigation: keep the first 30 days internal.

Risk: project rules living in chat instead of system policy.

Mitigation: every project guide must define checker, review, revision, and payment policy.

Risk: reviewers giving vague feedback.

Mitigation: require structured findings and concrete required fixes.

Risk: payment tracking becoming manual chaos.

Mitigation: payment ledger exists from week 4 even before automated payment.
