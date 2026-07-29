# Chunk Contract: WS-AUTH-001-11C2 - Effective Policy And Active Guide Read Cutover

## Status

Started by the user on 2026-07-29. The initial contract failed architecture,
security, product/ops, QA/test, CI-integrity, and senior-engineering L1 plan
review before runtime edits. The repaired contract passed all six repeat review
tracks with no remaining findings.

## Goal

Hard-cut exactly three effective-policy and active-guide GET surfaces to scoped
local administrative authority, exact canonical resource binding, and strict
read-only response schemas.

## Exact route, action, permission, and projection inventory

Paths are router-relative; every public path has the canonical `/api/v1`
prefix.

| Route | Action | Permission | Target | Response |
|---|---|---|---|---|
| `GET /projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy` | `project.effective_submission_artifact_policy.read` | `PROJECT_EFFECTIVE_POLICY_READ` | current approved effective policy for the exact guide and latest canonical source snapshot | `EffectiveProjectSubmissionArtifactPolicyResponse` |
| `GET /projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy` | `project.pre_submit_checker_policy.read` | `PROJECT_EFFECTIVE_POLICY_READ` | current compiled pre-submit checker policy for that exact effective policy | `PreSubmitCheckerPolicySummaryResponse` |
| `GET /projects/{project_id}/active-guide` | `project.active_guide.read` | `PROJECT_READ` | current active guide and its exact locked context, excluding the retired compensation configuration member | new strict `ActiveGuideReadResponse` |

All three routes allow only a covered Project Manager, a covered Audit
Authority, or a system-scoped Operator. Finance Authority, Access
Administrator, Submitter, Reviewer, Adjudicator, service identities, and every
unsupported principal deny. A caller holding both an allowed administrative
grant and a contributor grant receives the administrative projection selected
from the matched administrative authority; contributor authority never widens
the response.

`ActiveGuideReadResponse` contains exactly these top-level fields, each using
its existing strict nested schema: `guide`, `guide_source_snapshot`,
`guide_sufficiency_report`, `submission_artifact_policy`,
`effective_submission_artifact_policy`, `pre_submit_checker_policy`,
`post_submit_checker_policy`, `review_policy`, and `revision_policy`. It omits
the legacy aggregate's retired compensation configuration member completely
and cannot validate or serialize that member. This
chunk does not create a contributor or Finance active-guide projection.
Contributor guide and submission requirements remain task-scoped through the
task work-context and submission-requirements surfaces; actor authorization
context must not advertise `project.active_guide.read` from a project-role
grant.

## Risk and SLA

L1 / P1. Authorization, binding, or projection failure can disclose private
project configuration or silently retain obsolete token-role authority.

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
backend/app/modules/projects/schemas.py
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
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-11C2-effective-policy-active-guide-reads.md
```

An allowed file may change only for these three actions and their shared narrow
read-authority machinery. Workflow changes are permitted only to add the exact
11C2 composer coverage proof; no existing lane or threshold may change.

## Not allowed

```text
project, guide, source, policy, or payment mutation
setup diagnostic, project identity, or actor-context route changes except the
  negative active-guide advertisement proof described above
