# WS-POL-003-02 PR Trust Bundle

## Goal and design

Add one hidden `compile_project_guide` runtime method that sends the merged
strict context through exactly one provider call and validates the complete
untrusted result before returning. The existing adapter/helper is reused; no
second runtime, registry, compiler, or production path is introduced.

The unified call uses provider-level strict JSON schema, no tools/handoffs/MCP
or search capability, a tracing-disabled sensitive-data-excluding per-run
configuration, a 16 MiB complete-envelope cap, deterministic canonical prompt
serialization without double-encoding guide JSON, timeout/cancellation, and
sanitized failures.

## Scope

Changed runtime files are limited to the project-agent protocol, OpenAI adapter,
and focused fake-runtime tests. Initiative status, contract, and review evidence
are updated with them. No database, migration, AUTH, Celery, API, service
orchestration, policy persistence/approval, catalogue, checker runtime,
dependency, composition root, production caller, or live-cutover change exists.

## Acceptance proof

- Exactly one `Runner.run` call and one strict `ProjectGuideCompilationResult`
  schema wrapper are asserted.
- Canonical prompt input remains untrusted and is separated from instructions.
- No tool/network/file/handoff/MCP/search configuration is supplied.
- Provider tracing and sensitive trace data are explicitly disabled.
- Trusted semantic validation rejects shaped but invalid results before return.
- A valid near-bound quote-heavy guide that previously expanded above 16 MiB
  now serializes once below the bound; oversized envelopes deny before SDK I/O.
- Timeout is sanitized and caller cancellation propagates.
- Legacy runtime behavior and production call sites remain unchanged.

## Evidence and reviews

- Ruff passed.
- 79 focused/adjacent tests passed.
- Changed adapter coverage: 91.89 percent.
- Docstring coverage: 80.5 percent.
- Architecture, security, QA, product/operations, senior engineering, test
  delta, and CI integrity reviews passed after fixes.
- Stale wording, Markdown links, scope, lane ownership, and diff checks passed.

## Remaining risk and human focus

This method is deliberately hidden and unused. Later persistence/orchestration
chunks must preserve one logical attempt and must not enable provider tracing,
tools, or a second inference path. Human review should focus on canonical prompt
fidelity, the no-trace/no-tools boundary, result validation, cancellation/error
semantics, and absence of production rewiring.
