# Chunk Contract: WS-QUAL-002-02 — Coverage-Context Candidate Evidence

## Parent initiative
`WS-QUAL-002` — Behavior Ownership Catalogue
## Goal
Emit non-authoritative callable-to-test candidates from exact coverage contexts and measure hosted cost.
## Why this chunk exists
Imports do not prove behavior ownership.
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
backend/scripts/behavior_ownership.py
backend/scripts/run_test_lanes.py
backend/tests/test_behavior_ownership.py
backend/tests/test_ci_test_lanes.py
backend/pyproject.toml
.github/workflows/behavior-ownership-context.yml
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/**
```
## Not allowed
```text
backend/app/**; reviewed catalogue population; mutation cutover; coverage or test weakening; .github/workflows/mutation-pilot.yml; any required-check or blocking-gate change
```
## Acceptance criteria
- [ ] Context evidence binds exact head, callable lines, and collected nodes.
- [ ] Test discovery, collection, and completion evidence reuse `run_test_lanes.py` rather than introducing a parallel collector.
- [ ] Candidate output cannot satisfy reviewed ownership.
- [ ] The prototype runs in a separate non-blocking observational workflow and cannot delay or alter required mutation status.
- [ ] Added hosted runtime is at most two minutes and each uploaded artifact is at most 10 MiB; exceeding either limit stops adoption and triggers local-only redesign.
- [ ] Artifacts contain only commit SHAs, target paths, callable spans, collected node IDs, and line-coverage metadata, never environment values, secrets, tokens, request payloads, logs, or database values; retention is no more than seven days.
## Verification commands
```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_behavior_ownership.py tests/test_ci_test_lanes.py)
git diff --check origin/main...HEAD
```
## Required reviewers
Architecture, QA, security, CI integrity, reuse/dedup, and test delta.
## Human review focus
Candidate-only custody, isolation from required checks, and hosted cost.
## Stop conditions
Stop if contexts destabilize Backend or require PR-controlled authority.
