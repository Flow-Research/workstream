# WS-AUTH-003-01 External Review Response

## Comments addressed

- Replaced generic initiative and chunk lifecycle wording with AUTH
  module-boundary-specific states.
- Added the omitted exact assertion-inventory test node to behavior ownership.
- Canonicalized blank human service identities to `None` and rejected resource
  identifiers outside the public `UUID | str` contract.
- Corrected relative-import resolution for package initializers.
- Rejected dynamic import recovery through `sys.modules`, including `sys`
  aliases and computed access, and through standard-library dynamic loader
  modules (`imp`, `importlib`, `pkgutil`, `pydoc`, `runpy`, and `zipimport`).
- Rejected reordered trusted behavior-ownership assignments even when their
  authority digest is recomputed.
- Guarded non-string structural-policy digests with the mapped ledger error.
- Replaced eager `setdefault` inventory construction with a real cache lookup.

## Comments deferred

None.

## Human decisions needed

None. The findings tighten the already approved boundary contract without
moving runtime product behavior.

## Commands rerun

- Focused Ruff: passed.
- AUTH import-boundary validator: passed.
- AUTH test-structure validator: passed.
- Behavior-ownership validator: passed.
- Boundary, structure, and ownership tests: 175 passed.
- CI-integrity re-review: passed.
- Security re-review: passed after five focused bypass-probe rounds.
- Exact-head hosted CI: passed on the corrective implementation head; the final
  status-only head must preserve the same result.

## Remaining risks

The import and structural ledgers intentionally freeze legacy debt. Later
capability chunks must continue shrinking exact edges and oversized proof debt.
