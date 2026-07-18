# Chunk Contract: WS-QUAL-001-01B1B-R5 Single-Pass Abstract Flow

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: blocked at 641/650 during cycle-zero implementation review. Superseded
by B1B-R6; retain as review history and do not repair in place.

## Scope And Allocation

Replace path replay with single-consumption abstract flow while preserving the
reviewed symtable lexical resolver. Allowed files are
`backend/scripts/coverage_policy.py`, `backend/tests/test_coverage_contract.py`,
and WS-QUAL/global memory. B2/parser, docs, config, workflow, evidence,
`backend/app/**`, DB/API/product/AUTH, skips/xfails, exclusions, and coverage-
raising tests remain forbidden.

Cap the complete candidate at 650 lines from merge base: existing 535, policy
replacement through 600, regression matrix through 630, and 20 reserve.
Checkpoint at or before 610 before remaining tests. Stop above 650 or if proof
cannot fit. R5 permits two repair cycles; a same-class finding after cycle two
or any outside-scope finding stops/replans.

## Acceptance Criteria

- The semantic visitor consumes every AST and emitted symtable child exactly
  once. Alternative paths receive joined abstract incoming provenance; they
  never re-run a subtree or advance its child cursor twice. Try handlers receive
  conservative progressive body provenance, match cases retain failed-guard
  effects, and `finally` is applied once after joined alternatives.
- A separate cursor-neutral loop summary may inspect binding statements before
  the single semantic body visit. It is pure, scope-pruned, never enters nested
  function/lambda/class/comprehension scopes, never advances a child cursor,
  and never classifies calls. Definite or conditional later framework bindings
  enter the loop header as possible/ambiguous provenance, so next-iteration
  calls fail closed. Join zero/body/else outcomes without semantic replay.
- One recursive assignment helper pairs tuple/list RHS elements through nested
  unpacking, binds only Name/Starred/tuple/list targets, and visits executable
  Attribute/Subscript bases and indexes. Reuse it for normal, annotated,
  augmented, loop, with, exception, and comprehension targets.
- Inline-comprehension generator-clause targets are local; walrus effects bind
  the containing real lexical scope and reset across nested lambdas/functions.
  Comprehension body effects are optional, including zero iterations and lazy
  genexpr execution, and join with the incoming state.
- Preserve chained ambiguity, future-annotation suppression, pytestmark,
  builtin/shadowed exec, TestCase proof, and the same deleted-raises resolver.
  Function-local variable annotations are non-executable and are not traversed
  even without the future import; module/class annotations remain executable
  unless postponed.
  Preserve rename, base-line/native/self assertion, cwd, root-helper, memory,
  and size invariants. Restore the empty-comprehension expectation to genuine
  framework-skip detection; no weakened tests.

## Verification And Review

Run all B1B/R4 checks plus nested def/lambda/genexpr in every control region,
loop-carried call-before-import, failed match guard effects, target base/index
loads, nested unpacked module/raises provenance, nested inline lambda walrus,
zero/lazy comprehension effects, function-local versus module/class annotation
execution, and deleted-raises counterparts. Required
reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, reuse/dedup, and test delta.

Stop after R5. Do not start B2 or chunk 02. AUTH continues independently.
