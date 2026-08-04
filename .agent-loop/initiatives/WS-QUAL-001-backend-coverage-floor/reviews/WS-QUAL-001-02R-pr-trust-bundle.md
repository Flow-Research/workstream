# WS-QUAL-001-02R PR Trust Bundle

## Goal and scope

Add meaningful fast project/setup behavior tests under the reviewed
`WS-QUAL-001-02R` contract. The implementation changes
`backend/tests/test_projects.py`; this evidence and status update remain within
the allowed QUAL initiative tree. No production, migration, workflow,
threshold, dependency, or public API file changes.

## What changed

- Added direct behavior coverage for payment-policy persistence, canonical
  project resolution, strict effective-policy limits, activation readiness,
  submission-policy derivation and approval, correction/supersession, setup
  queue payloads and bounded failures, post-submit summaries, and correction
  history, plus project-agent runtime composition from current settings.
- Added 60 focused cases through 17 test functions and parameterization.
- Reused production service, repository, and queue entry points without adding
  duplicate broad HTTP/PostgreSQL flows.

## Exact baseline and projected acceptance

Current-main Backend run `30891776021` on
`b47a7e64f7d75cda8a0681d1aff3bf0c4a5be4aa` recorded:

- 2,936 completed tests;
- 20,782 covered of 23,455 statements (88.603709 percent);
- 718.586 seconds hosted wall time;
- 546.201 seconds in the slowest lane.

The 89.55-percent threshold requires `ceil(23,455 * 0.8955) = 21,004`
covered statements. The first exact-head run (`30902039458`) passed every
semantic lane and the final fan-in, but measured 21,003 / 23,455, or
89.545939 percent: one statement below this chunk's stricter contract target.
The final composition-boundary test exercises the previously uncovered
project-agent runtime factory statement. A fresh GitHub exact-head fan-in is
authoritative for acceptance.

## Test and CI integrity

- Ruff passes for the changed test file.
- Focused new tests pass; reviewer runs observed 59 passing cases before the
  final one-case composition correction, which also passes independently.
- No test was removed, skipped, xfailed, weakened, or excluded from coverage.
- No workflow, runner, lane, coverage command, or threshold changed.
- Stale wording, authorization documentation, artifact contract, Markdown
  link, lightweight Agent Gates, whitespace, and allowed-path checks pass.
- The constrained local full-file run timed out at 1,200 seconds without a
  test failure at 40 percent. It is not used as performance evidence.

## Internal review

Senior engineering, QA, test delta, CI integrity, product/ops, and reuse/dedup
all passed on code revision `f32ebc6c0c2cf8411ca0373127b0fefd523156f8`.
Focused re-review of the CodeRabbit repair passed on `055b0db4`; the final
one-test coverage correction is undergoing focused re-review. Low risks are
the size of the existing mixed test module, fake fidelity, and the need to
confirm exact coverage/runtime in hosted CI.

## External review

| Source | Status | Required outcome |
|---|---:|---|
| Agent Gates | Passed on `055b0db4` | Must pass again on final exact PR head |
| Backend | Correction pending | Run `30902039458` passed, but 89.545939 percent missed the contract by one statement; final head must reach >=89.55 percent |
| CodeRabbit | Passed/rate-limited on `055b0db4` | Settings-cache finding repaired and answered; final exact-head status required |

## Human review focus

- Confirm the tests assert real project/setup behavior rather than percentage
  padding.
- Inspect fake fidelity around policy provenance and queue state transitions.
- Confirm hosted coverage reaches at least 89.55 percent and hosted runtime
  does not increase by more than 10 percent without explanation.

## Stop

This chunk does not raise the global CI floor. It stops for human review after
the exact-head external checks complete.
