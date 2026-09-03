# External Review Response: WS-ART-001-03B Planning Correction

## Comments Addressed

- CodeRabbit's reviews produced six valid findings. The contracts now
  preserve repository-wide 78% coverage before their scoped 90% reports; name
  exact v0.1 extraction limits, enforcement points, stable outcomes, boundary
  tests, cleanup, and executor-loss proof; map timeout and memory termination to
  non-retryable limit failure and executor loss to one bounded fresh retry;
  exhaustively map every extraction status to a redacted public code and
  remediation; use consistent
  `guide-read` wording; and require a second locked lineage/integrity/provenance
  validation immediately before report commit.
- Agent Gates correctly found five uses of retired human `worker` vocabulary in
  new planning text. They were replaced with parser runtime, executor, and
  project-setup executor wording. The future coverage command now avoids
  embedding the retired vocabulary while retaining explicit setup-executor
  coverage.
- Backend semantic-lane evidence showed one unrelated existing AUTH PostgreSQL
  concurrency failure: expected statuses `[200, 403]`, observed `[500, 200]` in
  `test_actor_identity_link_lifecycle_real_postgres_concurrency`. The other
  1,651 tests in that lane passed. This planning PR changes no backend runtime or
  tests; the next pushed head receives a fresh hosted rerun.

## Comments Deferred

- No backend product-code repair is justified from the isolated AUTH concurrency
  failure without reproduction on the new head; it is outside this planning
  diff.

## Human Decisions Needed

None for the current repair.

## Commands Rerun

```text
python3 scripts/check_stale_authorization_docs.py
git diff --check
```

Both pass. The full documentation/stale-contract suite is rerun before push.

## Remaining Risks

- Hosted Backend and Agent Gates must pass the repaired exact head, and all six
  CodeRabbit threads must be verified against that head.
