# PR Trust Bundle: WS-ART-001-02A2

## Chunk

`WS-ART-001-02A2` - Committed Source And Local Preparation

Merge intent: `.agent-loop/merge-intents/WS-ART-001-02A2.json`

## Goal

Build the inactive bounded source-preparation boundary that ArtifactStore v2
will consume while preserving active v1 behavior.

## Human-Approved Intent

- Intent: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/INTENT.md`
- Chunk contract: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks/WS-ART-001-02A2-committed-source-local-preparation.md`

The approved provider direction is LocalStorage for development, MinIO for
local/CI S3 proof, AWS S3 for v0.1 production, and Flow Node as a separate
future initiative. This chunk activates none of those future provider paths.

## What Changed

- Added sealed server commitment plus exact second-pass stream as one
  non-forgeable value.
- Added a private cross-process scratch reservation ledger with full-max
  admission, private/no-follow files, deadlines, process-identity-aware stale
  cleanup, and retryable custody.
- Added one shared bounded file-lock primitive and cancellation-safe
  LocalStorage private lock acquisition.
- Added configuration, documentation, focused tests, and cumulative CI proof.

## Why It Changed

The future provider path must store the exact bytes Workstream measured and
committed. Cancellation, lock contention, descriptor-close uncertainty, PID
reuse, or cleanup failure must not silently change those bytes or free their
quota early.

## Design Chosen

Workstream temporarily spools one opaque source under a bounded private scratch
manager, computes SHA-256 and byte count, seals an anonymous read descriptor,
and exposes only a `CommittedArtifactSource`. PostgreSQL is not used for scratch
coordination. Durable adapters later consume the committed stream and store
only their provider reference and commitment in product records.

## Alternatives Rejected

- Hashing while directly streaming an uncommitted source to the provider:
  rejected because provider bytes could exist before Workstream knows the final
  commitment.
- PostgreSQL or Redis scratch coordination: rejected because temporary byte
  custody is infrastructure state, not product state.
- PID-only stale ownership: rejected because PID reuse can preserve abandoned
  quota indefinitely.
- Unbounded file locks: rejected because cancellation could hang forever.

## Scope Control

### Allowed Files Changed

- Artifact preparation/source modules and LocalStorage private helpers.
- Shared cancellation/file-lock primitives and artifact configuration.
- Focused tests, workflow/gate assertions, artifact spec, and loop evidence.

### Files Outside Contract

- None. The contract was amended before final review to name the shared lock
  helper and existing composition-root timeout pass-through.

## Product Behavior

- [x] No Workstream product behavior changed.
- [ ] Product behavior changed and is explained here:

## Evidence

### Commands Run

```bash
cd backend && .venv/bin/ruff check app tests
cd backend && .venv/bin/pytest tests/test_artifact_preparation.py tests/test_local_artifact_store.py tests/test_config.py -q --cov=app.core.cancellation --cov=app.core.file_locks --cov=app.modules.artifacts.preparation --cov=app.modules.artifacts.sources --cov=app.core.config --cov-report=term-missing --cov-fail-under=90
cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json <temporary-path>/result.json --timeout-seconds 900 -- .venv/bin/python -m pytest tests/test_artifacts.py -q
python3 scripts/test_agent_gates.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
```

### Result Summary

```text
154 focused tests passed; scoped coverage 94.40%
38 isolated PostgreSQL artifact integration tests passed
207 isolated AUTH/authentication/Alembic integration tests passed after main integration
Ruff passed
Repository docstring coverage 94.8%
71 agent-gate tests passed
Stale artifact, wording, Markdown link, and diff checks passed
```

## Acceptance Criteria Proof

- [x] Server computes SHA-256 and exact size while writing the untrusted first pass once.
- [x] Sealed second-pass bytes are verified before the first provider byte can be yielded.
- [x] Client digest/size mismatch fails before any future provider call.
- [x] Every preparation reserves the full 512 MiB hard maximum under a bounded cross-process lock.
- [x] Quota, file count, concurrency, free-space, deadline, crash, cancellation, PID reuse, and filesystem attacks have regression coverage.
- [x] Active LocalStorage v1 interface and product behavior remain unchanged.

## Test Delta

### Tests Added

- Scratch construction, capacity, concurrency, stale cleanup, cancellation,
  descriptor/reader custody, PID reuse, and lock deadline tests.
- LocalStorage v1 regression, lock deadline, and cancellation-timeout tests.

### Tests Modified

- Artifact configuration and cumulative CI gate assertions.

### Tests Removed Or Skipped

- None.

## Internal Reviewer Results

Reviewed code SHA: `ae70bc2f10334f649c1af7f210e58ee378695a2b`

Reviewed at: `2026-07-16T09:03:51Z`

Reviewer run IDs: recorded in `WS-ART-001-02A2-internal-review-evidence.md`

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | PASS | None | Exact code SHA and focused gates passed. |
| QA/test | PASS | None | Exact cancellation identity, retry cleanup, and marker-order proof passed. |
| Security/auth | PASS | None | No authority or protected product surface changed. |
| Product/ops | PASS | None | No product lifecycle changed. |
| Architecture | PASS | None | Boundaries and inactive runtime scope remain intact. |
| CI integrity | PASS | None | No gate or threshold weakening. |
| Docs | PASS | None | Required artifact settings and behavior documented. |
| Reuse/dedup | PASS | None | Existing cancellation helper is reused; no parallel abstraction added. |
| Test delta | PASS | None | No removed, skipped, xfailed, or weakened tests. |

All nine final reviewer sessions are closed.

## External Review

External review response file:

- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/reviews/WS-ART-001-02A2-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | PASS | Five prior findings remain addressed; integrated head `4ca80de` received no new comment. |
| GitHub checks | PASS | Agent Gates and Backend full-suite coverage passed on integrated head `4ca80de`. |

## CI And Gate Integrity

- [x] No workflow weakening.
- [x] No lint/test/docstring gate weakening.
- [x] No coverage threshold weakening.
- [x] No package script weakening.
- [x] No unpinned new GitHub Action.
- [x] Checkout credential persistence remains disabled.

## Remaining Risks

- Linux `/proc` is required by the Linux/`fcntl` scratch implementation.
- Ambiguous live-process descriptor custody fails closed by retaining quota.
- The boundary remains inactive until separately approved `02A3`.

## Follow-Up Work

- `02A3` performs the clean ArtifactStore v2/LocalStorage cutover and should
  consolidate temporary v1 digest/stream helpers.
- `02B1` adds MinIO protocol proof and AWS S3 only after `02A3` merges and the
  user explicitly starts it.

## Human Review Focus

Please inspect:

- Whether a caller can detach a commitment from its bytes.
- Whether cancellation or cleanup can free quota before byte custody ends.
- Whether LocalStorage v1 behavior remains intact.
- Whether this stays inactive preparation rather than a second runtime path.

## Human Merge Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
