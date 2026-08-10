# Workstream PR Trust Bundle

## Chunk

`WS-AUTH-001-12I` - Unified Compilation Authorization Activation

## Goal

Activate only `project.guide_compilation.request` for an exact-project Project
Manager and `project.guide_compilation.execute` for the fixed
`workstream.project.setup` service, while leaving POL's hidden compilation
workflow inactive until WS-POL-003-03B composes it.

## Human-approved intent

Continue AUTH-12 after the ART/AUTH prerequisites, preserve strict module
boundaries, avoid local full-suite execution, and use hosted GitHub Backend
lanes for repository-wide coverage.

## What changed

- Added exact request/execute catalogue, policy, kernel, PREP, audit, and SQL
  parity plus migration `0063_compilation_authority`.
- Added the production AUTH implementation of the public compilation port.
- Added non-evidencing pre-provider authorization and fresh transaction-bound
  final PREP with AUTH-verified result digest.
- Enforced exact-project PM grant selection and fixed-service isolation.
- Extracted bounded AUTH-internal helpers while shrinking recorded structural
  debt and preserving the cross-module import ledger.
- Added focused runtime, actor-matrix, replay, strict-facts, migration, and
  downgrade-refusal proof.

## Why it changed

POL-03B must not call a provider or persist an accepted compilation until AUTH
can prove the exact current human request and fixed-service execution authority.

## Design chosen

The existing opaque PREP protocol remains the sole durable authorization path.
Preflight validates the complete typed attempt context but issues no handle and
stages no evidence. Final persistence uses a new transaction and a single-use
handle whose result digest AUTH recomputes. POL-03B retains atomic product
idempotency custody; AUTH does not add a competing durable replay protocol.

## Alternatives rejected

- A normal PREP consume for preflight: it could commit allowed evidence before
  provider I/O.
- Trusting the caller's final digest: it would not prove exact result facts.
- System-scoped PM fallback: compilation requests require the exact project.
- A second authorization protocol or POL-local evaluator.

## Scope control

No route, worker, provider call, prompt, product row, checker, ART, REV, task,
submission, or guide-activation behavior is added. Only the two 12I actions are
activated. The allowed-file contract was kept explicit.

## Product behavior

A covered PM may authorize dispatch/recovery for one immutable compilation
context. Only `workstream.project.setup` may pass exact preflight and authorize
accepted-result persistence. The workflow remains hidden until POL-03B wires
the port and product transaction.

## Acceptance criteria proof

- Exact PM project grant succeeds; system grant and actor/service substitutions
  deny.
- Preflight binds lineage, catalogues, agent, attempt, and provider key without
  a handle or evidence.
- Final result/component digest mismatch denies before PREP.
- Handles are opaque, transaction-bound, single-use, and replay-denying.
- Revoked services deny without allowed evidence.
- Migration roundtrip succeeds and retained request or execute evidence blocks
  downgrade.

## Tests/checks run

```text
Focused adapter/domain tests: 16 passed
AUTH boundary plus focused non-DB tests: 65 passed (before final test additions)
PostgreSQL 0063 roundtrip and retained-evidence downgrade tests: passed
Changed adapter coverage: 98.36% (90% required)
Ruff: passed
Authorization boundary: passed
Test-structure boundary: passed
Behavior ownership: passed
Stale authorization/Workstream wording: passed
Markdown links: passed
git diff --check: passed
```

Repository-wide tests and the 78% global floor run only in hosted GitHub
Backend lanes on the exact pushed head.

## Test delta

No tests were removed, skipped, weakened, or marked xfail. New focused tests
cover real-kernel positive and negative behavior rather than only mocks.

## CI integrity

No workflow, threshold, lint, typecheck, or failure-masking behavior was
weakened. Focused tests were added to the existing semantic lane and behavior
ownership manifests.

## Reviewer results

Architecture, security, QA, product/operations, senior engineering, CI
integrity, reuse/dedup, test-delta, and documentation reviews pass after their
findings were fixed.

## External review

GitHub Actions and CodeRabbit remain pending until the branch is pushed and the
ready PR exists.

## Remaining risks

- POL-03B must consume these boundaries in the same transaction as its unique
  operation/attempt transition; AUTH activation alone does not make the product
  flow live.
- The AUTH-internal `domain`/`runtime` partition has a non-blocking layering
  smell recorded by architecture review for later boundary recovery.

## Follow-up work

WS-POL-003-03B installs the live composition and provider/product ordering.
AUTH then resumes its approved post-12I sequence.

## Human review focus

- No preflight evidence or handle survives provider I/O.
- Exact-project PM selection when system and project grants coexist.
- Complete preflight and final digest binding.
- Only the two intended actions become active.

## Human merge ownership

- [ ] The user explicitly approves this specific PR for merge.
