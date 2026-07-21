# WS-AUTH-001-10A Internal Review Evidence

Reviewed code SHA: `184404a0c0744402b2582ce4a3a27c8207bc8cf8`

Reviewed implementation SHA: `e8d9c37e6fd552439ff9f0db8b2972337a3b019f`

Reviewed against trusted main: `70f9c7bcdb63680e545f661a956929379df138e4`

Reviewed at: `2026-07-21T13:37:12Z`

Reviewer run IDs: `auth10_plan_core`, `auth10_plan_security_qa`,
`auth10_plan_ops_ci_docs`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Scope

AUTH-10A adds the project-role qualification and immutable grant data/evidence
foundation only. It adds no route, active action, kernel/PREP behavior, or
callable read/issue/revoke service.

## Deterministic evidence

- Ruff passed for authorization, audit, migration, and focused test files.
- Fresh install and full downgrade passed through migration `0031`.
- Focused PostgreSQL migration tests passed for exact-role coexistence,
  constraints, timestamps, immutability, lifecycle, action/denial parity, every
  upgrade/downgrade refusal predicate, combined blockers, and no-mutation row
  preservation.
- `tests/test_audit.py`: 12 passed.
- Focused typed catalogue/schema tests passed.
- Stale authorization wording, Markdown links, and `git diff --check` passed.
- Full suite, shards, aggregate 78 percent coverage, authorization 90 percent
  coverage, API E2E, and Agent Gates are delegated to GitHub Actions.

One combined local selector was interrupted when the local Postgres container
process segfaulted and recovered. Its product assertions were rerun in isolated
groups successfully; this is not recorded as a passing test run.

## Reviewer Results

All tracks reviewed exact SHA `e8d9c37e` and passed after two repair loops:

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Immutable history, timestamps, refusal preservation, and bounded scope are coherent. |
| QA/test | PASS AFTER FIXES | none | Focused proof reaches every declared migration, ownership, and lifecycle boundary. |
| security/auth | PASS AFTER FIXES | none | Privacy shapes, exact-role ownership, and fail-closed upgrade/downgrade behavior pass. |
| product/ops | PASS | none | Independent roles coexist and no product route or behavior activates. |
| architecture | PASS AFTER FIXES | none | 10A remains data/evidence-only; 10B/10C ownership is preserved. |
| CI integrity | PASS AFTER FIXES | none | Generic round-trip is restored; no workflow, threshold, shard, or script weakened. |
| docs | PASS AFTER FIXES | none | Exact preflight, lock impact, and forward recovery are documented. |
| reuse/dedup | PASS | none | Existing authority, catalogue, audit, and migration conventions are reused. |
| test delta | PASS AFTER FIXES | none | Tests are additive; no assertion, selector, skip, or threshold was weakened. |

The repair loops added database-owned timestamps, truncate guards, ORM/schema
parity, general UUID parity, exhaustive refusal and row-preservation proof,
existing-row composite ownership proof, successful unrelated-history
preservation, and executable operator preflight queries.

Valid findings addressed: yes

Open sub-agent sessions: none

## Remaining external gates

GitHub full CI/coverage, CodeRabbit, and the human checkpoint remain. The user
retains merge ownership.
