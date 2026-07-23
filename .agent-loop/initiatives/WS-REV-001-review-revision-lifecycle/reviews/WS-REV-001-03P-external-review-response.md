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
- CodeRabbit run `9747dead-4c6c-4474-a989-4035a1292ec3` found three valid
  current-head issues. The evidence and status artifacts now bind their
  reviewed and post-repair candidates consistently, and migration 0034 now
  rejects `TRUNCATE` on both immutable policy tables with statement-level
  triggers that downgrade removes explicitly. The migration regression test
  exercises both rejection paths.

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
- Ruff and `git diff --check` for the CodeRabbit repair: PASS. The exact
  database-backed migration test could not start locally because
  `WORKSTREAM_TEST_DATABASE_URL` is unset; it remains required in GitHub
  Actions rather than substituting a weaker local database.

## Remaining risks

The CodeRabbit repair requires current-head GitHub Actions and incremental
CodeRabbit confirmation after push. No lifecycle, authorization, or ART
assertion was changed to obtain the repairs.
