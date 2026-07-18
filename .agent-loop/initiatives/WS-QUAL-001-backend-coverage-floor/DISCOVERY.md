# Discovery: WS-QUAL-001 Backend Coverage Floor

## Current enforcement

- `backend/pyproject.toml` has pytest configuration but no code-coverage tool or
  threshold.
- `.github/workflows/backend.yml` installs the development extra and runs plain
  `pytest -q`.
- `.github/pull_request_template.md` prohibits threshold weakening, but no code
  threshold currently exists.

## Measured baseline

An exact application measurement on the AUTH-02 tree used:

```bash
pytest -q --cov=app --cov-report=term-missing --cov-fail-under=90
```

After rerunning the contaminated project group against an isolated database,
the combined diagnostic result was 5,660 covered statements out of 7,232:
78.26 percent. Reaching 90 percent on that tree requires about 849 additional
covered statements, subject to the final main-based baseline.

Largest measured gaps:

| Module | Statements | Missing | Coverage |
|---|---:|---:|---:|
| `app/modules/projects/service.py` | 1,631 | 656 | 60% |
| `app/modules/tasks/service.py` | 650 | 270 | 58% |
| `app/modules/checkers/service.py` | 579 | 196 | 66% |
| `app/modules/projects/repository.py` | 233 | 82 | 65% |
| `app/modules/projects/router.py` | 211 | 76 | 64% |
| `app/modules/tasks/router.py` | 152 | 49 | 68% |

## Database contamination finding

The shared `workstream_test` database contained Alembic revision
`0016_artifact_domain` from another worktree while the measured branch ended at
`0015_post_submit_correction`. That caused 27 cascading project fixture errors.
A new isolated database produced 234/234 passing project tests. Coverage proof
must never share a mutable migration database across concurrent worktrees.

## Existing test ownership

- Project behavior: `backend/tests/test_projects.py`
- Task behavior: `backend/tests/test_tasks.py`
- Checker behavior: `backend/tests/test_checkers.py`
- Auth/adapters/core: focused files under `backend/tests/`
- Shared database fixtures and locking: `backend/tests/conftest.py`

## Unknowns to resolve in chunk 01

- Exact `origin/main` baseline after a clean isolated full run.
- Natural behavioral groupings that provide the largest defensible coverage
  gains without coupling tests to implementation details.
- Whether existing fixture cost can be reduced without changing test semantics.
- Exact Alembic head and app-file inventory on the reviewed main tree.

## Existing variable and guard behavior

`backend/tests/conftest.py` gives `WORKSTREAM_TEST_DATABASE_URL` precedence over
`WORKSTREAM_DATABASE_URL`; coverage commands must therefore provision and set
the former. Both API drill scripts currently allow only `workstream_test` and
`test_workstream`, so chunk 01 must update and test those guards for the strict
derived local name. The nonlocal write-risk override is not an isolation tool.
