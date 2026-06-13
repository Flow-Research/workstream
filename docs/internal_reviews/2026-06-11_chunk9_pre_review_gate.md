# Internal Review Evidence: Chunk 9 Pre-Review Gate

## Scope

- automatic checker run after submission lock
- task lifecycle movement through `auto_checking`
- checker-caused `needs_revision`
- internal `task_setup_blocked` repair route
- worker redaction for checker and audit output
- latest submission and retry behavior

## Required Tracks

### Senior Engineering

Status: passed after fixes.

Findings addressed:

- submission lock and automatic checker gate now commit atomically; failed checker policy validation no longer leaves a half-locked submission
- checker-driven task status changes now use the shared lifecycle transition guard
- checker and gate audit payloads include `trigger_source`
- tests assert gate events for pass, needs-revision, and blocked outcomes

### QA/Test

Status: passed after fixes.

Findings addressed:

- v1 auto `needs_revision` followed by v2 lock and auto `review_pending` is covered through API tests
- internal `task_setup_blocked` repair and manual retry to `review_pending` is covered
- checker-caused `needs_revision` task status is asserted directly
- gate audit events are asserted for clean, worker-fixable, and task-setup-blocked flows

### Security/Auth

Status: passed after fixes.

Findings addressed:

- worker task audit responses now redact internal checker routing, checker run ids, setup defect names, and gate reasons
- worker checker-run responses continue to hide internal `task_setup_blocked` routing and non-worker-visible results
- lock and checker gate are atomic, so policy failures do not create unrecoverable partial lock state
- audit redaction is covered by an assigned-worker API test

### Product/Ops

Status: passed.

Findings addressed:

- worker-facing outcomes remain simple: `needs_revision`, `accepted`, or `rejected`
- `task_setup_blocked` remains an internal checker routing recommendation, not a worker-facing outcome
- `pre_review_gate` is documented as a checker/audit phase while the persisted task state is `auto_checking`
- readiness proof is documented as current `CheckerRun` data; a separate readiness certificate remains optional later work

## Verification

- `cd backend && .venv/bin/python -m ruff check app tests scripts`
- `cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_checkers.py tests/test_tasks.py -q`
- `cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest -q`

## Final Gate

Valid findings addressed: yes.

Open sub-agent sessions: none.
