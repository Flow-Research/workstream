# Chunk Contract: WS-QUAL-002-03A — AUTH And Audit Ownership

## Parent initiative
`WS-QUAL-002` — Behavior Ownership Catalogue
## Goal
Review ownership for auth, actors, authorization, API controls, and audit.
## Why this chunk exists
AUTH is active and security-sensitive.
## Approved plan reference
- INTENT: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/CHUNK_MAP.md`
## Risk class
L1.
## SLA
P1.
## Allowed files
```text
.ci/behavior-ownership/auth/**
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/STATUS.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/chunks/WS-QUAL-002-03A-auth-ownership.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/reviews/WS-QUAL-002-03A-*
```
## Not allowed
```text
backend/app/**; workflows; mutation policy; authorization behavior; unreviewed promotion
```
## In-scope eligible targets
Exactly the targets whose `group` is `auth` in the machine-readable partition
committed by `WS-QUAL-002-01`. The validator must reject records outside that
closed set; no prose inference or overlapping fallback scope is allowed.
The validator reads the versioned partition only from protected base or the
approved foundation commit, verifies its digest, and rejects any population-PR
partition change, relocation, or shadow copy.
## Acceptance criteria
- [ ] Every target assigned to `auth` by the foundation partition is reviewed-owned or strictly structural-only; no other target is changed.
- [ ] Exact collected tests and context evidence support mappings.
- [ ] The validator collects and runs every exact pytest node referenced by changed records.
- [ ] AUTH selection generates without hand-authoring existing ownership.
## Verification commands
```bash
(cd backend && .venv/bin/python -m scripts.behavior_ownership validate --group auth --run-owned-tests)
git diff --check origin/main...HEAD
```
## Required reviewers
Architecture, QA, security, product/ops, docs, and test delta.
## Human review focus
Denial, admin, lineage, audit, and service-identity mappings.
## Stop conditions
Stop if bounded owning tests or real boundaries are missing.
