# WS-QUAL-001-04M PR Trust Bundle

## Chunk

`WS-QUAL-001-04M` — Changed-Scope Mutation Pilot (L1).

## Goal and approved intent

Measure whether one protected, pinned mutation engine can provide useful,
bounded, exact-head behavior evidence before any mutation result becomes a
blocking contributor policy.

## What changed and why

- Added deterministic changed-target and typed behavior-ownership policy.
- Extracted policy-free Git delta mechanics shared with the agent gate.
- Added a protected-base, read-only, independent Mutation Pilot workflow.
- Added complete result evidence, strong/weak calibration, focused tests, and
  operator documentation.

Coverage proves execution but not assertion sensitivity. This pilot measures
test sensitivity, noise, selection integrity, supply-chain custody, and runtime.

## Design chosen

Every eligible changed target requires a schema-v1 ownership record naming its
qualified callables, exact pytest nodes, observable outcomes, and essential real
boundaries. The workflow installs only the protected base-revision hash-locked
toolchain, rejects special archive entries, and runs baseline tests and exact
callable mutations in a disposable archive. Scores are observational; custody,
baseline, configuration, timeout, and evidence failures remain blocking.

Rejected alternatives: full-backend mutation, uncalibrated score gating,
PR-selected dependencies, mutable exclusion prose, and mutation in the
contributor checkout.

## Scope and product behavior

No application, migration, product lifecycle, authorization, payment,
reputation, Backend semantic-lane, coverage-floor, or existing test-inventory
behavior changes. `backend/uv.lock` and the protected mutation manifest remain
unchanged. Workstream product review decisions remain `accept`,
`needs_revision`, and `reject`; mutation evidence is engineering process proof.

## Acceptance proof

- Focused policy tests: 39 passed; 90.11-percent module coverage.
- Shared Git primitive and workflow invariants: 12 tests passed.
- Exact rebased pilot: 1,091 generated = 84 killed + 59 survived + 948
  excluded; zero timeout, suspicious, or error; 254.672 seconds.
- Strong calibration killed two representative mutants; weak calibration left
  two representative mutants alive.
- Schema/YAML, Ruff, links, stale scans, and diff checks passed.

## Test delta and CI integrity

No test was removed, skipped, xfailed, deselected, or weakened. The intentional
weak calibration is isolated and required to leave a representative survivor.
Existing Backend and its 78-percent global and protected 90-percent floors are
unchanged. The pilot is independent, read-only, SHA-pinned, credential-safe,
bounded to a 15-minute job/12-minute command, and uploads seven-day evidence.

## Reviewers and external review

Architecture, senior engineering, QA, security, product/ops, CI integrity,
docs, reuse/dedup, and test-delta internal tracks pass after valid findings were
fixed. CodeRabbit and GitHub Actions remain external checks after publication;
their findings are not predeclared complete.

## Remaining risks and follow-up

Hosted runtime and platform behavior must be confirmed on the final PR head.
Equivalent/excluded survivors require human calibration before any blocking
policy. `WS-QUAL-001-05M` is not started or pre-approved by this chunk.

## Human review focus and merge ownership

- Confirm protected-base dependency custody and untrusted PR isolation.
- Confirm target ownership and callable filtering cannot omit changed behavior.
- Inspect hosted runtime and complete outcome reconciliation.
- Confirm no mutation score or existing CI weakening was introduced.

Only the user may approve this specific PR for merge. After merge, stop at the
human calibration checkpoint; do not start `05M` automatically.
