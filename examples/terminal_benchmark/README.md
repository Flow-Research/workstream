# Terminal Benchmark Example

This directory contains Terminal Benchmark example material used to validate
Workstream behavior against a realistic external-project packet shape.

It is not Workstream product runtime code, not a required CI test, not formal
internal review evidence, and not a canonical checker implementation.

Do not cite files in this directory as proof that a Workstream implementation
chunk passed the zero-trust loop. Formal chunk evidence must live under the
approved `.agent-loop` or `docs/internal_reviews` paths for that chunk.

## Contents

- `terminal_benchmark_api_e2e.py`: manual real-API drill that exercises the
  current setup-agent policy-bundle route with a local Terminal Benchmark
  source-material directory and the OpenAI Agents SDK runtime.
- `LOCAL_VALIDATION_NOTES.md`: notes from the earlier local validation of the drill.

## Requirements

- Local Postgres test database only.
- `OPENAI_API_KEY`.
- `WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL`.
- `WORKSTREAM_TERMINAL_BENCH_FIXTURE` pointing at one local Terminal Benchmark
  source-material directory.
- `WORKSTREAM_TERMINAL_BENCH_GUIDE_ROOT` when the source-material directory is not under a
  Terminal Benchmark reference root containing `PROJECT_GUIDE.md` and
  `REVIEWER_PROGRAM.md`.
- Backend dependencies installed.

The script fails closed unless `WORKSTREAM_DATABASE_URL` points to local async
Postgres using `workstream_test` or `test_workstream`.

The script suppresses raw per-request progress paths and redacts fixture-derived
identifiers plus local Workstream UUIDs in stdout by default, so copied output
is safe for public PR evidence. Set
`WORKSTREAM_TERMINAL_BENCH_PRINT_RAW_LOCAL_IDS=1` only for local debugging.

The source-material path should point at a local Terminal Benchmark reference directory containing
`extracted/task.toml`, one `*_submission_*.zip`, one `review_packet_*.md`,
`static_guard.txt`, `docker_build.log`, `oracle_test.log`, and
`starter_m1_test.log`. Keep the concrete local path in your shell environment;
do not commit operator-specific source-material paths.

The script uses the OpenAI Agents SDK runtime. It has no deterministic local
runtime fallback.

## Manual Proof Shape

The authoritative proof for `WS-POL-001-06` was a live manual HTTP drill:

1. create a project;
2. create a project guide containing Terminal Benchmark submission, review, task, and
   review packet material;
3. create a guide-source snapshot with source hashes and excerpts;
4. run the guide sufficiency agent endpoint;
5. run the submission artifact policy derivation agent endpoint;
6. create an admin-reviewed exact project submission artifact policy;
7. approve the policy and activate the guide;
8. create, screen, release, claim, and start a task;
9. run pre-submit checks, blocked submission creation, successful submission
   creation, submission finalization, durable checker run, and revision resubmission
   through the HTTP APIs.

## Manual Drill Command

```bash
cd backend
WORKSTREAM_DATABASE_URL=<local-test-db-url> \
OPENAI_API_KEY="$OPENAI_API_KEY" \
WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL="${WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL:?set model}" \
WORKSTREAM_TERMINAL_BENCH_FIXTURE=<redacted-local-fixture-path> \
WORKSTREAM_TERMINAL_BENCH_GUIDE_ROOT=<redacted-local-guide-root> \
.venv/bin/python ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
```