contributor or Finance access to the active-guide aggregate
raw payment or internal diagnostic disclosure through active-guide
token-role fallback, dual authorization, or compatibility paths
generic artifact download authority
database models, schema, or migrations
audit subsystem changes
```

## Design boundary

- Every route uses `Depends(enforce_human_authorization_read)` before any
  project, guide, snapshot, or policy lookup. Rate control and authentication
  retain their established 429/503 and 401 behavior before private lookup.
  Non-human callers and authorization denials use the centralized concealed
  response, extended to these exact three actions.
- Reuse the 11C1 composition boundary with two narrow flows: one guide-bound
  effective-policy/pre-submit composer and one active-guide composer. Do not
  add three route-local authorization implementations or an open-ended
  projection framework. AUTH does not gain a parallel project repository.
- Add strict typed resource contexts and explicit kernel action mappings. The
  effective-policy context binds action, project, guide id/version/status,
  latest source snapshot id/hash, effective policy id/hash/status, and, for the
  pre-submit action, checker policy id/status and compiled-bundle hash. The
  active-guide context binds action, project, active guide id/version/status,
  source snapshot id/hash, and identifiers/hashes/statuses for every nested
  policy row included in `ActiveGuideReadResponse`. Each binding contributes to
  the decision resource-context digest.
- The effective-policy routes expose only the current approved effective policy
  and current compiled pre-submit summary for the exact requested guide and its
  latest canonical snapshot. Draft, superseded, ambiguous, missing, or stale
  rows conceal. The active-guide route exposes only the single current active
  guide whose complete included context passes activation invariants; inactive,
  replaced, incomplete, ambiguous, or stale context conceals.
- The composer locks the canonical project, guide, source snapshot, effective
  policy, pre-submit policy where applicable, every active-guide nested row,
  actor profile, exact identity link, and matched administrative grant with
  `for_update=True`. Authorization, response shaping, and commit occur while
  those bindings remain transaction-local. Concurrent revocation, replacement,
  supersession, or digest/status drift must deny without disclosure.
- After composition authorization, migrated service reads are
  authorization-neutral: they do not accept `ActorContext`, call legacy role
  helpers, or inspect issuer role claims. Response selection is server-owned
  from the matched administrative authority; it is never selected by the
  client or token metadata.
- Decision/audit evidence records action, permission, matched grant id/scope,
  denial code, and exact resource-context digest. Reads do not create product
  invalidation or cache state and cannot reuse evidence across actions,
  projects, guides, snapshots, policies, or transactions.

## Acceptance criteria

- Activate exactly the three inventory actions and no other planned action.
- The allowed/denied principal matrix and exact response schemas above are
  enforced. In particular, `PROJECT_READ` held by Finance or a project-role
  contributor does not authorize `PROJECT_ACTIVE_GUIDE_READ`; mutation
  permissions do not imply any of these reads, and these reads imply no
  mutation.
- Unauthorized and nonexistent projects/guides share the same action-aware
  concealed response as cross-project, same-project wrong-guide, wrong-version,
  wrong-snapshot, wrong-policy, draft, superseded, replaced, incomplete,
  ambiguous, or stale bindings.
- Tests cover allowed Project Manager, scoped Audit Authority, and system
  Operator grants plus wrong-scope, revoked grant, revoked identity link,
  suspended/deactivated actor, Finance, Access Administrator, every contributor
  role, mixed admin/contributor, and service/non-human cases.
- Admission-order tests prove canonical 429/503 rate behavior, 401 authentication
  behavior, and verifier 503 happen before private lookup; verified non-human,
  unauthorized, and nonexistent requests receive identical concealed 404.
- Concurrent actor/link/grant revocation and guide/snapshot/policy replacement
  or supersession cannot disclose through already resolved facts.
- Each route declares exactly one primary `x-workstream-action-id`; OpenAPI and
  API E2E prove these exact three activations and prove that no unrelated
  planned action became active.
- Projection snapshot tests prove `ActiveGuideReadResponse` has exactly its
  enumerated top-level fields and cannot serialize the legacy aggregate's
  retired compensation configuration member; the two
  policy routes retain only their named strict schemas.
- Allow and deny evidence assertions cover action, permission, matched grant,
  scope, denial code, and resource-context digest. No N+1 authorization lookup
  is introduced.
- Authorization spec, role matrix, project operating manual, and authorization
  operations docs match the exact mappings, schemas, lifecycle rules,
  task-scoped contributor guidance, concealment, and removal of token-role
  authority.

## Verification

Local deterministic checks are focused; the full suite runs only in GitHub
Actions because the local machine is too slow for the four-hour suite.

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_projects.py tests/test_api_controls.py)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_projects.py --cov=app.modules.projects.authorization_reads --cov-branch --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py --cov=app.modules.authorization --cov-branch --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python scripts/run_isolated_tests.py --metadata-json <tmp>/api-database.json --timeout-seconds 1500 -- .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 -m unittest -v scripts.test_lightweight_agent_gates
git diff --check
```

Before completion, scan changed docs for stale terminology and broken Markdown
links. Hosted `Backend / test` and `Agent Gates` are mandatory on the final PR
head after the last commit. Record their exact head SHA. Backend must preserve
all semantic lanes, isolated API E2E, the repository-wide 78 percent floor, the
authorization 90 percent floor, and an additive branch-aware 90 percent gate
for the narrow project authorization-read composer. The broad legacy project
subsystem is not falsely presented as a 90 percent gate.

## Required reviewers

Preimplementation: senior engineering, QA/test, security/auth, product/ops,
architecture, and CI integrity.

Implementation: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta.

## Stop conditions

Stop and repair before proceeding if any route cannot use centralized
concealment, an exact typed context, complete transaction-local binding, a
single local-grant authority path, or its strict response schema; or if the
implementation requires a migration, mutation behavior change, contributor or
Finance active-guide access, compatibility fallback, weakened CI, or cannot
prove the narrow composer at 90 percent branch coverage.
