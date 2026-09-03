# Chunk Contract: WS-CON-001-04A - Hidden Adapter-Binding Service

## Goal and risk

Implement authorization-ready binding create/read/suspend/resume domain behavior
and canonical resource composition while production routes remain unregistered
and AUTH actions remain planned. Retirement stays planned until dependency rows
exist. L1 payment/auth risk.

## Allowed files

```text
backend/app/modules/compensation/{schemas,repository,service}.py
backend/app/composition/compensation.py
backend/tests/{test_compensation,test_authorization,test_api_contract_e2e}.py
docs/spec_contribution_compensation.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-04A.json
```

## Not allowed

```text
production router registration, policy commands, delivery or callback
AUTH catalogue/grant/kernel/service-actor edits
concrete adapter, provider secret/ref, dependency or CI weakening
```

## Acceptance criteria

- [ ] AUTH's registration checkpoint is merged: exact planned binding actions,
  typed context contracts, applicable AdminRoleGrant definitions and prepared
  `T` protocol, plus the planned `compensation.fulfillment.report` ActionId/new
  PermissionId plus the human/AUTH-approved callback ServiceIdentity and exact
  static action row, with controlled ActorProfile/link provisioning and
  AUTH-09E admission. Both binding and callback actions remain planned and
  fail-closed. This chunk changes no AUTH file and uses only an explicit
  test decision/fake below the authorization boundary for domain-success tests.
- [ ] Create validates canonical active service ActorProfile/link, immutable
  approved ServiceIdentity, exact static row, and non-secret route identity.
- [ ] Mutations follow PLAN locks and transaction-revalidate authority; own-state
  concurrent suspend/resume is deterministic. AUTH prepares its exact bound
  handle first; CON locks binding/project rows and recomposes final facts; AUTH
  consumes the handle and evaluates once before CON mutates or flushes.
- [ ] The service accepts only an allowed decision whose complete resource-
  context digest, matched AdminRoleGrant ID and covered project match the
  locked binding facts; mismatched decision evidence is rejected. It flushes
  and never commits. The later AUTH activation gate—not a CON role-aware
  fake—proves Finance eligibility and every excluded/revoked/scope case.
- [ ] Retire remains registered/planned but non-executable; any attempt fails
  closed with stable not-active behavior. CON-10B later implements its
  dependency-aware resource behavior after assignment/lease/award/delivery rows
  exist; the post-CON-10B AUTH gate alone activates the action.
- [ ] Claims/delivery/callback races remain owned by 05/06/08A/08B/REV-13.
- [ ] Production OpenAPI remains unchanged.
- [ ] A later AUTH-owned gate integrates the central evaluators against this
  merged composer and alone changes availability. CON-04B cannot start until
  that activation passes.

## Verification and reviewers

Execute CON-04A in `../RUNTIME_VERIFICATION.md`; changed code is at least 90
percent. Senior engineering, QA/test, security/auth, product/ops, architecture,
docs, reuse/dedup and test-delta are required. Stop after hidden behavior.
