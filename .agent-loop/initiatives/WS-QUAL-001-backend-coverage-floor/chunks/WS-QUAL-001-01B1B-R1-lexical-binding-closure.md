# Chunk Contract: WS-QUAL-001-01B1B-R1 Lexical Binding Closure

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: stopped at the first size checkpoint. The resolver-only draft measured
282 lines before the required matrix, so the 300-line cap could not preserve
proof. Superseded by B1B-R2; do not resume.

## Goal And Scope

Complete the semantic delta guards using lexical binding rather than
file-global alias sets. Preserve all passing B1B repository, assertion-span,
rename, scope, size, and cwd behavior.

Risk: L1 test/CI integrity. SLA: P1. Allowed implementation files are
`backend/scripts/coverage_policy.py`, `backend/tests/test_coverage_contract.py`,
and WS-QUAL/global process evidence. Parser redesign, B2, docs, live config,
workflow/evidence mutation, `backend/app/**`, DB/API/product/AUTH behavior,
skips/xfails, exclusions, and coverage-raising tests remain forbidden.

The complete replacement candidate is capped at 300 non-memory lines from
merge base. The existing candidate is 223 lines. Forecast: replace the two
file-global analyzers with one shared resolver for at most 30 net lines, add
the binding/TestCase matrices for at most 40 net lines, and retain 7 lines of
reserve. Checkpoint at or before 270 lines, before adding the remaining matrix;
stop above 300 or if the forecast cannot preserve the required proof.

R1 resets the stopped B1B repair count because its reviewed contract replaces
the binding model. It permits at most two implementation-review repair cycles.
Any valid same-class finding remaining after cycle two requires another stop
and replan; any valid finding outside this corrective scope stops immediately.

## Acceptance Criteria

- Implement one shared static binding resolver used by both weakening and
  deleted-assertion analysis. It covers module, function, class, and nested
  scopes; parameters; imports and aliases; simple/annotated/augmented
  assignment and other name-store targets; and reassignment in statement
  order. Function-local names are determined for the whole function;
  `global`/`nonlocal` route to their declared scope, and method bodies do not
  inherit the class namespace as a closure.
- Bindings are classified as framework module/member, proven TestCase class or
  instance, local, or ambiguous. Conditional paths merge classifications;
  star imports, dynamic binding, or unresolved control-flow combinations that
  can retain a framework classification fail closed. A definite parameter or
  local reassignment is local before/after the relevant call as Python scope
  and statement order require.
- A local or parameter binding that shadows `pytest`, a module alias, or an
  imported `raises`/skip name must be treated as local, not framework behavior.
- Detect genuine pytest skip/xfail/importorskip and unittest skip decorators
  and exceptions. `self.skipTest` and `super().skipTest` are proven only inside
  a class whose base resolves to `unittest.TestCase` or its direct alias;
  another receiver is proven only when its binding comes from direct or
  aliased `TestCase` construction. Arbitrary local `.skipTest()` methods remain
  accepted.
- Base-AST deleted assertion detection must apply the same lexical resolution
  to direct/imported/module-aliased `pytest.raises` while preserving multiline
  native/self assertions and inert/local-lookalike acceptance.
- Preserve real committed rename rejection, root helper reuse, cwd restoration,
  exact global/WS-QUAL memory scope, and the implementation cap.
- Restore the local-lookalike test to its original non-weak expectation; tests
  may not be rewritten to accept broader guard behavior.

## Verification And Review

Run the complete B1B verification command set plus adversarial nested-scope,
parameter-shadow, before/after assignment-shadow, conditional ambiguity,
`global`/`nonlocal`, and recognized/unrecognized class/TestCase matrices.
Required reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, reuse/dedup, and test delta. Human focus: lexical
false positives/negatives, no weakened expectations, and no B2/AUTH spill.

Stop after R1. Do not start 01B2 or chunk 02. AUTH-02 may continue independently
in its already-authorized worktree.
