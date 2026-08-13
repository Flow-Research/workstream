# Revision Replay

## Status And Purpose

This is the planned v0.1 operating contract. Revision behavior remains
unavailable until its owning REV chunks, exact AUTH activation, and REV-13C joint
release complete.

Revision replay preserves an immutable answer to three questions: what the
reviewer required, how the submitter responded, and how a later reviewer
resolved each issue. No participant edits a prior Review, finding, response, or
resolution.

## Review-Rooted Preparation

Controlled revision replay begins only from one immutable
`Review(needs_revision)`. Checker remediation remains a separate CheckerRun-
rooted resubmission path using the Task's existing locked context; it does not
fabricate a Review, finding, preparation, reviewer contribution, or human actor.

Before contributor access, Workstream appends a RevisionContextPreparation. It
compares the prior Submission's complete stamped governing context with the
currently active applicable Project Guide/source, submission-artifact,
pre-submit/post-submit checker, review, revision, task-template/task-execution,
and submitter ContributionPolicy context:

- every exact component match: `kept`;
- all changed valid active components: `rebased` together, with `forward` or
  `backward` recorded where the component is ordered;
- missing, incomplete, inconsistent, revoked, or unsafe context: `blocked`.

The preparation keeps every exact component match and rebases every changed
valid component as one selected context. Any missing, incomplete, inconsistent,
revoked, or unsafe component blocks the whole preparation. It freezes the
selected context, context digest, prior Submission, originating Review, source
and target TaskAssignments, prior/next submitter ContributionPolicyVersion, and
change summary. Task Context returns the validated head, not moving selectors.
No rebase occurs during review; the reviewer reads the context stamped on the
leased Submission.

The completed reviewer contribution uses the originating ReviewLease version.
Successful human revision preparation may create a newly prepared task context
for the next attempt; it never rewrites an existing TaskAssignment. Each later
assignment and ReviewLease inherit that task's lock. The decision,
reviewer contribution/award, task/assignment effects, preparation or blocked
outcome, audit/outbox, and visible state commit once or roll back together.

## Submitter Response

For each unresolved blocking ReviewFinding, the assigned submitter creates one
immutable SubmissionFindingResponse containing:

- finding ID;
- response text and concrete change summary;
- optional finalized evidence binding;
- exact preparation head ID and digest;
- target Submission and TaskAssignment lineage.

Advisory findings may be answered but do not block resubmission unless the locked
policy explicitly requires a response. Vague aggregate “fixed all” text cannot
replace per-finding responses. The distinct checker-remediation path uses only
contributor-safe checker messages/fixes and requires no fabricated
ReviewFinding response or resolution.

## Resubmission And Checks

A human-Review Submission N+1 acknowledges the exact preparation head/digest,
links its immediate predecessor, and stamps the complete frozen context. A checker-
remediation Submission N+1 instead binds the exact final needs-revision
CheckerRun and the Task's existing locked context; it carries no preparation or
ReviewFinding response. Both paths rerun the normal finalization and checker
spine. Only a current successful `allow_review` may create a new queue entry.

Human Review return initially prefers the reviewer who requested revision. The
distinct corrected checker path enters open routing. Expiry,
decline, or invalidation opens the entry without resetting queue age.

## Reviewer Resolution

The later Review appends one FindingResolution for every required prior finding:

- `resolved`;
- `unresolved`;
- `not_applicable`.

Each resolution carries bounded rationale and optional evidence. It never edits
the original finding or submitter response. A new guide-grounded issue becomes a
new ReviewFinding on the later Review.

## Limits And Recovery

Exact human Review round counting, deadline anchor, and boundary require human
approval before implementation and exclude checker retries. Approved values use
database time and freeze on the Review-rooted episode. A reached revision limit
or deadline blocks further preparation and
`submission.create`; it does not automatically reject or cancel the task. The
task remains `needs_revision` until a covered Project Manager explicitly invokes
the planned reason-bound `review.revision_obligation.close` command. That
administrative closure uses task `cancelled`, releases the assignment, and
creates no synthetic Review or contribution.

A blocked or invalid context preparation can be repaired only by appending one
successor through the planned covered-manager repair command. Repair cannot
bypass limit/deadline exhaustion. Exact durable CheckerRun remediation is not
legacy; only ambiguous or truly rootless claimed human Review state uses
Operator evidence-linked close.

## Required Proof

A human-Review revision cannot return to human review unless every unresolved
blocking finding has one response, the exact preparation is still current,
Submission lineage is immediate and same-task, evidence bindings are finalized,
and the new `allow_review` CheckerRun is current for that Submission.

A checker-remediation submission cannot enter human review unless it binds the
exact final needs-revision CheckerRun that caused remediation through immutable
`remediation_source_checker_run_id`, preserves the Task's existing locked
context, has immediate same-task Submission lineage, and has a new current
`allow_review` CheckerRun. The source relation is server-derived, unique, and
cannot be rewritten by a later retry. It has no preparation or ReviewFinding
response requirement.
