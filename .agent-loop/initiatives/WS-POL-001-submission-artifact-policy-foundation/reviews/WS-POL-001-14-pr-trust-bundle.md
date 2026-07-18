# PR Trust Bundle: WS-POL-001-14

## Chunk

`WS-POL-001-14` - Submission finalization and API-visible proof.

## Goal

Make the submission handoff explicit as finalization, preserve system actor
audit provenance for automatic pre-review checker execution, and prove the
Terminal Benchmark flow through authorized HTTP APIs instead of database
inspection.

## Human-approved intent

Chunk contract:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-14-submission-finalize-no-db-drill.md`

The user approved returning to the Terminal Benchmark drill only after the
system exposes enough API surface to inspect setup, task context, finalization,
checker runs, and audit events without manually inspecting Postgres.

## What changed

- Added public `POST /api/v1/submissions/{submission_id}/finalize`.
- Removed the public submission lock route and public lock wording from active
  code, tests, examples, and docs.
- Public submission/evidence responses now use `finalized_at`.
- Finalization validates task locked context before running the pre-review gate.
- Finalization uses an atomic database guard so concurrent finalize calls cannot
  duplicate audit or checker side effects.
- The repository docstring explicitly explains that the public finalization
  lifecycle still writes the existing internal `locked_at` persistence column.
- Automatic checker execution writes audit events as
  `workstream-system:pre-review-gate` with requester provenance.
- Checker-run detail/list, task audit, task responses, submission responses,
  and locked-context reads use scoped operator visibility instead of broad role
  checks.
- API contract and Terminal Benchmark drills now prove finalization, checker
  runs, audit events, pre-submit blocking, and revision v1/v2 behavior through
  HTTP responses.

## Why it changed

The Terminal Benchmark drill exposed two product-contract problems:

- Public `/lock` wording sounded like storage mutation, not a project manager
  handoff into the pre-review gate.
- The proof still depended on database inspection for confidence in lifecycle
  state.

This chunk makes the public boundary clearer and proves the current Workstream
system through the same API surfaces a real operator or worker would use.

## Design chosen

Finalization is an operator handoff:

```text
submitted latest submission
-> POST /submissions/{id}/finalize
-> validate locked task context
-> write submission_finalized audit event
-> execute pre-review gate under workstream-system:pre-review-gate
-> expose checker-run and audit state through authorized APIs
```

The database column remains `locked_at` internally because it still represents
the immutable persistence boundary. Public responses expose `finalized_at`
because that is the user-facing lifecycle concept.

Authorization is intentionally scoped:

- `admin` can manage all tasks.
- `project_manager` can manage tasks they created until project-scoped role
  assignment exists.
- A worker who also has `project_manager` in the token does not receive
  operator-shaped data for an assigned task they did not create.

## Alternatives rejected

- Keeping a public lock alias: rejected because v0.1 has no backward
  compatibility obligation and stale names cause product confusion.
- Treating the automatic checker as the requester: rejected because audit must
  distinguish the system actor from the human/operator who finalized the
  submission.
- Continuing to prove lifecycle state through database reads: rejected because
  the live drill should use authorized product APIs.

## Scope control

### Allowed files changed

- `.agent-loop/` WS-POL-001 plan/status/chunk/review files
- `backend/app/modules/checkers/router.py`
- `backend/app/modules/checkers/runner.py`
- `backend/app/modules/checkers/service.py`
- `backend/app/modules/tasks/authorization.py`
- `backend/app/modules/tasks/router.py`
- `backend/app/modules/tasks/schemas.py`
- `backend/app/modules/tasks/service.py`
- `backend/scripts/api_contract_e2e.py`
- `backend/scripts/week2_api_e2e.py`
- `backend/tests/test_checkers.py`
- `backend/tests/test_tasks.py`
- active architecture, operations, roadmap, and checker docs
- `examples/terminal_benchmark/` README, notes, and API drill

### Files outside scope

None intentionally.

## Product Behavior

- [ ] No Workstream product behavior changed.
- [x] Product behavior changed and is explained here:

Project managers/admins finalize submitted packets instead of calling a public
lock endpoint. Workers see `finalized_at` in public submission/evidence
responses. Operators can inspect checker-run and audit state through API
responses after finalization.

## Acceptance criteria proof

- [x] Public finalization route replaces the old public handoff.
  Evidence: router/tests/scripts use `/finalize`; active stale scan passed.
- [x] Finalization is idempotent for latest submitted version and rejects
  invalid states.
  Evidence: task tests cover success, idempotency, unfinished task, unsubmitted
  row, non-latest version, unauthorized actors, invalid locked context, and
  duplicate side-effect prevention on repeated finalization.
- [x] Automatic checker run uses system actor audit provenance.
  Evidence: task/checker tests assert `workstream-system:pre-review-gate` and
  requester provenance.
- [x] Operator-only details are scoped correctly.
  Evidence: security findings were fixed; tests cover wrong project manager and
  multi-role worker/project-manager cases.
- [x] API contract drill proves checker-run and audit APIs after finalization.
  Evidence: `scripts/api_contract_e2e.py` passed.
- [x] Terminal Benchmark drill proves current lifecycle through HTTP-visible
  responses.
  Evidence: `examples/terminal_benchmark/terminal_benchmark_api_e2e.py` passed
  with the real OpenAI Agents SDK adapter.

## Tests/checks run

```bash
cd backend && .venv/bin/ruff check app/modules/tasks/repository.py app/modules/tasks/service.py tests/test_tasks.py
cd backend && .venv/bin/pytest tests/test_tasks.py::test_finalize_submission_requires_operator_and_latest_version tests/test_tasks.py::test_submission_finalize_guard_is_atomic -q
cd backend && .venv/bin/pytest tests/test_tasks.py tests/test_checkers.py
cd backend && WORKSTREAM_DATABASE_URL=<local-test-db-url> .venv/bin/python scripts/api_contract_e2e.py
bash -lc 'set -a; set +a; export WORKSTREAM_DATABASE_URL=<local-test-db-url>; export WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL=${WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL:-gpt-4.1}; export WORKSTREAM_TERMINAL_BENCH_FIXTURE=<redacted-local-fixture-path>; export WORKSTREAM_TERMINAL_BENCH_GUIDE_ROOT=<redacted-local-guide-root>; backend/.venv/bin/python examples/terminal_benchmark/terminal_benchmark_api_e2e.py'
python3 scripts/check_markdown_links.py
git diff --check
```

Result summary:

```text
Focused Ruff: passed
Focused finalize guard tests: 2 passed
Task/checker suite: 133 passed
API contract real API E2E: passed
Terminal Benchmark real API E2E: passed
Markdown links: passed for 27 changed Markdown files
Active stale wording scan: passed
git diff --check: passed
```

## Test delta

### Tests added

- Finalize rejects unfinished tasks.
- Finalize rejects unsubmitted submission rows.
- Finalize rejects invalid locked context.
- Finalize rejects non-latest submission versions.
- Finalize uses an atomic repository guard and repeat finalization does not
  create duplicate checker runs or audit events.
- Wrong project manager and multi-role worker/project-manager visibility cases
  for audit, checker, submission, task, and locked-context responses.
- Checker-run result integrity in the API contract drill.
- Terminal Benchmark blocked pre-submit proof with no persisted submission.

### Tests modified

- Existing submission lock tests and scripts were renamed to finalization.
- Existing checker-run tests now assert system actor/requester provenance and
  scoped response shapes.

### Tests removed/skipped

None.

## CI integrity

- [x] Coverage threshold unchanged
- [x] Lint unchanged
- [x] Typecheck unchanged
- [x] No workflow weakening
- [x] No package script weakening
- [x] No unpinned new GitHub Action
- [x] Checkout credential persistence unchanged

## External review

External review response file:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-14-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Addressed locally | Valid atomic finalization and docs findings fixed; broad project-manager access suggestion rejected as conflicting with scoped-operator security contract. Must rerun after push. |
| GitHub checks | Pending rerun | Local checks passed; GitHub checks must rerun after push. |

## Reviewer results

Reviewed implementation SHA: `8372c6e15299960cc78231603a463d238464bc35`

Reviewed at: 2026-07-08T12:01:24Z

Reviewer run IDs:

- senior engineering: `reviewer-run-id`
- QA/test: `reviewer-run-id`
- security/auth: `reviewer-run-id`
- product/ops: `reviewer-run-id`
- architecture: `reviewer-run-id`
- docs: `reviewer-run-id`
- reuse/dedup: `reviewer-run-id`
- test delta: `reviewer-run-id`
- senior engineering CodeRabbit fix: `reviewer-run-id`
- QA/test CodeRabbit fix: `reviewer-run-id`
- security/auth CodeRabbit fix: `reviewer-run-id`
- product/ops CodeRabbit fix: `reviewer-run-id`
- architecture CodeRabbit fix: `reviewer-run-id`
- docs CodeRabbit fix: `reviewer-run-id`
- reuse/dedup CodeRabbit fix: `reviewer-run-id`
- test delta CodeRabbit fix: `reviewer-run-id`
- senior engineering docstring fix: `reviewer-run-id`
- docs docstring fix: `reviewer-run-id`

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Atomic guard direction and final docstring bridge accepted; true concurrent API race test remains optional follow-up. |
| QA/test | PASS WITH LOW RISKS | None | Coverage accepted; repository guard and repeat-finalize side effects covered. |
| security/auth | PASS WITH LOW RISKS | None | Scoped-operator visibility and permissions wording accepted. |
| product/ops | PASS WITH LOW RISKS | None | User-facing wording and proof terminology fixed. |
| architecture | PASS WITH LOW RISKS | None | Boundary accepted; allowed-file contract updated. |
| docs | PASS WITH LOW RISKS | None | Multi-role precheck and finalization wording now match service behavior; evidence/trust metadata refreshed after docstring fix. |
| reuse/dedup | PASS WITH LOW RISKS | None | Shared authorization helper accepted. |
| test delta | PASS WITH LOW RISKS | None | Tests strengthened without weakening. |

All sub-agent sessions were closed before final reporting.

## Remaining risks

- Post-submit policy derivation agent work remains future scope. Current
  finalization executes the existing project post-submit checker policy.
- Reviewer packet visibility remains a future review-lifecycle chunk.
- CodeRabbit and GitHub checks must rerun after the final evidence push.

## Human review focus

Please inspect:

- Confirm `finalize` is the right public handoff name and `finalized_at` is the
  right public timestamp.
- Confirm scoped operator authorization is acceptable until project-scoped role
  assignment exists.
- Confirm system actor/requester audit separation is clear enough for future
  review and reputation records.
- Confirm the Terminal Benchmark proof now satisfies the real-API drill intent.

## Human ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
