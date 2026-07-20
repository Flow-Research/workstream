# WS-AUTH-001-PREP PR Trust Bundle

## Chunk

`WS-AUTH-001-PREP` - Prepared Mutation Authorization Protocol (L1).

## Goal And Human-Approved Intent

Provide one kernel-owned, single-use authorization preparation protocol for
mutation services that must lock authority before locking and changing their
product resource. The user explicitly asked to plan and fix `consume()` end to
end, while keeping the full suite on GitHub because the local machine is slow.

## What Changed And Why

- Adds typed prepared input and authority scope plus an opaque, nonserializable,
  single-use handle.
- Makes the authorization kernel acquire canonical authority locks, derive all
  facts, seal authority to the exact service/session/root transaction, and
  register the only valid consumption capability.
- Requires the participant to consume inside the same transaction after its
  product lock; one shared completion path records the canonical decision,
  evidence, and idempotency result.
- Adds a FastAPI dependency that owns rollback on denial or failure and never
  stages or commits product state itself.
- Adds focused and real-PostgreSQL proof for all supported actions, both race
  orders, replay/forgery/substitution attacks, transaction failures, timeouts,
  cancellation, and the sole eligible administrative grant invariant.

This protocol was chosen to preserve the established authority-first lock
order without handing callers reusable or caller-constructed authorization
facts. A serializable token, public prelocked context, caller-provided grant,
or second authorization path would weaken the trust boundary and was rejected.

## Scope And Product Behavior

The chunk adds authorization infrastructure and tests only. It activates no
planned action, changes no permission or role, adds no route-level product
consumer, performs no product mutation, and adds no migration. Ordinary
`require()` behavior remains unchanged.

## Acceptance Proof And Test Delta

- Ruff passed for the backend application/tests and for all final changed
  modules.
- 18 focused non-database PREP cases pass locally.
- PostgreSQL tests cover successful atomic mutation, rollback and commit
  failures, authorization denial, evidence failure, timeout, cancellation,
  double consumption, supported lifecycle/admin races in both lock orders, and
  database enforcement of the sole eligible grant invariant.
- Stale wording, Markdown links, loop-memory, merge-intent, and diff checks pass.
- No test, assertion, threshold, workflow, dependency, or coverage source was
  removed or weakened. GitHub Backend remains the authoritative full-suite gate
  for the 78 percent global and 90 percent changed-subsystem floors.

## Internal Review And CI Integrity

Implementation SHA `38acb8f91d3ddd2edd4cc26fb1e36b67fa130fd9` against trusted
main `fe0e4492a7de8699c06a52921cbdaa8a1a22e567` passes senior engineering,
QA/test, security/auth, product/ops, architecture, CI integrity, docs,
reuse/dedup, and test-delta review after safety repairs. No CI configuration,
coverage threshold, dependency, or migration changed.

## External Review And Remaining Risks

GitHub Backend, Agent Gates, and CodeRabbit remain pending until publication.
The primary remaining risk is an unforeseen transaction/cancellation behavior
under the hosted PostgreSQL matrix; the full hosted suite is the required gate.
Product integration risk is intentionally deferred because this chunk has no
consumer.

## Follow-Up And Human Review Focus

The same-initiative successor is `WS-AUTH-001-10`, Project Qualification And
Contributor Role Grants. Human review should focus on the service-private
consumer capability, exact context/root-transaction binding, authority-first
lock order, terminal handle invalidation, cancellation rollback, real-service
race proof, absence of a product consumer/migration, and the database-backed
sole-grant invariant.

## Human Merge Ownership

The agent may publish and repair this branch but may not merge it. Only the
human may approve this PR for merge. Trusted-main automation owns signed
post-merge memory generation.
