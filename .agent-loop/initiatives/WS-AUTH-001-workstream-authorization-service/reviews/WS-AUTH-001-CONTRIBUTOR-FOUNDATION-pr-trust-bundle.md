# WS-AUTH-001-CONTRIBUTOR-FOUNDATION PR Trust Bundle

## Goal

Clean-cut task-assignment and submission human attribution to canonical
`contributor_id`, enforce human ActorProfile lineage at the database boundary,
and revalidate the exact active caller inside contributor-write transactions.

## Changes

- Renames and narrows both live owner columns and indexes with no alias, fallback,
  dual field, guessed identity mapping, or historical audit rewrite.
- Adds exact foreign keys plus one reusable invoker-rights human-lineage trigger
  function and named triggers for both tables.
- Adds actor-owned profile/link locking and task-owned task/assignment locking in
  canonical order for claim and submission, with stable 403 and retryable 503
  responses and rollback.
- Updates public schemas, new audit evidence, the real API drill, current docs,
  persistent task coverage reporting, agent gates, and the schema-v2 merge intent.

## Boundary

This PR changes no ActionId, PermissionId, evaluator, grant, role behavior,
authorization decision/evidence path, service admission, task lifecycle, review
or revision behavior. The temporary legacy role token and separately owned
attestation/profile route cleanup remain AUTH-13/14 work. AUTH-09E stays inactive.

## Proof

- Repaired migration matrix: 2 passed in 102.35 seconds.
- Full observed contributor/lifecycle race matrix: 12 passed in 636.24 seconds.
- Canonical API-error mapping: 1 passed in 63.79 seconds.
- All eight Alembic tests implicated by the first Backend run passed in CI order
  on one isolated PostgreSQL database in 959.71 seconds; the three root
  lifecycle tests passed independently in 339.89 seconds.
- The second Backend run passed all 1,567 tests and every earlier coverage gate,
  then exposed task subsystem coverage at 84.14 percent. Twenty-four new direct
  task-service behavior cases pass and execute 92 statements from the exact CI
  missing set, projecting the unchanged task gate to about 90.90 percent.
- Real HTTP API contract drill: passed.
- Focused actor/task unit and database behavior tests: passed.
- Ruff, docstring gate (90.3 percent), stale scanners, Markdown links, diff
  integrity, one Alembic head, and 88 agent gates: passed.
- No skips, xfails, weakened assertions, exclusions, or threshold reductions.

GitHub Backend remains the authoritative mandatory proof for global 78 percent
and persistent actor/authorization/task 90 percent coverage before merge.

## Internal Review

Exact implementation SHA `4d1fc507c343d483677a332c2a91885e32571693` and
closeout head `4db178147bae457d9fccb3643fe6bd3919ba41c2` against trusted main
`93dd392484b397cfdfaaa833631dc2c27f591ed7` passed senior engineering,
QA/test, security/auth, product/ops, architecture, CI integrity, docs,
reuse/dedup, and test-delta review after every valid finding was repaired.
Test-only Backend repair `b48aa3dd8ba5ddc74b89524169a7df0a52a3fb27`
then passed fresh exact-SHA review across the same tracks with no findings. The
review confirmed that revision-specific lifecycle tests no longer conflate
`head` with `0026`, while general-head and dedicated `0027` coverage remain.
Task-coverage repair `0ca5a6326a893e6671848dacde484b7c784b7bd0`
also passed fresh exact-SHA review across all nine tracks with no findings.
Reviewers confirmed that the tests exercise production authorization,
attribution, fail-closed parsing, evidence bounds, and lock-conflict decisions;
mocks remain limited to existing orchestration seams.

## Human Review Focus

Review migration refusal/redaction and reversible preservation, exact database
object names, profile-to-link-to-task-to-assignment lock order, lifecycle race
outcomes, 403/503 privacy and rollback, clean `contributor_id` API/evidence
shape, and absence of authorization availability or later AUTH-13/14 behavior.

## Merge Ownership

The agent may publish and repair this branch but may not merge it. Only the
human may approve this PR for merge. After merge, trusted-main automation owns
schema-v2 memory generation; no manual post-merge memory PR should be opened
when that workflow succeeds.
