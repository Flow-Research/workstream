# Chunk Contract: WS-AUTH-001-12E — Guide Sufficiency Mutation Cutover

## Status and prerequisite

Current-main contract refresh from merge `3479ee71`. AUTH-12C and AUTH-12D are
merged. XINT-003-02A/02B satisfy and supersede the old 12D2 prerequisite. The
three 12E actions remain planned and unavailable.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Activate manual sufficiency creation, the HTTP agent-run request, and warning
acknowledgement for the covered Project Manager, plus the same run action for
the fixed setup service only through internal command resolution.

## Why this chunk exists

Sufficiency report lineage and external-agent transaction boundaries differ
from guide metadata and policy approval.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/projects/setup_queue.py
backend/app/modules/projects/sufficiency_mutation_service.py
backend/app/modules/projects/sufficiency_mutation_repository.py
backend/app/modules/projects/guide_mutation_router.py
backend/app/modules/artifacts/authorization.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/api/deps/authorization.py
backend/app/**/project_setup.py
backend/alembic/versions/0050_guide_sufficiency_authority.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/tests/conftest.py
backend/scripts/run_test_lanes.py
backend/scripts/api_contract_e2e.py
.github/workflows/backend.yml
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/operations_project_operating_manual.md
docs/roadmap_status.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

ART extraction/materialization/source-usage semantics, agent prompt semantics,
policy approval, guide activation, setup stages after sufficiency, checker or
REV execution, or token-role fallback. The existing verified-sufficiency Celery
entry may be cut over only to the 12E internal command boundary. Do not edit
migration 0046 or introduce a second prepared-authorization protocol.

## Acceptance criteria

- Exactly the three 12E catalogue rows become active; every unrelated planned
  action remains planned. Typed, database, OpenAPI, and service-matrix parity is
  exact.
- Every action binds exact project, draft guide/version, latest source snapshot
  and digest, setup generation, report where applicable, operation,
  request/idempotency digest, actor/link, session/root transaction, and
  grant-or-service authority.
- The existing prepared binding is extended with explicit sufficiency fields
  and final match helpers for project, guide/version, snapshot/hash, report,
  target/execution kind, setup generation, setup-service custody,
  stale-output/material digest, operation, and request facts. Project scope or
  request digest alone is not sufficient final binding.
- Report creation and warning acknowledgement are human Project Manager only.
  `project.guide_sufficiency.run` admits the covered Project Manager only over
  HTTP and also admits the fixed `workstream.project.setup` service only
  through internal command resolution and its closed matrix membership. The
  service receives no other human action and cannot invoke the public route.
- Service execution additionally locks and binds the active setup run, expected
  sufficiency step, task/correlation identity, project, guide, snapshot,
  generation, and stale-output digest. It records service profile, identity
  link, and static-matrix membership, never a fabricated matched grant.
- Internal service replay derives its namespace/key from the exact service
  profile/link, action, setup run, generation, expected step, task/correlation
  identity, snapshot/hash, and stale-output/material digest; it never depends on
  a public header.
- Public routes require valid UUID `Idempotency-Key`, expose their exact action
  metadata, resolve the canonical human actor, and never admit a service token.
  Committed replay is reauthorized before response; changed, pending, or
  cross-link reuse conflicts without invoking the agent or mutating product
  state.
- Cheap preflight occurs before ART materialization/provider access or agent
  invocation. No prepared handle crosses agent execution, rollback, commit,
  session, transaction, or Celery. Final persistence obtains fresh prepared
  authority and rejects stale/replaced source, setup run, generation, material,
  or output.
- The route or internal command owns one final successful commit. Product
  services and repositories flush only. Canonical auth, idempotency, and
  preflight denials commit bounded denial evidence from a clean transaction
  while creating no product state, replay completion, provider/agent call, or
  allowed evidence. Faults after success evidence is staged roll back the
  report/acknowledgement, replay row, and allowed evidence together.
- New authorized paths must not call the existing committing legacy
  sufficiency methods as wrappers. The new orchestrator is flush-only and may
  use only narrow pure validation or material-building helpers extracted from
  `ProjectService`. It must extract/reuse, rather than copy, the existing
  ART-material-to-agent-material mapping, prompt digest, report construction,
  and source-usage row staging. It reuses an AUTH-owned service
  context/revalidation path for `workstream.project.setup`; it must not copy
  ART-private authorization helpers or add a setup-service resolver.
- Migration 0050 adds one immutable replay ledger plus separate complete
  creation and acknowledgement authorization-provenance shapes. It does not
  duplicate ART extraction/source-usage provenance from 0046. Historical rows
  remain nullable/readable and are not rewritten.
