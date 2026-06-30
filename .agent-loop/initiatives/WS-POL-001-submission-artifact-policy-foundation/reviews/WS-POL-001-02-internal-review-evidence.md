# Internal Review Evidence: WS-POL-001-02

## Chunk

WS-POL-001-02

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: c2f79b835a1bb033ffffca79ec507b77efcaae3b

Reviewed at: 2026-06-30T10:43:35Z

Reviewer run IDs: 019f17ec-4836-7362-807c-8750cc247214, 019f17ec-500a-7d11-b25c-ba55d02f10b5, 019f17ec-578f-7650-a8d7-65cc3f387ac0, 019f17ec-5efb-7e70-93f1-2c9f15db0a15, 019f17ec-6962-7180-970b-c1a2d77692a1, 019f17ec-72f4-70b3-bdf9-3225f850e628, 019f1805-72b0-7192-80e0-fe5dc23fa79e, 019f1805-783d-72b1-a19e-d52f72ed4e95, 019f1805-8190-7343-b6c6-3f72f5934516, 019f1805-8b01-7653-ac72-cc1ad1c143b1, 019f1805-9550-7a71-8d34-280d5ab3a4fb, 019f1805-9e48-7991-bc1e-d5d63fbe56c5, 019f181c-c6d7-7440-8aba-0274ef59547b, 019f181c-cb5a-7561-96b1-0e0cb2216456, 019f1821-c3db-7e91-92e9-53138d1583d8, 019f1821-c895-7412-8278-ce4bdc81b3d0, 019f1821-d01c-7450-8246-145d7599ec69

After reviewed SHA `c2f79b835a1bb033ffffca79ec507b77efcaae3b`, only review evidence, initiative status, loop state, and PR trust-bundle files may change before PR publication.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Confirmed lazy runtime resolution, adapter isolation, no DB lock across agent calls, compiler project scope, and sanitized OpenAI adapter failures. |
| qa/test | PASS AFTER FIXES | None | Confirmed runtime boundary, deterministic local path, idempotency, source snapshot binding, warning acknowledgement, compiler semantic coverage, and approval-time compilation. |
| security/auth | PASS WITH LOW RISKS | None | No valid security findings. Confirmed keyless deterministic runtime, SDK isolation, sanitized runtime failures, server-side validation, unsafe source-ref rejection, and fail-closed compiler behavior. |
| product/ops | PASS | None | Confirmed operator workflow and primitive vocabulary now align with ADR/docs, and review decisions remain separate from pre-submit outcomes. |
| architecture | PASS | None | Confirmed expanded docs/README scope is in the chunk contract and map; agent derives policy while compiler owns checker spec/build/validation. |
| ci integrity | PASS | None | Confirmed only bounded optional `agents` extra changed package config; no workflow, script, coverage, or gate weakening. |
| docs | PASS | None | Confirmed ADR, checker framework, chunk map, plan, decisions, intent, active contract, and README align with the implemented contract and config. |
| reuse/dedup | PASS | None | Confirmed canonical hash helper and checker registry validation are reused; no missed shared abstraction blocks the chunk. |
| test delta | PASS | None | Confirmed tests strengthen compiler/runtime coverage, no skips/deletions/weakened assertions, and helpers now load compiler-produced policy rows. |

## Valid Findings Addressed

- Removed eager project-agent runtime construction from `ProjectService.__init__`; runtime now resolves only on explicit agent routes and maps configuration failure to a sanitized 503.
- Split agent execution from locked persistence: service preflights without a row lock, rolls back before runtime calls, then reacquires the setup lock and revalidates before persistence.
- Hardened the trusted compiler so primitive rules must be exact, traceable, registered, and semantically complete for the effective project policy.
- Replaced duplicated canonical JSON hashing with `app.core.hashing.canonical_json_hash`.
- Added OpenAI adapter failure wrapping so raw SDK/API errors do not leak through API responses.
- Aligned compiler primitive vocabulary with ADR/checker docs and expanded the chunk contract to include the necessary ADR/checker docs and README config updates.
- Corrected docs so `SubmissionArtifactPolicyDerivationAgent` derives artifact policy while Workstream's trusted compiler builds and validates the checker specification.
- Replaced old helper mutations in tests/E2E with loading compiler-produced `PreSubmitCheckerPolicy` rows.

## Commands Run

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
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
```

## Results

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
git diff --check passed.
Agent gate result: REVIEW_REQUIRED because this is a large L1 policy/runtime/compiler chunk touching risk-sensitive files and backend package config.
```

## Remaining Risks

- Chunk 3 must make tasks lock the guide source snapshot, effective project submission artifact policy hash, and project pre-submit checker bundle hash before `READY`.
- Chunk 3 must migrate submission creation runtime away from transitional task `required_files` / `required_evidence` authority.
- The OpenAI Agents SDK adapter is optional and isolated; production model choice and credentials remain environment-managed.
- The primitive-to-checker projection is validated against the registry, but future work may move checker-name constants into shared registry metadata if drift risk grows.
