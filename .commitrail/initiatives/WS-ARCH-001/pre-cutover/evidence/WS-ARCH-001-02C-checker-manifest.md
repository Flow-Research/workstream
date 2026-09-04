# WS-ARCH-001-02C CHECKER Public Capability Manifest

## Public surface

`app.modules.checkers.api` exposes only dependency-safe immutable contracts:

- `EffectivePreSubmissionPlanLineage`
- `EffectivePreSubmissionPlanEntry`
- `EffectivePreSubmissionExecutionPlan`
- `EffectivePreSubmissionPlanningPort`
- `PreSubmissionExecutionEntryFacts`
- `PreSubmissionExecutionFacts`
- `SubmissionPacketView`
- stable planning errors and immutable JSON support

The concrete `PreSubmissionCheckerCatalogue` implements the planning port
inside CHECKERS. It remains private and is composed as the runtime
implementation; callers receive no catalogue definition, executor, ORM row,
repository, session, scratch path, provider handle, or mutable policy record.

## Ownership

- TASKS locks task, assignment, predecessor, and project-policy references.
- CHECKERS deterministically compiles the single effective platform-plus-project
  plan from exact immutable lineage and locked policy values.
- CHECKERS projects bounded execution outcomes.
- ART retains prepared-artifact custody, storage scheme, evidence identity,
  evidence persistence, pass capability, and admission attachment.

`PreSubmissionExecutionResult.bounded_facts()` deliberately omits custody,
prepared generation, archive digest and byte count, semantic manifest digest,
storage scheme, scratch state, provider details, and evidence persistence.

## Removed private edges

The exact protected debt removed by this chunk is:

```text
artifacts/submission_admission.py -> checkers/catalogue.py
artifacts/submission_admission.py -> checkers/pre_submit_execution.py
tasks/pre_submit_context.py -> checkers/catalogue.py
tasks/pre_submit_context.py -> checkers/effective_plan.py
```

The touched callers now import only `app.modules.checkers.api`. Other frozen
CHECKER debt is unchanged and remains owned by its later capability chunk.

## Behavior and activation

The existing catalogue, compiler, plan hash, plan ordering, execution path, and
fail-closed validation remain unchanged. This chunk adds no action, permission,
route, durable job, persistence, provider access, or authorization activation.

## Evidence

- Module-boundary protected-base validation passes with all four entries removed.
- Separate focused CHECKER catalogue/effective-plan/submission-admission suites
  pass locally (`61 passed`). The dedicated public planning-port and bounded
  result tests pass (`2 passed`) in a new CHECKER-owned focused file; the frozen
  oversized legacy test file remains unchanged.
- The earlier contract-wide local coverage run reached 94.96 percent for
  `app.modules.checkers.api`, with `75 passed` and one database-backed setup
  error because `WORKSTREAM_TEST_DATABASE_URL` was not configured. The final
  contract command now uses the focused CHECKER test file, and GitHub's isolated
  database lanes own complete database-backed proof before merge readiness.
- Contract tests prove the public API has no private module dependency and the
  public execution result exposes no ART custody field.
