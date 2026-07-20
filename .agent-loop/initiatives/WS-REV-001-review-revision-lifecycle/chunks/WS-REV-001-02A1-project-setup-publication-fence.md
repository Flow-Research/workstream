# Chunk Contract: WS-REV-001-02A1 - Project And Setup Publication Fence

## Goal

Make every current Project Guide setup writer serialize through one shared
Project-first database fence and stable row-type/ID lock order. Preserve all
current route permissions, request/response shapes, guide activation behavior,
policy semantics, and setup-job orchestration.

## Risk Class

L1 concurrency, transaction, and shared project/setup service behavior.

## Preconditions

- Parent `WS-REV-001-02A` is merged with exact current-main dependency proof.
- The user separately starts this child from then-current trusted main.
- Read-only discovery confirms the writer inventory and no sibling merge has
  introduced an additional direct writer or migration conflict.

## Exact Writer Inventory

The fence covers these `ProjectService` mutation entry points:

```text
create_guide
update_draft_guide
create_guide_source_snapshot
approve_current_post_submit_checker_policy
request_post_submit_checker_policy_correction
create_guide_sufficiency_report
run_guide_sufficiency_agent persistence phase
acknowledge_guide_sufficiency_warnings
create_submission_artifact_policy
run_submission_artifact_policy_derivation_agent persistence phase
run_post_submit_checker_policy_derivation_agent persistence phase
update_submission_artifact_policy
approve_submission_artifact_policy
activate_guide
update_project_setup_run_task_id
update_project_setup_run_status
start_post_submit_setup_continuation
post-commit setup enqueue task-id bookkeeping
```

The start refresh must add any newly merged writer before implementation.
`project_setup.py` remains a service caller and performs no direct ORM mutation.

## Lock Contract

Every listed writer locks and refreshes the exact Project first. It then locks
existing rows in this type order, sorting every same-type set by ascending ID:

```text
ProjectGuide
GuideSourceSnapshot
GuideSufficiencyReport
ProjectSetupRun
SubmissionArtifactPolicy
EffectiveProjectSubmissionArtifactPolicy
PreSubmitCheckerPolicy
PostSubmitCheckerPolicy
ReviewPolicy
RevisionPolicy
payment_policies table row
```

The writer revalidates guide ownership and `draft` state after the locks and
before its first mutation. `create_guide` has no pre-existing guide to
revalidate: it locks/revalidates Project, inserts the new guide explicitly as
draft, and then writes its optional setup rows. Other insert-only rows are added
only after the existing graph is locked. Locked reads use `populate_existing`
or an equivalent refresh so the identity map cannot return pre-lock state. Agent/provider I/O happens
before the transaction fence; the service rolls back that read phase, performs
remote work, then reacquires and revalidates the complete fence before writing.

Setup-run commands that receive only `setup_run_id` first read an unlocked
`setup_run_id -> project_id` projection. That projection grants no authority and
is discarded after locking Project. The command then locks and refreshes the
ProjectSetupRun and full graph in the declared order and revalidates the
project/guide relation before mutation. An internal caller may instead supply a
claimed `project_id`, but the same post-lock equality and ownership checks are
mandatory. No command locks ProjectSetupRun merely to discover Project.

## Race Matrix

The implementation test matrix contains one row for every inventoried entry
point; grouping rows as an unnamed "mutation family" is not sufficient:

```text
create_guide
update_draft_guide
create_guide_source_snapshot
approve_current_post_submit_checker_policy
request_post_submit_checker_policy_correction
create_guide_sufficiency_report
run_guide_sufficiency_agent persistence phase
acknowledge_guide_sufficiency_warnings
create_submission_artifact_policy
run_submission_artifact_policy_derivation_agent persistence phase
run_post_submit_checker_policy_derivation_agent persistence phase
update_submission_artifact_policy
approve_submission_artifact_policy
activate_guide
update_project_setup_run_task_id
update_project_setup_run_status
start_post_submit_setup_continuation
post-commit setup enqueue task-id bookkeeping
```

Each row races with activation using independent sessions, observes the
PostgreSQL wait, and forces both Project-lock acquisition orders. Same-guide
activation-first cases reload the active guide and return the command's exact
existing denial/idempotent result without mutation. `create_guide` instead
revalidates the refreshed Project and preserves its exact current new-draft
outcome. Competing 02A1 activations retain draft-only winner/loser behavior.
Writer-first cases commit the whole writer result or its exact current denial;
activation then reloads the graph and either activates a complete guide or
returns its existing readiness denial. No order may commit partial setup or
stale remote output. A separate exhaustive structural test proves every current
and newly discovered writer enters the one shared Project-first fence.

