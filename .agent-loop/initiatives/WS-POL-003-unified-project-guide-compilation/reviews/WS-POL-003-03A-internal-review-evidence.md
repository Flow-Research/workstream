# WS-POL-003-03A Internal Review Evidence

Date: 2026-08-10. Risk: L1.

## Deterministic evidence

- Real-PostgreSQL focused compilation suite: 31 passed after external-review
  corrections.
- New guide-compilation subsystem coverage: 93.08 percent, above the required
  90 percent floor.
- Focused AUTH boundary, structure, behavior-ownership, and public contract
  proof: passed; reviewer run recorded 184 passing tests.
- Structure-boundary regression suite: 25 passed after explicitly placing
  every POL-03A production and test file inside the zero-growth/skip gate.
- Hosted-style semantic-lane collection: 3,764 tests collected and exact lane
  evidence validated; lane inventory regression suite: 34 passed.
- Empty upgrade/downgrade, non-empty downgrade refusal, real trigger,
  concurrency, replay, immutability, and crash-recovery tests passed.
- Scoped Ruff, authorization boundary, test structure, behavior ownership,
  stale wording, Markdown links, and diff integrity checks passed.
- GitHub now preserves the repository-wide 78 percent gate and adds an exact
  90 percent guide-compilation subsystem gate. No workflow failure policy or
  threshold was weakened.

## Review results

- Architecture: pass; the new Projects package depends only on the
  dependency-free AUTH public API and creates no competing protocol or live
  cross-module path.
- Security/authorization: pass after exact canonical resource-context digest,
  fixed service profile/link, action, permission, project, attempt, and audit
  evidence binding were enforced at the database boundary.
- QA: pass; exact attempt identity, crash replay, append-only root/child CAS,
  concurrent fork prevention, stale predecessor denial, state shapes, guarded
  downgrade, and hidden deny-only behavior are covered.
- Product/operations: pass; `provider_result_accepted` remains provider-result custody only and
  creates no approval, activation, review, payment, contribution, or reputation
  truth.
- Senior engineering: pass; package files remain below structural limits and
  the unsafe evidence-fixture default was removed.
- Test delta: pass; tests are additive, behavior-focused, and contain no skip,
  xfail, or weakened assertion path.
- CI integrity: pass after all focused tests entered the semantic-lane and
  structure inventories and the hosted 90 percent coverage gate was added.
- Docs: pass after documenting that downgrade is empty-only and otherwise
  requires forward recovery or separately reviewed destructive cleanup.
- Reuse/dedup: pass; keeping the public digest implementation dependency-light
  and the fixed service literal inside the boundary avoids introducing a
  private cross-module dependency.

Fresh corrective reviews after the CodeRabbit findings:

- Architecture: pass with low risks; the suggested distinction for unexpected
  storage failures was implemented as `GuideCompilationStorageError` while one
  repository-domain base remains catchable.
- Security: pass; state, authority evidence, lineage, migration, and deny-only
  behavior remain fail closed.
- QA: pass with low risks; the required PostgreSQL suite subsequently passed
  locally against a runner-owned isolated database.
- Test delta: initial fail was corrected, then pass with low risks after live
  migrated-vocabulary proof, deterministic DB-error classification, and
  trigger-cause plus durable-state assertions were added.
- CI integrity: pass with low risks; no threshold, failure policy, lane, lint,
  or test gate was weakened, and local PostgreSQL now matches CI's exact image.
- Senior engineering: pass with low risks; its live-migration parity concern is
  covered by the new `pg_get_constraintdef` and direct rejection test.

All valid findings were corrected and re-reviewed. No reviewer session remains
open.
