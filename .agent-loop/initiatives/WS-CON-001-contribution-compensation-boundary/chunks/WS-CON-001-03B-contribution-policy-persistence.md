# Chunk Contract: WS-CON-001-03B - Contribution Policy Persistence

## Goal and risk

Persist `ContributionPolicy`, immutable versions, exact rules, award
definitions, and one-active-policy-per-project without commands. L1 economic/
data risk.

## Allowed files

```text
backend/app/modules/contributions/{models,schemas,repository}.py
backend/app/modules/projects/models.py only contribution-policy relationship
backend/app/db/models.py
backend/alembic/versions/<next>_contribution_policy.py
backend/tests/{test_contributions,test_projects,test_alembic}.py
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-03B.json
```

## Not allowed

```text
service, route, claim, award result, adapter execution, AUTH or ART behavior
legacy fallback, alias, automatic conversion, or historical-row rewrite
public API, background executor, dependency or CI weakening
```

## Acceptance criteria

- [ ] One active ContributionPolicy per project points to one same-project
  published immutable ContributionPolicyVersion.
- [ ] Every publishable version has exactly one accepted_submission and one
  completed_review ContributionRule; each is unpaid or compensated.
- [ ] Unpaid rules have no definition. Compensated rules have at least one and
  at most two ContributionAwardDefinitions: at most one money and at most one
  project_points definition, each with exact positive decimal/unit/binding/
  provenance constraints.
- [ ] Published/retired content is immutable; missing policy has no fallback.
- [ ] Legacy classification follows D2/CON-05 and rewrites no history.
- [ ] Upgrade/downgrade and selector/version races use isolated PostgreSQL.

## Verification and reviewers

Execute CON-03B in `../RUNTIME_VERIFICATION.md`; changed subsystems are at least
90 percent. Required tracks: senior, QA, security, product, architecture, docs,
reuse, and test-delta. Stop after schema.
