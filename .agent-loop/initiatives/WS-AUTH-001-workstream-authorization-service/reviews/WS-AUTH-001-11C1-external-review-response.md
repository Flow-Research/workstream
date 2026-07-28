# WS-AUTH-001-11C1 External Review Response

## Comments addressed

- Corrected the verifier-outage sentence in the chunk contract.
- Wrapped the three repository joins identified by CodeRabbit.
- Bounded each diagnostic collection lock and response to the newest 100 rows,
  preserving deterministic newest-first ordering and matching the established
  retained-diagnostic cap.
- Strengthened `ProjectDiagnosticReadResourceContext`: snapshot hashes must be
  canonical SHA-256 digests, and existing non-collection targets must carry the
  paired snapshot identifier and hash. Collections remain bound by their exact
  ordered row-set digest.
- Narrowed the setup-run branch before accessing setup-run-only fields.
- Replaced the fixture's implicit submitter grant with an explicit, idempotent
  Access Administrator bootstrap helper.
- Updated the two stale full-suite active-action expectations reported by the
  first hosted Backend run.
- Updated the stale real-API E2E Project Manager action projection reported by
  the second hosted Backend run; the production response already contained the
  correct six newly active actions.

## Comments deferred or rejected

- The post-authorization `target is None` guard remains a sanitized invariant
  failure. Replacing it with a concealed 404 would hide a kernel defect if AUTH
  ever allowed facts declaring `target_exists=False`; the normal missing-target
  path is already concealed by the authorization dependency before this guard.
- The six reads remain serialized over actor, identity-link, and matched-grant
  rows. That locking is required by the approved anti-stale and concurrent-
  revocation contract. Removing it based only on a speculative contention note
  would weaken the security property. The bounded child collection limits the
  newly identified unbounded-lock risk.
- CodeRabbit's generic PR-description and docstring-coverage warnings do not
  identify a missing public contract or undocumented production callable. The
  PR links the repository trust bundle; production additions carry docstrings,
  and repository CI—not the bot's heuristic—owns coverage thresholds.

## Human decisions needed

None. Human merge approval remains required after exact-head hosted checks pass.

## Commands rerun

- `uv run ruff check app tests scripts`
- Focused audit, authorization-context, diagnostic resource validation,
  bounded-lock SQL, and six-action composer tests: 13 passed.
- Focused live PostgreSQL diagnostic-route proof could not start without
  `WORKSTREAM_TEST_DATABASE_URL`; the corresponding hosted lane remains required.
- Hosted Backend, Agent Gates, and CodeRabbit: required again on the final head.

## Remaining risks

- A diagnostic list intentionally returns at most the newest 100 records; an
  older exact record remains addressable through its individually authorized
  read route.
- Hosted semantic lanes, API E2E, and coverage gates must pass on the final head.
