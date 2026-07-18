# Chunk Contract: WS-POL-002-01 - Post-Submit Compiler Contract

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

Post-submit policy currently has a canonical body and hash, but it lacks a
trusted compiler contract equivalent to pre-submit. Before adding an agent,
Workstream needs deterministic compiler rules that prevent project policy from
weakening platform defaults or referencing unsupported checkers.

## Goal

Introduce the trusted compiler contract that produces the canonical
project-scoped `PostSubmitCheckerPolicy` body from a constrained spec.

This chunk is compiler-only. Durable provenance columns, setup-run output
fields, approval state, and guide activation changes are deferred to later
chunks so the first implementation remains reviewable.

## Target Behavior

- Compiler is owned by `backend/app/modules/projects/post_submit_policy.py`.
  `backend/app/modules/checkers/compiler.py` remains the pre-submit compiler
  module and must not import project post-submit policy helpers.
- Compiler always includes platform default durable post-submit checkers in
  `default_checkers` and `execution_checkers`.
- Compiler rejects unknown checker names.
- Compiler rejects attempts to remove or weaken defaults.
- Compiler rejects duplicate/conflicting checker classifications.
- Compiler rejects unsupported blocking-severity downgrade attempts.
- Compiler emits the canonical policy body and hash.
- Compiler supports default-only projects. A default-only constrained spec has
  empty project-specific `required_checkers` and `warning_checkers`; the
  compiled policy body still executes every platform default because
  `default_checkers` is stamped from the compiler's platform defaults and
  `execution_checkers` is compiled from that locked default list.
- `required_checkers` and `warning_checkers` represent project-specific routing
  classifications. They may reference registered non-default checkers, and
  `required_checkers` may also reference a default checker to tighten its
  routing for the project. Default-only projects leave both lists empty.
  Platform defaults remain mandatory through the compiler-owned default list
  and execution list, not by duplicating them into `required_checkers`.
- `policy_body.default_checkers` is a locked compiler output, not a runtime read
  from the mutable `DEFAULT_DURABLE_CHECKERS` constant.
- Platform blocking severities are `["critical", "high"]`, matching the
  existing checker runner. A constrained spec may tighten routing by adding
  known severities, but it cannot remove `critical` or `high`.
- Activation and runtime behavior are not changed in this chunk except where
  existing validation calls the canonical parser/body helpers. Persistence
  fields and setup-run statuses are defined in `WS-POL-002-02` and
  server-owned approval/activation enforcement remains in `WS-POL-002-03`.
- Existing real API drill scripts may be updated only to keep their bootstrap
  post-submit policy payloads aligned with the compiler's
  non-weakenable `["critical", "high"]` platform severity floor.

## Allowed Files

```text
backend/app/modules/projects/post_submit_policy.py
backend/app/modules/projects/service.py
backend/app/modules/projects/schemas.py
backend/tests/test_checkers.py
backend/tests/test_projects.py
backend/tests/test_tasks.py
backend/scripts/api_contract_e2e.py
examples/terminal_benchmark/terminal_benchmark_api_e2e.py
docs/architecture_checker_framework.md
docs/architecture_data_model.md
docs/architecture_lifecycle_state_machine.md
docs/operations_project_operating_manual.md
docs/operations_queue_policy.md
docs/operations_reviewer_workflow.md
docs/product_principles.md
docs/principles.md
docs/product_first_user_flows.md
docs/roadmap_30_day_master_plan.md
docs/roadmap_pilot_plan.md
docs/roles_permissions.md
docs/template_checker_policy.md
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not Allowed

```text
backend/app/adapters/project_agents/**
backend/app/modules/checkers/compiler.py
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/alembic/versions/**
backend/app/modules/tasks/**
frontend or demo UI work
payment/reputation/blockchain settlement
per-task checker generation
arbitrary generated checker code execution
```

## Acceptance Criteria

- A constrained post-submit checker spec can be compiled into a canonical
  project `PostSubmitCheckerPolicy` body.
- Default durable post-submit checkers are always present in
  `execution_checkers`.
- `policy_body.default_checkers` is copied from `DEFAULT_DURABLE_CHECKERS` at
  compile time and stamped with `compiler_version`; runtime validates the locked
  body by schema version, supported compiler version, canonical structure, and
  `policy_hash`, not by comparing old locked rows to today's default constant.
  This chunk must not change the `DEFAULT_DURABLE_CHECKERS` list; any future
  default-list change requires explicit human approval and security review in
  its own chunk.
- Default-only project policy compilation and activation are valid when all
  platform defaults remain present in `default_checkers` and
  `execution_checkers`.
- Unknown checker names fail closed.
- Duplicate or contradictory required/warning checker classifications fail
  closed.
- Policy hash equals `sha256(canonical_json(policy_body))`.
- Compiler implementation reuses or consolidates through existing
  `post_submit_policy.py` canonical body, hash, default-list, and locked-body
  parsing helpers instead of reimplementing a second post-submit canonicalizer.
- Compiler implementation must not introduce a reverse dependency from
  `backend/app/modules/checkers/compiler.py` into project modules.
- The locked-body parser rejects bodies whose `default_checkers` are malformed
  or inconsistent with `execution_checkers`; a locked body must also match the
  frozen default-checker snapshot for its stamped `compiler_version`. Later
  default-list constant changes therefore do not break older rows, but a v0.1
  body cannot invent a different v0.1 default list.
- Existing runtime tests still pass.
- Docs describe the compiler boundary and default checker list.

## Verification Commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
(cd backend && .venv/bin/pytest tests/test_projects.py tests/test_checkers.py -q)
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

- Confirm the compiler, not the agent, owns canonical runtime policy.
- Confirm project policy cannot weaken defaults.
- Confirm no task-specific checker generation is introduced.

## Stop conditions

Stop and escalate if:

- scope must expand beyond allowed files
- architecture direction changes
- auth/payment/policy/data boundary changes beyond this contract
- CI/test weakening is required to pass
- the same blocker remains after 2 repair attempts
- secrets or production data are needed
