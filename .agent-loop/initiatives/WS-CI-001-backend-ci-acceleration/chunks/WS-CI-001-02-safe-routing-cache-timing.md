# Chunk Contract: WS-CI-001-02 — Safe Routing, Cache, and Timing Refinement

## Parent initiative

`WS-CI-001` — Backend CI Acceleration

## Goal

Use measured evidence to decide whether fail-closed path routing, dependency
cache, or durable timing weights should be implemented now, and prospectively
contract the safer optimization that addresses the observed bottleneck.

## Why this chunk exists

Parallelization addresses elapsed test time first. Routing, caching, and timing
data have different trust and invalidation risks and require a separate review.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/CHUNK_MAP.md`

## Risk class

L1

## SLA

P2

## Start phase

`planning`

## Allowed files

To be fixed only after 01 hosted evidence and separate discovery.

## Not allowed

Implementation, activation, or successor declaration before a separate human
approval; any coverage/test weakening; backend product changes; 04B activation.

## Acceptance criteria

- [x] Routing is not implemented: current evidence does not justify suppression
      risk, and every change class continues to run the full required suite.
- [x] Dependency cache and durable timing weights are not implemented: their
      provenance/invalidation boundaries remain unresolved and cannot cross
      dependency or commit boundaries.
- [x] Future reassessment is identified as planning chunk `WS-CI-001-03`; it
      requires evidence after 02B, its own signed planning start, and fail-closed
      defaults. It is not this PR's successor.
- [x] Prospective `WS-CI-001-02A` and `WS-CI-001-02B` contracts split the
      migrate-once reset from semantic-lane orchestration without treating PR
      #180 as authorized implementation evidence.
- [x] The contracts require destructive-reset ownership, exact node custody,
      strict test assertions, all guarded-trigger restoration, unchanged
      coverage floors, isolated services, and exact hosted proof.

## Verification commands

```bash
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/test_agent_gates.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_internal_review_evidence.py
git diff --check origin/main...HEAD
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Whether any optimization can suppress required proof and whether added cache or
telemetry complexity is justified by measured results.

## Stop conditions

Stop if the plan attempts routing/cache/timing implementation, if successor
scope is not explicit, or if implementation begins before its signed start.
