# Revision Replay

## Status And Purpose

This is the planned v0.1 operating contract. Revision behavior remains
unavailable until its owning REV chunks, exact AUTH activation, and REV-13 joint
release complete.

Revision replay preserves an immutable answer to three questions: what the
reviewer required, how the submitter responded, and how a later reviewer
resolved each issue. No participant edits a prior Review, finding, response, or
resolution.

## Review-Rooted Preparation

Human revision begins only from an immutable `Review(needs_revision)`. Checker
remediation remains CheckerResult-rooted and does not fabricate a Review episode.

Before contributor access, Workstream appends a RevisionContextPreparation. It
compares the prior Submission's stamped Project Guide identity and activation
sequence with the currently active guide:

- exact pair match: `kept`;
- any different valid active pair: `rebased` with `forward` or `backward`;
- missing, incomplete, inconsistent, revoked, or unsafe context: `blocked`.

The preparation freezes the selected guide/source/task-execution policy context,
context digest, prior Submission, originating Review, source and target
TaskAssignments, and change summary. Task Context returns the validated head,
not a moving live guide. No guide rebase occurs during review; the reviewer
reads the context stamped on the leased Submission.

ContributionPolicyVersion is independent. The TaskAssignment freeze and each
ReviewLease freeze never change because guide context rebases.

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
replace per-finding responses.

## Resubmission And Checks

Submission N+1 acknowledges the exact preparation head/digest, links its
immediate predecessor, and stamps the frozen context. The normal finalization
and checker spine reruns. Only a current successful `allow_review` may create a
new queue entry.

The queue initially prefers the reviewer who requested revision. Expiry,
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

A reached revision limit or deadline blocks further preparation and
`submission.create`; it does not automatically reject or cancel the task. The
task remains `needs_revision` until a covered Project Manager explicitly invokes
the planned reason-bound obligation-close command. That administrative closure
uses task `cancelled`, releases the assignment, and creates no synthetic Review
or contribution.

A blocked or invalid Review-rooted preparation can be repaired only by appending
one successor through the planned covered-manager repair command. Legacy
`needs_revision` state with no Review/root requires an Operator evidence-linked
legacy close and cannot enter normal revision replay.

## Required Proof

A revision cannot return to human review unless every unresolved blocking
finding has one response, the exact preparation is still current, Submission
lineage is immediate and same-task, evidence bindings are finalized, and the
new CheckerRun is current for that Submission.
