# Revision Replay

## Status And Purpose

This contract covers controlled revision and the remaining human Review
integration. Human decision composition remains unavailable until its owning
REV work and exact AUTH activation complete. Checker-remediation replacement
uses public preparation and admission-backed Submission operations with a frozen
next-attempt context; it does not make human Review decisions available.

Revision replay preserves an immutable answer to three questions: what the
reviewer required, how the submitter responded, and how a later reviewer
resolved each issue. No participant edits a prior Review, finding, response, or
resolution.

## Source-Rooted Preparation

Human revision begins from one immutable `Review(needs_revision)`. Checker
remediation begins from the exact authorized current CheckerRun failure and its
routing manifest. Both require a frozen next-attempt preparation; checker
remediation never fabricates a Review, finding, reviewer contribution or human
actor.

Before contributor access, Workstream appends the source's immutable preparation:
TASK-owned `TaskRevisionPreparation` for checker remediation, or the planned
Review-rooted `RevisionContextPreparation` for genuine human decisions. It
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
selected context, context digest, prior Submission, exact routing manifest or
originating Review, source and target TaskAssignments, prior/next submitter ContributionPolicyVersion, and
change summary. Task Context returns the validated head, not moving selectors.
No rebase occurs during review; the reviewer reads the context stamped on the
leased Submission.

The completed reviewer contribution uses the originating ReviewLease version.
Successful revision preparation may atomically rebase the continuing
Task and TaskAssignment for the next submission attempt. Earlier Submissions
and ReviewLeases remain immutable; the next Submission and ReviewLease use the
rebased version. The decision,
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

The contributor uses the ordinary raw-ZIP submission command on the same task
and assignment with a new idempotency key. TASK selects the immediate
predecessor and governing revision context and rechecks eligibility before PRE
and intake acceptance. For checker remediation, the selected context binds
the predecessor's exact current needs-revision CheckerRun. Accepted custody
retains those facts for finalization and evaluation. Only a current successful
`allow_review` may create a new review queue entry.

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

The project RevisionPolicy requires an explicit integer `max_revision_rounds >= 0`;
there is no per-task override. Each assignment starts at round 0. A limit of 2
permits revisions 1 and 2; zero permits only the initial Submission. A final
contributor-fixable failure immediately records `TaskRevisionExhaustion`, closes
the assignment as `revision_exhausted`, and returns the task to `ready` in the
same authorized transaction. It creates no next preparation or deadline. History
projects the failed Submission as rejected with `revision_limit_reached`.

When another revision remains, the failure freezes a complete next-attempt
context and a fresh PostgreSQL-time allowance. A setup-blocked context pauses
that allowance and publishes durable PM-attention evidence. A blocked root
created with the original failure preserves the full policy duration. Recovery
of a missing root preserves only the unspent original allowance, including when
the recovered context is blocked; an already due source stays due.
Repair resumes only the stored remaining
time; repair of a running context preserves its deadline. The API exposes
`clock_state`, nullable `deadline_at`, and nullable `remaining_microseconds`:
paused means no deadline and a stored remainder; running means a deadline and
no stored remainder. Covered PM task detail exposes the same revision context.

Only a committed immutable successor ends a running opportunity. ZIP upload,
ready admission, replay and infrastructure retry do not. At the effective
deadline, durable expiry records `TaskRevisionExpiration`, closes the assignment
as `revision_expired`, and returns the task to `ready`. Task/assignment changes,
terminal evidence, authorization, audit and outbox intent commit together.
Neither exhaustion nor timeout fabricates a Review, contribution or award;
original Submissions and findings remain immutable.

There is no contributor-count limit or repeated-failure hold. Any eligible
contributor, including a previous claimant, may claim again under a new
assignment at round 0. The closed assignment remains terminal and its
`last_assignment_outcome.next_action` is `none`. Infrastructure failures use
bounded recovery and consume neither an attempt nor a revision window.
Checker and future human triggers share the intended policy; #554 owns genuine
human Review integration.

The recurring Celery scan uses PostgreSQL server time and recovers overdue
opportunities after downtime. Duplicate deliveries and old jobs recheck exact
source, assignment and status under TASK-first custody; they cannot reject a
newer submission or release another claimant. A new claimant starts round 0
with their own allowance while task-global Submission versions remain ordered.

Expiry delivery is explicitly safe to retry after a Celery process crashes: the new
invocation either performs the authorized transaction or acknowledges its exact
immutable receipt. Retries retain the exact scheduled clock and use bounded backoff. Stale timer
intents cannot expire a paused or resumed preparation.
An exhausted retry budget or rejected authority remains visible as dead-letter
work requiring operator resolution; it must not be reported as a completed timeout.

A blocked or invalid context preparation can be repaired only by appending one
successor through covered-manager repair. For checker-rooted preparations,
`POST /api/v1/projects/{project_id}/tasks/{task_id}/revision-context/repair` takes
`parent_preparation_id`, `parent_preparation_sha256`, a bounded `reason`, and an
`Idempotency-Key`. It records the exact parent and authorized child atomically.
Repair cannot reopen an exhausted assignment or an already elapsed running window. The contributor work-context
read exposes the frozen change summary and current eligibility.

The recurring service scan discovers current retained failures missing preparation
or scheduling. Fresh service authority freezes an unchanged context or a blocked
root and publishes its exact clock or paused-attention intent; it cannot
authorize a rebase. It also reconciles retained pre-upgrade failures: a source
already at its locked cap receives immediate exhaustion under fresh recovery
authority, even if its old timer still exists. That obsolete timer acknowledges
without recording a timeout. A retained setup-blocked running window receives
one paused successor preserving only its unspent PostgreSQL time; an already
due window remains due. Original records and scheduling intents stay immutable.
Exact already-scheduled work with no required reconciliation is a no-op.

Before enabling this journey, provision `workstream.task.revision_expirer` through
the existing authorized `POST /api/v1/service-actors` operation and keep its
profile and identity link active. The principal covers only revision expiry and
retained-window recovery. Run Celery Beat and Celery processes consuming both the
default queue for `workstream.tasks.scan_retained_revisions` and the existing
outbox delivery queue. The retained-source scan runs every 60 seconds; due events are dispatched
by the existing outbox scan. A missing or inactive principal does not grant
fallback authority: inspect scan failures and outbox dead-letter diagnostics.

For explicit manager recovery, the same endpoint accepts `routing_manifest_id`
and `reason` instead of the parent pair when the preparation is missing. It
records the missing root using the original failure's window; ordinary routing
replay does not create it. An expired source cannot gain more time. An exhausted source cannot create
a preparation; the recovery scan records its terminal outcome. Exact repair replay returns its original preparation identity and
window after fresh authorization, with eligibility evaluated against the current
source and preparation head.

## Required Proof

A human-Review revision cannot return to human review unless every unresolved
blocking finding has one response, the exact preparation is still current,
Submission lineage is immediate and same-task, evidence bindings are finalized,
and the new `allow_review` CheckerRun is current for that Submission.

A checker-remediation replacement uses the exact authorized needs-revision
routing manifest for the immediate predecessor's current completed CheckerRun.
ART evidence and admission, TASK dispatch and final AUTH resources retain the
server-selected `checker_remediation_manifest_id`; the new Submission links its
predecessor and admission without a duplicate cause field. It uses the frozen
next-attempt context, reruns full pre-submit intake, and has no human Review or
ReviewFinding response requirement. A later current `allow_review` result can
enter the ordinary review route only under its locked ReviewPolicy. A later
retry cannot rewrite the committed cause.
