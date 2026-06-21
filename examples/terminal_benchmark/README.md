# Terminal Benchmark Example

This directory contains a real API drill based on a Terminal Benchmark reviewer
fixture. It is example material for validating Workstream behavior against a
realistic packet shape.

It is not Workstream product runtime code, not a required CI test, not formal
internal review evidence, and not a canonical checker implementation.

Do not cite files in this directory as proof that a Workstream implementation
chunk passed the zero-trust loop. Formal chunk evidence must live under the
approved `.agent-loop` or `docs/internal_reviews` paths for that chunk.

## Contents

- `terminal_benchmark_api_e2e.py`: runs a local Week 1 and Week 2 API drill
  against one Terminal Benchmark fixture.
- `LOCAL_VALIDATION_NOTES.md`: notes from the earlier local validation of the drill.

## Requirements

- Local Postgres test database only.
- `WORKSTREAM_TERMINAL_BENCH_FIXTURE` pointing at one local Terminal Benchmark
  fixture directory.
- Backend dependencies installed.

The script fails closed unless `WORKSTREAM_DATABASE_URL` points to local async
Postgres using `workstream_test` or `test_workstream`.

## Example

```bash
cd backend
WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test \
WORKSTREAM_TERMINAL_BENCH_FIXTURE=/path/to/terminal-benchmark-fixture \
.venv/bin/python ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
```
