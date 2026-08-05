# Chunk Contract: WS-QUAL-002-03B — Artifact And Adapter Ownership

## Parent initiative
`WS-QUAL-002` — Behavior Ownership Catalogue
## Goal
Review ownership for artifacts, storage, extraction, materialization, and adapters.
## Why this chunk exists
These behaviors span filesystem, S3/MinIO, archive, and worker boundaries.
## Approved plan reference
- INTENT: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/CHUNK_MAP.md`
## Risk class
L1.
## SLA
P2.
## Allowed files
```text
.ci/behavior-ownership/artifacts/**
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/**
```
## In-scope eligible targets
Exactly the targets whose `group` is `artifacts` in the machine-readable
partition committed by `WS-QUAL-002-01`. The validator must reject records
outside that closed set; no prose inference or overlapping fallback scope is allowed.
## Not allowed
```text
backend/app/**; provider behavior; workflows; test weakening
```
## Acceptance criteria
- [ ] Every target assigned to `artifacts` by the foundation partition is reviewed or structural-only; no other target is changed.
- [ ] Storage, archive, scratch, and worker boundaries are explicit.
- [ ] Owning nodes remain bounded.
- [ ] The validator collects and runs every exact pytest node referenced by changed records, including real-provider boundary nodes where declared.
## Verification commands
```bash
(cd backend && .venv/bin/python -m scripts.behavior_ownership validate --group artifacts --run-owned-tests)
git diff --check origin/main...HEAD
```
## Required reviewers
Architecture, QA, security, product/ops, reuse/dedup, and test delta.
## Human review focus
Immutable artifact and real-provider ownership.
## Stop conditions
Stop if real-provider proof must weaken.
