# Chunk Contract: WS-ART-001-04A Upload, Inspection, And Sealing

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 03

Artifact contract phase: `guide_source_cutover`

## Goal

Add contributor-authorized task upload sessions/items, trusted archive
inspection, independent verification, immutable sealing, and artifact-set
manifests without running pre-submit or creating submissions.

## Allowed Files

- artifact upload-session/item/set models and one migration;
- artifact repository/service/router/schemas for upload, inspect, seal, and
  logical cancellation APIs and internal upload-session expiry;
- trusted archive/media inspection helpers;
- artifact call sites consuming exact decisions already delivered by the
  approved WS-AUTH dependency; no Authorization Service owner files;
- focused migration, concurrency, upload, inspection, sealing, and real-API tests;
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate;
- `scripts/test_agent_gates.py` only to assert that backend CI retains this
  chunk's exact scoped coverage sources and fail-closed 90 percent threshold;
- related docs and chunk memory.

## Not Allowed

- pre-submit checker execution or admission records;
- submission creation/finalization changes;
- post-submit checker or review changes;
- presigned/direct provider upload or provider identifiers in responses;
- free-form client policy/checker overrides;
- physical provider deletion on cancellation.

## Acceptance Criteria

- only the assigned contributor with exact task authorization can create or
  mutate a live task upload session;
- create, read, item write, seal, and cancel call the distinct task-scoped
  permissions `artifact.upload_session.create`,
  `artifact.upload_session.read`, `artifact.upload_item.write`,
  `artifact.upload_session.seal`, and `artifact.upload_session.cancel`
  through the central AUTH kernel with ART-owned canonical resource facts and
  guards; this chunk first supplies hidden behavior while actions remain planned,
  and AUTH alone activates them afterward; none implies another;
- every ID-addressed read/mutation uses concealed deny/not-found behavior and
  is tested across actors, projects, revocation, terminal states, and random IDs;
- upload requires a server-approved logical role, bounded display name, client
  SHA-256 commitment, expected byte count, and streamed file;
- Workstream prepares and hashes the complete stream, rejects mismatch before
  provider I/O, and derives the key only from the server commitment;
- PostgreSQL atomically enforces configured open-session slots at task, actor,
  project, and deployment scope; contributor item bytes use the generic 02C1
  admission service at task, authenticated actor, project, and deployment
  scope after canonical hashing and before provider I/O;
- PostgreSQL-clock expiry is owned by a bounded periodic Celery scanner and is
  also applied lazily before new-session admission. Both paths require the
  fixed internal permission `artifact.upload_session.expire`; one atomic
  terminal transition releases each open-session slot exactly once, and stale
  scanner execution cannot release it again;
- cancellation and expiry release only the open-session slot. Provisional and
  completed byte charges follow the generic admission state machine;
  cancelled, expired, and unbound completed bytes remain charged in v0.1,
  while exact deduplicated content is charged once per applicable scope;
- every item is independently verified before it can be sealed;
- limits cover item count, aggregate/per-file bytes, archive expansion, entry
  count, path safety, nesting, and compression ratio;
- sealing row-locks the session/items, requires verified replicas, creates a
  deterministic manifest/hash, and is idempotent under exact replay;
- cancellation is logical and cannot delete shared completed bytes;
- race tests cover upload/seal/cancel/expiry conflicts, repeated-session quota
  exhaustion, concurrent quota admission without oversubscription, terminal
  session-slot release by periodic and lazy expiry, retained charges for
  cancelled/expired/unbound content,
  and first-writer and cross-project digest-key poisoning attempts;
- changed subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent;
- backend CI installs this chunk's exact focused 90 percent gate, preserves
  every earlier scoped 90 percent gate, and retains the exact 78 percent
  repository command below; `scripts/test_agent_gates.py` fails on workflow
  command, source-set, threshold, or cumulative-retention drift.

## Exact CI Coverage Gates

```bash
coverage report --include='app/adapters/artifacts/*,app/core/cancellation.py,app/core/file_locks.py,app/interfaces/artifact_operations.py,app/interfaces/artifacts.py,app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/interfaces/external_services.py' --precision=2 --fail-under=90
coverage report --include='app/core/config.py' --precision=2 --fail-under=90
coverage report --include='app/workers/*' --precision=2 --fail-under=90
coverage report --include='app/main.py' --precision=2 --fail-under=90
coverage report --include='app/modules/audit/*' --precision=2 --fail-under=90
coverage report --include='app/api/router.py' --precision=2 --fail-under=90
coverage report --include='app/modules/projects/*' --precision=2 --fail-under=90
coverage report --include='app/adapters/project_agents/*,app/interfaces/project_agents.py' --precision=2 --fail-under=90
```

## Verification

```bash
docker compose up -d --wait postgres redis minio
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_artifact_upload_api.py -q --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Can a client choose a provider key or bypass independent verification?
- Is the sealed artifact-set commitment deterministic and immutable?
- Are archive and resource-exhaustion boundaries explicit and tested?
