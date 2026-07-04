# PR Trust Bundle: WS-POL-001-05

## Chunk

`WS-POL-001-05` - Revision Resubmission And Real API Drill

## Goal

Prove the current Workstream backend can move from project setup through task submission, post-submit evaluation, checker-caused `needs_revision`, fixed worker resubmission, and return to `review_pending` using real API calls and persisted Postgres state.

## Human-Approved Intent

- Intent: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/INTENT.md`
- Plan: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/PLAN.md`
- Chunk contract: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-05-revision-resubmission-real-api-drill.md`

## What Changed

- Added `evaluation_pending` as the canonical persisted/API task status for the post-submission evaluation window.
- Added migration `0009_evaluation_pending_status` to rewrite existing task and audit rows from the legacy token.
- Updated checker execution so post-submit runs enter `evaluation_pending` and then route to `review_pending`, `needs_revision`, or setup retry paths.
- Centralized required-checker warning escalation so required warnings become blocking post-submit failures.
- Proved checker-caused `needs_revision` with fixed v2 resubmission using real API flows.
- Hardened worker-visible checker and audit responses so internal manifest/auth details do not leak.
- Expanded Week 1/Week 2 real API drills, backend integration tests, stale-wording gates, and docs.

## Why It Changed

The worker-facing lifecycle needs to stay simple: pre-submit checker failure blocks submission creation, post-submit checker failures that the worker can fix become `needs_revision`, and successful automated evaluation reaches `review_pending`. Internally, the post-submission evaluation window needed a clear status name that does not sound like a product review decision or a checker implementation detail.

## Design Chosen

The persisted token is `evaluation_pending`. UI/display text may render this as `EVALUATION_PENDING`, but database/API records use the lowercase token.

Post-submit checker execution now uses this flow:

```text
submitted/review_pending
-> evaluation_pending
-> review_pending | needs_revision | internal setup retry
```

Pre-submit checker failures remain non-durable and return `pre_submission_checker_failed`; they do not create a submission. Post-submit checker failures are durable because a submission already exists. Required checker warnings are escalated once in the checker service so individual checkers cannot disagree about required severity.

## Alternatives Rejected

- Keep the removed legacy evaluation status name: rejected because it is vague and does not describe the broader post-submission evaluation window.
- Use `checker_retry` or operator-oriented names for all retry paths: rejected because trusted retry is internal infrastructure, while user-facing workers should only see actionable outcomes.
- Let individual checkers escalate required warnings: rejected because severity must be enforced centrally from the locked post-submit policy.

## Scope Control

Allowed implementation surface:

- `backend/alembic/versions/**`
- `backend/app/modules/checkers/**`
- `backend/app/modules/tasks/**`
- `backend/scripts/week1_api_e2e.py`
- `backend/scripts/week2_api_e2e.py`
- `backend/tests/**`
- `scripts/check_stale_workstream_wording.py`
- `scripts/test_agent_gates.py`
- Chunk-approved docs and `.agent-loop/` files

No frontend, human review decision implementation, payment/reputation/blockchain code, object storage, auth provider changes, agent runtime redesign, or per-task checker derivation was added.

## Product Behavior

- Worker pre-submit failure: `pre_submission_checker_failed`; no submission row is created.
- Worker-fixable post-submit checker failure: task becomes `needs_revision`.
- Fixed worker resubmission: creates a new submission version and returns to `review_pending` after automated checks pass.
- Internal post-submit evaluation window: persisted/API status `evaluation_pending`; display label can be `EVALUATION_PENDING`.
- Product review decision stored values remain only `accept`, `needs_revision`, and `reject`.

## Acceptance Criteria Proof

- Revision flow: Week 2 real API drill proves v1 checker-caused `needs_revision`, v2 replacement, stale v1 retry rejection, and final `review_pending`.
- Status rename: migration test proves removed legacy evaluation rows rewrite to `evaluation_pending` and downgrade reverses.
- No legacy persisted status: Week 2 DB invariants assert no old status remains in task or audit status columns.
- Worker privacy: integration tests assert non-owner privacy 404s, worker checker response redaction, and worker audit redaction.
- No fake side effects: API tests prove malicious internal checker-result payloads are rejected without task/submission/checker/audit side effects.
- Pre-submit remains non-durable: real API drill proves blocked pre-submit scenarios create no submission/checker/evidence/audit rows.
- Real API proof: Week 1 and Week 2 scripts run through FastAPI app paths against Postgres.

## Tests And Checks Run

```bash
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@127.0.0.1:5433/workstream_test .venv/bin/python -m pytest tests
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
git diff --check
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@127.0.0.1:5433/workstream_test .venv/bin/python scripts/week1_api_e2e.py
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@127.0.0.1:5433/workstream_test .venv/bin/python scripts/week2_api_e2e.py
```

Result summary:

```text
Full backend suite: 325 passed in 2296.09s.
Ruff: passed.
Docstring coverage: 100.0%.
Stale wording: passed.
Agent gate tests: 26 passed.
Markdown links: passed for 20 changed Markdown files.
Loop memory state: passed.
git diff --check: passed.
Week 1 real API e2e: passed.
Week 2 real API e2e: passed, including checker_caused_revision=needs_revision and fixed_resubmission=review_pending.
Static agent gate: REVIEW_REQUIRED for L1 migration/runtime/test/docs risk; internal reviewers accepted after fixes.
```

## Test Delta

### Tests added

- Alembic migration coverage for `0009_evaluation_pending_status`.
- Checker-caused revision and fixed resubmission API coverage.
- Worker checker/audit redaction coverage.
- Non-owner and malicious payload no-side-effect coverage.
- Stale-wording regression for split legacy status reconstruction.

### Tests modified

- Week 1 and Week 2 real API drills now assert `evaluation_pending` behavior and stronger database invariants.
- Existing submission ownership test now expects privacy-safe 404 for a non-owning worker submission-create attempt.

### Tests removed/skipped

- None.

## CI Integrity

- [x] Coverage threshold unchanged
- [x] Lint unchanged
- [x] Typecheck unchanged
- [x] No workflow weakening
- [x] No package script weakening
- [x] No unpinned new GitHub Action
- [x] Checkout credential persistence unchanged

## External Review

External review is tracked separately in:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-05-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Rate-limited | Status context is green, but detailed review did not run on latest head. Human can retry with `@coderabbitai review` when available. |
| GitHub checks | Passed | Agent Gates, Backend, and Week 1 API Demo UI passed. |

Internal review evidence does not replace external review.

## Reviewer Results

Reviewed code SHA: `5019afc57e7c6f5f7488f26a05b11c65a33e9f18`

Reviewed at: `2026-07-04T20:36:49Z`

Reviewer run IDs: see `WS-POL-001-05-internal-review-evidence.md`.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Scope and maintainability reviewed. |
| QA/test | PASS AFTER FIXES | None | Real API drill and edge cases reviewed after fixes. |
| security/auth | PASS AFTER FIXES | None | Worker privacy and no-side-effect paths reviewed after fixes. |
| product/ops | PASS | None | Lifecycle wording and worker-facing semantics reviewed. |
| architecture | PASS | None | Project/checker boundaries reviewed. |
| CI integrity | PASS | None | No gate weakening found. |
| docs | PASS | None | Docs and status naming reviewed. |
| reuse/dedup | PASS WITH LOW RISKS | None | Centralized escalation accepted. |
| test delta | PASS AFTER FIXES | None | Strengthened test assertions accepted. |

## Remaining Risks

- Existing external consumers must migrate from the old internal status token to `evaluation_pending`.
- Durable distributed checker workers remain future work; this chunk keeps v0.1 local execution semantics.
- Human review decision endpoints are still later work.

## Follow-Up Work

- Open the PR and capture CodeRabbit/GitHub review in the external review response file.
- After merge, update loop memory and stop before starting the next chunk.

## Human Review Focus

Please inspect:

- `evaluation_pending` status transitions and migration rewrite/downgrade.
- Checker-caused `needs_revision` and v2 resubmission behavior.
- Required-checker warning escalation in the checker service.
- Worker privacy redaction in checker and audit responses.
- Real API drill assertions in `backend/scripts/week2_api_e2e.py`.

## Human Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
