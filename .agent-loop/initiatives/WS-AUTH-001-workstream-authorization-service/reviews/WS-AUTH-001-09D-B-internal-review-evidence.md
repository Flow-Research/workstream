# WS-AUTH-001-09D-B Internal Review Evidence

Reviewed code SHA: `ab6669ebde0d5947ab8b4631667c9ec552ba7687`

Reviewed implementation SHA: `4bd377fb`

Reviewed against trusted main:
`1b5422fcaa361152af7c2b1f82a763d99c0e6db5`

Reviewed at: `2026-07-19T02:06:03Z`

Reviewer run IDs: `auth_xint_roles`, `auth_xint_art_service`,
`auth_xint_rev_con`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Deterministic Evidence

- Exactly `actor.identity_link.revoke` and
  `actor.identity_link.reactivate` become active. The catalogue contains 65
  ActionIds: 17 active and 48 planned.
- The two exact PostgreSQL lifecycle/concurrency nodes passed in 241.09 seconds.
  They prove lock-observed same-key, different-key, mixed profile/link/grant,
  three-administrator, and actor-self GET/PATCH races without timing sleeps.
- The isolated authorization selection passed 112 tests in 543.89 seconds at
  90.11 percent branch coverage, above the required 90 percent subsystem floor.
- After integrating ART-02B1 from trusted main, the exact focused PostgreSQL
  behavior selection passed 167 tests in 299.64 seconds. ART provider,
  workflow, storage, and initiative files are byte-identical to trusted main in
  this PR's final diff.
- Failure injection proves exact rollback of profile, link, grant, audit,
  idempotency, and verification-timestamp state with reusable losing keys and
  the stable retryable 503 response.
- Behavior tests prove exact replay after later state changes, mismatch and
  conflict preservation, self-revoke denial, missing-target concealment,
  final-Access-Administrator protection, service-target handling, and exact
  success, invalidation, and denial evidence.
- The old PR-head Backend run passed 1,334 tests at 85.09 percent global
  coverage, then exposed an 89.39 percent authorization slice. A five-case
  behavior test now proves route success, replay, mismatch, conflict, and SQL
  failure ordering and executes 29 previously uncounted lifecycle-route
  statements, exceeding the measured 12-statement deficit. All five cases pass;
  replacement CI remains authoritative for the final percentage.
- The isolated real HTTP API contract drill passed. Ruff, stale Workstream,
  authorization, and artifact scans, Markdown links, all 88 agent-gate tests,
  merge-intent validation, and diff integrity also passed.
- No test was skipped or marked xfail, and no coverage threshold, workflow
  gate, or production behavior was weakened after the deterministic proof.
- The planning repair inserts inactive
  `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` immediately after 09D-B. It owns the
  clean `contributor_id` field transition and canonical-human lineage; AUTH-13
  and AUTH-14 consume that foundation instead of renaming the fields later.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | The lifecycle orchestration, transaction ownership, exact resource binding, and contributor-foundation sequence are coherent. |
| QA/test | PASS AFTER FIXES | none | Real database locks and route outcomes assert exact final state, ordering, evidence, rollback, timestamps, and idempotency disposition. |
| security/auth | PASS AFTER FIXES | none | Authority is revalidated before disclosure; privacy-safe denial, final-admin preservation, and fail-closed rollback are proved. |
| product/ops | PASS AFTER FIXES | none | Only an effective system Access Administrator may mutate a link; reactivation restores neither a grant nor service admission. |
| architecture | PASS AFTER FIXES | none | AUTH retains centralized catalogue, evaluator, guard, evidence, and activation ownership without compatibility paths. |
| CI integrity | PASS AFTER FIXES | none | The genuine route behavior repair addresses the measured coverage deficit without changing the 90 percent authorization floor, repository floor, or isolated runner. |
| docs | PASS AFTER FIXES | none | API, operations, data model, lifecycle state, and successor gates match the implemented behavior. |
| reuse/dedup | PASS AFTER FIXES | none | The implementation reuses the canonical locks, authorization decision, evidence, idempotency, limiter, and route-owned commit paths. |
| test delta | PASS AFTER FIXES | none | Assertions were strengthened around lock observation, exact row snapshots, privacy, replay, and denial rather than relaxed to fit the code. |

## Findings Resolved

Valid findings addressed: yes

Open sub-agent sessions: none

QA's four initial proof findings were repaired by observing PostgreSQL lock
waits, asserting exact mixed-race final state, comparing complete rollback row
snapshots, and binding denial/replay timestamp behavior. Architecture and docs
findings added the immutable merge intent, retired fixed future migration
reservations, and aligned the public specification and data model. The
contributor-foundation contract was narrowed to exact files and lifecycle
guards. ART-main integration review corrected the exact 15-plus-2 action
arithmetic and strengthened deterministic rejection of retired AUTH and ART
state wording. Final test-delta review at `ab6669eb` confirmed that the CI
repair covers five real public route outcomes without production or threshold
changes.

## Remaining Risk And Gate

External GitHub Backend, Agent Gates, CodeRabbit, and explicit human review
remain. This chunk does not add fixed-service admission, grants, feature action
activation, or the contributor-field migration.

`WS-AUTH-001-CONTRIBUTOR-FOUNDATION` remains inactive until this chunk merges,
trusted-main automation records signed memory, and the user explicitly starts
it. Do not start the foundation, AUTH-09E, or another initiative automatically.
