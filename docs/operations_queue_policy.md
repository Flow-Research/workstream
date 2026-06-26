# Queue Policy

## Purpose

The queue is the operational truth of Workstream. It tells the team what exists, what is blocked, what needs human action, and what creates payment exposure.

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
- payment policy present
- required output defined

### Screening

Tasks that look ready but need independent release review before workers can claim them.

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
- post-submit checker policy is attached
- review policy is attached
- revision policy is attached
- payment policy is attached
- no open high-severity readiness finding

Policy:

- screening is where weak task guides and low-quality task specs fail
- workers do not see tasks that have not passed screening

### Ready

Tasks that can be claimed or assigned.

Owner:

- project manager

Exit requirement:

- assigned or claimed by worker

### Active

Tasks in `CLAIMED` or `IN_PROGRESS`.

Owner:

- worker
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
- admin if checker fails unexpectedly

Policy:

- checker failure because of platform/tooling stays in checker retry handling or audited admin/project manager intervention and does not move to human review
- retry and admin actions are recorded in audit history

### Pre Review Gate

Optional reviewer-simulation or adversarial readiness audit after automated checks and before normal human review.

Owner:

- reviewer lead
- quality lead
- assigned simulation reviewer

Policy:

- use this for high-value tasks, new project types, disputed checker outcomes, or projects still being calibrated
- the gate records findings or explicitly clears the packet for normal review
- unresolved blocking issues go to `NEEDS_REVISION` when worker-fixable or remain blocked from review until an admin/policy action is recorded

### Review Pending

Submission passed blocking checks and is ready for human review.

Owner:

- reviewer

Policy:

- reviewers only see this lane for normal work
- any high-severity checker failure in this lane is a system bug or admin override

### Needs Revision

Worker-facing lane for fixable issues from automated checks, pre-review gates, or human review.

Policy:

- before the worker resumes, Workstream prepares revision context against the active guide and policy records
- revision policy decides whether the next attempt keeps the prior locked context or rebases to the current active context
- a rebase must show the worker the prior version, next version, and change summary
- out-of-band guidance is not enforceable until it is encoded into guide, policy, task template, or checker contracts

Owner:

- worker
- operator

Policy:

- every task in this lane must have at least one structured finding
- resubmission must include revision replay

### Accepted

Work satisfies the project guide and acceptance criteria.

Owner:

- finance/reconciliation

Policy:

- accepted task must create or update payment record immediately
- accepted task is not confused with paid task

### Rejected

Work is not acceptable and will not continue in the normal revision loop.

Owner:

- project manager
- reviewer lead if disputed

Policy:

- rejection requires evidence and guide-grounded reason

### Payment Follow-Up

Payment follow-up is not a task queue lane. It is derived from payment records attached to accepted tasks.

Track:

- accepted but no payment record
- pending payout
- payout submitted
- paid
- disputed

## Daily Queue Review

Every operating day starts with:

1. count tasks by lane
2. clear screening tasks or send them back to draft
3. inspect stale active tasks
4. clear checker failures
5. assign review pending tasks
6. push needs revision tasks to workers
7. reconcile accepted but unpaid tasks
8. record new lessons learned

## Transition Guards

| Transition | Required Records |
| --- | --- |
| `DRAFT -> SCREENING` | project id, locked guide candidate, required task fields, payment policy |
| `SCREENING -> READY` | screening decision, guide version lock, guide source snapshot id/hash lock, acceptance criteria, effective project submission artifact policy hash lock, project `PreSubmitCheckerPolicy` compiled bundle hash lock, post-submit checker policy, review policy, revision policy, payment policy |
| `IN_PROGRESS -> SUBMITTED` | blocking pre-submit checks passed, submission packet, artifact hash manifest, evidence references, worker attestation |
| `SUBMITTED -> AUTO_CHECKING` | immutable submission version, post-submit checker policy version derived from the locked task context |
| `AUTO_CHECKING -> REVIEW_PENDING` | checker run for exact submission version, readiness certificate, no blocking failures |
| `AUTO_CHECKING -> NEEDS_REVISION` | checker run id, outcome source `auto_checker`, worker-visible checker failures with severity, message, suggested fix |
| `REVIEW_PENDING -> NEEDS_REVISION` | review decision, at least one structured finding, revision policy still permits revision |
| `REVIEW_PENDING -> ACCEPTED` | accepted review, acceptance evidence refs, contribution record, payment record |
| `NEEDS_REVISION -> IN_PROGRESS` | prior findings visible to worker, revision deadline active |
| resubmission after `NEEDS_REVISION` | revision replay covering every high and medium prior finding, revision count under policy limit |
| payment `PENDING -> PAID` | payment reference and payment audit event |

## Lane Capacity

Each project defines capacity limits:

- maximum active tasks per worker
- maximum review-pending tasks per reviewer
- maximum stale active age
- maximum accepted-unpaid age

Capacity limits prevent the queue from looking healthy while hidden work is stuck.

For early pilots, use conservative defaults:

- worker active task limit: 2
- reviewer review-pending limit: 5
- review SLA: 24 hours
- payment reconciliation SLA: daily

## Queue Health Metrics

- tasks ready
- tasks screening
- tasks active
- submitted awaiting checks
- review pending age
- needs revision age
- accepted unpaid amount
- rejected count
- paid total

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
- worker not closing findings
- task spec unclear

Fix:

- require revision replay
- audit reviewer wording
- update project guide

### Accepted But Unpaid Drift

Cause:

- acceptance and finance are disconnected

Fix:

- accepted transition creates payment record
- payment dashboard is reviewed daily

### Ready Lane Contains Weak Tasks

Cause:

- no ready gate
- task creator skipped project guide
- acceptance criteria are vague

Fix:

- run ready gate before `READY`
- add task creator checklist
- require reviewer simulation for first-of-kind tasks
