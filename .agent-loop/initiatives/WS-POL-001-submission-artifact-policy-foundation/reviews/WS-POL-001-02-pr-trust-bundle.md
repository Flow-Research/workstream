# PR Trust Bundle: WS-POL-001-02

## Chunk

`WS-POL-001-02` - Async Guide Analysis And Policy Derivation

## Goal

Add the Workstream-owned project-agent runtime boundary, local fixture adapter,
optional OpenAI Agents SDK adapter, async guide sufficiency and policy
derivation routes, and the trusted project pre-submit checker compiler.

## Human-Approved Intent

- Intent: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/INTENT.md`
- Plan: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/PLAN.md`
- Chunk contract: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-02-async-guide-analysis-policy-derivation.md`

## What Changed

- Added `ProjectGuideAgentRuntime` as a Workstream-owned port.
- Added local fixture project-agent runtime with no network or API key requirement.
- Added optional OpenAI Agents SDK adapter behind the port.
- Added adapter-specific config for `WORKSTREAM_PROJECT_AGENT_RUNTIME_ADAPTER`,
  `WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL`, and
  `WORKSTREAM_PROJECT_AGENT_RUN_TIMEOUT_SECONDS`.
- Added `WORKSTREAM_PROJECT_AGENT_MAX_PROMPT_BYTES` so model-backed adapters
  fail closed before sending oversized guide-source material to a runtime.
- Added async project routes to run guide sufficiency analysis and submission artifact policy derivation.
- Ensured agent calls run outside DB row locks and revalidate under lock before persistence.
- Added typed guide source material, source items, and representative task
  material so setup agents can inspect bounded, hash-bound project examples
  without introducing task-scoped checker generation.
- Persisted server-owned sufficiency and derivation agent provenance instead of trusting runtime/provider identity fields.
- Required agent derivation to follow a Workstream-agent sufficiency report for the same immutable snapshot.
- Required manual policy creation to wait for sufficiency clearance.
- Revalidated agent-derived policy provenance before approval and guide activation.
- Rejected approval of tampered draft policy rows where `policy_body` no longer
  matches `policy_hash`.
- Encoded sanitized FastAPI validation errors through `jsonable_encoder` before
  returning 422 responses.
- Clarified that `run-sufficiency-agent` can reuse an existing sufficiency
  report while `derive-submission-artifact-policy` rejects manual sufficiency
  reports.
- Added trusted compiler behavior for project `PreSubmitCheckerPolicy` bundles.
- Moved test/E2E helpers away from direct compiled-field mutation and onto compiler-produced rows.
- Aligned ADR/checker/data-model docs with the implemented contract.

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
- `docs/architecture_data_model.md`
- `docs/architecture_lockdown.md`
- `docs/decision_0011_submission_artifact_policy_drives_pre_submit.md`
- `docs/glossary.md`
- `docs/internal_reviews/2026-06-16_submission_artifact_policy_architecture.md`
- `docs/operations_workspace_packet_convention.md`
- `docs/product_first_user_flows.md`
- `docs/spec_chunk_3_project_guide_foundation.md`
- `docs/spec_chunk_7_checker_runner_registry.md`
- `docs/spec_chunk_8_submission_artifact_policy_checkers.md`
- `docs/template_checker_policy.md`
- `docs/template_project_guide.md`
- `docs/template_submission_artifact_policy.md`

Files outside scope:

- None. `docs/product_first_user_flows.md` was added to the chunk contract after
  internal review because the one-line clarification directly resolved the
  manual-sufficiency product/docs finding.

## Product Behavior

Project setup can now run two Workstream-internal agent-assisted steps:

1. `ProjectGuideSufficiencyAgent` assesses an immutable guide-source snapshot.
2. `SubmissionArtifactPolicyDerivationAgent` derives a draft submission artifact policy after agent sufficiency passes or passes with warnings.

Manual sufficiency reports remain possible for operator-controlled setup, but
they clear only the manual policy path. Agent derivation requires an
agent-created sufficiency report for the same snapshot. If a manual report
already occupies a snapshot, operators continue with manual policy creation or
create a fresh guide-source snapshot before running the agent-derived path.

The agent does not evaluate worker submissions. Workstream compiles deterministic
checker logic from the effective project submission artifact policy, and the
compiled project `PreSubmitCheckerPolicy` remains the runtime authority.
Warnings from sufficiency analysis can produce a draft policy before
acknowledgement, but approval and guide activation still require acknowledgement
by `admin` or `project_manager`.

This PR does not move task locked-context or submission creation runtime. That
is still Chunk 3.

## Acceptance Criteria Proof

- Runtime port and adapter isolation: `backend/app/interfaces/project_agents.py`, `backend/app/adapters/project_agents/**`
- Local fixture runtime: `backend/app/adapters/project_agents/local_fixture.py`, `backend/tests/test_projects.py`
- Optional OpenAI Agents SDK adapter: `backend/app/adapters/project_agents/openai_agent_sdk.py`, `backend/tests/test_projects.py`
- Async agent API routes: `backend/app/modules/projects/router.py`, `backend/app/modules/projects/service.py`
- No row lock across agent calls: `backend/app/modules/projects/service.py`
- Source snapshot binding and idempotency: `backend/tests/test_projects.py`
- Server-owned agent provenance: `backend/app/modules/projects/service.py`, `backend/tests/test_projects.py`
- Warning acknowledgement before approval/activation: `backend/tests/test_projects.py`
- Manual sufficiency/manual policy boundary: `backend/app/modules/projects/service.py`, `backend/tests/test_projects.py`
- Approval-time policy body/hash consistency: `backend/app/modules/projects/service.py`, `backend/tests/test_projects.py`
- Sanitized validation error encoding: `backend/app/main.py`, `backend/tests/test_projects.py`
- Trusted compiler and primitive coverage: `backend/app/modules/checkers/compiler.py`, `backend/tests/test_checkers.py`
- Approval-time compiler persistence: `backend/app/modules/projects/service.py`, `backend/tests/test_projects.py`
- Existing task/E2E helper migration: `backend/tests/test_tasks.py`, `backend/scripts/week1_api_e2e.py`

## Tests And Checks Run

```bash
cd backend && .venv/bin/python -m ruff check app/modules/projects/service.py tests/test_projects.py
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'sufficiency_agent or derivation_agent or submission_artifact_policy_creation_requires_sufficiency_report or manual_submission_artifact_policy_rejects_agent_provenance_fields or sufficiency_warnings_require_acknowledgement or blocking_sufficiency_report_prevents_policy_creation or worker_cannot_approve_submission_artifact_policy or draft_submission_artifact_policy_can_be_updated' -q
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'agent_derived_policy_approval_revalidates_server_owned_provenance or activation_revalidates_agent_derived_policy_provenance or sufficiency_agent_persists_server_owned_agent_identity or derivation_agent_requires_agent_sufficiency_report or derivation_agent_idempotency_uses_server_owned_policy_version or manual_submission_artifact_policy_rejects_agent_provenance_fields' -q
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q
cd backend && .venv/bin/python -m pytest tests/test_checkers.py tests/test_tasks.py -q
cd backend && .venv/bin/python -m pytest tests -q
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'sufficiency_agent_reuses_existing_manual_report or submission_artifact_policy_approval_rejects_body_hash_mismatch or project_guide_rejects_non_finite_source_metadata or review_policy_rejects_invalid_decision_names or project_create_validation_errors_are_structured' -q
cd backend && .venv/bin/python -m ruff check app/main.py app/modules/projects/service.py tests/test_projects.py
```

Result summary:

```text
Ruff touched files passed.
Ruff app/tests/scripts passed.
Focused provenance/manual-boundary tests passed: 13 passed, 162 deselected in 273.92s.
Focused approval/activation provenance revalidation tests passed: 6 passed, 171 deselected in 45.37s.
Project suite passed before final revalidation fix: 175 passed in 1745.31s.
Project suite passed after final revalidation fix: 177 passed in 837.59s.
Checker and task suites passed: 75 passed in 455.30s.
Full backend suite passed before the final small revalidation/doc patch: 279 passed in 2707.35s.
Docstring coverage passed: 100.0% (499/499).
Markdown link check passed for 24 changed Markdown files.
Stale wording check passed.
git diff --check passed.
Internal review evidence gate passed.
Loop memory state check passed.
Agent gate result: REVIEW_REQUIRED because this is a large L1 policy/runtime/compiler chunk touching risk-sensitive files and backend package config.
Final external-review fix focused tests passed: 5 passed, 174 deselected in 50.32s.
Final external-review fix touched-file ruff passed.
Focused runtime/source tests passed: 12 passed, 172 deselected in 41.99s.
Regression cluster after source_material_refs repair passed: 18 passed, 166 deselected in 119.94s.
Affected project/checker suite passed after helper repair: 221 passed in 1204.17s.
OpenAI Agents SDK adapter/config prompt-budget tests passed: 6 passed, 179 deselected in 10.82s.
Optional v1 manifest/content_excerpt focused tests passed: 4 passed, 182 deselected in 32.90s.
Final affected project/checker suite passed: 223 passed in 1435.00s.
Final docstring coverage passed: 100.0% (504/504).
```

## Reviewer Results

Reviewed code SHA: `aaffa7b25d88fcdff9a87e89d6a2f7ff6ceabb46`

Reviewed at: `2026-07-01T16:36:58Z`

Reviewer run IDs: see `WS-POL-001-02-internal-review-evidence.md`.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Runtime naming, warning-derivation contract drift, tracked local fixture, and process-evidence binding were reviewed. |
| QA/test | PASS AFTER FIXES | None | Confirmed adapter naming/config, timeout and prompt-budget coverage, local fixture guard, representative task material, and project/checker lifecycle coverage. |
| security/auth | PASS AFTER FIXES | None | Confirmed OpenAI Agents SDK errors remain sanitized, content excerpts and representative task material are untrusted source material, and the prompt-size guard fails closed. |
| product/ops | PASS | None | Confirmed project-scoped setup semantics, no task-scoped checker generation, and no confusion with product review decisions. |
| architecture | PASS | None | Confirmed the port/adapter boundary, project-scoped compiler, typed source material, and no service import of SDK classes. |
| CI integrity | PASS WITH LOW RISKS | None | No workflow weakening. Low residual: CI does not install optional `.[agents]`; adapter behavior remains delayed-import and fake-SDK tested. |
| docs | PASS AFTER FIXES | None | Confirmed scope lists, warning-derivation wording, status/trust/external-review state, and template docs are aligned. |
| reuse/dedup | PASS AFTER FIXES | None | Confirmed source item parsing uses `_source_material_items` and v1 manifests without `content_excerpt` remain valid. |
| test delta | PASS | None | Confirmed tests were strengthened without skips, xfails, or weakened assertions. |

## External Review

External review and CI passed on pushed head
`d7e4669f6fa6bd782a8f12e43bb5b94449fb235d`:

- CodeRabbit: pass, `Review completed`.
- Agent Gates: pass.
- Backend test: pass.
- Week 1 API Demo UI: pass.
- Unresolved non-outdated review threads: none.

## Remaining Risks

- Chunk 3 must lock task references to guide snapshot, effective project submission artifact policy hash, and project pre-submit checker bundle hash.
- Chunk 3 must migrate submission creation runtime away from transitional task `required_files` and `required_evidence`.
- OpenAI Agents SDK adapter production use still depends on environment-managed credentials and model choice.
- CI does not currently install optional `.[agents]`; adapter behavior is covered through delayed-import and fake-SDK tests.
- Local fixture adapter repeats a few default literals, but the output is untrusted and revalidated before approval.

## Human Review Focus

Please inspect:

- `ProjectService` async transaction boundaries around agent calls.
- Server-owned agent provenance and approval/activation revalidation.
- OpenAI Agents SDK adapter isolation and sanitized failure handling.
- Compiler semantic coverage rules and primitive vocabulary.
- Approval-time persistence of compiled `PreSubmitCheckerPolicy`.
- Manual sufficiency versus agent-derived setup path wording.

## Human Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
