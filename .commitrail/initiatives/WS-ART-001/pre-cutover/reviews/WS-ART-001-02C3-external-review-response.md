# WS-ART-001-02C3 External Review Response

## GitHub Actions run 29851665477

Comments addressed:

- shard 1 exposed that the new verification-lineage trigger blocked two
  existing pre-recovery drift/fence tests. The trigger now freezes lineage only
  after a job is a recovery source or retry; unrecovered initial jobs retain
  the drift behavior needed for fail-closed verification revalidation.
- shard 2 exposed that integrity mismatch moved a contributor upload item to
  `failed` without clearing stored-result references. The terminal transition
  now clears `content_id` and `provider_object_ref`, preserving the existing
  database state-shape invariant.
- the fan-in `test` failure was downstream of those two shard failures and
  requires no independent repair.

Comments deferred:

- CodeRabbit supplied no code findings because its review was rate limited.

Human decisions needed:

- none for these bounded CI repairs; explicit human approval remains required
  before merge.

Commands rerun:

- Ruff on the changed artifact service, migration, and focused tests: PASS.
- Both failed shard-1 tests and the failed shard-2 integrity-mismatch test:
  3 PASS.

Remaining risks:

- the complete hosted shards and cumulative coverage gates must rerun on the
  repaired commit.
