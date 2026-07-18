# Chunk Contract: WS-POL-002-PLAN - Post-Submit Checker Foundation Planning

## Parent Initiative

`WS-POL-002` - Post-Submit Checker Foundation

## Approved Plan Reference

- INTENT: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Problem Being Solved

The current post-submit checker runtime is durable and policy-locked, but the
project setup side is not yet as disciplined as pre-submit. Planning must close
the previous WS-POL-001 loop, discover the existing post-submit code path, and
define the smallest implementation chunks before code changes start.

## Goal

Produce intent, discovery, plan, decisions, risks, chunk map, and chunk
contracts for project-guide-derived post-submit checker setup.

## Allowed Files

```text
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/**
docs/roadmap_status.md
```

## Not Allowed

```text
backend/app/**
backend/alembic/versions/**
backend/tests/**
backend/scripts/**
frontend or demo UI work
payment/reputation/blockchain settlement
runtime product behavior changes
```

## Acceptance Criteria

- `WS-POL-001-16` loop memory is closed as merged through PR #84.
- `WS-POL-002` intent and discovery accurately describe the current
  post-submit runtime and the missing setup pipeline.
- Plan preserves project-scoped `PostSubmitCheckerPolicy`; no per-task checker
  generation is introduced.
- Plan defines exact setup trigger boundary after pre-submit approval/compile.
- Chunk contracts include allowed files, not-allowed changes, acceptance
  criteria, verification commands, required reviewers, and human review focus.
- Internal reviewer findings are addressed or explicitly documented.

## Verification Commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required Reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- docs
- reuse/dedup
- test delta
- CI integrity

## Human Review Focus

- Confirm the intent matches the desired post-submit checker direction.
- Confirm the setup trigger boundary is realistic against current code.
- Confirm implementation chunks are small enough to review.

## Stop conditions

Stop and escalate if:

- scope must expand beyond allowed files
- architecture direction changes
- auth/payment/policy/data boundary changes beyond this contract
- CI/test weakening is required to pass
- the same blocker remains after 2 repair attempts
- secrets or production data are needed
