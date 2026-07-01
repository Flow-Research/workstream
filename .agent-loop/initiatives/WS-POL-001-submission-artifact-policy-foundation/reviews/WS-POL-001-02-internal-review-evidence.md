# Internal Review Evidence: WS-POL-001-02

## Chunk

WS-POL-001-02

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 66fb9936c0a9f7fa04bbe783483dbdff0cfb5eb3

Reviewed at: 2026-07-01T08:56:11Z

Reviewer run IDs: 019f1cc9-3ace-70a0-b81b-fa5188f47a5d, 019f1cc9-3e04-7962-bc42-38c71e6e5f9d, 019f1cc9-48f1-7ec3-a4e2-09fea5b012a1, 019f1cc9-5954-7413-9dea-10d1c5df721e, 019f1cc9-61a4-77e2-ac55-76be99b17c2f, 019f1cc9-740c-7c31-9ba9-24cbab3019bf, 019f1cdf-f82a-70b1-8a2b-6cfedd686ac0, 019f1cdf-fa31-7f80-86f9-bd9861a20928, 019f1cdf-fd43-7731-b780-876654b43bf6, 019f1ce0-0518-75d2-852c-c23082bc4680, 019f1ce0-2042-7f72-bc12-d44d69949ccd, 019f1ce0-2959-7af0-9140-70922fdd8639, 019f1ce5-15d6-78d0-a6a7-bc343881782f, 019f1ce5-1877-7d81-b440-be48ca20e194

After reviewed SHA `66fb9936c0a9f7fa04bbe783483dbdff0cfb5eb3`, only review evidence, initiative status, loop state, and PR trust-bundle files may change before PR publication.

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

## Valid Findings Addressed

- Made persisted sufficiency-agent and derivation-agent identity server-owned. Runtime/provider-returned `agent_name`, `agent_version`, and policy versions cannot become audit provenance.
- Required an agent-created sufficiency report before running `SubmissionArtifactPolicyDerivationAgent`; manual sufficiency reports support only manual policy creation after clearance.
- Blocked manual `SubmissionArtifactPolicy` creation until sufficiency has passed or warnings are acknowledged.
- Revalidated agent-derived policy provenance before approval and guide activation, so seeded or stale spoofed rows cannot become effective or active.
- Documented the manual sufficiency path: a source snapshot has one sufficiency report; if a manual report already exists, operators continue through manual policy creation or create a fresh guide-source snapshot for the agent path.
- Added `docs/product_first_user_flows.md` to the WS-POL-001-02 chunk contract because the reviewed product-flow clarification directly resolved docs/product-ops findings.
- Earlier in the chunk, replaced eager runtime construction with lazy explicit agent-route resolution; split agent execution from locked persistence; hardened compiler semantic coverage; shared canonical hashing; sanitized OpenAI adapter failures; and aligned docs so the agent derives policy while Workstream's compiler builds deterministic checker bundles.

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
```

## Remaining Risks

- Chunk 3 must make tasks lock the guide source snapshot, effective project submission artifact policy hash, and project pre-submit checker bundle hash before `READY`.
- Chunk 3 must migrate submission creation runtime away from transitional task `required_files` and `required_evidence` authority.
- The optional OpenAI Agents SDK extra is adapter-isolated and fake-SDK tested; CI does not currently install `.[agents]`.
- Deterministic runtime output repeats a small number of default literals, but those outputs remain untrusted and are revalidated through schema, merge rules, provenance checks, and compiler checks before approval.
