# Queue Policy

## Status

Review and revision lanes below are the planned v0.1 operating contract. Their
routes and jobs remain unavailable until the owning REV chunks, exact AUTH
activation, and REV-13 joint release complete.

## Purpose

The queue is the operational truth of Workstream. It tells the team what
exists, what is blocked, what needs human action, and what creates contribution
or compensation-award exposure.

Queue lanes must be derived from task status, not manually maintained in separate lists.

## Lanes

### Draft

Tasks being prepared.

Owner:

- project manager
- task creator

Exit requirement:

- project guide attached
- acceptance criteria present
- required output defined

### Screening

Tasks that look ready but need independent release review before contributors can claim them.

Owner:

- project manager
- reviewer lead
- quality lead

Exit requirement:

- project guide version locked
- immutable guide source snapshot id/hash locked
- acceptance criteria are concrete
- effective project submission artifact policy hash locked
- project `PreSubmitCheckerPolicy` compiled bundle hash locked
- approved generated project `PostSubmitCheckerPolicy` is locked with matching
  guide, source snapshot, effective project policy, and pre-submit checker
  provenance
- review policy is attached
- revision policy is attached
- no open critical- or high-severity readiness finding

Policy:

- screening is where weak task guides and low-quality task specs fail
- contributors do not see tasks that have not passed screening

### Ready

Tasks that can be claimed or assigned.

Owner:

- project manager

Exit requirement:

- assigned or claimed by contributor

### Active

Tasks in `CLAIMED` or `IN_PROGRESS`.

Owner:

- contributor
- operator

Operational risk:

- stale active tasks block throughput

Policy:

- each active task must have a deadline or next check-in
- stale tasks get an owner action before deadline breach

### Submitted

Tasks with a new submission packet.

Owner:

- checker system

Exit requirement:

- checker run created

### Auto Checking

Checker run is active.

Owner:

- checker system
- Operator when infrastructure recovery is required

Policy:

- checker failure because of platform/tooling stays in checker retry handling;
  Operator retry uses `operations.checker.retry`, while covered Project Manager
  repair uses `project.task.manage`, and neither moves work directly to review
- retry and repair actions record matched grant/permission, reason, attempt, and
  immutable audit history

### Checker Admission Gate

Mandatory automated admission after post-submit checks and before human review.

Owner:

- checker system

Policy:

- only a durable, final, current `CheckerRun` outcome of `allow_review` admits
  the exact immutable Submission
- admission records the exact CheckerRun and verified binding facts; retries,
  superseded runs, and different Submissions cannot replace that anchor
- contributor-fixable checker failures may route the Task to `needs_revision`
  but create no Review, ReviewFinding, or reviewer contribution
- setup or provenance defects remain blocked until the owning covered repair or
  retry action succeeds
- human judgment begins only after admission and is recorded as an immutable
  Review

### Review Pending

Submission passed blocking checks and is ready for human review.

Owner:

- reviewer

Policy:

- reviewer current work returns an active lease, one server-selected offer, or
  none; reviewers never browse the complete lane
- any critical- or high-severity checker failure in this lane is a system bug;
  no administrative grant can override it into review readiness

### Needs Revision

Contributor-facing lane for fixable issues from automated checks, pre-review gates, or human review.

Policy:

- after a human `needs_revision` Review, Workstream compares the prior
  Submission guide identity/activation sequence with the currently active guide
- exact match keeps; any different valid pair rebases forward or backward;
  unsafe context blocks for manager repair
- Task Context returns the frozen preparation and change summary; the reviewer
  never rebases the leased Submission
- out-of-band guidance is not enforceable until it is encoded into guide, policy, task template, or checker contracts

Owner:

- contributor
- covered Project Manager for planned repair/obligation closure; Operator only
  for evidence-linked legacy recovery

Policy:

- checker-caused remediation carries CheckerResult lineage; human-review
  revision carries an immutable Review and at least one blocking finding
- human-review resubmission includes one immutable response per unresolved
  blocking finding

### Accepted

Work satisfies the project guide and acceptance criteria.

Owner:

- project operations
- finance/reconciliation only for payable contribution awards

Policy:

- the accepting Review creates reviewer `completed_review`, REV-owned
  FinalAcceptance, and FinalAcceptance-sourced submitter `accepted_submission`
  contribution records atomically
- each frozen contribution policy is evaluated independently; only payable
  contributions create awards and fulfillment follow-up
- accepted task is not confused with fulfilled compensation

### Rejected

Work is not acceptable and will not continue in the normal revision loop.

Owner:

- project manager for terminal-state observation
- authorized audit authority for non-mutating quality sampling only

Policy:

- rejection requires a bounded human, guide-grounded reason; structured
  findings and finalized evidence are optional when they add useful support
- the Task enters canonical `rejected`; only its same-task TaskAssignment is
  blocked and bound to the reject Review
- no FinalAcceptance or submitter contribution is created; no actor grant or
  unrelated task changes
