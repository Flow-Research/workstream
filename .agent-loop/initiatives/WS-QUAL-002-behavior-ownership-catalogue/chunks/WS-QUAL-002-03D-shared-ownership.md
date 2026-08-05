# Chunk Contract: WS-QUAL-002-03D — Shared Runtime And Script Ownership

## Parent initiative
`WS-QUAL-002` — Behavior Ownership Catalogue
## Goal
Review core, DB, interfaces, composition, async execution, and remaining scripts.
## Why this chunk exists
Completeness requires shared operational ownership without mixing product reviews.
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
.ci/behavior-ownership/shared/**
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/**
```
## In-scope eligible targets
Exactly the targets whose `group` is `shared` in the machine-readable partition
committed by `WS-QUAL-002-01`. The validator must reject records outside that
closed set; no prose inference or overlapping fallback scope is allowed.
## Not allowed
```text
backend/app/**; runtime behavior; DB behavior; workflows; test weakening
```
## Acceptance criteria
- [ ] Every target assigned to `shared` by the foundation partition is reviewed or structural-only; no other target is changed.
- [ ] Composition, DB, lock, async-execution, and script boundaries are explicit.
- [ ] No target appears in multiple groups.
- [ ] The validator collects and runs every exact pytest node referenced by changed records.
## Verification commands
```bash
(cd backend && .venv/bin/python -m scripts.behavior_ownership validate --group shared --run-owned-tests)
git diff --check origin/main...HEAD
```
## Required reviewers
Architecture, senior engineering, QA, security, CI integrity, reuse/dedup, and test delta.
## Human review focus
Composition roots, DB/locks, async execution, and scripts.
## Stop conditions
Stop if structural-only hides executable behavior.
