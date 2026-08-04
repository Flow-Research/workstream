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

None. A fresh CodeRabbit result and complete Backend run are required on the
repaired exact head.