- quality sampling cannot reopen, adjudicate, replace, or change the immutable
  Review, rejection, task state, assignment effect, or contribution lineage

### Compensation Fulfillment Follow-Up

Compensation follow-up is not a task queue lane. It is derived from payable
`CompensationAward` records and their fulfillment projections, whether the
source contribution is `completed_review` or `accepted_submission`.

Track:

- payable contribution missing its award or fulfillment projection
- pending award delivery
- acknowledged by adapter
- failed fulfillment
- fulfilled with immutable receipt

## Daily Queue Review

Every operating day starts with:

1. count tasks by lane
2. clear screening tasks or send them back to draft
3. inspect stale active tasks
4. clear checker failures
5. monitor server-selected review offers and active leases
6. push needs revision tasks to contributors
7. reconcile payable awards with pending/failed fulfillment projections
8. record new lessons learned

## Transition Guards

| Transition | Required Records |
| --- | --- |
| `DRAFT -> SCREENING` | project id, locked guide candidate, task source/description fields, acceptance and rejection criteria |
| `SCREENING -> READY` | screening decision, guide version lock, guide source snapshot id/hash lock, acceptance criteria, effective project submission artifact policy hash lock, project `PreSubmitCheckerPolicy` compiled bundle hash lock, approved generated project `PostSubmitCheckerPolicy` with matching provenance, review policy, revision policy |
| `READY -> CLAIMED` | active published ContributionPolicyVersion whose `accepted_submission` rule is explicit; TaskAssignment freezes that version |
| `IN_PROGRESS -> SUBMITTED` | blocking pre-submit checks passed, submission packet, artifact hash manifest, evidence references, contributor attestation |
| `SUBMITTED -> EVALUATION_PENDING` | immutable submission version, locked post-submit checker policy id/version/hash/body copied from the task context |
| `EVALUATION_PENDING -> REVIEW_PENDING` | durable, final, current CheckerRun for the exact Submission with outcome exactly `allow_review`, verified artifact bindings, no blocking failures |
| `EVALUATION_PENDING -> NEEDS_REVISION` | durable, final, current CheckerRun for the exact Submission with outcome exactly `needs_revision`, verified artifact bindings, outcome source `auto_checker`, contributor-visible checker failures with severity, message, suggested fix |
| `REVIEW_PENDING -> NEEDS_REVISION` | immutable Review, at least one blocking ReviewFinding, reviewer `completed_review`; no FinalAcceptance or submitter contribution |
| `REVIEW_PENDING -> ACCEPTED` | immutable accepting Review, FinalAcceptance, reviewer `completed_review`, submitter `accepted_submission` sourced from FinalAcceptance, applicable awards |
| `REVIEW_PENDING -> REJECTED` | immutable rejected Review, bounded reason, same-task assignment block, reviewer `completed_review`; no FinalAcceptance or submitter contribution |
| `NEEDS_REVISION -> SUBMITTED` | exact preparation head/digest, replacement Submission, response for every unresolved blocking finding, policy limit/deadline not reached |
| `NEEDS_REVISION -> CANCELLED` | covered manager limit/deadline closure or Operator legacy-context closure, bounded canonical reason, assignment release; no synthetic Review or contribution |
| compensation `pending -> fulfilled` | immutable fulfillment receipt, external reference, and audit event |

## Lane Capacity

Each project defines capacity limits:

- maximum active tasks per contributor
- maximum active ReviewLeases per reviewer
- maximum stale active age
- maximum pending/failed payable-award fulfillment age

Capacity limits prevent the queue from looking healthy while hidden work is stuck.

For early pilots, use conservative defaults:

- contributor active task limit: 2
- reviewer active ReviewLease limit: 1
- review SLA: 24 hours
- compensation fulfillment reconciliation SLA: daily

## Queue Health Metrics

- tasks ready
- tasks screening
- tasks active
- submitted awaiting checks
- review pending age
- needs revision age
- unfulfilled compensation award amount
- rejected count
- fulfilled compensation total

## Failure Modes

### Review Pending Pileup

Cause:

- not enough reviewers
- reviewers lack context
- checker output too noisy

Fix:

- assign reviewer owner
- improve review packet
- split projects by reviewer skill

### Needs Revision Looping

Cause:

- vague feedback
- contributor not closing findings
- task spec unclear

Fix:

- require revision replay
- audit reviewer wording
- update project guide

### Payable Contribution Fulfillment Drift

Cause:

- contribution award creation and fulfillment are disconnected

Fix:

- frozen contribution policy evaluation creates awards only for payable
  contributions; explicit unpaid rules create none
- compensation fulfillment dashboard is reviewed daily

### Ready Lane Contains Weak Tasks

Cause:

- no ready gate
- task creator skipped project guide
- acceptance criteria are vague

Fix:

- run ready gate before `READY`
- add task creator checklist
- require reviewer simulation for first-of-kind tasks
