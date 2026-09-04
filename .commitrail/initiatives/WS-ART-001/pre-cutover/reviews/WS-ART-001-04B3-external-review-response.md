# WS-ART-001-04B3 External Review Response

## Comments addressed

- The evidence-set database now binds `guide_id`, `project_id`, and
  `guide_version` to one canonical `ProjectGuide` row through a composite
  foreign key and matching unique target.
- Evidence orchestration now rejects an already-open session transaction before
  materialization, and captures the prepared generation before awaiting scratch
  work.
- Project evidence keys must project to a canonical relative path, so `.` and
  `..` cannot collapse into ambiguous evidence identities.
- The materializer and execution validator share one closed storage-scheme
  constant.
- Exact durable-evidence replay is documented as returning no new pass
  capability; later submission attempts must re-prepare the bundle.
- Migration `0058` now enforces result-status/failure-code shape and rejects a
  caller-supplied evidence-set creation timestamp outside the creating
  transaction.
- Tests cover noncanonical evidence keys, a mismatched prepared generation
  before capability consumption, and the transaction-free orchestration
  precondition.
- Evidence-set delete and truncate tests now avoid child-FK interference and
  assert the exact immutable-trigger error.
- The hosted task-lifecycle failure exposed one stale test mutation against the
  retired `evidence_keys` config field; the test now mutates the canonical
  `evidence_paths` field and proves required-evidence coverage fails closed.
- Policy primitive dispatch now has an explicit fail-closed default, result
  metadata types match their integer-only validator, result schema comes from
  the exact plan entry, and compiler/executor path checks share one helper.
- The persistence transaction explicitly starts at PostgreSQL `READ COMMITTED`
  before locked-context reads, so a conflict replay can observe the committed
  winning row.

## Comments deferred

None. CodeRabbit's suggested `task.locked_guide_id` filter was rejected because
`WorkstreamTask` intentionally has no such column. The task locks the unique
project/guide-version lineage; the new composite evidence foreign key binds the
resolved guide ID to that same project and version at persistence.

## Human decisions needed

The ART changes require no product decision. The hosted protected-mutation
workflow failure is a separate CI-reliability defect already repaired by PR
`#289`; that PR still requires repository-owner approval before merge.

## Verification

- focused Ruff validation for every changed Python file;
- focused effective/default pre-submit unit tests;
- isolated PostgreSQL evidence workflow and `0058` migration round trip;
- `git diff --check`.

## Remaining risks

PR `#291` cannot obtain a green protected-mutation result while the retired
workflow remains on `main`: its evaluator cannot map model/import-only changes
and its eight-claim ceiling is lower than this chunk's eligible target count.
No ART-local claim can safely bypass that failure.
