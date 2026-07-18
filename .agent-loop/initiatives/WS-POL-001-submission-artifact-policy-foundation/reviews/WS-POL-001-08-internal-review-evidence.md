# Internal Review Evidence: WS-POL-001-08

## Chunk

WS-POL-001-08

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: ec9810bf1408a12a9840645481619744fcbebe0f

Reviewed at: 2026-07-05T21:46:07Z

Reviewer run IDs: local-senior-engineering-review-20260705T214607Z, local-qa-test-review-20260705T214607Z, local-security-auth-review-20260705T214607Z, local-product-ops-review-20260705T214607Z, local-architecture-review-20260705T214607Z, local-docs-review-20260705T214607Z, local-reuse-dedup-review-20260705T214607Z, local-ci-integrity-review-20260705T214607Z, local-test-delta-review-20260705T214607Z

Note: no callable sub-agent spawn tool was available in this Codex session. The
reviewer tracks below were run from the repository reviewer skill instructions,
and no external review is counted as internal review evidence.

## Reviewed Change

Branch: `codex/ws-pol-001-08-celery-project-setup`

Scope:

- Adds Celery and Redis-backed project setup worker boundary.
- Automatically creates a guide-source snapshot and enqueues project setup when
  a draft guide is created.
- Automatically enqueues setup when a later draft guide-source snapshot is
  captured.
- Runs guide sufficiency first, stops on blocking sufficiency, and creates only
  a draft `SubmissionArtifactPolicy` when sufficiency passes or passes with
  warnings.
- Keeps policy approval and deterministic `PreSubmitCheckerPolicy` compilation
  human-owned through the existing approval path.
- Removes construction-state compatibility surfaces: project payment fields,
  guide checklist fields, task-owned artifact requirement fields, generic
  checker-policy version locks, compatibility wrappers, and the obsolete React
  proposal source document.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Fixed queue preflight ordering, removed read-path queue checks, and made post-commit enqueue semantics truthful. Removed unused checker-policy wrapper methods. |
| QA/test | PASS AFTER FIXES | None | Added autostart coverage for no inline agent execution, eager Celery success, blocked sufficiency stop, later snapshot enqueue, queue-unavailable no-partial-persist behavior, read-path availability, and late enqueue failure. |
| security/auth | PASS AFTER FIXES | None | Pinned the Redis image digest; internal automation uses explicit `workstream_system` actor provenance; no Workstream-owned auth session path was added. |
| product/ops | PASS AFTER FIXES | None | Normal setup no longer depends on manually calling internal trigger endpoints; project owner still supplies guide/payment terms while Workstream derives draft intake policy for human approval. Read paths remain available even if setup queue config is missing. |
| architecture | PASS AFTER FIXES | None | Celery owns the product-job boundary; FastAPI request path does not run agents inline or block the event loop for broker checks; post-submit/review/revision/payment lifecycle was not redesigned. |
| docs | PASS AFTER FIXES | None | README, ADR, system architecture, first user flow, checker framework, Chunk 3 docs, PR trust bundle, and external review response describe the current behavior; obsolete non-canonical proposal source was removed. |
| reuse/dedup | PASS AFTER FIXES | None | Reused existing `ProjectService` agent methods, repository writes, and checker compiler path; removed redundant compatibility wrappers instead of adding aliases. |
| ci integrity | PASS AFTER FIXES | None | Added dependency and local broker without weakening CI/workflow gates; reran agent gate tests and demo UI build. |
| test delta | PASS AFTER FIXES | None | Replaced removed compatibility/backfill tests with current-schema absence assertions and new automatic setup behavior tests; no tests were skipped. |

## Valid Findings Addressed

- Queue preflight originally happened only at enqueue time, after the guide and
  source snapshot had already committed. The service now checks queue readiness
  after project/guide existence validation and before mutation, and a test
  proves no guide/snapshot rows persist when the queue is unavailable.
- CodeRabbit found that the queue readiness check had leaked into the
  `get_project` read path. That check was removed, and a test proves project
  reads do not require project setup queue configuration.
- CodeRabbit found that the synchronous Celery/Kombu readiness check ran
  directly inside async service methods. The service now offloads queue
  readiness and enqueue work through `asyncio.to_thread`.
- CodeRabbit found that enqueue failure after commit could return a false 503
  even though the write persisted. Post-commit enqueue failure is now logged and
  leaves the successful create response intact; tests cover guide and source
  snapshot late-enqueue failures.
- Redis was first added with a mutable image tag. The local Compose service now
  pins the current `redis:7` image index digest.
- The diff still contained compatibility-shaped wrapper methods for old checker
  policy names. Those wrappers were removed because no live call sites used
  them.
- The Week 2 drill still asserted the removed generic
  `locked_checker_policy_version` and discarded evaluation status. The drill now
  verifies the current guide, post-submit checker, review, revision, payment,
  guide-source snapshot, effective project policy, and pre-submit checker locks.
- A tracked non-canonical React proposal source still contained stale schema and
  lifecycle wording. It was deleted so active docs do not carry obsolete
  architecture.
- The chunk contract originally excluded files needed for the explicit
  no-compatibility cleanup. The contract now records the user-approved scope
  extension and the no-alias acceptance criterion.

## Commands Run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/python -m pytest tests/test_alembic.py -q
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q -k "create_guide_autostart or create_source_snapshot_autostart"
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q -k "create_guide_autostart or create_source_snapshot_autostart or get_project_does_not_require_project_setup_queue or post_commit_enqueue_fails"
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q -k "project_create_rejects_payment_fields or project_guide_rejects_unknown_non_contract_fields or project_guide_update_rejects_unknown_non_contract_fields or activation_uses_policy_bundle_without_guide_owned_artifact_fields"
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q
npm --prefix demos/week1_api_demo_ui run build
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/test_agent_gates.py
python3 scripts/check_loop_memory_state.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
docker buildx imagetools inspect redis:7
```

Results:

- ruff: passed.
- Alembic tests: 4 passed in 69.68s.
- Project autostart tests before external review fixes: 5 passed, 188 deselected in 90.53s.
- Focused project setup queue/autostart tests after external review fixes: 8 passed, 188 deselected in 73.39s.
- Project request-body/policy cleanup focused tests: 7 passed, 185 deselected in 93.82s.
- Full project-module suite before external review fixes: 193 passed in 1964.10s.
- Full project-module suite after external review fixes: 196 passed in 1612.80s.
- Week 1 API demo UI build: passed.
- Markdown link check: passed for 17 changed Markdown files.
- Stale wording check: passed.
- Agent gate tests: 26 passed.
- Loop memory state check: passed.
- Workstream static agent gate: `REVIEW_REQUIRED` for expected L1 diff size,
  risky migration/checker/auth paths, build configuration changes, and test
  delta breadth. Required reviewer tracks covered those findings.
- Diff whitespace check: passed.
- Redis image digest resolved to `sha256:b2b95679e3b46fb51864949ed25ea976fc3a6bcc00a40a1bc00d568cb2822e50`.

## Remaining Risks

- This chunk uses direct Celery enqueue after commit. The service now fails
  before mutation when the queue is clearly unavailable, but a future durable
  outbox would be the stronger pattern for broker outages that happen exactly
  after commit.
- Explicit setup trigger routes remain available for development and repair;
  the normal setup flow no longer depends on them.
- External GitHub Actions and CodeRabbit have not run for this local branch yet.
  They must run after a PR is opened and should be recorded separately as
  external review evidence.
