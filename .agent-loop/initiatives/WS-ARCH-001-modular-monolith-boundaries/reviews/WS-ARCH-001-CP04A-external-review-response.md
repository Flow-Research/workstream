# WS-ARCH-001-CP04A External Review Response

## Reviewed target

- External finding target: `965ef61e8e5715979867e8aea2a1649f71c0e130`
- Pull request: `#348`
- Scope: executable-contract correction only; no runtime implementation

## Comments addressed

- CodeRabbit found that the governing acceptance checklist still named only
  CONTRIBUTIONS/COMPENSATION even though the detailed coverage atom covered
  every changed CP04A application surface. The checklist now has two separate
  requirements: each changed application surface must independently meet 90
  percent through its named focused report, and hosted repository-wide
  coverage must independently preserve the protected 78-percent baseline.
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
