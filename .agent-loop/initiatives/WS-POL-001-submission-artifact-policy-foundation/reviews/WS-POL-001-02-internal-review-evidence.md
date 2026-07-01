# Internal Review Evidence: WS-POL-001-02

## Chunk

WS-POL-001-02

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 75adc273aaf9be848233c62629ddaf5fcf424370

Reviewed at: 2026-07-01T11:37:44Z

Reviewer run IDs: 019f1cc9-3ace-70a0-b81b-fa5188f47a5d, 019f1cc9-3e04-7962-bc42-38c71e6e5f9d, 019f1cc9-48f1-7ec3-a4e2-09fea5b012a1, 019f1cc9-5954-7413-9dea-10d1c5df721e, 019f1cc9-61a4-77e2-ac55-76be99b17c2f, 019f1cc9-740c-7c31-9ba9-24cbab3019bf, 019f1cdf-f82a-70b1-8a2b-6cfedd686ac0, 019f1cdf-fa31-7f80-86f9-bd9861a20928, 019f1cdf-fd43-7731-b780-876654b43bf6, 019f1ce0-0518-75d2-852c-c23082bc4680, 019f1ce0-2042-7f72-bc12-d44d69949ccd, 019f1ce0-2959-7af0-9140-70922fdd8639, 019f1ce5-15d6-78d0-a6a7-bc343881782f, 019f1ce5-1877-7d81-b440-be48ca20e194, 019f1cf8-1378-7213-a2cd-58f0aa35e398, 019f1cf8-2eb2-76c1-a904-8f972fb6bd89, 019f1cf8-1e68-76c2-b169-e5fe13104793, 019f1cf8-4360-7943-b90b-ae6c9a635efe, 019f1cf8-56c4-7443-8f49-4dc392ba3f62, 019f1cf8-7936-7500-bcaf-3ba9c7bb6733, 019f1cff-7559-7e02-ba38-356451b8b579, 019f1cff-8065-7b73-ba0e-4fc800b9bfc7, 019f1cff-903f-7431-b04b-3d9675aa9990, 019f1cff-a0a2-7cb2-a9b5-00ba9341b467, 019f1cff-b4bb-7a83-990f-23b99235cb60, 019f1cff-d252-7f82-a037-0caaadf29fc8, 019f1d3a-b6bf-7382-8a83-99b6ac8a1fb5, 019f1d3a-ceae-7be0-afc5-d425f5c2ee51, 019f1d3a-e771-7a60-86d0-4cc92afc77cc, 019f1d62-5ed1-78b3-830f-f5bd045cd00d

After reviewed SHA `89420d15184d6ff00b13a537d81de94e0703f3af`, only review evidence, initiative status, loop state, and PR trust-bundle files may change before PR publication.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Initial low-risk finding on stale/seeded agent-derived policy provenance was fixed by revalidating before approval and activation. Final narrow scope re-review passed after `docs/product_first_user_flows.md` was added to the chunk contract. |
| qa/test | PASS | None | Confirmed Postgres-backed API coverage, idempotency, server-owned provenance, manual report boundary, unsafe source refs, compiler fail-closed coverage, and no out-of-scope runtime rewiring. |
| security/auth | PASS | None | Confirmed provider identity cannot spoof persisted provenance; OpenAI errors, source refs, validation errors, and compiler paths fail closed without secret leakage. |
| product/ops | PASS AFTER FIXES | None | Manual sufficiency/manual policy path and agent-derived setup path are now clear; worker/project-manager semantics remain fair. |
| architecture | PASS | None | Confirmed project-agent port/adapter separation, project-scoped compiler, no task-level checker generation, and no architecture drift. |
| ci integrity | PASS WITH LOW RISKS | None | No workflow weakening. Low residual: CI does not install optional `.[agents]`; adapter remains delayed-import and fake-SDK tested. Agent gate `REVIEW_REQUIRED` is expected for L1 risky-path work. |
| docs | PASS AFTER FIXES | None | Manual sufficiency occupying a source snapshot, operator path, glossary, first user flow, and server-owned provenance wording are now aligned. Final narrow scope re-review passed. |
| reuse/dedup | PASS WITH LOW RISKS | None | Shared hashing and checker registry validation are reused. Low residual: deterministic runtime repeats default literals, but output is untrusted and revalidated before approval. |
| test delta | PASS WITH LOW RISKS | None | Tests were strengthened; no skips, xfails, or removed regression coverage. Low residual: seeded stale-agent tests use broad spoofed identity, but implementation exact checks cover stale-version variants. |

Final external-review fix reviewers:

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Confirmed approval hash guard, validation encoding, route wording, and manual-report reuse test are minimal and in scope. |
| qa/test | PASS | None | Confirmed approval-time hash mismatch, validation error encoding, manual-report reuse, and derivation manual-report rejection coverage. |
| security/auth | PASS | None | Confirmed validation errors redact raw input and encode safely; tampered policy body/hash rows are rejected before approval. |
| product/ops | PASS | None | Confirmed operator fork is clear and remains project setup behavior, not a review decision. |
| docs | PASS | None | Confirmed sufficiency/derivation route wording and evidence wording are correct. |
| test delta | PASS | None | Confirmed new tests strengthen coverage and no skips or weakened assertions were added. |

