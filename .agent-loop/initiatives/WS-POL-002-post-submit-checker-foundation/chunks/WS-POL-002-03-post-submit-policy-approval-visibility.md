# Chunk Contract: WS-POL-002-03 - Server-Owned Policy Approval And Visibility APIs

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

Operators need API-visible post-submit setup state. The old guide create/update
payload path also needs to be removed once server-owned derivation exists, so
there is one authoritative policy path.

## Goal

Expose generated post-submit policy setup state through APIs and add the
server-owned approval/correction path for compiled post-submit checker policies.

## Target Behavior

- Setup-authorized admin or project_manager can inspect derivation input
  summary, derivation output, unsupported gaps, compiled policy summary, and
  policy hash under the current v0.1 bootstrap authorization boundary.
- Setup-authorized admin or project_manager can approve or request setup
  correction for the generated project post-submit policy.
- Correction supersedes rather than deletes the rejected compiled policy,
  preserves actor/reason/hash/body provenance, supplies bounded feedback to
  rederivation, and rejects an unchanged replacement.
- Guide create/update continues to reject `post_submit_checker_policy` from
  clients.
- Guide activation requires the approved compiled project
  `PostSubmitCheckerPolicy`.
- Contributor-facing APIs continue to hide internal policy body details.
- Submitters, reviewers, finance actors, and auditors are denied on new setup
  visibility and approval endpoints. Project-scoped project_manager grants are
  future Workstream role-assignment work, not part of WS-POL-002.

## Allowed Files

```text
backend/app/modules/projects/router.py
backend/app/modules/projects/service.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/models.py
backend/app/interfaces/project_agents.py
backend/app/adapters/project_agents/openai_agent_sdk.py
backend/alembic/versions/**
backend/tests/test_alembic.py
backend/tests/test_projects.py
backend/tests/test_auth.py
docs/product_first_user_flows.md
docs/operations_project_operating_manual.md
docs/operations_queue_policy.md
docs/architecture_data_model.md
docs/architecture_checker_framework.md
docs/architecture_lifecycle_state_machine.md
docs/current_system_data_flow.html
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not Allowed

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/service.py
frontend or demo UI work
payment/reputation/blockchain settlement
compatibility aliases for removed guide payload fields
```

## Acceptance Criteria

- Project setup APIs show generated post-submit policy status without database
  inspection.
- Guide create/update request-body rejection for obsolete
  `post_submit_checker_policy` payload fields remains covered.
- Activation blocks unless the compiled post-submit policy is approved and
  matches the guide/source context.
- Approval provenance is immutable and records actor id, role, timestamp,
  source snapshot id/hash, and compiled policy hash.
- API responses are role-scoped and do not leak internal policy body to contributors.
- Negative authorization tests cover submitter, reviewer, finance, and auditor
  access. A future project-scoped role-assignment chunk must add unrelated
  project_manager denial once project-level roles exist.
- Visibility responses redact raw source text, local paths, secrets,
  credential-shaped values, replayable refs, and exact source hashes by default.
- Tests cover request-body rejection, approval, activation guard, and operator
  visibility.

## Verification Commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
(cd backend && .venv/bin/pytest tests/test_projects.py tests/test_auth.py -q)
(cd backend && .venv/bin/pytest tests/test_alembic.py -q)
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

- Confirm there is one authoritative server-owned post-submit policy path.
- Confirm obsolete manual payload fields are removed, not aliased.
- Confirm visibility is useful for operators but safe for contributors.

## Stop conditions

Stop and escalate if:

- scope must expand beyond allowed files
- architecture direction changes
- auth/payment/policy/data boundary changes beyond this contract
- CI/test weakening is required to pass
- the same blocker remains after 2 repair attempts
- secrets or production data are needed
