# Workstream PR Trust Bundle

## Chunk

`WS-QUAL-001-PLAN` - Backend Coverage Floor Planning

PR: `https://github.com/Flow-Research/workstream/pull/99`

## Goal

Plan a non-bypassable path from the measured backend coverage baseline to the
user-required permanent 90 percent application statement-coverage floor.

## Human-Approved Intent

- Intent: `../INTENT.md`
- Plan: `../PLAN.md`
- Chunk map: `../CHUNK_MAP.md`
- First proposed contract: `../chunks/WS-QUAL-001-01-coverage-harness-baseline.md`

The user corrected the minimum from 80 to 90 percent. The plan applies that
target repository-wide under `backend/app`, not only to changed files.

## What Changed

- Added intent, discovery, decisions, risks, plan, status, and six exact chunk
  contracts.
- Recorded the isolated diagnostic: 5,660/7,232 statements, 78.26 percent, and
  about 849 additional covered statements required for 90 percent on AUTH-02.
- Defined safe per-worktree database isolation after a shared database caused
  27 cascading migration errors; an isolated rerun passed 234/234 project tests.
- Defined non-decreasing floors through baseline, 82, 84, 86, 88, and 90 percent.
- Updated active loop memory and paused AUTH-02 publication without changing its
  implementation.

## Why It Changed

The backend had no executable code-coverage threshold. Setting 90 percent
immediately would make all PRs red while leaving roughly 849 statements of
legacy debt inside an unrelated auth PR. The initiative creates a reviewable,
non-gaming path to the permanent gate.

## Design Chosen

Use one coverage/database harness, then bounded additive test chunks for project
service, project boundaries, tasks, checkers, and enumerated residual modules.
Each chunk is capped at 500 implementation lines and cannot lower the precise
configured floor.

## Alternatives Rejected

- A permanently red 90 percent gate without the missing tests.
- Diff-only coverage, which does not satisfy the repository-wide requirement.
- Coverage exclusions, pragmas, or narrowed source measurement.
- One giant cross-domain test PR.

## Scope Control

### Allowed Files Changed

- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/REVIEW_LOG.md`
- `.agent-loop/WORK_QUEUE.md`
- `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**`

### Files Outside Contract

- None.

## Product Behavior

- [x] No Workstream product behavior changed.
- [ ] Product behavior changed and is explained here.

No application, test, dependency, workflow, migration, API, authorization, or
runtime file changed.

## Evidence

### Commands Run

```bash
PR_HEAD_SHA=<head> python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
gh run watch <agent-gates-run> --exit-status
gh run watch <backend-run> --exit-status
```

### Result Summary

```text
Internal review evidence gate: passed
Loop memory state: passed
Stale authorization documentation: passed
Stale Workstream wording: passed
Markdown links: passed for all changed Markdown files
Agent gate regression tests: 31 passed
Diff hygiene: passed
GitHub Agent Gates: passed
GitHub Backend including tests and API drill: passed
CodeRabbit: valid wording comment addressed; thread resolved and description check passed
```

## Acceptance Criteria Proof

- [x] The complete `backend/app` inventory and anti-exclusion policy are defined.
- [x] The database provisioner has strict local naming, owned cleanup, and
  credential-redaction requirements.
- [x] The ratchet records exact numerator/denominator and cannot decrease.
- [x] Existing CI install, lint, docstring, complete test, and API drill gates
  must remain present and non-bypassed.
- [x] Six sequential chunks have exact scope, commands, reviewers, numeric exit
  floors, 500-line budgets, and stop conditions.
- [x] Production defects exposed by coverage tests require separate fixes.
- [x] Post-merge memory and a new user start are required between chunks.

## Test Delta

### Tests Added

- None; this PR is planning-only.

### Tests Modified

- None.

### Tests Removed Or Skipped

- None.

## Internal Reviewer Results

Reviewed code SHA: `0d9dd987d546c864fa8de7bae462e5e73a1b5ea9`

Reviewed at: `2026-07-12T06:27:02Z`

Reviewer run IDs: `ws-qual-001-plan-external-fix-senior-architecture-reuse/0d9dd987d546/2026-07-12`, `ws-qual-001-plan-external-fix-qa-ci-testdelta-0d9dd98-20260712T062655Z`, `WS-QUAL-001-PLAN/security-product-docs-external-fix/0d9dd987d546/2026-07-12T06:27:02Z`

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | PASS | None | Six bounded chunks and deterministic controls are reviewable. |
| QA/test | PASS | None | Isolated DB commands and outcome-based tests are required. |
| Security/auth | PASS | None | Local DB, credential, redaction, and no-product-change boundaries pass. |
| Product/ops | PASS | None | Lifecycle, state, audit, queue, HTTP, and fail-closed assertions are required. |
| Architecture | PASS | None | One reusable provisioner and policy boundary; no runtime scope. |
| CI integrity | PASS | None | Precise ratchet, inventory, existing gates, and bypass rejection pass. |
| Docs | PASS | None | Runbook and durable sequencing requirements pass. |
| Reuse/dedup | PASS | None | Existing fixtures remain canonical; copied helpers are forbidden. |
| Test delta | PASS | None | Additive tests and deterministic weakening scans are required. |

Internal evidence:
`WS-QUAL-001-PLAN-internal-review-evidence.md`

## External Review

External response:
`WS-QUAL-001-PLAN-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | PASS | Grammar thread resolved automatically; all five description/review checks passed. |
| GitHub checks | PASS | Agent Gates and Backend, including tests and API drill, passed on external-fix head `1931196`. |

## CI And Gate Integrity

- [x] No workflow weakening.
- [x] No lint/test/docstring gate weakening.
- [x] No coverage threshold weakening.
- [x] No package script weakening.
- [x] No unpinned new GitHub Action.
- [x] Checkout credential persistence remains disabled.

## Remaining Risks

- Chunk 01 must measure clean main; the 78.26 percent value is diagnostic from
  AUTH-02.
- Coverage tests may expose production defects that require separate changes.
- Suite runtime is high; performance work must not weaken isolation or proof.

## Follow-Up Work

After plan merge and post-merge memory, the user may explicitly start only
`WS-QUAL-001-01`. Do not start later chunks or resume AUTH-02 automatically.

## Human Review Focus

- Staged 82/84/86/88/90 floors and 500-line chunk budgets.
- DB ownership, credentials, cleanup, and redaction.
- App inventory and base-ref enforcement against coverage gaming.
- The proposed pause and later resumption of AUTH-02.

## Human Merge Ownership

- [x] I can explain what changed.
- [x] I can explain why it changed.
- [x] I know what could break.
- [x] I accept the remaining planning risks.
- [ ] The user explicitly approved this specific PR for merge.
