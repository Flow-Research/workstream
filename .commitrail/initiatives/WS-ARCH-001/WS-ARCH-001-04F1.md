# ARCH-04F1 — Verified checker failure evidence

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Risk: L1 — current-result custody and separation of contributor/setup failure.
- Intended merge outcome: the existing CHECKERS completion port verifies and returns
  retained completed failure evidence as well as success, without granting routing
  authority or enabling replacement submission.

## Intent

Advance group 1 of the [first contributor milestone](planning/PLAN.md#first-complete-contributor-milestone).
The existing `require_current_completion` accepts only `allow_review`, so TASK
cannot use its currentness, receipt and material checks for contributor remediation
or project/setup failures. `read_current_result` already classifies all completed
results, and retained typed member results already carry bounded codes/counters.
Extend that operation rather than adding a second checker command, result store,
classification algorithm or compatibility path.

## Bounded change

1. Extend `VerifiedEvaluationCompletion` with the existing immutable typed phase
   result. Bind its reference to that result using the canonical reference
   validator. Keep private artifact/provider coordinates out of this contract.
2. `require_current_completion` accepts each supported completed recommendation,
   independently derives it from the stored request/result and requires equality
   with the caller completion. Preserve exact owner-qualified lookup, event and
   phase receipts, material facts, root transaction and TASK-before-CHECKERS locks.
   Return the stored typed result, never caller-supplied findings.
3. Infrastructure failures remain ineligible for a completed-result reference:
   they produce no contributor-remediation evidence. Task/setup faults retain
   their distinct recommendation; no contributor blame is synthesized.
4. Preserve explicit `allow_review` gates in TASK request/source/outcome and the
   hidden completion handler. Widening the owner read must not authorize failure
   acceptance or move tasks. No new AUTH action, database mutation or registry entry.

## Allowed files

- `backend/app/modules/checkers/api/execution.py` and
  `backend/app/modules/checkers/execution_coordination.py`.
- Focused CHECKERS execution/contract tests and their existing support;
  existing TASK routing tests/support only for real failure fixtures and proving
  success-only consumer rejection. Exact test-lane inventory if adding a module.
- This record, adopted 04F contract, affected ARCH plan/map/overview and index,
  roadmap and checker architecture/spec text needed to distinguish verified
  failure reads from pending remediation mutation/authority/replacement intake.

## Prohibited changes

No new storage/migration, new evaluator, new checker command, authority activation,
production handler registration, public route, task transition, submission writer,
REV decision/revision or contribution/payment effect. No compatibility aliases,
skipped tests, weakened gates, time-cap changes or retained-data rewriting.

## Acceptance criteria

- Real fixed-service execution and PostgreSQL produce success, contributor failure
  and task/setup failure; exact completion verification returns the original full
  typed member results/counters and material/receipt lineage, without writes.
- Independently substituting a valid but wrong routing recommendation is rejected
  after exact identity lookup. A guard-removal probe fails that intended assertion.
- Real stored foreign-project completion selectors/receipts reject; valid controls
  for both stored sources precede substitutions. Retain existing TASK-currentness
  and transaction proofs, and add failure-specific successor/currentness proof.
- Infrastructure failure cannot become a verified completed result or contributor
  correction. Queued/nonterminal and superseded runs remain unavailable.
- A failure completion cannot enter existing success-only TASK reservation/source
  or completion delivery; prove no routing request or outcome effects.
- Pure contract proof rejects a different valid result bound to the same wrapper;
  retain the canonical result digest/reference checks rather than duplicating them.
- Caller rollback, native/root transaction and TASK-before-CHECKERS custody are
  unchanged. Inspect existing concurrency proof before adding redundant races.

## Risk and review routing

Plan review before implementation: architecture/reuse, security and QA/test delta.
Implementation adds docs/product operations and CI integrity for inventory and
full hosted evidence. Human focus: failure recommendation equality, exact stored
findings, currentness and no accidental success-authority expansion.

## Evidence

Inspect existing `tests/checkers/execution/test_coordination.py` and
`tests/tasks/post_submit_routing/test_evaluation_currentness.py` first.
New focused tests exercise the actual coordinator and fixed-service executor with
real PostgreSQL and artifact storage. Fixture handlers retain canonical definitions
and replace one selected handler with a definition-valid controlled failure. This
proves the declared classification/finalization path, not the underlying structural
condition. A separate controlled finalization fixture reuses `final_facts` and the
real executor's `finalize`, adding a valid non-empty `PostSubmitCounter`; no database
custody or AUTH guard is disabled to seed it.

Executable regression map:

| File under `backend/tests/` | Test | Boundary |
| --- | --- | --- |
| `checkers/execution/test_completion_evidence.py` | `test_current_completion_returns_exact_stored_result` | Success, contributor failure and setup fault through real executor with canonical/controlled registered handlers; exact typed results and material/receipt equality; no writes |
| same | `test_current_completion_preserves_nonempty_stored_counters` | Real authorized finalization of controlled bounded result with populated counters; returned result equals stored JSON/result |
| same | `test_current_completion_rejects_wrong_derived_recommendation` | All other valid recommendation literals with exact original identities; removing only equality guard must fail rejection assertion |
| same | `test_failure_completion_rejects_foreign_owner_and_receipts` | Two valid stored projects/completions before independent event/project/task/submission/reference/execute/finalize substitutions |
| same | `test_failure_completion_loses_currentness_to_successor` | Failure positive control, actual successor reservation, stale completion rejection without restoring fence |
| `checkers/execution/test_execution.py` (retained) | `test_infrastructure_failure_is_terminal` | Existing real unavailable-handler outcome; no completion event; canonical coordinator rejection. Pure wrapper test also rejects an infrastructure result |
| `checkers/execution/test_completion_contract.py` | `test_verified_completion_rejects_mismatched_result` | Valid wrapper plus different valid result; canonical identity/digest binding and infrastructure rejection |
| `tasks/post_submit_routing/test_failure_completion.py` | `test_stored_failure_cannot_enter_task_routing_or_completion_delivery` | Both actual stored failure envelopes; request/source/outcome guards and hidden handler reject, no routing request/manifest/outcome or economic effects |

Shared fixture code stays in `checkers/execution/completion_fixture.py`, reusing
existing material, executor and finalization helpers. New consumer-evidence modules
use existing TASK lanes with measured capacity; existing modules, partitioning,
time caps, services and exact-once inventory remain unchanged.

Run focused owner tests, boundaries, lint, stale wording, links and
Commitrail checks; then the complete hosted suite with zero skips/deselections
and real PostgreSQL/MinIO cleanup. Reports identify the exact head and any compatible
unchanged proof; a proposed test is not runtime evidence.

## Next boundary

Use these verified failure facts in TASK's authorized immutable remediation
handoff, then replacement ZIP intake through the existing ART/TASK operation and
explicit infrastructure recovery. This is the first owner-sized part of 04F;
04F remains incomplete until its failure/recovery workflow is proven. Production
composition, public intake and the real first-layer drill remain downstream.
