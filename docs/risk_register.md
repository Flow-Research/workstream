# Risk Register

## Purpose

This file tracks operational risks that can damage Workstream if ignored.

## Risks

### R1: Rules Live In Chat

Severity: high

Problem:

Project rules scattered across chat, memory, screenshots, or informal notes will create repeated mistakes.

Mitigation:

- every rule belongs in project guide, submission artifact policy, checker policy, review policy, revision policy, or payment policy
- daily lessons learned become document updates
- out-of-band guidance has no acceptance force until it becomes a guide, policy, template, or checker contract update
- revision context preparation shows workers any guide or policy changes before resubmission

### R1A: Revision Uses Stale Or Hidden Rules

Severity: high

Problem:

A task can be sent back for revision after the project guide or policies changed. If the worker is not shown the new context, the revision loop becomes unfair and reviewers may apply standards that were not visible when the worker resumed.

Mitigation:

- prior submissions remain tied to their locked guide and policy versions
- revision policy controls whether the next attempt rebases to current active guide and policy context
- worker and reviewer packets show prior version, next version, rebase reason, and change summary
- every rebase records an audit event

### R2: Weak Submissions Reach Review

Severity: high

Problem:

Reviewers waste time on missing files, broken packets, unclear evidence, and incomplete acceptance criteria.

Mitigation:

- blocking checker failures prevent `REVIEW_PENDING`
- checker output visible to worker and reviewer

### R3: Vague Reviewer Feedback

Severity: high

Problem:

Workers cannot close feedback that does not specify the issue, evidence, and required fix.

Mitigation:

- structured findings required
- reviewer quality metrics
- second-review audits

### R4: Revision Loops Without Closure

Severity: high

Problem:

Tasks repeatedly return for the same issue because prior feedback is not replayed.

Mitigation:

- mandatory revision replay
- checker verifies prior finding coverage
- reviewer marks closure per finding

### R5: Accepted Work Not Paid

Severity: high

Problem:

Acceptance and payment can drift apart if tracked manually.

Mitigation:

- acceptance creates pending payment record
- daily accepted-unpaid reconciliation
- paid state requires payment reference

### R6: Reviewer Abuse Or Low-Quality Review

Severity: medium

Problem:

Bad review decisions can demoralize workers and corrupt quality metrics.

Mitigation:

- reviewer reputation
- second-review sampling
- overturned decision tracking
- escalation process

### R7: Fake Evidence

Severity: high

Problem:

Workers may attach evidence that does not prove the work.

Mitigation:

- require artifact hashes for uploaded artifacts and storage-backed evidence
- require checker logs or reproducible artifacts
- require stable evidence IDs
- bind evidence IDs to submitted artifact hashes
- require reviewer citations to exact evidence IDs on acceptance
- reviewer must cite evidence in accept decision
- bind checker runs to immutable submission versions
- reject evidence that cannot be tied to the submitted artifact

### R8: Confidential Or Copied Data

Severity: high

Problem:

Using private client data or copied platform data can create legal and trust risk.

Mitigation:

- no-confidential-source-data checker
- forbidden file rules
- worker attestation
- guide rules for allowed materials

### R10: Status Bypass

Severity: high

Problem:

Tasks can be moved to review, accepted, or paid without completing the required checker, review, revision, or payment steps.

Mitigation:

- enforce state transitions in code
- require checker run id before `REVIEW_PENDING`
- require review id before `ACCEPTED`
- require accepted task and payment reference before `PAID`
- make admin overrides visible and non-destructive

### R11: Reviewer Collusion Or Rubber-Stamping

Severity: high

Problem:

Reviewers can repeatedly approve weak work for favored workers or skip evidence review.

Mitigation:

- sample accepted work for second review
- flag repeated worker-reviewer pairs
- require evidence citation on accept
- track overturned accept decisions
- require independent review for high-value or disputed tasks

### R12: Bad Project Guides

Severity: high

Problem:

A weak project guide creates vague tasks, inconsistent reviews, payment disputes, and checker blind spots.

Mitigation:

- guides require approval before activation
- every task locks a guide version
- repeated review issues become guide updates
- guide changes include effective date and change summary

### R13: Low-Quality Generated Submissions

Severity: medium

Problem:

Workers may submit generic LLM-generated artifacts that look structured but do not solve the task.

Mitigation:

- project guides define banned low-quality patterns
- checkers flag repeated boilerplate, placeholders, and fabricated helper artifacts
- reviewers judge task-specific evidence, not formatting polish
- repeated pattern matches affect worker reputation

### R14: Payment Disputes

Severity: high

Problem:

Accepted work, payout amount, and paid status can diverge, especially while payment is manual.

Mitigation:

- acceptance creates payment record automatically
- amount changes require adjustment record
- disputed payments move to `DISPUTED`
- daily reconciliation catches accepted-unpaid and paid-without-reference records

### R9: Overbuilding Marketplace Before Operating System

Severity: high

Problem:

Public marketplace features can distract from the quality engine.

Mitigation:

- v0.1 is internal
- no public bidding
- no blockchain dependency
- no source adapters until core lifecycle works
