# WS-ARCH-001-CP02 External Review Response

## CodeRabbit review at `3ccf4d35`

All seven comments were verified against current repository behavior rather
than applied blindly. Each was valid within the bounded interpretation below.

1. Stable operation identity: fixed. The trusted server-side command caller
   supplies one stable `operation_id`; external clients cannot choose it, CON
   computes the request digest, and retries preserve the same identity.
2. Exact allowed files: fixed. Globs and brace expansions were replaced with
   concrete production, test, generated-parity, initiative, and review paths.
3. Eligibility race: fixed. PROJECTS then ACTORS eligibility uses
   transaction-scoped locks or equivalent fences held through transaction end.
   Ineligibility/revocation race tests
   must prove no binding or event is created.
4. Migration references: fixed in the active CON handoff. `0052` is explicitly
   historical; the active graph ends at `0003_submission_lineage`. Historical
   chunk evidence was intentionally not rewritten.
5. Existing rows at `0004`: fixed without compatibility invention. The upgrade
   must fail before schema mutation when the binding table is non-empty; tests
   prove empty success and non-empty preservation/recreation requirement.
6. Reviewer vocabulary: fixed. Status values are lowercase `pass`; risk and
   remediation details are separate prose.
7. Test wording: fixed. The future proof names unit tests, PostgreSQL
   schema/lifecycle tests, concurrency tests, reset tests, boundary tests, and
   hosted full-coverage proof explicitly.

## Independent exact-head review after rebase

Four additional contract defects and one recovery gap were validated and fixed:

1. Owner eligibility now requires PROJECTS then ACTORS transaction-scoped locks
   or equivalent fences held through transaction end. Lockless revalidation is
   forbidden.
2. Every mutation fences and checks `operation_id` before binding-ID generation,
   product locks, or AUTH preparation/consumption. Duplicates create no new
   allowed mutation evidence or product effect.
3. Resume history now requires the immediately preceding same-binding suspended
   event and exact `prior.to_lifecycle_version == resumed.from_lifecycle_version`.
4. Migration proof now uses the real `backend/tests/test_alembic.py`, including
   `HEAD_REVISION = "0004_compensation_adapter_binding_lifecycle"`.
5. Unknown-commit recovery uses the stable operation identity, exact original
   facts, and request-scoped authorization of the recovered binding. It returns
   the stable result without mutation PREP reuse; mismatches or revoked/read-
   denied callers receive the same concealed conflict.

## Second independent exact-head review

Seven additional findings were validated and corrected:

1. Create, suspend, and resume now use one mandatory order: root transaction,
   digest, operation fence, recovery, operation-specific locks, AUTH prepare,
   AUTH consume, unconditional close, then mutation.
2. Duplicate semantics are singular: exact authorized recovery returns the
   immutable original result; any mismatch or denied current read returns a
   concealed conflict. Recovery never prepares mutation authority.
3. The allowed migration scope now includes `backend/alembic/env.py` and its
   required `0004_compensation_adapter_binding_lifecycle` head guard.
4. The operation fence is an exact PostgreSQL transaction advisory-lock
   mechanism with complete-UUID lookup and uniqueness proof, plus concurrency
   tests for all three mutations.
5. Every prepared object is closed in an unconditional `finally` around
   consume, before any product mutation; consume or close failure therefore
   creates no product effect.
6. Verification now includes the existing unavailable-action registration
   test.
7. The roadmap states CP02 hidden binding behavior, CP03 binding activation,
   CP04 hidden ContributionPolicy behavior, then CP05 policy activation.

The human decision was resolved explicitly: resume reacquires PROJECTS then
ACTORS eligibility fences before AUTH; suspend does not require eligibility so
an authorized Finance Authority can safely disable a revoked binding. The
mutation result and created-event transition fields are now exact.

## Third exact-head external review

Both reported blockers were replayed against head `57ee3503` and validated:

1. PREP closure now has one exact sequence everywhere: prepare, consume, close
   unconditionally around consume, then product mutation, lifecycle event, and
   flush. Consume or close failure precedes product mutation; a later product
   failure rolls back staged evidence without reviving the closed object.
2. Resume now has explicit concurrency proof for project ineligibility and
   adapter-actor revocation committing first, as well as owner-fence retention
   when resume wins. Every denial must produce no AUTH evidence, resumed event,
   or state/version change.

The earlier exact-diff reviewer passes were marked superseded before fresh
internal re-review. The latest CodeRabbit check was rate-limited, so it is not
represented as independent substantive review of the corrective head.

