# WS-AUTH-001-09C External Review Response

PR: `#146`

CodeRabbit run: `313d93f6-0386-4cce-97a6-d9442bdeebb3`

Published review head: `f08f4435ba68bbf285c5b21287e52c5907539aa1`

CodeRabbit test repair: `c64bcc726e45cd871bfc8514f61d350b8c1a960a`

Final reviewed lifecycle head: `2f4711fd55462898c32f82489a149ae53d6af192`

Reviewed against trusted main:
`a10d9018007d2e847b4870e9b26cbd24e24c7bb4`

## Actionable Findings

| Finding | Disposition | Repair and proof |
|---|---|---|
| Lock-wait helper accepted any PostgreSQL waiter | Accepted | Each transition publishes its exact backend PID immediately before the target mutation. The helper polls `pg_blocking_pids` for only that PID before releasing the paused administrative read. |
| Self-target response proof asserted only update count | Accepted | Profile reads assert exact `updated_at` and `last_seen_at` values; identity-link reads assert exact `last_verified_at`. |
| Effective-grant mock discarded positional authorization facts | Accepted | The mock records positional and keyword arguments, and tests assert the exact caller ActorProfile ID, action PermissionId, system-only mode, and locking options. |
| Missing-resource rollback covered only the profile route | Accepted | The behavior matrix covers both the profile and identity-link route with exact authorize, lookup, rollback, no-touch, and no-commit assertions. |
| Project-scoped Audit Authority denial covered only the profile route | Accepted | The real signed-token lifecycle test independently proves `permission_not_granted` for both administrative read routes. |

## Trusted-Main Reconciliation

PR #141 merged ART-02A3 as `a10d901` while the repair was in progress. The
branch integrates that trusted head without modifying ART production behavior.
The parallel-initiative Agent Gate now recognizes the exact merged record and
inactive ART-02B1 successor while preserving both original pre-merge review
branches. Internal review also removed obsolete AUTH-09C and ART-02A3 queue
prose and scoped its negative checks to the exact stale sentences.

## Validation

- Focused administrative route and kernel tests: 10 passed.
- Fresh isolated PostgreSQL lifecycle and exact lock-race tests: 2 passed in
  241.10 seconds through migration `0025_artifact_store_v2`.
- Authorization branch coverage remains 92.04 percent; production code is
  unchanged by the repair.
- Ruff, stale Workstream/authorization/artifact scans, Markdown links, merge
  intent, diff integrity, and all 80 Agent Gates: passed.
- No test was skipped, xfailed, removed, or weakened. No CI threshold,
  dependency, exclusion, or workflow changed.

## Review Result

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test-delta tracks pass exact reviewed
lifecycle head `2f4711f`. All five valid CodeRabbit findings are addressed, and
no internal finding remains open.

Replacement GitHub checks and explicit human merge approval remain. AUTH-09D is
inactive and must not start automatically.
