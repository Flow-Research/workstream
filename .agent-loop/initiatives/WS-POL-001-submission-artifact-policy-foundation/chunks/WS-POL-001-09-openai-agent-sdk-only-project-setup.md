# Chunk Contract: WS-POL-001-09 - OpenAI Agents SDK Only Project Setup Runtime

## Initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Remove the production `local_fixture` project setup runtime and the runtime
selector that made fixture-derived policies look like real agent SDK output.
Project guide sufficiency and submission artifact policy derivation now run
through the OpenAI Agents SDK runtime. Tests may use explicit test-local fakes,
but production code must not expose a no-network fixture adapter.

## Why This Chunk Exists

The Terminal Benchmark live API drill proved the lifecycle plumbing, but it also
showed that a fixture runtime can confuse the real product question: whether the
agent SDK can derive a project-specific `SubmissionArtifactPolicy` from the full
project guide. Workstream should fail closed when the real agent runtime is not
configured instead of silently producing generic fixture policy.

## Risk Class

L1

## Allowed Files

```text
backend/app/core/config.py
backend/app/adapters/project_agents/**
backend/tests/test_projects.py
backend/tests/test_config.py
README.md
examples/terminal_benchmark/**
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-09-openai-agent-sdk-only-project-setup.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-*
```

## Not Allowed

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/app/modules/projects/** except project-agent adapter imports if needed
backend/alembic/**
.github/workflows/**
demos/** except README command wording if directly impacted
frontend/**
payment/reputation/blockchain code
object-storage implementation
new agent runtime provider implementation
production secrets or committed .env files
```

## Acceptance Criteria

- Production project setup has no `local_fixture` runtime adapter.
- `WORKSTREAM_PROJECT_AGENT_RUNTIME_ADAPTER` is removed from active code and
  current operator docs.
- The project-agent runtime factory builds the OpenAI Agents SDK runtime and
  fails closed when the required model setting is missing.
- Tests use explicit test-local fakes for deterministic project-agent behavior;
  no production fixture adapter is imported by test setup routes.
- Terminal Benchmark example docs and script no longer refer to the removed
  runtime selector.
- README explains that automatic project setup needs OpenAI Agents SDK model and
  API-key settings.
- Temporary Week 1 demo startup does not enable setup autostart without the
  required OpenAI worker configuration.
- Stale wording scan, Markdown link check, ruff, focused project-agent tests,
  docstring coverage, and diff whitespace checks pass.

## Verification Commands

```bash
cd backend && .venv/bin/python -m ruff check app/core/config.py app/adapters/project_agents tests/test_projects.py tests/test_config.py
cd backend && .venv/bin/python -m pytest tests/test_config.py tests/test_projects.py -k 'create_guide_autostart_runs_celery_pipeline_to_draft_policy or create_guide_autostart_stops_before_derivation_when_sufficiency_blocks or project_agent_factory_requires_openai_agent_sdk_model or sufficiency_agent_route_is_async_idempotent_and_secret_safe or openai_runtime_misconfiguration_is_sanitized_and_agent_route_only or derivation_agent_allows_warning_report_without_acknowledgement_and_is_idempotent or agent_derived_warning_policy_requires_acknowledgement_before_approval' -q
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'agent or autostart or source_snapshot_integrity or openai or project_setup_pipeline' -q
cd backend && .venv/bin/docstr-coverage app/adapters/project_agents app/core/config.py --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required Internal Reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- docs
- reuse/dedup
- test delta

## Human Review Focus

- The removed fixture path cannot be used as a production project setup runtime.
- Test fakes are visibly test-local and cannot be mistaken for agent SDK output.
- Operator docs do not mention a removed runtime selector or imply fallback
  behavior.
- Workstream still keeps the project-agent port so future runtimes can be added
  deliberately in a separate chunk.
