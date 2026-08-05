# Chunk Contract: WS-AUTH-001-12G — Post-Submit Checker Policy Mutation Cutover

## Status and prerequisite

Proposed and inactive until 12F4 is merged.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Activate post-submit checker-policy derivation for the fixed setup service and
approval/correction request mutations for the covered Project Manager.

## Why this chunk exists

These configure project policy but must not expand into checker execution,
submission visibility, or the separately owned `WS-POL-002-03` behavior.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/projects/post_submit_policy.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/projects/setup_queue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/api/deps/authorization.py
backend/alembic/versions/<then-current-next>_post_submit_policy_authority.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

Checker run/trigger/retry/read behavior, submission/review lifecycle,
`WS-POL-002-03`, ART behavior, or token-role fallback.

## Acceptance criteria

- All three actions bind the exact project, draft guide, setup run/generation,
  compiled checker policy and current lifecycle status.
- `project.post_submit_checker_policy.derive` is fixed-service-only for
  `workstream.project.setup`; approval and correction remain human Project
  Manager-only. No principal inherits the other's actions.
- Service derivation additionally locks and binds the active setup run,
  expected post-submit-policy step, task/correlation identity, project, guide,
  generation, compiled-policy/output digest, and lifecycle status. It records
  the service profile, identity link, and static-matrix membership, never a
  fabricated human grant.
- Every derivation, approval, and correction transaction uses the shared total
  order for applicable rows: project, draft guide, latest source snapshot,
  setup run, sufficiency report, target draft submission policy, current
  approved submission policy, current effective policy, current pre-submit
  policy, then the existing/target post-submit policy. Missing optional rows are
  checked in that sequence; no alternate acquisition order is allowed.
- Derivation/approval/correction record local actor/link/grant-or-service,
  scope/action provenance and
  commit with decision evidence atomically.
- Missing/wrong setup run, wrong setup step/task/correlation, direct public
  service invocation, corrected/approved/stale/replaced policy or output,
  cross-project/guide/generation, service or human revocation, replay,
  copied/wrong handle, and transaction/session mismatch deny before mutation
  or continuation enqueue.
- No checker runtime permission is registered or activated.
- 12G owns post-submit approval/correction provenance columns and migration;
  every new mutation records actor/link/grant-or-service/scope/action/decision event while
  historical rows remain nullable/readable.
- Changed authorization/project modules remain at least 90 percent covered and
  final pushed head SHA passes `Backend / test` and `Agent Gates`.
- Concurrency proof overlaps 12F3 derivation, 12F4 approval, and each 12G
  mutation and shows one canonical outcome or stable denial with no deadlock,
  partial provenance, duplicate continuation, or split policy chain.

## Verification commands

Before start, freeze exact isolated-runner, seeded migration round-trip,
coverage, Ruff, API drill, stale-doc, link, and diff commands.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

WS-POL/checker boundary, lifecycle lineage, provenance, and enqueue atomicity.

## Stop conditions

Stop if checker execution/visibility or post-submit product semantics must
change.
