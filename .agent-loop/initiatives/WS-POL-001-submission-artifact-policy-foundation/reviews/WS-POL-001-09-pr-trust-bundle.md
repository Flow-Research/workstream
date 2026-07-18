# PR Trust Bundle: WS-POL-001-09

## Chunk

`WS-POL-001-09` - OpenAI Agents SDK Only Project Setup Runtime

## Goal

Remove the production deterministic project-agent fixture runtime so project
guide sufficiency and submission artifact policy derivation run only through
the OpenAI Agents SDK runtime in current production code.

## Human-Approved Intent

The user explicitly rejected the local fixture runtime because it made the
Terminal Benchmark proof look like real agent SDK derivation. The current
product question is whether the OpenAI Agents SDK can derive the project
submission policy from the full guide/source material. Workstream must fail
closed when the model-backed runtime is not configured.

Chunk contract:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-09-openai-agent-sdk-only-project-setup.md`

## What Changed

- Deleted `backend/app/adapters/project_agents/local_fixture.py`.
- Removed `project_agent_runtime_adapter` from active settings.
- Simplified the project-agent factory to build `OpenAIAgentSdkProjectGuideRuntime`.
- Added explicit test-local fake runtime in `backend/tests/test_projects.py`.
- Strengthened selector regression tests so the old
  `WORKSTREAM_PROJECT_AGENT_RUNTIME_ADAPTER=local_fixture` environment variable
  is ignored in `test` and cannot restore fixture behavior.
- Updated README and Terminal Benchmark examples to require OpenAI Agents SDK
  model/API-key settings and to avoid fallback/runtime-fixture wording.
- Added active WS-POL-001-09 loop state, status, chunk-map entry, and chunk
  contract without rewriting prior chunk history.

## Why It Changed

The fixture runtime was useful while plumbing the lifecycle, but it is now
harmful because it can hide whether model-backed setup actually works. A project
guide should trigger Workstream's real project-agent runtime. Tests can still
use explicit fakes, but production code should not expose a deterministic
fixture adapter.

## Design Chosen

- Keep the `ProjectGuideAgentRuntime` port/interface.
- Use OpenAI Agents SDK as the only active runtime implementation.
- Fail closed if `WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL` is missing.
- Treat the old runtime selector as ignored legacy environment noise.
- Keep deterministic behavior test-local and visibly named as a test fake.

## Alternatives Rejected

- Keep `local_fixture` as dev/test production adapter: rejected because it
  confuses real project setup proof.
- Keep a runtime selector with one live option: rejected because it implies
  another supported production path.
- Move deterministic fake into shared production code: rejected because the
  fake exists only for tests.

## Scope Control

No task lifecycle, checker runtime, post-submit policy, review/revision,
payment, reputation, blockchain, frontend, object storage, or workflow changes
were added.

Historical chunk contracts remain unchanged. The superseding decision is
recorded only in WS-POL-001-09 artifacts and active status/map files.

## Product Behavior

Automatic project setup now requires OpenAI Agents SDK configuration. If the
model is missing, setup routes fail closed through the existing sanitized agent
runtime error path. The Week 1 demo keeps project setup autostart disabled so it
does not imply a configured agent worker.

## Acceptance Criteria Proof

- No production `local_fixture` source remains.
- `WORKSTREAM_PROJECT_AGENT_RUNTIME_ADAPTER` is no longer a `Settings` field.
- Factory builds only `OpenAIAgentSdkProjectGuideRuntime`.
- Selector regression tests prove the old selector does not re-enable fixture
  behavior.
- Tests use `DeterministicTestProjectGuideAgentRuntime` only inside
  `backend/tests/test_projects.py`.
- README and examples no longer document a runtime selector or deterministic
  fallback.
- Week 1 demo startup sets `WORKSTREAM_PROJECT_SETUP_PIPELINE_AUTOSTART=false`.

## Tests/Checks Run

```bash
cd backend && .venv/bin/python -m ruff check app/core/config.py app/adapters/project_agents tests/test_projects.py tests/test_config.py
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'project_agent_factory_requires_openai_agent_sdk_model or project_agent_factory_ignores_removed_runtime_selector' -q
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'project_agent_factory_requires_openai_agent_sdk_model or project_agent_factory_ignores_removed_runtime_selector or openai_runtime_misconfiguration_is_sanitized_and_agent_route_only' -q
cd backend && .venv/bin/python -m pytest tests/test_config.py tests/test_projects.py -k 'create_guide_autostart_runs_celery_pipeline_to_draft_policy or create_guide_autostart_stops_before_derivation_when_sufficiency_blocks or project_agent_factory_requires_openai_agent_sdk_model or project_agent_factory_ignores_removed_runtime_selector or sufficiency_agent_route_is_async_idempotent_and_secret_safe or openai_runtime_misconfiguration_is_sanitized_and_agent_route_only or derivation_agent_allows_warning_report_without_acknowledgement_and_is_idempotent or agent_derived_warning_policy_requires_acknowledgement_before_approval' -q
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'agent or autostart or source_snapshot_integrity or openai or project_setup_pipeline' -q
cd backend && .venv/bin/python -m pytest tests/test_config.py tests/test_projects.py -q
cd backend && .venv/bin/docstr-coverage app/adapters/project_agents app/core/config.py --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Result summary:

