# Chunk Contract: WS-QUAL-001-01B1B-R10 TypeVar Child Order

Parent: `WS-QUAL-001` Backend Coverage Floor

## Goal

Close R9's single final-review defect: Python 3.13 exposes TypeVar bound and
default scopes as identically typed/named public children, so they must be
consumed in AST field order through one shared ordinal.

Risk: L1. SLA: fast. The user's instruction to keep AUTH and coverage moving is
the start signal after internal contract review passes.

## Scope And Limit

Allowed: `backend/scripts/coverage_policy.py`,
`backend/tests/test_coverage_contract.py`, and WS-QUAL/global loop memory.
All config, dependency, workflow, application, AUTH, B2, coverage-raising, and
Python-floor changes are forbidden.

Base is merged-main `060b780190435bc79464ae92fd9235a652f70e00`.
Complete policy/test raw added-plus-deleted delta must remain `<=620`; R9 is
553. Tests remain readable, preserved, and one new case per line. R10 allows
one repair cycle; any unrelated finding stops it.

## Acceptance Criteria

- When public `type variable` children exist, select only that public family and
  consume bound then default through one shared ordinal for the parameter/name/
  line, matching AST field order.
- When public children do not exist, retain the distinct Python 3.12 legacy
  `TypeVar bound`/`TypeVar default` families.
- Mixed bound/default nested lambda/genexpr shapes pair correctly for generic
  functions, classes, and type aliases; owned weakening syntax remains detected.
- Python 3.13 fixtures test clean and owned mixed bound/default forms. The same
  source is invalid-syntax fail-closed on Python 3.11/3.12.
- On Python 3.13 every mixed-shape fixture must first call `analyze_python`
  successfully, so fail-closed `SyntaxError` cannot satisfy a positive. Cover
  bound-lambda/default-genexpr and bound-genexpr/default-lambda orders across
  generic functions, classes, and type aliases. Clean forms remain clean;
  framework-owned skip forms set `weak=True`; framework-owned `pytest.raises`
  forms produce a concrete assertion range and block deletion.
- Preserve all 165 R9 cases/assertions and every syntax-policy behavior. Do not
  add execution/value/provenance logic or change comprehension selection.

## Verification And Review

Run the complete R9 gates with self-validation/raw cap changed to 620, and run
the identical focused matrix in isolated `backend[dev]` environments on Python
3.11, 3.12, and 3.13 with explicit interpreter assertions.

Required reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, test delta, and circuit breaker.
Human focus: shared public ordinal, legacy separation, mixed-shape proof,
unchanged policy behavior, cross-version evidence, and bounded scope.

## Stop Conditions

Stop above 620 lines, after one failed repair, if any supported-version proof
cannot run, or if config/dependency/workflow changes are required. Do not start
B2, chunk 02, AUTH-04, or any later coverage chunk automatically.