Final CodeRabbit follow-up reviewers:

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Found that broad `CancelledError` wrapping swallowed caller cancellation; fixed by propagating active task cancellation and wrapping SDK-originated cancellation only. |
| qa/test | PASS | None | Confirmed warning reports can derive without acknowledgement, approval still requires acknowledgement, and reuse-integrity coverage is present. |
| security/auth | PASS | None | Confirmed agent-derived policy reuse validates body/hash integrity and OpenAI adapter failures remain sanitized. |
| test delta | PASS AFTER FIXES | None | Found missing direct coverage for approval of an agent-derived warning policy; fixed with `test_agent_derived_warning_policy_requires_acknowledgement_before_approval`. |

## Valid Findings Addressed

- Made persisted sufficiency-agent and derivation-agent identity server-owned. Runtime/provider-returned `agent_name`, `agent_version`, and policy versions cannot become audit provenance.
- Required an agent-created sufficiency report before running `SubmissionArtifactPolicyDerivationAgent`; manual sufficiency reports support only manual policy creation after clearance.
- Blocked manual `SubmissionArtifactPolicy` creation until sufficiency has passed or warnings are acknowledged.
- Revalidated agent-derived policy provenance before approval and guide activation, so seeded or stale spoofed rows cannot become effective or active.
- Documented the manual sufficiency path: a source snapshot has one sufficiency report; if a manual report already exists, operators continue through manual policy creation or create a fresh guide-source snapshot for the agent path.
- Added `docs/product_first_user_flows.md` to the WS-POL-001-02 chunk contract because the reviewed product-flow clarification directly resolved docs/product-ops findings.
- Earlier in the chunk, replaced eager runtime construction with lazy explicit agent-route resolution; split agent execution from locked persistence; hardened compiler semantic coverage; shared canonical hashing; sanitized OpenAI adapter failures; and aligned docs so the agent derives policy while Workstream's compiler builds deterministic checker bundles.
- Wrapped SDK-originated OpenAI cancellation as `ProjectAgentRuntimeError` without swallowing caller/request/shutdown cancellation.
- Locked `warn_low_quality_generated_artifact` as warning-only with empty config.
- Split policy derivation sufficiency validation from policy approval validation, so warning reports can derive policy while approval still requires authorized warning acknowledgement.
- Revalidated existing agent-derived policy body/hash integrity before reuse.
- Added direct coverage that an agent-derived policy from a warning sufficiency report cannot be approved until warnings are acknowledged.

## Commands Run

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
cd backend && .venv/bin/python -m ruff check app/adapters/project_agents/openai_agents.py app/modules/checkers/compiler.py app/modules/projects/service.py tests/test_checkers.py tests/test_projects.py
python3 -S - <<'PY'
import os
import sys
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
sys.path.insert(0, '/home/abiorh/flow/workstream/backend')
sys.path.extend([
    '/home/abiorh/.local/lib/python3.12/site-packages',
    '/usr/local/lib/python3.12/dist-packages',
    '/usr/lib/python3/dist-packages',
])
import pytest
raise SystemExit(pytest.main([
    '-p', 'pytest_asyncio.plugin',
    'tests/test_projects.py::test_openai_agent_adapter_wraps_sdk_timeouts',
    'tests/test_projects.py::test_openai_agent_adapter_wraps_sdk_cancellation',
    'tests/test_projects.py::test_openai_agent_adapter_propagates_caller_cancellation',
    'tests/test_projects.py::test_agent_route_sanitizes_runtime_exception_chain',
]))
PY
python3 -S - <<'PY'
import os
import sys
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
sys.path.insert(0, '/home/abiorh/flow/workstream/backend')
sys.path.extend([
    '/home/abiorh/.local/lib/python3.12/site-packages',
    '/usr/local/lib/python3.12/dist-packages',
    '/usr/lib/python3/dist-packages',
])
import pytest
raise SystemExit(pytest.main([
    '-p', 'pytest_asyncio.plugin',
    'tests/test_checkers.py',
    'tests/test_projects.py',
]))
PY
python3 -S - <<'PY'
import os
import sys
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
sys.path.insert(0, '/home/abiorh/flow/workstream/backend')
sys.path.extend([
    '/home/abiorh/.local/lib/python3.12/site-packages',
    '/usr/local/lib/python3.12/dist-packages',
    '/usr/lib/python3/dist-packages',
])
import pytest
raise SystemExit(pytest.main([
    '-p', 'pytest_asyncio.plugin',
    'tests/test_projects.py::test_derivation_agent_allows_warning_report_without_acknowledgement_and_is_idempotent',
    'tests/test_projects.py::test_agent_derived_warning_policy_requires_acknowledgement_before_approval',
    'tests/test_projects.py::test_sufficiency_warnings_require_acknowledgement',
]))
PY
cd backend && .venv/bin/python -m ruff check tests/test_projects.py
```

## Results

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
CodeRabbit follow-up touched-file ruff passed.
Adapter timeout/cancellation focused tests passed: 4 passed in 9.96s.
Checker and project affected suites passed after follow-up fixes: 217 passed in 787.86s.
Warning-derived approval focused tests passed: 3 passed in 30.53s.
Final test-file ruff passed.
Final checker and project affected suites passed after added warning-derived approval coverage: 218 passed in 1164.34s.
```

## Remaining Risks

- Chunk 3 must make tasks lock the guide source snapshot, effective project submission artifact policy hash, and project pre-submit checker bundle hash before `READY`.
- Chunk 3 must migrate submission creation runtime away from transitional task `required_files` and `required_evidence` authority.
- The optional OpenAI Agents SDK extra is adapter-isolated and fake-SDK tested; CI does not currently install `.[agents]`.
- Deterministic runtime output repeats a few default literals, but those outputs remain untrusted and are revalidated through schema, merge rules, provenance checks, and compiler checks before approval.
