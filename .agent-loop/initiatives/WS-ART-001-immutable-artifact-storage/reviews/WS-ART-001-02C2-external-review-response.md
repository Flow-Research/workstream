# External Review Response: WS-ART-001-02C2

## Boundary

This file records GitHub Actions and CodeRabbit separately from internal review.
It does not replace internal exact-SHA evidence.

Reviewed implementation SHA: `ad46958ac11e8b1acff98c0c5f79c9a2a68797b9`

Trusted base: `fe0e4492a7de8699c06a52921cbdaa8a1a22e567`

PR: #159, `https://github.com/Flow-Research/workstream/pull/159`

## Current Status

| Source | Status | Notes |
|---|---:|---|
| GitHub Agent Gates | PASS | Run 29751926808 passed on the exact evidence head in 24 seconds. |
| GitHub Backend | PASS | Run 29751926993: 1,783 passed, 87.23% global coverage, all scoped floors passed. |
| CodeRabbit | PASS | Current-head review completed with no findings. |
| Human review | Pending | Only the user may approve merge. |

## Comments Addressed

- GitHub Backend job 88341704126 failed
  `test_outbox_database_error_never_reflects_payload` and
  `test_outbox_conflict_does_not_retain_stored_payload` with
  `mapping state could not be inspected`. The remaining 1,727 tests passed and
  coverage was 87.23 percent, so this was not a coverage failure.
- Test inspection now treats SQLAlchemy sessions as a bounded causal boundary,
  including ORM state and root transaction rollback exceptions, instead of
  traversing opaque weak registries.
- Sanitized outbox error branches delete service and payload-bearing traceback
  locals before raising payload-free public errors. This prevents reachability
  through repository -> session -> rollback exception without taking caller
  transaction ownership.
- The focused helper/outbox matrix passes 84 tests. All nine internal reviewers
  accepted the bounded repair on the exact reviewed SHA.
- CodeRabbit reported no findings on the earlier head. No old pass is treated as
  current-head evidence. Its new exact-head review also completed with no
  findings.
- Hosted Backend run 29751926993 passed all 1,783 tests in 1,357.81 seconds.
  Global coverage remained 87.23 percent and all scoped gates remained at or
  above 90 percent.

## Comments Deferred

None. Any new hosted failure on the published head becomes a required repair
input.

## Human Decisions Needed

Explicit merge approval only after GitHub checks and current-head external
review pass. Do not start `WS-ART-001-02C3` automatically.

## Commands Rerun

```text
Focused outbox/helper suite: 84 passed
Agent gates after latest main integration: 88 passed
Alembic heads: 0030_artifact_verification
Ruff: PASS
Markdown links: PASS
git diff --check: PASS
```

The local full-suite attempt was stopped at the user's request because it was
slowing their machine. One failure marker appeared before interruption, but no
final traceback was emitted. It is not pass or failure diagnosis evidence;
hosted Backend is authoritative.

## Remaining Risks

- Hosted Backend passes the exact published head and all coverage floors.
- The test-only SQLAlchemy rollback inspection is version-coupled.
- PR #158 ART custody and PR #160 REV custody remain availability-neutral; all
  transferred actions are still planned.

## Stop Condition

Publish, wait for hosted checks and current-head CodeRabbit review, repair any
valid finding, and request explicit human merge approval. Do not merge or start
the successor automatically.
