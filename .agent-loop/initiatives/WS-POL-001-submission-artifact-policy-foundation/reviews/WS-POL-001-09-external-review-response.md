# External Review Response: WS-POL-001-09

## Scope

External review feedback for PR #71: `Remove fixture project agent runtime`.

Internal sub-agent evidence is tracked separately in:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-internal-review-evidence.md`

## CodeRabbit Review

CodeRabbit completed review on 2026-07-06 and reported one nitpick.

| Source | Finding | Severity | Status | Response |
|---|---|---:|---|---|
| CodeRabbit | Repeated deterministic project-agent runtime monkeypatch boilerplate in `backend/tests/test_projects.py`. | Trivial | Fixed | Added the test-local `deterministic_project_agent_runtime` fixture and replaced repeated deterministic monkeypatch blocks. Custom failing/spoofing/capturing runtime patches remain local because they test different behaviors. |

## Verification

```bash
cd backend && .venv/bin/python -m ruff check app/core/config.py app/adapters/project_agents tests/test_projects.py tests/test_config.py
cd backend && .venv/bin/python -m pytest tests/test_config.py tests/test_projects.py -k 'create_guide_autostart_runs_celery_pipeline_to_draft_policy or create_guide_autostart_stops_before_derivation_when_sufficiency_blocks or project_agent_factory_requires_openai_agent_sdk_model or project_agent_factory_ignores_removed_runtime_selector or sufficiency_agent_route_is_async_idempotent_and_secret_safe or source_snapshot_integrity_accepts_v1_manifest_without_content_excerpt or sufficiency_agent_blocks_thin_guides or derivation_agent_allows_warning_report_without_acknowledgement_and_is_idempotent or agent_derived_warning_policy_requires_acknowledgement_before_approval or derivation_agent_validates_existing_policy_integrity_before_reuse or agent_derived_submission_artifact_policy_body_is_immutable' -q
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Results:

- ruff: passed.
- Focused post-CodeRabbit pytest slice: 11 passed, 188 deselected.
- Stale wording scan: passed.
- Markdown link check: passed for 9 changed Markdown files.
- Diff whitespace check: passed.

## Remaining External State

GitHub Actions and CodeRabbit must rerun after this response and fix are pushed.
