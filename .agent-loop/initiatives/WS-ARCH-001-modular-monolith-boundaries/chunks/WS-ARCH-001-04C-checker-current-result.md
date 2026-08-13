# Chunk Contract: WS-ARCH-001-04C CHECKER Current Result Persistence

Status: non-executable planning skeleton after 04A/04B. Risk: L1. Outcome:
CHECKERS installs hidden, deny-only execution of the exact post-submit plan and
persists one immutable final result with explicit
supersession/currentness and routing recommendation.

Allowed: CHECKER owner-local run/result repository, service and Celery execution code,
its public API, focused tests, migrations chosen from current main, boundary
ledgers and evidence/status. Not allowed: ART binding writes, TASK status
mutation, AUTH activation, REV admission, model inference outside the compiled
policy, or synchronous-first execution.

Execution must reuse the POL-003 single checker-service port and
`evaluate_post_submission(...)`; no second dispatcher, phase API, catalogue,
or caller-triggered execution path is allowed. Production remains fail-closed
until 04D activates the exact fixed-service boundaries.

Acceptance: retry and concurrency yield one current final result; stale plan,
generation, binding or Submission fails; `allow_review` is impossible for
failed/partial execution or while any blocking failure remains under the
locked post-submit policy; a blocking failure and current `allow_review`
cannot coexist; audit/outbox facts are atomic. Verify unit,
PostgreSQL concurrency, Celery retry/recovery, boundary validators, Ruff and
hosted coverage. Required reviews: architecture, security, product/ops, QA,
senior, CI and test delta.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.
