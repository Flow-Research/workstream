# Chunk: WS-CI-005-PLAN Semantic Proof Quality Planning

## Intent

Record the evidence-backed design and bounded delivery sequence for improving
reviewer proof discrimination after PR #349.

## Allowed files

```text
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-CI-005-semantic-proof-quality/**
```

## Not allowed

Application code, tests, workflows, reviewer skills/agents, validator behavior,
product documentation, schemas, migrations, or repository authority changes.

## Acceptance criteria

- Intent, discovery, plan, chunk map, status, risks, and decisions are present.
- PR #349 escaped failure classes are recorded without treating CodeRabbit as
  authoritative.
- Proof vocabulary and test-of-the-test design are explicit.
- Exactly three implementation chunks have bounded contracts.
- No implementation behavior is claimed complete.

## Risk

L1 planning for critical engineering infrastructure.

## Verification

```bash
python3 scripts/check_active_state_projections.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_review_contracts.py
git diff --check
```

## Required reviewers

Architecture, CI integrity, security, QA/test-delta, senior engineering,
reuse/dedup, and documentation. Product/operations verifies that engineering
review language does not alter Workstream product review decisions.

## Outcome on merge

The initiative plan becomes durable and `WS-CI-005-01` remains planned. No
implementation begins automatically.
