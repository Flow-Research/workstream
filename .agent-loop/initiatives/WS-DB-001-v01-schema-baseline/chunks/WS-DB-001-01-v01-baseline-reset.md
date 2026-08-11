# WS-DB-001-01: v0.1 Baseline Reset

## Intent

Atomically replace all pre-v0.1 development revisions with one exact current
schema baseline. No old database is upgradeable.

## Allowed files

- `backend/alembic/**`
- `backend/migration_contracts/**` for removal of obsolete frozen revisions
- `backend/app/modules/actors/service_identity_migration.py` and
  `backend/scripts/service_actor_identity_mapping.py` for removal only
- `backend/pyproject.toml` only to remove obsolete `migration_contracts`
  packaging configuration
- Migration/schema/catalogue/database-reset tests under `backend/tests/**`
- Migration, isolation, evidence, and lane scripts under `backend/scripts/**`
- `.github/workflows/backend.yml` only if exact lane custody must change
- Current migration/database documentation under `README.md`, `CONTRIBUTING.md`,
  `docs/**`, and this initiative's `.agent-loop/**`
- Structural/test/behavior ledgers only when regenerated from genuine changes

## Not allowed

- Product model, API, permission, action, role, lifecycle, or background-job behavior
- Compatibility stamps, aliases, bridge revisions, dual baselines, or retained
  old revision files
- CI timeout or coverage-floor weakening
- Editing historical review evidence merely to erase old revision names
- Unrelated code cleanup

## Acceptance criteria

1. `backend/alembic/versions/` contains exactly one Python revision,
   `0001_v01_baseline`, with `down_revision = None`.
2. A fresh database reaches the single head and exposes exact current tables,
   columns, keys, checks, indexes, sequences, types, functions, and triggers.
3. The raw normalized source-head manifest and installed-baseline manifest
   differ only by the committed, machine-checked correction that advances the
   two singleton-row sequences past their seeded keys.
4. Canonical authorization catalogue and fixed-service reference rows match
   runtime definitions exactly.
5. Database immutability, append-only, evidence-linkage, and lifecycle guards
   retain behavior proof.
6. Historical intermediate-state/downgrade tests are removed; every current
   invariant has focused replacement proof.
7. Current docs tell developers to recreate old databases and contain no live
   instruction to upgrade through removed revisions.
8. Full hosted Backend and Agent Gates pass without coverage or timeout
   weakening.
9. Before generation, the branch is rebased on current `main`; the source graph
   must contain exactly one head. If it is not the recorded
   `0063_compilation_authority`, source evidence and the baseline are regenerated
   from the new head rather than deleting concurrent work.
10. The root upgrade inspects the target before product DDL and refuses an old,
    stamped, or otherwise non-empty public schema. Tests prove refusal is
    atomic and provides recreate guidance.
11. Root downgrade raises before mutation. A test proves schema and seeded/data
    rows remain unchanged.
12. The committed manifest extractor covers a closed list of PostgreSQL object
    classes and has sentinel tests for each class. Source and baseline manifests
    are committed at
    `backend/alembic/baseline/v01_pre_reset_source_manifest.json` and
    `backend/alembic/baseline/v01_baseline_manifest.json`, with the sole
    approved difference recorded in `v01_approved_manifest_delta.json` and
    compared by the hosted suite.
    Sequence runtime state (`last_value`/`is_called` and equivalent identity
    restart state) is included; seed SQL restores it deterministically and a
    generated-key collision test proves correctness.
13. `MIGRATION_TEST_CUSTODY.md` maps every removed migration test to replacement
    current-invariant proof or an explicit obsolete-intermediate-state reason.
14. No runtime/test/script import of `backend/migration_contracts` or the
    revision-0023 mapping helper remains.
15. Unknown old revision stamps receive recreate guidance through Alembic
    environment preflight in `backend/alembic/env.py`, which reads and validates
    `alembic_version` before `context.run_migrations()` can calculate a revision
    path. No stamp is rewritten or accepted, and rejection leaves schema and
    data unchanged.
16. ACL manifests use only canonical `owner`, `PUBLIC`, and explicitly
    allowlisted stable application-principal names. Unknown grantees fail
    extraction. Baseline installation maps those names to configured target
    roles, and hosted parity tests compare effective privileges under every
    mapped principal rather than comparing role-name text alone.

## Verification commands

Run from the repository root, with the normal local isolated PostgreSQL admin
DSN supplied only through `WORKSTREAM_TEST_ADMIN_DATABASE_URL`:

```text
cd backend && .venv/bin/alembic heads
cd backend && .venv/bin/alembic history
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p pytest_asyncio.plugin tests/test_alembic.py tests/test_database_reset.py tests/test_isolated_database_runner.py
cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main
cd backend && .venv/bin/python -m scripts.authorization_boundary validate --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
cd backend && .venv/bin/python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
cd backend && .venv/bin/python -m scripts.behavior_ownership validate
cd backend && .venv/bin/ruff check app tests scripts
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
PR_NUMBER="${PR_NUMBER:?Set PR_NUMBER to the pull request number}"
gh pr checks "$PR_NUMBER" --watch
```

## Risk

L1 / critical persistence, authorization, audit, and CI impact.

## Required reviewers

- architecture
- security
- QA
- test delta
- CI integrity
- reuse/dedup
- senior engineering
- docs

## Human review focus

- Confirm that destructive clean-cut semantics are intended.
- Review old-head/new-baseline manifest parity, especially triggers and seeds.
- Confirm no product schema or authorization behavior changed.
- Confirm removed tests covered only obsolete transitions and their current
  invariants have replacement proof.
