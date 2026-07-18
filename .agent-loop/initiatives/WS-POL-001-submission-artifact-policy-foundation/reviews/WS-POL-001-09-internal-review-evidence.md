# Internal Review Evidence: WS-POL-001-09

## Chunk

WS-POL-001-09

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 49101d4ad3fc22ec6e6065b1e593ef04145db953

Reviewed at: 2026-07-09T06:13:59Z

Reviewer run IDs: senior-engineering-final-reviewer-run-id, qa-test-final-reviewer-run-id, security-auth-final-reviewer-run-id, product-ops-final-reviewer-run-id, architecture-final-reviewer-run-id, docs-final-reviewer-run-id, reuse-dedup-final-reviewer-run-id, test-delta-final-reviewer-run-id, ci-integrity-final-reviewer-run-id

Current privacy-scrub chunk: `WS-POL-001-16-terminal-benchmark-live-api-drill`.
This file was touched only to clarify a redacted fixture-path note. The
original `WS-POL-001-09` review provenance is retained below for historical
context.

Original reviewed revision:

Reviewed code SHA: daf31dfc0925482fd1dfdf057133d2e657c8868d

Reviewed at: 2026-07-06T05:18:52Z

Reviewer run IDs: senior-engineering-review-reviewer-run-id, qa-test-review-reviewer-run-id, security-auth-review-reviewer-run-id, product-ops-review-reviewer-run-id, architecture-review-reviewer-run-id, docs-review-reviewer-run-id, reuse-dedup-review-reviewer-run-id, test-delta-review-reviewer-run-id, post-coderabbit-senior-engineering-review-reviewer-run-id, post-coderabbit-reuse-dedup-review-reviewer-run-id, post-coderabbit-test-delta-review-reviewer-run-id

## Reviewed Change

Branch: `codex/ws-pol-001-09-openai-agent-sdk-only`

Scope:

- Removes the production `local_fixture` project setup runtime.
- Removes `WORKSTREAM_PROJECT_AGENT_RUNTIME_ADAPTER` from active settings.
- Keeps the project-agent port but makes the factory build only the OpenAI
  Agents SDK runtime for current production code.
- Moves deterministic project-agent behavior into an explicit test-local fake.
- Updates README and Terminal Benchmark example wording so no current operator
  docs imply a deterministic runtime fallback.
- Records `WS-POL-001-09` as the active bounded corrective chunk without
  rewriting prior chunk-contract history.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Verified maintainability, single-path runtime factory, fail-closed model config, append-only chunk-map update, and the post-CodeRabbit test fixture extraction. |
| QA/test | PASS | None | Confirmed removed production adapter, old selector ignored/failing closed, explicit test-local fakes, README/demo safety, and focused verification. |
| security/auth | PASS | None | Confirmed no production fixture fallback, old selector ignored by settings, model config fails closed, no secret exposure, and safe local example placeholders. |
| product/ops | PASS | None | Confirmed operator docs require OpenAI SDK model/API-key settings, Week 1 demo autostart is disabled, and product/runtime separation remains clear. |
| architecture | PASS WITH LOW RISKS | None | Confirmed project-agent port stays clean, no hidden fixture runtime remains, and historical chunk history is preserved. Low local `__pycache__` residue is ignored and untracked. |
| docs | PASS | None | Confirmed README and Terminal Benchmark docs no longer expose the removed runtime selector, fallback wording, or stale fixture placeholder. |
| reuse/dedup | PASS | None | No production abstraction missed; post-CodeRabbit fixture extraction removed the repeated deterministic runtime monkeypatch boilerplate. |
| test delta | PASS | None | Confirmed selector regressions run in `test`, missing model asserts the exact OpenAI model error, valid model returns OpenAI runtime, post-CodeRabbit fixture extraction preserves coverage, and no tests were skipped or weakened. |

## Valid Findings Addressed

- Initial reviewers found that the active chunk contract was missing while the
  diff changed runtime code, tests, README, examples, and loop state. Added
  `WS-POL-001-09` chunk contract, active status, and chunk-map entry.
- Reviewers found stale Terminal Benchmark wording that blurred real source
  material with the removed runtime fixture. Updated operator-facing examples
  to use `source-material` wording and removed fallback language.
