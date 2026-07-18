# Risk Register

## Purpose

This file tracks operational risks that can damage Workstream if ignored.

## Risks

### R1: Rules Live In Chat

Severity: high

Problem:

Project rules scattered across chat, memory, screenshots, or informal notes will create repeated mistakes.

Mitigation:

- every rule belongs in project guide, submission artifact policy, checker
  policy, review policy, revision policy, contribution policy, or task template
- daily lessons learned become document updates
- out-of-band guidance has no acceptance force until it becomes a guide, policy, template, or checker contract update
- revision context preparation shows contributors any guide or policy changes before resubmission

### R1A: Revision Uses Stale Or Hidden Rules

Severity: high

Problem:

A task can be sent back for revision after the project guide or policies changed. If the contributor is not shown the new context, the revision loop becomes unfair and reviewers may apply standards that were not visible when the contributor resumed.

Mitigation:

- prior Submissions remain tied to their stamped guide and policy context
- exact stamped guide identity/activation-sequence match keeps context; any
  different valid active pair rebases forward or backward; unsafe context blocks
- Task Context returns the frozen preparation; reviewer context uses the exact
  leased Submission stamp without a separate rebase
- every rebase records an audit event

### R2: Weak Submissions Reach Review

Severity: high

Problem:

Reviewers waste time on missing files, broken packets, unclear evidence, and incomplete acceptance criteria.

Mitigation:

- blocking checker failures prevent `REVIEW_PENDING`
- checker output visible to contributor and reviewer

### R3: Vague Reviewer Feedback

Severity: high

Problem:

Contributors cannot close feedback that does not specify the issue, evidence, and required fix.

Mitigation:

- structured blocking/advisory findings
- immutable SubmissionFindingResponse and later FindingResolution
- offline reviewer calibration without mutating product history
- reviewer quality metrics
- post-decision non-mutating reviewer-quality audits

### R4: Revision Loops Without Closure

Severity: high

Problem:

Tasks repeatedly return for the same issue because prior feedback is not replayed.

Mitigation:

- one immutable response per unresolved blocking finding
- checker readmission binds the exact replacement Submission and preparation
- later reviewer appends a resolution per required finding

### R5: Accepted Work Not Paid

Severity: high

Problem:

Payable awards and external fulfillment can drift apart if tracked manually.

Mitigation:

- every valid Review creates reviewer contribution atomically; accept also
  creates FinalAcceptance and the submitter contribution sourced from it
- payable contributions create immutable awards; explicit unpaid rules create
  none
- daily award/fulfillment reconciliation
- fulfilled state requires an immutable receipt and external reference

### R6: Reviewer Abuse Or Low-Quality Review

Severity: medium

Problem:

Bad review decisions can demoralize contributors and corrupt quality metrics.

Mitigation:

- evidence-backed reviewer quality projections when separately implemented
- offline sampling and calibration
- immutable decision/finding history for future analysis
- no v0.1 adjudication or mutable overturn path

### R7: Fake Evidence

Severity: high

Problem:

Contributors may attach evidence that does not prove the work.

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
- contributor attestation
- guide rules for allowed materials

### R10: Status Bypass

Severity: high

Problem:

Tasks can be moved to review or accepted without required lifecycle evidence, or
awards can be marked fulfilled without their compensation receipts.

Mitigation:

- enforce state transitions in code
- require checker run id before `REVIEW_PENDING`
- require accepting Review, FinalAcceptance, and exact reviewer/submitter
  contribution source shapes before `ACCEPTED`
- require an immutable payable award, exact fulfillment receipt, and external
  reference before fulfillment status can become `fulfilled`
- replace broad historical override language with registered, scoped,
  reasoned, non-destructive Project Manager repair or Operator recovery

### R11: Reviewer Collusion Or Rubber-Stamping

Severity: high

Problem:

Reviewers can repeatedly approve weak work for favored contributors or skip evidence review.

Mitigation:

- sample accepted work through offline quality analysis that creates no product
  Review, decision, adjudication state, or authority
- flag repeated contributor-reviewer pairs for operator investigation
- require evidence citation on accept
- record quality concerns as audit/operations evidence without overturning or
  mutating the immutable Review
- include high-value or disputed tasks in configurable offline samples; sampling
  cannot delay or replace the recorded decision

### R12: Bad Project Guides

Severity: high

Problem:

A weak project guide creates vague tasks, inconsistent reviews, compensation
disputes, and checker blind spots.

Mitigation:

- guides require approval before activation
- every task locks a guide version
- repeated review issues become guide updates
- guide changes include effective date and change summary

### R13: Low-Quality Generated Submissions

Severity: medium

Problem:

Contributors may submit generic LLM-generated artifacts that look structured but do not solve the task.

Mitigation:

- project guides define banned low-quality patterns
- checkers flag repeated boilerplate, placeholders, and fabricated helper artifacts
- reviewers judge task-specific evidence, not formatting polish
- repeated pattern matches remain future reputation inputs only after separate
  reputation implementation

### R14: Compensation Disputes

Severity: high

Problem:

Immutable award quantity and external fulfillment status can diverge, especially
while fulfillment is manual.

Mitigation:

- frozen contribution policy evaluation creates immutable awards for payable
  contributions only
- award quantities are immutable
- disputed fulfillment remains separate from contribution truth
- daily reconciliation catches missing projections and fulfilled-without-receipt
  records

### R9: Overbuilding Marketplace Before Operating System

Severity: high

Problem:

Public marketplace features can distract from the quality engine.

Mitigation:

- v0.1 is internal
- no public bidding
- no blockchain dependency
- no source adapters until core lifecycle works
