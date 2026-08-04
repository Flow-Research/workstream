# Chunk Contract: WS-POL-003-02 - Unified Agent Adapter

Status: Proposed after 01. Risk: L1.

## Goal

Implement one bounded `compile_project_guide` adapter call with untrusted-data
instructions, strict structured output, cancellation, timeout, and sanitized
failures. Do not rewire production workers.

## Allowed files

`backend/app/adapters/project_agents/**`, project-agent interfaces/configuration,
fake adapter tests, and WS-POL-003 docs.

## Not allowed

Database, authorization, worker, policy approval, registry, or checker runtime
changes; no provider trace persistence or tool/network capability.

## Acceptance

- One method consumes the canonical context and returns the strict result.
- Guide/task contents remain untrusted data and cannot alter instructions.
- Prompt/input limits, timeout, cancellation, and sanitized error behavior are
  preserved.
- Agent cannot emit code, commands, URLs, capabilities outside the projection,
  or approval decisions.

## Verification and review

Fake-runtime, injection, timeout/cancellation, and serialization tests. Required
reviewers: security, architecture, QA, product, test delta, CI integrity.
