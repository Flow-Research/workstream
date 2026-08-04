# WS-ART-001-04A1 Internal Review Evidence

## Evidence gate

Result: PASS.

- Scope stayed within the removal-only chunk. No route, ZIP parser, submission,
  checker-policy, review, provider, or AUTH activation was added.
- Ruff passed across `backend/app`, `backend/tests`, and `backend/scripts`.
- PostgreSQL proof passed for the exact empty upgrade/downgrade and all six
  populated refusal predicates. The final enriched refusal snapshot also
  preserves physical schema, foreign keys, indexes, row identifiers, and row
  values.
- The focused surviving ART paths passed: 59 admission/recovery/verification
  tests before review corrections, followed by 64 migration, architecture,
  authorization, checker lifecycle, and task-scoped recovery tests after the
  corrections.
- After hosted CI exposed missing submission lineage in the replacement
  checker-output operator fixture, the corrected operator/recovery pair passed
  all 15 tests.
- Stale artifact/auth/wording scans, Markdown links, and `git diff --check`
  passed. No dependency, workflow, coverage-threshold, or package-script change
  was made.

## Reviewer results

- Architecture: PASS after exact downgrade-schema correction.
- Security/auth: PASS.
- QA: PASS after checker-output, OpenAPI, SQL, and refusal-state proofs.
- Product/operations: PASS after operator migration guidance.
- Senior engineering: PASS after stale fixture and downgrade correction.
- CI integrity: PASS with no workflow, threshold, script, skip, or dependency
  weakening.
- Documentation: PASS.
- Reuse/dedup: PASS with one non-blocking test-helper locality risk.
- Test delta: PASS after restoring task-scoped checker recovery and after-I/O
  stale-race coverage.

## Findings resolved

- Recreated legacy timestamps are non-null with their predecessor defaults.
- Downgrade comparison now covers the relevant physical schema, not only table
  names.
- The stale `_AdmissionFacts.upload_item_id` fixture was removed.
- Checker-output put, verified, missing, integrity-mismatch, and recovery paths
  replace generic coverage formerly carried by contributor fixtures.
- Direct SQL cannot relabel a put attempt as contributor or downgrade a receipt
  to contract version 1.
- Canonical decisions and operator guidance no longer describe upload items as
  current runtime state.
- Every operator recovery request backed by the replacement checker-output
  fixture now carries its canonical submission identity.

## Residual risk

The recovery test imports one private checker-admission helper from another ART
test module. Review found no existing shared helper and treated this as low,
non-blocking locality debt. Move it only if another consumer appears.
