# WS-QUAL-003-07 — Isolate diagnostic-read behavior and repair masked rejection proof

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: Replace mixed diagnostic-read tests with exact scoped
  composition, digest, delegation and independent rejection proof.

## Intent

Continue the PROJECT test audit after PR #371. Three diagnostic composer tests
(eight expanded cases) remain in `backend/tests/test_projects.py`. Their digest
assertions accept any well-formed hash. Missing-project and foreign-guide checks
reuse an already missing target, masking failure of those guards. The test named
`locks_post_submit_policy_binding` uses only fake rows, not PostgreSQL locks.

No selected behavior is obsolete. Replace weak/mixed proof instead of deleting
needed protection to meet a test-count quota. Keep all real repository, SQL,
transaction, concurrency and authorization-kernel tests unchanged.

## Bounded change

### Allowed

- This record and `OVERVIEW.md`: durable outcome, assertion mapping, remaining risks.
- `backend/tests/test_projects.py`: remove only the three diagnostic composer
  functions, `_DiagnosticRepository`, `_DiagnosticAuthorization`, and unused imports.
- `backend/tests/projects/diagnostic_read_fixtures.py`: small controlled rows and
  AsyncMock ports; no database or duplicated evaluator.
- `backend/tests/projects/test_diagnostic_read_composition.py`: exact returned
  row/facts, independent canonical digest expectations and owner-call arguments.
- `backend/tests/projects/test_diagnostic_read_rejections.py`: isolated missing/
  foreign facts, unsupported action, post-submit lineage, authorizer exception.
- `backend/scripts/test_lane_catalogue.py`, `backend/tests/test_ci_lane_catalogue.py`:
  exact PROJECT owner-pair registration and focused workflow-selector regression.
- `.github/workflows/backend.yml`: replace only the three old diagnostic node
  selectors with the two complete new modules; keep policy-read modules and
  coverage source, branch mode, output file and 90% floor unchanged.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: exact inventory reconciliation;
  shrink monolith debt without new or enlarged debt.

### Not allowed

Production, migrations, permissions, routes, dependencies, other workflow steps,
coverage-floor reductions, skips, broad conftest changes, or imports from collected
test modules. Do not change the recorded AUTH concurrency failure in this slice.

## Design and decisions

Use standard AsyncMock ports instead of retaining custom permissive authorization
and catch-all repository methods. Each new rejection starts from fresh valid
project/guide/record facts, then changes one field. Missing project must short
circuit guide/target lookup; foreign guide must short circuit target lookup.
Record-project and record-guide mismatches must conceal the loaded record.

Successful diagnostic actions cover the existing six-action surface. Expected
facts and digest payloads are explicit fixture-owned values, not the production
target-kind map or composition helper used as its own oracle. Capture exact
owner-port arguments separately; that proves delegation, not real row locks.
Retain `get_project(..., for_update=True)` proof from the old fake.

Post-submit setup without output remains a valid diagnostic result. With an
output, bind both run and policy rows; missing policy and each of the five
lineage fields reject independently. Empty diagnostic lists remain authorized
existing collections, not missing resources. Valid-target authorization failure
propagates the same exception; permissive authorization on missing facts still
reaches the composer's fallback RuntimeError.

## Acceptance criteria

| Behavior atom | Named proof | Boundary |
| --- | --- | --- |
| Six actions return the exact selected result and complete facts | `test_diagnostic_read_binds_exact_facts` | Composition |
| Six actions hash the explicit canonical diagnostic rows | `test_diagnostic_read_binds_exact_digest` | Composition |
| Each action delegates exact project/guide/version/target selectors | `test_diagnostic_read_calls_exact_owner_port` | Delegation, not row locking |
| Empty sufficiency/policy collections remain existing targets | `test_empty_diagnostic_collection_remains_readable` | Composition |
| Unsupported action touches neither repository nor authorization | `test_unsupported_diagnostic_action_short_circuits` | Service ordering |
| Missing project, missing guide, foreign guide independently conceal | `test_invalid_diagnostic_parent_conceals_target` | Composer fallback |
| Missing setup run independently conceals | `test_missing_diagnostic_record_is_concealed` | Composer fallback |
| Foreign record project/guide independently conceal | `test_foreign_diagnostic_record_is_concealed` | Composer fallback, not stored tenant isolation |
| Run and attached policy both enter the exact binding digest | `test_post_submit_diagnostic_binds_both_rows` | Composition |
| Missing policy and each project/guide/version/snapshot/hash mismatch reject | `test_post_submit_diagnostic_rejects_invalid_policy` | Composer fallback |
| Valid-target authorizer exception cannot return diagnostic data | `test_diagnostic_read_propagates_authorizer_exception` | Service exception propagation |

Every old assertion maps to equal or stronger proof above. All unrelated test
definitions, decorators and parameter rows stay AST-identical. New modules stay
below 500 lines; tests own one primary behavior, helpers remain below 100 lines.

## Risk and review routing

- L1: authorization-fact proof and hosted focused-gate selection.
- Plan review before implementation: focused guard/oracle/selection feasibility.
- Final QA/test-delta; security/CI-integrity; architecture/reuse reviews.
- Human focus: independent rejection fixtures, exact digest oracle, honest
  fake-versus-database boundary, and no lost baseline behavior.

## Evidence

Run the original eight cases before replacement. Locally run both new modules,
the two retained policy/active-guide modules and catalogue tests; execute the
exact focused 90% branch-coverage command. Run Ruff, debt inventory/validation,
Commitrail, Markdown links, stale scans and diff checks. Hosted CI owns the full
suite, all PostgreSQL proofs, node custody and global/subsystem coverage.

Valid controls must pass. A wrong well-formed digest must pass the old prefix
test but fail the new equality. Bypassing the guide-project guard with a valid
record must fail its rejection test, not a fixture error. Wrong owner selectors
must fail exact call capture. Restoring the stale workflow selector must fail its
command regression. Temporary mutants remain outside Git.

## Review findings

Discovery confirms the masked invalid-parent cases and mislabeled lock proof.
Only the selected controlled-row proof is repaired; no global security or
exhaustive test-audit claim is made.

## Reconciliation

- Current source: main `a9bea2fd`, merged exact policy-read slice 06.
- Next usable boundary: remaining PROJECT mutation tests, then AUTH with its
  recorded intermittent suspension-race diagnosis before routine decomposition.
- Remaining risks: mocked ports do not prove tenant query filters, PostgreSQL
  locks, authorization grants, transaction rollback or stored evidence.