- Report creation, agent-derived output, and warning acknowledgement each record
  actor/link/grant-or-service/scope/action and decision-event provenance.
- Missing/wrong setup run, wrong setup step or task, direct public service
  invocation, cross-project/guide/snapshot/generation, replay, service or human
  revocation, stale output, wrong transaction/session, and concurrent duplicate
  effects fail closed. Copied, wrong-action, wrong-resource, wrong-link, and
  wrong-service handles also deny. Every denial proves no report/acknowledgement,
  replay completion, provider/agent call when preflight should deny, or allowed
  decision evidence.
- Side-effect-ordering tests use a counting `GuideSufficiencyMaterialPort` and
  agent fake to prove preflight denials perform zero material loads,
  allocations/provider access, or agent calls. Stale final facts deny before
  report persistence.
- OpenAPI/API tests prove the three exact action metadata values, mandatory UUID
  idempotency keys, human-only public admission, and service-token rejection
  before product execution.
- Route composition reuses or extracts the existing strict UUID
  `Idempotency-Key` parser convention and preserves the guide/policy mutation
  error shape; it does not add a third route-local parser variant.
- Each action has a replay matrix covering exact committed replay, changed and
  pending reuse, cross-action key reuse, and identity-link substitution. Fault
  injection after final consume proves report/acknowledgement, replay, and
  decision evidence roll back together.
- Existing async concurrency, one-effect, server-owned agent identity, and
  secret non-persistence assertions are strengthened with idempotency rather
  than removed. The obsolete manual-report reuse test becomes a stronger
  conflict test with zero material/agent calls. ART-03B4 material/provenance
  tests remain unchanged, unskipped, and in their canonical lanes.
- Manual reports remain a distinct explicit manual-policy input. They are never
  returned as an agent-run replay, treated as fixed-service setup output, or
  accepted as agent-created derivation evidence. A human or service agent run
  conflicts on a pre-existing manual report unless it has the exact run-owned
  action, setup/material provenance, and replay identity for that mode.
- PostgreSQL proves constraint closure, concurrent one-effect replay,
  append-only replay completion, populated downgrade refusal where required,
  safe empty downgrade, and re-upgrade. Existing migration 0046 remains
  byte-for-byte unchanged.
- Changed authorization/project modules remain at least 90 percent covered and
  final pushed head SHA passes `Backend / test` and `Agent Gates`.
- The project operating manual documents all three active routes, UUID
  idempotency, Project Manager-only public admission, service-token rejection,
  and distinct manual versus agent-backed setup paths.
- The current capability ledger records the merged 12E activation without
  claiming downstream policy derivation, guide activation, or setup-worker
  cutover.

## Verification commands

```bash
cd backend
.venv/bin/ruff check app tests scripts
.venv/bin/pytest -q tests/test_authorization.py -k 'sufficiency and (prepared or service or unavailable or catalogue)'
.venv/bin/pytest -q tests/test_projects.py -k 'sufficiency'
.venv/bin/pytest -q tests/test_alembic.py -k '0050 or guide_sufficiency_authority'
.venv/bin/pytest -q tests/test_ci_test_lanes.py
.venv/bin/coverage erase
.venv/bin/coverage run --concurrency=greenlet -m pytest -q tests/test_authorization.py -k 'prepared or catalogue or sufficiency or service'
.venv/bin/coverage run --concurrency=greenlet --append -m pytest -q tests/test_projects.py -k 'sufficiency'
.venv/bin/coverage report --include='app/modules/projects/sufficiency_mutation_*.py' --precision=2 --fail-under=90
.venv/bin/python scripts/run_test_lanes.py --collect-only --metadata-dir /tmp/ws-auth-12e-lanes --summary-json /tmp/ws-auth-12e-lanes.json
.venv/bin/python scripts/api_contract_e2e.py
cd ..
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

The exact pushed head must pass Agent Gates and GitHub Backend: all five hosted
PostgreSQL semantic lanes, the existing authorization-subsystem coverage gate
at or above 90 percent, and aggregate repository coverage at or above 78
percent. No local full-suite run is required.
Any new test module must be assigned to exactly one canonical semantic lane and
`tests/test_ci_test_lanes.py` must prove the inventory remains complete.
`backend/scripts/run_test_lanes.py` may change only when test inventory requires
that exact lane assignment; it is not a general CI adjustment surface.
Every focused selector above must select and pass non-zero 12E tests; the trust
bundle records the exact selected counts.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

External-agent boundary, exact snapshot/generation, and acknowledgement
provenance.

## Stop conditions

Stop if a handle crosses external work or extracted bytes/content authority is
required from AUTH-12.
