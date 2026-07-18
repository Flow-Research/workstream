# External Review Response: WS-POL-002-02

## Source

PR #88 external checks and CodeRabbit comments.

## Comment Triage

| Source | Severity | Status | Response |
|---|---:|---|---|
| CodeRabbit | Minor | fixed | Normalized compiled post-submit worker return dictionaries. |
| CodeRabbit | Trivial | fixed | Wrapped migration composite FK names and matching downgrade drops with `op.f()`. |
| CodeRabbit | Trivial | fixed | Deduplicated mutable Celery setup task configuration. |
| CodeRabbit | Major | already satisfied | Migration 0014 explicitly rejects existing draft-era checker rows before adding non-null setup-provenance columns. |
| CodeRabbit | Major | stale / not applied | `.agent-loop/REVIEW_LOG.md` line 23 describes already-merged PR #87, not current PR #88. |
| CodeRabbit | Major | invalid; clarified / not applied | Internal engineering reviewer verdicts must remain `PASS`, `PASS WITH LOW RISKS`, or `PASS AFTER FIXES`; product review decision tokens are not used for engineering evidence, and the evidence tables now say so explicitly. |
| CodeRabbit | Major | fixed | Removed requester-provenance mismatch from automatic pre-review gate requeue eligibility. |
| CodeRabbit | Minor | fixed | Clarified "required shared" grammar in the chunk contract. |

## Comments Addressed

### Worker return shape for compiled post-submit policies

Status: addressed.

Finding:

- CodeRabbit found inconsistent `post_submit_policy_compiled` worker return
  dictionaries across newly compiled, already compiled, and stale-recovery
  paths.

Decision:

- Valid. Worker results are audit/debug evidence and should have one terminal
  shape.

Fix:

- Normalized compiled and idempotent worker returns to include `status`,
  `idempotent`, and `post_submit_checker_policy_id`.
- Added focused regression assertions for the idempotent and redelivery paths.

### Composite foreign-key naming in migration 0014

Status: addressed.

Finding:

- CodeRabbit found composite foreign-key names in
  `0014_post_submit_setup_continuation.py` that were not wrapped with
  `op.f()`.

Decision:

- Valid. Migration naming should consistently respect Alembic naming
  conventions.

Fix:

- Wrapped the three checker-policy composite FK names with `op.f()` in upgrade
  and used matching `op.drop_constraint(op.f(...), ...)` calls in downgrade.

### Celery setup task config duplication

Status: addressed.

Finding:

- CodeRabbit found repeated Celery configuration assignment for pre-submit and
  post-submit setup tasks.

Decision:

- Valid. The repeated block was low risk but easy to keep consistent now.

Fix:

- Replaced the duplicated assignment block with one loop over the setup tasks,
  preserving the existing broker, result backend, eager mode, and `memory://`
  fallback behavior.

## Comments Already Satisfied Or Not Applied

### Existing checker-policy rows during migration

Status: already satisfied by the current migration contract.

Finding:

- CodeRabbit requested either a backfill path before enforcing new non-null
  checker-policy provenance columns, or an explicit reset requirement.

Decision:

- The reset requirement is the intended contract for this building-phase
  schema. We are not preserving draft-era checker rows that lack setup
  provenance.

Evidence:

- Migration `0014_post_submit_setup_continuation.py` runs
  `_preflight_no_legacy_checker_policy_rows()` before adding the non-null
  provenance columns and raises a clear reset error for existing draft-era
  rows.

### Review log wording

Status: not applied.

Finding:

- CodeRabbit flagged `.agent-loop/REVIEW_LOG.md` line 23 as if it claimed PR
  #88 external review was complete while PR #88 was still pending.

Decision:

- The finding is stale/out of scope for `WS-POL-002-02`. That entry describes
  merged PR #87 (`WS-POL-002-01`), not the current PR #88 gate. No code or
  evidence change is needed.

### Internal reviewer result values

Status: clarified; product-token rewrite not applied.

Finding:

- CodeRabbit requested changing internal reviewer result values from
  `PASS`, `PASS WITH LOW RISKS`, and `PASS AFTER FIXES` to Workstream product
  review decision tokens such as `accept`.

