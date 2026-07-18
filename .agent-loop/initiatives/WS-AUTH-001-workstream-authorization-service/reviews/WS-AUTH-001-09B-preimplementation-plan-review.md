# WS-AUTH-001-09B Preimplementation Plan Review

## Scope

Controlled provisioning of one fixed service ActorProfile and one opaque
Identity Issuer link by an effective system Access Administrator. No service
runtime admission, feature action activation, grant, or assignment is in scope.

## Initial candidate

- SHA: `b9cd55e236e6cb5f806a2c3f8a299a574d7165d1`
- Result: **FAIL**
- Runtime edits at review: none

## Required repairs

| Track | Result | Required repair |
|---|---|---|
| security/auth and role semantics | FAIL | Use the configured issuer through `AuthVerifier`; add an exact typed provisioning resource; bind request, decision, evidence, and replay; prove privacy and strict 422 output. |
| actor/service integration | FAIL | Do not fabricate service verification; add forward migration `0024`; make service verification nullable; keep human links verified; shift future migration custody. |
| architecture/concurrency and REV/CON integration | FAIL | Use AuthorityControl -> profile -> link -> grant ordering, repair inverse shared helpers, serialize both identity domains, and add independent-session crossed-race proof. |
| evidence/idempotency | FAIL | Preserve current true-to-false invalidation semantics, remove obsolete request shape/helper, bind the exact success/invalidation chain, and define deterministic conflicts. |
| QA/CI | FAIL | Add explicit branch-aware 90 percent actor and authorization coverage gates plus migration, rollback, replay, redaction, and no-deadlock behavior tests. |

## Repaired candidate boundary

The repaired contract makes provisioning an unverified identity-binding
operation. It exposes canonical configured issuer through the existing verifier
port, adds migration `0024` for service-link verification semantics, uses one
canonical profile-before-link lock order, keeps the existing negative-projection
invalidation direction, removes the obsolete idempotency request shape without
compatibility, and leaves all service and feature actions denied.

The first repaired candidate at `8f53fe3` passed architecture/concurrency review
but failed service-boundary and security review on five still-valid details: the
test database variable, pre-resolution legacy service denial, an obsolete HTTPS
digest restriction, stale link-before-profile documentation, and missing
verifier-boundary coverage. All five are repaired in the next planning-only
candidate. Runtime implementation must not begin until every required
preimplementation track passes that exact SHA.

## Final candidate

- SHA: `4a980fdd024a3311d604ec3e2cb38a8897f8a2cf`
- Result: **PASS**
- Runtime edits at review: none

| Reviewer group | Result | Open finding |
|---|---|---|
| security/auth and role semantics | PASS | none |
| actor/service and ART integration | PASS | none |
| architecture/concurrency and REV/CON integration | PASS | none |

The exact candidate passed all 80 agent-gate tests, stale wording,
authorization-doc consistency, Markdown links, and diff integrity. Runtime may
begin only within this reviewed 09B contract.
