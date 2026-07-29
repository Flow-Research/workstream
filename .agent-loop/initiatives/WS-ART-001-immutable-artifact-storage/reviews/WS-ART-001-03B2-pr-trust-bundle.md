# Workstream PR Trust Bundle

## Chunk

`WS-ART-001-03B2` — Guide Materialization And Classification (L1)

## Goal

Read exact verified guide-source bytes through the fixed guide-reader boundary,
recompute their identity in bounded private scratch, and persist only immutable
syntactic classification or bounded ART incident evidence.

## Intent And Planning Context

- Intent: Project Manager guide items may use the approved document, table,
  text, JSON, or image formats; they are not contributor submission ZIPs.
- Chunk contract: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks/WS-ART-001-03B2-guide-materialization-classification.md`

## What Changed

- Added exact fixed-reader materialization with pre/post lineage validation.
- Added provider-neutral streaming, complete rehash/size verification, and typed
  bounded scratch inspection.
- Added deterministic format classification, immutable evidence, bounded
  incidents, migration `0040`, tests, documentation, and review evidence.

## Why It Changed

Workstream must prove the exact verified guide bytes before later extraction or
sufficiency processing; object-store presence or caller metadata is insufficient.

## Design Chosen

Transaction A locks exact lineage and consumes prepared authority before the
provider read. The canonical store streams into canonical scratch. Transaction B
relocks the same facts before persisting one immutable result.

## Alternatives Rejected

- Direct S3/MinIO reads, arbitrary temp files, generic download authority,
  serialized prepared handles, caller excerpts, and parsing during upload.

## Scope Control

### Allowed Files Changed

- ART interfaces, models, migration, materialization/classification services,
  focused tests, ART specification, and this chunk's evidence.

### Files Outside Stated Scope

- None.

## Product Behavior

- [x] Product behavior changed and is explained here: hidden fixed-service guide
  materialization/classification exists, but `artifact.guide_source.read`
  remains planned and unavailable until AUTH-04B.

## Evidence

### Commands Run

```bash
uv run --no-sync ruff check app tests scripts alembic/versions/0040_guide_materialization.py
uv run --no-sync pytest -q tests/test_guide_formats.py tests/test_artifact_preparation.py
WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin> uv run --no-sync python scripts/run_isolated_tests.py <focused materialization tests>
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py
git diff --check
```

### Result Summary

```text
Focused guide/preparation tests: 35 passed
Database-backed materialization selection: 13 passed before review repair
Immutable-conflict database proof: 1 passed after repair
Backend exact head 1381d371: passed in 12m47s
Agent Gates exact head 1381d371: passed in 19s
CodeRabbit final-head review: completed; two evidence-wording findings repaired
```

## Acceptance Criteria Proof

- [x] Exact verified lineage and active namespace are checked before provider I/O.
- [x] Complete digest and byte count are recomputed on every read.
- [x] Stale/replaced/missing/mismatched content fails closed with bounded evidence.
- [x] Classification is syntactic, bounded, immutable, and provider-neutral.
- [x] Live AUTH actions remain planned and unavailable.

## Test Delta

### Tests Added

- Format signatures, OOXML/container safety, exact limits, image variants,
  typed inspection, materialization lineage, incidents, replay, cancellation,
  timeout, conflict, migration, and architecture fences.

### Tests Modified

- Alembic head/fingerprint, artifact architecture, preparation, and guide-binding
  integration coverage.

### Tests Removed Or Skipped

- None.

## Internal Reviewer Results

Reviewed code SHA: `1381d371`

Reviewed at: 2026-07-29

Reviewer run IDs: recorded in the paired internal-review evidence.

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | PASS WITH LOW RISKS | None | Repair delta also passed |
| QA/test | PASS WITH LOW RISKS | None | Repair delta also passed |
| Security/auth | PASS | None | Repair delta also passed |
| Product/ops | PASS | None | Exact custody preserved |
| Architecture | PASS WITH LOW RISKS | None | Canonical facade/store/scratch reused |
| CI integrity | PASS WITH LOW RISKS | None | No gate weakening |
| Docs | PASS | None | Specification and evidence aligned |
| Reuse/dedup | PASS WITH LOW RISKS | None | No parallel boundary introduced |
| Test delta | PASS WITH LOW RISKS | None | No removed or weakened tests |

## External Review

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | PASS AFTER FIXES | Six initial findings and two final evidence findings repaired |
| GitHub checks | PASS | Backend and Agent Gates green on `1381d371` |

## CI And Gate Integrity

- [x] No workflow weakening.
- [x] No lint/test/docstring gate weakening.
- [x] No coverage threshold weakening.
- [x] No package script weakening.
- [x] No unpinned new GitHub Action.
- [x] Checkout credential persistence unchanged.

## Remaining Risks

Classification is syntactic by design. Semantic extraction belongs to 03B3A;
live fixed-reader authorization belongs to AUTH-04B.

## Follow-Up Work

03B3A adds extraction, 03B3B adds durable continuation, 03B4 finalizes the
hidden manifest, AUTH-04B activates exact fixed-service actions, and 03C later
performs the separate legacy cutover.

## Human Review Focus

Please inspect active namespace fencing, pre/post generation locks, complete
rehash comparison, nested-archive bounds, incident privacy, and deny-only AUTH.

## Human Merge Ownership

- [x] I can explain what changed.
- [x] I can explain why it changed.
- [x] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
