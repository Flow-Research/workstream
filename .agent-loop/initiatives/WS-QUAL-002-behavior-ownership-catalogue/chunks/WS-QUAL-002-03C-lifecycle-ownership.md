# Chunk Contract: WS-QUAL-002-03C — Product Lifecycle Ownership

## Parent initiative
`WS-QUAL-002` — Behavior Ownership Catalogue
## Goal
Review projects, tasks, checkers, reviews, contributions, compensation, and outbox ownership.
## Why this chunk exists
These modules establish Workstream lifecycle truth.
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
.ci/behavior-ownership/lifecycle/**
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/**
```
## In-scope eligible targets
Exactly the targets whose `group` is `lifecycle` in the machine-readable
partition committed by `WS-QUAL-002-01`. The validator must reject records
outside that closed set; no prose inference or overlapping fallback scope is allowed.
## Not allowed
```text
backend/app/**; lifecycle states; review decisions; payment behavior; workflows
```
## Acceptance criteria
- [ ] Every target assigned to `lifecycle` by the foundation partition is reviewed or structural-only; no other target is changed.
- [ ] State, denial, idempotency, revision, and concurrency outcomes are explicit.
- [ ] Engineering ownership does not redefine product decisions.
- [ ] The validator collects and runs every exact pytest node referenced by changed records.
## Verification commands
```bash
(cd backend && .venv/bin/python -m scripts.behavior_ownership validate --group lifecycle --run-owned-tests)
git diff --check origin/main...HEAD
```
## Required reviewers
Architecture, QA, security, product/ops, and test delta.
## Human review focus
End-to-end lifecycle boundaries.
## Stop conditions
Stop on product-semantic drift or unbounded owning nodes.
