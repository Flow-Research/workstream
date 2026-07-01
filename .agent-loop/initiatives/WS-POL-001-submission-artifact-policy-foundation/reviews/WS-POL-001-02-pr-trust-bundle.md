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
- Persisted server-owned sufficiency and derivation agent provenance instead of trusting runtime/provider identity fields.
- Required agent derivation to follow a Workstream-agent sufficiency report for the same immutable snapshot.
- Required manual policy creation to wait for sufficiency clearance.
- Revalidated agent-derived policy provenance before approval and guide activation.
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

Files outside scope:

- None. `docs/product_first_user_flows.md` was added to the chunk contract after
  internal review because the one-line clarification directly resolved the
  manual-sufficiency product/docs finding.

## Product Behavior

Project setup can now run two Workstream-internal agent-assisted steps:

1. `ProjectGuideSufficiencyAgent` assesses an immutable guide-source snapshot.
2. `SubmissionArtifactPolicyDerivationAgent` derives a draft submission artifact policy after agent sufficiency passes or warnings are acknowledged.

Manual sufficiency reports remain possible for operator-controlled setup, but
they clear only the manual policy path. Agent derivation requires an
agent-created sufficiency report for the same snapshot. If a manual report
already occupies a snapshot, operators continue with manual policy creation or
create a fresh guide-source snapshot before running the agent-derived path.

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
- Server-owned agent provenance: `backend/app/modules/projects/service.py`, `backend/tests/test_projects.py`
- Warning acknowledgement before derivation: `backend/tests/test_projects.py`
- Manual sufficiency/manual policy boundary: `backend/app/modules/projects/service.py`, `backend/tests/test_projects.py`
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
```

## Reviewer Results

Reviewed code SHA: `66fb9936c0a9f7fa04bbe783483dbdff0cfb5eb3`

Reviewed at: `2026-07-01T08:56:11Z`

Reviewer run IDs: see `WS-POL-001-02-internal-review-evidence.md`.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Provenance revalidation and final scope correction reviewed. |
| QA/test | PASS | None | Confirmed Postgres-backed API and idempotency coverage. |
| security/auth | PASS | None | Confirmed provider identity cannot spoof persisted provenance. |
| product/ops | PASS AFTER FIXES | None | Confirmed manual and agent-derived setup paths are clear. |
| architecture | PASS | None | Confirmed project-scoped compiler and port/adapter boundary. |
| CI integrity | PASS WITH LOW RISKS | None | No workflow weakening; optional agent extra remains adapter-isolated. |
| docs | PASS AFTER FIXES | None | Confirmed docs now align with manual sufficiency and server-owned provenance. |
| reuse/dedup | PASS WITH LOW RISKS | None | No blocking duplication; deterministic output is still untrusted and revalidated. |
| test delta | PASS WITH LOW RISKS | None | Tests were strengthened; no skips or weakened assertions. |

## External Review

External review should be checked after pushing this final evidence commit.
CodeRabbit, GitHub Actions, and human PR review are external checks and do not
replace the internal reviewer evidence above.

## Remaining Risks

- Chunk 3 must lock task references to guide snapshot, effective project submission artifact policy hash, and project pre-submit checker bundle hash.
- Chunk 3 must migrate submission creation runtime away from transitional task `required_files` and `required_evidence`.
- OpenAI runtime production use still depends on environment-managed credentials and model choice.
- CI does not currently install optional `.[agents]`; adapter behavior is covered through delayed-import and fake-SDK tests.
- Deterministic runtime repeats a few default literals, but the output is untrusted and revalidated before approval.

## Human Review Focus

Please inspect:

- `ProjectService` async transaction boundaries around agent calls.
- Server-owned agent provenance and approval/activation revalidation.
- OpenAI adapter isolation and sanitized failure handling.
- Compiler semantic coverage rules and primitive vocabulary.
- Approval-time persistence of compiled `PreSubmitCheckerPolicy`.
- Manual sufficiency versus agent-derived setup path wording.

## Human Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
