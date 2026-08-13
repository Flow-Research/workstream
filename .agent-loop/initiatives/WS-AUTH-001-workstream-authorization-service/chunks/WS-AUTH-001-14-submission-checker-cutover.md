# Chunk Contract: WS-AUTH-001-14 - Submission, Checker, And Audit Visibility Cutover

## Status

Superseded and non-executable. Its concerns are split across the merged
WS-ARCH-001-02G/02H activation, future WS-ARCH-001-03C task readiness,
WS-ARCH-001-04D post-submit activation, 04E canonical routing, 04F checker
remediation, and later REV admission/public 02I cutover. Historical
`WS-ART-001-05B` and `WS-XINT-002-06B` must not be used as start gates.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Verify exact admission authority and activate `submission.create`, bounded
checker read/repair authority, contributor projections, and task audit
visibility. ART and POL retain submission mutations, checker execution,
findings, routing, and the sole checker-port product behavior.

## Why this chunk exists

Submission/checker authorization shares locked-task provenance and contributor
redaction rules but is separable from task claim and system-worker execution.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/tasks/router.py
backend/app/modules/tasks/service.py
backend/app/modules/tasks/schemas.py
backend/app/modules/tasks/models.py
backend/app/modules/actors/**
backend/app/modules/checkers/**
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/alembic/versions/<then-current-next>_*.py
backend/app/modules/authorization/**
backend/app/modules/audit/**
backend/app/api/deps/auth.py
backend/tests/test_tasks.py
backend/tests/test_checkers.py
backend/tests/test_auth.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-14.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
submission creation/finalization or artifact binding product mutations
checker execution/routing, standalone precheck triggers, or ordinary checker triggers
agent adapters, guide compilation, or checker-policy derivation
checker-port implementation, checker findings, or product lifecycle behavior
internal Celery worker authority cutover
review queue/lease/decision implementation
token role fallback
legacy active-worker-profile or workflow-eligibility compatibility fallback
```

## Acceptance criteria

- An exact-project submitter grant plus active assignment is required to
  create submissions; reviewer, adjudicator, and admin-only callers cannot
  submit. After submitter revocation, retained reviewer/adjudicator/admin grants
  do not preserve submission authority.
- Contributor artifact staging behavior and resource facts remain owned by
  `WS-ART-001-04A`; this chunk neither activates upload actions nor provides
  direct provider access. Dedicated AUTH custodians activate the actions only
  after hidden ART behavior merges. Submission authority never implies
  artifact-storage authority.
- `submission.create` authorizes only consumption of one exact verified ART
  admission under its existing active assignment and locked unified-compilation
  lineage; every
  migrated submission/checker/audit route declares one primary registered
  action against a feature-owned canonical target and keeps artifact bytes and
  unnecessary actor data outside `ResourceContext` and authority evidence.
- AUTH must register/evaluate/consume `submission.create` authority and commit
  its decision evidence; feature owners alone perform the protected Submission
  mutation.
- Generated OpenAPI/command manifest-delta tests prove every protected
  submission/checker/audit surface migrated here has exactly one active
  `ActionId` declaration.
- There is no caller-selectable or standalone precheck trigger. The sole POL
  checker port consumes the compiled plan automatically at the ART scratch and
  stored boundaries. AUTH exposes no alternate checker API.
- Manager repair and Operator retry resume the same Submission, admission,
  compilation, plan, checker, and run-attempt identity. They cannot select a
  checker, change policy, or create a second business effect.
- Project Manager repair uses covered `project.task.manage`; Operator recovery
  uses distinct `operations.submission_gate.repair` and
  `operations.checker.retry` permissions. Each path requires a reason and
  records matched grant/permission without granting general project authority.
- AUTH-07A migration `0021` already gives
  `operations.submission_gate.repair` and `operations.checker.retry`
  PermissionId/ActionId typed and PostgreSQL parity as planned metadata. This
  chunk promotes each action only with its feature resource composer, Operator
  candidate, guards, surface declaration, reason, evidence, and behavior tests.
  This chunk's then-current migration owns checker-field changes and exact new
  ActionId evidence parity; it changes no PermissionId mapping and does not
  rename Submission ownership again.
- Contributor reads preserve ownership, hidden-result redaction, and concealed
  not-found behavior.
- Audit reads expose only permission-appropriate bounded fields before counts.
- Operator `operations.status.read` receives only the bounded submission/checker
  operational projection required for recovery. Audit Authority `audit.read`
  receives covered task/submission/checker evidence-chain reads. Both are
  read-only, filter before counts/cursors, redact artifact bytes and unnecessary
  actor data, conceal unauthorized resources, and have mutation-denial tests.
- Revocation/suspension applies on next request and sensitive commit recheck.
- No migrated operation uses token roles or `require_any_role()`.
- Submission removes the final `LegacyWorkflowEligibilityCompatibility`
  consumer; eligibility is the exact-project submitter grant plus active
  assignment and lifecycle guards.
- Submission ownership and attestation plus checker-result visibility fields
  use `contributor_id`, `contributor_attestation`, `contributor_message`,
  `contributor_suggested_fix`, `contributor_evidence_refs`, and
  `contributor_visible` across persistence, models, schemas, services, runner
  contracts, audit payloads, and tests. Submission-policy JSON and derivation
  contracts use `contributor_facing_fix`. The merged contributor foundation
  already supplies canonical `Submission.contributor_id`; this chunk consumes
  it while removing its remaining separately enumerated legacy property names
  without public API aliases.
- With the final consumer removed, the legacy `/api/v1/workers/me/profile`
  route, typed-profile activation service/schema, and token-role workflow
  observation fields plus the now-unused compatibility adapter/allowlist are
  removed in the same chunk. Route-removal,
  stale-reference, fresh-database intake, and full API drill tests prove no
  intermediate release requires deleted metadata.
- For a replacement assignee on a durable `needs_revision` obligation,
  submission creation must consume that obligation atomically, link the
  superseded submission, and include replay for every prior high/medium finding
  under the prepared locked/rebased revision context. Missing linkage, context,
  or replay is denied without clearing or weakening the obligation. Tests cover
  successful replacement submission, each missing requirement, transaction
  failure/rollback, retry, and preservation of prior immutable attempts.
- Full backend suite and API contract drill pass.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q \
  tests/test_authorization.py tests/test_auth.py tests/test_tasks.py \
  tests/test_checkers.py --cov=app.modules.authorization \
  --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic downgrade -1)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review assignment ownership, manager repair scope, checker-result redaction,
audit disclosure, and unchanged checker routing.

## Stop conditions

Stop if authorization cutover requires changing checker outcomes, task states,
or review lifecycle behavior, if a wrong role can submit, or if a mutation
bypasses AUTH-PREP.
