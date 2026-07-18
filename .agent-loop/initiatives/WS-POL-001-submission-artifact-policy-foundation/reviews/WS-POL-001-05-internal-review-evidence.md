# Internal Review Evidence: WS-POL-001-05

## Chunk

WS-POL-001-05

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 5019afc57e7c6f5f7488f26a05b11c65a33e9f18

Reviewed at: 2026-07-04T20:36:49Z

Reviewer run IDs: senior-engineering-final-local-review, security-auth-final-local-review, product-ops-final-local-review, architecture-final-local-review, docs-final-local-review, reuse-dedup-final-local-review, 019f2e80-d494-7920-a91e-4912b798ecf1, 019f2e80-fa13-7783-85f1-621fc9ebf468, 019f2e84-7ade-7fa2-a314-e0487b2a8154

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Confirmed the revision/resubmission lifecycle is bounded to this chunk and does not introduce human review, payment, reputation, or frontend scope. |
| QA/test | PASS AFTER FIXES | None | Verified the real API drill covers checker-caused `needs_revision`, fixed v2 resubmission, non-owner privacy, malicious payload rejection, trusted retry, and no-row pre-submit blocking. |
| security/auth | PASS AFTER FIXES | None | Confirmed worker-visible checker responses and audit events redact internal manifest/auth fields, non-owning worker access returns privacy-safe 404s, and fake checker-result payloads create no side effects. |
| product/ops | PASS | None | Confirmed worker-facing outcomes remain `pre_submission_checker_failed`, `needs_revision`, and `review_pending`, while post-submission evaluation uses `evaluation_pending` internally. |
| architecture | PASS | None | Confirmed the chunk preserves project-scoped pre-submit and post-submit policy boundaries and does not reintroduce per-task checker derivation. |
| CI integrity | PASS | None | Confirmed no workflow/package/test-gate weakening; stale-token gate and its runner coverage were strengthened. |
| docs | PASS | None | Confirmed docs use `evaluation_pending` consistently and preserve the user-facing review decision contract. |
| reuse/dedup | PASS WITH LOW RISKS | None | Confirmed required-checker warning escalation is centralized in the checker service rather than duplicated in individual checkers. |
| test delta | PASS AFTER FIXES | None | Confirmed test additions strengthen assertions without skips, monkeypatch shortcuts, or weakened expectations. |

## Valid Findings Addressed

- Replaced the legacy post-submission evaluation lifecycle token with `evaluation_pending` and added migration coverage for `workstream_tasks.status`, `audit_events.from_status`, and `audit_events.to_status`.
- Added a stale-wording gate regression so split-string reconstruction of the legacy status is caught by `scripts/check_stale_workstream_wording.py` and executed by `scripts/test_agent_gates.py`.
- Moved required-checker warning escalation into the checker service so required warnings deterministically become blocking post-submit failures while optional warnings remain non-blocking.
- Strengthened checker-caused revision coverage: v1 reaches `needs_revision`, no human review decision is created, worker-visible results contain actionable fix data, stale v1 checker retry is rejected, and fixed v2 reaches `review_pending`.
- Proved pre-submit failure remains non-durable: blocked pre-submit scenarios create no submission, no checker run, no evidence rows, and no audit side effects.
- Hardened worker privacy: non-owning workers receive 404s without side effects, worker checker responses omit internal manifests, and worker-visible checker-gate audit entries redact actor/auth metadata.
- Added trusted retry proof for the post-submit evaluation window: `review_pending -> evaluation_pending -> review_pending`.
- Expanded database invariants to verify no removed legacy evaluation status remains and submission/task locked policy context remains stable through revision and resubmission.

## Commands Run

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

## Results

```text
Full Postgres-backed backend suite passed: 325 passed in 2296.09s.
Ruff app/tests/scripts passed.
Docstring coverage passed: 100.0% (542/542).
Stale wording check passed.
Agent gate tests passed: 26 agent gate tests passed.
Markdown link check passed for 20 changed Markdown files.
Loop memory state check passed.
git diff --check passed.
Week 1 real API e2e passed.
Week 2 real API e2e passed.
Week 2 summary: trusted_retry=review_pending->evaluation_pending->review_pending; checker_caused_revision=needs_revision; fixed_resubmission=review_pending; task_setup_blocked=evaluation_pending->review_pending.
Static agent gate result: REVIEW_REQUIRED because this is a large risk-sensitive migration/runtime/test/docs chunk. Internal reviewer tracks completed and accepted the risk.
```

## Remaining Risks

- `evaluation_pending` is now the persisted/API token for the post-submission evaluation window. Any external dashboard expecting the removed legacy token must be updated before consuming this branch.
- Post-submit checker execution is still local service execution for v0.1. Durable distributed workers remain later infrastructure, not part of this chunk.
- Human review decision implementation remains a later chunk; this chunk only proves checker-caused revision and resubmission back to `review_pending`.
