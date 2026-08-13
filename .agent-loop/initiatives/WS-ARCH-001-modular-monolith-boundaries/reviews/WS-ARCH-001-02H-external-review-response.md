# WS-ARCH-001-02H External Review Response

## Comments addressed

- Expanded the chunk verification contract to retain the repository-wide 78%
  gate and require 90% coverage for AUTH, ART, and TASK.
- Moved strict Submission creation resource construction inside its owner
  translation boundary and moved fixed-service ART resource construction inside
  the ART translation boundary.
- Changed revoked-link proof to raise the canonical
  `PreparedAuthorizationUnsupported` lifecycle denial before asserting the
  concealed ART error and zero database effect.
- Changed service-matrix proof to use active `project.read`, which the artifact
  binding service does not own.
- Kept 02H under Integration In Progress until the PR merges.
- Split the oversized PostgreSQL proof and extracted new AUTH behavior into
  bounded submission-specific modules. The structural-debt ledger records only
  measured shrinkage and the validator rejects new or growing debt.

## Comments deferred

None.

## Human decisions needed

None.

## Commands rerun

- Focused Ruff checks.
- AUTH module-boundary and behavior-ownership validators.
- AUTH structural-debt validator.
- Stale authorization wording and Markdown-link checks.
- Isolated PostgreSQL focused suites and coverage gates.
- Hosted GitHub Actions exact-head lanes: pending the final pushed correction.

## Remaining risks

The public Submission route remains unchanged and gated by 02I.
