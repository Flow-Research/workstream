# Chunk Contract: WS-QUAL-002-04 — Catalogue Completeness And PR Preparation

## Parent initiative
`WS-QUAL-002` — Behavior Ownership Catalogue
## Goal
Require current catalogue data and provide one-command PR preparation.
## Why this chunk exists
Ownership must be machine-visible before implementation review.
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
backend/tests/test_behavior_ownership.py
scripts/test_lightweight_agent_gates.py
scripts/workstream_agent_gate.py
CONTRIBUTING.md
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/STATUS.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/reviews/WS-QUAL-002-04-*
```
## Not allowed
```text
mutation reactivation; backend/app/**; coverage weakening; administrator approval gates
```
## Acceptance criteria
- [ ] All current eligible targets reconcile exactly.
- [ ] Tests collect and candidates cannot satisfy completeness.
- [ ] One command reports ready selection or precise new/remapped gaps.
- [ ] The contributor interface remains `python3 scripts/workstream_agent_gate.py`; its structured output adds a `behavior_ownership` result containing `ready`, exact selected callables, and typed new/remapped gaps while preserving all existing gate findings.
## Verification commands
```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_behavior_ownership.py)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_lightweight_agent_gates.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD
git diff --check origin/main...HEAD
```
## Required reviewers
Architecture, QA, security, CI integrity, docs, reuse/dedup, and test delta.
## Human review focus
No admin action and precise contributor repair.
## Stop conditions
Stop if unrelated work is blocked ambiguously. Changes to this contract require
parent-initiative approval and are outside the chunk's own write authority.
