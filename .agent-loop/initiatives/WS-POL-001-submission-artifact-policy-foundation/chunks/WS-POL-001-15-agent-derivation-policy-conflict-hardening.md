# Chunk Contract: WS-POL-001-15 - Agent Derivation Policy Conflict Hardening

## Parent Initiative

`WS-POL-001` - Submission Artifact Policy Foundation

## Goal

Harden project submission artifact policy derivation so the OpenAI Agents SDK
runtime does not emit self-conflicting required artifact and forbidden artifact
rules for real Terminal Benchmark guide material.

## Why This Chunk Exists

The accepted no-DB Terminal Benchmark live API drill from `main` reached guide
creation, source snapshot capture, sufficiency analysis, and warning
acknowledgement, then failed at agent-derived submission artifact policy
creation with:

```text
required artifact conflicts with forbidden artifacts
```

Direct reproduction showed the agent can require a real Terminal Benchmark file
such as `steps/milestone_1/tests/test_m1.py` while also emitting a forbidden
pattern that matches it. The server correctly rejects that conflict; the missing
piece is a sharper derivation contract and regression coverage.

## Risk Class

L1

## SLA

P1

## Work Type

Project setup agent contract, policy validation tests, real API drill.

## Depends On

`WS-POL-001-14`

## Allowed Files

```text
backend/app/adapters/project_agents/openai_agent_sdk.py
backend/tests/test_projects.py
examples/terminal_benchmark/terminal_benchmark_api_e2e.py
docs/roadmap_status.md
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

## Not Allowed

```text
backend/alembic/versions/**
backend/app/adapters/auth/**
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/app/modules/projects/models.py
backend/app/modules/projects/router.py
backend/app/modules/projects/repository.py
payment/reputation/blockchain settlement
frontend/demo UI work
new agent runtime providers
weakening Workstream default forbidden artifact rules
```

## Acceptance Criteria

- `SubmissionArtifactPolicyDerivationAgent` instructions explicitly require the
  derived policy to be internally consistent: no forbidden artifact pattern may
  match a required artifact path/key or required evidence key/label.
- The instructions distinguish worker submission artifacts from source snapshot,
  reviewer-only, and example material.
- The instructions prefer deterministic project-level artifact intake contracts
  over overfitting to one representative task.
- Server-side forbidden artifact validation remains fail-closed for unsafe
  required artifact paths and keys.
- Tests pin the prompt contract so future edits cannot remove the
  self-conflict prohibition.
- Tests keep deterministic rejection coverage for genuinely unsafe required
  artifact paths or keys.
- The accepted Terminal Benchmark live API drill proceeds past
  `derive-submission-artifact-policy` through the HTTP-visible no-DB proof path.

## Verification Commands

```bash
cd backend && .venv/bin/pytest tests/test_projects.py -q
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
```

## Required Reviewers

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

## Human Review Focus

Whether the derivation contract keeps the server guard strict while preventing
real setup agents from creating self-conflicting project policies.

## Stop Conditions

- Stop if the fix requires weakening default forbidden artifact enforcement.
- Stop if the live drill failure is caused by genuinely unsafe Terminal
  Benchmark source material rather than agent output.
- Stop if a new agent runtime provider or task-specific checker generation is
  needed.
