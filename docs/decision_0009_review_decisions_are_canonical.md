# ADR 0009: Review Decisions Are Canonical

## Status

Accepted

## Context

Workstream review results drive task state, revision loops, contribution
records, conditional compensation awards, and reputation signals.

If projects invent their own review outcome labels, downstream lifecycle rules become ambiguous.

Automated checker results also influence workflow routing before human review. That routing is not the same thing as a human review decision.

## Decision

The only canonical stored review decision values are:

- accept
- needs_revision
- reject

Display labels may render these as "Accept", "Needs revision", and "Reject", but persisted records, audit events, API payloads, and analytics must use the canonical stored values.

`Escalated` is not a review decision value.

Every valid human decision appends one immutable `Review`. Every submitted
`ReviewFinding` and every later `FindingResolution` is immutable; later rounds
append history rather than updating it. An `accept` Review additionally creates
one internal immutable `FinalAcceptance`. Only that fact can source the
submitter `accepted_submission` ContributionRecord. `needs_revision` and
`reject` create no FinalAcceptance and no submitter contribution.

Offline calibration, suspected fraud, compensation holds, or registered
recovery may create separate evidence or audit records, but they do not replace
the reviewer decision contract. Authorization recovery never creates a review
decision. Adjudication is a future separately approved lifecycle and adds no
v0.1 decision or state.

Checker routing recommendations use a separate contract. A checker can recommend that a submission is ready for review, needs contributor revision, needs checker retry handling, or cannot proceed because the task's locked setup is incomplete. A checker cannot accept or reject work.

Canonical checker routing recommendation values are:

- not_evaluated
- allow_review
- needs_revision
- checker_retry
- task_setup_blocked

`allow_review` must not be stored as `accept`. It only means the automated checker found no blocking issue and the packet may proceed to human review. Only a human review decision can store `accept`.

`task_setup_blocked` must not be stored as `needs_revision`. It means the task's
locked contract or policy context is incomplete, stale, or unsafe to review. An
authorized covered Project Manager must repair or re-screen the task before
contributor-facing revision or human review can continue.

`needs_revision` can appear in both contracts, but the source must be explicit:

- checker-caused revision: `outcome_source = auto_checker`, `review_decision_id = null`
- human reviewer revision: `outcome_source = human_review`, `review_decision_id = <review decision id>`

Checker-caused remediation follows CheckerResult lineage and does not enter the
Review-rooted revision-preparation chain. Only the human-review case creates the
immutable Review, findings, reviewer contribution, and
`RevisionContextPreparation` episode defined by the active review contract.

## Consequences

Positive:

- task state transitions remain simple
- review analytics can compare decisions across projects
- human revision preparation has one Review-rooted entry point
- contribution logic can depend on immutable Review and FinalAcceptance facts
- automated checker routing cannot accidentally masquerade as human acceptance or rejection

Tradeoff:

- special handling must be modeled as workflow, audit, dispute, or registered
  recovery records instead of extra review decisions
- code and docs must name checker routing fields clearly so reviewers do not confuse them with review decision fields
