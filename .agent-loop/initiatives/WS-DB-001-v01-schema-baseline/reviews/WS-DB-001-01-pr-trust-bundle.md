# WS-DB-001-01 PR Trust Bundle

## Intent and scope

Reset the unreleased v0.1 development migration graph to one authoritative
Alembic baseline while preserving the exact current schema, reference data,
security behavior, and application contracts. Historical revisions and their
migration-only tooling are removed; existing databases are not upgraded through
the deleted graph.

## Design

- One root/head revision installs deterministic schema and reference-data SQL.
- Canonical manifests prove the baseline against the pre-reset schema, with one
  explicit sequence-state delta.
- Fresh empty databases are supported; old stamps and nonempty schemas fail
  closed; downgrade is unsupported.
- Product behavior, authorization, module-boundary, and coverage tests remain in
  the parallel hosted lanes.

## Verification and review

- Alembic reports exactly one root/head.
- Focused baseline, reset, behavior-ownership, authorization documentation, and
  test-structure tests pass locally.
- Ruff, boundary checks, stale-wording scan, markdown-link checks, and diff
  whitespace checks pass locally.
- Required architecture, security, QA, test-delta, CI-integrity, reuse, senior,
  and documentation reviews have no unresolved valid finding.
- CodeRabbit has no actionable thread; its automated review is service-limited
  by the atomic clean-cut file count.

## Human review focus

- Confirm the clean-cut policy: recreate development databases and require a
  separately reviewed forward remediation for any pre-v0.1 production data.
- Confirm the deterministic schema/reference manifests and approved sequence
  delta represent the intended v0.1 database.
- Confirm no removed migration-only workflow remains presented as current.

## Remaining gate

All exact-head GitHub Actions lanes and the aggregate coverage job must pass
before merge.
