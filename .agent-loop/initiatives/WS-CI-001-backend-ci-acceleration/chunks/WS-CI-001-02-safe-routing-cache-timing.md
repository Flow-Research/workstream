# Chunk Contract: WS-CI-001-02 — Safe Routing, Cache, and Timing Refinement

## Parent initiative

`WS-CI-001` — Backend CI Acceleration

## Goal

Use measured 01 evidence to consider fail-closed path routing, dependency cache,
and durable shard weights without weakening full-suite requirements.

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

- [ ] A separate reviewed amendment defines exact files and fail-closed routing.
- [ ] Cache and timing provenance cannot cross dependency or commit boundaries.
- [ ] Full-suite-required change classes default closed on ambiguity.
- [ ] Prospective `WS-CI-001-02A` and `WS-CI-001-02B` contracts split the
      migrate-once reset from semantic-lane orchestration without treating PR
      #180 as authorized implementation evidence.
- [ ] The contracts require destructive-reset ownership, exact node custody,
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

Stop if 01 is not merged and stable, if scope is not explicit, or if the user has
not separately approved this chunk.