- Reviewers found retrospective edits to historical `WS-POL-001-02` and
  `WS-POL-001-06` contracts, plus the historical `WS-POL-001-06` entry in
  `CHUNK_MAP.md`. Reverted those historical changes and kept the correction in
  `WS-POL-001-09`.
- Test-delta found the first selector regression would have passed under the
  old production deny path. Strengthened selector tests to run in `test`, assert
  the exact OpenAI model configuration error, and prove valid model settings
  still build `OpenAIAgentSdkProjectGuideRuntime`.
- Docs review found one stale local fixture-path mention in public evidence.
  Updated it to the explicit redaction marker `<redacted-local-fixture-path>`.
- CodeRabbit found repeated deterministic runtime monkeypatch boilerplate in
  project-agent tests. Extracted `deterministic_project_agent_runtime` as a
  test-local fixture, kept custom failing/spoofing/capturing runtime patches
  local to their tests, and reran post-CodeRabbit senior engineering,
  reuse/dedup, and test-delta reviewers.

## Commands Run

```bash
cd backend && .venv/bin/python -m ruff check app/core/config.py app/adapters/project_agents tests/test_projects.py tests/test_config.py
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'project_agent_factory_requires_openai_agent_sdk_model or project_agent_factory_ignores_removed_runtime_selector' -q
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'project_agent_factory_requires_openai_agent_sdk_model or project_agent_factory_ignores_removed_runtime_selector or openai_runtime_misconfiguration_is_sanitized_and_agent_route_only' -q
cd backend && .venv/bin/python -m pytest tests/test_config.py tests/test_projects.py -k 'create_guide_autostart_runs_celery_pipeline_to_draft_policy or create_guide_autostart_stops_before_derivation_when_sufficiency_blocks or project_agent_factory_requires_openai_agent_sdk_model or project_agent_factory_ignores_removed_runtime_selector or sufficiency_agent_route_is_async_idempotent_and_secret_safe or openai_runtime_misconfiguration_is_sanitized_and_agent_route_only or derivation_agent_allows_warning_report_without_acknowledgement_and_is_idempotent or agent_derived_warning_policy_requires_acknowledgement_before_approval' -q
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'agent or autostart or source_snapshot_integrity or openai or project_setup_pipeline' -q
cd backend && .venv/bin/python -m pytest tests/test_config.py tests/test_projects.py -q
cd backend && .venv/bin/python -m pytest tests/test_config.py tests/test_projects.py -k 'create_guide_autostart_runs_celery_pipeline_to_draft_policy or create_guide_autostart_stops_before_derivation_when_sufficiency_blocks or project_agent_factory_requires_openai_agent_sdk_model or project_agent_factory_ignores_removed_runtime_selector or sufficiency_agent_route_is_async_idempotent_and_secret_safe or source_snapshot_integrity_accepts_v1_manifest_without_content_excerpt or sufficiency_agent_blocks_thin_guides or derivation_agent_allows_warning_report_without_acknowledgement_and_is_idempotent or agent_derived_warning_policy_requires_acknowledgement_before_approval or derivation_agent_validates_existing_policy_integrity_before_reuse or agent_derived_submission_artifact_policy_body_is_immutable' -q
cd backend && .venv/bin/docstr-coverage app/adapters/project_agents app/core/config.py --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Results:

- ruff: passed.
- Selector regression tests: 2 passed, 195 deselected.
- Selector/runtime route focused tests: 3 passed, 194 deselected.
- Expanded focused project-agent slice: 8 passed, 191 deselected.
- Broader project-agent/autostart slice: 31 passed, 165 deselected.
- Full `tests/test_config.py` and `tests/test_projects.py`: 198 passed.
- Post-CodeRabbit deterministic runtime fixture slice: 11 passed, 188 deselected.
- Docstring coverage: 100.0%.
- Stale wording scan: passed.
- Markdown link check: passed for 7 changed Markdown files.
- Diff whitespace check: passed.

## Remaining Risks

- External CodeRabbit review produced one nitpick and was handled in
  `WS-POL-001-09-external-review-response.md`. GitHub Actions passed before the
  post-CodeRabbit fix and must rerun after the follow-up evidence push.
- Test-local fake injection is repeated in several tests. It is acceptable for
  this chunk only where tests use custom failing/spoofing/capturing runtimes.
