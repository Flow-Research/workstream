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