## Exact-diff correction after implementation review at `7f189f1a`

The five reported blockers and the handoff correction were replayed against
the implementation rather than applied automatically. All were valid:

1. Resume attribution had no database-verifiable anchor. The binding now
   persists `resumed_by` and database-owned `resumed_at`, and PostgreSQL rejects
   a resumed event whose actor differs from the transition anchor.
2. Dedicated PREP failure tests now cover consume denial, consume exception,
   wrong returned actor, exactly-once closure, no mutation after failure, and a
   product failure after successful close. The latter proves rollback of both
   product and staged participant effects and rejection of the closed object.
3. PostgreSQL negative tests now cover same-state transitions, version skips,
   retired transitions, every immutable binding identity, malformed and
   cross-binding prior-suspension references, forged resume attribution, and
   event update, delete, and truncate attempts.
4. The implementation exceeded the originally merged allowed-file list. The
   executable contract now records the exact expansion as a reviewed scope
   correction, explains why each category was required, and makes human
   approval of PR #337 the acceptance boundary. It does not misrepresent the
   files as part of the original approval.
5. The trust bundle and implementation evidence were revised after the new
   proof was added; earlier reviewer conclusions do not stand in for fresh
   exact-diff review.

The active AUTH handoff now distinguishes current main at migration `0003`
from the `0004` head that CP02 installs on merge. No compatibility path was
added.

## Test-integrity review at `b043c846`

All three reported evidence gaps were replayed and found valid:

1. A new concurrency test uses distinct operation identities and route keys
   for the same project and instrument. It proves one create succeeds, one
   receives the concealed conflict, only one mutation authorization is
   prepared, and exactly one active binding/event commits. The existing
   same-operation test remains the separate idempotent-recovery proof.
2. The authorization participant now queries the live transaction during
   consume and requires zero binding rows and zero lifecycle events before it
   stages its own effect. Rollback assertions remain as the separate atomicity
   proof after denial, exception, wrong actor, or downstream product failure.
3. Direct PostgreSQL tests now additionally cover a valid-shape active no-op
   update, suspended-to-active version skipping, and a resumed event that
   references an older same-binding suspension instead of the immediately
   preceding event.

The unused allowed-file, generic constraint-name, and indirect route-validator
observations do not weaken a product or security invariant and are not expanded
in this corrective diff. CodeRabbit still has not supplied substantive review
of the corrected implementation head.

The first hosted run of that correction exposed an independent strict-fake
defect: prepared authority stored `id(transaction)`, and Python could reuse that
address for a later transaction. The fake now retains the transaction object
itself and requires object identity during consume. This strengthens the
existing wrong-transaction proof without changing production behavior or any
CI threshold.

## CodeRabbit implementation review at `31f6d730`

All seven threads were replayed against the exact head and found valid. The
repair remains within CP02 and changes no production activation or lifecycle
semantics:

1. `CURRENT_STATE.md` now describes CP02 as complete on merge, consistent with
   the capability ledger while PR #337 remains open.
2. The ACTORS public fact describes an eligible adapter actor rather than
   prematurely classifying it as the future CP03 service identity.
3. Transaction-participant rollback tests pin their temporary-table probe,
   mutation, and assertion transactions to one physical PostgreSQL connection.
4. Owner-fence concurrency tests observe both the authorization event and the
   mutation task with a timeout, propagate early failures, and cancel and await
   both tasks during cleanup instead of hanging.
5. The committed-ineligibility test avoids a null-primary-key ORM lookup for
   create operations.
6. The missing-event PostgreSQL assertion matches the lifecycle-event guard's
   error rather than accepting an unrelated `DBAPIError`.
7. Alembic proof compares the exact four PostgreSQL function names rather than
   accepting any four overload rows.

CodeRabbit's advisory repository-external docstring percentage is not a
Workstream merge gate. The repository's own docstring and coverage gates remain
unchanged.

## Verification after correction

- architecture re-review: pass;
- security/authorization re-review: pass;
- senior-engineering re-review: recorded in the final trust bundle;
- stale authorization and Workstream wording checks: pass;
- changed Markdown links: pass;
- atomic chunk-state synchronization: pass;
- `git diff --check`: pass.

Merge readiness always requires exact-head hosted CI. GitHub's live checks are
the authority for that transient state; this durable record does not describe a
check as pending or reuse an earlier head as proof for a later commit.
