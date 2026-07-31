# Chunk Contract: WS-XINT-003-03A — Reviewer Queue And Lease Activation

## Status and risk

Non-implementable planning skeleton after 02. Refresh exact files and commands
on current main before an explicit user request. L1 reviewer authority and concurrency.

## Goal

Activate concealed reviewer current-work through `review.queue.read`, plus
`review.claim`, `review.release`, and `review.decline_preference` against merged
hidden REV queue/lease behavior.

## Allowed files

Enumerate exact REV queue/lease, AUTH context/composer/catalogue parity, migration,
route, test, documentation, and evidence files at current-main start.

## Not allowed

Decision, finding, artifact byte, revision submission, contribution, recovery,
or lifecycle-release behavior; token roles or direct grant queries in REV.

## Acceptance criteria

- Reviewer current-work returns exactly the active lease, one server-selected
  offer, or none. It never exposes the backlog. It requires an active exact-
  project reviewer grant and conceals self-authored submissions.
- Claim locks AUTH authority, queue, submission contributor lineage, preference,
  and reviewer global lease state before atomically creating exactly one lease,
  one immutable `ReviewPacketManifest`, and freezing exact review/contribution
  policy facts. The manifest binds queue, lease, Submission, final/current
  CheckerRun/results, stamped context, and verified ART bindings.
- One reviewer holds at most one active lease globally and one submission has at
  most one active lease; crossed claims have one winner.
- Release and preference decline require the owning active lease/reviewer and
  are idempotent without rewriting history.
- Revocation, suspension, wrong project/role, self-review, stale queue, copied
  handle, and replay deny with no lease mutation.

## Verification and reviewers

PostgreSQL concurrency, PREP denial, concealment, route parity, focused
90-percent coverage, hosted full coverage; architecture, security, product/ops,
QA, senior, reuse, docs, test-delta, and CI-integrity review.

## Stop

Merge and stop before timer/service activation.
