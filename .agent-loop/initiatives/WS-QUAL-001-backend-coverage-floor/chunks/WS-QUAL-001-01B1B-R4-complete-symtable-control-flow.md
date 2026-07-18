# Chunk Contract: WS-QUAL-001-01B1B-R4 Complete Symtable Control Flow

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: blocked at 535/550 during cycle-zero implementation review. Superseded
by B1B-R5; retain as review history and do not repair in place.

## Scope And Allocation

Finish the reviewed symtable resolver's reproduced control/value-flow gaps.
Allowed files are `backend/scripts/coverage_policy.py`,
`backend/tests/test_coverage_contract.py`, and WS-QUAL/global memory. B2/parser,
docs, config, workflow, evidence, `backend/app/**`, DB/API/product/AUTH, skips,
xfails, exclusions, and coverage-raising tests remain forbidden.

Cap the complete candidate at 550 lines from merge base: existing 468, policy
repair through 515, regression matrix through 535, and 15 reserve. Checkpoint
at or before 520 before remaining tests. Stop above 550 or if proof cannot fit.
R4 permits two repair cycles; a same-class finding after cycle two or any
outside-scope finding stops/replans.

## Acceptance Criteria

- Retain stdlib `symtable` lexical authority and deterministic ordinal child
  consumption. Python 3.12 list/set/dict comprehensions use isolated generator-
  clause target frames because the compiler emits no child; genexpr must consume
  a validated child. Walrus targets bind the containing module/function per
  symtable, including nested inlined-comprehension regressions.
- Evaluate try body progress, each handler, else, and loop/match alternatives as
  independent executable paths. A handler conservatively includes provenance
  written before a possible exception. Join alternatives before applying the
  mandatory `finally` region. Any framework-retaining path fails closed.
- Bind only true Name/Starred/tuple/list assignment targets; attribute/subscript
  bases remain loads. Cover augmented writes, annotations, named expressions,
  with/exception targets, and match captures at their symtable-owned scope.
- Preserve chained ambiguity through `.mark`, `.TestCase`, construction, and
  `.skipTest`. With future annotations, do not traverse postponed annotation
  expressions or expect child tables. Builtin `exec` remains blocked while a
  definite shadow remains accepted.
- The same resolver protects deleted raises across all cases. Preserve every
  passing rename, base-line, native/self assertion, cwd, root-helper, memory,
  and size invariant. Tests remain genuine and may not be weakened.

## Verification And Review

Run all B1B/R3 checks plus regressions for multi-handler try with progressive
body provenance/finally, multi-case match, loop else, exact assignment targets,
AugAssign, match capture, chained mark/TestCase ambiguity, future annotations,
and nested inline-comprehension walrus ownership. Required reviewers: senior
engineering, QA/test, security/auth, product/ops, architecture, CI integrity,
reuse/dedup, and test delta.

Stop after R4. Do not start B2 or chunk 02. AUTH continues independently.
