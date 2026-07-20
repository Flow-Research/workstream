# Internal Review Evidence: WS-CON-001-02A

## Chunk

`WS-CON-001-02A` - Shared Transactional Outbox Persistence

Risk: L1 infrastructure, schema, concurrency, audit, and data-integrity risk.

## Baseline And Scope

Trusted main SHA: `3b1d63796c086f53fc2b0aeefe096387b82485ec`

The implementation is limited to one linear PostgreSQL migration after
ART-owned revision `0028_artifact_admission`, the generic outbox persistence/append module, shared
metadata registration, focused tests,
initiative evidence, and exactly one merge intent. It adds no dispatcher,
delivery executor, Celery registration, broker, route, feature handler, AUTH
identifier, contribution, compensation, review, task, project, audit, or ART
behavior.

The user-owned unstaged deletion of the older contribution reference PDF is
outside the chunk and is excluded from every commit and review.

REV PLAN2 PR #150 is planning/specification-only. It preserves the exact 02A
runtime and migration while refreshing future CON/REV gate names. The first
post-AUTH full-suite attempt was stopped after two hours when that PR advanced
trusted main; its metadata was removed and it is not evidence.

ART-02B1 PR #151 changes no 02A code or migration, but it adds locked S3 SDK
dependencies, a real MinIO CI service, and substantial backend tests. A second
full-suite attempt was stopped after 3 hours 7 minutes when that PR advanced
trusted main; its metadata was removed and it is not evidence.

AUTH-09D-B PR #152 changes no 02A code or migration. It activates exactly two
identity-link lifecycle actions and adds substantial AUTH route/test coverage.
A third full-suite attempt was stopped after one hour when that PR advanced
trusted main; its metadata was removed and it is not evidence.

A fourth local full-suite attempt on the frozen `93dd3924` baseline was stopped
after approximately 4 hours 15 minutes by human direction to keep
repository-wide suites in GitHub CI. Its metadata was removed and it is not
evidence. The active verification rule now uses bounded focused proof locally
and requires the existing GitHub Backend full-suite job on the pushed PR.

Contributor-foundation PR #153 advances trusted main to `8d5eb15b`, owns
`0027_contributor_foundation`, clean-cuts TaskAssignment/Submission attribution
to canonical human `contributor_id`, and adds active-human write revalidation.
It changes no CON authority or outbox behavior. CON-02A is therefore reconciled
as linear child `0028_shared_transactional_outbox`; AUTH's revision-specific
`0026` lifecycle tests remain revision-specific, while CON owns separate
outbox-head proof. Fresh bounded verification and exact-SHA reviewer results
below supersede earlier publication evidence.

ART-02C1 PR #154 advances trusted main to `44f2467c` and owns
`0028_artifact_admission`. It changes no outbox or CON authority behavior.
CON-02A is reconciled as its linear child
`0029_shared_transactional_outbox`; all earlier `0028` outbox results remain
historical until the bounded `0029` row and exact-SHA reviewers pass.

REV-02A PR #156 then advances trusted main to `3b1d6379` with planning and
contract decomposition only. It adds no migration, runtime model, outbox seam,
or CON authority. The `0029` migration topology and generic outbox behavior
remain unchanged; fresh exact-SHA proof and review bind to this baseline.

## Current PR #154 Reconciliation Verification Results

```text
73 passed, 32 deselected (exact bounded isolated outbox/migration row on ART `0028` / CON `0029` after Proxy repair)
outbox coverage: 95.90% (244 statements, 10 missed; required: at least 90%)
10 passed in 0.09s (security-sensitive assertion helper suite after CI Proxy regression repair)
1 passed in 63.77s (AUTH revision-specific 0026 lifecycle downgrade/reupgrade)
Alembic heads: one head, `0029_shared_transactional_outbox`
Ruff on CON-02A, ART `0028`, CON `0029`, and reconciliation tests: passed
repository-wide isolated PostgreSQL plus real-MinIO suite: required in GitHub CI after push
```

The first bounded run exposed a test-helper compatibility failure while walking
an opaque Pydantic internal `Mapping`; the outbox exception and formatted
traceback contained no secret. The helper now falls back to recursively
inspecting concrete object state and fails closed when state is unavailable.
Its dedicated regression test proves a raising mapping cannot hide a retained
secret. The repaired exact bounded row passed as recorded above.

The first GitHub Backend run on PR head `44fc78f3` completed the full suite at
87.19 percent repository coverage but failed two outbox secrecy tests because
recursive helper inspection traversed a live module-globals dictionary while a
nested import mutated it. The assertion now snapshots built-in dictionary
entries before recursion. A deterministic nested-mapping regression proves the
old live iteration failure and the repaired traversal; no product or CI
threshold behavior changed.

