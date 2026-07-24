# PR Trust Bundle: WS-AUTH-001-10C

## Chunk And Goal

`WS-AUTH-001-10C` adds PREP-bound, idempotent, auditable issue and revoke
mutations for independent exact-project contributor roles. Risk is L1
authorization, concurrency, migration, and audit integrity.

Reviewed implementation SHA: `2e2969fe712f361ff14b1c90bca439d16777d255`

## Change, Design, And Scope

- A covered Project Manager can issue submitter, reviewer, or adjudicator for
  one exact project and revoke one exact stored grant.
- Issue captures an immutable qualification snapshot before the issued event.
  Revoke derives target and role only from the locked grant and emits the closed
  future-obligation invalidation projection.
- Replay reauthorizes and reloads canonical ownership and state. Exact action,
  permission, authority kind, project scope, grant, resource, digest, target,
  role, status, and version facts are bound before completion.
- Concealment paths expose one stable `404 resource_not_found`; explicit
  self-grant and self-revoke guards retain their contract errors.
- Migration 0034 freezes every inherited function, trigger, fact constraint,
  and privacy definition it rewrites. It admits only the exact issue pair and
  binds revoke invalidation to the same actor, grant, role, project, cause,
  target reference, and future obligation.
- Issue is available for draft, active, and paused projects; revoke remains
  available for every existing project state, including archived.

AUTH-11, frontend work, task assignment, review reconciliation, automated role
conversion, and unrelated migrations remain out of scope.

## Proof And Review

Focused lint, route, lifecycle, decision-binding, audit, PostgreSQL linkage,
migration drift/refusal, downgrade, stale-wording, markdown-link, and diff
checks pass. The isolated database proof includes exact schema teardown and
no-mutation assertions for rejected evidence.

All nine internal tracks pass the reviewed implementation SHA with no blocking
finding and no open sub-agent session. No test or CI gate was weakened.

GitHub Backend must run the full shards, hosted API E2E, repository-wide
78 percent coverage floor, and authorization-subsystem 90 percent floor.

## External Review, Risk, And Human Focus

GitHub CI, Agent Gates, CodeRabbit, and human review remain required after
publication. Human review should focus on transaction and lock order, PREP
decision binding, target concealment, project lifecycle rules, replay
reauthorization, exact migration hashes, issue evidence ordering, and revoke
invalidation linkage/atomicity.

The user retains merge ownership; do not merge without explicit approval of
the specific PR. The declared same-initiative successor `WS-AUTH-001-11`
requires a separate trusted-main explicit start and must not begin
automatically.