Decision:

- Invalid for the engineering loop. Product review decisions are
  `accept`, `needs_revision`, and `reject`; internal engineering reviewer
  results are process evidence and intentionally use engineering verdicts.

Evidence:

- `AGENTS.md` requires keeping engineering-loop review separate from
  Workstream product review decisions.
- `.codex/agents/*-reviewer.toml` reviewer agents end with `PASS`,
  `PASS WITH LOW RISKS`, or `FAIL`.
- `scripts/check_internal_review_evidence.py` explicitly accepts
  `PASS`, `PASS AFTER FIXES`, and `PASS WITH LOW RISKS` and would reject the
  proposed product decision tokens in this evidence table.

Follow-up:

- Added explicit notes before the reviewer-result tables in the internal
  evidence and PR trust bundle so the engineering verdict values are not
  mistaken for Workstream product review decision values.

### Requester-provenance mismatch requeue

Status: addressed.

Finding:

- CodeRabbit found `requester_provenance_mismatch` in the automatic gate
  retryable failure set.

Decision:

- Valid. A requester-provenance mismatch means the checker-run failure details
  and locked submission audit must be inspected as an integrity failure, not
  treated as a queue or setup defect.

Fix:

- Removed `requester_provenance_mismatch` from the retryable failure codes.
- Updated the tampered-provenance regression test to assert `/finalize` returns
  HTTP 409 and leaves the failed checker run terminal.
- Updated the submission and pre-review gate specs to name provenance mismatch
  as non-repairable through automatic requeue.

### Chunk-contract grammar

Status: addressed.

Finding:

- CodeRabbit flagged the phrase "required shared" in the chunk contract.

Decision:

- Valid wording cleanup.

Fix:

- Rephrased the sentence to "required that ... helpers be shared."

## Commands Rerun

```bash
cd backend && .venv/bin/pytest tests/test_alembic.py -q
cd backend && .venv/bin/pytest tests/test_projects.py::test_project_setup_queue_syncs_all_setup_task_settings -q
cd backend && .venv/bin/pytest tests/test_projects.py::test_post_submit_continuation_is_idempotent_after_compile tests/test_projects.py::test_post_submit_continuation_running_worker_redelivery_resumes_setup -q
cd backend && .venv/bin/ruff check app/modules/projects/setup_queue.py app/workers/project_setup.py app/modules/projects/models.py tests/test_projects.py tests/test_alembic.py
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
cd backend && .venv/bin/pytest tests/test_tasks.py::test_queued_gate_rejects_tampered_requester_provenance -q
cd backend && .venv/bin/pytest tests/test_tasks.py::test_queued_gate_rejects_tampered_requester_provenance tests/test_tasks.py::test_finalize_repairs_locked_submission_with_missing_pre_review_gate tests/test_tasks.py::test_failed_pre_review_gate_repair_is_idempotent_while_queued tests/test_tasks.py::test_eager_pre_review_gate_failure_after_submission_is_repairable tests/test_tasks.py::test_unknown_checker_gate_failure_is_repairable tests/test_tasks.py::test_nonrepairable_failed_gate_does_not_return_success tests/test_tasks.py::test_queued_gate_policy_error_is_failed_and_repairable tests/test_tasks.py::test_queued_gate_fails_closed_when_lock_audit_is_missing -q
cd backend && .venv/bin/ruff check app/modules/checkers/service.py tests/test_tasks.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/test_agent_gates.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Final rebind result: `check_internal_review_evidence.py` passed after the
internal evidence and trust bundle were bound to reviewed implementation SHA
`67fb3caa302e03e5fdf99d4ad148c200d86348df`.

## External Check Status

GitHub Actions and CodeRabbit passed on the previous pushed head. This
evidence-only response update must run on the PR head before human merge
review.

## Human Decisions Needed

None after GitHub current-head checks are green. Human merge review remains the
required checkpoint.

## Remaining Risks

- `WS-POL-002-03` must replace the temporary CI activation bridge with the
  server-owned post-submit approval API.
