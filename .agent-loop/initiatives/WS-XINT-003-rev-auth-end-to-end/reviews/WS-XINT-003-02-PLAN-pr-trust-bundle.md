# PR Trust Bundle: WS-XINT-003-02 Planning Refresh

## Goal and result

Reconcile the policy portion of the REV-AUTH plan with current main before any
runtime change. The result splits the retired 02 parent into one bounded,
implementation-ready persistence child (02A) and a later non-implementable
authorization/route activation child (02B).

## Scope

Planning and contract Markdown only. No runtime code, migration, route,
catalogue availability, contribution behavior, workflow, dependency, test, or
coverage configuration changed.

## Design

- 02A adopts the existing ReviewPolicy and RevisionPolicy tables as immutable,
  append-only REV history on migration head 0045 and removes four unused legacy
  callables. It activates nothing.
- 02B later adds exact guide-scoped routes, consumes AUTH PREP against locked
  facts, and activates only the two policy actions.
- 02B deliberately generalizes the existing guide replay ledger into one
  closed project-mutation replay ledger while preserving guide replay rows; it
  forbids alternate, policy-only, or in-memory replay paths.
- 02B cannot be implemented until 02A merges and its exact files, migration,
  symbols, and verification commands are refreshed from then-current main.
- Reviewer contribution and accept-only submitter contribution remain a later
  typed CON boundary. This planning refresh changes no contribution policy,
  record, award, fulfillment, or reputation behavior.

## Proof

All deterministic documentation checks pass. The exact existing authorization
tests proving planned policy-action closure and closed project-mutation resource
contexts pass: 2 passed, 378 deselected.

## Internal review

Architecture, QA/product, and security/docs/CI all pass after their valid
findings were corrected. No reviewer session remains open.

## CI and external review

No CI surface changed or weakened. GitHub Actions must run the full suite and
repository-wide coverage on the exact PR head. CodeRabbit comments must be
resolved before human merge.

## Remaining risks

02A is L1 database work and must prove lossless migration/downgrade refusal,
append-only enforcement, activation-race safety, and at least 90 percent focused
changed-subsystem coverage. 02B remains intentionally unavailable for start.

## Human review focus

Confirm the REV-owned persistence versus AUTH-owned mutation boundary, the
single replay architecture, exact guide lineage, absence of activation, and the
stop after 02A.

## Human merge ownership

Only the human may merge this PR.
