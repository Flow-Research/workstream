# Chunk Contract: WS-XINT-003-02B — Prepared Policy Mutation Activation

## Goal

Expose the only review/revision policy mutation surface for covered Project
Managers, consume AUTH PREP against final locked facts, append immutable policy
versions, record bounded decision evidence atomically, and activate only the two
policy ActionIds.

## Prerequisite

Merged 02A at the then-current main head. Refresh exact symbols and migration
state before implementation; do not duplicate 02A persistence. This contract is
non-implementable until that refresh replaces every conditional file and
verification placeholder.

## Risk class

L1 authorization and policy mutation.

## Allowed files

```text
backend/app/api/router.py
backend/app/api/deps/authorization.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/projects/models.py
backend/app/modules/projects/guide_mutation_repository.py
backend/app/modules/projects/project_mutation_repository.py
backend/app/modules/projects/guide_mutation_service.py
backend/app/modules/projects/policy_mutation_router.py
backend/app/modules/projects/policy_mutation_service.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/schemas.py
backend/alembic/versions/<then-current-next>_project_policy_mutation_authority.py
backend/tests/test_alembic.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/operations_roles_permissions.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/**
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-12D2-guide-bound-policy-mutations.md
```

The post-02A refresh must decide exact rename/delete paths and replace the
migration placeholder before implementation.

## Not allowed

- Policy persistence redesign, guide create/update compatibility, generic
  mutation service locator, alternate writer/repository, direct grant reads in
  project code, Review/queue/lease/revision execution, ART, CON, Task,
  Submission, frontend, or dependency changes.

## Acceptance criteria

- Separate `PUT /api/v1/projects/{project_id}/guides/{guide_id}/review-policy`
  and `/revision-policy` routes declare exactly their corresponding primary
  ActionIds and require UUID idempotency keys before actor provisioning. Request
  JSON cannot choose authoritative project/guide relationships.
- `ProjectPolicyMutationService` follows the established project mutation
  composition convention without inheriting unrelated guide behavior.
- Only an active human Project Manager with the exact project grant and
  `project.review_policy.manage` may mutate the matching draft guide lineage.
- PREP binds actor/link/grant, action, project, guide ID/version, current or
  reserved policy identity/generation/digest, request digest, idempotency key,
  session, and root transaction; final consumption uses locked current facts.
- The service calls only 02A's append-only repository primitives. Exact replay
  returns the committed response after reauthorization; changed, copied,
  cross-action/project/guide, revoked, stale, or concurrent requests fail closed.
- Policy row, authorization decision evidence, audit/provenance, and replay
  result commit once; every injected failure rolls back all four.
- Existing guide replay rows are preserved while
  `GuideMutationIdempotencyRecord`/`GuideMutationRepository` are deliberately
  generalized to one closed project-mutation replay model/repository. Its
  database action constraint admits the three existing guide actions and only
  the two policy actions; both guide and policy services use that one ledger.
- Only `project.review_policy.update` and
  `project.revision_policy.update` transition from planned to active. No review
  execution action or product route is released.

## Verification commands

This section is intentionally not implementation-ready. Freeze exact focused
commands after 02A merges. They must include policy route,
authorization denial/replay, PostgreSQL concurrency/rollback, OpenAPI action
parity, Ruff, changed-subsystem 90-percent coverage, stale authorization docs,
Markdown links, diff integrity, and GitHub-hosted full coverage.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, test-delta, and CI integrity.

## Human review focus

Single writer, exact covered-project authority, PREP final-fact binding,
idempotency, atomic evidence, and exactly two action activations.

## Stop

Merge and stop before reviewer queue/lease work.
