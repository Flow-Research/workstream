# Chunk Contract: WS-QUAL-001-01B1B-R6 Provenance Closure

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: blocked at 800/800 after cycle-one implementation review. Superseded by
B1B-R7; retain as review history and do not repair in place.

## Scope And Allocation

Close the reviewed single-pass resolver with transitive provenance and exact
evaluation order. Allowed files are `backend/scripts/coverage_policy.py`,
`backend/tests/test_coverage_contract.py`, and WS-QUAL/global memory. B2/parser,
docs, config, workflow, evidence, `backend/app/**`, DB/API/product/AUTH,
skips/xfails, exclusions, and coverage-raising tests remain forbidden.

Cap the complete candidate at 800 lines from merge base: existing 641, policy
closure through 720, regression matrix through 770, and 30 reserve. Checkpoint
at or before 740 before remaining tests. Stop above 800 or if proof cannot fit.
R6 permits two repair cycles; a same-class finding after cycle two or any
outside-scope finding stops/replans.

## Acceptance Criteria

- Replace duplicate loop RHS heuristics with one shared cursor-neutral,
  scope-pruned provenance summary. Iterate bindings to a fixed point so alias
  chains, TestCase construction, direct/imported raises, conditional bindings,
  and later assignments all enter the loop header as possible provenance.
- The summary prunes nested bodies but inspects outer-evaluated function
  defaults/decorators, class decorators/bases/keywords, and required iterable
  expressions. It ignores function-local annotations and lazy/unconsumed
  comprehension/genexpr bodies; containing-scope walrus effects are included
  only where execution can occur before the next-iteration use.
- Propagate iterable element provenance through for/comprehension targets,
  including nested unpacking. Shared target traversal visits executable
  Attribute/Subscript bases/indexes and never binds their load Names. Deleted
  raises uses identical provenance.
- Preserve Python 3.12 evaluation order: AnnAssign RHS, target base/index, then
  executable annotation; AugAssign target base/index before RHS; exception type
  before `as` binding. Function-local/postponed annotations remain suppressed.
- Normal try handlers retain progressive mutually exclusive flow. TryStar is a
  separate sequential handler-carried flow because multiple `except*` handlers
  can execute. Every syntax/symtable child remains consumed once.
- Preserve all passing control joins, optional comprehension writes, chained
  ambiguity, pytestmark/exec/TestCase, rename, base-line/native/self assertion,
  cwd, root-helper, memory, and size behavior. No weakened tests.

## Verification And Review

Run all B1B/R5 checks plus transitive alias/TestCase chains, outer-evaluated
defaults/decorators/bases, annotation/lazy-summary negatives, iterable target
module/raises provenance, target-evaluation walrus ordering, exception-type
ordering, sequential mixed `except*`, nested lexical nodes in every control
region, and deleted-raises counterparts. Required reviewers: senior
engineering, QA/test, security/auth, product/ops, architecture, CI integrity,
reuse/dedup, and test delta.

Stop after R6. Do not start B2 or chunk 02. AUTH continues independently.
