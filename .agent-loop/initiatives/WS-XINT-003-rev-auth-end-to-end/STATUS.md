# Status: WS-XINT-003 REV-AUTH End-to-End Contract

## Current status

WS-XINT-003-01 contract reconciliation is complete and awaiting human
review/merge. No runtime code or action availability is changed.

## Baseline

- Planning branch began from `origin/main` at `99dc0b34` after AUTH-12D merged.
- Existing REV actions remain planned/unreleased as product surfaces.
- XINT-002 remains the owner of review artifact materialization/binding and
  human-review submission-artifact activation.

## Main finding

REV-03P and AUTH-12D2 overlap around review/revision policy persistence and
mutation. The first implementation wave must settle one persistence path:
REV-owned semantics with AUTH-owned mutation authorization.

## Current reconciliation

- `ACTION_CUSTODY.md` is the canonical action/principal/resource/wave table.
- REV-03P and AUTH-12D2 name one future append-only policy writer path.
- XINT-002-07 is split into 07A availability and 07B evaluator extension.
- All registered review actions remain planned; four lifecycle/recovery actions
  remain missing until 08R; no service identity is provisioned by chunk 01.

## Next step

Open the chunk-01 PR, run hosted exact-head gates, address external review, and
obtain human merge. Then stop before runtime policy work in WS-XINT-003-02.
