# Chunk Contract: WS-CON-001-03B - Contribution Policy Persistence

## Goal and risk

Persist `ContributionPolicy`, immutable versions, exact rules, award
definitions, and one-active-policy-per-project without commands. L1 economic/
data risk.

This chunk follows `03A`. Its published immutable
`ContributionPolicyVersion` identity is the non-null foreign-key target needed
by REV `03A2` lease/policy-freeze persistence; it does not implement REV rows.

## Allowed files

```text
backend/app/modules/contributions/{__init__,models,schemas,repository}.py
backend/app/modules/projects/models.py only contribution-policy relationship
backend/app/db/models.py
backend/alembic/versions/<next>_contribution_policy.py
backend/tests/{test_contributions,test_projects,test_alembic}.py
backend/tests/conftest.py only canonical reset table inventory and schema fingerprint
.github/workflows/backend.yml only fixed contribution subsystem coverage gate
backend/scripts/run_test_lanes.py only assign test_contributions to shared_foundations
docs/spec_contribution_compensation.md only configured-unit persistence clarification
docs/architecture_data_model.md only configured-unit persistence clarification
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
```

## Not allowed

```text
service, route, claim, award result, adapter execution, AUTH or ART behavior
legacy fallback, alias, automatic conversion, or historical-row rewrite
public API, background executor, dependency or CI weakening
```

## Acceptance criteria

- [x] One active ContributionPolicy per project points to one same-project
  published immutable ContributionPolicyVersion.
- [x] Every publishable version has exactly one accepted_submission and one
  completed_review ContributionRule; each is unpaid or compensated. PostgreSQL
  deferred validation enforces the complete graph before a published version
  or active selector can commit; repository validation is not sufficient.
- [x] Unpaid rules have no definition. Compensated rules have at least one and
  at most two ContributionAwardDefinitions: at most one money and at most one
  project_points definition. Money units are uppercase project-enabled ISO 4217
  codes; project-points units have `(project_id, unit_code)` identity. Every
  definition matches its rule's project, version, contribution type, and unit,
  and its adapter binding matches project and instrument.
- [x] PostgreSQL rejects updates/deletes to published or retired versions and
  their rules/definitions; missing policy has no fallback. Focused PostgreSQL
  tests prove that child rows cannot rewrite published economic truth.
- [x] Composite PostgreSQL keys prove same-project policy/version/rule/
  definition lineage, expose stable `(version_id, project_id)` targets for
  future REV freezes, and bind definitions to 03A ownership by
  `(adapter_binding_id, project_id, instrument_type)`.
- [x] Quantities use `NUMERIC(38,18)` and closed Pydantic decimal-string
  validation with identical bounds. Float inputs, leading plus signs, exponent
  notation, non-finite values, zero, negatives, overflow, excess precision,
  and rounding are rejected.
- [x] PostgreSQL stores the unrounded numeric input and applies the exact
  `NUMERIC(38,18)` value envelope explicitly before persistence, avoiding
  PostgreSQL typemod rounding; project-points quantities are whole numbers.
- [x] A migration-owned immutable ISO 4217 List One registry and project-owned
  compensation-unit rows make money enablement and `(project_id, unit_code)`
  points identity durable; definitions use a composite unit foreign key.
- [x] Legacy classification follows D10/CON-05 and rewrites no history.
- [x] Upgrade/downgrade and selector/version races use isolated PostgreSQL.
- [x] Isolated PostgreSQL proves concurrent active-selector and publishability
  races cannot commit an invalid or mixed policy graph.
- [x] The migration is allocated from the then-current single head and exposes
  a stable owner contract for the later REV foreign key.

## Verification and reviewers

Execute CON-03B in `../RUNTIME_VERIFICATION.md`; changed subsystems are at least
90 percent. Required tracks: senior, QA, security, product, architecture, docs,
reuse, and test-delta. Stop after schema.
