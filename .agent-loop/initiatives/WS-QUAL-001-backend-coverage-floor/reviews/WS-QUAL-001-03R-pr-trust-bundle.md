# WS-QUAL-001-03R PR Trust Bundle

## Chunk

`WS-QUAL-001-03R` — Checker Behavior Coverage.

## Goal

Raise global backend coverage from the exact current-main 89.619016-percent
baseline to at least 90.25 percent through meaningful checker-owned behavior
tests, without changing production behavior or CI policy.

## Human-approved intent

Continue the approved QUAL initiative one bounded chunk at a time, preserve
real PostgreSQL/system proof, and move fast business-rule coverage into the
smallest owning layer rather than adding arbitrary infrastructure or shards.

## What changed and why

- Added 94 focused cases in `backend/tests/test_checkers.py` for runner,
  compiler, service, authorization, routing, redaction, policy-lock, automatic
  gate, recovery, provenance, and fail-closed behavior.
- Updated only the QUAL initiative's discovery, contract, map, status, and
  review evidence so durable memory matches the implementation.
- The tests cover 168 statements that current main does not cover: checker
  service 107, runner 45, and compiler 16.

## Design chosen

Use direct runner/compiler/service tests and bounded repository/session fakes
for checker-owned decisions. Keep existing broad HTTP/PostgreSQL flows as the
small contract suite and leave production composition unchanged.

## Alternatives rejected

- More arbitrary CI shards: they move runtime rather than establish ownership.
- Duplicate end-to-end flows: slower and disallowed by the contract.
- Artificial execution or coverage exclusions: they would weaken trust.
- Production refactoring in this chunk: outside the reviewed test-only scope.

## Scope control

The implementation is limited to `backend/tests/test_checkers.py` and the
`WS-QUAL-001` initiative tree. It changes no production code, migration,
workflow, threshold, dependency, public API, skip, xfail, or coverage omit
rule. The circuit breaker passed with a size exception because this remains one
test file and one production boundary with no production behavior change.

## Product behavior

No product behavior changes. The tests preserve the distinction between
checker routing recommendations and the only stored human review decisions:
`accept`, `needs_revision`, and `reject`.

## Acceptance criteria proof

Current-main Backend run `30921410531` on `5b853d50` recorded 3,068 completed
tests, 21,453 / 23,938 covered statements (89.619016 percent), 727.166 seconds
hosted wall time, and a 567.994-second slowest lane. The target requires 21,605
covered statements. Local differential coverage projects 21,621 / 23,938
(90.320829 percent); hosted exact-head fan-in is authoritative.

## Tests and checks run

- Ruff: pass.
- Focused selection: 94 passed, 76 deselected in 37.76 seconds.
- Checker collection: 170 tests collected.
- Git whitespace and allowed-path checks: pass.
- Lightweight Agent Gates: 10 passed.
- Local full checker file: approximately 95 percent completed without failure
  before the 1,200-second runner bound; not claimed as a complete pass.

## Test delta and CI integrity

Tests are additive. No assertion was deleted or weakened, and no test was
skipped, xfailed, deselected by CI, or excluded from coverage. No workflow,
runner, lane, service, coverage command, or threshold changed.

## Reviewer results

Senior engineering, QA/test, test delta, CI integrity, product/ops, and
reuse/dedup reviewed exact code SHA `23235d506d9f16cb000ba9e9219e4f3e28ddbb79`.
All pass. The first reuse finding was withdrawn after git history proved the
cited broad system tests were pre-existing main content shifted by the new
insertion.

## External review

Agent Gates passed on the published head. CodeRabbit's one trivial finding was
valid: the contract needed to distinguish the bounded local 1,200-second
diagnostic timeout from hosted complete-pass authority. The contract now says
that explicitly. Backend exact-head semantic lanes and final fan-in are still
running; human review remains pending.

## Remaining risks and follow-up work

- Hosted coverage may differ from the local differential projection.
- Hosted runtime must remain within 10 percent of the recorded baseline unless
  the change is explained before merge.
- Raising the blocking global floor is a separate successor decision after
  this exact-head coverage is proven; it is not part of 03R.

## Human review focus

- Confirm tests exercise observable checker invariants rather than percentage
  padding.
- Inspect fake fidelity around policy provenance and gate state transitions.
- Confirm hosted coverage is at least 90.25 percent and runtime remains within
  the contract bound.

## Human merge ownership

This chunk stops after exact-head external checks and human review. It will not
be merged without the user's explicit approval for this PR.
