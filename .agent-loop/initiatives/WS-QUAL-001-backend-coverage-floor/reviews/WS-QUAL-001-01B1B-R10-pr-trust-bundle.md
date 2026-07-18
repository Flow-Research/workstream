# WS-QUAL-001-01B1B-R10 PR Trust Bundle

## Intent

Finish the semantic test-integrity gate without embedding a Python execution
model. The final policy is conservative syntax ownership: known pytest/unittest
weakening constructs are rejected and assertion deletion is protected.

## Design

- Exact absolute framework imports and finite simple aliases establish monotone
  lexical ownership.
- Runtime reachability, values, containers, consumers, and provenance do not.
- Stdlib symtable supplies lexical scopes across Python 3.11-3.13.
- Capability-based child selection supports Python 3.11 comprehension tables,
  Python 3.12+ inlining, and Python 3.13 public TypeVar child ordering.

## Scope

- `backend/scripts/coverage_policy.py`
- `backend/tests/test_coverage_contract.py`
- WS-QUAL/global loop memory, contracts, decisions, and review evidence

The 23-file external-repair branch diff contains 1,967 additions and 39 deletions.
Only 584 raw lines belong to the policy/test implementation; the remainder is
the retained R1-R10 planning, stop, and review history. No CI workflow is enabled
here; B2 owns mandatory GitHub enforcement after this PR merges.

## Verification

The identical 172-test matrix passes on Python 3.11, 3.12, and 3.13.
Ruff, dependency integrity, self-validation, exact scope, ancestry, wording,
memory, links, and diff hygiene pass. The original implementation passed all
nine reviewer tracks and the circuit breaker at `15d0b80`. The external-repair
code is `4bcf910`; all nine required reviewer tracks and the circuit breaker
pass at final reviewed head `7e192b8`.

## Risk And Human Focus

- The policy is intentionally conservative once syntax is framework-owned.
- Deleted test lines fail closed when base-source retrieval fails.
- Local parameters/declarations, relative imports, unknown framework members,
  unrelated attributes, and non-TestCase `self.skipTest` remain clean.
- Human review should confirm the syntax-only boundary, cross-version symtable
  selection, readable behavior matrix, and absence of CI/config/application
  drift.

## Follow-Up Gate

Stop after human review and merge. B2 remains inactive until this PR and its
post-merge memory are merged and the user explicitly starts B2. Coverage stays
at the measured 79.25 percent until B2 and coverage-raising chunks 02-06 run.
