# Reviewer Workflow

## Status

This is the planned v0.1 operating contract. Reviewer routes and jobs remain
unavailable until their hidden REV behavior, exact AUTH activation, and the
REV-13 joint release complete. `spec_review_lifecycle.md` is normative.

## Reviewer Job

The reviewer decides whether one exact leased Submission satisfies the task and
the Project Guide context stamped on that Submission. No guide rebase occurs
during review, and the active-at-read-time guide does not replace stamped context.

The reviewer must have an exact active project `reviewer` grant represented by
canonical human `ActorProfile.id`. Submitter, adjudicator, administrative, or
token-role authority does not substitute. No-self-review and lifecycle guards
still apply.

## Current Work And Claim

The reviewer current-work operation returns an active lease, one server-selected
offer, or none. It never returns the complete backlog. A claim creates one
ReviewLease and immutable ReviewPacketManifest under PostgreSQL race guards.

The reviewer may read artifact bytes only for the exact Submission packet named
by the current active lease. Authorized history contains bounded metadata, not
prior or unrelated artifact bytes.

## Review Inputs

The planned Review Context contains:

- queue, lease, Submission, and admitting CheckerRun identity;
- stamped Project Guide identity, version, and activation sequence;
- task description and acceptance criteria;
- submission summary and exact packet bindings;
- checker results and bounded evidence;
- prior immutable Reviews and findings when relevant;
- revision preparation transition, submitter responses, and prior resolutions.

## Decisions

Allowed decisions are exactly `accept`, `needs_revision`, and `reject`.

Every valid decision appends one immutable Review. Every submitted finding and
later resolution is immutable. Every Review creates one reviewer
`completed_review` ContributionRecord and evaluates the ReviewLease-frozen
ContributionPolicyVersion, regardless of outcome.

`accept` means the Submission satisfies its stamped context. It additionally
creates one immutable FinalAcceptance, accepts the task, completes the
TaskAssignment, and creates the submitter `accepted_submission` from
FinalAcceptance. There is no direct Review-to-submitter contribution inference.

`needs_revision` means concrete blocking issues are fixable. It keeps the
TaskAssignment active, creates no FinalAcceptance, and creates no submitter
contribution.

`reject` means the work is not reasonably salvageable or violates the governing
contract. It requires a bounded human reason, blocks the same-task assignment,
sets the task to `rejected`, and creates no FinalAcceptance or submitter
contribution.

## Findings

A ReviewFinding contains:

- lifecycle meaning: `blocking` or `advisory`;
- area;
- issue and rationale;
- required change for blocking findings;
- optional finalized evidence binding.

`needs_revision` requires at least one unresolved blocking finding. Advisory
findings must not become preference-only acceptance requirements. Reject
requires its bounded reason; structured findings are optional when they add
useful evidence and are never fabricated merely to satisfy a field.

## Revision Review

For a revised Submission, the reviewer checks each required immutable
SubmissionFindingResponse and appends one FindingResolution with result
`resolved`, `unresolved`, or `not_applicable`. The reviewer does not edit the
prior finding or response.

The revised Submission initially returns to the reviewer who requested the
revision. Preference expiry, decline, or authority invalidation opens the same
queue entry without resetting its age.

## Decision Transaction

The route owns one transaction:

```text
AUTH prepared authority and final evaluation
-> append Review/findings/resolutions
-> consume ReviewLease and close ReviewQueueEntry
-> CON reviewer operation
-> accept: FinalAcceptance + task effects + CON submitter operation
   needs_revision: task effect only
   reject: assignment block + task effect
-> REV stages shared audit/outbox
-> commit once
```

The transaction performs no Artifact Storage call. Any participant failure rolls
back all lifecycle, contribution, award, audit, and outbox effects.

Accept must create:

- review decision record
- one immutable internal FinalAcceptance linked to the exact Review, existing
  versioned Submission, task, submitter, recording reviewer, and locked
  ReviewPolicy
- acceptance audit event
- reviewer `completed_review` contribution record
- submitter `accepted_submission` contribution record sourced from
  FinalAcceptance, not directly from Review.decision
- any awards required by the separately frozen reviewer and submitter
  contribution policies

The reviewer cites the strongest evidence supporting acceptance, not only
"looks good."

## Needs Revision

Use needs_revision when:

- issues are fixable
- the submission is not acceptable yet
- reviewer can describe concrete required fixes

Do not write vague feedback. Every blocking issue must tell the contributor
what is wrong and what must change.

Needs-revision feedback must not introduce preference-only work. If the guide
does not require it and acceptance is not blocked by it, record it as advisory.

Each blocking finding must have:

- exact issue
- why it blocks acceptance
- required fix
- evidence reference or file/section reference

Recording `needs_revision` sets the Task to `needs_revision`, keeps the same
TaskAssignment `active`, and creates no FinalAcceptance or submitter
contribution. The reviewer `completed_review` still commits atomically.

## Reject

Use reject when:

- the work is fundamentally wrong
- the submission is non-original or violates policy
- the task cannot be salvaged by reasonable revision
- the contributor submitted prohibited material

Use reject carefully. If the work can be reasonably corrected through one
revision cycle, use `needs_revision`.

Recording `reject` sets the Task to canonical `rejected` with the bounded human
reason and blocks only the same-task TaskAssignment with its source Review. It
changes no actor grant or unrelated task and creates no FinalAcceptance or
submitter contribution. `closed/review_rejected` is not a canonical state.

Every valid recorded `needs_revision` or `reject` decision still creates the
reviewer's `completed_review` contribution and evaluates the ReviewLease-frozen
reviewer contribution policy. Neither decision creates a submitter contribution
or submitter award.

## Offline Reviewer Quality

Track:

- review count
- decision distribution
- non-mutating sampled-quality findings
- unclear feedback reports
- average turnaround
- repeated missed prior findings

Offline quality evidence may be recorded when:

- feedback is marked unclear
- non-mutating sampling finds unsupported acceptance/rejection reasoning
- reviewer misses unresolved prior findings

These quality signals never reopen or replace Review, FinalAcceptance, task, or
ContributionRecord truth. V0.1 has no adjudication decision or queue.

## Reviewer Checklist

Before any decision:

- confirm the exact active lease and packet;
- use the guide/policy context stamped on the Submission;
- verify the admitting CheckerRun belongs to that Submission;
- ground judgment in acceptance criteria and available evidence;
- check all required prior responses and resolutions;
- distinguish blocking requirements from advisory observations;
- confirm the decision-specific task, assignment, FinalAcceptance, and
  contribution effects can commit atomically.
- confirm both frozen contribution policies can be evaluated and that an
  explicit unpaid result is valid and creates no award.

Before `needs_revision`, confirm every blocking issue has an actionable required
change and no unrelated preference is demanded. Before `reject`, confirm the
bounded reason is guide-grounded and the work is not reasonably fixable.

Offline sampling and calibration may evaluate review quality, but they do not
create adjudication state, overturn a Review, or mutate immutable history.

## Non-Mutating Quality Sampling

During the first 30 days, audit at least:

- 25 percent of accepted submissions
- 25 percent of rejected submissions
- any submission matching the configured high-value criterion in
  `ReviewPolicy`

Sampling checks whether the reviewer followed the guide and cited evidence. It
does not create a Review, adjudication result, reopen path, replacement
FinalAcceptance, or lifecycle mutation.
