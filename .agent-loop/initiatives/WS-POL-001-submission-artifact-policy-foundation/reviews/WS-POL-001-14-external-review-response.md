# External Review Response: WS-POL-001-14

## Scope

External review for PR #79.

This file tracks CodeRabbit, GitHub Actions, and GitHub review feedback. It is
separate from internal reviewer evidence so human reviewers can inspect external
findings without conflating them with Codex sub-agent review.

## CodeRabbit Findings

| Source | Finding | Decision | Resolution |
|---|---|---:|---|
| CodeRabbit | Concurrent `finalize_submission` calls could both pass the in-memory `locked_at` check and duplicate audit/checker side effects. | Valid | Added atomic `finalize_submission_if_unlocked()` conditional update, refreshed stale persisted rows on repeat finalize, and added tests asserting no duplicate checker runs or audit events. |
| CodeRabbit | `docs/current_system_data_flow.html` used stale "locked guide and policy versions" wording. | Valid | Reworded the public flow to say finalization records against the task's server-owned guide and policy context. |
| CodeRabbit | `operations_roles_permissions.md` combined precheck and finalization in one permission row. | Valid | Split into separate `Run submission precheck` and `Finalize submission` rows, and added multi-role precheck clarification. |
| CodeRabbit | `finalize_submission_if_unlocked()` mixes finalize naming with the internal `locked_at` column. | Valid | Added a docstring bridge explaining that `locked_at` remains the immutable storage boundary while the method follows public finalize terminology. |
| CodeRabbit | Let every `project_manager` read locked context for all tasks. | Rejected | This conflicts with the v0.1 scoped-operator security contract. Until project-scoped role assignments exist, non-admin project-manager access is limited to tasks the actor created. |

## GitHub Checks

Local checks were rerun before this response file was written. GitHub checks
must rerun after the fix push.

## Validation

```bash
cd backend && .venv/bin/ruff check app/modules/tasks/repository.py app/modules/tasks/service.py tests/test_tasks.py
cd backend && .venv/bin/ruff check app/modules/tasks/repository.py
cd backend && .venv/bin/pytest tests/test_tasks.py::test_finalize_submission_requires_operator_and_latest_version tests/test_tasks.py::test_submission_finalize_guard_is_atomic -q
cd backend && .venv/bin/pytest tests/test_tasks.py tests/test_checkers.py
cd backend && WORKSTREAM_DATABASE_URL=<local-test-db-url> .venv/bin/python scripts/api_contract_e2e.py
bash -lc 'set -a; set +a; export WORKSTREAM_DATABASE_URL=<local-test-db-url>; export WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL=${WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL:-gpt-4.1}; export WORKSTREAM_TERMINAL_BENCH_FIXTURE=<redacted-local-fixture-path>; export WORKSTREAM_TERMINAL_BENCH_GUIDE_ROOT=<redacted-local-guide-root>; backend/.venv/bin/python examples/terminal_benchmark/terminal_benchmark_api_e2e.py'
python3 scripts/check_markdown_links.py
git diff --check
```

Results:

- Focused Ruff: passed.
- CodeRabbit docstring-nitpick Ruff: passed.
- Focused finalize guard tests: 2 passed.
- Task/checker suite: 133 passed.
- API contract real API E2E: passed.
- Terminal Benchmark real API E2E: passed.
- Markdown links: passed for 27 changed Markdown files.
- Stale wording scan: passed with no matches.
- Diff whitespace check: passed.

## Remaining External Review State

The fix commit must be pushed so CodeRabbit and GitHub Actions can rerun against
the final branch head.
