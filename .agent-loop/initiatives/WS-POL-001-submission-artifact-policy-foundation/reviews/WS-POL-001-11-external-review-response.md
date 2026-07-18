# External Review Response: WS-POL-001-11

## Scope

This file records CodeRabbit and GitHub review feedback for the actor identity
and profile registry chunk. It is separate from internal reviewer evidence.

## CodeRabbit Findings

### Accepted And Fixed

- `get_registered_actor` failure handling: fixed before this response. Registry
  persistence failures now map to structured HTTP errors in the dependency.
- `ActorRepository.upsert_identity` stale ORM row: fixed before this response.
  The repository reloads with `populate_existing=True`.
- Actor profile metadata `{}` handling: fixed before this response. Explicit
  empty metadata is preserved and covered by regression tests.
- No-op actor observation updates: fixed before this response. Repeated
  observation does not rewrite unchanged observed profiles.
- Actor profile constraints duplicated constants: fixed before this response.
  The SQLAlchemy model derives check-constraint values from actor constants.
- Redundant identity refresh in worker profile activation: fixed before this
  response. The route passes `identity_already_refreshed=True`, and the service
  only falls back to identity upsert when no registered identity exists.
- Actor registry hot-path N+1 profile reads: fixed in this response. The
  freshness guard now loads all profiles once with `list_profiles(actor_id)`.
- Duplicated trusted relationship claim parsing: fixed in this response.
  `normalized_relationship_profile_claims()` is the shared sanitizer for audit
  snapshots and actor profile observation.
- Actor audit writes through task repository: fixed in this response. Actor
  service now writes through `AuditRepository`.
- Deterministic hardening doc output mismatch: fixed in this response. The
  recorded API contract output now includes `API contract real API e2e passed`.

### Intentionally Rejected

- Restore legacy `worker_profiles` and `reviewer_profiles` backfill before
  dropping the tables: rejected. This chunk intentionally removes obsolete
  experimental profile stores without backward compatibility because Workstream
  is still in the build phase and the human direction is to strip stale models
  rather than preserve them.

### Deferred

- Shared migration fixture extraction across `test_auth.py`, `test_actors.py`,
  and `test_tasks.py`: deferred. The duplication is low-risk test plumbing and
  broad fixture churn is not required to close the actor registry behavior
  issues in this chunk.

## Validation

Validation commands are recorded in the PR trust bundle and internal review
evidence after the final reviewed SHA is locked.
