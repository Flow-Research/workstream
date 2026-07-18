# External Review Response: WS-POL-002-01

## Source

PR #87 external checks.

## Comments Addressed

### Backend CI failure

Status: addressed.

Finding:

- The Backend workflow failed in `tests/test_tasks.py` at
  `test_screening_uses_persisted_post_submit_policy_body_after_default_drift`.
  The test name and assertion did not reflect the final versioned compiler
  contract for locked post-submit policy bodies.

Decision:

- The old expectation was stale under `WS-POL-002-01`. The compiler now stamps
  `compiler_version` and the emitted default list into `policy_body`. Runtime
  validates the locked body by supported compiler version, internal consistency,
  and `policy_hash`, not by comparing old locked rows to today's mutable
  `DEFAULT_DURABLE_CHECKERS` constant. Future default-list changes still require
  explicit versioning or migration work and must not silently reinterpret old
  locked bodies.

Fix:

- Renamed the test to
  `test_screening_uses_versioned_post_submit_policy_body_after_default_drift`.
- Updated the assertion to expect `200` and verify that screening stamps the
  persisted v0.1 policy body and hash after a later mutation to the current
  default-checker constant.
- Added parser regression coverage for unsupported compiler versions and
  self-consistent default-list drift that does not match the frozen v0.1
  compiler snapshot.

Verification:

```bash
cd backend && .venv/bin/pytest tests/test_tasks.py::test_screening_uses_versioned_post_submit_policy_body_after_default_drift -q
cd backend && .venv/bin/ruff check tests/test_tasks.py
```

Results:

- Focused CI-fix test: 1 passed.
- Ruff: passed.

Internal post-fix review:

- QA/test: PASS.
- Test delta: PASS.

## External Check Status

- Backend, Agent Gates, and CodeRabbit passed on the previous push.
- This file now includes additional unpushed fixes for the versioned default
  snapshot contract. GitHub Actions and CodeRabbit must rerun after this fix
  push before the PR is considered externally clear.

## Comments Deferred

None.

## Human Decisions Needed

None before human merge review.

## Commands Rerun

```bash
cd backend && .venv/bin/pytest tests/test_tasks.py::test_screening_uses_versioned_post_submit_policy_body_after_default_drift -q
cd backend && .venv/bin/ruff check tests/test_tasks.py
```

## Remaining Risks

- External checks are pending rerun for this unpushed fix diff. Human merge
  review is still required after the rerun is green.