The next GitHub Backend run on PR head `2fba5bab` reached the same 87.19
percent repository coverage and 1665 passing tests, then exposed a Celery
`Proxy` that reports `isinstance(proxy, dict)` without owning built-in dict
storage. Real dict subclasses are now identified from their concrete type;
framework proxies use the Mapping protocol. The exact regression proves the
Proxy path still detects a retained secret rather than bypassing inspection.

## Implemented Contract

- One immutable event envelope contains caller-provided event, aggregate,
  project, correlation, causation, idempotency, and payload facts; PostgreSQL
  forces producer and occurrence time.
- Operational delivery state is a separate closed shape prepared for a later
  migration-free 02B implementation but exposes no transition service here.
- Insert/update/delete/truncate custody prevents forged initial state, immutable
  envelope mutation, illegal transitions, evidence regression, physical
  deletion, and archival reopening.
- Terminal retention is archival-in-place. A guarded downgrade takes an
  `ACCESS EXCLUSIVE` lock and refuses durable rows.
- Payload input is strict, bounded, lower-snake-case JSON with recursive secret
  key rejection, ordinary validation mapped to a detached domain error, one
  defensive deep snapshot, and stable input/persistence errors with no
  payload-bearing cause or context.
- Append reuses `canonical_json_hash`, reserves with PostgreSQL conflict
  handling, locks both identities in deterministic order, flushes only the
  caller session, and never commits or publishes.
- Exact replay preserves database occurrence time; any immutable drift or split
  event/idempotency identity raises `outbox_idempotency_conflict`.

## Pre-PR #153 Reconciliation Verification Results

```text
43 passed, 30 deselected in 60.22s (exact bounded isolated outbox row after final review repair)
outbox coverage after final review repair: 95.73% (required: at least 90%)
78 passed in 378.36s on current main's outbox/migration, real-MinIO ART, and AUTH-09D-B suite
pre-repair outbox coverage: 95.43%
8 passed, 56 deselected in 50.92s (exact contract selector)
2 passed in 88.51s (affected AUTH lifecycle downgrade tests)
16 passed in 102.10s (isolated database runner self-tests with admin URL)
real API contract end-to-end on 0027: passed
88 passed (agent-loop gates after AUTH-09D-B)
Ruff: passed
Docstring coverage: passed at 90.4%
Markdown links: passed for 15 changed Markdown files
Workstream/AUTH/ART/REV stale-contract scans: passed after PR #152 reconciliation
merge intent and git diff --check: passed
Alembic heads: one head, 0027_shared_transactional_outbox after PR #152 (historical)
repository-wide isolated PostgreSQL plus real-MinIO suite: required in GitHub CI after push
```

## Pre-Reconciliation Verification Results

These results were produced on the former `f18b620` / outbox-0026 chain. They
prove the implementation before AUTH-09D-A but are not publication evidence for
the reconciled `93dd3924` / outbox-0027 chain. PR #153 supersedes that chain;
fresh bounded `8d5eb15b` / outbox-0028 evidence is recorded separately and
GitHub CI owns exact-head repository-wide proof after the full PR is pushed.

```text
33 passed in 151.73s on the former ART 0025 -> CON 0026 chain
outbox coverage: 95.43% (required: at least 90%)
8 passed, 51 deselected in 125.42s (exact contract selector)
1 passed, 25 deselected in 96.33s (migration/downgrade guard)
16 passed in 180.79s (isolated database runner self-tests in a quiet window)
real API contract end-to-end: passed
1347 passed in 17741.96s / 4:55:41 (exact isolated PostgreSQL full suite)
repository coverage: 85.35% (required: at least 78%)
isolated evidence database: workstream_test_d513fb2f03b1
isolated evidence tree: f72bb6e6dc71cb38dcb397b34caf9db6f916db4c
isolated evidence Alembic head: 0026_shared_transactional_outbox (superseded)
87 passed (agent-loop gates)
Ruff: passed
Docstring coverage: passed at 91.5%
Markdown links: passed for 15 changed Markdown files
Workstream stale wording: passed
AUTH stale documentation: passed
ART stale contract: passed at phase artifact_store_cutover
REV stale contract: passed
git diff --check: passed
local roadmap workbook: absent, so the one-sheet export check is not applicable
```

The historical full suite used the unchanged test command, isolation rule,
assertions, and coverage thresholds. Its measured 4:55:41 runtime explains why
repository-wide proof is now CI-owned. Exact-SHA reviewer results were
superseded when AUTH-09D-A changed the backend and migration head.

## Test Delta

