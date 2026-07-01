# Internal Review Evidence: WS-POL-001-02

## Chunk

WS-POL-001-02

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: aaffa7b25d88fcdff9a87e89d6a2f7ff6ceabb46

Reviewed at: 2026-07-01T16:36:58Z

Reviewer run IDs: 019f1e55-1304-7773-94f2-3092281eb6b0, 019f1e55-767f-74e3-a742-293185c0a3bb, 019f1e55-5649-7693-8db1-af9f6f91565b, 019f1e55-3877-7872-8847-21ce2651bd80, 019f1e5c-6267-73b2-8fef-835c36172923, 019f1e5d-a8f6-7432-9f33-a201b0f8cd65, 019f1e7a-b782-72d1-90b0-ab4e72cd6210, 019f1e7e-803d-7493-bdfa-3c076c356671, 019f1e7e-1988-7363-8d44-1afea561311b, 019f1e7a-81c2-73f2-a9b1-19b8a73634cf, 019f1e8a-d40f-7f30-9391-64725ef887d3, 019f1e8a-fa0e-7b63-ad81-0055681b002f, 019f1e8c-11ab-7470-84a9-35cb3a96933d

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Runtime naming, warning-derivation contract drift, tracked local fixture, and process-evidence binding were reviewed. Final implementation SHA is `aaffa7b25d88fcdff9a87e89d6a2f7ff6ceabb46`. |
| qa/test | PASS AFTER FIXES | None | Confirmed adapter naming/config, timeout and prompt-budget coverage, local fixture guard, representative task material, and project/checker lifecycle coverage. |
| security/auth | PASS AFTER FIXES | None | Confirmed OpenAI Agents SDK errors remain sanitized, content excerpts and representative task material are untrusted source material, and the prompt-size guard fails closed. |
| product/ops | PASS | None | Confirmed project-scoped setup semantics, no task-scoped checker generation, and no confusion with product review decisions. |
| architecture | PASS | None | Confirmed the port/adapter boundary, project-scoped compiler, typed source material, and no service import of SDK classes. |
| ci integrity | PASS WITH LOW RISKS | None | No workflow weakening. Low residual: CI does not install optional `.[agents]`; OpenAI Agents SDK behavior is covered through delayed-import and fake-SDK tests. |
| docs | PASS AFTER FIXES | None | Confirmed scope lists, warning-derivation wording, status/trust/external-review state, and template docs are aligned. |
| reuse/dedup | PASS AFTER FIXES | None | Confirmed source item parsing uses `_source_material_items` and v1 manifests without `content_excerpt` remain valid. |
| test delta | PASS | None | Confirmed tests were strengthened without skips, xfails, or weakened assertions. |

## Valid Findings Addressed

- Renamed the runtime selector and adapter files to adapter-specific terms: `local_fixture` and `openai_agent_sdk`.
- Replaced vague OpenAI runtime config with `WORKSTREAM_PROJECT_AGENT_RUNTIME_ADAPTER`, `WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL`, `WORKSTREAM_PROJECT_AGENT_RUN_TIMEOUT_SECONDS`, and `WORKSTREAM_PROJECT_AGENT_MAX_PROMPT_BYTES`.
- Added a fail-closed prompt-size guard before the OpenAI Agents SDK adapter imports or calls the SDK.
- Made the local fixture adapter dev/test-only and included it in the committed tree.
- Added typed source item and representative task material contracts for setup agents.
- Added bounded `content_excerpt` support in the source snapshot manifest while preserving v1 snapshots that do not contain that optional key.
- Kept representative task material as untrusted source material for project setup only; it does not create task-scoped policy or checker generation.
- Fixed scope artifacts so `docs/template_submission_artifact_policy.md` is allowed in the parent chunk map, active chunk contract, and trust bundle.
- Aligned PLAN, DECISIONS, chunk contract, docs, and trust bundle so draft derivation may run after `passed_with_warnings`, while policy approval and guide activation require acknowledgement by `admin` or `project_manager`.
- Rewrote external review response/status/trust wording so older CodeRabbit/GitHub results are historical and current external review is pending until the branch is pushed again.

## Commands Run

