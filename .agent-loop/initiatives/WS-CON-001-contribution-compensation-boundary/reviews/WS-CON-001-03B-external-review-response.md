# External Review Response: WS-CON-001-03B

## Comments addressed

- GitHub `project_lifecycle` lane failed because the `Project` mapper named
  `ContributionPolicy` in a reverse ORM relationship even when a project-only
  process had not imported the contributions module. The resulting mapper
  initialization failure cascaded into actor-registry 503 responses.
- Removed the unnecessary bidirectional ORM relationship. Database foreign
  keys and composite same-project lineage remain authoritative and unchanged.

## Comments deferred

- None.

## Human decisions needed

- None beyond normal PR review and merge approval.

## Commands rerun

```text
project-only configure_mappers probe: passed
isolated test_projects.py::test_active_guide_lookup_surfaces_duplicate_rows: passed
Ruff: passed
git diff --check: passed
```

## Remaining risks

GitHub CI and CodeRabbit must complete on the repaired commit.
