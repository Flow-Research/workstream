# WS-QUAL-003 — Behavior-first test-suite cleanup

- Disposition: Planned
- Intent: audit every current test, remove redundant or meaningless proof,
  replace weak assertions, add missing critical behavior, and dismantle oversized
  test files before resuming product implementation.
- First bounded change: [01 — first proof cleanup](WS-QUAL-003-01.md).
- PROJECT slice: [02 — readiness and retired-route proof](WS-QUAL-003-02.md).
- PROJECT custody slice: [03 — fixtures and locked-context transactions](WS-QUAL-003-03.md).
- CI slice: [04 — rebalance seven hosted workers](WS-QUAL-003-04.md).
- PROJECT setup slice: [05 — detach guide/bundle support](WS-QUAL-003-05.md).
- PROJECT read slice: [06 — exact policy-read proof](WS-QUAL-003-06.md).
- Next usable boundary after 06: continue PROJECT diagnostic/mutation behavior
  audit and cohesive test-body extraction, then AUTH.
  The full suite audit remains open.
- Preserve: production semantics, public boundaries, real database/isolation/
  concurrency proof, current coverage floors, full hosted execution, human merge.
- Product work: POL-04A2 remains planned; this initiative does not implement it.

## Baseline and honest audit coverage

At main `12c58431`, a static AST inventory of `test_*.py` under `backend/tests`,
`backend/scripts`, and `scripts` found 161 files, 2,722 named test functions,
118,552 source lines, and 51 files with at least 500 lines. These are source
counts, not pytest-expanded case counts and not a semantic review verdict.

Hosted Backend run `33998298054` collected 4,352 cases and reported 91.4031%
global statement coverage. Its synthetic merge tree and main's tree both equal
`2464cadcfff4769c35dbf80e87b7218909111864`. Reuse the hosted manifest and coverage
artifacts; do not rerun the full suite locally merely to enumerate cases.

| Large file | Lines | Named tests | Required treatment |
|---|---:|---:|---|
| `backend/tests/test_projects.py` | 15,700 | 277 | Audit each behavior, extract scoped fixtures, split into project-owned modules |
| `backend/tests/test_authorization.py` | 13,384 | 163 | Preserve real kernel versus PostgreSQL proof; remove imports from test modules |
| `backend/tests/test_auth.py` | 7,423 | 74 | Separate token verification, routes, bootstrap, service identities, actor lifecycle |
| `backend/tests/test_tasks.py` | 7,300 | 116 | Separate assignment, submission, revision, readiness and transaction proof |
| `backend/tests/test_checkers.py` | 4,729 | 119 | Separate policy validation, execution, persistence and result boundaries |

Initial discovery inspected 38 CON/COMPENSATION/review files (264 test functions
in 36 test-bearing files), selected AUTH adapters and monolith regions, and
selected ART/PROJECT bodies. This is not an exhaustive review of 4,352 cases.
The remaining monolith bodies, other subsystems and tooling must still be audited.

## Audit method

For each named test and each materially distinct parameter case, trace its
fixture, actual production call, discriminating assertion and side effects.
Classify it as keep, consolidate, remove with named surviving proof, strengthen,
or missing proof to add. No deletion is justified by file size, similar names,
identical AST bodies alone, coverage percentage or a desired test-count target.

Use the existing behavior-ownership catalogue and behavior contracts when they
already map a changed proof. Reconcile references to deleted/renamed tests in
the same change. Do not create another ownership engine or mandatory global gate.
Keep detailed command/node inventories as PR evidence; durable change records
name removals, replacements and unresolved audit scope.

Every new or rewritten test module stays below 500 lines and each test owns one
primary behavior. Splitting a file alone is not a completed semantic audit.
Move shared fixtures into owner-scoped support/conftest files and preserve their
scope, isolation, imports, collection, and lifecycle cleanup. Remove unrelated
assertions only when their own surviving proof is identified.

## Reviewable sequence

1. Initial AUTH/CON duplicates and genuine deny-default/fact-binding proof.
2. PROJECT retired-route redundancy and project test decomposition; add missing
   inactive-project locked-context denial at the real persistence boundary.
3. AUTH/authentication monolith decomposition and exact historical-evidence
   replay checks, preserving PostgreSQL, revocation, replay and concurrency.
4. TASK/submission/checker test audit and owner-scoped decomposition.
5. ART storage/extraction/recovery audit, replacing coverage-only buckets with
   exact resource-limit, isolation, classification and side-effect assertions.
6. Remaining CON/REV/ACTORS/audit/config/API/tooling proofs and oversized files.
7. Reconcile the complete hosted node manifest against reviewed dispositions,
   remaining oversized-file inventory, behavior coverage and measured CI costs.

One PR at a time. Do not claim completion while any baseline case lacks a
disposition or while removed protection lacks an equivalent or stronger proof.
No fixed reduction percentage or same-day completion claim overrides safety.

## Concrete follow-up findings

- PROJECT slice 02 removed five redundant retired-route journeys while retaining
  service-seam, runtime/database and warning translation proof. Slice 03 isolates
  client fixtures and locked-policy contracts and proves both project-inactivation
  transaction orderings. Slice 05 isolates the guide/bundle helper graph and
  removes the remaining locked-context import from the PROJECT test monolith.
  It preserves all helper behavior and test cases; this dependency cleanup is
  not a completed semantic audit of their consumers.
- PROJECT slice 06 replaces four mixed/weak read tests with focused exact-fact,
  exact-digest, validator-delegation and rejection proof. A well-formed wrong
  digest passed the old prefix assertions; the new equality checks reject it.
  The fake validator no longer repeats a composer guard that could mask a broken
  composer. Repository/transaction proof remains separate and unchanged.
- AUTH projection replay uses a nonexistent decision in its negative test;
  add existing-but-tampered stored decision coverage, not more random-ID cases.
- Before routine AUTH decomposition, diagnose the intermittent three-admin
  suspension race in `test_actor_profile_lifecycle_real_postgres_concurrency`.
  Main run `34032455068` returned `[500, 200]` rather than `[200, 200]`; unchanged
  source passed another run. A test-only lock-observer timeout/assertion is a
  plausible cause, not a confirmed diagnosis. Capture the exception class and
  hook phase, then observe the exact waiter PID on a fresh database to distinguish
  harness failure from a runtime fault. Preserve the success assertion, rollback
  checks and real concurrent sessions; do not retry away, skip or weaken it.
- CON publication non-reuse and reverse-order concurrency test names overstate
  their actual one-call assertions; preserve real races and repair the claims.
- Guide extraction has a parent-coverage bucket mixing limits, seccomp and
  format parsing; preserve unique behavior in focused tests before pruning it.
- CI slice 04 exposed two pre-existing incidental coverage paths, not omitted
  product tests. During AUTH/ACTORS audit, force both first-access sessions past
  the initial miss and prove the contender waits then returns the winner's
  persisted identity after lock release (`actors/service.py` post-lock branch).
  During CON audit, persist prior policy versions and assert the real repository's
  `next_version_number` result; entering its awaited query is not completed proof.

## Risks and verification

Repository-wide scope is L0; each bounded test-only change is routed by its
actual safety impact. QA/test-delta and CI-integrity assess removed protection;
security reviews changed authority proof. Other specialties are used only for
their affected boundaries. Full tests, PostgreSQL and global/subsystem coverage
stay in GitHub Actions. Focused local tests and targeted test-of-test mutations
must show assertions detect the intended defect, not fixture failures.

Coverage is a guardrail, not proof completeness. This audit may add valuable
cases while reducing duplicate execution, fixture cost and source volume.
