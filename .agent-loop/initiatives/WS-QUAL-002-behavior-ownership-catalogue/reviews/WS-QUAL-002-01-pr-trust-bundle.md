# PR Trust Bundle: WS-QUAL-002-01

## Chunk

`WS-QUAL-002-01` — Behavior Ownership Catalogue Foundation.

## Goal And Human-Approved Intent

Add one versioned catalogue contract, exact eligible-target partition, and
deterministic read-only generator/validator without activating mutation CI or
changing Workstream product behavior. The human separately approved the narrow
contract correction that assigns the new focused test module to the existing
`shared_foundations` lane.

## What Changed And Why

- Added the schema separating `candidate`, `reviewed`, and strict
  `structural_only` records.
- Added the canonical digest-bound partition assigning every eligible target to
  exactly one population group.
- Added deterministic inventory, non-authoritative candidate generation,
  validation, exact pytest collection, and optional exact owned-test execution.
- Added fail-closed custody, symlink, path, schema, callable, test, remap,
  carry-forward, structural-side-effect, identity, and effective-owner checks.
- Added contributor and backend-testing documentation plus a real reviewed
  example.

## Design Chosen

The tooling delegates eligibility, safe paths, callable spans, changed-callable
derivation, outcomes, boundaries, and test-node syntax to
`backend/scripts/mutation_policy.py`. Candidate inference is structurally
non-authoritative. Protected records remain byte-identical or resolve through
exactly one reviewed, evidence-preserving remap. The initial empty catalogue is
reported as incomplete rather than promoted or blocked.

## Alternatives Rejected

No wildcard/group inference authority, branch-local partition replacement,
callable-wide mutation activation, inferred reviewed ownership, free-form
structural exemption, parallel AST implementation, or workflow change.

## Scope Control And Product Behavior

All files are within the approved contract plus the human-approved single lane
assignment. No `.github/workflows/**`, backend application module, migration,
coverage floor, timeout, skip, deselection, product review decision,
authorization rule, payment, reputation, or `ContributionRecord` behavior
changed.

## Acceptance Proof And Tests

- 49 focused tests pass.
- `scripts.behavior_ownership` focused coverage is 91.30 percent, above 90.
- 33 semantic-lane contract tests pass.
- Ruff passes for all touched backend Python files.
- Real validation reports 176 unresolved targets and `complete: false`.
- Candidate generation remains `authoritative: false`, emits no empty-callable
  candidate, and separates structural-review targets.
- Markdown links pass; stale wording passed during product/operations review.

## Test Delta And CI Integrity

One focused test module was added and assigned to `shared_foundations`. No test
was removed, skipped, deselected, weakened, or moved between existing lanes. No
workflow, coverage threshold, package configuration, or required-check behavior
changed.

## Reviewer Results

- Architecture: PASS.
- Senior engineering: PASS after typed non-reviewed supersession and physical
  group-directory enforcement.
- QA: PASS after current callable-owner uniqueness.
- Security: PASS after protected deletion and multiple-effective-owner repairs.
- Product/operations: PASS.
- CI integrity: PASS.
- Documentation: PASS after using a real example and documenting strict
  structural exclusions.
- Reuse/deduplication: PASS.
- Test delta: PASS.

## External Review

CodeRabbit and exact-head GitHub checks are pending after PR creation. They
supplement, but do not replace, the internal reviews above.

## Remaining Risks And Follow-Up

The catalogue is intentionally incomplete until population chunks `03A` through
`03D` merge. Context evidence (`02`), completeness integration (`04`), and any
future changed-line mutation reactivation (`05`) remain separate approved
chunks. Mutation enforcement remains retired.

## Human Review Focus

Review candidate-versus-reviewed authority, protected partition bootstrap and
future trusted-base custody, remap carry-forward/effective-owner rules, strict
structural-only behavior, and the single lane assignment.

## Human Merge Ownership

- [x] Intent, scope, and non-goals are explicit.
- [x] Deterministic local evidence passes.
- [x] Required internal reviewers pass.
- [ ] External review findings are addressed.
- [ ] Exact-head GitHub checks pass.
- [ ] The user explicitly approves this PR for merge.
