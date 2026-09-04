# WS-CON-001 — Contribution and conditional compensation

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: hidden policy behavior.
- Intent: turn accepted work into immutable ContributionRecords and optional
  project-policy-driven compensation awards without coupling lifecycle truth to
  an economic provider.
- Next usable boundary: prepare CP05 activation, then guide-activation
  validation/persistence before task readiness.
- Governing sources: `docs/spec_contribution_compensation.md`,
  [`CONFORMANCE.md`](CONFORMANCE.md), code, migrations, and tests.
- Preserve: exact policy-version lineage, no claim-time drift, decimal-string
  quantity integrity, atomic REV/CON effects, and no runtime reputation
  projection in v0.1.

## Delivered

- Shared outbox, adapter-binding persistence and hidden lifecycle behavior,
  contribution-policy persistence and hidden draft/publication/retirement
  behavior, and shared lifecycle-audit participation are merged.
- Finance Authority adapter-binding actions are active; five policy actions
  remain unavailable. ContributionRecord, award, dispatch, fulfillment, and
  public CON behavior are not yet complete.

## Remaining v0.1 sequence

1. CP05 activates only the merged hidden policy behavior.
2. CP06 validates the frozen policy; CP07 binds it to ProjectGuide; CP08 locks
   it through TaskAssignment and Submission; CP09 removes the replaced legacy
   economic path after replacement activation.
3. Add ContributionRecord/CompensationAward persistence after stable REV FK
   targets, then the atomic REV/CON decision participant before live decisions.
4. Add dispatcher, fulfillment, reconciliation, and product reads only after
   their exact AUTH service identities and actions exist.
