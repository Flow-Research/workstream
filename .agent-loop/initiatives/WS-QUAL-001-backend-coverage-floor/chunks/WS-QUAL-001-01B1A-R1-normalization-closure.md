# Chunk Contract: WS-QUAL-001-01B1A-R1 Normalization Closure

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: stopped at `c0fa4a2` after an additional valid finding; superseded by
01B1A-R2. Retain this contract as review history and do not resume it.

## Goal And Reason

Publish the complete 01B1A parser candidate after closing exactly the two
normalization bypasses recorded by final QA/security review. This replacement
resets the repair loop with explicit known scope; it does not reopen the
superseded candidate for an unbounded third repair.

Risk: L1 test-policy integrity. SLA: P1.

## Scope And Budget

Allowed implementation files: `backend/scripts/coverage_policy.py`,
`backend/tests/test_coverage_contract.py`, and existing 01B1A runbook text in
`docs/operations_backend_testing.md`; WS-QUAL/global memory and reviews are
allowed process evidence.

Forbidden: any parser redesign beyond the two named fixes, semantic Git/delta
guards, 01B1B/01B2 behavior, live config/workflow/evidence changes,
`backend/app/**`, database runner, API, product/auth behavior, skips/xfails,
coverage exclusions/pragmas, or coverage-raising tests.

The complete replacement candidate remains capped at 400 implementation lines
from merge base. Stop and replan immediately above 400 or on any additional
valid finding beyond the two named fixes.

## Acceptance Criteria

- Normalize the stripped PEP 508 requirement name with collapsed `[-_.]+` and
  reject leading-space/case/repeated-punctuation duplicates of pytest-cov while
  accepting exactly one literal `pytest-cov==7.1.0`.
- Token-aware application comment validation rejects coverage-recognized
  `pragma:nocover` and `pragma: nocover` forms in addition to existing
  case/colon/spacing forms, while inert strings/docstrings remain accepted.
- Preserve all 01B1A parser, arithmetic, schema, credential, inventory,
  read-only CLI, scope, and 400-line behavior evidence.

## Verification And Review

Run the full 01B1A contract command set, including exact merge-base scope and
400-line accounting. Required reviewers: senior engineering, QA/test,
security/auth, product/ops, architecture, CI integrity, docs, reuse/dedup, and
test delta. Human focus: only the two recorded bypasses, preservation of prior
parser proof, and no B1B/B2/AUTH spill.

Stop after this corrective chunk. Do not start 01B1B, 01B2, or chunk 02.
