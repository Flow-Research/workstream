# Chunk Contract: WS-ART-001-02A1 - External Service Adapter Foundation

Initiative: `WS-ART-001` | Risk: L1 | Status: Active after explicit user start on 2026-07-15

Artifact contract phase: `foundation`

## Goal

Install only ADR 0014's small typed external-service adapter and factory
foundation. Do not migrate ArtifactStore or any other external capability in
this chunk.

## Allowed Files

- `backend/app/interfaces/external_services.py`
- focused tests for adapter identity, root errors, registration, and factory
  construction
- `.github/workflows/backend.yml` only to add the exact 90 percent scoped gate
- `scripts/test_agent_gates.py` only to assert the exact workflow command,
  source set, threshold, and cumulative retention
- `.agent-loop/merge-intents/WS-ART-001-02A1.json`
- `WS-ART-001-02A2` chunk heading only, to make the declared successor title
  machine-verifiable by the schema-v2 merge-memory validator
- directly related ADR 0014, glossary, and chunk memory

## Not Allowed

- ArtifactStore interface, implementation, configuration, model, or migration
  changes;
- migration of auth, project-agent, storage, payment, or any other capability;
- provider SDKs or concrete provider construction;
- public routes, Celery tasks, or product lifecycle changes;
- service locators, runtime plugin discovery, import scanning, mutable global
  registration, compatibility aliases, or fallback constructors.

## Acceptance Criteria

- `ExternalServiceAdapter` contains only immutable capability/provider identity
  and root configuration, availability, and protocol error semantics shared by
  every external capability.
- Root errors retain only stable codes/categories and sanitized adapter
  identity. They do not retain raw settings, credentials, payloads, or original
  transport exceptions in public attributes, text, or representation.
- `ExternalServiceAdapterFactory[TAdapter]` supports explicit typed
  registration and construction and fails closed on duplicate and unknown
  providers.
- registration remains composition-root owned; the foundation performs no
  implicit discovery and has no global mutable registry.
- no existing external capability is migrated or behaviorally changed.
- focused tests cover the entire new foundation at or above 90 percent and
  repository coverage does not fall below the current baseline.
- backend CI installs this chunk's exact focused 90 percent gate, preserves
  every earlier scoped 90 percent gate, and retains the exact 78 percent
  repository command below; `scripts/test_agent_gates.py` fails on workflow
  command, source-set, threshold, or cumulative-retention drift.

## Exact CI Coverage Gate

```bash
coverage report --include='app/adapters/artifacts/*,app/core/cancellation.py,app/core/file_locks.py,app/interfaces/artifact_operations.py,app/interfaces/artifacts.py,app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/interfaces/external_services.py' --precision=2 --fail-under=90
```

## Verification

```bash
docker compose up -d --wait postgres redis
(cd backend && .venv/bin/ruff check app tests)
(cd backend && .venv/bin/pytest tests/test_external_service_adapters.py -q --cov=app.interfaces.external_services --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is the shared foundation genuinely smaller than every capability port?
- Is construction explicit and typed without becoming a service locator?
- Did the chunk avoid migrating unrelated capability owners?
