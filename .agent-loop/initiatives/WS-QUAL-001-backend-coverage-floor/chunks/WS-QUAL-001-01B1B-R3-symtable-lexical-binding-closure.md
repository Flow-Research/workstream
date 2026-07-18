# Chunk Contract: WS-QUAL-001-01B1B-R3 Symtable Lexical Binding Closure

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: blocked at 468/500 after cycle-zero review. Cycle-one repair lacked
credible proof within 32 lines, so no repair was attempted. Superseded by R4.

## Scope And Allocation

Complete semantic test-delta guards using stdlib `symtable` for lexical facts
and bounded AST value flow for pytest/unittest provenance. Allowed files are
`backend/scripts/coverage_policy.py`, `backend/tests/test_coverage_contract.py`,
and WS-QUAL/global memory. B2/parser work, docs, config, workflows, evidence,
`backend/app/**`, DB/API/product/AUTH behavior, skips/xfails, exclusions, and
coverage-raising tests are forbidden.

Use the normal 500-line L1 cap from merge base: existing reviewed candidate 348,
symtable resolver and control joins through 420, reproduced/adversarial matrix
through 480, and 20 reserve. Checkpoint at or before 440 before the remaining
matrix. Stop above 500 or if proof cannot fit. R3 permits two implementation
review repair cycles; any same-class finding after cycle two or any outside-
scope finding stops/replans.

## Acceptance Criteria

- `symtable` is authoritative for module/function/lambda/comprehension/class
  namespaces, parameters including varargs/kwargs, whole-function locals,
  globals/nonlocals, exception/loop/with targets, and class non-closure.
- Within each parent scope, pair AST scope-creating nodes with
  `SymbolTable.get_children()` in source traversal ordinal. Validate expected
  table type, normalized name, and line, consume each child exactly once, and
  fail closed on missing, mismatched, or extra children; do not use a
  collision-prone `(name, line)` lookup.
- On the locked Python 3.12 runtime, list/set/dict comprehensions are compiler-
  inlined and emit no child table. Isolate only their AST binding targets while
  leaving outer iterable evaluation in the parent scope. Generator expressions
  must consume a validated `genexpr` child. Any unexpected emitted child or
  missing/mismatched generator child fails closed.
- AST value flow classifies framework modules/members, TestCase class/instance,
  local, and ambiguity. Imports, assignment/annotation/named expressions,
  decorators, `pytestmark` scalar/list forms, and If/loop/try/match joins are
  handled; paths retaining framework provenance fail closed.
- Try handlers, match cases, loop body/else, and equivalent alternatives are
  evaluated from independent incoming states before joining. Attribute and
  subscript assignment bases are loads, not binding targets; augmented writes
  and match captures follow their actual symbol-table ownership.
- Detect genuine skip/xfail/importorskip and unittest behavior. `skipTest`
  requires a resolved TestCase receiver or ambiguous path retaining one;
  arbitrary locals remain accepted. Builtin `exec` fails closed, while a
  definite local/parameter named `exec` remains accepted.
- Deleted native/self/pytest-raises assertions use the same resolver, including
  multiline calls and every scope/shadow/control case. Preserve inert strings,
  committed rename rejection, base-line mapping, root helpers, cwd restoration,
  exact memory scope, and size enforcement. No weakened tests.
- With `from __future__ import annotations`, non-executable annotations are not
  traversed as runtime expressions or paired to nonexistent child tables.

## Verification And Review

Run all B1B checks and regressions for lambda, varargs/kwargs, comprehensions,
exception targets, nested classes, annotations, loops/try/match, `pytestmark`,
shadowed `exec`, TestCase ambiguity, and deleted raises. Include two same-line
lambdas/comprehensions and repeated same-name definitions to prove ordinal
scope-table pairing. Required reviewers:
senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, reuse/dedup, and test delta.

Stop after R3. Do not start B2 or chunk 02. AUTH continues independently.
