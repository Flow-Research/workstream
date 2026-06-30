# PR Trust Bundle: WS-POL-001-02

## Chunk

`WS-POL-001-02` - Async Guide Analysis And Policy Derivation

## Goal

Add the Workstream-owned project-agent runtime boundary, deterministic local
runtime, optional OpenAI Agents SDK adapter, async guide sufficiency and policy
derivation routes, and the trusted project pre-submit checker compiler.

## Human-Approved Intent

- Intent: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/INTENT.md`
- Plan: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/PLAN.md`
- Chunk contract: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-02-async-guide-analysis-policy-derivation.md`

## What Changed

- Added `ProjectGuideAgentRuntime` as a Workstream-owned port.
- Added deterministic local/test project-agent runtime with no network or API key requirement.
- Added optional OpenAI Agents SDK adapter behind the port.
- Added config for `WORKSTREAM_PROJECT_AGENT_RUNTIME` and `WORKSTREAM_OPENAI_AGENT_MODEL`.
- Added async project routes to run guide sufficiency analysis and submission artifact policy derivation.
- Ensured agent calls run outside DB row locks and revalidate under lock before persistence.
- Added trusted compiler for project `PreSubmitCheckerPolicy` bundles.
- Moved test/E2E helpers away from direct compiled-field mutation and onto compiler-produced rows.
- Aligned ADR/checker docs with the implemented contract: agent derives policy; compiler builds and validates checker spec/bundle.
- Documented optional OpenAI agent runtime setup in `README.md`.

## Scope Control

Allowed files changed:

- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**`
- `README.md`
- `backend/pyproject.toml`
- `backend/app/core/config.py`
- `backend/app/core/hashing.py`
- `backend/app/core/project_agents.py`
- `backend/app/interfaces/project_agents.py`
- `backend/app/adapters/project_agents/**`
- `backend/app/modules/projects/**`
- `backend/app/modules/checkers/**`
- `backend/tests/test_projects.py`
- `backend/tests/test_checkers.py`
- `backend/tests/test_tasks.py`
- `backend/scripts/week1_api_e2e.py`
- `docs/architecture_checker_framework.md`
- `docs/decision_0011_submission_artifact_policy_drives_pre_submit.md`

Files outside scope:

- None.

## Product Behavior

Project setup can now run two Workstream-internal agent-assisted steps:

1. `ProjectGuideSufficiencyAgent` assesses an immutable guide-source snapshot.
2. `SubmissionArtifactPolicyDerivationAgent` derives a draft submission artifact policy after sufficiency passes or warnings are acknowledged.

The agent does not evaluate worker submissions. Workstream compiles deterministic
checker logic from the effective project submission artifact policy, and the
compiled project `PreSubmitCheckerPolicy` remains the runtime authority.

This PR does not move task locked-context or submission creation runtime. That
is still Chunk 3.

## Acceptance Criteria Proof

- Runtime port and adapter isolation: `backend/app/interfaces/project_agents.py`, `backend/app/adapters/project_agents/**`
- Deterministic local runtime: `backend/app/adapters/project_agents/deterministic.py`, `backend/tests/test_projects.py`
- Optional OpenAI adapter: `backend/app/adapters/project_agents/openai_agents.py`, `backend/tests/test_projects.py`
- Async agent API routes: `backend/app/modules/projects/router.py`, `backend/app/modules/projects/service.py`
- No row lock across agent calls: `backend/app/modules/projects/service.py`
- Source snapshot binding and idempotency: `backend/tests/test_projects.py`
- Warning acknowledgement before derivation: `backend/tests/test_projects.py`
- Trusted compiler and primitive coverage: `backend/app/modules/checkers/compiler.py`, `backend/tests/test_checkers.py`
- Approval-time compiler persistence: `backend/app/modules/projects/service.py`, `backend/tests/test_projects.py`
- Existing task/E2E helper migration: `backend/tests/test_tasks.py`, `backend/scripts/week1_api_e2e.py`

## Tests And Checks Run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_checkers.py -k 'pre_submit_compiler'
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py -k 'deterministic_sufficiency_agent or openai_runtime_misconfiguration or derivation_agent_requires_warning'
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_tasks.py
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py tests/test_checkers.py
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
```

Result summary:

```text
Ruff passed.
Focused compiler tests passed: 11 passed.
Focused project-agent tests passed: 4 passed.
Task tests passed: 39 passed.
Full backend test suite passed before final primitive/docs-only fix: 264 passed in 2477.25s.
Post-fix project/checker suite passed: 197 passed in 1389.02s.
Docstring coverage passed: 100.0% (487/487).
Markdown link check passed for 11 changed Markdown files.
Stale wording check passed.
Loop memory state check passed.
Internal review evidence gate passed.
git diff --check passed.
Agent gate returned REVIEW_REQUIRED as expected for L1 risky-path work.
```

## Reviewer Results

Reviewed code SHA: `c2f79b835a1bb033ffffca79ec507b77efcaae3b`

Reviewed at: `2026-06-30T10:43:35Z`

Reviewer run IDs: see `WS-POL-001-02-internal-review-evidence.md`.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Confirmed lazy runtime, no lock across agent calls, adapter isolation, and project-scoped compiler. |
| QA/test | PASS AFTER FIXES | None | Confirmed idempotency, compiler semantic tests, warning acknowledgement, and approval-time compilation. |
| security/auth | PASS WITH LOW RISKS | None | No valid security findings; adapter failures are sanitized and guide material remains untrusted. |
| product/ops | PASS | None | Confirmed operator workflow and primitive vocabulary are aligned. |
| architecture | PASS | None | Confirmed scope, boundaries, and no task/submission runtime drift. |
| CI integrity | PASS | None | Confirmed optional extra only; no gate weakening. |
| docs | PASS | None | Confirmed docs align with implementation and config. |
| reuse/dedup | PASS | None | Confirmed shared hashing and registry validation reuse. |
| test delta | PASS | None | Confirmed tests were strengthened and no skips/deletions were added. |

## External Review

External review has not run yet for this chunk. CodeRabbit, GitHub Actions, and
human PR review should be checked after the PR is opened.

## Remaining Risks

- Chunk 3 must lock task references to guide snapshot, effective project submission artifact policy hash, and project pre-submit checker bundle hash.
- Chunk 3 must migrate submission creation runtime away from transitional task `required_files` and `required_evidence`.
- OpenAI runtime production use still depends on environment-managed credentials and model choice.
- Primitive-to-checker projection is registry-validated; future registry metadata can reduce duplicated checker-name strings if needed.

## Human Review Focus

Please inspect:

- `ProjectService` async transaction boundaries around agent calls.
- OpenAI adapter isolation and sanitized failure handling.
- Compiler semantic coverage rules and primitive vocabulary.
- Approval-time persistence of compiled `PreSubmitCheckerPolicy`.
- Docs agreement between ADR 0011, checker framework, chunk contract, and README config.

## Human Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
