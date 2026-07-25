# Chunk Contract: WS-AUTH-002-01 — Four Authorization Public Docstrings

## Parent initiative

`WS-AUTH-002` — Authorization Docstring Lint Correction

## Goal

Resolve the four reported AUTH-owned docstring findings without changing
runtime behavior or weakening any lint gate.

## Why this chunk exists

PR #198 must consume clean AUTH-owned source from trusted `main` before its
exact-head checks can be trusted.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-002-authorization-docstring-lint-correction/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-002-authorization-docstring-lint-correction/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-002-authorization-docstring-lint-correction/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Start phase

`implementation`

## Allowed files

```text
backend/app/modules/authorization/project_role_schemas.py
.agent-loop/initiatives/WS-AUTH-002-authorization-docstring-lint-correction/STATUS.md
.agent-loop/initiatives/WS-AUTH-002-authorization-docstring-lint-correction/reviews/WS-AUTH-002-01-internal-review-evidence.md
.agent-loop/initiatives/WS-AUTH-002-authorization-docstring-lint-correction/reviews/WS-AUTH-002-01-pr-trust-bundle.md
.agent-loop/merge-intents/WS-AUTH-002-01.json
```

## Not allowed

```text
runtime, validation, serialization structure, API structure, database, migration, or test changes
Ruff, docstring, coverage, workflow, package, or CI configuration changes
symbols other than _reason, ProjectRoleGrantIssueBody, ProjectRoleGrantRevokeBody,
and ProjectRoleGrantMutationResponse
unrelated docstring cleanup
PR #198 branch changes
```

## Acceptance criteria

- [ ] Each of the four named symbols has a concise behavior-accurate public docstring.
- [ ] The source diff contains docstrings only.
- [ ] Ruff 0.15.22 passes without configuration or invocation changes.
- [ ] Docstring coverage passes without exclusions or threshold changes.
- [ ] Generated schema changes, if any, are limited to descriptions sourced from the four docstrings.
- [ ] No test, runtime, API, schema, migration, or CI behavior changes.
- [ ] Merge intent has no successor and leaves this corrective initiative stopped.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && test "$(.venv/bin/python -m ruff --version)" = "ruff 0.15.22")
(cd backend && .venv/bin/docstr-coverage --config .docstr.yaml)
(cd backend && .venv/bin/python -m py_compile app/modules/authorization/project_role_schemas.py)
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Confirm the source change is exactly four docstrings and that no quality gate,
validation rule, or authorization behavior changed.

## Stop conditions

Stop if resolving the findings requires code behavior, tests, configuration,
workflow changes, or more than the four named docstrings.
