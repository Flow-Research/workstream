# PR Trust Bundle: WS-ENG-007-00R4

## Intent

Allow a signed start for an idle initiative after another initiative becomes the
latest global merge, without attaching one PR's protected evidence to another
initiative's lifecycle.

## Scope

- Keep the latest global merge and its protected evidence unchanged.
- Validate the selected initiative's authority projection independently.
- Bind that projection byte-for-byte to its prior signed ledger basis.
- Add updater and independent-checker regressions for the exact failure.

## Reviewed Revision

`c59bff278945c3d8e63a6ea776a6bf6206df8af8`

## CI Integrity

- No workflow, permission, required check, coverage floor, test, reviewer, signed
  start, or human merge checkpoint was removed or weakened.
- The exact updater gate passes 289 tests at 90.18 percent branch coverage.
- The exact independent-checker gate passes 296 tests at 90.40 percent branch
  coverage.

## Reviewer Result

All nine required internal tracks passed after fixes. No Critical or High
finding remains open.

## Human Review Focus

- Confirm authority projection validation no longer constructs a synthetic merge
  record with foreign protected evidence.
- Confirm source/completed identity remains bound to the prior signed initiative
  record by both transition validators.
- Confirm malformed authority metadata fails closed in updater and checker.
- Confirm no successor starts automatically.

## Remaining Risk

A new `main` merge before this recovery lands requires the branch and evidence to
be refreshed normally; the signed event still requires exact current `main`.
