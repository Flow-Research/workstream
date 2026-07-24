# Chunk Contract: WS-ART-001-04A One-ZIP Scratch Intake And Manifest

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 03C and AUTH planned registration

Artifact contract phase: `guide_source_cutover`

## Goal

Accept exactly one contributor outer ZIP into bounded private scratch, safely
inspect its complete internal tree, and produce authoritative archive and
semantic-manifest commitments without provider I/O, project checker execution,
or Submission creation.

## Allowed Files

- ART-owned scratch-intake, ZIP inspection, normalization, and manifest code;
- existing `ArtifactUploadSession`/`ArtifactUploadItem` models, migration,
  repositories, schemas, and routes only to remove them or make them unreachable
  as contributor intake; no retained provider/content-result staging semantics;
- task-scoped hidden upload surface and ART canonical resource facts/guards;
- one migration for the bounded intake/manifest control plane if required;
- focused archive, quota, concurrency, cleanup, fuzz/regression, API, coverage,
  docs, and chunk-memory changes;
- CI files only to add and preserve the exact scoped 90 percent gate.

## Not Allowed

- `ArtifactStore.put`, `ArtifactContent`, replica, binding, or provider I/O;
- project pre-submit checker execution or admission;
- Submission, Review, Contribution, compensation, reputation, or delivery work;
- multi-item submission sets, direct/presigned uploads, candidate storage,
  retention windows, or physical deletion;
- AUTH-owned catalogue, evaluator, grant, identity, matrix, or activation edits;
- raising current configured limits.

## Acceptance Criteria

- a contributor attempt accepts exactly one outer ZIP and rejects every other
  archive form or additional item;
- Workstream streams, sizes, and hashes the exact ZIP while reserving bounded
  aggregate scratch through the canonical `ArtifactScratchManager`;
- the outer ZIP tree is walked recursively without `extractall`; ZIP entries
  contained inside that tree remain opaque ordinary files by default;
- path normalization rejects absolute/drive/UNC paths, `.`/`..`, NUL/control
  characters, backslashes, symlinks/special entries, duplicate normalized paths,
  Unicode-normalization collisions, and configured case-fold collisions;
- bounded streaming enforces current upload, extracted-byte, per-file, entry,
  path-depth/path-length, compression-ratio, deadline, concurrency, and free-space
  limits without allocating from untrusted declared sizes;
- the canonical semantic manifest records normalized file and directory paths,
  entry type, and file SHA-256/byte count; timestamps, compression, comments,
  ownership, and platform permission metadata do not affect its hash;
- explicit empty directories and deterministic synthetic parents have one
  documented canonical representation;
- exact archive hash and semantic manifest hash are compared with the immediate
  prior immutable Submission under task/version locking; equality returns a
  stable unchanged error before checker or provider I/O;
- the server-computed ZIP commitment is authoritative; an optional client
  commitment can only cause early mismatch rejection;
- successful output is a process-local, lease-bound prepared bundle handle that
  contains no path/provider reference in an API response and is unusable after
  cleanup, expiry, process loss, or generation mismatch;
- that handle is metadata around the existing `ArtifactScratchManager`,
  `PreparedArtifact`, and `CommittedArtifactSource` lifecycle, not a second
  handle/lease/ledger/quota/cleanup abstraction;
- 04A exposes only internal hidden library seams and tests. It composes no
  contributor route until 04C completes the same-process orchestration;
- every old multi-step upload-session/item route and action path is removed or
  statically unreachable; no multi-item or provider-result compatibility path
  remains;
- process loss requires reupload; normal, error, cancellation, timeout, and
  crash cleanup release scratch quota without deleting durable artifacts;
- the route declares only planned action `artifact.submission_bundle.prepare`,
  mapped by AUTH to `submission.create`, with ART-owned task/assignment/actor
  facts and guards; the old multi-step upload-session actions are not accepted
  as aliases or alternate routes;
- hidden behavior remains unavailable until AUTH activates that exact action
  only after 04A-04C publish the complete surface/guard manifest;
- focused subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent.

## Exact CI Coverage Gates

```bash
coverage report --include='app/adapters/artifacts/*,app/core/cancellation.py,app/core/file_locks.py,app/interfaces/artifact_operations.py,app/interfaces/artifacts.py,app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/interfaces/external_services.py' --precision=2 --fail-under=90
coverage report --include='app/core/config.py' --precision=2 --fail-under=90
coverage report --include='app/workers/*' --precision=2 --fail-under=90
coverage report --include='app/main.py' --precision=2 --fail-under=90
coverage report --include='app/adapters/artifacts/s3_compatible.py' --precision=2 --fail-under=90
coverage report --include='app/core/s3_validation.py' --precision=2 --fail-under=90
coverage report --include='app/modules/audit/*' --precision=2 --fail-under=90
coverage report --include='app/api/router.py' --precision=2 --fail-under=90
coverage report --include='app/modules/projects/*' --precision=2 --fail-under=90
coverage report --include='app/adapters/project_agents/*,app/interfaces/project_agents.py' --precision=2 --fail-under=90
```

## Verification

```bash
docker compose up -d --wait postgres redis
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_submission_bundle_intake.py tests/test_submission_zip_safety.py tests/test_submission_bundle_manifest.py tests/test_artifact_scratch_manager.py -q --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Can more than one outer ZIP or unchecked bytes escape scratch?
- Is recursive inspection clearly the outer archive tree, not nested unpacking?
- Does semantic equality ignore packaging-only changes without ignoring files?
