# Chunk Contract: WS-QUAL-001-01B1A-R2 Canonical Coverage Grammar

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: implemented within scope; all required implementation-review tracks
passed at code candidate `40ac7a9b5a9319b0fdccef396aa82342b324e4c3`.

## Goal And Scope

Complete the parser candidate by replacing the approximate pragma matcher with
the installed coverage runtime's canonical default exclusion grammar. Preserve
R1's verified requirement normalization and every prior 01B1A behavior.

Risk: L1 test-policy integrity. SLA: P1. Allowed implementation files are
`backend/scripts/coverage_policy.py`, `backend/tests/test_coverage_contract.py`,
and preservation-only 01B1A runbook text. WS-QUAL/global process evidence is
allowed. Every R1 forbidden boundary remains forbidden, including semantic
delta, B1B/B2, live config/workflow/evidence, application, DB, API, product, and
AUTH changes.

The complete candidate remains capped at 400 implementation lines from merge
base. Stop above 400 or on any additional valid finding.

## Acceptance Criteria

- Reuse `coverage.config.DEFAULT_EXCLUDE[0]` from the installed coverage runtime
  selected by the pinned pytest-cov toolchain when inspecting COMMENT tokens;
  do not maintain an approximate pragma regex.
- Reject comments coverage.py recognizes, including compact `pragma:nocover`.
- Accept explanatory comments and substrings that canonical coverage.py does
  not recognize, including `This documentation mentions pragma: no cover` and
  `notapragmanocover`.
- Preserve stripped PEP 508 normalized exact-pin enforcement, inert
  string/docstring behavior, all parser/arithmetic/schema/credential/inventory
  evidence, the read-only CLI, exact scope, and the 400-line cap.

## Verification And Review

Run the complete 01B1A command set, record the resolved coverage.py version,
and run direct equivalence probes against that same runtime's canonical regex.
Required reviewers: senior engineering, QA/test,
security/auth, product/ops, architecture, CI integrity, docs, reuse/dedup, and
test delta. Human focus: exact canonical reuse, false-positive/negative parity,
and no scope expansion.

Stop after R2. Do not start 01B1B, 01B2, or chunk 02.
