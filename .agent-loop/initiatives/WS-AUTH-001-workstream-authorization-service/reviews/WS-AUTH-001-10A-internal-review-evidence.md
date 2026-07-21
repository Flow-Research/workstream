# WS-AUTH-001-10A Internal Review Evidence

Reviewed code SHA: `3e6ba3dbf265ce287b4f8bf114f3c3081f63f94e`

Reviewed implementation SHA: `e8d9c37e6fd552439ff9f0db8b2972337a3b019f`

Reviewed against trusted main: `dda60ed0cb97d9de4a375df4147f31172cb3839b`

Reviewed at: `2026-07-21T14:01:09Z`

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

All tracks then re-reviewed the exact integrated and repaired SHA `933f17f7`
after trusted main advanced. The integration preserved the reviewed AUTH-10A
implementation byte-for-byte. One new fail-closed validator finding was fixed:
the merge intent successor title now exactly matches the reviewed 10B contract
heading. Senior engineering, architecture, reuse/dedup, security/auth, QA/test,
test delta, product/ops, CI integrity, and docs all passed the repaired SHA.

All tracks also reviewed CI repair SHA `3e6ba3db`. The repair keeps the
historical 0021 action-parity test scoped to actions present at that revision
and extends the transaction-scoped privileged test reset to clear the two new
immutable role-history tables without weakening their production guards. The
dedicated 0031 tests retain proof of all five new action pairs. All tracks
passed with no open finding.

Open sub-agent sessions: none

## Remaining external gates

GitHub full CI/coverage, CodeRabbit, and the human checkpoint remain. The user
retains merge ownership.
