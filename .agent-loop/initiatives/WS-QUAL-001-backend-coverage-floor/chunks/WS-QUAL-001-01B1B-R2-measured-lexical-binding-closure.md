# Chunk Contract: WS-QUAL-001-01B1B-R2 Measured Lexical Binding Closure

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: blocked at 348/350 during cycle-zero implementation review. Standard
lexical/control-flow proof could not fit the two-line reserve. Superseded by
B1B-R3; retain as review history and do not repair in place.

## Scope And Budget

Complete B1B's semantic guards with the lexical model already reviewed for R1.
Allowed files are `backend/scripts/coverage_policy.py`,
`backend/tests/test_coverage_contract.py`, and WS-QUAL/global memory. Parser or
B2 work, docs, configuration, workflows, evidence, `backend/app/**`, DB/API,
product/AUTH behavior, skips/xfails, exclusions, and coverage-raising tests are
forbidden.

The candidate is capped at 350 non-memory lines from merge base: existing B1B
223, lint-clean shared resolver through 290, adversarial matrix through 340,
and 10 reserve. Checkpoint at or before 310 before the remaining matrix. Stop
above 350 or if proof cannot fit. R2 permits at most two review repair cycles;
a same-class finding after cycle two or any outside-scope finding stops/replans.

## Binding Contract

- One shared AST resolver serves skip/xfail weakening and deleted-assertion
  analysis across module, function, class, and nested scopes.
- Parameters and whole-function locals shadow outer bindings. Imports, simple
  and other name-store assignments, reassignment order, `global`, `nonlocal`,
  and class-method non-closure follow Python lexical behavior. Conditional or
  dynamic ambiguity that can retain a framework binding fails closed.
- Resolve direct and aliased pytest/unittest modules and members. Detect genuine
  skip/xfail/importorskip, unittest decorators/exceptions, and deleted
  `pytest.raises` calls, including multiline calls.
- `self.skipTest` and `super().skipTest` require a resolved TestCase subclass;
  another receiver requires direct or aliased TestCase construction. Arbitrary
  local `.skipTest()` and shadowed pytest/raises names remain accepted.
- Preserve committed test-rename rejection, base-AST line mapping, native/self
  assertion deletion, inert strings/comments, root-helper reuse, cwd restore,
  global/WS-QUAL memory scope, and exact size enforcement. Restore the weakened
  local-lookalike expectation; no test may be rewritten for broader behavior.

## Verification And Review

Run the complete B1B commands plus nested, parameter, before/after assignment,
conditional, `global`/`nonlocal`, class non-closure, TestCase, and local
lookalike matrices. Required reviewers: senior engineering, QA/test,
security/auth, product/ops, architecture, CI integrity, reuse/dedup, and test
delta. Human focus: exact binding behavior, genuine tests, size, and no B2/AUTH
spill.

Stop after R2. Do not start 01B2 or chunk 02. AUTH continues independently.
