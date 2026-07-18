# Workstream PR Trust Bundle

## Chunk

`WS-QUAL-001-01B1A-R2` - Canonical Coverage Grammar

PR: `https://github.com/Flow-Research/workstream/pull/105`

## Goal And Human-Approved Intent

Create the read-only parser/arithmetic foundation for the repository-wide 90
percent backend coverage policy. The user approved finishing coverage behavior
proof in parallel with isolated AUTH work.

## What Changed And Why

- Added complete-app coverage JSON inventory and arithmetic validation.
- Added intended config, canonical evidence, and runner metadata parsers.
- Added a compute-only CLI that prints an exact candidate floor and writes
  nothing.
- Added 58 genuine behavior cases for malformed, adversarial, boundary, secret,
  provenance, and read-only outcomes.
- Reused coverage.py's installed canonical exclusion grammar after approximate
  regexes produced both bypasses and false positives.

## Design And Alternatives

The parser core is separate from Git semantic-delta enforcement and later CI
publication. Rejected alternatives were raw-text pragma scans, approximate
coverage regexes, narrowed app inventory, exclusions, and percentage-only tests.

## Scope Control

Allowed implementation files changed:

- `backend/scripts/coverage_policy.py`
- `backend/tests/test_coverage_contract.py`
- `docs/operations_backend_testing.md`

Process artifacts changed only under WS-QUAL and global loop memory. No
application, live config, workflow, committed baseline evidence, database,
API, product, or AUTH implementation changed. Complete implementation delta:
398/400 lines from base `8829a7e`.

## Acceptance Criteria Proof

- [x] Complete app inventory reconciles per-file and top-level counts.
- [x] Exact integer arithmetic covers 0, 100, repeating, truncation, and huge counts.
- [x] Config parsing rejects malformed tables, non-exact pins, selectors, exclusions, and invalid floors.
- [x] Evidence and metadata enforce bounded schema, SHA, version, DB, Alembic, arithmetic, and credential rules.
- [x] Comment-token validation matches the installed coverage runtime exactly.
- [x] CLI behavior is stable, read-only, evidence-free, and non-Postgres.

## Tests And CI Integrity

```text
58 focused behavior tests passed
Ruff passed for app, tests, and scripts
pip check passed
coverage.py 7.15.0 recorded
exact scope and 398/400 cap passed
wording, auth-doc, Markdown-link, and diff checks passed
```

Tests are additive. No skip, xfail, assertion deletion, selection narrowing,
coverage pragma, live floor, workflow, or package-script weakening was added.

## Reviewer Results

All required internal tracks passed at evidence head
`84082c6025617ea599ae37cda65291e1ffa07421`: senior engineering, QA/test,
security/auth, product/ops, architecture, CI integrity, docs, reuse/dedup, and
test delta. Internal evidence:
`WS-QUAL-001-01B1A-R2-internal-review-evidence.md`.

## External Review

Pending GitHub checks, CodeRabbit, and human review.

## Remaining Risks And Follow-Up

- The installed coverage.py version is not exactly pinned; 01B2 owns committed
  version evidence and CI publication.
- 01B1B and 01B2 remain inactive until their independent merge-memory-start
  checkpoints.
- The measured whole-app baseline remains 79.25 percent; later behavior-test
  chunks must reach the permanent 90 percent floor.

## Human Review Focus

- Fail-closed schema and config behavior.
- Same-runtime coverage pragma parity.
- Genuine arithmetic/inventory assertions rather than percentage chasing.
- No early semantic-delta, CI publication, or AUTH scope.

## Human Merge Ownership

- [x] Intent, design, scope, tests, and remaining risks are documented.
- [x] Required internal reviewers passed.
- [ ] External checks passed.
- [ ] The user explicitly approved this specific PR for merge.
