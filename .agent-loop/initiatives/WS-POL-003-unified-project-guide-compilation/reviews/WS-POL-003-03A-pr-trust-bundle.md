# WS-POL-003-03A PR Trust Bundle

## Goal and design

Install hidden, immutable custody for one logical unified project-guide
compilation attempt per exact setup generation. Reservation persists before any
future provider I/O, uncertainty retains the same provider key, accepted output
survives a crash before projection, and append-only predecessor CAS prevents a
current-compilation fork.

The new Projects package is isolated from broad legacy project services. Its
only authorization dependency is a dependency-free public AUTH facts/port
module. The project-side adapter denies every operation in this chunk; no
action is activated and no route, worker, provider call, policy projection, or
live product behavior is added.

## Protected custody

- Exact attempt identity binds project, guide, source, setup generation,
  canonical inputs, catalogue snapshots, agent/instruction versions, operation,
  request, and one derived provider idempotency key.
- Accepted output is canonical, bounded, and revalidated against complete and
  component hashes before immutable persistence.
- A compilation requires matching allowed audit evidence for the exact actor,
  active fixed service profile/link, execute action, permission, attempt,
  project, and canonical resource-context digest.
- Database triggers reject illegal state transitions, mutation, deletion,
  truncation, stale predecessor use, concurrent forks, unrelated evidence, and
  non-empty downgrade.

## Scope and non-goals

The change adds migration 0062, focused ORM/contracts/repository/validation,
the public deny-only AUTH seam, behavior ownership records, structural and lane
registration, and tests. It does not call the compilation agent, enable AUTH
runtime actions, start Celery work, expose an API, approve or activate policy,
or alter submission/checker/review/contribution/compensation behavior.

## Evidence and reviews

- 26 focused PostgreSQL tests passed with 93.83 percent subsystem coverage.
- Boundary, behavior ownership, test structure, stale wording, links, Ruff, and
  diff checks passed.
- Hosted-style inventory collected 3,764 tests with exact lane evidence; the
  new package has an additive hosted 90 percent coverage gate.
- Architecture, security, QA, product/operations, senior engineering,
  test-delta, CI-integrity, docs, and reuse/dedup reviews passed after fixes.

## Remaining risk and human focus

Full repository coverage and all backend lanes must pass in GitHub Actions.
Human review should focus on whether any setup generation can acquire a second
provider key, whether accepted output can become policy accidentally, whether
append-only supersession can fork, whether audit evidence is exactly bound,
and whether the new authorization surface remains inactive and dependency-safe.
