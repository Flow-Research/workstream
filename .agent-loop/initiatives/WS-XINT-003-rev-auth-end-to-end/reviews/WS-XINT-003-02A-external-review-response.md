# External Review Response: WS-XINT-003-02A

## Comments addressed

- CodeRabbit's active-guide fixture finding was valid. The fixture now creates
  a draft, persists both exact selections, and activates in the final guarded
  step; the hosted regression subsequently passed.
- CodeRabbit's policy-hash finding was valid as ORM metadata drift. Review and
  revision model metadata now mirror migration 0046's existing identity-shape
  checks for positive generation, canonical SHA-256 digest, and closed semantics
  status. No duplicate database constraint was introduced.
- CodeRabbit's row-lock finding was valid. Joined review/revision lookups now
  lock only the selected policy row through `FOR UPDATE OF`, avoiding needless
  ProjectGuide contention.
- CodeRabbit's test-helper duplication finding was valid. One merged semantics
  mapping now feeds both digest validation and persistence, preventing duplicate
  keyword failure and digest/row drift.
- CodeRabbit's post-merge migration-test cleanup finding was valid. The initial
  downgrade now runs inside the protected cleanup block, and engine disposal is
  guarded so a partial downgrade failure still attempts restoration to head.

## Comments deferred

None. The generated description/docstring warnings were stale advisory output:
the PR uses the repository trust bundle and hosted docstring coverage passed.

## Human decisions needed

None beyond the repository-required human merge decision.

## Commands rerun

- Ruff for application, tests, and scripts.
- Focused policy-lineage, project activation, lock-scope/helper, and artifact
  fixture tests.
- Schema fingerprint and migration checks as part of exact-head hosted Backend.
- Authorization/artifact/wording/review-contract/Markdown-link checks.

## Remaining risks

Exact-head Agent Gates, Backend, and CodeRabbit must remain green; the external
comments are verified against and resolved in the current diff.