```bash
cd backend && .venv/bin/python -m ruff check app/core/config.py app/interfaces/project_agents.py app/adapters/project_agents app/modules/projects/schemas.py app/modules/projects/service.py tests/test_projects.py
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'source_snapshot_hash_is_server_computed_and_canonical or source_snapshot_can_use_only_project_guide_material or local_fixture_sufficiency_agent_is_async_idempotent_and_keyless or agent_material_includes_representative_task_context or local_fixture_agent_adapter_fails_closed_outside_dev_environments or project_agent_timeout_is_loaded_from_environment or openai_runtime_misconfiguration_is_sanitized_and_agent_route_only or openai_agent_sdk_adapter_wraps_sdk_failures or openai_agent_sdk_adapter_wraps_sdk_timeouts or openai_agent_sdk_adapter_wraps_sdk_cancellation or openai_agent_sdk_adapter_propagates_caller_cancellation or sufficiency_agent_blocks_thin_guides' -q
cd backend && .venv/bin/python -m ruff check app/modules/projects/service.py tests/test_projects.py
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py -k 'derivation_agent_allows_warning_report_without_acknowledgement_and_is_idempotent or agent_derived_warning_policy_requires_acknowledgement_before_approval or manual_submission_artifact_policy_rejects_agent_provenance_fields or agent_derived_submission_artifact_policy_body_is_immutable or derivation_agent_idempotency_uses_server_owned_policy_version or activation_revalidates_agent_derived_policy_provenance or submission_artifact_policy_approval_persists_effective_policy_hash or submission_artifact_policy_approval_rejects_body_hash_mismatch or approved_submission_artifact_policy_cannot_be_updated or database_enforces_effective_policy_submission_policy_hash or database_enforces_pre_submit_checker_effective_policy_hash or submission_artifact_policy_approval_merges_packaging_rules or approved_submission_artifact_policy_is_immutable or draft_submission_artifact_policy_can_be_updated or approving_replacement_policy_supersedes_prior_rows or approving_replacement_policy_with_same_effective_content_succeeds or replacement_policy_requires_complete_prior_effective_context or concurrent_policy_approvals_do_not_fork_current_chain' -q
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py tests/test_checkers.py -q
cd backend && .venv/bin/python -m ruff check app tests scripts && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'project_agent_timeout_is_loaded_from_environment or openai_agent_sdk_adapter_rejects_oversized_prompt_before_sdk_import or openai_agent_sdk_adapter_wraps_sdk_failures or openai_agent_sdk_adapter_wraps_sdk_timeouts or openai_agent_sdk_adapter_wraps_sdk_cancellation or openai_agent_sdk_adapter_propagates_caller_cancellation' -q
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py -k 'source_snapshot_integrity_accepts_v1_manifest_without_content_excerpt or agent_material_includes_representative_task_context or project_agent_timeout_is_loaded_from_environment or openai_agent_sdk_adapter_rejects_oversized_prompt_before_sdk_import' -q
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py tests/test_checkers.py -q
```

## Results

```text
Focused runtime/source tests passed: 12 passed, 172 deselected in 41.99s.
Regression cluster after source_material_refs repair passed: 18 passed, 166 deselected in 119.94s.
Affected project/checker suite passed after helper repair: 221 passed in 1204.17s.
OpenAI Agents SDK adapter/config prompt-budget tests passed: 6 passed, 179 deselected in 10.82s.
Optional v1 manifest/content_excerpt focused tests passed: 4 passed, 182 deselected in 32.90s.
Final affected project/checker suite passed: 223 passed in 1435.00s.
Full ruff passed.
Docstring coverage passed: 100.0% (504/504).
Markdown link check passed for 25 changed Markdown files.
Stale wording check passed.
git diff --check passed.
```

## Remaining Risks

- Chunk 3 must make tasks lock the guide source snapshot, effective project submission artifact policy hash, and project pre-submit checker bundle hash before `READY`.
- Chunk 3 must migrate submission creation runtime away from transitional task `required_files` and `required_evidence` authority.
- The optional OpenAI Agents SDK extra is adapter-isolated and fake-SDK tested; CI does not currently install `.[agents]`.
- Local fixture adapter output repeats a few default literals, but those outputs remain untrusted and are revalidated through schema, merge rules, provenance checks, and compiler checks before approval.
