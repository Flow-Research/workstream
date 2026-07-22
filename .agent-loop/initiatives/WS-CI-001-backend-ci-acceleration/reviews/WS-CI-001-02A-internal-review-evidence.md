# Internal Review Evidence

## Chunk

`WS-CI-001-02A` — Safe Migrate-Once Database Reset

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: cf91bb81ac44e9ff9cbdc0f8b924959ee1a0554e

Reviewed at: 2026-07-22T14:22:45Z

Reviewer run IDs: eng006_senior_arch_docs, eng006_qa_ci_tests, eng006_security_ops_reuse

After the reviewed SHA, only review evidence, status, and trust-bundle files
changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Full hosted Backend and coverage evidence remains required. |
| QA/test | PASS | None | Exact collection is 1,888 baseline plus 29 reset tests; hosted proof remains required. |
| security/auth | PASS | None | Custody, schema drift, rollback, and destructive boundaries pass. |
| product/ops | PASS | None | Product behavior is unchanged and contributor attribution is preserved. |
| architecture | PASS | None | Generic namespace inventory closed the last schema-object gap. |
| CI integrity | PASS | None | No workflow, runner, coverage-command, or threshold change; hosted gates remain blocking. |
| docs | PASS | None | Status, evidence, and trust bundle describe the bounded implementation. |
| reuse/dedup | PASS | None | The canonical isolated runner and one reset inventory remain authoritative. |
| test delta | PASS | None | No removed, skipped, deselected, or weakened tests; hosted completion remains required. |

## Valid Findings Addressed

- Rejected destructive reset targets unless the URL and live PostgreSQL state
  prove an isolated loopback database owned by its exact least-privileged role.
- Replaced dynamic table discovery with reviewed protected and resettable
  inventories, including all seven trigger-guarded tables.
- Bound reset to an exact migrated-schema fingerprint covering direct public
  namespace membership and detailed structural and executable definitions.
- Added fail-closed tests for unexpected tables, functions, composite types,
  collations, columns, and triggers, proving rejection occurs before mutation.
- Proved repeated reset, exception, cancellation, and real termination preserve
  protected state and restore every guarded trigger.
- Replaced schema-contract teardown's marker-trusting upgrade with a full
  custody-checked rebuild so migration tests cannot poison later shard tests.
- Removed the obsolete, uncalled `include_canonical_actors` reset keyword after
  CodeRabbit identified that it no longer represented behavior.
- Marked all four migration mutators outside `test_alembic.py`, added static
  ownership guidance, and made runtime teardown detect, attribute, recover, and
  preserve errors for hidden schema drift.
- Restored exact Boolean assertions and preserved the trusted-main collection.

## Evidence

- `ruff check tests/conftest.py tests/test_database_reset.py`: passed.
- Isolated reset suite: 27 passed on a freshly migrated database.
- Focused schema-contract-to-ordinary-test ordering proof: 2 passed.
- Runtime hidden-drift detection and recovery proof: passed.
- Isolated runner suite: 16 passed.
- Collection: 1,917 tests, exactly 1,888 trusted-main tests plus 29 reset tests.
- Agent gates: 95 passed.
- `git diff --check`: passed.

## Remaining Hosted Conditions

- The unchanged GitHub Backend job must pass the complete 1,917-test suite on
  the PR head; local machine timing is not performance evidence.
- Hosted PostgreSQL must reproduce the committed canonical schema fingerprint.
- The unchanged global 78 percent and every protected 90 percent coverage gate
  must pass before merge readiness is reported.