Tests add strict schema/privacy bounds; one core-schema error boundary across
constructor, model methods, and `TypeAdapter` Python/JSON/string modes; valid
mode parity; hostile top-level and nested dict/list/string subclasses;
payload-free outbox traceback locals, including idempotency conflicts;
defensive nested-payload snapshotting across the first await; stable database
error redaction; caller rollback including injected post-reservation failure;
exact replay; immutable drift; split identity; concurrent commit/rollback
races; direct-SQL custody; legal and illegal delivery transitions; terminal
archival; delete/truncate denial; exact migration surface; and concurrent
downgrade writer behavior. Shared secret-retention helper tests prove dict,
list, and string subclasses plus slotted dataclass state cannot bypass deep
inspection through the tested override paths.
Existing assertions, skips, coverage settings, and test commands are unchanged.

## Current Exact-SHA Internal Review

Reviewed code SHA: `9be9c88a19c4301f2b7ac606b6782604a48472bb`

Reviewed against trusted main:
`3b1d63796c086f53fc2b0aeefe096387b82485ec`

Reviewer runs: `/root/proxy_repair_senior_arch_reuse`,
`/root/proxy_repair_qa_product_docs`, `/root/proxy_repair_security_ci`

Open sub-agent sessions: none

Valid findings addressed: yes. The repair loop corrected the ART-parent
downgrade target, closed separated and compact sensitive-key-name bypasses,
preserved benign key-like words, and refreshed the active status baseline and
bounded evidence. The GitHub full-suite repair snapshots mutable framework
state and adds deterministic regression coverage. The final confirmation
passed all nine tracks.

| Reviewer | Result | Blocking findings |
|---|---|---|
| Senior engineering | PASS | none |
| QA/test | PASS | none |
| Security/auth | PASS | none |
| Product/ops | PASS | none |
| Architecture | PASS | none |
| Docs | PASS | none |
| Reuse/dedup | PASS | none |
| Test delta | PASS | none |
| CI integrity | PASS | none |

## Superseded Pre-PR #153 Internal Review

Historical reviewed code SHA: `460573287270965d730c83f5f1e52f3acf1c0671`

Reviewed at: 2026-07-19T09:15:29Z

Reviewer run IDs: senior-engineering/architecture/reuse-dedup=/root/con01_arch_senior_reuse; QA-test/product-ops/docs/test-delta=/root/con01_qa_product_docs; security-auth/CI-integrity=/root/con01_security_ci

Valid findings addressed: yes

Open sub-agent sessions: none

This review remains useful implementation history but is not publication
evidence for the `8d5eb15b` / `0028` reconciliation. All nine tracks must bind
to the new exact candidate SHA before push.

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| Senior engineering | PASS WITH LOW RISKS | None | Fixed top-level hostile mapping traversal and confirmed valid constructor/model/TypeAdapter modes. Fixed model configuration is intentional; arbitrary runtime string-mode option overrides are not a supported 02A contract. |
| QA/test | PASS | None | Hostile string, slotted state, top-level payload, and conflict-retention regressions close every prior test gap. |
| Security/auth | PASS | None | Payload-bearing validation, persistence, and conflict state is absent from the tested exception and outbox traceback graph; no AUTH surface was added. |
| Product/ops | PASS | None | Generic flush-only persistence adds no product lifecycle, payment, dispatcher, or worker behavior. |
| Architecture | PASS | None | Caller-session ownership and feature-neutral 02A boundary remain intact. |
| Docs | PASS | None | Focused proof, GitHub-only full-suite gate, and complete Ruff scope agree across the contract and trust bundle. |
| Reuse/dedup | PASS | None | Canonical hashing and shared deep-retention assertion are reused; no duplicate framework was introduced. |
| Test delta | PASS | None | All changes are additive; no skip, xfail, threshold, selector, or assertion weakening. |
| CI integrity | PASS | None | Existing GitHub full-suite and 78 percent repository coverage gates remain unchanged and mandatory. |

The final repair loop resolved every earlier reviewer finding: nested payload
snapshotting, stable payload-free persistence errors, rollback after a
post-reservation failure, detached Pydantic entry points, valid JSON/string
mode parity, `TypeAdapter` coverage, traceback-local scrubbing, hostile nested
and top-level built-in subclasses, shared helper traversal, idempotency-
conflict reservation retention, and complete repeatable Ruff scope.

## Remaining Human Gates

- Human approval is required for the specific PR before merge.
- 02B remains a separately started chunk and owns dispatcher/recovery behavior.
- `outbox.dispatch`, its fixed service identity/static row, AUTH-09E admission,
  prepared authorization, and activation remain upstream gates for 02B.
- No passing check grants a feature handler authority through dispatcher
  authority.

## Stop Condition

Stop at the CON-02A full PR human checkpoint. Do not merge without explicit
approval for that PR and do not begin `WS-CON-001-02B` automatically.
