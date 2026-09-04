# PR Trust Bundle: WS-AUTH-001-12F3

## Chunk

`WS-AUTH-001-12F3` — Fixed-Service Policy Derivation (L1).

## Goal

Activate submission-policy derivation only for `workstream.project.setup`, run
it through fresh fixed-service PREP in Celery, and remove public inline agent
derivation.

## Human-approved intent

Complete AUTH-12F3 end to end without weakening authorization, tests, or CI;
use GitHub Actions for the full suite and coverage proof.

## What changed

- Activated only `project.submission_artifact_policy.derive` for the fixed
  project-setup service.
- Removed the public derive endpoint and role-based product-service seam.
- Added exact setup/lineage/provenance validation, fresh pre-I/O and final PREP,
  total lock ordering, atomic decision/product evidence, and exact replay.
- Added a DB-enforced `reserved -> pending -> committed` execution-claim state
  machine so process loss cannot repeat material or agent I/O.
- Made warning-acknowledgement replay retry a failed same-generation enqueue
  without rerunning sufficiency.
- Updated migration parity, schema fingerprint, tests, specifications, and ops
  guidance.

## Why it changed

Automatic setup derivation needed a closed fixed-service boundary, exact
transactional evidence, and crash-safe replay before it could be activated.

## Design chosen

Reuse the opaque `PreparedAuthorizationHandle` protocol and fixed-service
composition. Commit only a deterministic `reserved` execution claim before
external I/O; after I/O, reload and lock the complete lineage, consume fresh
transaction-bound authority, then atomically bind and complete replay with the
policy and setup output.

## Alternatives rejected

- Public or human inline agent invocation.
- Raw authorization context, serialized handles, or an ART-local evaluator.
- Advisory locking alone; it cannot survive process loss.
- Deleting durable reservations during downgrade.

## Scope control

No approval/effective/pre-submit mutation, post-submit policy activation, ART
behavior, generic service authority, frontend work, or CI changes are included.

## Product behavior

An authoritative same-generation sufficiency result permits only the fixed
setup service to derive one immutable draft. Exact committed redelivery returns
that draft without external I/O. A failed post-reservation execution remains
durably fenced. Project Managers may create manual drafts but cannot invoke the
derivation agent inline.

## Acceptance criteria proof

- Fixed service/action isolation and PREP integrity: authorization tests.
- Exact running/completed custody and stale-output denial: focused project tests.
- Real commit, immutable provenance/defaults, exact replay, durable failure
  reservation, and zero-I/O redelivery: PostgreSQL integration test.
- Migration upgrade/downgrade and single-head integrity: isolated Alembic test.
- Removed route: OpenAPI/import-reachability project tests.

## Tests/checks run

- Ruff and Python compile checks passed.
- AUTH selector: 2 passed.
- Worker/replay/custody selector: 8 passed.
- CI lane integrity: 33 passed.
- PostgreSQL service/replay/crash test: 1 passed.
- Isolated Alembic round trip: 1 passed.
- Stale authorization wording, Markdown links, and `git diff --check` passed.
- Full repository coverage is intentionally delegated to hosted GitHub Actions.

## Test delta

Added fixed-service PREP, worker composition, stale custody, exact completed
replay, real PostgreSQL success/replay/crash recovery, route removal, catalogue
activation, migration-head, provenance, immutable-manual-update, and default
policy-floor assertions. No tests were skipped or weakened.

## CI integrity

No workflow, lane, lint, coverage, or package-script changes. Repository-wide
78% and changed-subsystem 90% requirements remain intact.

## Reviewer results

Architecture, security, QA, senior engineering, product/ops, test-delta, reuse,
docs, and CI-integrity reviews passed after findings were fixed.

## External review

CodeRabbit reported no actionable comments. The first hosted Backend run found
three stale contract expectations after the fixed-service cutover; they were
corrected without changing authorization behavior or CI. Fresh exact-head
GitHub Actions checks are required after the corrective push.

The corrective local evidence passed: Ruff, two focused OpenAPI/audit tests,
and four focused PostgreSQL migration regressions. CI-integrity re-review passed
with no required fixes.

The following hosted run passed every semantic lane, then found that the
real-API drill had not injected its deterministic agent into the new 12F3
policy-derivation module. Test composition was corrected without adding a
production fallback; the API-contract support selector passes locally.

## Remaining risks

Low: execution-fence and worker composition scaffolding parallels sufficiency;
extract a shared helper only if a third boundary establishes a stable pattern.

## Follow-up work

After human merge, reassess and start `WS-AUTH-001-12F4` as its own bounded
chunk. Do not start it automatically from this PR.

## Human review focus

Review migration 0059's one-way guards, the pre-I/O commit boundary, final
atomic PREP/evidence transaction, exact completed replay, and fixed-service-only
catalogue activation.

## Human merge ownership

Only the user may authorize merge of the specific PR.
