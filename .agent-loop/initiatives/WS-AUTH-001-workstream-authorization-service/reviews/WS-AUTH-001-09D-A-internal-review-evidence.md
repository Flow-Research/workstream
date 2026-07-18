# WS-AUTH-001-09D-A Internal Review Evidence

Reviewed code SHA: `7c33e6453a2c91256c8fd416c63e30b95fd9d825`

Reviewed implementation SHA: `7c33e6453a2c91256c8fd416c63e30b95fd9d825`

Reviewed against trusted main:
`f18b620932bb257dc1dc355bc0504271813dc6b1`

Reviewed at: `2026-07-18T18:08:51Z`

Reviewer run IDs: `auth_xint_roles`, `auth_xint_rev_con`,
`auth_xint_art_service`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, migration/data integrity, CI integrity, docs, reuse/dedup, and
test delta

## Deterministic Evidence

- Migration `0026_actor_profile_lifecycle` is the sole head after trusted ART
  migration `0025`. Five exact upgrade, guard, dirty-row, downgrade, and
  re-upgrade nodes pass in 250.95 seconds on isolated PostgreSQL. The two
  repaired guard and dirty-row nodes pass in 111.55 seconds and prove all 29
  `str.strip()` whitespace code points plus previous-head NBSP refusal.
- The real signed-token lifecycle matrix covers human and fixed-service profile
  suspend, reactivate, and terminal deactivate behavior. It also covers all nine
  injected transaction failure stages with stable 503 responses and no partial
  state, audit, timestamp, or idempotency residue. It passes in 100.36 seconds.
- Ordered races identify each second PostgreSQL connection and observe
  `wait_event_type='Lock'` before releasing the first request. The exact race
  node passes in 140.69 seconds without timing sleeps establishing order.
- Actor branch coverage passes at 90.70 percent. Authorization branch coverage
  passes 110 tests at 91.78 percent, and the lifecycle service is 100 percent
  branch-covered. The external repair changes reason normalization constraints
  and additive behavior proof without changing route or authorization logic.
- The exact catalogue test passes with 65 ActionIds: 15 active and 50 planned.
  Three historical migration nodes affected by the owner split pass in 199.52
  seconds, and all 30 Alembic tests collect without a stale enum error.
- The Backend failure was one historical fixture reset violating the new
  identity-link reactivation guard, followed by 18 Alembic failures and 354
  downstream setup errors. The repaired rollback node and immediately following
  migration node pass together in 110.04 seconds without weakening the original
  revoked, suspended, or deactivated refusal assertions.
- The real HTTP API contract, repository-wide Ruff, stale Workstream and
  authorization scans, Markdown links, all 87 Agent Gates, merge-intent
  validation, and diff integrity pass. No workflow, dependency, threshold,
  exclusion, or skip changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Lifecycle state, transaction ownership, idempotency, rollback, and lock order are coherent. |
| QA/test | PASS AFTER FIXES | none | Additive proof covers every Python whitespace point, all five reason fields, prior-head refusal, and the original lifecycle matrix. |
| security/auth | PASS AFTER FIXES | none | Denials conceal matched-grant internals, target disclosure follows authorization, and fresh reactivation attribution is enforced. |
| product/ops | PASS | none | Authorized administrators can manage exact profiles without admitting service callers or activating link mutations. |
| architecture | PASS AFTER FIXES | none | Central AUTH ownership, route-owned commit, and exact 09D-A/09D-B activation custody remain intact. |
| CI integrity | PASS AFTER FIXES | none | No workflow, dependency, threshold, exclusion, or skip changed; deterministic gates remain intact. |
| docs | PASS AFTER FIXES | none | Supported-runtime wording, specification, operations, trust, and durable state evidence agree. |
| reuse/dedup | PASS | none | Existing AUTH kernel, repositories, evidence, idempotency, and transaction helpers are reused. |
| test delta | PASS AFTER FIXES | none | Tests are additive and behavior-based; no assertion, threshold, or selection was weakened. |

## Findings Resolved

The first QA review found four blockers: denial evidence retained matched-grant
IDs, database guards accepted missing or stale reactivation provenance, the
fixed-service/failure matrix was incomplete, and races did not observe a real
database waiter. All four were repaired and independently re-reviewed.

Architecture/migration review then found two blockers: code-owned activation
custody still named the rejected 09D parent, and migration refusal branches were
not all exercised. Exact child owners and the complete refusal matrix were
added. Final review found four historical Alembic selectors using the removed
parent enum; they now preserve their original include/exclude semantics with
both child owners.

External review then found PostgreSQL's one-argument `btrim` did not match API
`str.strip()` behavior and that exact-head evidence was stale. The database now
captures the 29-point supported-runtime whitespace set in live metadata and
migration `0026`; direct constraint and dirty-upgrade tests prove the boundary.
The canonical reviewer table no longer contains an unrecognized migration row.
Migration/data-integrity review passes outside the canonical table: `0026`
remains the sole head, pre-DDL refusal preserves revision/schema/data, and all
five migration nodes pass. The replacement Backend failure then exposed a
test-only cleanup path that performed an unattributed reactivation. Both history
guards are now disabled only around neutral fixture restoration and re-enabled
in `finally`; all lifecycle provenance is cleared and production guards remain
unchanged. All required tracks pass final exact reviewed head
`7c33e6453a2c91256c8fd416c63e30b95fd9d825`.

Valid findings addressed: yes

Open sub-agent sessions: none

## Remaining Gate

GitHub Backend, Agent Gates, CodeRabbit, and explicit human merge approval are
external gates. `WS-AUTH-001-09D-B` remains inactive until this chunk merges,
trusted-main memory passes, and the user explicitly starts it.
