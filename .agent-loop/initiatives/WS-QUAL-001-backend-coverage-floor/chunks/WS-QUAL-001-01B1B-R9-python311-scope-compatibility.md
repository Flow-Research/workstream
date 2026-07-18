# Chunk Contract: WS-QUAL-001-01B1B-R9 Python 3.11 Scope Compatibility

Parent: `WS-QUAL-001` Backend Coverage Floor

## Goal

Close the single R8 final-review defect: syntactic scope pairing must support
both Python 3.11 child comprehension tables and Python 3.12+ inlined
comprehensions. This is a compatibility closure, not another policy redesign.

Risk: L1. SLA: fast. The user's instruction to fix and finish the blocking
coverage gate is the start signal after this contract passes internal review.

## Scope And Limit

Allowed: `backend/scripts/coverage_policy.py`,
`backend/tests/test_coverage_contract.py`, and WS-QUAL/global loop memory.
Everything else is forbidden, including dependencies, Python-floor changes,
workflow/CI changes, B2, chunk 02, AUTH-03, application code, exclusions, and
coverage-raising tests.

Base SHA is merged main `060b780190435bc79464ae92fd9235a652f70e00`.
The complete policy/test delta must remain at or below 600 raw added-plus-deleted
lines; the R8 candidate is 537. Tests remain readable and one new case per line.
R9 has one repair cycle. Any unrelated finding or size failure stops it.

## Acceptance Criteria

- Detect whether a list/set/dict comprehension has a matching stdlib symtable
  child. Enter it on Python 3.11; use the containing table when Python 3.12+
  inlines the comprehension. Do not branch only on a hard-coded version number.
- Generator expressions continue entering their required `genexpr` table.
- Nested lambda/genexpr/function scopes pair under the selected comprehension
  table, including same-line and multiply nested forms.
- Comprehension targets shadow framework names through nested scopes on both
  supported interpreter families; owned names remain detected when unshadowed.
- Python 3.12-only PEP 695 fixtures expect fail-closed invalid syntax on Python
  3.11 and retain their existing semantic expectations on Python 3.12+.
- Preserve every R8 behavior and deterministic gate. No execution, value,
  reachability, consumer, or provenance model may be added.
- Preserve every merged-main and R8 case and assertion. Only PEP 695 expected
  results may be version-conditional: fail-closed invalid syntax on 3.11 versus
  the existing semantic expectation on 3.12+. Do not remove, skip, xfail,
  weaken, compress, or reduce the non-PEP matrix/test count on either version.
  Every new R9 case occupies one physical line.

## Verification And Review

Run the existing 3.12 focused/Ruff/pip/self-validation/documentation/scope/raw
delta gates, plus a Python 3.11 focused run using an isolated uv environment:

```text
uv run --no-project --isolated --python 3.11 --with-editable 'backend[dev]' python -c 'import sys; assert sys.version_info[:2] == (3, 11)'
uv run --no-project --isolated --python 3.11 --with-editable 'backend[dev]' python -m pytest -q backend/tests/test_coverage_contract.py
test -z "$(git diff --name-only 060b780190435bc79464ae92fd9235a652f70e00...HEAD | grep -Ev '^(backend/scripts/coverage_policy.py|backend/tests/test_coverage_contract.py|\.agent-loop/(LOOP_STATE.md|REVIEW_LOG.md|WORK_QUEUE.md|initiatives/WS-QUAL-001-backend-coverage-floor/.*))$')"
test "$(git diff --numstat 060b780190435bc79464ae92fd9235a652f70e00...HEAD -- backend/scripts/coverage_policy.py backend/tests/test_coverage_contract.py | awk '{total += $1 + $2} END {print total + 0}')" -le 600
cd backend && BASE_SHA=060b780190435bc79464ae92fd9235a652f70e00 .venv/bin/python -c 'import os, sys; sys.path.insert(0, "scripts"); import coverage_policy as policy; policy.validate_delta(os.environ["BASE_SHA"], 600, {"backend/scripts/coverage_policy.py", "backend/tests/test_coverage_contract.py"})'
```

Required reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, test delta, and circuit breaker.
Human focus: introspected symtable compatibility, dual-version proof, unchanged
syntax policy, readable tests, and no Python-floor or workflow change.

## Stop Conditions

Stop above 600 lines, after one failed repair, if Python 3.11 proof cannot run,
or if the fix requires config/workflow/dependency changes. Do not start B2,
chunk 02, AUTH-03, or any later chunk automatically.
