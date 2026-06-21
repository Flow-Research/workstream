# Terminal Benchmark Real API Drill Local Validation Notes

This file records local validation notes for the Terminal Benchmark example
drill. It is not Workstream internal-review evidence for a product chunk and
does not make this example part of required CI.

Date: 2026-06-15

Example scope:

- `examples/terminal_benchmark/terminal_benchmark_api_e2e.py`
- historical local checker revision experiment, not included in this example
- historical local checker tests, not included in this example

Purpose:

Use a real Terminal Benchmark reviewer fixture as a Week 1 and Week 2 API drill:

- project and active guide creation
- task screening, release, claim, and start
- pre-submit checker feedback for intake
- submission packet creation
- submission lock
- automatic durable checker gate
- `review_pending`
- `needs_revision`
- fixed resubmission from revision state

## Local Observations

Engineering observations:

- The default fixture path was private/local, and ambiguous fixture file
  selection could hide mixed artifacts.
- The pre-submit checker set and persisted fixture artifact/evidence contract
  were under-asserted.
- The example now requires an explicit `WORKSTREAM_TERMINAL_BENCH_FIXTURE`,
  fails on ambiguous fixture matches, and asserts pre-submit checker set,
  artifact manifest, evidence rows, hashes, sizes, labels, checker statuses,
  and checker counts.

QA observations:

- Successful pre-submit non-durability and exact checker result counts were not
  proven in the first local draft.
- The fixed revision packet skipped pre-submit feedback in the first local draft.
- The example asserts no durable submissions are created by pre-submit checks,
  exact run counters and statuses match expectations, and the fixed revision
  packet runs pre-submit feedback before v2 submission.

Security observations:

- An inherited non-local database override could allow writes outside local test
  Postgres.
- Fixture paths could leak through persisted identifiers or normal success
  output.
- The example uses a strict local-only Postgres guard, derives a stable fixture
  id from content hashes, persists sanitized fixture identifiers, and normal
  success output does not print the absolute fixture path.

Product/ops observations:

- Demo worker profile bootstrap could be confused with canonical workflow.
- Locked wording used time-relative and external-tool-specific phrasing.
- Demo bootstrap is explicitly labeled as non-canonical v0.1 setup, output
  includes `worker_profile_setup=demo_bootstrap_not_canonical_workflow`, and
  guide/submission wording uses stable Terminal Benchmark fixture language.

## Validations

Commands run:

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage app scripts --config .docstr.yaml
git diff --check
cd backend && .venv/bin/python -m pytest tests/test_checkers.py -k 'pre_submit_check_allows_worker_revision_packet_feedback or pre_submit_check_returns_feedback_without_durable_run'
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test WORKSTREAM_TERMINAL_BENCH_FIXTURE=/path/to/terminal-benchmark-fixture .venv/bin/python ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
cd backend && .venv/bin/python -m pytest
```

Results:

- ruff passed
- docstring coverage passed at 100.0%
- diff whitespace check passed
- targeted checker tests passed: 2 passed
- Terminal Benchmark real API drill passed
- full backend pytest passed: 115 passed

These notes are historical local validation notes only. They do not certify any
future chunk and do not replace required internal reviewer evidence.
