# Chunk Contract: WS-POL-003-02 - Unified Agent Adapter

Status: Implementation and internal review complete; awaiting external review
and human merge. Risk: L1.

## Goal

Implement one bounded `compile_project_guide` adapter call with untrusted-data
instructions, strict structured output, cancellation, timeout, and sanitized
failures. Do not rewire production Celery orchestration.

## Allowed files

- `backend/app/interfaces/project_agents.py`
- `backend/app/adapters/project_agents/openai_agent_sdk.py`
- `backend/tests/test_agent_runtime.py`
- `.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/CHUNK_MAP.md`
- `.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/STATUS.md`
- `.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/chunks/WS-POL-003-02-unified-agent-adapter.md`
- `.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/reviews/WS-POL-003-02-internal-review-evidence.md`
- `.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/reviews/WS-POL-003-02-pr-trust-bundle.md`

## Not allowed

Database models or migrations; authorization; Celery or production service
orchestration; policy approval/persistence; registry or checker runtime;
composition-root/runtime selection; dependencies; provider trace persistence;
tools, network/file capabilities, or live cutover. The three transitional
runtime methods and their callers remain unchanged until their cutover chunk.

## Acceptance

- One method consumes the canonical context and returns the strict result.
- The unified method uses provider-level `strict_json_schema=True`; the helper
  may remain non-strict only for the transitional legacy policy method.
- Guide/task contents remain untrusted data and cannot alter instructions.
- Prompt/input limits, timeout, cancellation, and sanitized error behavior are
  preserved.
- The complete unified prompt is capped at 16 MiB. Trusted serialization parses
  the already-canonical guide payload into the prompt envelope instead of
  double-encoding it as a JSON string, leaving bounded room above the 12 MiB
  verified ART material limit for canonical catalogue/context overhead;
  oversized envelopes fail before provider I/O.
- Agent cannot emit code, commands, URLs, capabilities outside the projection,
  or approval decisions.
- The adapter applies the merged trusted result validator before returning.
- Existing runtime methods and production callers remain behaviorally unchanged.
- Fake-SDK proof records exactly one `Runner.run` call, strict output wrapping
  for `ProjectGuideCompilationResult`, and absence of tools, handoffs, MCP,
  file-search, web-search, or equivalent capability configuration.
- The unified call supplies a per-run SDK configuration with tracing disabled
  and sensitive trace capture excluded; provider tracing is not a persistence
  path for guide context or results.
- Tests prove context-bound trusted validation happens before return and rejects
  semantically invalid provider output.

## Verification and review

Commands:

```bash
cd backend
uv run ruff check app/interfaces/project_agents.py app/adapters/project_agents/openai_agent_sdk.py tests/test_agent_runtime.py
uv run pytest -q tests/test_agent_runtime.py tests/test_project_guide_compilation_contracts.py
uv run docstr-coverage --config .docstr.yaml
git diff --name-only origin/main
git diff --check
```

Hosted GitHub Backend lanes own the full Postgres-backed suite and repository
coverage proof; no local full suite is required.

Required reviewers: security, architecture, QA, product/operations, test delta,
CI integrity, and senior engineering.

Human review focus: confirm one provider call with strict structured output,
no tool/network surface, untrusted material isolation, context-bound trusted
validation, cancellation propagation, sanitized failures, and no production
orchestration/caller rewiring.
