# External Review Response: WS-QUAL-001-01A

## Comments Addressed

- Marked the superseded combined contract's verification block as historical
  and non-executable.
- Scoped the 700-line exception explicitly to 01A and documented 01A's runner,
  guard, CI, and runbook exception to the later tests-only coverage rule.
- Preserved role-aware cleanup after verifying it is required to terminate the
  unique ephemeral role's detached admin-database session before `DROP ROLE`.
  The plan now states the ownership boundary; real Postgres tests prove
  unrelated sessions survive.
- Corrected the runbook to distinguish admin-database provisioning/cleanup from
  isolated application execution and to document host-failure recovery.
- Tightened CI to a 210-minute child deadline inside a 240-minute job deadline.
- Centralized the strict derived database regex in the runner and reused the
  same compiled object in both API drills.
- Replaced generic authority wording after Agent Gates identified
  `GENERIC_ADMIN_PRODUCT_AUTHORITY`.

## Comments Deferred

None. The request to narrow cleanup to `datname` alone was resolved through the
reviewer's offered alternative: explicit justification and behavior proof for
the broader unique-role boundary. Narrowing the query would leak the role when
its session remains on the admin database after the owned database is absent.

## Informational Findings

CodeRabbit reported 34.78 percent docstring coverage by scanning a different
surface. The repository's configured gate scopes `backend/app`; it passed at
100 percent, 928/928 required docstrings. No unrelated script docstrings were
added.

## Commands Rerun

```text
16 runner lifecycle tests passed in 200.74s
14 API guard tests passed
Ruff passed
pip check passed
configured docstring coverage passed at 100% (928/928)
stale authorization documentation check passed
stale Workstream wording check passed
Markdown link check passed for 12 changed files
git diff --check passed
implementation delta: 700/700
strict derived database/role catalog: clean
```

## Remaining Risks

- The provisioned application suite's measured runtime is 3:08:04; the child
  deadline has about 22 minutes of measured headroom.
- Host-level termination can still prevent cleanup and require exact manual
  recovery using strict catalog names.
- Whole-backend coverage remains 79.25 percent; this chunk does not start 01B.
