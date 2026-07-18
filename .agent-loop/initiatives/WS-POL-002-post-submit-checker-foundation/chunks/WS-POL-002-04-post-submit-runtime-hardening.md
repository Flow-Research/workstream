# Chunk Contract: WS-POL-002-04 - Locked Runtime Execution And Routing Hardening

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

Runtime already locks and executes post-submit policy, but it must be hardened
against the new generated/approved policy source and prove routing behavior
against worker-fixable failures, internal setup defects, and trusted retries.

## Goal

Harden only the runtime deltas introduced by generated and approved project
`PostSubmitCheckerPolicy` records, while preserving already-proven finalization,
locked-policy validation, and checker routing behavior.

## Target Behavior

- Task locked context stamps the generated, approved post-submit policy
  provenance added by WS-POL-002.
- Finalization rejects generated-policy source snapshot or approval provenance
  mismatches before checker execution.
- Internal setup and retry routes expose bounded reason, owner, next action, and
  retry/audit provenance to authorized operators only.
- Reviewers receive tasks only after the task reaches `review_pending`.
- Existing worker-fixable `needs_revision`, internal `task_setup_blocked`, and
  trusted `checker_retry` semantics are regression-tested, not redesigned.

## Allowed Files

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/app/modules/projects/service.py
backend/tests/test_tasks.py
backend/tests/test_checkers.py
backend/scripts/api_contract_e2e.py
docs/architecture_lifecycle_state_machine.md
docs/architecture_checker_framework.md
docs/operations_queue_policy.md
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not Allowed

```text
backend/app/adapters/auth/**
frontend or demo UI work
payment/reputation/blockchain settlement
per-task checker generation
new review decision values
```

## Acceptance Criteria

- Generated approved post-submit policy provenance is locked onto tasks and
  submissions.
- Finalization fails closed for missing/stale/mismatched generated-policy
  source snapshot, approval, or hash provenance.
- Operator-visible internal route responses include bounded reason, owner, next
  action, retry eligibility, and audit event id.
- Worker-facing responses hide internal setup blocked and checker retry routes.
- Reviewers cannot access tasks/runs before `review_pending`.
- Checker-caused `needs_revision` keeps `outcome_source = auto_checker` and
  does not create or reference a human review decision id.
- Existing pre-submit behavior is unchanged.
- Tests cover new generated-policy provenance mismatches plus regression cases
  for pass, worker-fixable failure, setup blocked, trusted retry, stale
  submission, and stale policy body behavior.

## Verification Commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
(cd backend && .venv/bin/pytest tests/test_tasks.py tests/test_checkers.py -q)
(cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py)
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

- Confirm post-submit routing remains distinct from review decisions.
- Confirm worker-facing responses stay understandable.
- Confirm no pre-submit regression is introduced.

## Stop conditions

Stop and escalate if:

- scope must expand beyond allowed files
- architecture direction changes
- auth/payment/policy/data boundary changes beyond this contract
- CI/test weakening is required to pass
- the same blocker remains after 2 repair attempts
- secrets or production data are needed
