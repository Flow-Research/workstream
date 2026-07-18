# Chunk Contract: WS-QUAL-001-01B1B-R7 Iterable Provenance

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: all ten internal plan-review tracks passed at `f0134aa`; implementation
started under the user's parallel coverage/AUTH direction on 2026-07-13.

## Scope And Allocation

Replace ad hoc iterable substitution and consumption allowlists with one
recursive provenance abstraction. Allowed files are
`backend/scripts/coverage_policy.py`, `backend/tests/test_coverage_contract.py`,
and WS-QUAL/global memory. B2/parser, docs, config, workflow, evidence,
`backend/app/**`, DB/API/product/AUTH, skips/xfails, exclusions, and coverage-
raising tests remain forbidden.

Cap the complete candidate at 950 lines from merge base: existing 800, policy
replacement through 870, regression matrix through 920, and 30 reserve.
Checkpoint at or before 890 before remaining tests. Stop above 950 or if proof
cannot fit. R7 permits two repair cycles; a same-class finding after cycle two
or any outside-scope finding stops/replans.

## Acceptance Criteria

- One recursive `element provenance` abstraction handles tuple/list/set
  elements, dict keys, and list/set/dict comprehension or genexpr elements.
  Comprehension target bindings are derived recursively from each generator's
  iterable and applied when resolving the yielded element, including nested
  unpacking and mixed framework/local values. Deleted raises uses the same path.
- Generator consumption is structural: for/comprehension iteration consumes
  its iterable, and explicitly eager consumers propagate genexpr bodies without
  a brittle closed builtin list. Lazy/unconsumed genexpr bodies remain pruned.
- Reachability walks every generator clause in order. A literal-empty clause
  prevents later clauses/body effects; reachable eager clauses propagate outer-
  owned walrus effects. No first-generator-only approximation.
- Eager class bodies propagate only declared-global Assign/AnnAssign/NamedExpr,
  Import/ImportFrom, and AugAssign effects to loop fixed points. Ordinary class
  attributes remain isolated.
- Preserve exact evaluation order, single AST/symtable consumption, progressive
  normal handler tests, sequential TryStar, target load/store separation,
  future/local annotations, fixed-point aliases/TestCase, optional writes,
  pytestmark/exec, rename, deleted/native/self assertions, cwd/root/memory, and
  size behavior. No weakened tests.

## Verification And Review

Run all B1B/R6 checks plus passthrough and transformed gen/list/set/dict
iterables, set/dict literals and keys, mixed nested elements, nested structural
generator consumers, later-empty comprehension clauses, class-global import/
from-import/AugAssign, and deleted-raises counterparts. Required reviewers:
senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, reuse/dedup, and test delta.

Stop after R7. Do not start B2 or chunk 02. AUTH continues independently.
