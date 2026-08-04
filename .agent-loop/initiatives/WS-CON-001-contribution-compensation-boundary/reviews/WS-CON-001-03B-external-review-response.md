# External Review Response: WS-CON-001-03B

## Comments addressed

- GitHub `project_lifecycle` lane failed because the `Project` mapper named
  `ContributionPolicy` in a reverse ORM relationship even when a project-only
  process had not imported the contributions module. The resulting mapper
  initialization failure cascaded into actor-registry 503 responses.
- Removed the unnecessary bidirectional ORM relationship. Database foreign
  keys and composite same-project lineage remain authoritative and unchanged.
- CodeRabbit's four actionable findings were accepted: the chunk-map stop
  boundary and contract doc scope are current, migration check-constraint names
  now follow metadata conventions, and the contribution migration round trip no
  longer runs from the shared lane. The canonical partitioned Alembic test
  already proves the same 0054 head downgrade/upgrade path.
- Removed the redundant configured-unit unique index; its composite primary key
  remains the award-definition FK target.

## Comments deferred

- CodeRabbit's whole-history graph-scan performance suggestion is deferred to
  the later command/service chunk. PostgreSQL deferred constraint triggers are
  necessarily row-level, and 03B intentionally favors a complete fail-closed
  validation before scale behavior exists.
- The ISO snapshot remains duplicated deliberately because migrations must be
  immutable and self-contained; a parity test prevents application precheck
  drift. Defensive Decimal post-regex checks remain explicit and harmless.
- Additional policy-input unit cases are optional; the closed validators are
  covered by the 95% subsystem gate and current negative tests.

## Human decisions needed

- None beyond normal PR review and merge approval.

## Commands rerun

```text
project-only configure_mappers probe: passed
isolated test_projects.py::test_active_guide_lookup_surfaces_duplicate_rows: passed
semantic-lane integrity: 33 passed
focused isolated contribution PostgreSQL suite: 44 passed
canonical Alembic head upgrade/downgrade: 1 passed
contribution subsystem coverage: 94.89%
Ruff: passed
git diff --check: passed
```

## Remaining risks

GitHub CI and CodeRabbit must complete on the repaired commit.
