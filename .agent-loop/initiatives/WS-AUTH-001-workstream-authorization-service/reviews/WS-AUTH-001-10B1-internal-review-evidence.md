# WS-AUTH-001-10B1 Internal Review Evidence

Reviewed code SHA: `746e577adca41d81cc0fbc9ee12dfbab12aac464`

Reviewed against trusted main: `92b8a7aa813c5914d8191547b62eb3823a37a140`

Reviewed at: `2026-07-22T00:30:00Z`

Reviewer run IDs: `auth10b1_final_core`,
`auth10b1_final_security_qa`, and `auth10b1_final_ops_docs_ci`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

Main-integration merge SHA: `3b90fbd7cf3c80c3dcfc199953317492e4ddcd2e`.
The reviewed tree also contains the CodeRabbit-requested PostgreSQL-major
prerequisite and the post-ART migration-lineage reconciliation.

## Scope

AUTH-10B1 adds one closed `authorization_read` scope to the existing durable
PostgreSQL API control, bounded configuration, and an unattached dependency. It
adds no route, action activation, cursor, disclosure, or mutation behavior.

## Deterministic evidence

- Focused isolated selector: PASS, 27 tests; 174 deselected.
- Migration/new-scope database proofs: PASS, 4 tests.
- Final old/new-scope concurrent consumption proof: PASS, 2 tests.
- Post-CI migration-head repair proof: PASS, 3 tests together in a fresh
  isolated PostgreSQL database.
- Post-main combined ART/AUTH lineage proof: PASS, 3 tests in a fresh isolated
  PostgreSQL database.
- Alembic heads: PASS, exactly `0033_authorization_read_rate`.
- Dependency and digest proofs: PASS, 6 tests.
- Ruff on all contract-owned Python paths: PASS.
- Agent Gates: PASS, 89 tests.
- Stale authorization documentation: PASS.
- Markdown links: PASS for all changed Markdown files.
- `git diff --check`: PASS.
- Full backend shards, aggregate 78 percent coverage, additive API-controls 90
  percent coverage, migration proof, and API E2E remain GitHub-owned evidence.

## Reviewer results

| Reviewer | Result | Blocking findings |
|---|---|---|
| senior engineering | PASS AFTER FIXES | none |
| QA/test | PASS AFTER FIXES | none |
| security/auth | PASS AFTER FIXES | none |
| product/ops | PASS AFTER FIXES | none |
| architecture | PASS AFTER FIXES | none |
| CI integrity | PASS AFTER FIXES | none |
| docs | PASS AFTER FIXES | none |
| reuse/dedup | PASS AFTER FIXES | none |
| test delta | PASS AFTER FIXES | none |

## Findings resolved

The repair loop added exact fail-closed migration constraint validation and
drift/no-mutation tests, reused the existing scoped writer helper, directly
proved durable new-scope limit/reset/separation/concurrency behavior, moved the
new scope's own 429 and private 503 behavior under test, regression-protected
the additive coverage command, and documented safe constraint-drift recovery.
Old first-access and admin-mutation proofs remain present alongside the new
scope; no test was removed, skipped, or weakened.

GitHub shard 3 initially failed because three pre-existing migration tests
still treated `0031_project_role_grants` as current `head`. The first stale
assertion aborted before test-owned cleanup and caused the remaining downgrade
failures. Repair `a8a0daef` changed those expectations to then-current AUTH
head `0032`. Run `29875491247` exposed two multi-step refusal-state
expectations; repair `8ceb4e16` correctly proved a refusal retains the starting
head. After ART merged `0032_artifact_recovery`, integration merge `3b90fbd7`
rebased AUTH linearly to `0033_authorization_read_rate`. Current-head and
refusal expectations now retain `0033`, while successful AUTH downgrade stops
at direct predecessor ART `0032`. All nine tracks passed on final integrated
implementation/docs SHA `2d6d347e` against main `92b8a7aa`.

## Post-integration CodeRabbit repair

CodeRabbit's preservation finding was repaired in test SHA `746e577a`. The
round-trip now seeds and asserts both legacy scopes through upgrade, refused
downgrade, and successful downgrade. The focused isolated PostgreSQL 16 proof
passed 1/1, and all nine reviewer tracks re-reviewed the one-file delta: senior
engineering, architecture, reuse/dedup, security/auth, QA/test, test delta,
product/ops, docs, and CI integrity all passed with no findings.

Valid findings addressed: yes

Open sub-agent sessions: none after evidence publication

## Remaining gate

GitHub Actions, CodeRabbit, and explicit human review remain. After merge,
signed loop memory must stop at declared successor `WS-AUTH-001-10B2`; it must
not start without a separate explicit event on exact trusted `main`.
