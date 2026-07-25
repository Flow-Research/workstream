# Decisions: WS-AUTH-002 — Authorization Docstring Lint Correction

## D1 — Preserve AUTH-11

Use a separate AUTH-owned corrective initiative because AUTH-11 represents a
different security-sensitive product cutover.

## D2 — Documentation-only repair

Resolve the findings with four concise docstrings. Do not change validation,
tests, configuration, or CI.

## D3 — Trusted-main sequencing

Merge the correction before PR #198 integrates `main`; then require new
exact-head checks on PR #198.
