# WS-QUAL-003 — Behavior-first test-suite cleanup

- Disposition: Planned
- Intent: audit every current test, remove redundant or meaningless proof,
  replace weak assertions, add missing critical behavior, and dismantle oversized
  test files. Bounded product implementation may proceed concurrently in a
  separate branch or worktree; every remaining audit obligation still applies.
  Coordinate explicit file ownership and shared tests/CI registration.
- First bounded change: [01 — first proof cleanup](WS-QUAL-003-01.md).
- PROJECT slice: [02 — readiness and retired-route proof](WS-QUAL-003-02.md).
- PROJECT custody slice: [03 — fixtures and locked-context transactions](WS-QUAL-003-03.md).
- CI slice: [04 — rebalance seven hosted workers](WS-QUAL-003-04.md).
- PROJECT setup slice: [05 — detach guide/bundle support](WS-QUAL-003-05.md).
- PROJECT read slice: [06 — exact policy-read proof](WS-QUAL-003-06.md).
- PROJECT diagnostic slice: [07 — independent diagnostic-read proof](WS-QUAL-003-07.md).
- PROJECT fence slice: [08 — deterministic mutation execution-fence proof](WS-QUAL-003-08.md).
- PROJECT sufficiency family: [09 — mutation composition and replay proof](WS-QUAL-003-09.md).
- PROJECT submission-policy family: [10 — manual mutation and replay proof](WS-QUAL-003-10.md).
- Replay correction: [11 — realistic conflicts and retained-case rationale](WS-QUAL-003-11.md).
  Its reconciliation supersedes the affected historical test mappings in 09/10.
- AUTH cleanup: [12 — projection proof and staged AUTH audit](WS-QUAL-003-12.md).
  The human expanded this change to use reviewed commit checkpoints in one PR;
  projection proof is its first stage, not its completion boundary.
- AUTH admin-access slice: [13 — lifecycle proof audit](WS-QUAL-003-13.md).
- AUTH test-input slice: [14 — make cursor and decision-boundary tests discriminating](WS-QUAL-003-14.md).
- After 13's intended merge outcome: inventory the remaining service-actor
  provisioning and profile/link lifecycle families, then remaining AUTH owners.
  Do not repeat the selected actor, authentication or admin-access audit.
  The full suite audit remains open.
- Preserve: intended production semantics, public boundaries, real database/isolation/
  concurrency proof, current coverage floors, full hosted execution, human merge.
- Product work: POL-04A2 hidden finalization and AUTH-12B2 exact authority are
  delivered; POL-04B live cutover proceeds independently of this audit.

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
Audit the implementation alongside its tests. Confirmed defects require a
bounded production correction and a regression that rejects the pre-fix behavior;
test growth alone is not progress. Prefer realistic fixtures, strict failure
ports and proof at the actual transaction boundary over branch-count exercises.

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

Sequence this audit's PRs one at a time; this does not pause separate product
work. Reconcile shared-file changes before integration. Do not claim completion
while any baseline case lacks a
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
- AUTH slice 12 distinguishes missing decisions from existing mismatched
  decisions. It preserves the missing-row guard, exercises twelve independent
  stored-fact substitutions through the real replay matcher, and adds the
  artifact-policy positive. These controlled audit-port substitutions prove
  service matching, not database corruption or PostgreSQL isolation. The
  same change audits all 34 actor-registry tests and 51 authentication tests,
  removes the actor monolith, repairs real lock/rotation/rollback evidence and
  maps every original assertion. Its exact limits live in record 12; remaining
  AUTH lifecycle families beyond the selected slices are unaudited.
- AUTH slice 13 audits eight mixed bootstrap/admin-access tests and preserves
  all 203 original assertion spans in named survivors. It retains the real
  signed-token API journey, replaces arrival-only races with exact database
  blocker proof, and checks actual staged state before injected commit failure.
  A missing-owner-lock negative control calibrates the race proof. Fresh read
  cases keep database triggers enabled instead of resetting shared lifecycle
  rows. Three oversized functions are removed without moving them into helpers;
  the remaining fifteen monolith test bodies are unchanged.
- PROJECT slice 07 replaces the remaining mixed diagnostic composer tests with
  exact facts/digests and owner selectors. Each invalid-parent case now starts
  with a valid record, so a pre-existing missing target cannot hide a broken
  guide guard. Post-submit lineage and empty collections have independent proof.
  These mocks prove composition/delegation, not PostgreSQL locks or tenant filters.
- PROJECT slice 08 extracts two fence guards from a mixed test and adds exact
  identity/signed-key and cleanup-order proof for sufficiency and submission
  policy execution. Actual task cancellation is exercised through mock
  connection ports; physical PostgreSQL contention/crash release remains a
  separate boundary.
- PROJECT slice 09 replaces the six mixed controlled-port sufficiency mutation
  tests as one family: report creation, acknowledgement, dispatch, authority,
  lineage, replay and public concealment. Fresh negative controls cover missing
  guards and exact PREP facts. Its paired audit removes redundant/impossible
  cases, repairs missing report-generation validation during acknowledgement,
  and adds real late-conflict rollback proof for report, replay and AUTH effects.
  Slice 10 audits the mixed controlled-port submission-policy family, replaces
  weak query/provenance assertions, rejects empty creation-version identities,
  and preserves the real PostgreSQL family unchanged. Other PROJECT families
  and the recorded transaction-proof limitations remain unaudited.
- Slice 11 repaired the shared AUTH concurrency observer: a real PostgreSQL
  counterexample reproduced the transaction-cached observer miss and verified
  fresh observation while the exact waiter remained blocked. The extracted
  harness preserves diagnostic exception causes and original profile/link
  lifecycle assertions. This proves the observer defect and repair, not the
  exact cause of the historical HTTP 500 responses. Remaining AUTH proof audit
  and decomposition continue without repeating this completed diagnosis.
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
