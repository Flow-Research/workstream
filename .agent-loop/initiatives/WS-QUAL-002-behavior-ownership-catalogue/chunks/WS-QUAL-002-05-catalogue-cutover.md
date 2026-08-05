# Chunk Contract: WS-QUAL-002-05 — Catalogue-First Mutation Cutover

## Parent initiative
`WS-QUAL-002` — Behavior Ownership Catalogue
## Goal
Use protected catalogue ownership by default and prove AUTH no longer pauses.
## Why this chunk exists
This delivers reusable ownership while preserving changed-scope mutation.
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
backend/scripts/mutation_policy.py
backend/tests/test_mutation_policy.py
backend/scripts/behavior_ownership.py
backend/tests/test_behavior_ownership.py
.github/workflows/mutation-pilot.yml
.ci/behavior-claims/**
.ci/behavior-ownership/**
CONTRIBUTING.md
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/**
```
## Not allowed
```text
backend/app/**; migrations; global mutation; scores; exemptions; PR authority for existing ownership; test weakening
```
## Acceptance criteria
- [ ] Existing callables resolve from the catalogue physically loaded from the exact protected base SHA, never from PR head, without manual claims.
- [ ] New/remapped callables require additive validated PR-head records and cannot replace protected records.
- [ ] PR data that deletes, narrows, downgrades, changes tests/outcomes/boundaries, or otherwise replaces existing protected reviewed ownership fails closed.
- [ ] Negative tests prove forged PR-head ownership cannot affect protected-base selection and exact callable custody remains authoritative.
- [ ] AUTH rehearsal and hosted mutation pass within the current cap.
- [ ] Human explicitly approves cutover.
## Verification commands
```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_behavior_ownership.py tests/test_mutation_policy.py)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_lightweight_agent_gates.py
git diff --check origin/main...HEAD
```
## Required reviewers
Architecture, senior engineering, QA, security, product/ops, CI integrity, docs, reuse/dedup, and test delta.
## Human review focus
Protected engineering-gate custody, additive flow, AUTH usability, and hosted runtime.
## Stop conditions
Stop if catalogue is incomplete, AUTH still needs routine claims, or 05M weakens.
