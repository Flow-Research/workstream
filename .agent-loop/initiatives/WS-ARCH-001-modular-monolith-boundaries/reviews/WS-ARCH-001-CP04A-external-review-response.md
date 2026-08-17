# WS-ARCH-001-CP04A External Review Response

## Reviewed target

- External finding target: `965ef61e8e5715979867e8aea2a1649f71c0e130`
- Pull request: `#348`
- Scope: executable-contract correction only; no runtime implementation

## Comments addressed

- CodeRabbit found that the governing acceptance checklist still named only
  CONTRIBUTIONS/COMPENSATION even though the detailed coverage atom covered
  every changed CP04A application surface. Exact-head replay then found that
  the same summary checklist grouped other independently failing behaviors.
  The duplicate grouped checklist is removed: every atomized row in the
  acceptance-to-test map is now explicitly an independently required governing
  criterion with its own named proof and execution custody.
- Coverage proof omitted changed COMPENSATION composition/schema surfaces and
  combined the focused 90-percent requirement with the repository-wide
  78-percent baseline. The contract now names all changed production packages
  in one coverage collection, enforces 90 percent with a separate report for
  every changed application surface, and gives the global 78-percent baseline
  a separate atom, command/custody, and CI-integrity ownership.
- Compound trace rows could hide independently failing behavior. The contract
  now separates acceptance versus duplicate rejection, active versus
  same-project resources, transition shape versus operation uniqueness, each
  immutable-event database guard, file size versus test behavior, focused
  versus global coverage, and the remaining compound negative-scope/resource
  cases found during replay. A second test-delta replay identified remaining
  compound public-view, owner-port, graph-replacement, close, recovery, and
  concurrency rows; those are now split as well.
- The canonical `CompensationInstrumentType` home was ambiguous. The contract
  now requires the dedicated public module
  `app.modules.compensation.api.instruments`, re-exported by the package while
  private COMPENSATION schemas and external consumers import the public source.

## Comments deferred

None.

## Human decisions needed

None beyond normal approval and merge authority. The corrections do not alter
the approved product lifecycle or activate runtime behavior.

## Commands rerun

Corrective head `77f615f8` passed diff, Markdown, stale-wording, active-state,
chunk-state, architecture, security, product/operations, QA, test-delta, and
CI-integrity review. The final metadata head must replay exact-head closure and
hosted GitHub gates before merge readiness is claimed.

## Remaining risks

The named tests and coverage commands are future implementation obligations.
Their semantic adequacy must be reviewed against the implementation diff; this
planning response is not runtime proof.

## PR #349 adversarial implementation replay

All five findings reported against head `58b977ac` were replayed and found
valid:

- `project_points` now requires integer scale, so `1.0` is rejected before
  owner locking or authorization;
- CONTRIBUTIONS verifies the exact binding ID and instrument type returned by
  the COMPENSATION public owner port, not only its project ID;
- malformed rule objects are type-checked before field access and return the
  concealed domain conflict;
- a real PostgreSQL test stages authorization evidence, flushes the complete
  product graph and event, then forces a late failure and proves transaction
  rollback removes every effect;
- misleading fake-handle claims were removed. CP04A proves port rejection and
  close/no-product-effect behavior; CP05/AUTH owns genuine handle-binding
  semantics.

Fresh exact-head review and hosted CI are required after these corrections.

A subsequent reuse review found that CP04A had duplicated but weakened the
existing CONTRIBUTIONS quantity bounds. The schema and hidden behavior now use
one canonical validator for positivity, canonical form, maximum magnitude,
maximum scale, and integer-scale project points. Overflow and over-scale input
is rejected before owner locks, authorization, or graph replacement. This
finding invalidates all earlier exact-head receipts until replayed.

## PR #349 substantive CodeRabbit replay

CodeRabbit's eight threads against `3ee52b65` were replayed rather than applied
mechanically. All eight were valid:

- nullable event-state and attribution comparisons are now NULL-safe, with
  direct PostgreSQL regression proof;
- lifecycle events now enforce composite policy/project and
  version/policy/project ownership in ORM and migration truth;
- cross-project read concealment now exercises the real repository;
- create-draft owner mismatch returns concealed `not_found`;
- update-draft always type-checks its required version selector;
- boundary proof uses the repository's AST import scanner;
- project, binding, and instrument owner-fact mismatches have exact tests; and
- ARCH status records hidden CP04A behavior and continued unavailability.

The schema-validation nit was also valid: its first pass no longer uses
`assert` or a fake money instrument. The suggestion to consume AUTH before
owner-resource locking was not applied because it contradicts the approved
fail-closed order and would authorize before exact owner-held resource facts
are fenced against time-of-check/time-of-use drift.

These changes make every earlier review and CI receipt historical. Fresh
exact-head review and hosted CI are required before merge readiness is claimed.
