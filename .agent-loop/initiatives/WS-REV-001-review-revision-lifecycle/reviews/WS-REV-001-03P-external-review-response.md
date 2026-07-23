# External Review Response: WS-REV-001-03P

## Comments addressed

- GitHub Backend run `30025075528`, job `89267629866`, failed API E2E because
  `guide_payload()` still sent five retired policy fields, used obsolete finding
  names, and omitted the two canonical review durations.
- A prospectively reviewed scope amendment authorized only the policy request
  fixture. Candidate `b68a1e22b3bf373d15479784d545fcc9b5737f64`
  removes those retired inputs, uses `description` and `severity`, and supplies
  900-second preference and 1800-second lease durations.
- Shard 1 jobs exposed six stale current-head/atomic-downgrade expectations in
  `tests/test_alembic.py`. They now expect sole head
  `0034_review_revision_policy`; historical downgrade targets are unchanged.
- Shard 3 job `89267629913` exposed an ART proof fixture that inserted immutable
  policies after guide publication. After prospective scope review, the same
  guide is constructed draft, the same policies are flushed, and its prior
  active/approval/effective values are assigned before Task, Submission, or
  CheckerRun setup. Every ART assertion and final fixture fact is unchanged.
- Aggregate `test` failed only because API E2E and shards 1 and 3 failed.
  Shards 2 and 4 passed.

## Comments deferred

None.

## Human decisions needed

Only the normal explicit approval to merge PR #195 after every current-head
external check passes. The repair does not start 03A.

## Commands rerun

- Ruff on the API fixture and both affected test files: PASS.
- Four exact failed Alembic tests: PASS in 341.07 seconds.
- Exact failed ART test: PASS in 6.71 seconds.
- `git diff --check`: PASS.
- Senior/architecture/reuse, QA/product/test-delta, and security/docs/CI
  exact-SHA review: PASS.
- Fresh API E2E, all shards, aggregate test, and coverage evidence: pending
  GitHub Actions after push.

## Remaining risks

CodeRabbit did not perform a review: its green status explicitly reported that
the review limit was reached and it could not start. An actual current-head
CodeRabbit review remains required. No lifecycle, authorization, or ART
assertion was changed to obtain the repairs.
