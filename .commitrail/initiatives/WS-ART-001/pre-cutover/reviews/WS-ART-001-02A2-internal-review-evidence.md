# Internal Review Evidence: WS-ART-001-02A2

## Chunk

`WS-ART-001-02A2`: Committed Source And Local Preparation

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: ae70bc2f10334f649c1af7f210e58ee378695a2b

Reviewed at: 2026-07-16T09:03:51Z

Reviewer run IDs: senior-engineering=019f6a24-31a2-7222-b83f-4a0bbcea7579; architecture=019f6a24-426b-7e11-9f7b-7ef4f00c3f17; QA/test=019f6a24-5137-7d43-9335-ea622d1861f6; security/auth=019f6a24-6db3-7f12-b9e0-1eabc39046d2; product/ops=019f6a24-9a10-7e92-b8db-ac2e8ea04e3f; reuse/dedup=019f6a24-b7cf-7e41-a1f5-57bb7aa7f5f4; CI-integrity=019f6a27-5582-7480-9810-972c89935a20; test-delta=019f6a27-6496-7d83-92bc-af1a778a9992; docs=019f6a27-5ba4-7d33-b799-07e838fe193e

AUTH-08 base-integration review run IDs: senior-engineering=019f6a07-2431-7eb1-81f3-57757b44d478; architecture=019f6a07-2d1c-7d90-95e8-985373837c24; QA/test=019f6a07-31f8-70a3-8742-a44cb3ecdf15; security/auth=019f6a07-3cbd-74f3-8d1d-0b930bd1c77e; product/ops=019f6a07-37d6-73c3-8cd0-cfcc390e7369; reuse/dedup=019f6a07-43d8-71d0-befe-9d3aa8a14140

After the reviewed SHA, only initiative review evidence and status files may
change without invalidating this review.

## Reviewed Change

- Added the inactive provider-neutral `PreparedArtifact` and
  `CommittedArtifactSource` boundary. A server commitment remains inseparable
  from the exact second-pass bytes.
- Added bounded, private, cross-process scratch custody with aggregate quota,
  file/concurrency limits, free-space admission, deadlines, stale cleanup, and
  fail-closed filesystem validation.
- Bound stale reservation ownership to Linux boot identity plus process start,
  preventing PID reuse from retaining abandoned quota.
- Kept anonymous read descriptors and ledger reservations under one cleanup
  owner until reader close and durable release both succeed.
- Added one shared bounded flock primitive for scratch and LocalStorage private
  operation locks, including cancellation-preserving timeout behavior.
- Preserved the active ArtifactStore v1 interface, provider selection, routes,
  schema, and product lifecycle.
- Expanded the cumulative 90 percent CI coverage contract to include the shared
  lock primitive.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Exact code SHA and focused gates passed. |
| QA/test | PASS | None | Exact cancellation identity, retryable `.part` custody, and lock-order proof passed. |
| security/auth | PASS | None | No auth, permission, secret, payment, or tenant boundary changed. |
| product/ops | PASS | None | No operator, contributor, reviewer, payment, or reputation workflow changed. |
| architecture | PASS | None | No alternate provider, factory, runtime, or product path was introduced. |
| CI integrity | PASS | None | The 78 percent repository gate and cumulative scoped 90 percent gates remain fail closed. |
| docs | PASS | None | Settings, defaults, scope, and inactive-cleanup behavior are documented. |
| reuse/dedup | PASS | None | Existing cancellation ownership helper is reused; test-only order instrumentation is localized. |
| test delta | PASS | None | No test was removed, skipped, xfailed, or weakened. |

## Valid Findings Addressed

- Rejected non-finite duration values instead of admitting `NaN` or infinity.
- Deferred root-marker content validation until after the ledger lock and made
  multiprocessing result collection bounded.
- Prevented failed reader close from releasing quota while bytes remained open.
- Closed the anonymous read descriptor when first-pass descriptor ownership
  became uncertain.
- Replaced the constructor's unbounded ledger lock with the shared deadline.
- Replaced PID-only stale ownership with boot/process-start identity.
- Replaced LocalStorage's unbounded private flock with the same bounded helper.
- Preserved the caller's `CancelledError` when a background lock acquisition
  later reaches its deadline.
- Preserved the exact original caller cancellation when unpublished temporary
  cleanup fails, retained the `.part` file under retryable intent ownership,
  and proved later canonical cleanup plus exact-request retry.
- Replaced timing-dependent marker-order proof with explicit spawned-child,
  lock-attempt, lock-acquired, and marker-validation events; widened only the
  bounded cold-start allowance after a reviewer reproduced a loaded-run flake.
- Integrated trusted `main` at AUTH-08 merge `aa0fdcd`, preserved ART-02A2 as
  the only active authored chunk, and corrected stale queue wording so AUTH-09
  and POL-002-04 remain inactive pending explicit user starts.

## Commands Run

```bash
cd backend && .venv/bin/ruff check app tests
cd backend && .venv/bin/pytest \
  tests/test_artifact_preparation.py \
  tests/test_local_artifact_store.py \
  tests/test_config.py -q \
  --cov=app.core.cancellation \
  --cov=app.core.file_locks \
  --cov=app.modules.artifacts.preparation \
  --cov=app.modules.artifacts.sources \
  --cov=app.core.config \
  --cov-report=term-missing --cov-fail-under=90
cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json <temporary-path>/result.json --timeout-seconds 900 -- \
  .venv/bin/python -m pytest tests/test_artifacts.py -q
cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json <temporary-path>/result.json --timeout-seconds 12600 -- \
  .venv/bin/python -m pytest tests/test_authorization.py tests/test_auth.py tests/test_alembic.py -q
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/test_agent_gates.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Results: Ruff passed; 154 focused tests passed at 94.40 percent scoped
coverage; the shared lock primitive is at 100 percent; 38 PostgreSQL artifact
integration tests passed in an isolated disposable database; 207 isolated
AUTH/authentication/Alembic integration tests passed on the merged base;
repository docstring coverage passed at 94.8 percent; 71 agent-gate tests
passed; stale artifact, stale wording, Markdown link, and diff checks passed.

The full repository suite and 78 percent whole-app floor remain authoritative
in GitHub Backend CI for the published evidence-bound head.

## Remaining Risks

- Linux `/proc` is an explicit runtime dependency of this Linux/`fcntl` scratch
  implementation and must remain true at hosted activation.
- Live-process ambiguous descriptor custody intentionally retains quota until
  explicit cleanup or process exit.
- `02A3` should consolidate temporary v1 digest/stream helpers during the clean
  cut instead of carrying duplicate conventions forward.
- This boundary remains inactive until the separately approved `02A3` cutover.

## Stop Condition

Publish the evidence-bound head for external CI, CodeRabbit, and human review.
Do not merge without explicit user approval and do not start `02A3`.