- ruff: passed.
- Selector regressions: 2 passed.
- Selector/runtime route focused tests: 3 passed.
- Expanded focused project-agent slice: 8 passed.
- Broader project-agent/autostart slice: 31 passed.
- Full config/projects suite: 198 passed.
- Docstring coverage: 100.0%.
- Stale wording, Markdown link, and diff whitespace checks: passed.

## Test Delta

Tests added or strengthened:

- `test_project_agent_factory_requires_openai_agent_sdk_model`
- `test_project_agent_factory_ignores_removed_runtime_selector`
- explicit test-local fake runtime for route/autostart tests.

Tests removed or rewritten:

- old production `local_fixture` outside-dev fail-closed test removed because
  the production fixture adapter no longer exists.

## CI Integrity

- No GitHub workflow was changed.
- No lint/test/docstring command was weakened.
- No dependency was added.

## Reviewer Results

Internal review evidence:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-internal-review-evidence.md`

Reviewed code SHA: `daf31dfc0925482fd1dfdf057133d2e657c8868d`

Reviewed at: `2026-07-06T05:18:52Z`

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Runtime factory, scope history, and post-CodeRabbit test fixture extraction reviewed. |
| QA/test | PASS | None | Acceptance criteria and focused checks reviewed. |
| security/auth | PASS | None | Fail-closed config and secret handling reviewed. |
| product/ops | PASS | None | Operator docs and product/runtime separation reviewed. |
| architecture | PASS WITH LOW RISKS | None | Project-agent port and scope integrity reviewed. |
| docs | PASS | None | Runtime selector/fallback wording reviewed. |
| reuse/dedup | PASS | None | No production abstraction issue; repeated deterministic runtime monkeypatches extracted. |
| test delta | PASS | None | Selector regression tests and post-CodeRabbit fixture extraction reviewed. |

## External Review

CodeRabbit found one valid nitpick: repeated deterministic project-agent runtime
monkeypatch boilerplate in `backend/tests/test_projects.py`. It was fixed by
extracting the test-local `deterministic_project_agent_runtime` fixture and
recorded separately in:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-external-review-response.md`

GitHub Actions passed before the post-CodeRabbit fix and must rerun after the
follow-up evidence push.

## Remaining Risks

- External CI and CodeRabbit must rerun after the post-CodeRabbit fix is pushed.
- Custom failing/spoofing/capturing runtime patches remain local to their tests
  because they are intentionally different behaviors.

## Human Review Focus

- Confirm production project setup should now have only the OpenAI Agents SDK
  runtime path.
- Confirm test-local fakes are acceptable and visibly separated from production.
- Confirm historical chunk contracts are preserved while WS-POL-001-09 records
  the superseding decision.

## Human Merge Ownership

Only the user can approve and merge this PR. Codex must not merge it without
explicit user approval for that specific PR.
