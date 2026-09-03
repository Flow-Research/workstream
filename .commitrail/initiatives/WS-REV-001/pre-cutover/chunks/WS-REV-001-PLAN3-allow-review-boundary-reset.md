# Chunk Contract: WS-REV-001-PLAN3 - Allow-Review Boundary Reset

## Parent

WS-REV-001 review and revision lifecycle.

## Goal

Correct the initiative plan so REV starts only from a durable final checker
outcome of `allow_review`, consumes the existing Submission and its exact
submitted/verified artifacts, and never implements upstream owner gaps.

## Why

The superseded 02A plan incorrectly assigned Project Guide, setup publication,
activation, and Task intake responsibilities to REV.

## Risk

L1: ownership, audit lineage, contribution, and future adjudication semantics.

## Allowed files

- `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**`
- `.agent-loop/merge-intents/WS-REV-001-PLAN3.json`

## Not allowed

- Application code, migrations, tests, workflows, routes, or schemas.
- Project Guide setup/activation, Task intake, Submission creation, checker, AUTH,
  ART, or CON owner implementation.
- Adjudication implementation.
- Starting 03P, 03A, or any other runtime chunk.

## Acceptance criteria

- 02A/02B/02C ownership plans are visibly retired and non-executable.
- REV begins at the exact durable `allow_review` outcome.
- REV consumes the same finalized Submission and submitted/verified artifacts.
- Each Review appends immutable findings and one of `accept`, `needs_revision`,
  or `reject`, with a traversable predecessor Review link.
- Submission versions retain traversable predecessor lineage across revisions.
- Every completed Review creates one reviewer contribution.
- Only `accept` creates FinalAcceptance and exactly one submitter accepted-task
  contribution.
- The complete Submission/Review history remains available as future
  adjudication input; adjudication remains out of scope.
- Upstream gaps are documented for their owner and never implemented by REV.

## Verification

- Validate initiative consistency and schema-v2 merge intent.
- Run repository documentation/link/stale-wording checks applicable to changed
  files and the focused agent-gate suite.
- Obtain required internal plan, architecture, senior/QA, security, product/ops,
  docs, and reuse review on the exact candidate.

## Human review focus

Confirm the ownership boundary, lineage semantics, contribution cardinality,
and that 03P is the first future REV runtime chunk, followed by 03A.

## Stop

Planning complete. Awaiting merge and a signed workflow start before implementation.
