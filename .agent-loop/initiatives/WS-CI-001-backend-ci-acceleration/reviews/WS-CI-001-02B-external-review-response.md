# External Review Response

## Chunk

`WS-CI-001-02B` — Exact-Custody Semantic Test Lanes

## Source

CodeRabbit inline review on PR #198, posted 2026-07-24 against `f5d2abd7`.

## Comments addressed

All fourteen comments were valid and addressed:

1. Standardized `parameterized` and `full-service` wording.
2. Clarified that the rebalance preserved the final workflow contract and gates.
3. Replaced the absolute Ruff claim with the observed resolver-drift failure.
4. Synchronized status history with reviewed and hosted node evidence.
5. Initially clarified the 480-second failure behavior. After exact-head hosted
   proof exceeded the target while every correctness and coverage gate passed,
   the owner explicitly accepted the measured risk and required the accepted
   performance target not to leave the required check permanently red.
6. Mapped `git rev-parse` failures to the stable isolated-runner error contract.
7. Preserved `KeyboardInterrupt` and `SystemExit` during MinIO bucket creation.
8. Preserved failed lane evidence when isolation metadata was never created.
9. Reported pytest collection failure before manifest validation.
10. Preserved exactly four failed lane rows after runtime and partial-startup
    orchestration failures.
11. Removed inherited `PYTEST_ADDOPTS` and `PYTEST_PLUGINS` from independent
    collection.
12. Made UUID restoration unconditional in the validator regression test.
13. Documented PostgreSQL as the service container and MinIO as an in-step,
    loopback-published container with a health loop.
14. Added an Agent Gate assertion for the step that reads `run.exit` and fails
    the required check.

## Comments deferred

None.

## Human decisions needed

The repository owner explicitly accepted the measured timing risk from hosted
runs `30121249272` and `30123755007` and deferred further speed optimization.
The workflow continues to record whether the 480-second target was met, but an
accepted performance miss no longer overrides successful test, custody,
coverage, isolation, and service-contract gates.

## Commands rerun

```bash
cd backend
ruff check app tests scripts
python -m pytest -q tests/test_ci_test_lanes.py tests/test_test_lane_evidence.py tests/test_isolated_database_runner.py -k '<non-service selection>'
cd ..
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py <changed Markdown files>
git diff --check
```

Local result before final evidence binding: exact Ruff passed, 89 focused
non-service tests passed, 11 service-backed tests remained mandatory for hosted
CI, and all 100 Agent Gate tests passed.

## Internal repair review

Reviewed code SHA: `24f3b638b175352ddce3548d8c247b65c3328087`

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test-delta tracks passed. Low residual risks
are limited to generic synthetic failure codes and reliance on job logs for the
parent-side orchestration cause.

## Remaining risks

- The final repair head still requires fresh GitHub Agent Gates, Backend, and
  external review.
- The eight-minute goal remains unmet and is explicitly visible in hosted
  evidence through `timing_target_met: false`; optimization remains deferred.
