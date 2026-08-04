# WS-QUAL-001-02R External Review Response

## CodeRabbit finding addressed

CodeRabbit correctly found that three new tests cleared the cached settings
only inline. A failing assertion could therefore leave an environment-derived
`Settings` object cached after `monkeypatch` restored the environment.

The repair adds `isolated_project_settings_cache`, which clears before the test
and unconditionally clears in a `finally` block. The submission-policy approval
test and both parameterized queue tests use the fixture. Inline cache clearing
was removed.

## Verification

- `cd backend && .venv/bin/ruff check tests/test_projects.py` — pass.
- Repaired focused selection — 5 passed, 376 deselected in 52.59 seconds.
- `git diff --check` — pass.

## Deferred comments

None.

## Hosted coverage correction

Backend run `30902039458` passed all five semantic lanes and the final fan-in
on repaired head `055b0db4`. It completed 2,995 tests with 21,003 / 23,455
covered statements (89.545939 percent), 671.329 seconds total hosted wall time,
and a 500.118-second slowest lane. Runtime remained within the contract, but
coverage missed the 89.55-percent target by one statement.

The final test exercises the real project-agent composition boundary and
asserts that the runtime factory receives the current settings. Ruff and the
focused test pass locally. Fresh exact-head Agent Gates, Backend, and external
review status remain required.
