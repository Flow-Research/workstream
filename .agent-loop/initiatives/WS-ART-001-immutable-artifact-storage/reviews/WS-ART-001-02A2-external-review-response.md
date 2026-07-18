# External Review Response: WS-ART-001-02A2

## Pull Request

PR #129: `https://github.com/Flow-Research/workstream/pull/129`

Reviewed code SHA: `ae70bc2f10334f649c1af7f210e58ee378695a2b`

Published evidence-bound head: `4ca80deede70b9b88f4cff01f01939f1309a20f6`

## External Checks

- Agent Gates: passed on integrated head `4ca80de` in GitHub Actions run
  `29486045005`.
- Backend: passed on integrated head `4ca80de` in GitHub Actions run
  `29485906937`, including full-suite, scoped coverage, and real API checks.
- CodeRabbit: passed on integrated head `4ca80de`; all five prior actionable
  findings remain addressed and no new comment was posted.

## Comments Addressed

- CodeRabbit: reject `NaN` and infinity in artifact preparation durations.
  Fixed with finite-number validation and regression cases.
- CodeRabbit: do not validate an in-progress root marker before acquiring the
  ledger lock. Fixed by validating marker contents under the lock.
- CodeRabbit: bound multiprocessing pipe receives and guarantee child cleanup.
  Fixed with timed `poll`, explicit failure, and `finally` cleanup.
- CodeRabbit: preserve the original cancellation when temporary cleanup fails
  and retain retryable `.part` ownership. Fixed in `aba8325` with exact
  cancellation-message proof, retained-file proof, canonical cleanup retry,
  and successful exact-request retry.
- CodeRabbit: make marker-validation ordering independent of spawned-process
  startup speed. Fixed in `aba8325` with explicit child-start and lock/order
  events plus bounded cold-start and child-shutdown limits.

## Comments Deferred

- None.

## Human Decisions Needed

The user remains the only merge authority for PR #129. Passing external checks
will not authorize merge or start `02A3`.

## Commands Rerun

Local deterministic and internal integration evidence is recorded in
`WS-ART-001-02A2-internal-review-evidence.md`. GitHub Agent Gates, Backend, and
CodeRabbit inspected and passed the integrated evidence-bound head.

## Remaining Risks

- The preparation boundary is intentionally inactive until `02A3`.
- No external finding remains open. A later implementation change would
  invalidate this evidence and require relevant review again.
