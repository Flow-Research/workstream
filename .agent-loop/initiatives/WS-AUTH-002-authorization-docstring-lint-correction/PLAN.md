# Plan: WS-AUTH-002 — Authorization Docstring Lint Correction

## Approach

1. Land this planning-only intake with one reviewed implementation successor.
2. Start `WS-AUTH-002-01` through the signed explicit-event workflow.
3. Add concise public docstrings to only the four reported symbols.
4. Run exact Ruff and docstring checks plus repository evidence gates.
5. Run required internal reviewers and publish one corrective PR.
6. After human-approved merge, allow PR #198 to pull trusted `main` and rerun
   exact-head checks.

## Rejected alternatives

- Do not weaken or exclude Ruff/docstring rules.
- Do not fold the correction into PR #198 because AUTH owns the affected file.
- Do not consume `WS-AUTH-001-11`; that chunk owns a different authorization
  cutover and its completion evidence must remain truthful.
- Do not perform unrelated missing-docstring cleanup.

## Preserved boundaries

The implementation changes documentation only. Pydantic validation,
serialization structure, authorization semantics, database state, migrations,
and CI configuration remain unchanged. Generated JSON Schema/OpenAPI may gain
only description metadata sourced from the Pydantic model docstrings; no
structural contract delta is permitted.

## Proof strategy

Review the exact source diff, run Ruff 0.15.22 and docstring coverage, compile
the module, run deterministic repository gates, and require senior, QA,
security, product, architecture, docs, reuse, CI-integrity, and test-delta
review.
