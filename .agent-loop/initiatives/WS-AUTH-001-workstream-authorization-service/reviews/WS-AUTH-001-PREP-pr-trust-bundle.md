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
  product lock; one shared AUTH completion path records the canonical decision
  and evidence. The participant command retains ownership of durable
  idempotency.
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
- 13 focused PostgreSQL cases pass locally and cover successful atomic mutation, rollback and commit
  failures, authorization denial, evidence failure, timeout, cancellation,
  double consumption, supported lifecycle/admin races in both lock orders, and
  database enforcement of the sole eligible grant invariant.
- Stale wording, Markdown links, loop-memory, merge-intent, and diff checks pass.
- No test, assertion, threshold, workflow, dependency, or coverage source was
  removed or weakened. GitHub Backend remains the authoritative full-suite gate
  for the 78 percent global and 90 percent changed-subsystem floors.

## Internal Review And CI Integrity

Final reviewed merge candidate `8d9436f2f76c81a37b0b5f17271789099da714b2`,
containing implementation `38acb8f91d3ddd2edd4cc26fb1e36b67fa130fd9` and
fixture repair `eaa7073d45fa4a8382f2b44401b93cae7df34744`, against trusted main
`58d0514aa5f6751a310d750f8dab8a946ca08fa5` passes senior engineering,
QA/test, security/auth, product/ops, architecture, CI integrity, docs,
reuse/dedup, and test-delta review after safety, fixture, and trusted-main
CI-acceleration sync review. The sharded Backend is trusted-main behavior and
is unchanged by PREP; no coverage threshold, dependency, or migration changed.
External-status response `11a64da9406d0be5fb35ab32ce3ff742d105c648` also
passes all nine internal tracks and binds each external result to its exact
published SHA/run without changing runtime or CI behavior. PostgreSQL shard
repair `349ac3130c61c76ccfec1bdb723d5ca614d44fe2` and trusted-main ENG sync
`57ee7a30586ad69c02d23d4e6069bcd129e0ec01` are included in the final exact-SHA
review.

## External Review And Remaining Risks

For prior published head `8a705e5bb104fb77d3a589f37b1eb45987b2515d`, Agent Gates
run `29784118660` passed. CodeRabbit run
`d64c773b-4f76-491e-ae6e-cab19d25dc4b` completed with one minor provenance
comment, addressed by explicitly binding these statuses here. The trusted-main
sharded Backend run `29784025021` failed in shard 2 and exposed additional
PREP PostgreSQL fixture defects: invalid duplicate bootstrap provenance, stale
audit column/event expectations, incomplete bootstrap-control teardown, and an
over-specific mutation-first denial expectation. Those cases now establish and
restore a valid bootstrap state and assert the kernel's privacy-safe
`permission_not_granted` result; all 13 focused PostgreSQL PREP/race cases pass
locally. Earlier single-job Backend runs exposed
invalid PostgreSQL fixture setup/teardown: bootstrap-only provenance and
immutable-history triggers rejected synthetic test data cleanup, then leaked
evidence caused cascading migration errors. The fixture-only repair bypasses
user triggers while retaining database indexes and constraints. A refreshed
GitHub Backend run remains the authoritative full-suite/coverage proof. Product
integration risk is intentionally deferred because this chunk has no consumer.

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
