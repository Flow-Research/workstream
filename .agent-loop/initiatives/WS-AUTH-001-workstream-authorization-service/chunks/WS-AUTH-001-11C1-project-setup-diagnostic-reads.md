# Chunk Contract: WS-AUTH-001-11C1 - Project Setup Diagnostic Read Cutover

## Status

Started by the user on 2026-07-28. The repaired contract passed architecture,
security, product/ops, QA/test, CI-integrity, and senior-engineering L1 plan
review; bounded implementation and deterministic evidence are in progress.

## Goal

Hard-cut exactly six project-guide setup and draft diagnostic GET surfaces to
scoped local administrative grants as their sole product-authority source.

## Exact route, action, and permission inventory

Paths below are router-relative; every public path has the canonical `/api/v1`
prefix.

| Route | Action | Permission |
|---|---|---|
| `GET /projects/{project_id}/guides/{guide_id}/setup-runs/latest` | `project.setup_run.read` | `PROJECT_SETUP_DIAGNOSTIC_READ` |
| `GET /projects/{project_id}/guides/{guide_id}/sufficiency-reports` | `project.guide_sufficiency_report.list` | `PROJECT_SETUP_DIAGNOSTIC_READ` |
| `GET /projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}` | `project.guide_sufficiency_report.read` | `PROJECT_SETUP_DIAGNOSTIC_READ` |
| `GET /projects/{project_id}/guides/{guide_id}/submission-artifact-policies` | `project.submission_artifact_policy.list` | `PROJECT_EFFECTIVE_POLICY_READ` |
| `GET /projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}` | `project.submission_artifact_policy.read` | `PROJECT_EFFECTIVE_POLICY_READ` |
| `GET /projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/setup` | `project.post_submit_checker_policy_setup.read` | `PROJECT_EFFECTIVE_POLICY_READ` |

## Risk and SLA

L1 / P1. Authorization or concealment failure can disclose private project
configuration or silently retain obsolete token-role authority.

## Allowed files

```text
backend/app/api/deps/authorization.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/repository.py
backend/app/modules/authorization/runtime.py
backend/app/modules/authorization/read_service.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/router.py
backend/app/modules/projects/service.py
backend/tests/test_api_controls.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/scripts/api_contract_e2e.py
.github/workflows/backend.yml
docs/operations_authorization_service.md
docs/operations_roles_permissions.md
docs/operations_project_operating_manual.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

An allowed file may change only for this chunk's six actions and their shared,
narrow read-authority machinery. No database migration is permitted.

## Not allowed

```text
project or policy mutation
project identity or actor-context routes
the 11C2 effective submission-artifact-policy, pre-submit-checker-policy,
  or active-guide routes
contributor access to setup diagnostics
token-role fallback, dual authorization, or compatibility paths
generic artifact download authority
database schema or migration changes
```

## Design boundary

- Every route uses `Depends(enforce_human_authorization_read)` before any
  project, guide, or child lookup. Rate control and authentication retain their
  established 429/503 and 401 behavior before private lookup. Non-human callers
  and authorization denials use the existing centralized concealed response.
- One narrow application-layer composer resolves canonical project, guide, and
  child facts through `ProjectRepository`; AUTH does not gain a parallel
  project repository. The six routes must not duplicate bespoke authorization
  flows.
- New strict typed resource context(s) bind the action to `project_id`,
  `guide_id`, guide version, target kind, target identifier where applicable,
  existence and ownership facts, and the source snapshot identifier/digest
  where the projection has one. The six actions receive explicit kernel
  context mappings. Decision/audit evidence includes the action, permission,
  matched grant identifier and scope, denial code, and exact resource-context
  digest.
- After router/composition authorization, migrated service reads are
  authorization-neutral. They do not accept `ActorContext` and do not call
  the legacy role helper or inspect issuer role claims.
- Transaction-local revalidation locks the canonical actor profile, exact
  identity link, and matched administrative grant (`for_update=True`) through
  disclosure/commit. A revoked link/grant or changed binding cannot pass on a
  stale decision.
- Historical setup runs, reports, and draft/superseded policies remain readable
  diagnostics when the exact row is canonically bound to the requested
  project, guide, guide version, and source snapshot. Supersession alone does
  not conceal history. The `latest` setup route and checker-setup projection
  bind the exact canonical row selected in the transaction and deny if those
  facts change before projection.

## Acceptance criteria

- Activate exactly the six inventory actions and no other planned action.
- Canonical project, guide, and child ownership is resolved before disclosure.
  Unauthorized, nonexistent, cross-project, cross-guide, wrong-child-binding,
  and stale-context requests share the action-aware concealed public response.
- Same-project/different-guide, same-guide/different-version or snapshot, and
  copied child identifiers cannot disclose data.
- Project Manager, scoped Audit Authority, and system Operator grants allow
  their exact read-only projections. Finance Authority, Access Administrator,
  contributor grants, wrong-scope grants, non-human callers, revoked grants,
  revoked links, and suspended/deactivated actors deny.
- Admission-order tests prove that rate exhaustion preserves canonical 429 with
  retry metadata, rate-store failure preserves canonical 503, missing/invalid
  bearer authentication preserves canonical 401 (and a verifier outage
  preserves its canonical 503), and a verified non-human subject receives concealed 404,
  all before any project, guide, or child lookup.
- Read permissions grant no mutation authority, and mutation permissions do not
  imply diagnostic read authority.
- Every migrated route declares exactly one primary action in the canonical
  OpenAPI inventory and uses local grants as its sole product-authority source.
- Concurrent revocation or replacement cannot disclose through a previously
  resolved actor, identity link, grant, guide, child, version, or snapshot.
- Per-action allow/deny evidence is persisted with the exact context digest and
  no N+1 authorization lookup is introduced.
- Authorization spec, role matrix, project operating manual, and authorization
  operations docs match the mappings, projections, concealment, history
  semantics, and removal of token-role authority.

## Verification

Local deterministic checks are focused; the full suite runs only in GitHub
Actions because the local machine is too slow for the four-hour suite.

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_projects.py tests/test_api_controls.py)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_projects.py --cov=app.modules.projects.authorization_reads --cov-branch --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py --cov=app.modules.authorization --cov-branch --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 -m unittest -v scripts.test_lightweight_agent_gates
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Before completion, scan changed docs for stale terminology and broken Markdown
links. Hosted `Backend / test` is mandatory before merge and must preserve all
semantic lanes, API E2E, the repository-wide 78 percent floor, the applicable
authorization 90 percent floor, and an additive branch-aware 90 percent gate
for the narrow new project authorization-read composer. The existing broad
legacy project subsystem is not falsely presented as a 90 percent gate.

## Required reviewers

Preimplementation: senior engineering, QA/test, security/auth, product/ops,
architecture, and CI integrity.

Implementation: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta.

## Stop conditions

Stop and repair before proceeding if a route cannot use centralized
concealment, exact typed child binding, transaction-local revalidation, or a
single local-grant authority path; or if implementation requires a migration,
mutation behavior change, 11C2 route, compatibility fallback, weakened CI, or
cannot prove the narrow new composer at 90 percent branch coverage.
