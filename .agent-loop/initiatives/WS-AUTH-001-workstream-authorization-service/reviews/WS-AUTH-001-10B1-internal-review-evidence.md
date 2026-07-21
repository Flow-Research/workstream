# WS-AUTH-001-10B1 Internal Review Evidence

Reviewed code SHA: `9b33edea094fa997f03c3a7f7e57ecc9fd20bda8`

Reviewed against trusted main: `1473f7a0cab6d879c7b7c049a9b94f557ad712c2`

Reviewed at: `2026-07-21T23:20:00Z`

Reviewer run IDs: `auth10b1_final_core`,
`auth10b1_final_security_qa`, and `auth10b1_final_ops_docs_ci`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

Executable-code SHA: `8ceb4e16d8e152572c94ad3032d8a2edc2cea55e`;
the reviewed tree SHA additionally contains the CodeRabbit-requested
PostgreSQL-major operations prerequisite and its response record.

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
failures. Repair `a8a0daef` changed those three current-head expectations to
`0032_authorization_read_rate`. Run `29875491247` then exposed two multi-step
refusal-state expectations: refusal inside `0031` rolls back the preceding
`0032` downgrade transaction and retains `0032_authorization_read_rate`.
Repair `8ceb4e16` changes only those two expectations. The successful direct
`0032` to `0031` assertion remains `0031`. A fresh isolated three-test sequence
passed, and all nine tracks re-reviewed exact repair SHA `8ceb4e16` and passed.

Valid findings addressed: yes

Open sub-agent sessions: none after evidence publication

## Remaining gate

GitHub Actions, CodeRabbit, and explicit human review remain. After merge,
signed loop memory must stop at declared successor `WS-AUTH-001-10B2`; it must
not start without a separate explicit event on exact trusted `main`.
