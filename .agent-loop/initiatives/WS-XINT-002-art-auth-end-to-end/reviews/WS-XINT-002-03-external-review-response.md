# WS-XINT-002-03 External Review Response

## Hosted Backend run 30284611419

The semantic lanes executed but the independent evidence validator correctly
failed because `shared_foundations` contained three test failures.

- The missing-object put test now proves two prepared and two consumed
  capabilities in exact `claim`, `terminal` order.
- The terminal-authority-drift double now permits claim consumption and denies
  only terminal consumption, preserving the running retry fence and committing
  no terminal facts.
- The custody parser accepts the exact active/current-availability table header
  while retaining exact action-set and duplicate validation.

The focused isolated PostgreSQL rerun passed all four relevant regressions.
QA, test-delta, and CI-integrity re-reviews passed. No workflow, lane,
threshold, skip, or coverage policy changed.

## CodeRabbit review

- Accepted the process-lifecycle finding. Celery child initialization now
  claims and initializes one provider store, operations lease it against
  shutdown, disabled storage skips initialization, and shutdown waits for
  active leases. A concrete local bootstrap/store test prevents namespace
  identity from crossing the lifecycle boundary.
- Accepted malformed selector normalization. Invalid UUID or prepared-scope
  selectors now fail as `ArtifactAuthorityDeniedError` and have a focused test.
- Accepted the denial-contract finding. Both specifications now describe the
  ART-only rollback-then-clean-restage exception, including still-planned exact
  denials issuing no handle.
- The recovery terminal-denial finding was already repaired on the current
  head with phase-aware claim/terminal behavior.
- The `${EMPTY}` split in the contract is required by the repository stale-
  wording policy. Its shell assignment is now explicit, so the documented
  coverage targets expand deterministically without reintroducing prohibited
  wording.

Architecture, security, QA, and reuse/dedup focused re-reviews passed after the
repairs. Ruff, focused tests, stale checks, markdown links, and diff checks
passed.

## Hosted Backend run 30287247882

Three semantic lanes passed. The schema-contract lane exposed six existing
Alembic tests that still named migration `0036` as repository head after this
chunk added `0037`. Eight exact expected-revision values now name `0037`; all
schema, downgrade-refusal, row-preservation, and trigger assertions remain
unchanged. The same isolated six-test selection passed in 509.88 seconds, lane
inventory passed, and CI-integrity plus test-delta re-reviews passed. No CI or
coverage configuration changed.

## CodeRabbit eager/non-prefork follow-up

Accepted. Resolver and verifier task bodies now idempotently initialize the
process runtime before leasing it, covering eager, solo, and thread execution
without weakening prefork startup. General `worker_shutdown` complements the
prefork child shutdown signal. The real Celery task bodies run under eager mode
in the focused regression; runtime, exact PREP action/context pairing, and
direct-require denial tests passed. Architecture, security, and QA focused
re-reviews passed.
