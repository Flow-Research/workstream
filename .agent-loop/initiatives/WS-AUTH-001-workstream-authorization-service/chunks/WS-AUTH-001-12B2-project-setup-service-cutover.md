# Chunk Contract: WS-AUTH-001-12B2 — Project Setup Service Runtime Cutover

## Status and prerequisite

Proposed and inactive. Requires merged 12B, 12E, 12F, and 12G.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Activate `project.setup_run.update` and cut both Celery setup entry points to
the fixed `workstream.project.setup` identity after every product action they
invoke is active for that identity.

## Why this chunk exists

Provisioning the service early avoids invented authority, but switching the
call graph early would duplicate or bypass sufficiency and policy provenance.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/service.py
backend/app/modules/projects/setup_queue.py
backend/app/workers/project_setup.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

New service identity, new product action, human route behavior, generic setup
authority, serialized handles, ART/checker/review/contribution behavior, or
issuer-claim compatibility.

## Acceptance criteria

- Entry requires merged 12B, 12E, 12F, and 12G; the fixed identity has active
  sufficiency-run, submission-policy-derive, and post-submit-policy-derive
  memberships before either Celery entry point changes.
- `project.setup_run.update` alone covers setup context validation, task-id and
  status changes, continuation start, output-id persistence, terminal errors,
  and enqueue-failure persistence. Product rows retain their owning 12E/12F/12G
  actions and provenance.
- Celery payloads carry durable IDs/generation facts only. Each product or
  ledger mutation resolves fresh service context and consumes fresh PREP in its
  own root transaction after exact canonical locks.
- No handle crosses Celery, agent calls, rollback, commit, session, or
  transaction. Wrong/stale/cross-resource IDs, revoked service, replay, copied
  handle, and partial failure deny or roll back without mixed provenance.
- The fabricated human-management ActorContext is removed from the full call
  graph, and static scanning proves no setup mutation uses it.
- Changed authorization/project/setup-service modules remain at least 90
  percent covered. Final pushed head SHA passes `Backend / test` and
  `Agent Gates`.

## Verification commands

Before start, freeze exact isolated-runner, coverage, Celery payload/rollback,
all-pairs service denial, stale-doc, Ruff, API drill, link, and diff commands.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

No duplicated product authority, exact setup ledger ownership, fresh per-step
authorization, and complete removal of fabricated human authority.

## Stop conditions

Stop if any called product action is unavailable, a handle must cross an
external boundary, or setup-run authority would own a product row.