### Executable Race Harness

The race harness uses two independent `AsyncSession` instances and a third
observer connection. A test-only fence callback signals immediately after the
first session owns the Project row. The second command is then started, and the
observer polls `pg_stat_activity`/`pg_blocking_pids` until PostgreSQL reports the
second backend blocked by the first. Polling is bounded by the test timeout and
does not use sleeps as ordering evidence. Each case runs with writer-first and
activation-first Project ownership.

Except for `create_guide`, both commands target the same guide within a matrix
row, but the two acquisition-order cases may use different valid initial graphs.
Writer-first starts from the minimum graph on which that writer's documented
success or idempotent result is feasible; it commits the whole result, and then
activation either succeeds when the write completes readiness or raises its
existing `GuideActivationBlocked` readiness denial when the write intentionally
leaves the graph incomplete. Activation-first always starts from a fully ready
draft, commits activation, and then the writer refreshes the now-active guide
and raises `GuideEditBlocked`; competing activation instead raises
`GuideActivationBlocked` with "only draft guides can be activated". Every case
snapshots the complete graph before the losing command and asserts that the
loser changes no row.

| Writer row | Writer-first result | Activation-first result |
|---|---|---|
| `create_guide` | new version returns as `draft`; activation of a separate ready draft succeeds | separate ready draft activates; the distinct new version still returns as `draft` |
| `update_draft_guide` | response contains a non-source edit; activation succeeds | `GuideEditBlocked` |
| `create_guide_source_snapshot` | snapshot/setup run commit; activation returns its incomplete-setup readiness denial | `GuideEditBlocked` |
| `approve_current_post_submit_checker_policy` | approved response; activation succeeds | `GuideEditBlocked` |
| `request_post_submit_checker_policy_correction` | correction response; activation returns its compiled-output readiness denial | `GuideEditBlocked` |
| `create_guide_sufficiency_report` | graph lacks only its unique report; a passing report completes readiness and activation succeeds | ready graph activates; `GuideEditBlocked`, with the original report unchanged |
| `run_guide_sufficiency_agent` persistence | graph lacks only its unique report; agent report returns `created=True`, completes readiness, and activation succeeds | ready graph activates; `GuideEditBlocked`, with no second report inserted |
| `acknowledge_guide_sufficiency_warnings` | acknowledged response; activation succeeds | `GuideEditBlocked` |
| `create_submission_artifact_policy` | draft response; activation uses the separate approved current policy and succeeds | `GuideEditBlocked` |
| `run_submission_artifact_policy_derivation_agent` persistence | fixture has a separate manual approved current policy and no agent-derived row; agent draft returns `created=True`, and activation uses the approved current policy | ready graph activates; `GuideEditBlocked`, with no agent-derived policy inserted |
| `run_post_submit_checker_policy_derivation_agent` persistence | correction-ready graph has no compiled replacement; compiled policy returns `created=True`, and activation returns its approval-readiness denial | ready graph with its approved current policy activates; `GuideEditBlocked`, with no replacement inserted |
| `update_submission_artifact_policy` | updated draft response; activation uses the separate approved current policy and succeeds | `GuideEditBlocked` |
| `approve_submission_artifact_policy` | effective/pre-submit bundle response; activation returns its post-submit readiness denial | `GuideEditBlocked` |
| `activate_guide` | active response | losing activation raises the existing draft-only `GuideActivationBlocked` |
| `update_project_setup_run_task_id` | task-ID response | `GuideEditBlocked`; setup run unchanged |
| `update_project_setup_run_status` | status response | `GuideEditBlocked`; setup run unchanged |
| `start_post_submit_setup_continuation` | `"started"`, with a separate existing `"already_compiled"` idempotency fixture | `GuideEditBlocked`; setup run unchanged |
| post-commit enqueue task-ID bookkeeping | actual helper returns task ID and delegates once to `update_project_setup_run_task_id`; activation then sees committed bookkeeping | activation wins; helper delegates to the fenced participant, which raises `GuideEditBlocked`; no direct setup-run mutation |

