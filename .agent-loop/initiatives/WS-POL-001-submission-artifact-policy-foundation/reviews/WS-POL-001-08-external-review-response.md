# External Review Response: WS-POL-001-08

## Chunk

WS-POL-001-08

## Reviewed Revision

Reviewed code SHA: ec9810bf1408a12a9840645481619744fcbebe0f

Reviewed at: 2026-07-05T21:46:07Z

External source: CodeRabbit review on PR #69

## Comments Addressed

| Source | Severity | Finding | Resolution |
|---|---:|---|---|
| CodeRabbit | Critical | `get_project` called project setup queue readiness even though it is a read path, which could make reads return 503 when Celery is not configured. | Removed the queue readiness check from `get_project`; added `test_get_project_does_not_require_project_setup_queue`. |
| CodeRabbit | Major | Celery broker readiness used blocking Kombu network I/O directly inside async service methods. | Converted the service queue readiness path to `await asyncio.to_thread(...)`, keeping the Celery adapter synchronous but not blocking the event loop. |
| CodeRabbit | Major | A broker failure after commit could return 503 even though guide/source snapshot rows were already persisted. | Split pre-mutation readiness from post-commit enqueue. Preflight still fails before mutation when the queue is clearly unavailable; post-commit enqueue failure is logged and the durable create response remains successful. Added guide and source-snapshot tests for late enqueue failure. |

## Comments Deferred

None.

## Human Decisions Needed

None. The fixes preserve the approved product behavior:

- setup remains automatic when guide/source material is captured;
- the request path does not run agents inline;
- Celery remains the project setup worker boundary;
- no backward-compatibility alias or legacy field was restored.

## Commands Rerun

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q -k "create_guide_autostart or create_source_snapshot_autostart or get_project_does_not_require_project_setup_queue or post_commit_enqueue_fails"
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Results:

- ruff: passed.
- Focused project setup queue/autostart tests: 8 passed, 188 deselected.
- Full project-module suite: 196 passed in 1612.80s.
- Stale wording check: passed.
- Markdown link check: passed for 16 changed Markdown files.
- Diff whitespace check: passed.

## Remaining Risks

Direct enqueue after commit is now semantically honest for the API caller, but a
future durable outbox remains the stronger production pattern for guaranteed
eventual enqueue after broker outages.
