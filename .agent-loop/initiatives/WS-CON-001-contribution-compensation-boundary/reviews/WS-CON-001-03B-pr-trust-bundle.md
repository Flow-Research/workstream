# PR Trust Bundle: WS-CON-001-03B

## Outcome

Adds migration `0055_contribution_policy` and the SQLAlchemy/Pydantic
foundation for project-scoped contribution policies and immutable published
economic rules.

## Design And Boundaries

- One active policy per project selects one same-policy published version.
- Deferred PostgreSQL validation requires exactly the submission and review
  rules and the correct unpaid/compensated definition graph.
- Composite keys preserve same-project lineage through policy, version, rule,
  configured unit, award definition, and the 03A adapter binding.
- Money uses project-enabled current ISO 4217 codes; project points use a
  project-scoped unit and whole-number quantities.
- Exact numeric input is stored without PostgreSQL typemod rounding and checked
  against the 20-integer/18-fractional-digit envelope.
- Published/retired content, ISO registry rows, unit rows, and table contents
  reject unauthorized mutation, deletion, reparenting, and truncation.
- No command/service/API/AUTH/ART/REV behavior is introduced.

## Verification

- 44 focused isolated PostgreSQL tests passed, including the active-selector
  negative regression.
- Canonical head upgrade/downgrade passed.
- Contribution subsystem coverage is 94.89%.
- Hosted CI enforces at least 90% contribution-subsystem coverage.
- The contribution test module is assigned exactly once to the
  `shared_foundations` semantic lane; lane-integrity tests pass.
- Ruff, diff hygiene, Markdown links, and all applicable stale scans pass.
- Required internal reviewers pass after their valid findings were repaired.

## Human Review Focus

1. Confirm 0055 remains a linear child of AUTH 0054 on the reconciled main head.
2. Confirm deferred graph validation and child locking prevent mixed published
   economic truth.
3. Confirm money/points unit provenance and exact numeric constraints match the
   canonical specification.
4. Confirm 03B remains schema-only and does not claim AUTH, ART, or REV behavior.

## Remaining External Gate

The first hosted project-lifecycle run exposed an import-order failure from an
unnecessary reverse ORM relationship. That relationship was removed without
changing database lineage, and the exact formerly failing project test passes
in isolation. GitHub CI and CodeRabbit must pass on the repaired exact head.
Human merge is required, and no subsequent chunk begins automatically.
