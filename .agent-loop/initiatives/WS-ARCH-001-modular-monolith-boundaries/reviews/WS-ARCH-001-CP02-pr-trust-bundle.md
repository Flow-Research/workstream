# WS-ARCH-001-CP02 PR Trust Bundle

## Chunk

`WS-ARCH-001-CP02`: Hidden Adapter-Binding Behavior.

## Goal and approved intent

Implement CON-owned, route-unreachable create/read/suspend/resume behavior for
project compensation adapter bindings. Keep production deny-default and all
four AUTH actions planned/unavailable until CP03 installs the real owner and
authorization adapters.

## What changed and why

- Added immutable public CON requests, results, views, and authorization ports.
- Added public PROJECTS and ACTORS eligibility ports without private imports.
- Added CON repository/service orchestration with PostgreSQL advisory operation
  fencing, exact authorized recovery, row locking, and concealed conflicts.
- Added migration `0004` with immutable contiguous lifecycle-event history,
  database-verifiable create/suspend/resume attribution guards,
  one-active-binding constraints, and empty-table-only upgrade protection.
- Added focused unit, PostgreSQL, concurrency, boundary, ownership, reset, and
  Alembic tests; split fixtures and test doubles into named files so no test
  file reaches 500 lines or shadows repository pytest configuration.
- Reconciled ARCH, CON, roadmap, and current-state records because CP03 is the
  next activation gate after this merge.

## Design chosen

Every mutation follows one order: root transaction, canonical digest,
transaction-scoped operation fence, recovery, owner/product locks, AUTH
prepare/consume/close, product mutation, lifecycle event, and flush. Exact
duplicates may return the immutable original result only after current read
authorization. Any mismatch or denied read returns one concealed conflict and
performs no second mutation authorization or effect.

PROJECTS then ACTORS eligibility fences are retained through create and resume.
Suspend remains possible after owner ineligibility so authorized operators can
disable a binding. CP02 test proof uses an explicit test-only eligibility
marker; existing service identities and unmarked human actors cannot
substitute. CP03 owns
the real compensation-adapter identity rule and AUTH composition.

## Alternatives rejected

- Raw role checks or a CON-local authorization evaluator.
- Imports from AUTH, PROJECTS, or ACTORS private implementation modules.
- Generic service eligibility or reuse of ART/REV identities.
- Mutation retry without an operation fence and current read authorization.
- Mutable or best-effort lifecycle history.
- Compatibility paths for retired fact names or lifecycle behavior.

## Scope control and product behavior

No route, evaluator, grant, service matrix row, production service identity,
action activation, ContributionPolicy behavior, retirement, fulfillment,
callback, delivery, provider call, or credential behavior is added. The hidden
service defaults to denial, so production behavior remains unavailable.

## Acceptance criteria proof

Focused tests prove contiguous create/suspend/resume history; immutable event
and binding identity; exact duplicate recovery for all mutations; mismatch and
read-denial concealment; one-effect concurrency; owner ineligibility before
AUTH; retained project and actor locks; close-before-mutation failure; copied,
replayed, closed, or wrong-transaction fake PREP rejection; no existing ART or
human identity substitution; deny-default production composition; consume
denial/exception/wrong-actor closure and rollback; failure after successful
close; complete forbidden-transition and immutable-identity rejection; forged
resume-attribution rejection; and event update/delete/truncate rejection.
Distinct-operation create races separately prove the one-active-binding
invariant rather than relying on same-operation recovery. The AUTH participant
also inspects the live transaction during consume and proves that no binding or
lifecycle event has been staged before authorization. PostgreSQL proof includes
suspended-to-active version skips and stale same-binding suspension references.
The strict PREP fake retains the actual transaction object and compares by
identity, so Python object-address reuse cannot make a later transaction appear
to be the prepared transaction.

## Tests and checks run

- Ruff on all touched backend modules and tests: pass.
- Repository docstring coverage: 80.2%, pass.
- Focused non-database CP02 and AUTH registration tests: pass.
- Canonical semantic-lane collection: pass.
- Module, authorization, test-structure, and behavior-ownership gates: pass.
- Stale wording, changed Markdown links, chunk-state synchronization, and
  `git diff --check`: pass.
- The hosted migration failure caused by double application of SQLAlchemy's
  constraint naming convention was corrected with finalized Alembic names;
  the schema test now proves the exact replacement constraints.
- Migration `0004` widens Alembic's revision column before stamping its
  longer canonical revision identifier; the schema test proves the new bound.
- The database-reset fingerprint is reconciled to the exact hosted `0004`
  schema, and migration preflight evidence retains internal foreign-key
  enforcement instead of attempting to disable PostgreSQL system triggers.
- PostgreSQL behavior, migration, reset, semantic lanes, and repository-wide
  coverage are proven by mandatory hosted GitHub checks, not a local full run.

## Test delta and CI integrity

The superseded 03A deny-all-update and raw-table race tests were replaced by
service-bound lifecycle, advisory-lock, recovery, and database-guard tests. No
skip, xfail, omission, threshold reduction, workflow bypass, or coverage
weakening was introduced. Repository coverage floors remain unchanged.

## Reviewed scope correction

Implementation revealed necessary parity and proof files outside the originally
merged allowed-file list: ORM aggregation, canonical architecture text, CI
ownership/lane metadata, shared test support, schema-reset/Alembic contracts,
and split authorization/database guard tests. The executable contract records
the exact paths and rationale. Approval of PR #337 explicitly accepts this
corrected scope; it is not represented as part of the earlier approval and does
not authorize adjacent CON behavior.

## Reviewer results

Architecture, security, product/operations, QA, test-delta, CI-integrity,
reuse/dedup, senior-engineering, and documentation reviews are recorded in the
implementation review evidence. Valid findings were fixed; low risks are
carried to CP03 where the real adapters and identity are installed.

## External review

The planning-stage external findings and their validated disposition remain in
`WS-ARCH-001-CP02-external-review-response.md`. Implementation-head GitHub and
CodeRabbit findings must be replayed against the code before any fix. GitHub's
live exact-head checks are the authority for transient status.

## Remaining risks and follow-up

CP02 deliberately proves hidden behavior with deny-default production
composition and strict test adapters. CP03 must install the real AUTH PREP,
PROJECTS, and ACTORS adapters; register the approved compensation service
identity; repeat real-adapter transaction/fence proofs; and activate only the
four adapter-binding actions. CP04/CP05 own ContributionPolicy behavior and
activation.

## Human review focus and merge ownership

Review the mutation order, owner-lock retention, database event guards,
authorized duplicate recovery, absence of existing-service substitution, and
continued lack of route/action activation. Only an authorized human may approve
and merge this PR.
