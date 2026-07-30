# WS-AUTH-001-12A External Review Response

External review: CodeRabbit review on PR #226 at head `232996c3`

## Comments addressed

- Replaced the migration placeholder in the allowed-file boundary with the
  exact implemented `0041_project_mutation_action_evidence.py` path. The
  revision identifier remains the separately frozen
  `0041_project_mutation_evidence` value.
- Added `tests/conftest.py` to the chunk's Ruff verification command so every
  changed Python file is covered by the declared lint proof.
- Replaced the tautological `PermissionId` membership assertion with the exact
  four pre-existing permissions used by the eighteen project-mutation actions.
- Documented the migration's intentional dependency on PostgreSQL constraint
  rendering and its fail-closed drift guards.
- Made the project-mutation resource and target-kind maps immutable.
- Hoisted the static admin action-to-resource map out of the authorization hot
  path and froze it.
- Made resource-to-PREP scope derivation explicitly static, removing the test's
  `None` receiver workaround.
- Consolidated repeated setup-service custody checks without changing their
  validation order or error wording.

## Comments deferred

None. All three actionable comments and five collapsed nitpicks were addressed.

## Human decisions needed

None.

## Commands rerun

- `git diff --check`
- Ruff over `tests/test_alembic.py` and `tests/conftest.py`
- Focused authorization tests: `2 passed, 366 deselected`
- The local isolated PostgreSQL runner refused the configured admin database
  with `unsafe_admin_database`; this safety guard was not bypassed, and hosted
  CI owns the isolated migration proof.
- Stale authorization wording, stale Workstream wording, and Markdown-link
  checks

Hosted `Backend / test` and `Agent Gates` are pending on the corrective pushed
head and remain required before merge readiness.

## Remaining risks

The actions remain planned and externally inactive. Runtime activation and
mutation-service integration remain owned by their separately bounded child
chunks.
