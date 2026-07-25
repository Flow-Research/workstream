# Discovery: WS-AUTH-002 — Authorization Docstring Lint Correction

## Observed state

- PR #194 merged project-role grant mutations into `main`.
- PR #198 is the CI semantic-lane change that must consume the correction.
- Ruff 0.15.22 passes `ruff check app tests scripts`; the Ruff gate is healthy.
- CodeRabbit's docstring lint identifies exactly four missing public docstrings
  in `backend/app/modules/authorization/project_role_schemas.py`:
  `_reason`, `ProjectRoleGrantIssueBody`, `ProjectRoleGrantRevokeBody`, and
  `ProjectRoleGrantMutationResponse`.
- `WS-AUTH-001` is stopped after `WS-AUTH-001-10C` with `WS-AUTH-001-11` as its
  declared successor. AUTH-11 is a security-sensitive product cutover and must
  not be falsely consumed for this correction.

## Relevant verification

- `backend/.venv/bin/python -m ruff check app tests scripts`
- `backend/.venv/bin/docstr-coverage --config .docstr.yaml`
- Python compilation of the one changed module
- stale-wording, Markdown-link, internal-evidence, and whitespace gates

## Risks

The main risk is scope laundering: using a lint correction to alter validation
or weaken a gate. A one-source-file allowlist and explicit non-goals prevent it.
