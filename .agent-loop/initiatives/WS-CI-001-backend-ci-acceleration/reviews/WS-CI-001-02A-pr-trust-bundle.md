# PR Trust Bundle

## Chunk

`WS-CI-001-02A` — Safe Migrate-Once Database Reset

Merge intent: `.agent-loop/merge-intents/WS-CI-001-02A.json`

## Goal

Adopt Konan's migrate-once fixture work while proving that every destructive
reset is confined to an exact runner-owned database and reviewed schema.

## What Changed

- Migrated selected backend fixtures to one migration followed by transactional
  database resets.
- Added live database and role custody checks before any destructive action.
- Added exact protected/resettable inventories and a canonical full-schema
  fingerprint, including generic public namespace-object membership.
- Added rollback, signal, repeated-reset, and adversarial schema-drift tests.
- Made explicitly marked whole-schema migration tests rebuild from blank,
  custody-checked schema state in both setup and teardown.
- Preserved exact assertions, existing test collection, coverage thresholds,
  workflows, runner topology, product code, and migrations.

## Scope and Attribution

The implementation stays within the signed 02A allowlist. The adopted source
work is preserved in commit `58125242` with Konan as author; subsequent commits
are bounded safety and review repairs. No workflow or product behavior changed.

## Acceptance Evidence

- Fresh isolated reset suite: 27 passed.
- Exact collection: 1,915 tests, equal to 1,888 on trusted main plus 27 new
  reset tests; no existing node was lost.
- Rerun, exception, cancellation, and SIGTERM paths preserve Alembic and actor
  migration state and leave all seven guarded triggers enabled.
- Unexpected table, function, type, collation, column, and trigger drift fails
  before reset and remains present after rejection.
- 95 agent gate tests and diff integrity passed.

## CI Integrity

- [x] No workflow, shard, lane, runner, or coverage command changed
- [x] No test was skipped, deselected, removed, or weakened
- [x] Global 78 percent and all protected 90 percent floors remain blocking
- [ ] Full GitHub Backend workflow passes the exact PR head
- [ ] Hosted PostgreSQL reproduces the canonical schema fingerprint

## Internal Review

Reviewed code SHA: 18a8c7f2d81a28e58144e8a98f0998539f06bd39

Reviewed at: 2026-07-22T13:52:38Z

Reviewer run IDs: eng006_senior_arch_docs, eng006_qa_ci_tests, eng006_security_ops_reuse

Senior/architecture and QA/CI/test-delta passed after the hosted ordering repair,
with only hosted evidence conditions. Security/auth, product/ops, reuse/dedup,
and documentation passed without a code blocker. All valid internal findings
were repaired.

## Remaining Risk and Human Review Focus

The fingerprint intentionally binds PostgreSQL catalog definitions, so the
hosted PostgreSQL run is the portability proof. Review database/role custody,
schema fingerprint completeness, rollback restoration, exact test delta, and
Konan's preserved attribution.

Local duration is not used to claim performance success. Only the complete
GitHub Backend job and all coverage gates determine acceptance.

## Follow-up

Do not start `WS-CI-001-02B` automatically. After this PR merges and signed
memory reconciles, it remains a same-initiative successor requiring explicit
start.

## Human Merge Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
