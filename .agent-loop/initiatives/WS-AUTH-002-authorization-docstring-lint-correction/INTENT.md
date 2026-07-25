# Intent: WS-AUTH-002 — Authorization Docstring Lint Correction

## Human goal

Correct the four AUTH-owned public-docstring findings that appear when PR #198
consumes the project-role mutation code from `main`, without weakening Ruff,
docstring coverage, CI, or authorization behavior.

## Success state

The four findings in `project_role_schemas.py` are resolved by concise,
behavior-accurate docstrings. The exact Ruff gate and docstring tooling remain
unchanged, the corrective PR merges independently, and PR #198 can consume the
result from trusted `main`.

## Non-goals

- No runtime, validation, API, schema, migration, or test behavior changes.
- No broad docstring cleanup.
- No Ruff, docstring, coverage, workflow, or branch-protection changes.
- No work from `WS-AUTH-001-11`.

## Human direction

The repository owner directed a narrow AUTH-owned corrective chunk, followed by
a fresh `main` integration and exact-head checks on PR #198.