For the three agent rows, a controllable runtime pauses after receiving the
valid read snapshot. The competing activation commits before the runtime
returns. Tests assert the read transaction was rolled back before runtime entry,
`pg_locks` shows no publication-fence lock during remote work, runtime failure
leaves no transaction or partial write, and successful remote return reacquires
and refreshes the complete graph before stale output is rejected.

Structural exhaustiveness is independent of the fence's registry: an AST test
discovers public `ProjectService` methods containing commit/flush calls or
assignments/add/upsert calls for Project Guide/setup models, expands the three
agent persistence phases and the after-commit enqueue helper, and compares that
discovery with the literal 18-row contract list. A separate assertion checks
that every discovered writer calls the shared fence and that no setup worker
imports ORM models or invokes approval/activation service methods.

## Allowed Files

```text
backend/app/modules/projects/{repository,service}.py
backend/app/workers/project_setup.py only if needed to remove direct persistence or call a fenced service method
backend/tests/test_projects.py
.github/workflows/backend.yml
scripts/test_agent_gates.py only to register and fail-close the additive Project coverage command
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-02A1.json
```

## Not Allowed

```text
models, migrations, public schemas, routers, or API shapes
guide activation sequence or approver-lineage behavior
active-repeat or superseded-guide activation behavior changes
Task or Submission fields, lifecycle, screening, or attribution
ReviewPolicy, RevisionPolicy, compensation-policy, or artifact-policy semantics
AUTH actions, permissions, grants, evaluators, availability, or actor schema
ART, CON, review queue, Review, FinalAcceptance, or adjudication behavior
external I/O while any publication-fence lock is held
```

## Acceptance Criteria

- One reusable repository/service fence implements the declared type order;
  writers do not reproduce ad hoc lock sequences.
- Every inventoried writer acquires Project first, refreshes locked rows, and
  revalidates the guide is still draft before mutation, with the declared
  create-guide exception for a newly inserted draft. `activate_guide` preserves
  its current draft-only behavior in this child.
- Post-commit setup enqueue never mutates `ProjectSetupRun` directly; it invokes
  the fenced task-ID participant.
- Setup jobs remain service-only callers. In this chunk, "can never become a
  Project Guide approver" means exhaustive structural isolation: setup-job modules
  neither mutate ORM models nor call human approval or guide-activation service
  entry points. Direct rejection of non-human/service approvers is owned and
  tested by `WS-REV-001-02A3`; 02A1 does not change authorization or approver
  behavior.
- Agent work performs no external call under locks and cannot persist stale
  output after guide activation or replacement setup wins.
- Independent-session tests satisfy every row and assertion in the named race
  matrix and observe PostgreSQL lock waits rather than depending on sleeps.
- Current authorization, response status, policy values, task behavior, and
  setup-job output remain unchanged.
- Backend CI adds an additive 90 percent `app/modules/projects/*` report,
  preserves the global 78 percent floor and existing task/actor/authorization/
  background-job gates, and adds an exact 90 percent `project_setup.py` report
  only if that file changes.

## Verification

The full Projects/repository suites and their coverage reports are CI-only.
Locally, run every test added for 02A1 plus the bounded static, lint,
documentation, and repository-policy commands below; do not run the full
legacy Projects or repository suite on the development host.

```bash
# GitHub Actions only (full suites and coverage):
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q tests/test_projects.py)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78)
(cd backend && .venv/bin/coverage report --include='app/modules/projects/*' --precision=2 --fail-under=90)
(cd backend && .venv/bin/coverage report --include='app/workers/project_setup.py' --precision=2 --fail-under=90) # only when this file changes

# Local bounded checks:
(cd backend && .venv/bin/python -m ruff check app/modules/projects app/workers/project_setup.py tests/test_projects.py)
(cd backend && .venv/bin/docstr-coverage --config .docstr.yaml)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 backend/.venv/bin/python scripts/test_agent_gates.py
backend/.venv/bin/python scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
git diff --unified=0 origin/main...HEAD -- backend/tests | (! rg '^-(.*assert|.*pytest\.raises|.*pytest\.mark\.(skip|xfail)|.*skipTest)')
git diff --check
```

## Required Reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human Review Focus

Complete writer inventory, stable lock order, stale identity-map prevention,
remote-I/O separation, setup-job indirect writes, race evidence, and unchanged
runtime semantics.

## Stop Condition

Merge, record automated memory, and stop. Do not start 02A3 automatically.
